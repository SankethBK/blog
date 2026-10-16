---
title:  "Performance Engineering: Memory Hierarchy, Caches, and Data Layout"
date:   2026-10-11
categories: ["performance-engineering"]
tags: ["performance", "memory", "cache", "data-layout", "tlb", "prefetching"]

---

# Performance Engineering: Memory Hierarchy, Caches, and Data Layout

This note is the natural follow-up to the CPU microarchitecture note. There we saw that the CPU retires instructions as fast as it can and stalls when it cannot overlap work. For most programs, the dominant reason it cannot overlap work is memory: data is not where the CPU needs it, when the CPU needs it.

The goal here is to understand the cache hierarchy as a programmer sees it, how data layout controls cache behavior, and how to measure that behavior with the right tools.

## 1. Why memory dominates performance

CPU clock speeds and DRAM latency have diverged for decades. A CPU cycle is less than a nanosecond. A main-memory access can be hundreds of cycles. The gap is bridged by caches and by hiding latency through parallelism.

```text
relative access time (orders of magnitude, not exact)

register          ~1 cycle
L1 cache          ~4 cycles
L2 cache          ~12 cycles
L3 cache          ~40 cycles
DRAM              ~200-300 cycles
SSD               ~100,000 cycles
network/disk      ~10,000,000+ cycles
```

A program that touches main memory on every iteration spends most of its time waiting, not computing. The difference between a cache hit and a cache miss is often 50-100x. That is why data layout and access pattern usually beat micro-optimizations.

## 2. The memory hierarchy

Memory is organized as a hierarchy because no single technology satisfies all three goals: speed, capacity, and cost. Fast memory is expensive and small. Cheap memory is slow and large.

```text
small, fast, expensive
   ┌───────────────┐
   │   registers   │
   ├───────────────┤
   │  L1 cache     │  per core, split into data and instruction
   ├───────────────┤
   │  L2 cache     │  usually private per core
   ├───────────────┤
   │  L3 cache     │  shared across cores
   ├───────────────┤
   │  DRAM         │  main memory
   ├───────────────┤
   │  disk/SSD     │  persistent storage
   └───────────────┘
large, slow, cheap
```

| Level | Typical size (x86 desktop/laptop) | Typical latency | Managed by |
|-------|-----------------------------------|-----------------|------------|
| L1d | 32-48 KiB per core | ~4 cycles | Hardware |
| L1i | 32-64 KiB per core | ~4 cycles | Hardware |
| L2 | 256 KiB - 1 MiB per core | ~12 cycles | Hardware |
| L3 | 8-64 MiB shared | ~40 cycles | Hardware |
| DRAM | 8-64 GiB | ~200-300 cycles | Hardware + OS page tables |
| Disk/SSD | 256+ GiB | ~10,000-100,000+ cycles | OS + filesystem |

The hardware moves data automatically. Your job is to make the access patterns friendly enough that the hardware's predictions are right.

## 3. Cache lines

Data is not moved one byte at a time. It is moved in **cache lines**, typically 64 bytes on x86 and 64 bytes on most ARM cores. A load of one byte brings the entire surrounding 64-byte block into cache.

```text
memory address layout:

   line 0            line 1            line 2
┌─────────────────┬─────────────────┬─────────────────┐
│ byte 0 ... 63   │ byte 64 ... 127 │ byte 128 ... 191│
└─────────────────┴─────────────────┴─────────────────┘

reading byte 5 brings line 0 into cache.
reading byte 70 brings line 1 into cache.
```

This is why spatial locality matters. If you access `a[0]`, then `a[1]`, then `a[2]`, the second and third accesses are free because they are already in the cache line. If you access `a[0]`, then `a[1024]`, then `a[2048]`, each access likely misses.

A useful rule: the CPU fetches a whole cache line for roughly the cost of one access. Design data structures so that the bytes you actually use are near the bytes you fetch.

## 4. Temporal and spatial locality

Caches exploit two kinds of locality:

- **Temporal locality:** if you use a piece of data, you will probably use it again soon. The data stays in cache between accesses.
- **Spatial locality:** if you use a piece of data, you will probably use nearby data soon. Neighboring data arrives in the same cache line.

Code with good locality runs fast. Code with poor locality runs slow even if the instruction count is low.

```c
// good spatial locality: sequential scan
for (int i = 0; i < n; i++) {
    sum += a[i];
}

// poor spatial locality: strided or random access
for (int i = 0; i < n; i++) {
    sum += a[i * 1024];   // jumps across cache lines
}
```

A linked list usually has poor spatial locality because nodes are scattered in memory. An array has good spatial locality because elements are contiguous.

## 5. How caches are organized

A cache is divided into **sets**, each of which holds some number of **ways**. An address maps to exactly one set, but can be stored in any way within that set.

| Organization | Description | Trade-off |
|--------------|-------------|-----------|
| Direct-mapped | 1 way per set | Simple, but prone to conflict misses. |
| Set-associative | N ways per set | Balances flexibility and complexity. |
| Fully associative | Any line anywhere | No conflicts, but expensive and slow for large caches. |

Most CPU caches are set-associative. For example, a 32 KiB L1 cache with 64-byte lines has 512 lines. If it is 8-way set-associative, it has 64 sets with 8 ways each.

```text
address bits used for cache lookup:

┌──────────────────┬───────────────┬────────────┐
│    tag           │   set index   │  offset    │
│  (which line)    │  (which set)  │ (byte in   │
│                  │               │  cache line)│
└──────────────────┴───────────────┴────────────┘
```

The offset selects the byte within a 64-byte line. The set index selects which set. The tag identifies which memory line is stored there.

A **conflict miss** happens when two frequently accessed addresses map to the same set and evict each other, even though other cache sets are idle. This is why power-of-two stride access patterns can be pathological.

```text
conflict miss example:

array size 4096, stride 1024 floats (4096 bytes)
both a[0] and a[1024] map to the same set in a small cache
each access evicts the previous one
cache hit rate collapses despite the cache being large enough overall
```

## 6. Data layout: structure of arrays vs array of structures

How you lay out data in memory is one of the highest-impact decisions you can make.

```c
// Array of Structures (AoS)
struct Particle {
    float x, y, z;   // position
    float vx, vy, vz; // velocity
};
struct Particle particles[N];

// Structure of Arrays (SoA)
struct Particles {
    float x[N], y[N], z[N];
    float vx[N], vy[N], vz[N];
};
```

If your loop only touches `x`, `y`, and `z`, the AoS version loads `vx`, `vy`, `vz` into cache too, wasting half the cache line. The SoA version loads only the needed fields and uses cache lines efficiently.

```c
// AoS: 6 floats per particle, only 3 are used
for (int i = 0; i < N; i++) {
    update_position(&particles[i]);
}

// SoA: 3 contiguous arrays of floats
for (int i = 0; i < N; i++) {
    update_position(&p, i);
}
```

The choice depends on the access pattern:

- Use **SoA** when you touch one field across many elements.
- Use **AoS** when you touch most fields of one element together.
- A hybrid (array of small structures of arrays) is common in high-performance code.

## 7. Alignment and padding

A variable is **naturally aligned** if its address is a multiple of its size. A 4-byte `float` should be at an address divisible by 4. An 8-byte `double` or pointer should be at an address divisible by 8. A 16-byte SIMD type should be at an address divisible by 16.

Misaligned access can cross a cache line, requiring two cache accesses instead of one. On some architectures it raises faults or requires extra hardware support.

```c
// potential misalignment: offset 4 within the struct
struct Bad {
    char c;          // 1 byte
    // 3 bytes padding if compiler inserts it
    float f;         // 4 bytes
};

// if the compiler does not pad, f may be misaligned
```

Compilers usually pad structs to maintain alignment, but that padding can be surprising:

```c
struct A {
    char c;    // 1 byte
    double d;  // 8 bytes, aligned to 8
    int i;     // 4 bytes
};

// typical layout on x86-64:
// c + 7 bytes padding + d (8 bytes) + i (4 bytes) + 4 bytes padding
// total: 24 bytes, not 13
```

Reordering fields can reduce size and improve cache utilization:

```c
struct Better {
    double d;   // 8 bytes
    int i;      // 4 bytes
    char c;     // 1 byte
    // 3 bytes padding
};
// total: 16 bytes
```

## 8. Cache thrashing, capacity misses, and conflict misses

There are three distinct reasons a cache access can miss:

| Miss type | Cause | Fix |
|-----------|-------|-----|
| **Compulsory** | First access to a line; unavoidable | Prefetching can hide latency but not eliminate the miss. |
| **Capacity** | The working set is larger than the cache | Reduce working set, block/tile the algorithm, process in chunks. |
| **Conflict** | Multiple lines compete for the same set | Change access pattern or data size to break alignment. |

**Thrashing** is when the working set is close to the cache size and lines constantly evict each other. A loop that streams through a buffer exactly the size of L2 may thrash L2 because each new line evicts the previous one.

**Capacity misses** are solved by making the working set smaller or by blocking so that a smaller chunk fits in cache at a time.

**Conflict misses** are solved by avoiding power-of-two strides and by being aware of cache associativity.

## 9. Prefetching

CPUs contain hardware prefetchers that predict future accesses and fetch data before it is needed. Common prefetcher types:

| Type | Behavior |
|------|----------|
| **Stream prefetcher** | Detects sequential or strided access and fetches ahead. |
| **Adjacent-line prefetcher** | Fetches the next line when one is accessed. |
| **Pattern prefetcher** | Learns more complex repeating strides or access patterns. |

Prefetchers are extremely effective for sequential scans. They are ineffective or counterproductive for random access.

You can also insert explicit software prefetch instructions:

```c
#include <immintrin.h>

for (int i = 0; i < n; i++) {
    _mm_prefetch((const char *)&a[i + 64], _MM_HINT_T0);  // L1 prefetch
    sum += a[i];
}
```

Software prefetching is fragile. It helps when the hardware prefetcher cannot figure out the pattern, but it can hurt if the data is already in cache or if the prefetch distance is wrong. In most cases, a clean access pattern is better than explicit prefetches.

## 10. TLB and page walks

The CPU uses virtual addresses. Memory uses physical addresses. The translation is done through page tables, and the result is cached in the **translation lookaside buffer (TLB)**.

A TLB miss triggers a **page walk**, which may require reading multiple levels of page tables from memory. On x86-64 that can be 4-5 memory accesses. A TLB miss is therefore much more expensive than a cache miss.

```text
TLB hierarchy:

L1 dTLB:    64-128 entries, 1-4 cycles
L2 STLB:    1024-2048 entries, ~10 cycles
page walk:  hundreds of cycles if tables not in cache
```

| Page size | Coverage with 64-entry L1 TLB |
|-----------|-------------------------------|
| 4 KiB | 256 KiB |
| 2 MiB | 128 MiB |
| 1 GiB | 64 GiB |

Larger pages reduce TLB pressure because each TLB entry covers more memory. Linux supports **huge pages** (`hugetlbfs`, `THP`). For large working sets, huge pages can dramatically reduce page-walk overhead.

```bash
# check transparent huge page status
cat /sys/kernel/mm/transparent_hugepage/enabled

# check huge page allocation
cat /proc/meminfo | grep Huge
```

Common symptoms of TLB pressure:

- High `dTLB-load-misses` counter.
- A program slows down when the working set crosses a few megabytes, even though L3 is much larger.
- Random access patterns hurt more than sequential ones because sequential streams reuse TLB entries.

## 11. False sharing and true sharing

**False sharing** happens when two threads write to different variables that happen to live in the same cache line. The cache coherence protocol serializes updates to that line even though the threads do not share data logically.

```c
int counters[2];   // likely in the same cache line

// thread 0
for (...) counters[0]++;

// thread 1
for (...) counters[1]++;
```

The two counters are independent variables, but the coherence protocol sees writes to the same cache line and bounces it between cores. The fix is padding so that each counter occupies its own cache line:

```c
struct PaddedCounter {
    int value;
    char pad[60];   // 64 bytes total
};
struct PaddedCounter counters[2];
```

**True sharing** is when threads legitimately access the same variable. That requires synchronization and is not solved by padding.

False sharing is a classic micro-optimization trap because the fix is trivial once diagnosed but invisible in source code. `perf c2c` (cache-to-cache) can detect it on supported hardware.

## 12. NUMA

Non-uniform memory access (NUMA) becomes relevant on multi-socket servers. Each socket has its own local DRAM. A core can access its own memory quickly and another socket's memory more slowly.

```text
socket 0                       socket 1
┌──────────────┐               ┌──────────────┐
│ cores + L3   │──interconnect──│ cores + L3   │
│ local DRAM   │               │ local DRAM   │
└──────────────┘               └──────────────┘
```

For single-socket laptops and desktops, NUMA does not matter. For servers, it matters a lot. The Linux `numactl` tool can bind memory allocation and thread execution to specific sockets.

```bash
numactl --hardware            # show NUMA topology
numactl --cpunodebind=0 --membind=0 ./program
```

Even on a single socket, memory bandwidth is shared. If many cores stream through memory, the shared DRAM bandwidth can saturate before any single core is CPU-bound.

## 13. Measuring cache behavior

The right counters tell you whether memory is your bottleneck and which level is hurting you.

```bash
perf stat -e cycles,instructions,L1-dcache-load-misses,L1-dcache-loads,\
               LLC-load-misses,LLC-loads,dTLB-load-misses,dTLB-loads,\
               branch-misses ./your_program
```

| Counter | Interpretation |
|---------|----------------|
| `L1-dcache-load-misses` / `L1-dcache-loads` | L1 data cache miss rate. |
| `LLC-load-misses` / `LLC-loads` | Last-level cache miss rate; these went to DRAM. |
| `dTLB-load-misses` / `dTLB-loads` | TLB miss rate. |

`cachegrind` (part of Valgrind) simulates the cache and reports exact hit/miss numbers for every line of code. It is slow but deterministic and does not depend on real hardware counters.

```bash
valgrind --tool=cachegrind ./your_program
cachegrind_annotate cg.out.*
```

For raw memory latency and bandwidth, tools like Intel Memory Latency Checker (`mlc`) or `lmbench` are useful. These require root and are meant for dedicated machines, not busy laptops.

For a quick sanity check of your access pattern, a microbenchmark that sweeps an array of increasing size can reveal cache sizes and latencies:

```c
// simple pointer-chasing benchmark
// each node points to another cache line; measure average access time
// as the working set grows past L1, L2, L3, and DRAM
```

The curve will show flat regions at each cache level, then a jump to DRAM latency.

## 14. Worked example: row-major vs column-major traversal

A matrix stored in C is row-major: `A[i][j]` and `A[i][j+1]` are adjacent in memory.

```c
// row-major: good spatial locality
for (int i = 0; i < N; i++) {
    for (int j = 0; j < N; j++) {
        sum += A[i][j];
    }
}

// column-major: poor spatial locality in C
for (int j = 0; j < N; j++) {
    for (int i = 0; i < N; i++) {
        sum += A[i][j];
    }
}
```

The row-major version touches memory sequentially. The column-major version jumps by `N * sizeof(float)` bytes per access. For large matrices, the column-major version can be 5-10x slower.

The same principle applies to multidimensional arrays in any language: traverse in the order the language stores elements.

## 15. Worked example: blocking for cache reuse

Matrix multiplication is the classic example where a better algorithm improves cache reuse.

```c
// naive: C[i][j] += A[i][k] * B[k][j]
for i
  for j
    for k
      C[i][j] += A[i][k] * B[k][j];
```

The naive order reads `B[k][j]` with a large stride and does not reuse `A[i][k]` once it falls out of cache. A blocked version processes a small submatrix that fits in cache:

```c
// blocked: process BLOCK x BLOCK tiles
for ii in steps of BLOCK
  for jj in steps of BLOCK
    for kk in steps of BLOCK
      for i in [ii, ii+BLOCK)
        for j in [jj, jj+BLOCK)
          for k in [kk, kk+BLOCK)
            C[i][j] += A[i][k] * B[k][j];
```

A block size chosen to fit in L1 or L2 keeps the working set small, increases reuse, and turns a memory-bound problem into a compute-bound one. The actual code is more complex because of boundary conditions, but the idea is universal: **process data in chunks that fit in fast memory.**

## 16. What comes next

This note covered the memory side of the single-machine model. The next notes in the sequence will cover:

- **The Linux kernel path:** syscalls, scheduling, virtual memory, page cache, block IO, and how to measure kernel overhead.
- **Concurrency and synchronization:** atomics, memory ordering, locks, lock-free structures, and the cost of sharing across cores.
- **Compiler interactions:** what the compiler can optimize, when it fails, and how to read assembly.
- **Rigorous benchmarking:** distributions, variance, timer precision, noise reduction, and statistical methods.

Memory is usually the first thing to profile after CPU stalls. Once you can read cache and TLB counters, you can usually explain why a hot loop is slow without guessing.

## 17. Questions to think about

1. You have an array of structs where each struct is 64 bytes. You only read one 4-byte field per struct in a tight loop. What is the effective memory bandwidth utilization as a fraction of the bytes moved, and what data-layout change would raise it?

2. You write a loop that strides through an array with a power-of-two step, and performance suddenly drops at a specific array size even though that size is smaller than the cache. What cache property caused the drop, and what two changes to the code or data size would likely fix it?

3. A program with a 200 MiB working set runs fine on a server with 1 GiB pages but slows down on a laptop using only 4 KiB pages. The L3 cache is 12 MiB in both cases. Explain why the page size matters, which `perf` counter would confirm it, and why the L3 size is not the relevant comparison.

4. Two threads increment different counters that are not protected by a lock. Throughput is much lower than expected and does not scale with core count. The counters are declared as separate global `int64_t` variables. What could cause this, how would you prove it, and what is the minimum code change to fix it?

5. You replace a random hash-table lookup with a sequential scan over a sorted array. The sorted scan touches more total bytes but is faster. Explain the hardware mechanisms that make sequential access cheaper, and give a situation where the random hash lookup would still win despite the cache cost.

6. A matrix multiplication program runs well for N=512 but poorly for N=513. The matrix is stored in row-major order. What memory-system difference between the two sizes could explain the slowdown, and how would you verify whether it is a cache-size effect or an alignment/conflict effect?
