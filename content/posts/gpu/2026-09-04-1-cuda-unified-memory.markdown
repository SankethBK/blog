---
title:  "CUDA Unified Memory: One Pointer, Two Processors"
date:   2026-09-04
categories: ["gpu"]
tags: ["gpu", "cuda", "nvidia", "unified-memory", "memory-management"]

---

# CUDA Unified Memory: One Pointer, Two Processors

The [previous note](/gpu/2026-09-02-2-cuda-streams) covered explicit CUDA streams and how to overlap host-device transfers with computation. This note covers **Unified Memory**, an alternative to explicit `cudaMalloc` / `cudaMemcpy` / `cudaFree`. It lets both CPU and GPU use a single pointer, at the cost of some performance complexity under the hood.

Unified Memory is seductive: it removes the need to think about host and device pointers separately. But it does not remove the physical reality that CPU and GPU memory are separate. Understanding when it helps and when it hurts is essential.

---

## 1. The explicit memory model recap

In the CUDA programming model note, every array had two versions:

- `h_a` — allocated with `malloc`, lives in CPU RAM.
- `d_a` — allocated with `cudaMalloc`, lives in GPU RAM.

Data moved between them with `cudaMemcpy`.

```text
CPU memory          GPU memory
   h_a ─────────────► d_a   (cudaMemcpyHostToDevice)
   h_a ◄───────────── d_a   (cudaMemcpyDeviceToHost)
```

This is fast and predictable, but it requires the programmer to manage two pointers and schedule transfers. Unified Memory collapses this into one pointer.

---

## 2. What Unified Memory is

With Unified Memory, you allocate memory once and both the CPU and GPU can access it through the same pointer.

```cpp
float *data;
cudaMallocManaged(&data, bytes);

// CPU can read/write
data[0] = 1.0f;

// GPU can read/write
kernel<<<grid, block>>>(data, n);
```

The CUDA runtime and driver handle the physical movement of pages between CPU and GPU memory automatically. The pointer is valid on both processors.

```text
Unified Memory

CPU ──► single pointer `data` ◄── GPU
           │
           ▼
     Pages migrate between
     host RAM and device RAM
     on demand
```

This looks like magic, and for small or infrequent data movement it often feels like magic. For performance-critical code, the magic has costs.

---

## 3. How it works under the hood

Unified Memory is implemented using **page faults** and **page migration**.

- Memory is allocated in a virtual address space that both CPU and GPU can reference.
- Initially, pages may live in CPU memory.
- When the GPU touches a page that is not resident in GPU memory, a page fault occurs.
- The CUDA driver migrates that page from CPU memory to GPU memory.
- If the CPU touches the page again while it is on the GPU, the page may migrate back.

```text
Step 1: cudaMallocManaged creates virtual pages
        Physical location: CPU RAM

Step 2: GPU kernel reads data[0]
        Page fault ──► migrate page to GPU RAM

Step 3: CPU reads data[0]
        Page fault ──► migrate page back to CPU RAM
```

Modern NVIDIA GPUs and drivers also support **oversubscription** and **on-demand paging**, where pages can be accessed from the other processor's memory without a full migration. But the basic model is still "move pages to the processor that uses them."

---

## 4. cudaMallocManaged vs cudaMalloc

| Operation | Explicit model | Unified Memory |
|-----------|---------------|----------------|
| Allocate | `cudaMalloc(&d_a, bytes)` | `cudaMallocManaged(&a, bytes)` |
| Free | `cudaFree(d_a)` | `cudaFree(a)` |
| CPU access | `h_a[i]` | `a[i]` |
| GPU access | `d_a[i]` in kernel | `a[i]` in kernel |
| Transfer | `cudaMemcpy(h_a, d_a, ...)` | automatic on page fault |

The code is simpler. But transfers still happen; they are just implicit.

---

## 5. A simple Unified Memory example

```cpp
#include <cuda_runtime.h>
#include <stdio.h>

__global__ void scale(float *data, int n, float factor)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        data[i] *= factor;
    }
}

int main()
{
    int n = 1 << 20;
    size_t bytes = n * sizeof(float);

    float *data;
    cudaMallocManaged(&data, bytes);

    // Initialize on CPU
    for (int i = 0; i < n; i++) {
        data[i] = 1.0f;
    }

    // Launch kernel on GPU
    scale<<<(n + 255) / 256, 256>>>(data, n, 2.0f);
    cudaDeviceSynchronize();

    // Use results on CPU
    printf("data[0] = %f\n", data[0]);

    cudaFree(data);
    return 0;
}
```

This is the same program as the explicit version, but with one pointer and no `cudaMemcpy`. The first time the GPU kernel reads `data`, pages migrate to the GPU. After `cudaDeviceSynchronize`, the CPU reads `data[0]`; the page may migrate back.

---

## 6. The performance trap: page faults are expensive

The danger of Unified Memory is that page faults hide behind innocent-looking pointer accesses. If your algorithm ping-pongs data between CPU and GPU, every access can trigger a migration.

```text
Bad pattern with Unified Memory:

CPU: write data[0]
GPU: read data[0]   → page fault, migrate
CPU: write data[1]
GPU: read data[1]   → page fault, migrate
CPU: write data[2]
GPU: read data[2]   → page fault, migrate
...

Each access becomes a PCIe transfer plus page-fault overhead.
```

This is much slower than explicit `cudaMemcpy` for the whole array. The explicit model forces you to think about bulk transfers; Unified Memory can let you accidentally fragment them.

---

## 7. When Unified Memory is a win

Unified Memory is good when:

- Data is large and its access pattern is simple and predictable (one big CPU-to-GPU handoff).
- You are prototyping and want to avoid the bookkeeping of two pointers.
- The data genuinely needs to be accessed by both processors with no clear owner.
- You are oversubscribing GPU memory and relying on demand paging.

It is less good when:

- Performance is critical and you can structure explicit transfers cleanly.
- You touch the same data back and forth from both processors.
- You need fine-grained control over memory placement.

A good rule of thumb: Unified Memory is for convenience and complexity reduction; explicit `cudaMalloc`/`cudaMemcpy` is for peak performance.

> This is different from apple's unified memory where unified memory means cpu and gpu literally read from same memory rather than illusion of same memory with on-demand paging. 

---

## 8. Pre-fetching: cudaMemPrefetchAsync

You can reduce page-fault overhead by telling the runtime where data should live before it is used.

```cpp
// Move data to GPU before kernel launch
cudaMemPrefetchAsync(data, bytes, deviceId, stream);

kernel<<<grid, block, 0, stream>>>(data, n);

// Move data back to CPU after kernel
cudaMemPrefetchAsync(data, bytes, cudaCpuDeviceId, stream);
cudaStreamSynchronize(stream);
```

This gives you some of the predictability of explicit transfers while keeping the single-pointer model. It is especially useful when you know the next access pattern.

---

## 9. Coherence and synchronization

Unified Memory is coherent, but the programmer is still responsible for synchronization. If the CPU reads data while a GPU kernel is still writing it, the result is a race condition.

Use `cudaDeviceSynchronize()` or `cudaStreamSynchronize()` to ensure the GPU has finished before the CPU reads the data. Without it, the CPU may read stale values from before the migration.

```cpp
kernel<<<grid, block>>>(data, n);
// cudaDeviceSynchronize();   // required before CPU reads
printf("%f\n", data[0]);     // undefined behavior without sync
```

This is the same synchronization requirement as explicit memory; Unified Memory does not remove it.

---

## 10. Unified Memory vs explicit transfers, summarized

```text
                    Explicit cudaMalloc     cudaMallocManaged
Code complexity     Higher (two pointers)   Lower (one pointer)
Transfer control    Explicit, bulk            Implicit, per-page
Peak performance    Higher                    Lower unless prefetched
Oversubscription    Hard to do well           Supported by demand paging
Best for            Production kernels        Prototyping, sparse access
```

Neither is always right. Many production CUDA programs use a mix: explicit memory for the hot path, Unified Memory for data structures that are awkward to partition.

---

## 11. Summary

Unified Memory gives you a single pointer that works on both CPU and GPU. It simplifies code by making data movement implicit, but it does not eliminate the cost of moving data. Pages migrate on demand, and that migration has overhead.

Key takeaways:

- Use `cudaMallocManaged` for a single pointer accessible from both processors.
- The first GPU access causes page faults and migration; plan for it.
- Avoid CPU/GPU ping-pong on the same data.
- Use `cudaMemPrefetchAsync` to move data proactively.
- Still synchronize before CPU reads after GPU writes.

Unified Memory is a productivity feature, not a performance feature. For peak performance, explicit `cudaMalloc`/`cudaMemcpy` and streams usually win.

---

## 12. What comes next

With Unified Memory covered, the next logical topics are:

- **Multi-GPU programming**: using more than one GPU, peer-to-peer memory access, and NVLink.
- **Advanced memory models**: texture memory, constant memory, and cache control hints.

Multi-GPU is the natural next step if you want to scale beyond one accelerator.
