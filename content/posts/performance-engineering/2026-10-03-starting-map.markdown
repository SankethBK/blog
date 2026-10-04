---
title:  "Performance Engineering: A Practical Starting Map"
date:   2026-10-03
categories: ["performance-engineering"]
tags: ["performance", "systems", "linux", "cpu", "profiling"]

---

# Performance Engineering: A Practical Starting Map

This is the first note in a performance-engineering sequence. It is not a summary of an SRE handbook, a cloud-observability guide, or a treatise on dashboard design. The goal is practical skill at the level of a single machine: understand why a program is slow, decide what to change, and verify that the change worked.

The contexts that matter here are things like a chess engine, the microbenchmark problems on HFT University, a hot loop in the Linux kernel, or any single-node program where you own the source and the hardware. The operating system is the boundary we press against; the hardware is the ground truth.

## 1. The core question

Performance engineering reduces to one question:

```text
Where does the time go, and is that the cheapest place to buy a speedup?
```

Everything else — profilers, counters, queueing theory, cache geometry — is equipment for answering that question accurately. Guessing is expensive. Wrong optimizations are worse than no optimizations because they add complexity without improving the metric that matters.

The metric that matters is almost always **wall-clock time for a real workload**. All other numbers (CPU usage, cache-miss rate, instructions per cycle) are diagnostic tools, not targets. A 30% drop in cache misses is only good if it actually makes the program faster on the workload you care about.

## 2. Latency, throughput, and the shape of work

Before touching a profiler, be precise about what you are optimizing.

| Term | Meaning | Example question |
|------|---------|------------------|
| **Latency** | Time for one unit of work | How long does one search take? |
| **Throughput** | Units of work per unit time | How many requests per second? |
| **Utilization** | How busy a resource is | Is the CPU at 100%? |
| **Efficiency** | Work done per unit of resource | How many searches per joule? |

Latency and throughput are related but not interchangeable. A web server can have high throughput and terrible tail latency. A chess engine cares mostly about latency for one search, but a match player cares about throughput (nodes per second).

```text
single request latency  →  one trip through the program
throughput              →  how many trips fit in a second
```

Utilization is a trap. 100% CPU can mean the program is efficient, or it can mean it is spinning on a lock, or that it is doing unnecessary work. Never optimize utilization directly.

## 3. The two levers for making software faster

Every speedup comes from one of two places:

1. **Do less work.** Better algorithms, fewer allocations, fewer syscalls, less cache thrashing, smaller working sets.
2. **Do the remaining work faster.** Better instruction selection, vectorization, parallelism, lower memory latency, fewer pipeline stalls, less synchronization.

Beginners usually reach for lever 2 too early. Experts spend most of their time on lever 1, because lever 2 has hard ceilings while lever 1 can change the problem entirely. A O(n log n) algorithm beaten by an O(n) algorithm wins even if the O(n log n) code is hand-tuned assembly.

```text
lever 1: change the amount of work
         algorithm, data layout, pruning, batching, avoiding redundancy

lever 2: make each unit of work faster
         SIMD, threads, cache-friendly access, prefetching, lower latency
```

A performance engineer constantly switches between them. Profiling tells you which lever is worth pulling.

## 4. Where CPU time actually goes

The CPU does not measure time in seconds. It measures time in **clock cycles**. A useful identity:

```text
total_cycles ≈ instruction_count × CPI
```

Where CPI is **cycles per instruction**. The product tells you how many cycles the program consumed. To go faster, lower one or both factors.

| Component | What affects it |
|-----------|-----------------|
| Instruction count | Algorithm, compiler, data structure choices |
| CPI | Stalls: cache misses, branch mispredictions, dependencies, TLB misses, resource contention |

A modern out-of-order CPU tries to execute many instructions at once, so CPI can be below 1.0 if the program is highly parallel at the instruction level. But real programs spend cycles waiting, not executing. The waiting is where the money is.

Common reasons the CPU waits:

- **Cache misses.** Data is not in L1/L2/L3; must be fetched from DRAM.
- **Branch mispredictions.** The CPU guessed wrong and has to flush the pipeline.
- **Data dependencies.** The next instruction needs a result that is not ready yet.
- **TLB misses.** Virtual-to-physical address translation is not cached.
- **Resource contention.** Ports, execution units, or load/store queues are full.
- **Serialization.** Atomic instructions, memory fences, or model-specific serializing ops.

```text
fast CPU time:  few instructions, low CPI, predictable data and control flow
slow CPU time:  many instructions, high CPI, cache misses, bad branches, dependencies
```

The first thing a profiler like `perf` gives you is a decomposition into instructions and cycles. That decomposition decides whether you are in the instruction-count world or the CPI world.

## 5. The memory wall

Memory is the dominant bottleneck in most programs. CPU clock speeds have grown much faster than DRAM latency over the last few decades. The gap is bridged by caches.

```text
typical access latencies (order of magnitude):

register       ~0 cycles
L1 cache       ~4 cycles
L2 cache       ~12 cycles
L3 cache       ~40 cycles
DRAM           ~100-300 cycles
SSD            ~10,000-100,000 cycles
network/disk   ~millions of cycles
```

The CPU hides memory latency in three ways: caches, out-of-order execution, and prefetching. Caches work when your program has **locality**:

- **Temporal locality:** reuse the same data soon.
- **Spatial locality:** access nearby data soon.

A cache miss to DRAM costs hundreds of cycles. During those cycles the CPU may do other useful work if it has independent instructions, but many programs are a chain of dependent loads.

```text
pointer chasing example:
    while (node) { node = node->next; }

Each load depends on the previous one. Prefetchers and OoO cannot hide the latency.
This pattern is memory-latency bound.
```

**Cache lines** matter. Data is moved between memory and cache in fixed-size blocks, usually 64 bytes on x86. Accessing one byte brings in 63 neighbors. If your next access is to a neighbor, the load is free. If it is to a different cache line, you pay the miss cost.

**False sharing** is a specific cache-line hazard. Two threads write to different variables that happen to live on the same cache line. The cache coherency protocol (MESI and its variants) bounces that line between cores, even though the threads do not logically share data. This can serialize performance.

```text
thread A writes x[0]  ─┐
thread B writes x[1]   │  same cache line → coherence traffic → slowdown
```

## 6. The operating system as part of the hardware interface

The Linux kernel sits between your program and the hardware. Ignoring it is fine until it becomes the bottleneck, which happens more often than people expect.

Places the kernel can eat time:

- **System calls.** Each syscall is a mode switch. Cheap syscalls (e.g. `getpid`) cost tens to hundreds of cycles. Expensive ones (disk IO, network) can cost millions. Batch when possible.
- **Scheduler.** Context switches, migration between cores, preemption, priority inversion.
- **Virtual memory.** Page faults, TLB misses, page-table walks, swapping.
- **Page cache and block IO.** Reads from disk go through the page cache; writes can be buffered or synchronous.
- **Synchronization primitives.** Futexes, mutexes, rwlocks, semaphores — all involve kernel mediation when contended.
- **Interrupts and timers.** Timer interrupts, network interrupts, rescheduling.

```text
user code
   ↓ syscall
kernel
   ↓
hardware: CPU, caches, memory, disk, network
```

Tools like `perf`, `strace`, `bcc`, and `eBPF` let you observe the kernel boundary. A program that is "CPU bound" might actually be bound by kernel time spent in locks or page faults.

## 7. Profiling and measurement tools

You cannot optimize what you do not measure. The tools below are the practical kit for single-machine work.

| Tool | What it gives you | Typical use |
|------|-------------------|-------------|
| `time` / `clock_gettime` | Wall-clock and CPU time | Quick sanity checks |
| `perf stat` | Cycles, instructions, cache misses, branch misses | Bottleneck category |
| `perf record` / `perf report` | Where time is spent in code | Hotspot location |
| `perf annotate` | Source/asm with costs per line | Why a line is slow |
| `perf top` | Live hotspot view | Interactive investigation |
| `strace` | Syscall trace | Syscall overhead and patterns |
| `valgrind --tool=cachegrind` | Cache hit/miss simulation | Cache behavior (slow but exact) |
| `flamegraph` | Visual call-stack profile | Broad performance shape |
| `toplev` | Micro-architecture metrics | CPU-bound bottleneck drill-down |

`perf` is the workhorse. Start with:

```bash
perf stat ./your_program
```

Look at these first:

```text
cycles              → total work done
instructions        → how much you asked the CPU to do
cycles/instructions → CPI; >1 often means stalls
LLC-load-misses     → main memory pressure
branch-misses       → control-flow unpredictability
```

If `instructions` is high relative to the work accomplished, you are in the algorithmic-reduction game. If `cycles/instructions` is high, you are in the stall-reduction game.

For microbenchmarks, also watch:

- Warmup: first iterations may include JIT, cache fill, or frequency scaling.
- Noise: disable turbo, pin threads, run multiple times, report variance.
- Dead code elimination: make sure the compiler does not delete your benchmark.
- Loop hoisting: the compiler may move work outside the measured loop.

## 8. A practical analysis loop

Here is the loop that actually produces reliable speedups:

```text
1. Define the workload and the metric.
2. Reproduce the measurement until it is stable.
3. Profile to find the hotspot.
4. Form a hypothesis about the bottleneck.
5. Make one focused change.
6. Measure again.
7. If faster, keep it and return to step 3. If not, revert it.
```

The most common failure modes are:

- **Optimizing before measuring.** You rewrite the parser because you assume it is slow; the real cost was a hidden sort.
- **Changing many things at once.** You cannot tell which change helped.
- **Measuring in a different environment.** Production is not your laptop; frequency scaling, thermal limits, and background noise differ.
- **Ignoring variance.** Wall-clock time is a random variable. Report distributions, not single runs.
- **Keeping losing changes.** If a change does not improve the real metric, delete it. Pride is a tax on the codebase.

A good profiler result is a hypothesis generator. A bad profiler result is a Rorschach test where you see whatever you want.

## 9. Laws that shape the work

**Amdahl's Law.** If a fraction `P` of a program can be sped up by `N` times, the total speedup is:

```text
Speedup = 1 / ((1 - P) + P/N)
```

The serial remainder dominates. A program that is 90% parallelizable has a maximum speedup of 10x, even with infinite cores. This is why locking, serialization, and setup costs are so dangerous: they live in the `1 - P` part.

**Little's Law.** In a stable system:

```text
Throughput = Average concurrency / Average latency
```

It is deceptively simple and extremely useful. If you want higher throughput you can either lower latency or increase concurrency. Sometimes the cheapest way to serve more requests is to let more in flight, not to make each one faster.

**Universal Scalability Law (USL).** Extends Amdahl's Law by adding a **coherency penalty** term. As concurrency grows, synchronization and cache-coherency traffic eventually make performance get worse, not just flatten. This explains why adding threads gives linear speedup at first, then diminishing returns, then degradation.

```text
Speedup = N / (1 + α(N - 1) + βN(N - 1))

N  = number of processors
α  = contention penalty
β  = coherency penalty
```

These laws are not recipes; they are reality checks. They stop you from expecting miracles.

## 10. Common bottleneck categories

Use this as a first-pass classifier. Each points to a different lever.

| Category | Signature | What to try |
|----------|-----------|-------------|
| **CPU compute bound** | High instructions, low stalls | Better algorithm, vectorize, reduce branches |
| **Memory bandwidth bound** | High memory traffic, CPI moderate, LLC miss rate high | Reduce memory traffic, improve locality, batch access |
| **Memory latency bound** | Pointer chasing, dependent loads, many L1/L2 misses | Reorder access, prefetch, use arrays instead of linked lists |
| **Branch misprediction bound** | High branch-miss rate | Make branches predictable, branchless code, sort data first |
| **Synchronization bound** | Contended locks, futex time, USL coherency penalty | Finer locking, lock-free structures, reduce sharing |
| **IO bound** | Time in read/write, disk/network wait | Batch, async, cache, reduce syscall count |
| **Instruction fetch bound** | Front-end stalls, icache misses | Reduce code size, hot-loop alignment, avoid excessive inlining |

A program is usually a mixture. The dominant category is the one that explains most of the wall-clock time.

## 11. What comes next

This note is the map, not the territory. The next notes will drill into:

- **CPU microarchitecture in detail:** pipelines, execution ports, the reorder buffer, retirement, and how modern x86 and ARM cores execute instructions.
- **Memory and caches:** cache mapping, prefetchers, false sharing, NUMA, huge pages, and how the Linux kernel manages memory.
- **The Linux kernel path:** syscalls, scheduling, page faults, block IO, the VFS and page cache, and how to measure kernel time.
- **Concurrency and synchronization:** locks, atomics, memory ordering, lock-free patterns, and the cost of sharing.
- **Compiler interactions:** what the compiler can and cannot optimize, how to read assembly, and when hand-tuning beats the compiler.
- **Rigorous benchmarking:** statistics, variance, timer precision, anti-noise techniques, and how to avoid fooling yourself.
- **Domain applications:** applying the framework to a chess engine, HFT-style microbenchmarks, and kernel-level hot paths.

Each of these builds on the single-machine model from this note: define the workload, find where time goes, classify the bottleneck, change one thing, measure again.

## 12. Questions to think about

1. A program runs in half the time when you double the CPU frequency, but only 10% faster when you double the core count. What does that tell you about the nature of its bottlenecks, and what measurements would confirm your guess?

2. You have a loop that touches every element of a large array exactly once. `perf` shows a low instruction count but a very high CPI. Without seeing the source, what are the three most likely causes, and how would you distinguish between them with additional counters?

3. A microbenchmark reports 5 ns per operation. You change the benchmark to use a different input size and the time per operation jumps to 50 ns. The algorithm is O(n). Why might the time per operation still increase with `n`, and how would you decide whether the algorithm or the memory hierarchy is responsible?

4. Two threads each increment a private counter in a tight loop. When placed on different cores, the combined throughput is lower than on the same core. The counters are in different global variables. What mechanism could cause this, what tool would prove it, and what code change would likely fix it?

5. You replace a hash table with a sorted array and binary search. The instruction count drops, but wall-clock time increases. The data set fits in L2 cache. What categories of cost might the binary search be hiding that the hash table did not have, and how would you verify which one dominates?

6. A server has 100 connections in flight and CPU at 80%. You increase the connection limit to 10,000. Throughput rises, then plateaus, then falls while CPU is still below 100%. What class of models explains this shape, and what Linux/kernel measurements would tell you whether contention or coherency is the dominant cause?
