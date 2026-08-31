---
title:  "CUDA Memory Coalescing: Why Access Patterns Matter"
date:   2026-08-30
categories: ["gpu"]
tags: ["gpu", "cuda", "nvidia", "memory-coalescing", "performance"]

---

# CUDA Memory Coalescing: Why Access Patterns Matter

The [previous note](/gpu/2026-08-30-2-cuda-programming-model) showed how to write and launch a CUDA kernel. This note answers the first performance question: why does the same kernel sometimes run 5× or 10× slower just because of how threads read memory?

The answer is **memory coalescing**. Because GPU memory is optimized for bandwidth over latency, the hardware rewards access patterns where threads in a warp read or write contiguous addresses together. If they do not, the GPU wastes bandwidth and cycles fetching data that most threads ignore.

---

## 1. Recap: GPU memory is bandwidth-oriented

From the earlier hardware note:

- CPU memory is optimized for **low latency** on random accesses.
- GPU memory (GDDR/HBM) is optimized for **high bandwidth** on wide, contiguous transfers.

A single memory access on a GPU can be slow, but the memory bus is very wide. The goal is to move large chunks of data in few transactions. Coalescing is the software side of that bet: arrange your threads so that 32 adjacent threads access 32 adjacent memory locations, and the hardware can satisfy all of them with one wide read.

---

## 2. What coalescing means

A memory request from a warp is **coalesced** when the 32 threads in the warp access a contiguous, aligned region of memory that can be covered by as few cache lines / transactions as possible.

The ideal pattern:

```text
Thread 0 reads address 0
Thread 1 reads address 1
Thread 2 reads address 2
...
Thread 31 reads address 31
```

The hardware sees this and fetches one or a few wide contiguous chunks, giving every thread the byte it needs.

```text
Warp memory request (ideal):

Thread:   0   1   2   3   ...  31
Address:  0   1   2   3   ...  31
          |← contiguous 32 words →|

Memory controller: one wide read
```

The opposite — every thread in the warp reading a random address far from the others — forces the memory controller to issue many separate transactions, leaving most of each fetched chunk unused.

---

## 3. The hardware transaction view

Modern GPUs fetch memory in cache-line-sized chunks (for example, 128 bytes per L2 cache line, though exact sizes vary by architecture). When a warp requests 32 consecutive 4-byte floats starting at a 128-byte-aligned address, the entire request fits into one cache line.

```text
One cache line = 128 bytes
32 floats × 4 bytes = 128 bytes

Threads 0..31 read addresses 0..127 (as bytes)
→ exactly one 128-byte transaction
→ all 128 bytes are used
```

If the threads instead read every 4th float (strided access), the warp still touches 128 bytes total but spread across a much wider range, requiring more transactions.

```text
Strided access, stride = 4:

Thread:   0    1    2    3   ...
Address:  0    16   32   48  ...

Each thread touches 4 bytes, but the span is 512 bytes
→ multiple cache lines fetched
→ most bytes in each line wasted
```

---

## 4. Coalesced vs uncoalesced examples

Consider a 1D array and a kernel that reads one element per thread.

### Coalesced read

```cuda
__global__ void copy_coalesced(float *in, float *out, int n)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        out[i] = in[i];
    }
}
```

```text
Threads:  0  1  2  3  ...  31
Indices:  0  1  2  3  ...  31

Adjacent threads read adjacent floats.
Coalesced.
```

### Uncoalesced strided read

```cuda
__global__ void copy_strided(float *in, float *out, int n, int stride)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        out[i] = in[i * stride];
    }
}
```

With `stride = 4`:

```text
Threads:  0  1  2  3  ...  31
Indices:  0  4  8 12  ... 124

Adjacent threads do NOT read adjacent memory.
Uncoalesced; wastes memory bandwidth.
```

The strided version does the same total amount of arithmetic but can be many times slower because the memory subsystem is underutilized.

---

## 5. Misaligned access

Even contiguous access can be slightly less efficient if it is not aligned to the memory bus width. If a warp reads addresses 4..35 instead of 0..31, the request may span two cache lines instead of one.

```text
Aligned:    0..31  →  one transaction
Misaligned: 4..35  →  two transactions (covers two cache lines)
```

For large contiguous arrays, the first warp in a block may be misaligned, but the rest are usually aligned. The effect is small unless you deliberately use odd offsets.

---

## 6. Coalescing in 2D: row-major vs column-major

This is the most common real-world coalescing mistake. C and CUDA store 2D arrays in **row-major order**: consecutive elements in a row are adjacent in memory; consecutive elements in a column are far apart.

```text
Row-major layout (memory address increases left-to-right, then top-to-bottom):

    col 0   col 1   col 2
row 0  [0]     [1]     [2]
row 1  [3]     [4]     [5]
row 2  [6]     [7]     [8]
```

Suppose you use a 2D block where `threadIdx.x` varies across columns and `threadIdx.y` varies across rows.

### Coalesced 2D access

```cuda
int col = blockIdx.x * blockDim.x + threadIdx.x;
int row = blockIdx.y * blockDim.y + threadIdx.y;
int idx = row * width + col;
float val = image[idx];
```

Within a warp, `threadIdx.x` changes and `threadIdx.y` is constant. So adjacent threads in the warp read adjacent columns in the same row. Since the row is contiguous in memory, this is coalesced.

```text
Warp reads row 0, columns 0..31:
Thread 0 → address 0
Thread 1 → address 1
...
Thread 31 → address 31

Adjacent threads → adjacent memory. Coalesced.
```

> Why does threadIdx.y remain constant while threadIdx.x changes within a warp?

This is the exact "aha!" moment for CUDA indexing.

The short answer: **`y` remains constant within a warp because CUDA linearizes 2D thread indices in X-major order (X changes fastest, Y changes second, Z changes last).**

---

### The Thread Linearization Formula

When you launch a 2D block of threads—say `dim3 blockSize(16, 16)` (256 threads total)—the GPU hardware doesn't actually understand 2D coordinates. It must flatten those 256 threads into a 1D sequence from index `0` to `255` so it can group them into warps of 32.

CUDA uses this exact formula to calculate the 1D thread ID:

`Thread ID (1D) = threadIdx.x + (threadIdx.y * blockDim.x)`

Because `threadIdx.x` is not multiplied by anything, **it increments first (fastest)**.

---

### Walking Through Warp 0 (Threads 0 to 31)

Assume a block size of 16x16 (`blockDim.x = 16`, `blockDim.y = 16`):

#### First 16 Threads (Linear IDs 0 to 15):

* Thread 0:  `x = 0`,  `y = 0` → `0 + (0 * 16) = 0`
* Thread 1:  `x = 1`,  `y = 0` → `1 + (0 * 16) = 1`
* Thread 2:  `x = 2`,  `y = 0` → `2 + (0 * 16) = 2`
* ...
* Thread 15: `x = 15`, `y = 0` → `15 + (0 * 16) = 15`

*(Notice: For all 16 of these threads, **`y` is stuck at 0**, while `x` sweeps across row 0).*

#### Next 16 Threads (Linear IDs 16 to 31):

* Thread 16: `x = 0`,  `y = 1` → `0 + (1 * 16) = 16`
* Thread 17: `x = 1`,  `y = 1` → `1 + (1 * 16) = 17`
* ...
* Thread 31: `x = 15`, `y = 1` → `15 + (1 * 16) = 31`

*(Notice: For all 16 of these threads, **`y` is stuck at 1**, while `x` sweeps across row 1).*

---

### Why Warp 0 Experiences Coalesced Reads

**Warp 0** is made of **Linear Threads 0 through 31**.

Inside Warp 0:

* Threads 0–15 are all on **`y = 0`**, reading columns `x = 0..15` of Row 0.
* Threads 16–31 are all on **`y = 1`**, reading columns `x = 0..15` of Row 1.

Because `x` varies step-by-step while `y` stays fixed for spans of 16 threads, adjacent threads in the warp request **adjacent memory addresses in VRAM**.

```
Linear Threads in Warp 0: [ T0, T1, T2, ... T15 | T16, T17, ... T31 ]
                            └── Row 0 (y=0) ──┘   └── Row 1 (y=1) ──┘
VRAM Memory Layout:       [   Address 0, 1, 2... | Address 16, 17... ]
                            ▲───────────────────▲
                            Contiguous memory = COALESCED!

```

---


### Uncoalesced 2D access (the classic bug)

If you accidentally swap the mapping so that adjacent threads read down a column:

```cuda
// BAD: adjacent threads read down a column
int col = blockIdx.y * blockDim.y + threadIdx.y;  // wrong axis
int row = blockIdx.x * blockDim.x + threadIdx.x;  // wrong axis
int idx = row * width + col;
float val = image[idx];
```

Adjacent threads now differ in `row`, not `col`. They read addresses 0, width, 2*width, 3*width, ... which are far apart in memory.

```text
Thread 0 → address 0
Thread 1 → address width
Thread 2 → address 2*width
...

Adjacent threads → far apart memory. Uncoalesced.
```

This is the single most common reason image-processing kernels run slowly on a GPU.

---

## 7. The role of the L1 and L2 cache

Modern NVIDIA GPUs cache global memory accesses. If a warp reads coalesced contiguous data, the cache lines fetched are likely reused by nearby warps, amplifying the benefit.

```text
Warp 0 reads addresses 0..31    → fetches cache line 0..127
Warp 1 reads addresses 32..63   → fetches cache line 128..255
Warp 2 reads addresses 64..95   → fetches cache line 256..383

Each warp gets a full, fresh, useful cache line.
```

With random access, cache lines are fetched but only one word is used, and the chance that another warp needs the same line is low. The cache helps random access somewhat, but it cannot fix fundamentally scattered patterns.

---

## 8. Transpose example: coalescing on both reads and writes

Matrix transpose is the classic coalescing puzzle. A naive transpose reads rows (coalesced) but writes columns (uncoalesced).

```text
Read:  row i, all columns → contiguous in memory → coalesced
Write: column j, all rows → strided in memory → uncoalesced
```

To transpose efficiently, CUDA programmers use **shared memory tiling**: load a tile into shared memory with coalesced reads, then write the transposed tile back with coalesced writes. We will cover shared-memory tiling in the next note; for now, recognize that coalescing is the motivation.


```cpp
#include <iostream>
#include <cuda_runtime.h>

#define N 1024          // 1024 x 1024 Matrix
#define TILE_DIM 32     // 32x32 Thread Tile (Matching Warp dimensions)

// ============================================================================
// 1. NAIVE TRANSPOSE KERNEL
// Reads rows (Coalesced), writes columns (UNCOALESCED - Slow)
// ============================================================================
__global__ void transposeNaive(const float* in, float* out, int width, int height) {
    int x = blockIdx.x * blockDim.x + threadIdx.x; // Global Column
    int y = blockIdx.y * blockDim.y + threadIdx.y; // Global Row

    if (x < width && y < height) {
        // Read contiguous (Row-Major: y * width + x) -> Coalesced
        float val = in[y * width + x];

        // Write strided (Transposed position: x * height + y) -> UNCOALESCED
        out[x * height + y] = val;
    }
}

// ============================================================================
// 2. SHARED MEMORY TILE TRANSPOSE KERNEL
// Coalesced Reads into Shared Memory, Coalesced Writes to Global Memory
// ============================================================================
__global__ void transposeCoalesced(const float* in, float* out, int width, int height) {
    // Shared Memory Tile (32x33 to prevent Bank Conflicts using 1-float padding)
    __shared__ float tile[TILE_DIM][TILE_DIM + 1];

    // Compute input matrix indices (Reading row-wise)
    int x = blockIdx.x * TILE_DIM + threadIdx.x;
    int y = blockIdx.y * TILE_DIM + threadIdx.y;

    // 1. Read from Global Memory (COALESCED) -> Store into Shared Memory
    if (x < width && y < height) {
        tile[threadIdx.y][threadIdx.x] = in[y * width + x];
    }

    // Wait for all 1024 threads in the block to finish loading their tile
    __syncthreads();

    // Compute output matrix indices (Re-map thread blocks to Transposed Grid)
    int out_x = blockIdx.y * TILE_DIM + threadIdx.x;
    int out_y = blockIdx.x * TILE_DIM + threadIdx.y;

    // 2. Read from Shared Memory (Transposed) -> Write to Global Memory (COALESCED)
    if (out_x < height && out_y < width) {
        // Notice we read tile[threadIdx.x][threadIdx.y] (Transposed read from fast SRAM)
        // And write out_y * height + out_x (COALESCED contiguous write to VRAM)
        out[out_y * height + out_x] = tile[threadIdx.x][threadIdx.y];
    }
}

int main() {
    size_t bytes = N * N * sizeof(float);

    // Host Memory Allocation
    float *h_in = (float*)malloc(bytes);
    float *h_out = (float*)malloc(bytes);

    for (int i = 0; i < N * N; i++) {
        h_in[i] = static_cast<float>(i);
    }

    // Device Memory Allocation
    float *d_in, *d_out;
    cudaMalloc(&d_in, bytes);
    cudaMalloc(&d_out, bytes);

    cudaMemcpy(d_in, h_in, bytes, cudaMemcpyHostToDevice);

    // Grid and Block dimensions (32x32 threads = 1024 threads per block)
    dim3 blockSize(TILE_DIM, TILE_DIM);
    dim3 gridSize((N + TILE_DIM - 1) / TILE_DIM, (N + TILE_DIM - 1) / TILE_DIM);

    // CUDA Events for Execution Timing
    cudaEvent_t start, stop;
    cudaEventCreate(&start);
    cudaEventCreate(&stop);

    // --- Execute Naive Transpose ---
    cudaEventRecord(start);
    transposeNaive<<<gridSize, blockSize>>>(d_in, d_out, N, N);
    cudaEventRecord(stop);
    cudaEventSynchronize(stop);
    float naiveTime = 0;
    cudaEventElapsedTime(&naiveTime, start, stop);

    // --- Execute Coalesced Transpose ---
    cudaEventRecord(start);
    transposeCoalesced<<<gridSize, blockSize>>>(d_in, d_out, N, N);
    cudaEventRecord(stop);
    cudaEventSynchronize(stop);
    float coalescedTime = 0;
    cudaEventElapsedTime(&coalescedTime, start, stop);

    // Display Performance Results
    std::cout << "Matrix Size: " << N << "x" << N << std::endl;
    std::cout << "Naive Transpose Time:     " << naiveTime << " ms" << std::endl;
    std::cout << "Coalesced Transpose Time: " << coalescedTime << " ms" << std::endl;
    std::cout << "Speedup Factor:           " << naiveTime / coalescedTime << "x" << std::endl;

    // Cleanup
    cudaFree(d_in);
    cudaFree(d_out);
    free(h_in);
    free(h_out);

    return 0;
}
```


---

## 9. Measuring the impact

You do not need exact numbers, but the order of magnitude is important:

- A coalesced memory-bound kernel can approach the theoretical memory bandwidth of the GPU (hundreds of GB/s on modern cards).
- An uncoalesced or random-access version of the same kernel may achieve only a small fraction of that bandwidth.

For a simple copy or element-wise kernel, the difference between coalesced and badly strided access can easily be 5× to 20×.

---

## 10. Summary: the coalescing rule

When writing a kernel, ask this about every memory access inside a warp:

> Do adjacent threads in the warp access adjacent memory addresses?

If yes, the access is coalesced and efficient.

If no, figure out whether the pattern is unavoidable or a bug. Often it is fixable by:

- swapping which thread index maps to which data dimension,
- padding or transposing data before the kernel,
- using shared memory to reorganize accesses, or
- accepting the cost because the algorithm genuinely needs scattered access.

```text
COALESCING CHECKLIST

□ Adjacent threads → adjacent memory addresses?
□ Access is mostly contiguous within each warp?
□ For 2D data, adjacent threads move along the contiguous dimension?
□ If strided access is needed, consider shared-memory tiling or pre-transposing
```

---

## 11. What comes next

Coalescing is the first performance topic, but it is not the only one. The next note should cover **shared-memory tiling**: how to use `__shared__` memory to load data coalesced from global memory, reorganize it inside the SM, and then write it back coalesced even when the natural algorithm wants an uncoalesced pattern. After that comes **occupancy**: how register and shared-memory usage determine how many warps can live on an SM, and therefore how well the GPU hides latency.
