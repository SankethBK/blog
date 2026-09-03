---
title:  "CUDA Reduction: Parallel Sum, Max, and Other Tree Algorithms"
date:   2026-09-02
categories: ["gpu"]
tags: ["gpu", "cuda", "nvidia", "reduction", "parallel-algorithms"]

---

# CUDA Reduction: Parallel Sum, Max, and Other Tree Algorithms

The [previous note](/gpu/2026-09-01-2-cuda-occupancy) covered occupancy. This note covers **reduction**: taking a large array and producing a single value (a sum, max, min, product, or any associative binary operation). Reduction is one of the most important parallel algorithms on a GPU, and it teaches several key CUDA ideas at once: shared memory, thread cooperation, warp-level execution, and multi-kernel launches.

This note builds the algorithm step by step, from a naive atomic version to a tree-based shared-memory reduction.

---

## 1. What reduction is

A reduction applies a binary operator to all elements of an array to produce one result.

```text
Input:  [3, 1, 4, 1, 5, 9, 2, 6]
Sum:    3 + 1 + 4 + 1 + 5 + 9 + 2 + 6 = 31
Max:    max(3, 1, 4, 1, 5, 9, 2, 6) = 9
```

The operator must be **associative** (and usually commutative) for tree-style parallel reduction to work. Addition, maximum, minimum, multiplication, and bitwise AND/OR/XOR are all associative.

On a CPU, reduction is simple: loop through the array and accumulate. On a GPU, thousands of threads produce partial results, and those partial results must be combined into one.

---

## 2. The naive atomic approach (and why it is slow)

The simplest CUDA reduction uses a global variable and atomic operations:

```cpp
__global__ void sumAtomic(const float *in, float *out, int n)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        atomicAdd(out, in[i]);
    }
}
```

All threads in all blocks atomically add to a single global variable.

```text
Thread 0: atomicAdd(&total, in[0])
Thread 1: atomicAdd(&total, in[1])
Thread 2: atomicAdd(&total, in[2])
...

Total is a single global memory location.
Every thread serializes on that one location.
```

This is slow because:

- Atomic operations to the same memory address serialize.
- Thousands of threads contend for one global variable.
- The memory bus carries updates back and forth constantly.

The atomic version is simple and correct, but it defeats the entire purpose of the GPU. We can do much better with a tree.

> Let's understand what exactly happened here slowly

Here we are calling `atomicAdd(out, in[i]);` but we haven't defined `atomicAdd` anywhere, because its a function provided by GPU. Because `atomicAdd` relies on direct hardware support from the GPU's memory controllers, you don't write it using standard C++ logic. However, if you were to build atomicAdd yourself using fundamental low-level synchronization primitives, it would look like a **Compare-And-Swap (CAS)** loop.
(This is for another day).


> We see the pointer to `out` being passed as parameter to `sumAtomic`, does this exist on SRAM on VRAM?

No, `out` is NOT in SRAM. That global variable sits far away in VRAM (Global Memory / DRAM).


> There are 2 problems now, 
> 1. VRAM is already slow 
> 2. we are hammering it with multiple threads

You identified the double penalty:

1. **High Latency Penalty:** Going off-chip to VRAM takes 400 to 800 clock cycles per access compared to ~1 to 3 cycles for SRAM.
2. **Contention Penalty (Serialization):** When multiple threads issue an atomic request to the exact same physical address, the memory controller locks that memory location. Instead of processing 32 thread requests at once in parallel, it serves them one at a time.

Combined, 1,000,000 threads trying to `atomicAdd` to one VRAM location causes the GPU to execute 1,000,000 sequential VRAM writes, which is significantly slower than doing the same sum on a single CPU core!

> The operation seems to have a RAW hazard, does GPU has builtin way identifying and of handling it?

Yes, the GPU hardware handles this at two distinct levels: Scoreboarding and Atomic Memory Units.

**A. Intra-Thread Data Dependencies (Register Hazards)**

Inside a single thread, the GPU's instruction scheduler uses an Instruction Scoreboard to track dependency hazards (RAW, WAR, WAW). If Thread 0 executes:

```cpp
float x = A[i];  // Load from VRAM (Write to register x)
float y = x + 5; // Read from register x (RAW Dependency!)
```

```
Clock Cycle 0:    Thread issues read request for A[i] to VRAM.
Clock Cycles 1-399: Data is traveling across the memory bus from VRAM to the SM...
Clock Cycle 400:  Data finally arrives and is written into Register 'x'.
```

Now, look at the very next instruction:

```cpp
float y = x + 5; // Needs the value inside Register 'x'
```

The arithmetic core (ALU) needs to compute `x + 5` right now at Clock Cycle 1. But the data for x won't physically arrive inside the register until Clock Cycle 400.

The SM's warp scheduler sees that instruction 2 depends on register x from instruction 1. The scheduler instantly stalls that warp and switches to another ready warp on the SM until the VRAM load finishes.

**B. Inter-Thread Atomic Contention (Memory Hazards)**

When thousands of threads issue `atomicAdd(&out, val)` simultaneously, the warp scheduler doesn't stall for inter-thread dependencies—it issues the atomic memory instructions down to the L2 Cache / Memory Controllers.

Modern NVIDIA GPUs contain hardware Atomic Memory Units (AMUs) right inside the L2 Cache:

- The AMU detects that 32 threads in a warp are hitting address `&out`.
- The hardware ALU inside the L2 Cache holds a lock on that memory line and processes the additions in hardware sequence.
- It resolves the RAW race conditions automatically so no data is lost or overwritten incorrectly, but it serializes the hardware throughput to maintain correctness.

> Another interesting thing here is "what if the next instruction is not dependent on the slow VRAM read? will the warp scheduler still switch to different warps or will it continue to run the next instruction of same threads of current warp?

If the very next instruction does not depend on register x, the warp scheduler will keep executing instructions from the exact same warp!

It will not force a switch to another warp unless it hits an instruction that is blocked waiting for data, or runs out of ready instructions in that warp's pipeline.

Consider this modified sequence for a thread:

```cpp
float x = A[i];  // Instruction 1: Load from VRAM into register 'x' (Takes ~400 cycles)
float z = b + c; // Instruction 2: Independent math! Uses registers 'b' and 'c'
float w = d * e; // Instruction 3: Independent math! Uses registers 'd' and 'e'
float y = x + 5; // Instruction 4: RAW Dependency on 'x'! Must wait.
```

Here is how the GPU handles this at the hardware level:

```
Clock Cycle 0:   Issues "x = A[i]". Register 'x' is marked "NOT READY" in the Scoreboard.
Clock Cycle 1:   Looks at next instruction: "z = b + c". 
                 Does it need 'x'? No! 
                 ──► SAME WARP executes "z = b + c" immediately (0 delay).

Clock Cycle 2:   Looks at next instruction: "w = d * e". 
                 Does it need 'x'? No! 
                 ──► SAME WARP executes "w = d * e" immediately.

Clock Cycle 3:   Looks at next instruction: "y = x + 5". 
                 Does it need 'x'? YES! 'x' is still traveling from VRAM (Cycle 3/400).
                 ──► WARP STALLS HERE! 
                 ──► Warp Scheduler NOW switches to another ready warp on the SM.
```



---

## 3. The tree reduction idea

Instead of everyone writing to one global variable, combine values in pairs, then combine the results of those pairs, and so on, until one value remains.

```text
Input:  [3, 1, 4, 1, 5, 9, 2, 6]

Step 1: [3+1, 4+1, 5+9, 2+6] = [4, 5, 14, 8]
Step 2: [4+5, 14+8]        = [9, 22]
Step 3: [9 + 22]           = [31]

This is a binary tree of depth log2(N).
```

A tree reduces the problem size by half at each step, so it takes `log2(N)` steps instead of `N` steps. For a million elements, that is 20 steps instead of a million.

On a GPU, the tree is implemented inside each block using shared memory. One block produces one partial sum. All partial sums are then reduced to the final result.

---

## 4. Shared-memory reduction inside a block

Each block loads its chunk of the input into shared memory, then performs the tree reduction in shared memory. The result of each block is written to a partial-result array in global memory. A second kernel (or a final CPU step) reduces the partial results.

```cpp
#define BLOCK_SIZE 256

__global__ void reduceBlock(const float *in, float *out, int n)
{
    __shared__ float sdata[BLOCK_SIZE];

    int tid = threadIdx.x;
    int i = blockIdx.x * blockDim.x + threadIdx.x;

    // 1. Load one element per thread into shared memory
    sdata[tid] = (i < n) ? in[i] : 0.0f;
    __syncthreads();

    // 2. Tree reduction in shared memory
    for (int s = 1; s < blockDim.x; s *= 2) {
        if (tid % (2 * s) == 0) {
            sdata[tid] += sdata[tid + s];
        }
        __syncthreads();
    }

    // 3. Thread 0 writes the block's partial sum
    if (tid == 0) {
        out[blockIdx.x] = sdata[0];
    }
}
```

> This piece of code is genius because it does in place merge-sort kinda thing. First we allocate an array of size = number of threads, each thread runs a loop. 
> In first iteration, s = 2
> thread 0: does a[0] = a[0] + a[1]
> thread 1: nothing (not divisible by 2)
> thread 2: does a[2] = a[2] + a[2], ...
>
> In second iteration, s = 2. Now notice how a[1], a[3], ... are kind of elements we pretend don't exist
> thread 0: does a[0] = a[0] + a[2]
> thread 1,2,3: does nothing as not divisble by 4
> thread 4: does a[4] = a[4] + a[6] and so on.
>
> There is a `__syncthreads` after each itwration because we want each thread to finish writing their results, as other threads would be using it in next iteration. 
>
> We don't need to worry about coalasced acces here, because rememeber its SRAM

### How the loop works

For `BLOCK_SIZE = 8`:

```text
Initial shared memory:
sdata: [a0, a1, a2, a3, a4, a5, a6, a7]

Step s = 1: threads 0,2,4,6 add pairs offset by 1
  sdata[0] += sdata[1]  → [a0+a1, a1, a2, a3, a4, a5, a6, a7]
  sdata[2] += sdata[3]  → [a0+a1, a1, a2+a3, a3, a4, a5, a6, a7]
  sdata[4] += sdata[5]
  sdata[6] += sdata[7]

Step s = 2: threads 0,4 add pairs offset by 2
  sdata[0] += sdata[2]  → [a0+a1+a2+a3, ..., ..., ...]
  sdata[4] += sdata[6]

Step s = 4: thread 0 adds pairs offset by 4
  sdata[0] += sdata[4]  → [sum of all, ..., ..., ...]
```

After `log2(BLOCK_SIZE)` steps, `sdata[0]` holds the sum of the block's chunk.

### Thread participation

At each step, fewer threads participate. Half the threads are idle at step 1, three-quarters are idle by step 2, and so on. This is a real source of inefficiency that the optimized versions address.

```text
Step 1 (s=1):  T0 T_ T2 T_ T4 T_ T6 T_   active
Step 2 (s=2):  T0 T_ T_ T_ T4 T_ T_ T_   active
Step 3 (s=4):  T0 T_ T_ T_ T_ T_ T_ T_   active
```

(`T_` means inactive due to the `if` condition.)

---

## 5. Interleaved vs sequential addressing

The version above uses **interleaved addressing**: active threads are spaced apart by `2*s`. This pattern causes **bank conflicts** because threads that access `sdata[tid]` and `sdata[tid + s]` with `s` as a power of two may hit the same memory bank.

A better pattern is **sequential addressing**: fold the array in half at each step, with the first half of the threads always active.

```cpp
for (int s = blockDim.x / 2; s > 0; s >>= 1) {
    if (tid < s) {
        sdata[tid] += sdata[tid + s];
    }
    __syncthreads();
}
```

```text
Initial shared memory:
sdata: [a0, a1, a2, a3, a4, a5, a6, a7]

Step s = 4: threads 0..3 add sdata[tid] += sdata[tid+4]
  sdata[0] += sdata[4]
  sdata[1] += sdata[5]
  sdata[2] += sdata[6]
  sdata[3] += sdata[7]
  sdata: [a0+a4, a1+a5, a2+a6, a3+a7, a4, a5, a6, a7]

Step s = 2: threads 0..1 add sdata[tid] += sdata[tid+2]
  sdata[0] += sdata[2]
  sdata[1] += sdata[3]
  sdata: [sum of 0,2,4,6; sum of 1,3,5,7; ...; ...]

Step s = 1: thread 0 adds sdata[0] += sdata[1]
  sdata[0] = sum of all
```

Sequential addressing keeps the active threads contiguous (the first `s` threads) and avoids most bank conflicts because consecutive threads access consecutive shared-memory addresses.

> So the threads will still be inactive in same way, but what this solves is bank conflicts. In previous method, there is a rist of thread 0 and thread 32 both hitting bank 0. But here that won't happen....

> Wait a second, i thought i understood bank conflicts, but apparently not. So let's take a step back.

> From previous note

**What are Shared Memory Banks?**

Shared Memory (on-chip SRAM) is physically split into **32 equal memory banks** (numbered 0 to 31) that operate in parallel.

* **Bank 0:** Stores elements 0, 32, 64, ...
* **Bank 1:** Stores elements 1, 33, 65, ...
* **Bank 31:** Stores elements 31, 63, 95, ...

The rule for maximum speed: **Each of the 32 threads in a warp should access a DIFFERENT bank at the same clock cycle.**

> So the first question here is
> Let's say out blocksize is 64 divided into 2 warps, then we end up allocating an array of size 64 
> warp 0 thread 0 access elem 0: bank 0
> warp 1 thread 0 accesses elem 32: bank 0, is this not a bank conflict? Because a SM is perfectly capable of scheduling multiple SM's right? 

Well, apprarently seems like its not.

Bank conflicts are purely a warp-level, simultaneous hardware event.

The 32 physical memory banks on an SM only care about what happens within a single warp at a single clock cycle execution phase.

When your block has 64 threads:
- Warp 0 = Threads 0 to 31
- Warp 1 = Threads 32 to 63

Because Warp 0 and Warp 1 are scheduled and executed at different times (or on different instruction cycles), their reads never collide in the shared memory crossbar.

- Thread 0 in Warp 0 hits Bank 0 during Warp 0's turn.
- Thread 0 in Warp 1 (which is threadIdx.x = 32) hits Bank 0 during Warp 1's turn.

Since those two accesses do not happen simultaneously in the same warp instruction, zero bank conflict occurs.

> But this is a not a good enough reason to convince myself, next clock cycle? then why did we say SM schedules multiple warps in parallel

But hold off this question for a moment, let's find understand why its a problem only within a warp:

### The Golden Rule of Bank Conflicts

The Golden Rule of Bank Conflicts

To trigger a Bank Conflict, you need **two or more threads INSIDE THE SAME WARP** to request *different array indices* that map to the *same physical bank* during the *same instruction*.

#### Example 1: Warp 0 (No Conflict ⚡)

* Thread 0 reads `sdata[0]` -> **Bank 0**
* Thread 1 reads `sdata[1]` -> **Bank 1**
* Thread 2 reads `sdata[2]` -> **Bank 2**
* ...
* Thread 31 reads `sdata[31]` -> **Bank 31**
*(32 distinct banks for 32 threads in the same warp -> **PERFECT**)*

---

#### Example 2: Warp 0 (32-Way Bank Conflict 🐢)

* Thread 0 reads `sdata[0]` -> **Bank 0**
* Thread 1 reads `sdata[32]` -> **Bank 0**
* Thread 2 reads `sdata[64]` -> **Bank 0**
* ...
* Thread 31 reads `sdata[992]` -> **Bank 0**
*(32 threads in the SAME warp trying to hit Bank 0 simultaneously -> **32-WAY CONFLICT!**)*

---

### One Exception: The Broadcast Mechanism

There is one special case where multiple threads in the same warp *can* hit the same bank without conflict: **when they read the exact same memory address.**

* Thread 0 reads `sdata[5]` -> **Bank 5**
* Thread 1 reads `sdata[5]` -> **Bank 5**
* Thread 2 reads `sdata[5]` -> **Bank 5**

If threads in a warp read the **exact same word**, the hardware uses a **multicast/broadcast unit** to read Bank 5 once and broadcast the value to all requesting threads in 1 clock cycle.

> Now that we are clear, why is it problem within a warp and not b/w multiple warps of a block?
> This is important thought, because i ended up recollecting things i learnt in first few notes


**1. Threads in a Warp Execute in Lockstep**

Every thread in a single 32-thread warp executes the exact same instruction at the exact same physical clock cycle.

When a warp executes `sdata[tid]`, all 32 threads throw their 32 target memory addresses at the 32 Shared Memory banks simultaneously in 1 clock cycle.

- If those 32 addresses hit 32 distinct banks, all 32 reads complete in 1 clock cycle ⚡
- If 32 threads hit different addresses in Bank 0, Bank 0 must serialize them one-by-one, forcing the warp to take 32 clock cycles 🐢


**2. Why Inter-Warp Waiting is Fast (1-2 Cycles vs 32 Cycles)**

Your reasoning about inter-warp arbitration is completely correct:
- **Internal Bank Conflict Penalty (Intra-Warp):** If 32 threads inside Warp 0 collide on Bank 0, Warp 0 is stuck inside the Shared Memory pipeline for 32 clock cycles resolving the conflict sequentially.
- H**ardware Inter-Warp Arbitration (Inter-Warp):** If Warp 0 and Warp 1 hit the memory pipeline at the exact same moment, the hardware memory scheduler simply lets Warp 0 go first on Clock Cycle T, and delays Warp 1 by 1 or 2 clock cycles to Cycle T+1.

A 1-cycle hardware scheduling delay between two independent warps is virtually free, whereas a 32-way intra-warp bank conflict degrades your on-chip SRAM throughput by 32x.

> Now let's understand why the first approach had bank conflict in the first place

```cpp
 sdata[tid] += sdata[tid + s]; 
```

This makes it looks like thread 0 needs both `a[0]` and `a[1]`, because that expression is `a[0] = a[0] + a[1]` at the end of day right? 

Right! But when we said all threads of a warp executes same instruction at the same time, we didn't just mean C program lines, we meant at lower level like assembly equivalent. So thread 0 needs `a[1]` in first ins and `a[0]` in next ins. 

I thought very hard and couldn't reason why first approach has bank conflict but failed. Turns out it doesn't!

> gemini's corrected response - pasting it as it is because it's good

You are **absolutely right**, and whoever told you that is spot on. I made a mistake in my previous explanation by conflating the history of older GPUs with what actually happens on modern hardware.

I owe you a massive correction: **On modern GPUs, the first approach (`if (tid % (2*s) == 0)`) has ZERO bank conflicts.**

Here is exactly why you are right, why I got it wrong, and what the *actual* villain of the first approach is.


**Why the First Approach has NO Bank Conflicts**

Let's do the exact math for Warp 0 (Threads 0 to 31) on a modern GPU with **32 Shared Memory Banks**, looking at Step 1 ($s=1$):

The active threads are 0, 2, 4, 6, 8 ... 30.

* Thread 0 reads index 0 -> **Bank 0**
* Thread 2 reads index 2 -> **Bank 2**
* Thread 16 reads index 16 -> **Bank 16**
* Thread 30 reads index 30 -> **Bank 30**

Every single active thread in Warp 0 hits a completely unique, even-numbered bank. **Zero bank conflicts.**

What about later steps? Let's look at $s=16$:

* The code is `if (tid % 32 == 0)`.
* In Warp 0 (Threads 0 to 31), the **only** active thread is Thread 0!
* If only 1 thread in the warp is making a memory request, a bank conflict is physically impossible.

*(Note: The myth that this approach causes bank conflicts comes from very old GPUs—pre-2010—which only had **16 memory banks**. On those old chips, Thread 0 and Thread 16 would both hit Bank 0, causing a conflict. But on modern 32-bank hardware, this is entirely false.)*


### The REAL Problem: Catastrophic Warp Divergence

If there are no bank conflicts, why is the first approach so slow?

The problem it suffers from is **Warp Divergence**.

In CUDA, a warp of 32 threads executes instructions together. If some threads in the warp take an `if` branch and others don't, the hardware must still spend the clock cycles executing the instruction, but it masks off (turns off) the inactive threads.

> It means once the code branches - warp will still execute the instruction inside a branch for all threads, but it simply hides the effect of that instruction for threads who won't take that branch.  

Look at how much of your GPU's computing power is being thrown in the trash in the first approach:

* **Step s=1:** Threads 0,2,4.. active. Threads 1,3,5.. idle. -> **50% of the Warp is wasted.**
* **Step s=2:** Threads 0,4,8.. active. -> **75% of the Warp is wasted.**
* **Step s=16:** Only Thread 0 active. -> **97% of the Warp is wasted!**

Even though only a few threads are doing work, the warp still takes the full amount of time to execute.

---

### What the Second Approach *Actually* Solves

The second approach (Sequential Addressing: `if (tid < s)`) is not about fixing bank conflicts—it's a masterclass in **curing Warp Divergence**.

Let's say your block size is 256 (which is 8 Warps). Look at how the GPU executes the sequential approach:

**Step s = 128:**

* `if (tid < 128)`
* Threads 0 to 127 are active.
* That is exactly **Warps 0, 1, 2, and 3**.
* These 4 warps are **100% active** (zero divergence). The remaining 4 warps are 100% idle, so the hardware scheduler completely skips them, saving massive time!

**Step s = 32:**

* `if (tid < 32)`
* Threads 0 to 31 are active.
* That is exactly **Warp 0**.
* Warp 0 is **100% active** (zero divergence).

By keeping the active threads contiguous, you ensure that the GPU packs the work into **full, non-divergent warps** for as long as mathematically possible, rather than spreading a tiny amount of work across a bunch of mostly-empty warps.

Thank you for pushing back on this—it's exactly how you uncover what the hardware is *really* doing underneath the abstractions!

> In simple words what its saying is, the number of threads going black are still same, but they are not interleaved anymore. It is like 0,1,2,...x and x+1,x+2,....n go black. What this means is some of the later warps can be entirely turned off and not scheduled at all! compared to later approach where some threads in every warp would be active for quite sometime. 

> But how will the warp know that threads in this warp will do no useful work from on and it can be turned off entirely? is it smart enough to figure out the condition inside the loop never becomes true for any of the iterations?


The short answer is: **No, the hardware is not smart enough to look ahead.** It does not know the condition will be false for all future iterations.

The warp is never actually "turned off permanently" or retired early. It stays alive, but it uses a hardware trick to **instantaneously skip the heavy lifting** inside the loop.

Here is exactly what happens under the hood.

#### 1. The Active Mask (How `if` statements work in hardware)

When a warp hits an `if (condition)` statement, the hardware evaluates that condition for all 32 threads simultaneously. It stores the result in a 32-bit register called the **Active Mask**, where each bit represents a thread (1 = true, 0 = false).

* **Warp 0 (Threads 0-31) checking `if (tid < 32)`:**
The mask evaluates to `11111111111111111111111111111111`. The hardware sees 1s and executes the math inside the `if` block.
* **Warp 4 (Threads 128-159) checking `if (tid < 32)`:**
The mask evaluates to `00000000000000000000000000000000`.

#### 2. The Zero-Mask Jump

When the warp scheduler sees that a warp's Active Mask for an `if` block is exactly zero (all 32 bits are 0), it does something highly optimized: **it instantly jumps the program counter past the end of the `if` block.**

Warp 4 doesn't execute memory loads, it doesn't do addition, and it doesn't write to shared memory. It bypasses the expensive payload in 1 clock cycle.

#### 3. Why the warp CANNOT be turned off entirely

You might wonder, *"Why doesn't the warp just exit the loop completely?"*

Look closely at the loop structure:

```cpp
for (int s = blockDim.x / 2; s > 0; s >>= 1) {
    if (tid < s) {
        sdata[tid] += sdata[tid + s];
    }
    __syncthreads(); // <--- THE TRAP!
}

```

Every single thread in the block **must** hit `__syncthreads()`. If the GPU permanently turned off Warps 4 through 7 because they had no more math to do, Warps 0 through 3 would reach `__syncthreads()` and wait forever for the other warps to arrive, causing a complete GPU deadlock!

#### The Reality of the Execution

For the later iterations (like $s=16$ or $s=8$), Warps 4 through 7 are still running the `for` loop. They are just running it incredibly fast:

1. Update `s` (Very fast).
2. Evaluate `if (tid < s)` -> Mask is 0 (Very fast).
3. Jump past the math (Instant).
4. Hit `__syncthreads()` and wait for Warp 0 to finish its math.

Even though they are "awake," they consume almost zero ALU (math) pipeline resources and zero memory bandwidth, leaving the physical hardware completely free to process Warp 0 at maximum speed!

---

## 6. A complete two-level reduction

One block produces one partial sum. If the array is larger than one block can handle, launch many blocks and then reduce the partial sums.

```text
Input array: 1,000,000 elements
Block size: 256 threads

Level 1: 3907 blocks (ceil(1,000,000 / 256))
Each block loads 256 elements, reduces them, writes 1 partial sum.
Result: 3907 partial sums.

Level 2: launch another reduction kernel on the 3907 partial sums.
Result: ~16 partial sums.

Level 3: repeat until one value remains.
```

In practice, if the final partial-result array is small enough (a few thousand elements), the last reduction can be done on the CPU, or a second kernel can finish it. CUDA libraries like Thrust and cuBLAS handle this automatically.

---

## 7. Why the last warp does not need `__syncthreads()`

Once the reduction reaches the warp level (the last 32 elements), all active threads are in the same warp. Warps execute in lockstep, so synchronization is implicit within the warp.

```text
After s = 32, only threads 0..31 may still be active.
These are warp 0 of the block.

Within a warp, instructions are already synchronized.
`__syncthreads()` is unnecessary.
```

This observation is the basis for warp-shuffle reduction, which avoids shared memory entirely for the last few steps.

---

## 8. Warp-shuffle reduction

Modern CUDA provides warp-level primitives like `__shfl_down_sync` that let threads in the same warp exchange values without shared memory or barriers.

```cpp
__inline__ __device__ float warpReduceSum(float val)
{
    for (int offset = warpSize / 2; offset > 0; offset /= 2) {
        val += __shfl_down_sync(0xffffffff, val, offset);
    }
    return val;
}
```

Each warp reduces its own 32 values to a single value in its lane 0. Then lane 0 of each warp writes its result to shared memory (or to a small array), and a final few steps finish the reduction.

```text
Warp of 32 threads, each holds one value:

Step offset = 16: lane i adds lane i+16
Step offset = 8:  lane i adds lane i+8
Step offset = 4:  lane i adds lane i+4
Step offset = 2:  lane i adds lane i+2
Step offset = 1:  lane i adds lane i+1

Lane 0 now holds the sum of the warp.
```

This is faster than shared memory for the final stages because:

- No shared-memory bank conflicts.
- No explicit synchronization needed inside the warp.
- Data moves through a dedicated warp-shuffle network.

> Let's understand more on `__shfl_down_sync`:

Think of Shared Memory like a **shared whiteboard** in a room: Thread 16 writes a number on the board, steps back, and Thread 0 walks up to read it. That requires memory allocation, address calculations, and bank checks.

**Warp Shuffle (`__shfl_down_sync`) eliminates the whiteboard entirely.**

Inside every NVIDIA Streaming Multiprocessor (SM), there is a physical hardware network connecting the **registers** of all 32 threads in a warp. A warp shuffle lets a thread reach directly into another thread's private register and copy its value in a single clock cycle—no memory needed.

---

### Anatomy of `__shfl_down_sync`

```cpp
float retrieved_val = __shfl_down_sync(0xffffffff, val, offset);

```

* **`0xffffffff` (Full Mask):** Tells the GPU that all 32 threads in the warp are participating (32 ones in binary).
* **`val`:** The variable sitting in your thread's local **register** (not shared memory!).
* **`offset`:** How many thread lanes "ahead" to look. Thread $i$ reads the register of Thread $i + \text{offset}$.

---

### Step-by-Step Trace (Warp of 32 Threads)

Suppose each thread starts with a private register variable `val`:

* Thread 0 has `val = 10`
* Thread 16 has `val = 20`
* Thread 24 has `val = 5`, etc.

Here is how the loop executes across the hardware lanes:

#### 1. `offset = 16`

```cpp
val += __shfl_down_sync(0xffffffff, val, 16);

```

* **Thread 0** reaches into **Thread 16's** register, grabs `20`, and adds it to its own `10`.
*(Thread 0's `val` is now $10 + 20 = 30$)*
* **Thread 8** reaches into **Thread 24's** register, grabs `5`, and adds it to its own `val`.
* All 16 thread pairs exchange data **simultaneously in 1 clock cycle**.

#### 2. `offset = 8`

```cpp
val += __shfl_down_sync(0xffffffff, val, 8);

```

* **Thread 0** reaches into **Thread 8's** register (which now contains Thread 8 + Thread 24) and adds it to its own running total.

#### 3. `offset = 4, 2, 1`

* The process continues halving down to `offset = 1`.
* **Thread 0's `val` register** now holds the sum of all 32 threads in the warp.

---

### Shared Memory vs. Warp Shuffle

| Feature | Volatile Shared Memory (`sdata`) | Warp Shuffle (`__shfl_down_sync`) |
| --- | --- | --- |
| **Where data lives** | Shared Memory (SRAM) | Private Registers |
| **Data Transfer** | Write to SRAM $\rightarrow$ Read from SRAM | Direct Register-to-Register Crossbar |
| **Code Overhead** | Requires `__shared__` array, pointer casts, `volatile` | A 4-line function operating on local variables |
| **Bank Conflicts** | Possible if indices aren't strictly guarded | **Physically impossible** |

---

### The Complete Clean Warp Reduction Function

Instead of writing complex shared memory code for the final 32 elements, CUDA developers drop this helper function into their kernels:

```cpp
__device__ float warpReduceSum(float val) {
    for (int offset = 16; offset > 0; offset /= 2) {
        val += __shfl_down_sync(0xffffffff, val, offset);
    }
    return val; // Lane 0 now holds the sum of all 32 threads
}

```

Every warp in your block can run this independently to collapse its 32 threads down to a single value in Lane 0!

`val` is not in VRAM, its a local variable proviate to thread's register. In caller function, there would be a line like

```cpp
float val = (global_idx < n) ? in[global_idx] : 0.0f;
```

---

## 9. Optimizations in real code

The full optimized reduction kernel combines several techniques:

1. **Sequential addressing** to avoid bank conflicts.
2. **Loop unrolling** for the last few steps to reduce loop overhead.
3. **Warp shuffle** for the last warp instead of shared memory.
4. **Multiple loads per thread** so each block processes more elements, amortizing block overhead.
5. **Vectorized loads** (float2/float4) to increase memory bandwidth.

These optimizations are what make CUDA reductions approach peak memory bandwidth. The Mark Harris reduction talk and the CUDA samples both demonstrate this progression.

---

## 10. Reduction is a pattern, not just sum

The same tree structure works for any associative, commutative operator:

- **max** / **min**: replace `+` with `max` or `min`.
- **product**: replace `+` with `*`.
- **bitwise AND / OR / XOR**: replace `+` with `&`, `|`, or `^`.
- **argmax / argmin**: store both the value and its index; combine by comparing values.

```cpp
if (tid < s) {
    sdata[tid] = max(sdata[tid], sdata[tid + s]);
}
```

The skeleton stays the same; only the combination operator changes.

---

## 11. Common pitfalls

### Non-associative operators

Floating-point addition is technically not associative due to rounding. A parallel reduction may produce a slightly different result than a sequential sum. This is usually acceptable, but it matters for numerical analysis.

### Empty or small inputs

If `n` is smaller than the block size, all threads without valid input must load an identity element (0 for sum, -inf for max, etc.). Otherwise, garbage values enter the reduction.

### Race conditions without `__syncthreads()`

Every reduction step reads values that another thread wrote in the previous step. The barrier is essential.

### Last block partial sums

When the array size is not a multiple of the block size, the last block loads fewer valid elements. Make sure the padding values are identity elements, not garbage.

---

## 12. Summary

Reduction is the fundamental parallel pattern for combining many values into one.

```text
NAIVE:    one atomic variable            → simple, slow
TREE:     pair-wise combine in log2(N)  → fast, requires cooperation

BLOCK REDUCTION:
  1. Load chunk into shared memory
  2. Reduce in shared memory using a tree
  3. Thread 0 writes partial sum to global memory
  4. Repeat with another kernel or CPU step until one value remains
```

Key techniques:

- **Sequential addressing** avoids shared-memory bank conflicts.
- **Warp shuffle** avoids shared memory and barriers for the last warp.
- **Multiple elements per thread** improves memory bandwidth and efficiency.

Reduction appears everywhere in CUDA programs: sum of losses in machine learning, max in reductions, histograms, prefix scans, and many more. Understanding the tree pattern is essential for moving beyond element-wise kernels.

---

## 13. What comes next

With reduction understood, the next logical topic is **CUDA streams and host/device overlap**: launching kernels and memory copies asynchronously so the GPU can compute while the CPU prepares the next batch of data. This is where CUDA stops being about single-kernel speed and starts being about pipeline efficiency.
