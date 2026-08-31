---
title:  "CUDA Shared Memory Tiling"
date:   2026-09-01
categories: ["gpu"]
tags: ["gpu", "cuda", "nvidia", "shared-memory", "tiling", "performance"]

---

# CUDA Shared Memory Tiling

The [previous note](/gpu/2026-08-30-3-cuda-memory-coalescing) showed that coalesced memory access is the key to memory-bound kernel performance. But some algorithms naturally want uncoalesced access patterns. The fix is **shared-memory tiling**: load data into fast on-chip SRAM in a coalesced way, rearrange it there, then write it back to global memory in a coalesced way.

This note explains the tiling pattern, why `__syncthreads()` is essential, the bank-conflict problem, and how to choose tile sizes.

---

## 1. What shared memory is, revisited

From the hardware note: each SM has a small, fast, on-chip SRAM. CUDA exposes part of it as **shared memory** (`__shared__` in code). Key facts:

- It lives on the SM, so access is roughly 100× faster than global memory.
- It is visible only to threads in the same block.
- It is programmer-managed, not an automatic cache.
- It is a limited resource, so using more per block reduces occupancy.

Shared memory turns the GPU from "read directly from slow global memory" into "read once, reuse many times, write back efficiently."

---

## 2. The tiling pattern

A tile is a small sub-block of data that one thread block loads into shared memory. The general flow is:

```text
1. Each thread loads one (or a few) elements from global memory
   into shared memory, using coalesced access.

2. __syncthreads()
   Wait until every thread in the block has finished loading.

3. Each thread reads from shared memory in whatever pattern the
   algorithm needs (even if it would be uncoalesced in global memory).

4. Compute and/or write results back to global memory in a coalesced pattern.
```

The trick is that the expensive, coalescing-sensitive operation happens only at the boundaries (global loads/stores). The cheap, flexible access happens in shared memory.

```text
Global Memory (slow, off-chip)        Shared Memory (fast, on-chip)
        │                                    │
        │  coalesced load                    │  flexible read/write
        ▼                                    ▼
   [ tile data ]  ───────────────►   [ tile in __shared__ ]
        ▲                                    │
        │  coalesced store                   │  compute / transpose
        │                                    │
        └────────────────────────────────────┘
```

---

## 3. The classic example: matrix transpose

Matrix transpose reads rows (coalesced) but writes columns (uncoalesced). Tiling fixes this.

### Naive transpose (uncoalesced writes)

```cpp
__global__ void transposeNaive(const float *in, float *out,
                               int width, int height)
{
    int x = blockIdx.x * blockDim.x + threadIdx.x;
    int y = blockIdx.y * blockDim.y + threadIdx.y;

    if (x < width && y < height) {
        float val = in[y * width + x];      // coalesced read
        out[x * height + y] = val;          // uncoalesced write
    }
}
```

The write is uncoalesced because adjacent threads in a warp write to memory separated by `height` floats.

### Tiled transpose

```cpp
#define TILE_DIM 32

__global__ void transposeTiled(const float *in, float *out,
                             int width, int height)
{
    // 1. Allocate shared memory tile, with padding to avoid bank conflicts
    __shared__ float tile[TILE_DIM][TILE_DIM + 1];

    // 2. Global input coordinates
    int x = blockIdx.x * TILE_DIM + threadIdx.x;
    int y = blockIdx.y * TILE_DIM + threadIdx.y;

    // 3. Coalesced load from global memory into shared memory
    if (x < width && y < height) {
        tile[threadIdx.y][threadIdx.x] = in[y * width + x];
    }

    // 4. Wait for all threads in the block to finish loading
    __syncthreads();

    // 5. Compute transposed output coordinates
    //    The block (blockIdx.x, blockIdx.y) maps to (blockIdx.y, blockIdx.x) in output.
    int outX = blockIdx.y * TILE_DIM + threadIdx.x;
    int outY = blockIdx.x * TILE_DIM + threadIdx.y;

    // 6. Read transposed from shared memory, write coalesced to global memory
    if (outX < height && outY < width) {
        out[outY * height + outX] = tile[threadIdx.x][threadIdx.y];
    }
}
```

Launch:

```cpp
dim3 blockSize(TILE_DIM, TILE_DIM);
dim3 gridSize((width + TILE_DIM - 1) / TILE_DIM,
              (height + TILE_DIM - 1) / TILE_DIM);
transposeTiled<<<gridSize, blockSize>>>(d_in, d_out, width, height);
```

> _syncthreads() syncs all threads in a block..., but how?  if a block has say 1024 threads, 32 threads form a warp, in one batch only 4 warps are scheduled, does it mean for all warps it executes until here and stops?

Yes. Even though the hardware scheduler can only execute a few warps at the exact same time (due to physical execution resource limits on the Streaming Multiprocessor), `__syncthreads()` forces a logical barrier across the entire block.

The GPU hardware maintains a barrier state for that specific thread block. When a warp reaches the `__syncthreads()` instruction, the hardware pauses that warp and marks it as "blocked."

Once those first 4 active warps hit the barrier and pause, they clear out of the active scheduler. The GPU then schedules the next batch of warps (e.g., warps 5 through 8). This process repeats until all warps in the block have reached the barrier.

Once the 32nd warp arrives, the hardware clears the barrier. All 32 warps are marked as "ready" again, and the scheduler resumes executing them batch-by-batch from the very next instruction.

> ` __shared__ float tile[TILE_DIM][TILE_DIM + 1];`, does this mean each thread gets a 32x33 Tile?

**No, individual threads do NOT get a 32x33 tile of their own.**

The entire block of **1,024 threads shares one single 32x33 matrix** in shared memory. Each individual thread in the block is only responsible for holding **1 single float** inside that grid.

### What are Shared Memory Banks?

Shared Memory (on-chip SRAM) is physically split into **32 equal memory banks** (numbered 0 to 31) that operate in parallel.

* **Bank 0:** Stores elements 0, 32, 64, ...
* **Bank 1:** Stores elements 1, 33, 65, ...
* **Bank 31:** Stores elements 31, 63, 95, ...

The rule for maximum speed: **Each of the 32 threads in a warp should access a DIFFERENT bank at the same clock cycle.**

#### Without Padding: `float tile[32][32]` (Bank Conflict)

If you allocate a strict 32 x 32 matrix in 2D shared memory:

| Row in Tile | Column 0 Bank | Column 1 Bank | ... | Column 31 Bank |
| --- | --- | --- | --- | --- |
| **Row 0** | **Bank 0** | Bank 1 | ... | Bank 31 |
| **Row 1** | **Bank 0** | Bank 1 | ... | Bank 31 |
| **Row 2** | **Bank 0** | Bank 1 | ... | Bank 31 |

#### Phase 1: The Load (Coalesced & Fast ⚡)

Threads read row-wise: `tile[threadIdx.y][threadIdx.x]`.

Thread 0 reads Bank 0, Thread 1 reads Bank 1, Thread 31 reads Bank 31.

**Result:** 32 different banks accessed simultaneously -> Zero conflict!

#### Phase 2: The Transposed Read (32-Way Bank Conflict 🐢)

When writing back out to global memory, the code reads down a column: `tile[threadIdx.x][threadIdx.y]`.

Look at what happens when Warp 0 (`threadIdx.y = 0`) reads down **Column 0** (`threadIdx.x` goes from 0 to 31):

* Thread 0 reads `tile[0][0]` -> **Bank 0**
* Thread 1 reads `tile[1][0]` -> **Bank 0**
* Thread 2 reads `tile[2][0]` -> **Bank 0**
* ...
* Thread 31 reads `tile[31][0]` -> **Bank 0**

**All 32 threads in the warp are fighting to read from Bank 0 at the exact same instant.** The hardware is forced to serialize the request into 32 separate sequential reads, slowing down your fast on-chip SRAM by 32x.

---

### With Padding: `float tile[32][33]` (Fixed!)

By adding **1 extra dummy column** (`TILE_DIM + 1`), you shift the memory address layout of every row by 1 position:

| Row in Tile | Column 0 Bank | Column 1 Bank | ... | Column 31 Bank | Column 32 (Padding) |
| --- | --- | --- | --- | --- | --- |
| **Row 0** | **Bank 0** | Bank 1 | ... | Bank 31 | Bank 0 |
| **Row 1** | **Bank 1** | Bank 2 | ... | Bank 0 | Bank 1 |
| **Row 2** | **Bank 2** | Bank 3 | ... | Bank 1 | Bank 2 |

Look at **Column 0** now as you read down vertically:

* Thread 0 reads `tile[0][0]` -> **Bank 0**
* Thread 1 reads `tile[1][0]` -> **Bank 1**
* Thread 2 reads `tile[2][0]` -> **Bank 2**
* ...
* Thread 31 reads `tile[31][0]` -> **Bank 31**

Because of the `+ 1` shift, reading down a column now accesses **32 distinct memory banks simultaneously**.

---

## 4. Walkthrough with diagrams

### Step 1: Coalesced load into shared memory

Each thread in a 32×32 block loads one element from global memory. Adjacent threads in a warp read adjacent columns in the same row, so the load is coalesced.

```text
Input matrix, row-major

           col 0..31      col 32..63
         +-----------+-----------+
row 0-31 | block(0,0)| block(1,0)|
         +-----------+-----------+

Within block(0,0):
Thread (tx,ty) loads in[ty * width + tx]

Warp 0: threads (0..31, 0) read addresses 0..31 in row 0  → coalesced
Warp 1: threads (0..31, 1) read addresses width..width+31  → coalesced
...
```

### Step 2: `__syncthreads()`

Some threads load faster than others, or their memory requests return earlier. The barrier guarantees that when a thread proceeds to step 3, every entry of the tile has been written by some thread in the block.

Without the barrier, a thread could read from `tile[x][y]` before the thread responsible for writing that element had finished.

```text
Thread A loads tile[0][0]
Thread B loads tile[0][1]
...
Thread Z loads tile[31][31]

        __syncthreads()
              │
              ▼
All 1024 loads complete before any read begins
```

### Step 3: Coalesced write from shared memory

Now each thread reads from shared memory with swapped indices and writes to global memory. Adjacent threads in a warp write adjacent columns in the same output row.

```text
Output matrix, row-major (transposed)

            col 0..31       col 32..63
         +------------+------------+
row 0-31 | block(0,0) | block(0,1) |
         +------------+------------+

The block that read block(0,0) now writes block(0,0) in the output grid.
Thread (tx,ty) writes out[ty * height + tx] in the transposed block.

Adjacent threads differ in tx → adjacent columns → coalesced.
```

---

## 5. Bank conflicts and the +1 padding

Shared memory is divided into **banks**. Multiple threads in a warp can access shared memory simultaneously, but only if they hit different banks. If multiple threads hit the same bank at the same time, their accesses serialize, causing a **bank conflict**.

For a 32×32 `float` tile:

```text
Without padding: tile[32][32]

Column 0: tile[0][0], tile[1][0], tile[2][0], ..., tile[31][0]
These are 32 floats apart in memory.

If each float is 4 bytes and there are 32 banks, 32 floats apart means
128 bytes apart, which maps to the SAME bank.

So a warp reading column 0 all hits bank 0 → 32-way bank conflict.
```

With `tile[32][33]`, consecutive row elements are 33 floats apart:

```text
With padding: tile[32][33]

Column 0: tile[0][0], tile[1][0], tile[2][0], ..., tile[31][0]
These are 33 floats apart.

33 floats × 4 bytes = 132 bytes
132 bytes mod (32 banks × 4 bytes) = 132 mod 128 = 4 bytes

So each row element in the same column maps to a different bank.
```

The extra column wastes a small amount of shared memory but eliminates the conflict.

```text
Column read without padding:          Column read with padding:
tile[0][0]  → bank 0                  tile[0][0]  → bank 0
tile[1][0]  → bank 0   (CONFLICT)     tile[1][0]  → bank 1
tile[2][0]  → bank 0   (CONFLICT)     tile[2][0]  → bank 2
...                                   ...

Without padding: 32 serialized accesses.
With padding:    1 parallel access.
```

---

## 6. `__syncthreads()` in detail

`__syncthreads()` is a barrier for all threads in the same block. Every thread must reach it before any thread can proceed past it.

### Why it is needed

In the transpose example, threads read shared-memory locations that other threads wrote. Without a barrier, you have a read-after-write race.

```text
Thread 0 writes tile[0][0]
Thread 1 reads  tile[0][0]

Without barrier:
  Thread 1 might read before Thread 0 has written.

With barrier:
  Thread 0 writes → barrier → Thread 1 reads
  The read is guaranteed to see the write.
```

### The divergence deadlock

`__syncthreads()` must be called by **all** threads in the block, or none. If some threads take a branch that includes the barrier and others do not, the waiting threads hang forever.

```cpp
// DANGEROUS
if (threadIdx.x < 16) {
    // some work
    __syncthreads();   // threads 16..31 never reach here
} else {
    // other work
    // no __syncthreads()
}
```

This kernel will deadlock. The fix is to call `__syncthreads()` outside the branch so that all threads in the block execute it:

```cpp
// SAFE
if (threadIdx.x < 16) {
    // some work
} else {
    // other work
}
__syncthreads();   // all threads reach this
```

---

## 7. Tile size tradeoffs

Choosing `TILE_DIM` involves balancing several factors:

| Factor | Larger tile | Smaller tile |
|--------|-------------|--------------|
| Data reuse | More reuse per global load | Less reuse |
| Shared memory use | More per block, lower occupancy | Less per block, higher occupancy |
| Work per thread | More, fewer global transactions | Less, more global transactions |
| Bank conflicts | Easier to hit with power-of-2 tiles | Less of an issue |

A 32×32 tile is popular because:

- It matches the warp width (32 threads).
- A 32×32 `float` tile with padding uses `32 × 33 × 4 = 4,224 bytes` of shared memory, which fits comfortably on modern GPUs.
- It gives one warp per row/column, making coalescing natural.

But the right tile size depends on the algorithm and the GPU's shared-memory capacity. For example, double-precision matrices need twice the shared memory per element, so a smaller tile might be necessary.

---

## 8. Boundary handling for partial tiles

Real matrices are not always multiples of the tile size. The guards in the transpose kernel handle this:

```cpp
if (x < width && y < height) {
    tile[threadIdx.y][threadIdx.x] = in[y * width + x];
}
```

Threads outside the matrix simply do not load. The shared-memory tile may contain uninitialized values at the edges, but those positions are never written back because of the output guard.

```text
Matrix width = 50, TILE_DIM = 32

Block (1,0) covers columns 32..49, but the tile is 32×32.
Threads with tx >= 18 skip the load.
Threads with outX >= 50 or outY >= 50 skip the store.

The uninitialized edge values in shared memory are harmless.
```

---

## 9. Another example: matrix multiplication

Tiling is also the key to fast matrix multiplication. Without tiling, each thread reads one row of A and one column of B, but the row of A is not reused by other threads in the block.

With tiling, the block loads a tile of A and a tile of B into shared memory. All threads in the block then compute partial dot products using those tiles. The same A and B elements are reused across many threads, reducing global memory traffic.

```text
For each output tile:
    Load tile A into shared memory  (coalesced)
    Load tile B into shared memory  (coalesced)
    __syncthreads()
    Each thread accumulates its partial dot product
    __syncthreads()
Write output tile (coalesced)
```

The full matrix-multiplication kernel is longer, but the pattern is identical: coalesced load, barrier, compute from shared memory, barrier, coalesced store.

---

## 10. Summary

Shared-memory tiling is the standard technique for fixing uncoalesced access patterns and reusing data.

```text
TILING PATTERN

1. Coalesced load from global memory into __shared__
2. __syncthreads()
3. Read/compute from shared memory in whatever pattern you need
4. __syncthreads() if necessary
5. Coalesced write back to global memory
```

Key takeaways:

- Shared memory is fast but limited and block-scoped.
- `__syncthreads()` prevents read-after-write races and must be reached by all threads in the block.
- Bank conflicts can be avoided with padding, most commonly `TILE_DIM + 1`.
- Tile size affects both performance and occupancy.
- Boundary guards handle partial tiles at the edges.

---

## 11. What comes next

With coalescing and tiling understood, the next major performance topic is **occupancy**: how register and shared-memory usage limit the number of warps that can live on an SM, and therefore how well the GPU hides memory latency. After that, the natural progression is to concrete optimization patterns like loop unrolling, warp shuffle, and CUDA streams.
