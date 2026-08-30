---
title:  "CUDA Thread Hierarchy: Grids, Blocks, Warps, and Threads"
date:   2026-08-30
categories: ["gpu"]
tags: ["gpu", "cuda", "nvidia", "parallel-computing", "thread-hierarchy"]

---

# CUDA Thread Hierarchy: Grids, Blocks, Warps, and Threads

The [previous note](/gpu/2026-08-29-anatomy-of-a-gpu) mapped the hardware: SM, warp scheduler, register file, shared memory, L2, device memory. This note maps the *software abstraction* CUDA exposes on top of that hardware. The two maps fit together almost one-to-one, and once you see how, most of CUDA stops being arbitrary syntax and becomes named hardware concepts.

CUDA organizes parallel work into four nested levels:

```text
Grid
 └── Block  (threads in a block can share fast on-chip memory, and sync)
      └── Warp (32 threads, executed in lockstep on the hardware)
           └── Thread  (your kernel code, from one thread's point of view)
```

This note works from the bottom up: start with the thread (the thing you actually program), then warp, then block, then grid, then show how the whole tower maps onto the GPU die.

---

## 1. The thread: you write scalar code

A **CUDA thread** is the smallest unit of execution. It has its own:

- program counter (conceptually — in practice warps share one)
- register state
- private local memory
- a unique identity (`threadIdx`)

When you write a CUDA kernel, you write it as if it runs on **one scalar thread**. You do not write a loop over pixels or matrix elements; you write what *one* element does, and CUDA launches millions of these threads.

### Mental model

On a CPU, if you want to add two arrays, you write:

```text
for i = 0 to N-1:
    C[i] = A[i] + B[i]
```

On a GPU, the kernel is:

```text
i = my_global_thread_id
C[i] = A[i] + B[i]
```

The loop is replaced by the launch: you ask the GPU to spawn N threads, each one picking its own `i`. This is the central programming shift.

```text
CPU thinking:        GPU thinking:
"iterate over data"  "spawn one worker per data element"
```

---

## 2. The warp: 32 threads in lockstep

A **warp** is a group of 32 threads that the hardware executes together. This is not a software convenience; it is the GPU's native execution width. NVIDIA SMs are physically built around issuing one instruction for 32 lanes at once.

### What "lockstep" actually means

When a warp scheduler issues an instruction, all 32 threads in the warp do the same operation at the same time — but each thread operates on its *own* data.

```text
Warp of 32 threads executing:  C[i] = A[i] + B[i]

Thread 0:  C[0]  = A[0]  + B[0]
Thread 1:  C[1]  = A[1]  + B[1]
Thread 2:  C[2]  = A[2]  + B[2]
  ...
Thread 31: C[31] = A[31] + B[31]

Same instruction, different data → SIMD at the hardware level,
but programmed as if each thread is independent → SIMT.
```

All 32 threads fetch the same instruction, but each thread has its own registers holding its own `i`, its own `A[i]`, its own `B[i]`. The arithmetic happens in parallel across 32 lanes.

### Why 32?

Because the SM's ALU partitions, schedulers, and register file are designed around 32-wide lockstep execution. It is not tunable. You do not choose warp size in CUDA; it is a fixed property of NVIDIA hardware.

```text
Thread 0  Thread 1  Thread 2  ...  Thread 31
   |         |         |              |
   +---------+---------+--------------+
             |
         ONE instruction
             |
             v
      32 ALU lanes in parallel
```

### Warp divergence: the first performance trap

Because a warp executes one instruction at a time, if the 32 threads in a warp take different paths through a branch, the warp must execute **both** paths. Threads not taking the current path are masked off (they do not write results).

```text
if (x > 0) {
    // path A
} else {
    // path B
}
```

If, in one warp, 16 threads have `x > 0` and 16 do not, the hardware does this:

```text
cycle 1:  execute path A with threads 0..15 active, 16..31 masked off
cycle 2:  execute path B with threads 16..31 active, 0..15 masked off
```

The warp took twice as long as it would have if all threads had agreed. This is **warp divergence**. It serializes branches *within a warp*, not across warps.

```text
Good: all threads in warp take same branch
      Warp:  [A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A]
      Cost:  1 path

Bad: threads split evenly
      Warp:  [A A A A A A A A A A A A A A A A B B B B B B B B B B B B B B B B]
      Cost:  A then B  → 2× the branch work
```

The important detail: divergence is **per-warp**. If thread 0 is in warp 0 and takes path A, and thread 32 is in warp 1 and takes path B, those are different warps. Each warp is internally uniform, so there is no divergence penalty. The bad case is only when threads *inside the same warp* disagree.

### Activity mask

Internally, the SM tracks which threads in a warp are active with an **activity mask**. A branch sets the mask; the instructions inside the branch only affect threads whose bit is set.

```text
Warp activity mask (32 bits, one per thread):

Path A active:  11111111111111110000000000000000
Path B active:  00000000000000001111111111111111
```

The hardware literally cannot issue a partially-active instruction differently; it runs the instruction for all 32 lanes and just disables the writeback for masked-off threads.

### Warp scheduler revisited

Remember from the hardware note: the warp scheduler picks a *ready warp* each cycle and issues its next instruction. It does not pick individual threads. This is why the warp is the real scheduling unit, even though the thread is the programming unit.

```text
SM
 └── Warp scheduler
      ├── Warp 0  (threads 0-31)
      ├── Warp 1  (threads 32-63)
      ├── Warp 2  (threads 64-95)
      └── ...
```

When the scheduler issues for warp 0, all 32 threads of warp 0 advance one instruction together.

---

## 3. The block: a group of threads that live together on one SM

A **block** (also called a CTA, Cooperative Thread Array) is a group of threads that are guaranteed to run on the same SM. This is the key unit for two things:

1. **Shared memory**: threads in a block can use a fast, programmer-managed scratchpad.
2. **Synchronization**: threads in a block can barrier-synchronize with each other.

A block can contain up to 1024 threads on modern NVIDIA GPUs. Threads within a block are organized in up to three dimensions (`threadIdx.x`, `threadIdx.y`, `threadIdx.z`), which is convenient for mapping to 1D, 2D, or 3D data.

### Blocks are hardware-scheduled onto one SM

When you launch a kernel, the GigaThread Engine assigns blocks to SMs. One block is never split across SMs; it stays on one SM for its entire life.

```text
Kernel launch:

Grid
 ├── Block 0  ──→  SM 5
 ├── Block 1  ──→  SM 12
 ├── Block 2  ──→  SM 5   (if SM 5 still has room)
 ├── Block 3  ──→  SM 88
 └── ...
```

A single SM can run multiple blocks at the same time, as long as the combined resources (registers, shared memory, warp slots) fit. This is why a block is capped in size: it must fit within one SM's resources.

### Threads in a block → warps automatically

The 1024 threads in a block are divided into warps of 32 by the hardware:

```text
Block of 256 threads
 ├── Warp 0:   threads 0..31
 ├── Warp 1:  threads 32..63
 ├── Warp 2:  threads 64..95
 ├── Warp 3:  threads 96..127
 ├── Warp 4: threads 128..159
 ├── Warp 5: threads 160..191
 ├── Warp 6: threads 192..223
 └── Warp 7: threads 224..255
```

The grouping is deterministic: thread IDs increase linearly, and every consecutive 32 threads form a warp. For 3D blocks, the hardware linearizes the index in x-major order (x changes fastest, then y, then z). This matters for memory coalescing, which we will cover later.

> This is bit contradicting because a block has 1024 threads but only 32 threads can execute simultaneously because of the warp size scheduled per SM. Aren't we losing out parallelism per block this way? A block with 1024 threads is divided into 64 warps, if a SM executes 1 warp at a time, then it shouldn't it take 64 clock cycles to execute the block?

The immediate answer to this is "a SM can execute multiple warps simultaneously". We already saw a SM has 4 partitions, and each partition can execute 1 warp at a time. So, a SM can execute 4 warps simultaneously. So 128 threads can execute simultaneously, which will reduce it to 32 clock cycles to execute the block.

#### Inside an SM: The Hardware Sub-Cores

An SM is not just one giant execution pipe. On modern architectures (like Ampere, Ada Lovelace, or Hopper), a single SM is physically divided into 4 processing blocks (often called SMSPs or execution sub-cores).

Each of those 4 sub-cores contains its own:
- Warp Scheduler & Dispatch Unit
- Dedicated Register File
- Group of FP32 / INT32 CUDA Cores

```
STREAMING MULTIPROCESSOR (SM)
 ┌──────────────────────────────────────────────────────────────────┐
 ├─────────────────┬─────────────────┬─────────────────┬────────────┤
 │  Sub-Core 0     │  Sub-Core 1     │  Sub-Core 2     │ Sub-Core 3 │
 │                 │                 │                 │            │
 │ [Warp Scheduler]│ [Warp Scheduler]│ [Warp Scheduler]│ [Warp Sched]│
 │ [32 CUDA Cores] │ [32 CUDA Cores] │ [32 CUDA Cores] │ [32 Cores] │
 └─────────────────┴─────────────────┴─────────────────┴────────────┘
 ```

 Because an SM has 4 Warp Schedulers, it can physically execute 4 warps (128 threads) simultaneously on Cycle 1.

How a 1,024-Thread Block Actually Runs on 1 SMWhen a block of 1,024 threads ($32 \text{ warps}$) is assigned to an SM:All 32 warps are loaded into the SM's memory at once. Their registers and state live on chip simultaneously.Cycle 1: The 4 Warp Schedulers pick 4 ready warps (say, Warp 0, Warp 8, Warp 16, Warp 24) and issue instructions to their respective 32 CUDA Cores simultaneously.Cycle 2: If those 4 warps stall (e.g., waiting to fetch data from VRAM), the schedulers instantly switch context with zero overhead to 4 other ready warps (say, Warp 1, Warp 9, Warp 17, Warp 25).

#### How a 1,024-Thread Block Actually Runs on 1 SM

When a block of 1,024 threads (32 warps) is assigned to an SM:

1. **All 32 warps are loaded into the SM's memory at once.** Their registers and state live on chip simultaneously.
2. **Cycle 1**: The 4 Warp Schedulers pick 4 ready warps (say, Warp 0, Warp 8, Warp 16, Warp 24) and issue instructions to their respective 32 CUDA Cores simultaneously.
3. **Cycle 2**: If those 4 warps stall (e.g., waiting to fetch data from VRAM), the schedulers instantly switch context with zero overhead to 4 other ready warps (say, Warp 1, Warp 9, Warp 17, Warp 25).

#### Why Keep 1,024 Threads on 1 SM If They Can't All Run at Once?

This brings us to the core secret of GPU performance: **Latency Hiding.**

- When Warp 0 asks to read data from main memory (VRAM), it takes hundreds of clock cycles for that data to return.
- On a CPU, the core would sit idle or try complex branch predictions.
- On a GPU, while Warp 0 is waiting for memory, the SM simply executes Warp 1, Warp 2, Warp 3, and so on.

By the time the schedulers cycle through the other warps in the block, Warp 0's memory fetch has finished, and it is ready to execute again. **Having 1,024 threads sitting on the SM isn't about running them all in 1 cycle—it's about making sure the GPU cores NEVER run out of work to do while waiting for memory.**

### Shared memory: the block's fast scratchpad

Each SM has a small, fast, on-chip SRAM that CUDA exposes as **shared memory**. Because the block lives on one SM, all threads in that block can read and write the same shared memory.

```text
Block on one SM
 ├── Thread 0  ──┐
 ├── Thread 1  ──┤
 ├── Thread 2  ──┼──→  Shared Memory (on-chip, ~tens of KB)
 ├── ...       ──┤
 └── Thread N  ──┘
```

Typical pattern:

1. Each thread loads one element from global memory into shared memory.
2. All threads call `__syncthreads()` to make sure the loads are visible.
3. Threads read from shared memory (now fast and reusable) instead of global memory.

Shared memory is the main way threads within a block cooperate. Blocks cannot see each other's shared memory.

### Synchronization inside a block

`__syncthreads()` is a barrier: every thread in the block must reach it before any thread proceeds. This is safe and cheap because all threads are on the same SM. There is no built-in way to synchronize all threads in the entire grid inside a kernel — blocks are independent by design.

```text
Thread 0:  load → sync → compute → sync → store
Thread 1:  load → sync → compute → sync → store
Thread 2:  load → sync → compute → sync → store
              ↑              ↑
           barrier        barrier
```

If one thread is late to the barrier, all threads wait. Deadlocks happen if a thread can reach a `__syncthreads()` on one branch but not another within the same block.

### Block resource limits

A block is not just "up to 1024 threads." It is also constrained by what one SM has available:

- **Registers**: if each thread uses 64 registers and the block has 1024 threads, the block needs 65,536 registers. If the SM's register file is 64K registers, the block cannot run.
- **Shared memory**: if the block uses 48 KB of shared memory and the SM only has 48 KB configured for shared memory, only one such block can be resident on that SM.
- **Warps**: an SM has a maximum number of resident warps. A 1024-thread block is 32 warps, which may fill a large fraction of an SM's warp slots by itself.

These constraints determine **occupancy**: how many warps can be resident on an SM at once. The hardware note introduced occupancy; the thread hierarchy is where it becomes concrete.

> The math with registers seems bit off, because if an SM runs only 128 thread together, it only needs 64 * 128 = 8192 registers to be reserved right? why does it needs to reserve the registers for entire block 64 * 1024 = 65536?

But that’s not how the resource limit is being calculated.

A block of 1024 threads requires: `1024 * 64 = 65,536` registers. That’s because the entire block is allocated resources when it is resident, even though the SM’s execution hardware processes those threads in groups/waves rather than all at once.

**A block is a logical unit that gets resources allocated for all of its threads when the block is resident.**

**Because the SM switches between warps instantly without saving/restoring register state to main memory (zero-overhead context switching), all 65,536 registers must stay resident in the SM's physical register file the entire time the block lives on that SM.**

When a block is created, it will be pinned to one of the SM's. Let's say blocks A and B are both pinned to same SM. Block A has 12 warps with 20k registers and block B has 24 warps with 30k registers. Since their combined register requirement is 50k, both of them can be pinned to same SM. Since a SM runs 4 warps at a time, it can pick any combinations of warps from both blocks since all of them have already been allocated memory. 

```
Time 1:
A-W0  A-W1  B-W3  B-W7

Time 2:
A-W5  B-W1  B-W2  A-W8

Time 3:
B-W9  B-W10 A-W2  A-W3
```



---

## 4. The grid: all blocks of one kernel launch

A **grid** is the collection of all blocks launched by one kernel invocation. Blocks in a grid are **independent**:

- They can execute in any order.
- They can run on any SM.
- There is no guaranteed way for one block to communicate with another block during the kernel.

This independence is what lets the GPU scale from a few SMs to hundreds of SMs. The scheduler is free to assign blocks wherever there is room.

```text
Grid for one kernel launch
 ├── Block (0,0)
 ├── Block (1,0)
 ├── Block (2,0)
 ├── ...
 ├── Block (0,1)
 ├── Block (1,1)
 └── ...

Each block is an independent bag of warps that can land on any SM.
```

### Grids can also be 1D, 2D, or 3D

Just like blocks, grids are given as `(blockIdx.x, blockIdx.y, blockIdx.z)`. This is useful when your data is naturally 2D (images) or 3D (volumes). Internally, the hardware still linearizes block IDs when handing work to SMs.

### No global synchronization within a kernel

Because blocks are independent, you cannot put a barrier across the whole grid inside a kernel. If you need all blocks to finish before something else happens, you end the kernel and launch a new one. The kernel boundary is the implicit global synchronization point.

```text
Kernel 1 runs  →  all blocks finish  →  Kernel 2 runs
         ↑                                    ↑
   this is the global sync point       (implicit, guaranteed by CUDA)
```

This is a real constraint. Algorithms that need global communication within one kernel usually have to use atomic operations or split the work into multiple kernels.

---

## 5. Indexing: how a thread finds its data element

Even before writing CUDA code, it helps to see how the indices fit together. Every thread has access to these built-in variables:

- `blockIdx.x`, `blockIdx.y`, `blockIdx.z`: which block this thread is in
- `threadIdx.x`, `threadIdx.y`, `threadIdx.z`: which thread inside the block
- `blockDim.x`, `blockDim.y`, `blockDim.z`: how many threads are in the block
- `gridDim.x`, `gridDim.y`, `gridDim.z`: how many blocks are in the grid

### 1D example

For a 1D grid and 1D block, the global thread ID is:

```text
global_thread_id = blockIdx.x * blockDim.x + threadIdx.x
```

```text
Grid of 4 blocks, block size 8 threads

block 0:  threads 0..7    → global IDs 0..7
block 1:  threads 0..7    → global IDs 8..15
block 2:  threads 0..7    → global IDs 16..23
block 3:  threads 0..7    → global IDs 24..31
```

### 2D example (image processing)

For a 2D image, you might use 2D blocks and a 2D grid:

```text
row = blockIdx.y * blockDim.y + threadIdx.y
col = blockIdx.x * blockDim.x + threadIdx.x

pixel index = row * image_width + col
```

```text
Image divided into 2×2 blocks of 4×4 threads:

        col 0-3       col 4-7
      +-----------+-----------+
row0-3| block(0,0)| block(1,0)|
      | 16 threads| 16 threads|
      +-----------+-----------+
row4-7| block(0,1)| block(1,1)|
      | 16 threads| 16 threads|
      +-----------+-----------+
```

Each thread processes one pixel. Threads inside a block are near each other in the image, which helps memory access patterns (more on that below).

> What's going on here is, when we write CUDA code, we won't have an iterator like i, instead there will be a massive array and each thread has to figure out the element it needs to operate on. For 1D array, its quite simple, the global_thread_id would be the element we operate on. 



**Making Sense of the 2D logic**

CUDA lets you assign 3D coordinates (x, y, z) to blocks and threads purely to make coordinate math easier when working with 2D images, 3D spatial grids, or matrices. The GPU hardware doesn't actually have "2D grids" or "3D cubes" of cores inside it. VRAM is just a single long 1D line of memory addresses ($0, 1, 2, 3, ...), and threads run in 1D warps of 32.

**How CUDA Defines 3D Coordinates**

When launching a kernel, you tell CUDA how to structure your threads:

```cpp
// Create 2D blocks of 16x16 threads (Total = 256 threads per block)
dim3 threadsPerBlock(16, 16, 1); 

// Create a 2D grid of blocks to cover an 800x600 image
dim3 numBlocks(50, 38, 1); 

// Launch kernel
processImage<<<numBlocks, threadsPerBlock>>>(...);
```

> Imagine a 800x600 image chopped up into pieces of 16x16 squares. 

Inside your kernel code, every thread automatically gets built-in variables assigned by CUDA:

| Variable | What it represents |
| --- | --- |
| `threadIdx.x` | Your column position *inside* your local block (e.g., 0 to 15) |
| `threadIdx.y` | Your row position *inside* your local block (e.g., 0 to 15) |
| `blockIdx.x` | Which block column you belong to in the grid (e.g., 0 to 49) |
| `blockIdx.y` | Which block row you belong to in the grid (e.g., 0 to 37) |
| `blockDim.x` | The width of a block (here: 16 threads wide) |
| `blockDim.y` | The height of a block (here: 16 threads tall) |


**Step-by-Step: Finding a Pixel in an Image**

Suppose you have an 800-pixel wide image, and you assign Thread (x=2, y=3) inside Block (x=4, y=1) (assuming 16x16 thread blocks).

**Step 1: Calculate the global X (Column)**

How many threads are to your left?
4 full blocks to your left, plus 2 threads inside your own block:

```
col = (blockIdx.x x blockDim.x) + threadIdx.x
col = (4 x 16) + 2 = 66
```

**Step 2: Calculate the global Y (Row)**

How many threads are above you?
1 full block above you, plus 3 threads inside your own block:

```
row = (blockIdx.y x blockDim.y) + threadIdx.y
row = (1 x 16) + 3 = 19
```

Your thread is responsible for pixel (66, 19) on the 2D image.

**Step 3: Convert 2D (66, 19) into 1D Memory Index**

Because VRAM memory stores image pixels sequentially (Row 0 first, then Row 1, then Row 2...):

```
Row 0: [Pixel 0, Pixel 1, ... Pixel 799]          (800 items)
Row 1: [Pixel 800, Pixel 801, ... Pixel 1599]     (800 items)
...
Row 19: Starts at index (19 * 800) = 15,200
```

To skip 19 complete rows of 800 pixels each, and move 66 columns to the right:

```
memory_index = (row x image_width) + col
memory_index = (19 x 800) + 66 = 15,266
```

Your thread directly reads `imageData[15266]`.

---

## 6. Mapping the hierarchy to the hardware

Now we can overlay the software hierarchy onto the hardware from the previous note.

```text
Software (CUDA)              Hardware (NVIDIA GPU)
-----------------            -----------------------
Grid                         Entire kernel launch
 └── Block                    └── assigned to one SM
      └── Warp                └── executed by warp scheduler
           └── Thread              └── one ALU lane
```

More concretely:

```text
Launch a kernel with a grid of many blocks
        |
        v
GigaThread Engine distributes blocks to SMs
        |
        v
Each SM receives one or more blocks
        |
        v
The SM's warp schedulers run the warps of those blocks
        |
        v
Each warp executes 32 threads in lockstep on the SM's ALUs
```

### What executes where

| Software unit | Hardware home | Key property |
|---------------|---------------|--------------|
| Thread | One lane of a warp | Has its own registers, scalar view of code |
| Warp | Warp scheduler on one SM | 32 threads executed lockstep, scheduling unit |
| Block | One SM (whole lifetime) | Threads share shared memory and can synchronize |
| Grid | Whole GPU | All blocks of one kernel launch, independent |

This table is worth memorizing. Most CUDA performance questions eventually reduce to "what is the unit of X?" and this table answers it.

---

## 7. Memory visibility across the hierarchy

Different levels of the hierarchy can see different memory.

```text
Thread:    sees its own registers and local memory
              |
Warp:       threads share the same instruction stream
              |
Block:      threads share shared memory and L1 cache
              |
Grid:       all blocks share global memory (device memory) and L2
              |
CPU:        host memory, separate address space
```

- **Registers**: private to each thread. Fastest, automatically used by the compiler for local variables.
- **Local memory**: also private to each thread, but stored in device memory if the compiler cannot keep it in registers. Slow spill space.
- **Shared memory**: visible to all threads in one block, on-chip, fast, programmer-managed.
- **Global memory**: visible to all threads in all blocks, off-chip (GDDR/HBM), large, high bandwidth but high latency.
- **L1/L2 caches**: automatic caches of global memory traffic.
- **Host memory**: CPU memory, only reachable through explicit copies or unified memory mechanisms.

The hierarchy of execution maps cleanly onto the memory hierarchy from the previous note.

---

## 8. Why this hierarchy exists

The hierarchy is not an accident. Each level solves a specific problem:

| Level | Problem it solves |
|-------|-------------------|
| Thread | Gives the programmer a simple scalar programming model. |
| Warp | Matches the hardware's 32-wide SIMD/SIMT execution. |
| Block | Bundles threads that share an SM, so they can use fast shared memory and synchronize cheaply. |
| Grid | Provides independent, schedulable chunks of work that the GigaThread Engine can scatter across all SMs. |

Without warps, you would have to think about 32-wide SIMD explicitly. Without blocks, shared memory and synchronization would have to span the whole chip, which is too expensive. Without grids, there would be no coarse unit for the global scheduler to distribute.

---

## 9. Common beginner misconceptions

### "A thread is like a CPU thread"

No. A CPU thread is an independent, preemptively scheduled execution context with its own stack and instruction pointer, scheduled by the OS. A CUDA thread is a scalar lane inside a warp; it cannot run independently of its warp, and it is not preempted by the OS. The right mental model is "one iteration of a massively parallel loop."

### "If I launch 1024 threads in a block, they all run at the same time"

Not necessarily. A block has 1024 threads, which is 32 warps. The SM may only be able to issue instructions from a few warps per cycle, and the rest wait their turn. The block is *resident* on the SM; warps within it take turns based on the scheduler.

### "More threads always means faster"

Only up to the point where you have enough warps to hide latency. Beyond that, adding threads can hurt if you exceed register/shared-memory budgets and reduce occupancy. Also, if your kernel is memory-bound, extra threads cannot exceed the memory bandwidth.

### "Divergence is bad across the whole grid"

Divergence is only bad *within a warp*. Threads in different warps can branch differently with no penalty, because warps are independent scheduling units.

### "Blocks communicate through global memory"

Technically yes, but there is no synchronization guarantee. One block may write to global memory, and another block may read it, but you cannot safely assume the write is visible to the other block unless you end the kernel. For within-block cooperation, use shared memory and `__syncthreads()`.

---

## 10. A concrete picture: matrix addition

Suppose you want to add two 1024×1024 matrices. You launch a 2D grid of 2D blocks.

```text
Matrix dimensions: 1024 × 1024
Block size:        16 × 16  = 256 threads per block
Grid size:         64 × 64   = 4096 blocks
Total threads:     256 × 4096 = 1,048,576 threads
```

Each thread computes one element of the output matrix:

```text
row = blockIdx.y * 16 + threadIdx.y
col = blockIdx.x * 16 + threadIdx.x
C[row][col] = A[row][col] + B[row][col]
```

Hardware view:

```text
Grid (4096 blocks)
 ├── Block (0,0) ──→ SM 7
 │      └── 256 threads → 8 warps
 │            └── each warp adds 32 matrix elements in lockstep
 ├── Block (1,0) ──→ SM 23
 │      └── 256 threads → 8 warps
 ├── ...
 └── Block (63,63) ──→ some SM with free capacity
```

No thread loops over the matrix. Every element has its own thread. The GPU fills all SMs with these independent blocks until the matrix is covered.

---

## 11. Summary: the hierarchy, one page

```text
GRID  ─────────────────────────────────────────────
 All blocks of one kernel launch.
 Blocks are independent; can run on any SM, in any order.
 No global synchronization inside the kernel.

   BLOCK  ──────────────────────────────────────────
   A group of threads that live together on one SM.
   Threads in a block share fast on-chip shared memory.
   Threads in a block can synchronize with __syncthreads().
   Block size is limited by SM resources (registers, shared mem, warps).

     WARP  ────────────────────────────────────────
     A hardware unit of 32 threads executed in lockstep.
     The SM's warp scheduler schedules one warp at a time.
     Divergence within a warp serializes branches.

       THREAD  ────────────────────────────────────
       The scalar unit you program.
       Each thread has its own registers and a unique index.
       You write the kernel as if one thread runs it;
       CUDA launches thousands or millions of copies.
```

### Mapping table

| Concept | Unit size | Can sync with | Shares memory with | Maps to hardware |
|---------|-----------|---------------|--------------------|------------------|
| Thread | 1 thread | — | itself only | One ALU lane |
| Warp | 32 threads | implicit lockstep | nothing explicit | Warp scheduler issue |
| Block | up to 1024 threads | `__syncthreads()` | threads in block | One SM |
| Grid | many blocks | kernel boundary | all threads via global memory | Whole GPU |

---

## 12. What comes next

With the hardware and hierarchy in place, the next logical step is the actual CUDA programming model: how you write a kernel, how you launch it with `<<<grid, block>>>`, and how the built-in indices (`threadIdx`, `blockIdx`, `blockDim`, `gridDim`) let each thread find its work. After that, the first real CUDA performance topics are memory coalescing, occupancy, and shared-memory tiling.

But before writing code, internalize this: CUDA programming is writing scalar code for one thread, launching it as a grid of blocks, and letting the hardware map those blocks onto SMs, warps onto schedulers, and threads onto ALU lanes. Everything else is details on top of that frame.
