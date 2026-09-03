---
title:  "CUDA Streams and Host/Device Overlap"
date:   2026-09-02
categories: ["gpu"]
tags: ["gpu", "cuda", "nvidia", "streams", "overlap", "performance"]

---

# CUDA Streams and Host/Device Overlap

The [previous note](/gpu/2026-09-02-1-cuda-reduction) covered reduction, the first parallel algorithm on the GPU side. This note moves to the **host-device boundary**: how to keep the GPU busy while the CPU prepares the next batch of data, and how to overlap data movement with computation.

So far, every kernel launch and every `cudaMemcpy` has been synchronous. The host waits, the GPU works, the host waits again. CUDA **streams** let you break that pattern.

---

## 1. The default stream is synchronous

Every CUDA operation happens in a stream. If you do not specify one, it runs in the **default stream** (also called stream 0 or the null stream).

The default stream behaves as if it is synchronous with respect to the host:

- `cudaMemcpy` in the default stream blocks the host until the copy completes.
- A kernel launch in the default stream returns immediately, but the next default-stream operation waits for the previous one.

```text
Default stream timeline:

Host:  memcpy H2D  →  kernel  →  memcpy D2H  →  next batch
GPU:   copy        →  run     →  copy

The GPU is idle during host preparation time.
```

This is simple and correct, but it leaves performance on the table. While the GPU is running the kernel, the host could be preparing the next input. And while the GPU is computing one batch, the copy engine could be moving the previous batch's results back.

> Here is what actually happens sequentially when you execute that loop:

### Step-by-Step Breakdown over Time

```
Time ───►

CPU: [BLOCKS on H2D] ────────► [Launch] [BLOCKS on D2H] ──────────────────────► [Prep Batch 2]
GPU: [Copy H2D Engine] ──────► [Compute Core Runs Kernel] ──► [Copy D2H Engine] ──► [GPU IDLE!]

```

1. **`cudaMemcpy(H2D)`:** The CPU calls `cudaMemcpy`. Because `cudaMemcpy` is a synchronous blocking call, **the CPU completely freezes**. It sits idle waiting for the GPU copy engine to finish moving data from Host RAM to VRAM.
2. **`kernel<<<...>>>()`:** The CPU wakes up, issues the kernel launch command to the GPU queue (which takes a fraction of a microsecond), and immediately moves to the next line.
3. **`cudaMemcpy(D2H)`:** The CPU calls `cudaMemcpy` to get results back. Because it is blocking, **the CPU freezes again**. It sits doing nothing while:
* The GPU computes the kernel.
* The GPU copy engine transfers the output back to Host RAM.


4. **Host Preparation:** The CPU finally wakes up and prepares Batch 2 (e.g., loading images from disk, preprocessing). During this entire CPU preparation phase, **the GPU compute cores and copy engines sit 100% idle!**

---

### Why Performance is Left on the Table

In the default stream, three physical hardware engines exist on your system, but **only ONE runs at any given second**:

| Hardware Engine | Status during H2D Copy | Status during Kernel Run | Status during CPU Prep |
| --- | --- | --- | --- |
| **CPU Core** | 🛑 Blocked | 🛑 Blocked | ⚡ **Active** |
| **GPU Copy Engine** | ⚡ **Active** | 🛑 Idle | 🛑 Idle |
| **GPU Compute Core (SMs)** | 🛑 Idle | ⚡ **Active** | 🛑 Idle |

Because execution is strictly serialized, total runtime is simply the **sum of all steps added together**:


---

## 2. What a stream is

A **stream** is an ordered sequence of CUDA operations issued to the GPU. Operations within a single stream execute in the order they were issued. Operations in different streams may run concurrently, depending on GPU resources.

Think of a stream as a FIFO command queue:

```text
Stream 1:  memcpy H2D → kernel A → memcpy D2H
Stream 2:  memcpy H2D → kernel B → memcpy D2H
Stream 3:  memcpy H2D → kernel C → memcpy D2H
```

The GPU can execute commands from multiple streams at the same time if it has:

- copy engines available for transfers,
- SMs available for kernels,
- no explicit synchronization forcing serialization.

---

## 3. Creating and using streams

Streams are created and destroyed with `cudaStreamCreate` and `cudaStreamDestroy`.

```cpp
cudaStream_t stream1, stream2;
cudaStreamCreate(&stream1);
cudaStreamCreate(&stream2);

kernel<<<grid, block, 0, stream1>>>(d_a, n);
kernel<<<grid, block, 0, stream2>>>(d_b, n);

cudaStreamDestroy(stream1);
cudaStreamDestroy(stream2);
```

The `0` in `<<<grid, block, 0, stream>>>` is the shared-memory bytes per block (dynamic shared memory, not used here). The fourth argument is the stream.

```text
Kernel launch syntax:

<<<gridDim, blockDim, sharedMemBytes, stream>>>
```

If you omit the last two arguments, CUDA uses 0 shared memory and the default stream.

---

## 4. Asynchronous memory transfers with cudaMemcpyAsync

`cudaMemcpy` is synchronous. The asynchronous version is `cudaMemcpyAsync`:

```cpp
cudaMemcpyAsync(dst, src, bytes, kind, stream);
```

It submits the copy to the stream and returns immediately. The host can then do other work or enqueue more operations. The actual transfer happens asynchronously with respect to the host, but in order with respect to other operations in the same stream.

**Important:** `cudaMemcpyAsync` requires **pinned host memory** (page-locked memory). Pinned memory cannot be swapped out by the OS, so the GPU's DMA engine can read/write it directly. Regular `malloc` memory is pageable and cannot be used with `cudaMemcpyAsync`.

Use `cudaMallocHost` or `cudaHostAlloc` to allocate pinned memory:

```cpp
float *h_a;
cudaMallocHost(&h_a, bytes);

// ... use h_a with cudaMemcpyAsync ...

cudaFreeHost(h_a);
```

Without pinned memory, `cudaMemcpyAsync` falls back to a synchronous copy internally, defeating the purpose.

---

## 5. Overlapping copy and compute

The classic streaming pattern splits work into chunks and pipelines them across multiple streams. Each stream follows this pattern:

```text
Stream i:
  1. copy chunk i host → device
  2. process chunk i on device
  3. copy chunk i device → host
```

With two or more streams, the copy engine and the compute engine can overlap:

```text
Timeline with two streams:

Stream 1:  H2D  →  kernel  →  D2H
Stream 2:       H2D  →  kernel  →  D2H

GPU engine usage:
copy:      [====]       [====]       [====]
compute:        [=======]    [=======]

The copy and compute engines are busy simultaneously.
```

For this to work, the chunks must be independent. Stream 2's H2D must not depend on Stream 1's results, and so on.

### Code skeleton

```cpp
const int numStreams = 4;
cudaStream_t streams[numStreams];
for (int i = 0; i < numStreams; i++) {
    cudaStreamCreate(&streams[i]);
}

// Split data into chunks
int chunkSize = totalSize / numStreams;

for (int i = 0; i < numStreams; i++) {
    int offset = i * chunkSize;
    float *d_chunk = d_data + offset;
    float *h_chunk = h_data + offset;

    cudaMemcpyAsync(d_chunk, h_chunk, chunkBytes,
                    cudaMemcpyHostToDevice, streams[i]);

    kernel<<<grid, block, 0, streams[i]>>>(d_chunk, chunkSize);

    cudaMemcpyAsync(h_chunk, d_chunk, chunkBytes,
                    cudaMemcpyDeviceToHost, streams[i]);
}

for (int i = 0; i < numStreams; i++) {
    cudaStreamSynchronize(streams[i]);
    cudaStreamDestroy(streams[i]);
}
```

>  so is this true only when using streams, because i remember a SM has multiple partitions and it can let multiple blocks run in parallel on spare partitions, but i didn't know it can of multiple kernels (don't confuse, only threads inside a warp do lockstep execution)

**Yes, running multiple different kernels concurrently requires non-default streams.** In the default stream, kernel launches are strictly serialized: the GPU Work Distributor will never launch `kernelB` until `kernelA` has completely finished, even if `kernelA` leaves 90% of the GPU idle.

When you use separate streams, the GPU can execute different kernels in parallel across two distinct levels:

---

### 1. Across Different SMs (Spatial Coexistence)

If `kernelA` launches with a small grid (e.g., 4 blocks) on an 80-SM GPU, it leaves 76 SMs completely unused.

When `kernelB` is launched in `stream2`, the hardware work scheduler sees available SMs and immediately assigns `kernelB`'s blocks to those idle SMs. Both kernels compute simultaneously on different parts of the chip.

---

### 2. On the EXACT SAME SM (Resource Coexistence)

Different kernels can even share the **exact same physical SM**.

An SM does not allocate resources at the "kernel" level; it allocates resources at the **block** level based on hardware limits:

* Register file size
* Shared Memory allocation
* Max warps per SM
* Max blocks per SM

If `kernelA` places a block on SM 0 that uses only 20% of SM 0's registers and shared memory, SM 0 still has 80% of its capacity free. If `kernelB` arrives from `stream2`, the SM scheduler will load a block from `kernelB` onto SM 0 right alongside `kernelA`'s block.

The SM's warp schedulers will then interleave warps from **both kernels** on the same execution sub-cores/processing blocks.

---

### Summary of Rules

| Scenario | Default Stream | Non-Default Streams (`stream1`, `stream2`) |
| --- | --- | --- |
| **Same Kernel, Multiple Blocks** | Runs in parallel across SMs / Sub-cores | Runs in parallel across SMs / Sub-cores |
| **Different Kernels** | Strictly Serialized 🐢 (`kernelB` waits) | **Concurrent Execution ⚡ (Runs on spare SMs & within same SM)** |

This hardware capability is managed by the GPU's **Hyper-Q** engine, which maintains multiple hardware command queues feeding directly into the global Work Distributor.

---

## 6. Overlapping multiple kernels

Even if there is no data transfer to overlap, streams let multiple independent kernels run concurrently on different SMs:

```cpp
kernelA<<<grid, block, 0, stream1>>>(...);
kernelB<<<grid, block, 0, stream2>>>(...);
```

If `kernelA` does not fill all SMs, `kernelB` can use the spare ones. This is most useful when kernels are small or when you have multiple independent workloads to feed the GPU.

```text
Single stream:
SM usage:  [Kernel A]  [Kernel B]
            sequential

Two streams:
SM usage:  [Kernel A    ]
           [    Kernel B]
            overlapping
```

---

## 7. Synchronization

Because stream operations are asynchronous, you must explicitly wait for them.

### cudaStreamSynchronize

Blocks the host until all operations in a specific stream have completed:

```cpp
cudaStreamSynchronize(stream);
```

Use this when the host needs the results of that stream's work.

### cudaDeviceSynchronize

Blocks the host until all operations in all streams have completed:

```cpp
cudaDeviceSynchronize();
```

This is the bigger hammer. It is simpler but can over-synchronize, reducing concurrency.

### cudaEvent

CUDA events can mark points in a stream and be used for fine-grained timing or synchronization:

```cpp
cudaEvent_t start, stop;
cudaEventCreate(&start);
cudaEventCreate(&stop);

cudaEventRecord(start, stream);
kernel<<<grid, block, 0, stream>>>(...);
cudaEventRecord(stop, stream);

cudaEventSynchronize(stop);
float ms;
cudaEventElapsedTime(&ms, start, stop);
```

Events are also useful for cross-stream synchronization.

---

## 8. The default stream and other streams

The default stream has special behavior: operations in the default stream synchronize with all other streams. This means a default-stream operation waits for all existing operations in all other streams to finish, and all future operations in other streams wait for the default-stream operation to finish.

```text
Stream 1:  op1 → op2
Stream 2:  opA → opB
Default:            opX

opX waits for op2 and opB.
opX also blocks op2's and opB's successors? No — actually, opX blocks
anything issued after opX in any stream.
```

This is a common source of accidental serialization. If you create explicit streams for concurrency, avoid putting anything in the default stream, or understand that it acts as a global barrier.

For this reason, production CUDA code that uses streams usually puts everything in explicit streams and avoids stream 0 entirely.

---

## 9. When streams help and when they do not

Streams help when there is idle hardware to exploit:

- **Host/device transfer overlap**: copy data while the GPU computes.
- **Kernel/kernel overlap**: run multiple kernels concurrently.
- **Host computation overlap**: do CPU work while the GPU runs.

Streams do not help when:

- The kernel already saturates the GPU. Adding transfers or other kernels does not create more SMs or memory bandwidth.
- The workload is a single large kernel with no chunking possible.
- The host cannot produce data fast enough to keep the GPU fed.

The main win is usually **pipelining**: breaking a large problem into chunks and keeping the copy and compute engines busy at the same time.

---

## 10. A complete streaming example

```cpp
#include <cuda_runtime.h>

__global__ void scale(float *d, int n, float factor)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        d[i] *= factor;
    }
}

int main()
{
    const int totalSize = 4 * 1024 * 1024;
    const int numStreams = 4;
    const int chunkSize = totalSize / numStreams;
    const size_t chunkBytes = chunkSize * sizeof(float);

    cudaStream_t streams[numStreams];
    float *h_data, *d_data;

    cudaMallocHost(&h_data, totalSize * sizeof(float));  // pinned
    cudaMalloc(&d_data, totalSize * sizeof(float));

    for (int i = 0; i < numStreams; i++) {
        cudaStreamCreate(&streams[i]);
    }

    for (int i = 0; i < numStreams; i++) {
        int offset = i * chunkSize;
        cudaMemcpyAsync(d_data + offset, h_data + offset,
                        chunkBytes, cudaMemcpyHostToDevice,
                        streams[i]);

        scale<<<(chunkSize + 255) / 256, 256, 0, streams[i]>>>(
            d_data + offset, chunkSize, 2.0f);

        cudaMemcpyAsync(h_data + offset, d_data + offset,
                        chunkBytes, cudaMemcpyDeviceToHost,
                        streams[i]);
    }

    for (int i = 0; i < numStreams; i++) {
        cudaStreamSynchronize(streams[i]);
        cudaStreamDestroy(streams[i]);
    }

    cudaFree(d_data);
    cudaFreeHost(h_data);

    return 0;
}
```

This skeleton is the basis for almost every production CUDA pipeline.

---

## 11. Summary

Streams turn CUDA from a synchronous request-reply model into a pipelined one.

```text
WITHOUT STREAMS:
Host:  copy → wait → kernel → wait → copy → wait
GPU:   copy        run         copy

WITH STREAMS:
Host:  copy1 copy2 copy3 copy4
GPU copy engine:  H2D1 H2D2 H2D3 H2D4
GPU compute:         K1   K2   K3   K4
GPU copy engine:        D2H1 D2H2 D2H3 D2H4
```

Key points:

- A stream is an ordered queue of GPU operations.
- Operations in different streams may overlap.
- Use `cudaMemcpyAsync` with pinned host memory for asynchronous transfers.
- Use `cudaStreamSynchronize` or `cudaEventSynchronize` to wait for specific work.
- The default stream synchronizes with all other streams; avoid mixing it with explicit streams.
- Streams are most valuable when the problem can be chunked and the GPU has idle copy/compute capacity.

---

## 12. What comes next

With streams in place, the next topics move into more advanced GPU programming:

- **Unified Memory**: a single virtual address space shared between CPU and GPU, with automatic page migration.
- **Multi-GPU programming**: scaling across several GPUs with peer-to-peer copies and NVLink.
- **Advanced memory models**: texture objects, constant memory, and cache control hints.

These are the tools for building larger GPU systems rather than single kernels.
