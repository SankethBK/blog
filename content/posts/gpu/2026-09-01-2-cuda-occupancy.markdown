---
title:  "CUDA Occupancy: Filling the SM to Hide Latency"
date:   2026-09-01
categories: ["gpu"]
tags: ["gpu", "cuda", "nvidia", "occupancy", "performance"]

---

# CUDA Occupancy: Filling the SM to Hide Latency

The [previous note](/gpu/2026-09-01-1-cuda-shared-memory-tiling) showed how to use shared memory to fix uncoalesced access patterns. This note covers **occupancy**: how many warps can live on an SM at the same time, and why that number determines whether the GPU can hide memory latency.

Occupancy is the first CUDA performance topic that is not about memory access at all. It is about keeping the warp schedulers busy.

---

## 1. Why occupancy matters

From the hardware note, the key idea of a GPU warp scheduler is **latency hiding through oversubscription**:

- A warp stalls when it waits for memory or a long-latency instruction.
- The scheduler switches to a different ready warp at zero cost.
- If there are no other ready warps, the ALUs sit idle.

```text
SM with only 1 resident warp:

cycle:  1    2    3    4    5    6    7    8
W0:    run  run  stall ...............  run
ALU:   busy busy idle idle idle idle idle busy

SM with 4 resident warps:

cycle:  1    2    3    4    5    6    7    8
W0:    run  run  stall ...............  run
W1:                run  run  stall ....
W2:                          run  run  stall
W3:                                    run  run
ALU:   busy busy busy busy busy busy busy busy
```

More resident warps means more opportunities to find work when one warp stalls. **Occupancy** is the ratio of actual resident warps to the maximum number the SM can hold.

```text
occupancy = (resident warps per SM) / (maximum warps per SM)
```

On modern NVIDIA GPUs, an SM can hold 16 to 64 warps depending on the architecture. Higher occupancy is usually better, but it is not the only performance metric.

---

## 2. What limits occupancy

Three hardware resources cap how many warps an SM can keep resident:

1. **Warp slots**: the SM has a fixed maximum number of resident warps (e.g., 32 or 48 or 64).
2. **Register file**: each thread needs registers. If each thread uses many registers, fewer threads (and thus fewer warps) fit.
3. **Shared memory**: each block uses some shared memory. If each block uses a lot, fewer blocks fit on the SM.

The SM also has a limit on the number of resident blocks, but for typical block sizes that limit is rarely the binding constraint.

```text
SM capacity:

Maximum resident warps:      32 (example)
Register file size:          64 K 32-bit registers
Shared memory size:          48 KB (configurable)
Maximum resident blocks:     32

Your kernel:
Threads per block:           256  → 8 warps per block
Registers per thread:        64   → 256 * 64 = 16,384 registers per block
Shared memory per block:     4 KB

Maximum warps from register file:  64K / 64 = 1024 threads = 32 warps
Maximum warps from shared memory: 48 KB / 4 KB = 12 blocks * 8 warps = 96 warps (but capped at 32)
Maximum warps from warp slots:    32

So occupancy is limited by warp slots → 32 / 32 = 100%
```

If you increase registers per thread to 128:

```text
Registers per block: 256 * 128 = 32,768
Maximum warps from register file: 64K / 128 = 512 threads = 16 warps

Occupancy = 16 / 32 = 50%
```

This is why register usage is a first-class CUDA optimization concern. The compiler decides how many registers a kernel uses, but your code influences that decision.

---

## 3. How to think about occupancy in practice

You do not usually compute occupancy by hand. NVIDIA provides the **CUDA Occupancy Calculator** (an Excel spreadsheet) and the `cudaOccupancyMaxPotentialBlockSize` runtime API. But understanding what those tools do is essential.

### The three constraints, visualized

```text
Constraint 1: Warp slots

SM can hold 32 warps.

Threads per block = 256 → 8 warps per block
Max blocks from warp slots = 32 / 8 = 4 blocks

Constraint 2: Register file

Registers per thread = 64
Threads per block = 256
Registers per block = 16,384
SM register file = 65,536
Max blocks from registers = 65,536 / 16,384 = 4 blocks

Constraint 3: Shared memory

Shared memory per block = 16 KB
SM shared memory = 48 KB
Max blocks from shared memory = 48 / 16 = 3 blocks

Binding constraint: shared memory → 3 blocks → 24 warps
Occupancy = 24 / 32 = 75%
```

The smallest of the three maxima wins.

---

## 4. Block size vs occupancy

Block size affects occupancy because it determines how many warps each block carries, and because some resources are allocated per block even if the block is small.

Consider a kernel with 32 registers per thread and 0 shared memory, on an SM that holds 32 warps and 64K registers.

```text
Block size  | Warps/block | Max blocks (registers) | Max blocks (warp slots) | Occupancy
----------- | ----------- | ---------------------- | ----------------------- | ----------
64 threads  | 2 warps     | 32                     | 16                      | 32 warps / 32 = 100%
128 threads | 4 warps     | 16                     | 8                       | 32 warps / 32 = 100%
256 threads | 8 warps     | 8                      | 4                       | 32 warps / 32 = 100%
512 threads | 16 warps    | 4                      | 2                       | 32 warps / 32 = 100%
1024 threads| 32 warps    | 2                      | 1                       | 32 warps / 32 = 100%
```

In this case, any block size reaches 100% occupancy because the kernel is light on registers and uses no shared memory.

Now increase registers per thread to 128:

```text
Block size  | Reg/block | Max blocks (registers) | Occupancy
----------- | --------- | ---------------------- | ----------
64 threads  | 8,192     | 8                      | 16 warps / 32 = 50%
128 threads | 16,384    | 4                      | 16 warps / 32 = 50%
256 threads | 32,768    | 2                      | 16 warps / 32 = 50%
512 threads | 65,536    | 1                      | 16 warps / 32 = 50%
1024 threads| 131,072   | 0                      | kernel cannot launch
```

Notice that changing block size does not always help. If the binding constraint is registers per thread, smaller blocks do not change the total number of resident threads. The register file is the bottleneck.

---

## 5. The occupancy vs register-pressure tradeoff

Registers are the fastest memory on the GPU. Using more registers can make a kernel faster by keeping intermediate values in fast storage instead of spilling to local memory. But more registers per thread reduces occupancy, which means fewer warps to hide latency.

```text
High registers, low occupancy:
  Each thread runs fast, but there are fewer warps to switch to on a stall.

Low registers, high occupancy:
  Each thread has less fast storage, but more warps can hide latency.
```

The right balance depends on the kernel:

- Compute-bound kernels benefit from more registers because they keep the ALUs fed with operands.
- Memory-bound kernels benefit from high occupancy because they need many warps to cover memory latency.

This is why the compiler's `-maxrregcount` flag and launch-bound annotations exist: they let you force the compiler to use fewer registers per thread, trading per-thread speed for occupancy.

---

## 6. Shared memory vs occupancy

Shared memory is also limited per SM. A block that uses a lot of shared memory reduces how many blocks can fit on the SM.

```text
SM shared memory = 48 KB
Shared memory per block = 24 KB
Max blocks from shared memory = 2

Even if warp slots and registers allow more, only 2 blocks fit.
```

This is the main tension in tiling: larger tiles reuse more data, but use more shared memory, which can reduce occupancy. Sometimes a smaller tile with higher occupancy beats a larger tile with more reuse.

> Reducing tile size can only be achieved by reducing block size eg: 16x16 instead of 32x32. This also means number of threads per block, but since a SM can run multiple blocks concurrently, the total number of threads per SM remains the same.

---

## 7. When high occupancy does not matter

High occupancy is not always the goal. Two important exceptions:

### Sufficient occupancy

If your kernel already has enough warps to hide the latency of its memory or instruction dependencies, adding more warps does nothing. There is a point of diminishing returns.

```text
Memory latency ≈ 400 cycles
Each warp can hide latency for other warps while waiting

If 16 warps already keep the ALUs busy, going to 32 warps
may not speed the kernel up.
```

### Compute-bound kernels

If a kernel is limited by arithmetic throughput rather than memory latency, occupancy matters less than instruction-level parallelism and efficient use of the ALUs. A kernel with 50% occupancy but no memory stalls can still saturate the compute units.

The real question is not "what is my occupancy?" but "is my occupancy high enough to hide the latency my kernel actually experiences?"

> Bottom line it only starts hurting when the ALU's sit idle, if ALU's are fully utilized then occupancy doesn't matter.

---

## 8. Measuring occupancy

### cudaOccupancyMaxPotentialBlockSize

CUDA provides a runtime function that suggests a block size for maximum occupancy:

```cuda
int minGridSize, blockSize;
cudaOccupancyMaxPotentialBlockSize(
    &minGridSize, &blockSize, myKernel, 0, 0);
```

This gives you a block size that the runtime estimates will maximize occupancy for your kernel, given its register and shared-memory usage. It is a useful starting point, not a guaranteed optimum.

### The Occupancy Calculator

NVIDIA also distributes an Excel spreadsheet where you enter:

- GPU compute capability
- Threads per block
- Registers per thread
- Shared memory per block

and it reports occupancy. This is useful for understanding limits, but real tuning usually happens with profilers.

### Profilers

Tools like `ncu` (NVIDIA Compute Profiler) report actual achieved occupancy and identify whether you are limited by registers, shared memory, or warp slots.

---

## 9. Practical guidelines

1. **Start with a block size that is a multiple of 32** — a warp. Common choices are 128, 256, or 512 threads. 256 is a safe default.

2. **Do not chase 100% occupancy blindly.** 50% or 75% is often enough, especially if the kernel is compute-bound.

3. **Check register usage if occupancy is unexpectedly low.** The compiler may be using more registers than you realize.

4. **Watch shared-memory usage in tiled kernels.** A larger tile is not always better if it cuts occupancy in half.

5. **Use the runtime occupancy API or a profiler** to ground decisions in numbers rather than guessing.

---

## 10. Summary

Occupancy is the fraction of the SM's warp capacity that your kernel actually uses. It is determined by the tightest of three constraints: warp slots, register file, and shared memory.

```text
OCCUPANCY = resident warps / max warps per SM

Limited by:
  - warp slots         (hard architecture limit)
  - registers per thread (register file / registers per thread)
  - shared memory per block (SM shared memory / shared memory per block)
```

Higher occupancy helps hide latency, especially in memory-bound kernels. But it is not the only goal: register pressure, shared-memory tiling, and instruction-level parallelism also matter. The right target is "enough occupancy to cover the latency your kernel sees," not necessarily 100%.

---

## 11. What comes next

With coalescing, tiling, and occupancy in place, the next topics are concrete optimization techniques:

- **Loop unrolling** and **#pragma unroll** to reduce loop overhead.
- **Warp shuffle** for low-latency communication between threads in the same warp without shared memory.
- **CUDA streams** for overlapping kernel execution with host-device data transfers.
- **Reduction algorithms** for parallel sum/max operations.

These are the tools that turn a correct CUDA kernel into a fast one.
