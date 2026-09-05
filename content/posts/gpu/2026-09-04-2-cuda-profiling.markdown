---
title:  "CUDA Profiling and Performance Measurement"
date:   2026-09-04
categories: ["gpu"]
tags: ["gpu", "cuda", "nvidia", "profiling", "performance"]

---

# CUDA Profiling and Performance Measurement

The notes up to this point covered what makes CUDA kernels fast in theory: coalescing, tiling, occupancy, and asynchronous execution. This note covers how to **measure** whether a kernel is actually fast and how to find the bottleneck when it is not.

Profiling is what separates guessing from optimization. Without it, you can apply every best practice and still be slower than a simpler implementation.

---

## 1. Two levels of profiling

CUDA profiling happens at two levels:

1. **System / timeline profiling** — shows what the CPU, GPU, copy engines, and streams are doing over time.
2. **Kernel / instruction profiling** — zooms into one kernel and reports hardware metrics like occupancy, memory throughput, and instruction mix.

| Tool | Level | Use case |
|------|-------|----------|
| `cudaEvent_t` | In-code timing | Quick kernel timing inside your program |
| Nsight Systems | System timeline | Find idle time, copy/compute overlap, launch gaps |
| Nsight Compute (`ncu`) | Kernel metrics | Why is this kernel slow? Memory or compute bound? |

On older setups, `nvprof` and `nvvp` were used. Modern workflow uses Nsight Systems and Nsight Compute.

---

## 2. In-code timing with cudaEvent

The simplest way to time a kernel is with CUDA events.

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
printf("Kernel time: %f ms\n", ms);

cudaEventDestroy(start);
cudaEventDestroy(stop);
```

Events record timestamps on the GPU timeline. `cudaEventElapsedTime` returns milliseconds. This is good enough for comparing versions of a kernel.

**Important:** `cudaEventRecord(stop, stream)` only marks the end of the kernel in the stream. You must call `cudaEventSynchronize(stop)` on the host to wait for the event before reading the elapsed time. Without synchronization, you read the timer before the kernel has finished.

---

## 3. Measuring effective memory bandwidth

For memory-bound kernels, the key metric is **effective memory bandwidth**:

```text
effective_bandwidth_GBps = (bytes_read + bytes_written) / kernel_time_in_seconds / 1e9
```

Example: a vector add kernel reads two arrays and writes one array, each `n * sizeof(float)` bytes, for `n = 1,048,576` floats.

```text
bytes = 3 * 1,048,576 * 4 = 12,582,912 bytes
kernel time = 0.05 ms = 0.00005 s
bandwidth = 12,582,912 / 0.00005 / 1e9 = 251.7 GB/s
```

Compare this to your GPU's theoretical memory bandwidth. If you are within a large fraction of it, the kernel is memory-bound and well-optimized for its access pattern. If you are far below it, something is wrong: uncoalesced access, low occupancy, or unnecessary memory traffic.

---

## 4. Measuring compute throughput

For compute-bound kernels, measure **effective compute throughput** in FLOP/s:

```text
effective_FLOP_s = number_of_floating_point_operations / kernel_time_in_seconds
```

Example: a kernel that performs one multiply-add per element on `n` elements:

```text
FLOPs = 2 * n
kernel time = 0.1 ms
effective = 2 * n / 0.0001
```

Compare to your GPU's theoretical peak FP32 throughput. If you are close, the kernel is compute-bound. If not, the bottleneck may be memory latency, instruction latency, or occupancy.

---

## 5. The roofline model, briefly

The roofline model is a way to classify kernels:

- **Memory-bound**: limited by how fast you can move data.
- **Compute-bound**: limited by how many arithmetic operations the ALUs can perform.

You can estimate which one your kernel is before profiling:

```text
arithmetic_intensity = FLOPs / bytes_moved
```

A kernel with low arithmetic intensity (few operations per byte) is usually memory-bound. A kernel with high arithmetic intensity is usually compute-bound.

```text
Vector add:    1 add per 12 bytes read/written → memory-bound
Matrix multiply: 2*n FLOPs per ~8n bytes → can be compute-bound
```

This matters because the optimization strategy differs:

- Memory-bound: optimize access pattern, coalescing, tiling, bandwidth.
- Compute-bound: optimize instruction mix, occupancy, register usage, Tensor Cores.

---

## 6. Nsight Systems: the timeline view

Nsight Systems shows a timeline of your whole application:

```bash
nsys profile -o report ./my_program
nsys-ui report.nsys-rep
```

You can see:

- When the CPU is active.
- When GPU kernels run.
- When memory copies happen.
- Gaps where the GPU is idle.

```text
CPU:  [launch] [launch]      [sync]  [copy]
GPU:       [kernel1] [kernel2]   [idle] [kernel3]
Copy:                         [H2D]        [D2H]
```

This is the right tool for answering questions like:

- Are my kernels overlapping with copies?
- Is the GPU sitting idle waiting for the CPU?
- Are my kernels launching quickly, or is there a long gap between launches?

---

## 7. Nsight Compute (`ncu`): the kernel microscope

Nsight Compute profiles a single kernel and reports dozens of hardware metrics.

```bash
ncu -o report ./my_program
ncu-ui report.ncu-rep
```

Or, to profile a specific kernel:

```bash
ncu --kernel-name myKernel ./my_program
```

### Key metrics to watch

| Metric | What it tells you |
|--------|-------------------|
| Achieved occupancy | How many warps were resident relative to the SM's maximum |
| Memory throughput | How close you are to the memory bandwidth limit |
| Compute throughput | How close you are to the ALU throughput limit |
| L1/L2 hit rate | Whether your memory accesses are cache-friendly |
| Branch divergence | Whether threads in warps are taking different paths |
| Instruction mix | How much time is spent on FMA, load/store, SFU, etc. |

### Interpreting the results

If Nsight Compute says:

- **Memory throughput is high, compute is low** → kernel is memory-bound. Check coalescing and tiling.
- **Compute throughput is high, memory is low** → kernel is compute-bound. Check instruction mix and occupancy.
- **Occupancy is low** → check register usage and shared memory per block.
- **L1/L2 hit rate is low** → check memory access locality.
- **Branch divergence is high** → your `if` statements are causing warp serialization.

---

## 8. The optimization loop

Profiling turns optimization into a loop:

```text
1. Measure baseline time and identify the bottleneck.
2. Form a hypothesis: "I think the kernel is slow because of uncoalesced access."
3. Make one targeted change.
4. Measure again.
5. If faster, keep the change. If not, revert and try another hypothesis.
```

Never change three things at once. If you do, you cannot tell which change helped.

---

## 9. Common profiling mistakes

### Timing only once

GPU times vary due to clock boosting, thermal throttling, and other workloads. Run several times and take an average.

### Forgetting warm-up

The first kernel launch may include JIT compilation or memory page setup. Run the kernel once before starting the timer.

### Including `cudaMemcpy` in kernel time

If you time from before the H2D copy to after the D2H copy, you are measuring transfer time, not kernel time. Time the kernel separately.

### Comparing against CPU without optimizing the CPU

A naive CPU implementation is not a fair baseline. If your goal is to show the GPU wins, compare against an optimized CPU version too.

### Optimizing the wrong thing

A kernel that takes 1 ms but is called 10,000 times matters more than a kernel that takes 100 ms but is called once. Profile the whole application, not just isolated kernels.

---

## 10. A minimal benchmarking harness

Here is a pattern you can reuse for every lab:

```cpp
void benchmark(void (*kernel)(...), const char *name,
               int blocks, int threads, int warmup, int trials)
{
    // Warm-up
    for (int i = 0; i < warmup; i++) {
        kernel<<<blocks, threads>>>(...);
    }
    cudaDeviceSynchronize();

    // Time
    cudaEvent_t start, stop;
    cudaEventCreate(&start);
    cudaEventCreate(&stop);

    cudaEventRecord(start);
    for (int i = 0; i < trials; i++) {
        kernel<<<blocks, threads>>>(...);
    }
    cudaEventRecord(stop);
    cudaEventSynchronize(stop);

    float ms;
    cudaEventElapsedTime(&ms, start, stop);
    printf("%s: %f ms per call (%d trials)\n", name, ms / trials, trials);

    cudaEventDestroy(start);
    cudaEventDestroy(stop);
}
```

Use this to compare naive, tiled, and optimized versions of the same kernel.

> Why can't we just use time difference between `time.Now()` rather than CUDA events? 

Your intuition about accuracy is on the right track, but the primary reason CPU wall-clock timing fails is **asynchronous execution**.

---

### 1. The Asynchrony Trap (The #1 Reason)

CUDA kernel launches (`kernel<<<...>>>()`) are **non-blocking asynchronous API calls**. When the CPU executes a kernel launch line, it does not wait for the GPU to finish—it simply places the command into the GPU queue and instantly returns to the next line of code on the CPU (taking ~3–5 microseconds).

If you write this using standard CPU timers:

```cpp
auto start = std::chrono::high_resolution_clock::now();

myKernel<<<grid, block>>>(d_data); // Returns instantly!

auto end = std::chrono::high_resolution_clock::now();
auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();

```

`duration` will report **~3–5 microseconds**, regardless of whether `myKernel` takes 1 millisecond or 10 minutes to run on the GPU. You measured how long the CPU took to queue the kernel, not how long the GPU took to execute it.

---

### 2. Can't We Just Add `cudaDeviceSynchronize()` to CPU Timing?

You *could* force CPU timing to work by halting the CPU until the GPU finishes:

```cpp
auto start = std::chrono::high_resolution_clock::now();

myKernel<<<grid, block>>>(d_data);
cudaDeviceSynchronize(); // Force CPU to wait for GPU to complete

auto end = std::chrono::high_resolution_clock::now();

```

While this measures the execution time, it introduces three major flaws:

* **Host/OS Overhead Jitter:** `cudaDeviceSynchronize()` causes the CPU thread to sleep and wait for an interrupt from the GPU driver. The time it takes for the OS to wake up the CPU thread, handle context switches, and return to your code adds non-deterministic noise (10–50+ microseconds) to your measurement.
* **Flushes the Entire Device:** `cudaDeviceSynchronize()` stalls **all** CUDA streams and operations across the entire GPU, destroying any concurrent execution you might have set up.
* **Coarse Precision:** CPU timers measure through multiple layers of abstraction (C++ stdlib $\rightarrow$ OS Kernel $\rightarrow$ NVIDIA Driver $\rightarrow$ PCIe Bus $\rightarrow$ GPU).

---

### 3. How CUDA Events Work Under the Hood

When you use `cudaEventRecord(start)` and `cudaEventRecord(stop)`:

1. **Hardware Queue Markers:** The driver places special timestamp markers directly into the GPU's execution stream queue alongside your kernels.
2. **On-Chip GPU Clock:** When the GPU reaches `start` in its queue, the hardware SM clock counter logs an exact hardware cycle timestamp on the GPU chip itself.
3. **Pure Execution Timing:** `cudaEventElapsedTime()` calculates the exact difference using those hardware timestamps.

```
GPU Queue: [Event: start] ──► [myKernel Execution] ──► [Event: stop]
               ▲                                            ▲
         GPU Timestamp 1                              GPU Timestamp 2

```

---

### Summary Comparison

| Feature | CPU Wall Clock (`std::chrono`) | CUDA Events (`cudaEvent_t`) |
| --- | --- | --- |
| **Measures** | Time elapsed on Host CPU | Execution time on GPU hardware |
| **Asynchronous Kernel Support** | ❌ Fails (Returns instantly) | ⚡ Native (Measures queue execution) |
| **Measurement Precision** | Distorted by OS/Driver latency | Sub-microsecond (Hardware cycle accurate) |
| **Stream Overhead** | Requires `cudaDeviceSynchronize()` (Pipeline stall) | Non-blocking (Can profile specific streams) |

---

## 11. Summary

Profiling is the difference between knowing your code is fast and hoping it is fast.

| Tool | Use it for |
|------|-----------|
| `cudaEvent_t` | In-code kernel timing |
| Nsight Systems | Timeline, overlap, idle gaps |
| Nsight Compute (`ncu`) | Kernel metrics and bottleneck identification |

Key metrics:

- **Effective bandwidth** for memory-bound kernels.
- **Effective FLOP/s** for compute-bound kernels.
- **Achieved occupancy** for latency hiding.
- **Cache hit rates** and **branch divergence** for access and control patterns.

The optimization loop is: measure, hypothesize, change one thing, measure again. Every lab from here on should follow that loop.

---

## 12. What comes next

With profiling covered, you are ready for the lab sequence. The first lab will be a simple **vector add benchmark** to practice timing, then move into coalescing, transpose, matrix multiplication, reduction, and streams. Each lab should include a baseline, a hypothesis, a measured change, and a comparison.
