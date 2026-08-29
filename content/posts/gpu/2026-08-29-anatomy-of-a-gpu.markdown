---
title:  "Anatomy of a GPU: Hardware Components (NVIDIA)"
date:   2026-08-29
categories: ["gpu"]
tags: ["gpu", "cuda", "nvidia", "computer-architecture"]

---

# Anatomy of a GPU: Hardware Components

The [previous note](/gpu/2026-08-29-cpu-vs-gpu) covered *why* GPUs look the way they do — throughput over latency, thousands of simple cores instead of a few smart ones. This note zooms into the actual silicon: what physically sits on a GPU die, what each piece is called, and what job it does. The goal is to have concrete hardware nouns (SM, warp scheduler, register file, L2, ...) in hand before those same nouns start showing up as CUDA concepts (`threadIdx`, `__shared__`, occupancy, ...).

Since GPU architecture details differ across vendors (and even across generations from the same vendor), this note sticks to **NVIDIA's terminology and design**, since that's what CUDA targets. Exact numbers (core counts, cache sizes, register file size) change every generation (Volta → Turing → Ampere → Hopper → Blackwell), but the *categories* of components and their roles have stayed remarkably stable — that stability is what makes this worth learning as a mental model rather than as trivia about one specific chip.

---

## The 30,000-foot view

A CPU die is mostly control logic and cache wrapped around a handful of ALUs. A GPU die inverts that ratio — most of the silicon is either arithmetic units or the memory system feeding them, and control logic per "core" is deliberately kept simple.

```text
GPU die
 ├── Host interface (PCIe / NVLink) — talks to the CPU
 ├── GigaThread Engine — global work distributor
 ├── L2 cache — shared by the whole chip
 ├── Memory controllers — connect to HBM/GDDR (device memory)
 └── GPCs (Graphics/General Processing Clusters)
       └── SMs (Streaming Multiprocessors)   ← the real "core" of a GPU
             ├── Warp schedulers + dispatch units
             ├── CUDA cores (INT32 / FP32 ALUs)
             ├── Tensor cores (matrix multiply-accumulate units)
             ├── Special Function Units (SFU)
             ├── Load/Store units
             ├── Register file
             └── Shared memory / L1 data cache
```

Everything below this line is either **inside an SM** (the compute engine) or part of the **memory system** that feeds SMs data. Almost everything you'll later tune in CUDA maps to one of these boxes.

Physically laid out on the die, it looks roughly like this — a ring of memory controllers around the edge, a shared L2 in the middle, and GPCs (each holding several SMs) tiling the rest of the chip:

```text
                         Host Interface (PCIe / NVLink)
                                     |
                            GigaThread Engine
                                     |
        +--------------------------------------------------------+
        |  MemCtrl   GPC 0        GPC 1        GPC 2   MemCtrl    |
        |    |      [SM][SM]    [SM][SM]     [SM][SM]     |       |
        |    |      [SM][SM]    [SM][SM]     [SM][SM]     |       |
        |    |                                            |       |
        |    |               shared  L2  cache            |       |
        |    |                                            |       |
        |    |      [SM][SM]    [SM][SM]     [SM][SM]     |       |
        |    |      [SM][SM]    [SM][SM]     [SM][SM]     |       |
        |  MemCtrl   GPC 3        GPC 4        GPC 5   MemCtrl    |
        +--------------------------------------------------------+
                    |                              |
                 HBM/GDDR                       HBM/GDDR
              (device memory)                (device memory)
```

(Real chips vary in GPC/SM counts and floorplan — this is the *shape* of the design, not a schematic of any specific part.)

---

## The Streaming Multiprocessor (SM): the GPU's "core"

If a CPU core is the basic unit of "a place where instructions execute," the **SM (Streaming Multiprocessor)** is the GPU's equivalent. A GPU chip contains dozens to well over a hundred SMs (grouped into GPCs, which are mostly just a physical/organizational grouping — think of a GPC as a mini-cluster of SMs sharing some local infrastructure).

Crucially, an SM is **not** one "core" in the CPU sense — it's itself a small parallel processor containing many ALUs, its own scheduler(s), its own register file, and its own fast on-chip memory. When people say a GPU has "thousands of cores," those are the ALUs living inside all the SMs combined, not thousands of independent SMs.

This matters a lot for CUDA later: a **thread block** you launch is scheduled onto exactly one SM (and stays there for its lifetime), and an SM can hold multiple resident blocks at once, resources permitting. Understanding what lives inside an SM is understanding what those thread blocks are actually competing for.

### What's inside an SM

```text
                         Streaming Multiprocessor (SM)
   +--------------------------------------------------------------------+
   |  Instruction Cache / Instruction Buffer                            |
   |----------------------------------------------------------------    |
   |  Partition 0        Partition 1        Partition 2   Partition 3   |
   |  Warp Scheduler     Warp Scheduler     Warp Sched.    Warp Sched.  |
   |  Dispatch Unit      Dispatch Unit      Dispatch Unit  Dispatch Unit|
   |                                                                    |
   |  [CUDA][CUDA][CUDA]  [CUDA][CUDA][CUDA]   ...  repeated per part.  |
   |  [CUDA][CUDA][CUDA]  [CUDA][CUDA][CUDA]                            |
   |  [ SFU ]             [ SFU ]                                       |
   |  [Tensor Core]       [Tensor Core]                                 |
   |  [LD/ST][LD/ST]      [LD/ST][LD/ST]                                |
   |----------------------------------------------------------------    |
   |            Register File (partitioned across resident threads)    |
   |----------------------------------------------------------------    |
   |     L1 Data Cache  /  Shared Memory   (same on-chip SRAM)          |
   +--------------------------------------------------------------------+
```

Each partition is a self-contained scheduling unit: its warp scheduler picks one ready warp per cycle and dispatches its next instruction to that partition's own slice of CUDA cores, SFU, and Tensor Core — the four partitions run largely independently of each other.

#### CUDA Cores (the ALUs)

These are the basic arithmetic units — the GPU's analog of a CPU's ALU, except there are dozens to over a hundred of them *per SM*, and each one is much simpler than a CPU ALU. A CUDA core typically handles a single FP32 (and/or INT32) operation per cycle; there's no out-of-order execution, no speculation, no branch prediction hardware sitting around one of these — that complexity is exactly what got traded away for sheer count (as covered in the CPU vs GPU note).

CUDA cores are organized into **partitions** within the SM (commonly 4 per SM in recent architectures), each partition serviced by its own warp scheduler — see below.

#### Tensor Cores

Introduced with the Volta architecture (2017) and present in every NVIDIA architecture since, Tensor Cores are specialized units that perform small matrix multiply-accumulate operations (`D = A×B + C`) in a single operation, at much higher throughput than doing the equivalent with regular CUDA cores one multiply-add at a time. They typically operate on reduced/mixed precision (FP16, BF16, INT8, and newer FP8/FP4 formats on later generations) accumulated into higher precision.

These exist specifically because deep learning workloads are dominated by matrix multiplication, and CUDA is now as much a machine-learning substrate as a general HPC one. You won't touch Tensor Cores directly in early CUDA (they're normally reached through libraries like cuBLAS/cuDNN or higher-level frameworks), but it's worth knowing they're a physically distinct unit sitting alongside the regular CUDA cores, not just "the same ALUs running faster."

> CUDA cores perform one `A * B + C` at a time (in 1 clock cycle), while tensor cores perform up to 64 parallel Fused Multiply-Add operations (doing \(4 x 4 x 4) math matrix operations) inside a single core in 1 single clock cycle, . Newer Tensor Cores process even larger dimensions instantly.

#### Special Function Units (SFU)

A small number of dedicated units per SM for transcendental and other functions that would be slow to compute with plain add/multiply — `sin`, `cos`, `exp`, `log`, reciprocal, reciprocal-square-root. These are fast-approximation hardware (trading some precision for speed), which is why CUDA distinguishes fast intrinsics (`__sinf`, `__expf`, routed to SFUs) from the precise standard-library math functions (computed via software sequences on the regular CUDA cores).

#### Load/Store (LD/ST) Units

Handle address calculation and issuing of memory read/write requests for global, local, and shared memory accesses. There are far fewer of these than CUDA cores per SM, which is one reason memory-bound kernels (kernels that mostly load/store rather than compute) often can't keep all the ALUs fed — a preview of why memory access patterns end up mattering so much in CUDA.

#### Warp Scheduler(s) — the GPU's "control unit"

This is the closest thing an SM has to a CPU's control unit, but it does a very different job. A CPU's control unit exists largely to keep *one* instruction stream moving despite branches, hazards, and stalls — hence branch predictors, out-of-order windows, and speculation. A GPU's warp scheduler instead manages *many* independent instruction streams (warps — groups of 32 threads executing in lockstep) resident on the SM at once, and its main trick is **latency hiding through oversubscription**: when one warp stalls (e.g., waiting on a memory load), the scheduler simply switches to issuing instructions from a different warp that's ready to go, at zero cost — there's no pipeline flush or speculation to unwind, because switching warps is just picking a different, independent instruction stream.

Modern SMs have multiple warp schedulers (e.g., 4 per SM), each with its own dispatch unit, each responsible for a partition of the SM's CUDA cores. This is why an SM can have many more resident warps than it can execute in a single cycle — the extra warps exist specifically as a reservoir to hide memory and instruction latency. This single idea — hide latency by having a huge surplus of parallel work, rather than by predicting/speculating on one thread — is arguably the single biggest philosophical difference between CPU and GPU control logic, and it's why GPUs *want* you to launch far more threads than there are physical ALUs to run them.

```text
One warp scheduler's issue slot over time, with 4 resident warps (W0-W3):

cycle:   1    2    3    4    5    6    7    8
W0:     [run][run] stall (waiting on memory) ......... [run]
W1:                [run][run] stall .............
W2:                          [run][run] stall ...
W3:                                    [run][run] stall

issued: W0   W0   W1   W1   W2   W2   W3   W3   <- scheduler always has
                                                     someone ready to go
```

No warp individually got faster — but the ALU partition was never idle waiting on any single warp's memory request. This is latency hiding: stalls are covered by switching to *other* independent work, not by predicting or reordering around the stall the way a CPU would.

#### Register File — the GPU's "registers," at a very different scale

Each SM has a single large register file (tens of thousands of 32-bit registers, e.g. 64K on many recent architectures) that is **statically partitioned at kernel-launch time** among all the threads resident on that SM. If your kernel uses more registers per thread, fewer threads (and thus fewer warps) can be resident simultaneously — this is a real, first-class performance concern in CUDA called **occupancy**, and it's a direct consequence of this hardware fact: registers aren't a fixed handful shared by everyone the way a CPU core's dozen-ish architectural registers are; they're a large shared pool sliced up per-thread.

#### Shared Memory / L1 Data Cache

A relatively small (tens to a couple hundred KB, depending on architecture and configuration) chunk of fast on-chip SRAM per SM, physically the same hardware resource split (in a configurable ratio, on many architectures) between two roles:

- **L1 data cache:** an automatic hardware cache for global memory accesses, working the way you'd expect from CPU caches, just much smaller relative to the amount of parallel work happening.
- **Shared memory:** a programmer-managed scratchpad (`__shared__` in CUDA) that all threads in a block can read and write, and use to synchronize through (`__syncthreads()`). This is the closest thing a GPU has to explicit inter-thread communication at low latency, and it's one of the most important tools for writing fast CUDA kernels — data loaded once into shared memory can be reused by every thread in the block instead of each thread hitting slower global memory independently.

The key distinction from a CPU's L1 cache: shared memory isn't just a cache the hardware manages for you — you explicitly decide what goes into it and when, which is a genuinely new kind of decision CPU programming rarely asks you to make.

#### Instruction Cache / Instruction Buffer

A small cache holding recently fetched instructions for the warps resident on the SM, analogous in purpose to a CPU's I-cache, just serving many concurrent instruction streams instead of one.

---

## Above the SM: the chip-wide shared infrastructure

### GPCs (Processing Clusters)

SMs are grouped into GPCs, mostly a physical/organizational unit — a way of laying out and scaling the chip (more GPCs = more SMs = a bigger, more capable GPU across a product line) rather than something you reason about directly while writing CUDA. You generally don't address a GPC in software; it's a manufacturing/floorplan concept, not a programming one.

### L2 Cache

Unlike the per-SM L1/shared memory, there is a single **L2 cache shared by every SM on the chip** (multiple MBs on modern GPUs — e.g. tens of MB on data-center parts). It sits between the SMs and the memory controllers, caching global memory traffic for all SMs. Because it's shared chip-wide, it's also one of the mechanisms that lets different SMs cooperate on the same data more cheaply than always going all the way out to device memory.

### Memory Controllers and Device Memory (HBM/GDDR)

The GPU's main memory ("device memory," what CUDA calls `cudaMalloc`'d memory) is physically separate from the CPU's system RAM. It's connected to the chip through multiple memory controllers in parallel, feeding either:

- **GDDR** (used on most consumer/gaming GPUs), or
- **HBM — High Bandwidth Memory** (used on data-center GPUs like the A100/H100/B100 class), which stacks memory dies vertically right next to the compute die for a much wider, higher-bandwidth connection.

As covered in the CPU vs GPU note, this memory is built and tuned for **bandwidth** over **latency** — many parallel channels moving huge volumes of data per second, at the cost of any single access being relatively slow. This is the hardware reason memory coalescing (warps accessing contiguous addresses together) matters so much once you're writing kernels: it's what lets your access pattern actually exploit that wide, parallel memory bus instead of wasting most of each fetched chunk.

### GigaThread Engine (global work distributor)

A hardware scheduler sitting above all the SMs, responsible for taking the grid of thread blocks a kernel launch describes and assigning blocks to SMs that have room for them (based on register file space, shared memory, and warp-slot availability). Once a block is assigned to an SM, the per-SM warp schedulers take over from there. Think of it as a two-level scheduling hierarchy: the GigaThread Engine decides *which SM* runs *which block*; each SM's warp schedulers then decide *which warp* within that SM issues *this cycle*.

### Host Interface (PCIe / NVLink)

The physical link connecting the GPU to the CPU (and, in multi-GPU systems, to other GPUs). Standard consumer/most workstation setups use **PCIe**; NVIDIA's data-center parts additionally support **NVLink**, a much higher-bandwidth proprietary interconnect for GPU-to-GPU (and in some systems, GPU-to-CPU) communication. As the earlier note flagged, host and device memory are physically separate address spaces — this interface is the (comparatively slow, relative to on-chip bandwidth) pipe all of that host↔device data has to cross, which is why minimizing and batching transfers over it is a recurring CUDA optimization theme.

---

## The memory hierarchy, top to bottom

Pulling every memory-related piece above into one picture, from fastest/smallest/most-private to slowest/largest/most-shared:

```text
 fast, small, private            Registers (per thread, in the SM's register file)
        |                               |
        |                        Shared Memory / L1  (per SM, on-chip SRAM)
        |                               |
        |                          L2 Cache  (chip-wide, shared by all SMs)
        |                               |
        |                    Device Memory (GDDR/HBM)  (off-chip, on the GPU board)
        v                               |
 slow, large, shared           = = = PCIe / NVLink = = =   (the host<->device boundary)
                                        |
                                  Host (CPU) Memory
```

Everything above the PCIe/NVLink line is memory the GPU can touch directly, at speeds ranging from a few cycles (registers) to a few hundred cycles (device memory). Crossing that line to host memory is orders of magnitude slower than any of the on-GPU hops above it — which is exactly why "minimize host↔device traffic" is the first optimization rule in CUDA, before anything about kernels themselves.

---

## CPU component ↔ GPU component, side by side

| Role                         | CPU                                                  | GPU (NVIDIA)                                                              |
| ---------------------------- | ----------------------------------------------------- | ---------------------------------------------------------------------------- |
| Basic execution unit          | Core                                                  | SM (Streaming Multiprocessor) — itself a small parallel processor            |
| Arithmetic unit                | ALU (few per core, complex)                          | CUDA cores (many per SM, simple); Tensor Cores for matrix ops                |
| Control logic                  | Control unit: branch predictor, OOO scheduler, speculation | Warp scheduler(s): pick a ready warp, no prediction/speculation needed       |
| Fast private storage            | Register file (small, tens of architectural registers) | Register file (large, tens of thousands, statically split across threads)    |
| Small fast memory                | L1/L2/L3 cache (hardware-managed)                    | L1 cache **+** shared memory (same SRAM, partly programmer-managed) per SM     |
| Chip-wide cache                  | Shared LLC (L3)                                       | Shared L2 (chip-wide, feeds all SMs)                                          |
| Main memory                       | System DRAM, latency-optimized                        | Device memory (GDDR/HBM), bandwidth-optimized                                |
| Special math hardware              | FPU (often integrated into the core pipeline)         | Special Function Units (SFU) — fast approximate transcendentals               |
| Global scheduling                   | OS scheduler (software, across cores)                 | GigaThread Engine (hardware, assigns blocks to SMs)                          |
| External interconnect                | Memory bus / QPI / Infinity Fabric                    | PCIe (standard) / NVLink (high-bandwidth, data-center)                      |

---

## Why this hardware layout is exactly what CUDA is designed around

Once these pieces are in place, CUDA's programming model stops looking arbitrary:

- A **grid of thread blocks** exists because the GigaThread Engine needs coarse, independent chunks of work (blocks) to distribute across SMs.
- A **block** is capped in size and tied to shared memory/register budgets because it has to fit, in its entirety, as resident warps on a *single* SM.
- **`__shared__` memory** exists because the hardware literally has a chunk of fast, on-chip, programmer-addressable SRAM per SM that would otherwise sit unused if only treated as an automatic cache.
- **Warps of exactly 32 threads** exist because that's the lockstep execution granularity the SM's ALU partitions and schedulers are physically built around — it's not a software choice, it's the hardware's native unit of execution.
- **Occupancy** (how many warps can be resident on an SM at once) is a direct, computable consequence of how many registers and how much shared memory your kernel demands per thread/block, divided into the SM's fixed register file and shared memory budget.
- **Latency hiding instead of low-latency-per-thread** is the reason you're encouraged to launch *way* more threads than you have ALUs — the surplus warps are what the scheduler switches into whenever another warp stalls on memory.

Going into CUDA with this hardware picture in mind turns most of the "why does the API work this way" questions into "oh, that's just naming the hardware thing directly."
