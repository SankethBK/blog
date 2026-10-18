---
title:  "Lab 2: Memory Hierarchy and Caches"
date:   2026-10-17
categories: ["performance-engineering"]
tags: ["performance", "memory", "cache", "lab", "perf", "tlb", "false-sharing", "prefetching"]

---

# Lab 2: Memory Hierarchy and Caches

This is the hands-on report for the lab in `/home/sanketh/mem-lab` on the Linux x86 laptop. It is the practical companion to `content/posts/performance-engineering/2026-10-11-memory-and-caches.markdown` — every experiment measures something the theory note claims, and a few go past it.

> Same machine caveat as Lab 1: this is an **Intel Core i5-8250U** (15 W mobile part, base 1.6 GHz, max 3.4 GHz). It throttles under sustained load, so chase *ratios*, not absolute nanoseconds. All single-threaded timings below are pinned to one core with `taskset -c 2`.

## 0. Quick start

```bash
ssh sanketh@192.168.1.14
cd /home/sanketh/mem-lab
make

./run.sh all     # every experiment
./run.sh 6b      # one experiment (also: 1..11)
```

Machine summary (from `lscpu` and `/sys/devices/system/cpu/cpu0/cache/`):

| Item | Value |
|------|-------|
| CPU | Intel Core i5-8250U (Kaby Lake R) |
| Cores / threads | 4 / 8 (siblings: cpu0/4, cpu1/5, cpu2/6, cpu3/7) |
| L1d | 32 KiB per core, **8-way**, 64 B lines (64 sets) |
| L2 | 256 KiB per core, **4-way** (1024 sets) |
| L3 | 6 MiB shared, 12-way (8192 sets) |
| L1 dTLB (4K pages) | 64 entries, 4-way set-associative |
| GCC / kernel / perf | 9.4.0 / 5.15.0 / 5.15 |
| Transparent huge pages | mode = `madvise` |

Two practical notes:

- `kernel.perf_event_paranoid` is `-1` on this box from Lab 1. Everything in this lab only needs user-space counters, so if you have `1`, that is fine too.
- THP is in `madvise` mode (`cat /sys/kernel/mm/transparent_hugepage/enabled` → `[madvise]`). Anonymous mappings only get 2 MiB pages if the program asks with `madvise(MADV_HUGEPAGE)`. E7 and E6b rely on this.

All experiments share a tiny header like Lab 1's, plus a page-aligned allocator:

```c
// common.h
#pragma once
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
static inline double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;}
static inline uint64_t rng(uint64_t *s){*s^=*s<<13;*s^=*s>>7;*s^=*s<<17;return *s;}
static inline void *xalloc(size_t n){void*p=NULL;if(posix_memalign(&p,4096,n)){perror("posix_memalign");exit(1);}memset(p,0,n);return p;}
```

The Makefile and `run.sh` are on the laptop (`~/mem-lab/`). Compile flags are the Lab 1 set: `-O2 -g -fno-omit-frame-pointer -march=native`.

## 1. The latency staircase (E1)

**Concept:** a dependent pointer chase with one node per 64-byte line. Because each load needs the previous one, nothing overlaps — you measure pure load-to-use latency at each size, and each level of the hierarchy appears as a plateau. Theory note §1–2.

One detail that matters: **the links must live inside the lines being measured.** The first version of this experiment kept the `next[]` array densely packed in a separate array, and the first 10 sizes all printed the same latency because the actual footprint was 16x smaller than the label said (a 512 KiB "working set" only touched 32 KiB of link storage). Measuring the wrong thing is the most common lab bug; this is a good example.

**How to read this program (mental model).**

Picture `buf` as a long row of 64-byte boxes. We only use the first 8 bytes of each box; those 8 bytes hold the index of the *next* box to visit.

```text
buf layout (one box = one cache line)
+------+------+------+------+
| next | next | next | ...  |   <- only word 0 of each 64-byte line is used
+------+------+------+------+
```

`perm` is a shuffled list of box numbers. During setup we wire the boxes into one random cycle:

```text
for i = 0 .. nodes-1:
    box[perm[i]].next = perm[i+1]
box[perm[nodes-1]].next = perm[0]
```

The timed loop is a **dependent pointer chase**:

```text
p = 0
for s = 0 .. steps-1:
    p = box[p].next
```

In the C code, `p = b[p * WPL]` is exactly that: `WPL = 8` converts a box index into a word offset (64 bytes / 8 bytes per word). The `volatile` keeps the compiler from deleting the loop. Because the address of each load comes from the previous load, the CPU cannot overlap them, so each step is pure load-to-use latency.

```c
// e1_staircase.c
#include "common.h"

#define MAX_SIZE (512UL << 20)   /* 512 MiB upper cap */
#define LINE 64
#define WPL (LINE / sizeof(uint64_t))   /* words per line */

static uint64_t *buf;              /* link stored in first word of each line */
static uint32_t *perm;             /* shuffle scratch, not in the data path */

int main(void)
{
    static const size_t sizes[] = {
        1UL<<10, 2UL<<10, 4UL<<10, 8UL<<10, 16UL<<10, 32UL<<10,
        64UL<<10, 128UL<<10, 256UL<<10, 512UL<<10,
        1UL<<20, 2UL<<20, 4UL<<20, 8UL<<20, 16UL<<20,
        32UL<<20, 64UL<<20, 128UL<<20, 256UL<<20, 512UL<<20,
    };
    uint64_t seed = 0x12345678;

    buf  = xalloc(MAX_SIZE);
    perm = malloc((MAX_SIZE / LINE) * sizeof(uint32_t));
    if (!perm) { perror("malloc"); return 1; }

    puts("working set     ns/access");
    for (size_t si = 0; si < sizeof(sizes)/sizeof(sizes[0]); si++) {
        size_t size  = sizes[si];
        uint32_t nodes = size / LINE;

        /* random single cycle over node indices */
        for (uint32_t i = 0; i < nodes; i++) perm[i] = i;
        for (uint32_t i = nodes - 1; i > 0; i--) {
            uint32_t j = rng(&seed) % (i + 1);
            uint32_t t = perm[i]; perm[i] = perm[j]; perm[j] = t;
        }
        for (uint32_t i = 0; i < nodes - 1; i++)
            buf[(uint64_t)perm[i] * WPL] = perm[i + 1];
        buf[(uint64_t)perm[nodes - 1] * WPL] = perm[0];

        uint64_t steps = (uint64_t)nodes * 8;
        if (steps < (4UL << 20)) steps = 4UL << 20;
        if (steps > (32UL << 20)) steps = 32UL << 20;

        volatile uint64_t *b = buf;
        uint64_t p = 0;
        double t0 = now();
        for (uint64_t s = 0; s < steps; s++) p = b[p * WPL];
        double dt = now() - t0;
        (void)p;

        if (size < (1UL << 20))
            printf("%8zu KiB   %8.3f\n", size >> 10, dt * 1e9 / steps);
        else
            printf("%8zu MiB   %8.3f\n", size >> 20, dt * 1e9 / steps);
    }
    return 0;
}
```

```bash
taskset -c 2 ./e1_staircase
```

**Observed:**

```text
working set     ns/access
       1 KiB      2.065
       2 KiB      2.065
       4 KiB      2.065
       8 KiB      2.065
      16 KiB      2.065
      32 KiB      2.065
      64 KiB      4.132
     128 KiB      4.135
     256 KiB      6.216
     512 KiB     11.090
       1 MiB     12.966
       2 MiB     13.925
       4 MiB     23.873
       8 MiB     91.685
      16 MiB    113.040
      32 MiB    127.581
      64 MiB    130.873
     128 MiB    134.950
     256 MiB    132.925
     512 MiB    136.171
```

```text
  ns/access (log-ish view)
  136 ┤                                              ────────────  DRAM
   92 ┤                                     ┌
   24 ┤                               ┌─────             L3 region
   13 ┤                     ┌─────┐
    6 ┤              ┌
    4 ┤        ┌─────┐                       L2 plateau
    2 ┼────────┘                                  L1 plateau
      └──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──
         32K      128K     256K 512K 1M 2M 4M 8M   512M
```

The plateaus line up with the hardware table:

- **through 32 KiB: ~2.07 ns** — L1d (32 KiB per core). At this CPU's ~2.4 GHz typical turbo, 2.07 ns is about 5 cycles, which matches the 4-5 cycle L1 latency from the note.
- **64–128 KiB: ~4.13 ns** — L2-hit latency (~12 cycles).
- **512 KiB–4 MiB: ~11–24 ns** — the L3 region. It is not a clean shelf like L1/L2 because L3 is shared, adaptive, and the random cycle starts seeing conflicts (L3 is 8 MiB of lines to land in 6 MiB of capacity at 8 MiB size).
- **8 MiB and up: ~92–136 ns** — past the 6 MiB L3, this is DRAM plus page-walk cost (the random walk also beats up the TLB; we come back to that in E7).

The numbers tie directly to the note's latency table (§1): L1 ~4 cycles, L2 ~12, L3 ~40 (13 ns ≈ 30-40 cycles here), DRAM 200-300 cycles (110 ns ≈ 260).

## 2. Find the 64-byte cache line (E2)

**Concept:** sweep a working set much larger than L3 with a constant byte stride. While the stride is below the line size, several touches share one fetched line — the cost per touch rises with stride. At and above the line size, every touch is a new line fetch, and the curve flattens. The knee *is* the line size. Theory note §3.

**How to read this program (mental model).**

`a` is a 256 MiB byte array — large enough that no stride will fit in cache. The program walks this array repeatedly, stepping by `stride` bytes each time.

```text
stride = 1:  |*|*|*|*|*|*|*|*|...   every byte touched
stride = 32: |*--32B--*--32B--*|...   two touches per 64-byte line
stride = 64: |*--------64B--------*|... one touch per line
```

```text
for each stride s:
    reps = chosen so total touches ≈ 64 million
    for r = 0 .. reps-1:
        for off = 0; off < N; off += s:
            sum += a[off]
```

When `s < 64`, several loop iterations fall in the same cache line and share the cost of one fetch. Once `s` reaches 64, every iteration starts a new line fetch, so the cost per touch jumps and then stays flat. The knee *is* the 64-byte line size.

```c
// e2_linesize.c
#include "common.h"

#define N (256UL << 20)          /* 256 MiB working set (> 6 MiB L3) */

int main(void)
{
    static const size_t strides[] = {1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048};
    volatile uint8_t *a = xalloc(N);

    puts("stride (bytes)  ns/access");
    for (size_t si = 0; si < sizeof(strides)/sizeof(strides[0]); si++) {
        size_t s = strides[si];
        uint64_t touches = N / s;
        uint64_t target  = 64UL << 20;                 /* accesses per stride */
        uint64_t reps    = target / touches + 1;

        uint64_t sum = 0;
        double t0 = now();
        for (uint64_t r = 0; r < reps; r++)
            for (uint64_t off = 0; off < N; off += s)
                sum += a[off];
        double dt = now() - t0;
        (void)sum;

        printf("%8zu        %8.3f\n", s, dt * 1e9 / (reps * touches));
    }
    return 0;
}
```

**Observed:**

```text
stride (bytes)  ns/access
       1           0.385
       2           0.415
       4           0.464
       8           0.614
      16           1.064
      32           2.001
      64           8.136
     128          21.873
     256          27.493
     512          29.809
    1024          30.902
    2048          32.452
```

The cost doubles roughly with the stride while `stride < 64`, then jumps at **64** and saturates around 30 ns — exactly the DRAM-bound cost per fetched line. The printout is the 64-byte line seen with no references, just timing.

## 3. Same bytes, different order (E3)

**Concept:** all passes read exactly **one float per 64-byte line** of a 256 MiB array — same total bytes moved, same lines touched. The only difference is the *order*: `seq` visits lines in address order, `rand` visits them in a random permutation. What's left is the story of spatial locality, the L2 stream prefetcher, and TLB reach. Theory note §4, §10.

**How to read this program (mental model).**

`a` is a 256 MiB float array, but we only read **one float every 64 bytes**, so there are 4M logical "lines." `perm` decides the order in which we visit those lines.

```text
a: [line 0][line 1][line 2] ... [line 4M-1]
        ^ only first float of each 64-byte line is used
```

```text
fill each line's float with a random value     # prevents constant-folding
perm = either [0,1,2,...]  or a shuffle

sum = 0
for i in perm:
    sum += a[i * 16]      # 16 floats = 64 bytes, so i*16 is the line's first float
```

The same total bytes are moved in both modes. The only difference is the address sequence. Sequential mode lets the L2 stream prefetcher run ahead and keeps the TLB walker streaming; random mode defeats the prefetcher and jumps to a new 4 KiB page almost every step.

```c
// e3_seqrand.c
#include "common.h"

#define LINE_FLOATS 16                      /* 64 B / 4 B per float */
#define LINES (4UL << 20)                   /* 4 M lines = 256 MiB */

static float a[LINES * LINE_FLOATS];
static uint32_t perm[LINES];

int main(int argc, char **argv)
{
    const char *mode = argc > 1 ? argv[1] : "seq";
    uint64_t seed = 42;

    /* fill with data so the compiler cannot constant-fold the sum away */
    for (uint32_t i = 0; i < LINES; i++)
        a[(uint64_t)i * LINE_FLOATS] = (float)(rng(&seed) & 0xff);

    for (uint32_t i = 0; i < LINES; i++) perm[i] = i;
    if (strcmp(mode, "rand") == 0) {
        for (uint32_t i = LINES - 1; i > 0; i--) {
            uint32_t j = rng(&seed) % (i + 1);
            uint32_t t = perm[i]; perm[i] = perm[j]; perm[j] = t;
        }
    }

    float sink = 0.0f;
    double t0 = now();
    for (uint32_t i = 0; i < LINES; i++)
        sink += a[(uint64_t)perm[i] * LINE_FLOATS];
    double dt = now() - t0;

    double ns = dt * 1e9 / LINES;
    printf("%-8s %8.3f ns/line  %8.2f GB/s moved  (sink=%g)\n",
           mode, ns, 64.0 / ns, sink);
    return 0;
}
```

**Observed:**

```text
seq         3.604 ns/line     17.76 GB/s moved  (sink=5.34981e+08)
rand       29.809 ns/line      2.15 GB/s moved  (sink=5.34974e+08)
```

8.3x slower with *identical* lines fetched. The perf counters show what changed:

```text
-- seq          cycles 501,830,736   L1-misses 9,872,418   LLC-misses 1,544,224   dTLB-misses 141,730
-- rand         cycles 792,714,405   L1-misses 19,046,588  LLC-misses 5,501,988   dTLB-misses 5,191,429
```

Two effects stack. First, the **L2 stream prefetcher** recognizes the sequential walk and fetches lines before the loop asks; random order defeats it and every access becomes a demand miss (~5.5M LLC misses ≈ one per line). Second, 256 MiB is 65,536 pages of 4 KiB, and the random order jumps to a different page almost every step — `dTLB-load-misses` goes from 141k to 5.2M. The theory note's "sequential beats random" claim is several mechanisms cooperating, and each shows up as a different counter.

(One gotcha while building this: the first version left the array as a zero-initialized static and never wrote to it, so GCC **constant-folded the whole sum to zero** and printed `0.000 ns/line`. Fill your buffers with real data.)

## 4. Row-major vs column-major (E4)

The note's worked example (theory §15) directly. C stores `A[i][j]` and `A[i][j+1]` adjacent (row-major), so summing by rows streams while summing by columns strides by `N * 4` bytes.

**How to read this program (mental model).**

`m` is a flat `float[N*N]` array, which C stores in **row-major** order: row `i` occupies indices `[i*N, (i+1)*N)`. Element `(i,j)` is at `m[i*N + j]`.

```text
memory:  row 0 | row 1 | row 2 | ... | row N-1
         <------- N floats each ------>
```

The two loops visit the same elements with the same index expression, but in different orders:

```text
row-major:
    for i:
        for j:
            sum += m[i*N + j]      # walks memory left-to-right

column-major:
    for j:
        for i:
            sum += m[i*N + j]      # jumps by N*4 bytes each step
```

Row-major touches neighbors, so 16 floats share one cache line and 1024 floats share one 4 KiB page. Column-major steps by `N*4` bytes; at `N=4096` that step is 16 KiB, so every element is a new line and a new page.

```c
// e4_rowcol.c
#include "common.h"

int main(int argc, char **argv)
{
    int N = argc > 1 ? atoi(argv[1]) : 4096;      /* 4096x4096 floats = 64 MiB */
    int reps = argc > 2 ? atoi(argv[2]) : 4;
    const char *mode = argc > 3 ? argv[3] : "both";
    float *m = xalloc((size_t)N * N * sizeof(float));
    for (long i = 0; i < (long)N * N; i++) m[i] = 1.0f;

    float sink = 0.0f;
    double t, trow = 0, tcol = 0;

    if (strcmp(mode, "col") != 0) {
        t = now();
        for (int r = 0; r < reps; r++)
            for (int i = 0; i < N; i++)
                for (int j = 0; j < N; j++)
                    sink += m[(size_t)i * N + j];
        trow = (now() - t) / reps;
    }
    if (strcmp(mode, "row") != 0) {
        t = now();
        for (int r = 0; r < reps; r++)
            for (int j = 0; j < N; j++)
                for (int i = 0; i < N; i++)
                    sink += m[(size_t)i * N + j];
        tcol = (now() - t) / reps;
    }

    printf("N=%-4d  row-major %8.1f ms   col-major %8.1f ms   ratio %.1fx  (sink=%g)\n",
           N, trow * 1e3, tcol * 1e3, trow > 0 ? tcol / trow : 0.0, sink);
    return 0;
}
```

**Observed** (N = 4096, so rows are 16 KiB apart):

```text
N=4096  row-major     20.3 ms   col-major    279.9 ms   ratio 13.8x
```

```text
-- row:  cycles 204,877,483   L1-misses 3,393,401    LLC-misses 26,844      dTLB-misses 50,678
-- col:  cycles 458,921,901   L1-misses 27,605,451   LLC-misses 16,605,768  dTLB-misses 16,813,613
```

The counter table tells the whole story. Column access steps by a full row (16 KiB), so **every element is a new cache line** — 16.7M LLC misses ≈ one per element. And because the stride is *four pages*, **every element is also a new page** — 16.8M dTLB misses, also ≈ one per element. Row traversal amortizes a line over 16 floats and a page over 1024. This is why §4 of the note says the same principle applies in any language: traverse in memory order.

## 5. AoS vs SoA (E5)

**Concept:** the note's structure-of-arrays example (§7). The loop only uses `x, y, z` (3 of the 6 floats per particle), so the AoS layout hauls the unused velocities through the cache too.

**How to read this program (mental model).**

The same 4M particles are stored two ways:

```text
AoS:  Particle aos[N] = {x,y,z,vx,vy,vz}   // 24 bytes each
SoA:  float x[N], y[N], z[N]               // only the fields we read
```

Both loops compute the same thing:

```text
AoS:
    for i:
        sum += aos[i].x + aos[i].y + aos[i].z
        # fetches 24 bytes, uses 12

SoA:
    for i:
        sum += soa_x[i] + soa_y[i] + soa_z[i]
        # fetches 12 bytes, uses 12
```

AoS moves twice the cache traffic because it hauls the unused velocity fields along. Both streams are sequential, however, so the prefetcher keeps both reasonably fed; the wall-time speedup is smaller than the traffic ratio.

```c
// e5_aos_soa.c
#include "common.h"

#define N (4UL << 20)   /* 4 M particles */

typedef struct { float x, y, z, vx, vy, vz; } Particle;   /* 24 B */

static Particle aos[N];
static float soa_x[N], soa_y[N], soa_z[N];                /* only what we read */

int main(int argc, char **argv)
{
    const char *mode = argc > 1 ? argv[1] : "both";
    uint64_t seed = 7;
    for (size_t i = 0; i < N; i++) {
        aos[i].x = soa_x[i] = (float)(rng(&seed) & 0xff);
        aos[i].y = soa_y[i] = (float)(rng(&seed) & 0xff);
        aos[i].z = soa_z[i] = (float)(rng(&seed) & 0xff);
        aos[i].vx = aos[i].vy = aos[i].vz = 0.0f;
    }

    int reps = 8;
    double sink = 0.0, t, taos = 0, tsoa = 0;

    if (strcmp(mode, "soa") != 0) {
        t = now();
        for (int r = 0; r < reps; r++)
            for (size_t i = 0; i < N; i++)
                sink += aos[i].x + aos[i].y + aos[i].z;   /* use 12 of 24 B  */
        taos = (now() - t) / reps;
    }
    if (strcmp(mode, "aos") != 0) {
        t = now();
        for (int r = 0; r < reps; r++)
            for (size_t i = 0; i < N; i++)
                sink += soa_x[i] + soa_y[i] + soa_z[i];   /* use everything  */
        tsoa = (now() - t) / reps;
    }

    printf("N=%zu M  AoS %8.1f ms  SoA %8.1f ms  ratio %.2fx  (sink=%g)\n",
           N >> 20, taos * 1e3, tsoa * 1e3, tsoa > 0 ? taos / tsoa : 0.0, sink);
    return 0;
}
```

**Observed:**

```text
N=4 M  AoS      7.2 ms  SoA      5.4 ms  ratio 1.33x
-- AoS only:  cycles 494,933,896   LLC-misses 694,188
-- SoA only:  cycles 451,732,526   LLC-misses 120,908
```

AoS moves 96 MiB per sweep (24 B/particle), SoA moves 48 MiB (12 B/particle) — a 2:1 traffic ratio, visible in the roughly 6:1 LLC-miss ratio. Wall time only improves 1.33x. Why not 2x? Both loops are *sequential streams* that the prefetcher eats happily, so neither is DRAM-latency-bound; AoS hits ~13.3 GB/s effective while SoA's 48 MiB sweep finishes sooner but is partly limited elsewhere (L3, front-end). The honest version of the note's rule: SoA wins by moving **half the bytes**, and you should expect the time win to bracket *at most* the traffic ratio, not always reach it. (And if your loop touches *all six* fields, AoS is fine — layout choices follow the access pattern, not ideology.)

## 6. Measure L1 associativity with a knee (E6)

**Concept:** from the note's §5–6: an address maps to one set; a set has W ways. So take K lines that all map to the **same set** and pointer-chase them in a cycle. While K ≤ W, every line stays resident and every access is an L1 hit. At K = W + 1, the set must evict a line before the cycle comes back to it, and *every* access misses.

On this CPU, L1d is 32 KiB / 8-way / 64 B lines → 64 sets, and the set index lives in address bits 6–11 — which all lie *inside the 4 KiB page*. Any stride that is a multiple of 4096 bits keeps the set index constant: all K addresses land in the same set. A dependent chase exposes the latency directly.

**How to read this program (mental model).**

`buf` is a 64 MiB region. For each `K` we build a tiny cycle of `K` addresses, all separated by the same `stride`:

```text
for i = 0 .. K-1:
    buf[i*stride] = ((i+1) mod K) * stride
```

This creates a dependent chase that bounces among `K` lines:

```text
p = 0
repeat:
    p = buf[p]      # p is a byte offset; buf stores byte offsets
```

```text
stride = 4096:
    address bits 6..11 (the L1 set index) are identical for every line
    -> all K lines land in the SAME L1 set
    -> knee at K = 9 proves 8-way associativity

stride = 4160 (= 4096 + 64):
    each hop advances by one extra line, so lines land in DIFFERENT sets
    -> no knee, flat latency for any K
```

```c
// e6_assoc.c
#include "common.h"

#define SPAN (64UL << 20)

int main(int argc, char **argv)
{
    size_t stride = argc > 1 ? strtoul(argv[1], NULL, 0) : 4096;
    int    maxk   = argc > 2 ? atoi(argv[2]) : 12;
    int    kmin   = argc > 3 ? atoi(argv[3]) : 1;
    uint64_t steps = argc > 4 ? strtoull(argv[4], NULL, 0) : (4UL << 20);

    uint64_t *buf = xalloc(SPAN);
    volatile uint64_t *vb = buf;

    printf("stride %zu, chained cycle over K same-set lines\n", stride);
    puts("  K    ns/access");
    for (int k = kmin; k <= maxk; k++) {
        for (int i = 0; i < k; i++)
            buf[(uint64_t)(i * stride) / 8] = (uint64_t)(((i + 1) % k) * stride) / 8;

        uint64_t p = 0;
        double t0 = now();
        for (uint64_t s = 0; s < steps; s++) p = vb[p];
        double dt = now() - t0;
        (void)p;
        printf("%3d   %8.3f\n", k, dt * 1e9 / steps);
    }
    return 0;
}
```

**Observed:**

```text
stride 4096, chained cycle over K same-set lines     <-- same L1 set
  K    ns/access
  1      1.812
  2      1.781
  4      1.774
  8      1.793          flat: fits in 8 ways, pure L1 latency
  9      3.835        <-- knee at 9 = 8 ways + 1
 12      3.838

stride 4160 (4 KiB + 64 B), control: different L1 sets
  K    ns/access
  1      1.772
 12      1.770          flat: never conflicts, any K

stride 65536, same L1 set (again a multiple of 4096)
  K    ns/access
  1      1.772
  4      1.775
  5      4.425        <-- knee at 5?!  L1 is 8-way, what is this?
  8      4.427
  9      6.489
 12     11.453
```

The 4 KiB stride behaves exactly like the textbook: flat at L1 latency for K ≤ 8, jumps to ~3.8 ns (L2-hit territory) at K = 9, and the control stride (4096+64, which walks into a different set each hop) never jumps at all. `L1-dcache-load-misses` confirms: K=8 → ~2 misses per 1280 accesses, K=9 → misses ≈ accesses.

But the 64 KiB stride — also a multiple of 4096, same data-cache sets — shows a knee at **K = 5**, four lines short of L1's 8 ways. And it gets stranger: the L1 miss counters stay flat across the knee. That knee is not the data cache at all. The next section is the whole detective story.

## 7. The knee that wasn't: when a "cache conflict" is the DTLB (E6b)

Working hypothesis dump, in the order they got killed:

1. **"L1 conflict anyway"** — dead. `perf stat` on the K=5, 64 KiB case shows `L1-dcache-load-misses` ≈ K=4 levels (~1.3M over 67M steps, i.e. background noise, not 67M). `MEM_LOAD_RETIRED.L1_HIT` says ~87M of ~90M loads hit L1. The lines stay in the data cache.
2. **"L2 / LLC involvement"** — dead. `LLC-loads` ~30K total, nothing.
3. **"Maybe the visit order interacts with replacement policy"** — dead. A variant that permutes the K lines into a *random* cycle instead of sequential prints the identical numbers. It's not order-dependent.
4. **"TLB?"** — checked with the event `DTLB_LOAD_MISSES.STLB_HIT`:

```text
-- stride 65536, K=4:    797,438  DTLB_LOAD_MISSES.STLB_HIT
-- stride 65536, K=5: 67,930,682  DTLB_LOAD_MISSES.STLB_HIT     <-- ≈ every chase step!
-- stride 61440, K=5:    804,963  (control)
-- stride 4096, K=9:     815,625  (control: L1 data knee, no TLB drama)
```

Bingo. Every single link traversal at K=5 **misses the L1 DTLB and has to be served by the second-level shared TLB** (which is big enough to always hit — hence `MISS_CAUSES_A_WALK` stays at ~35K, page walks are not happening).

Why does the 64 KiB stride thrash the TLB at five pages? Translate the intuition of §5 of the note — the lookup-table machinery — to the TLB itself:

```text
L1 dTLB on this CPU: 64 entries for 4 KiB pages, 4-way set associative
   -> 16 sets, indexed by virtual-page-number bits (address bits 12..15)

page stride for a 65536-byte stride: 65536 / 4096 = 16 pages
   -> bits 12..15 of the address are IDENTICAL for all lines
   -> every line's page maps to the SAME DTLB set

4 ways, so the 5th distinct page evicts: knee at K = 5.
```

Sanity checks all line up:

- stride 61440 = 60 KiB = **15 pages** apart → walks through all 16 DTLB sets → **no knee** (measured flat).
- stride 65536+64 = 65600, i.e. still ~16 pages apart per hop → same DTLB set → **knee at 5** (measured).
- stride 4096 = 1 page apart → 16 different sets → no DTLB knee; you see the *data* knee at 9 instead (measured).

The clincher is to remove the game's board: back the buffer with **2 MiB huge pages**, so all the lines land in a *single* translated page and no DTLB entry is ever evicted. Small probe (`e6b_stride_probe.c`, a one-stride version of E6 with optional `madvise(MADV_HUGEPAGE)`, chasing from the interior of the buffer so the VMA's unaligned head being 4K-backed doesn't leak in):

**How to read `e6b_stride_probe.c` (mental model).**

This is the same dependent chase as E6, but it tests only **one** `(stride, K)` pair per run. The new variable is the page size.

```text
buf = mmap(large anonymous region)
if mode == "thp":
    madvise(buf, size, MADV_HUGEPAGE)   # ask kernel for 2 MiB pages

build the same K-line cycle of stride bytes
chase it and report latency
```

If the `stride=65536, K=5` knee is caused by the 4 KiB DTLB (a 16-page stride maps to one DTLB set), then backing the buffer with 2 MiB pages should make the knee disappear: all lines live in the same translated page, so no DTLB set is ever pressured.

```bash
$ taskset -c 2 ./e6b_stride_probe 65536 5 4k
stride 65536 K=5 4k     4.425 ns/access
$ taskset -c 2 ./e6b_stride_probe 65536 5 thp
stride 65536 K=5 thp    1.771 ns/access    <-- knee gone
```

Same code, same addresses, same data-cache behavior — the only thing that changed is the translation granularity, and the "mystery knee" vanishes.

The lesson that generalizes: **the tag/set-index lookup model applies to everything that caches**, not just the data cache hierarchy. The DTLB is also a set-associative cache with a page-number tag, and it has its own conflict misses at its own strides (2^16 bytes here, because `sets × page_size` = `16 × 4 KiB`). Power-of-two strides are hazardous in more places than the note's warning implies. And the second-order lesson: ***measurement first*** — I initially wrote this experiment expecting an L2-associativity knee, wrote the wrong narrative, and the counters corrected it.

## 8. TLB pressure and huge pages (E7)

Stay on the TLB. This time it's about *total* pressure rather than conflicts: pointer-chase one link per 4 KiB page across a 1 GiB region, in random page order. With 4 KiB pages that's 262,144 translations; with THP it's 512.

**How to read this program (mental model).**

`buf` is a 1 GiB anonymous mapping. The program optionally asks for 2 MiB huge pages, then faults every page with `memset` so the memory is actually present.

```text
if mode == "thp":
    madvise(buf, 1 GiB, MADV_HUGEPAGE)
memset(buf, 0, 1 GiB)          # force all pages to be allocated

pages = 1 GiB / page_size
perm = random shuffle of [0 .. pages-1]
for i:
    buf[perm[i] * words_per_page] = perm[i+1]   # one link per page
buf[perm[pages-1] * words_per_page] = perm[0]

p = 0
repeat:
    p = buf[p * words_per_page]                 # jump to a random page each step
```

Because 1 GiB is far larger than cache, every step is a DRAM miss. The only thing that changes between 4K and THP is the number of page translations the CPU must hold: 262,144 small pages versus 512 huge pages.

```c
// e7_tlb.c
#include "common.h"
#include <sys/mman.h>

#define REGION (1UL << 30)          /* 1 GiB */
#define PAGE   4096UL
#define NPAGES (REGION / PAGE)

int main(int argc, char **argv)
{
    int use_thp = argc > 1 && strcmp(argv[1], "thp") == 0;

    uint64_t *buf = mmap(NULL, REGION, PROT_READ | PROT_WRITE,
                         MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (buf == MAP_FAILED) { perror("mmap"); return 1; }
    if (use_thp && madvise(buf, REGION, MADV_HUGEPAGE) != 0) perror("madvise");

    memset(buf, 0, REGION);             /* fault every page in */

    uint64_t pages = NPAGES, wpp = PAGE / sizeof(uint64_t);
    uint32_t *perm = malloc(pages * sizeof(uint32_t));
    if (!perm) { perror("malloc"); return 1; }
    uint64_t seed = 99;
    for (uint32_t i = 0; i < pages; i++) perm[i] = i;
    for (uint32_t i = pages - 1; i > 0; i--) {
        uint32_t j = rng(&seed) % (i + 1);
        uint32_t t = perm[i]; perm[i] = perm[j]; perm[j] = t;
    }
    for (uint32_t i = 0; i < pages - 1; i++)
        buf[(uint64_t)perm[i] * wpp] = perm[i + 1];
    buf[(uint64_t)perm[pages - 1] * wpp] = perm[0];

    if (use_thp) {          /* prove the kernel actually used 2 MiB pages */
        FILE *f = fopen("/proc/self/smaps_rollup", "r");
        char line[256];
        while (f && fgets(line, sizeof line, f))
            if (strstr(line, "AnonHugePages")) printf("%s", line);
        if (f) fclose(f);
        fflush(stdout);
    }

    uint64_t steps = 8UL << 20;
    volatile uint64_t *vbuf = buf;
    uint64_t p = 0;
    double t0 = now();
    for (uint64_t s = 0; s < steps; s++) p = vbuf[p * wpp];
    double dt = now() - t0;
    (void)p;

    printf("%-4s  %8.3f ns/step over %lu pages\n",
           use_thp ? "thp" : "4k", dt * 1e9 / steps, pages);
    free(perm);
    munmap(buf, REGION);
    return 0;
}
```

**Observed:**

```text
4k    136.2 ns/step   dTLB-load-misses  8,929,592   page-faults  262,457   LLC-misses 8,583,632
AnonHugePages: 1046528 kB
thp   125.0 ns/step   dTLB-load-misses      9,857   page-faults    1,336   LLC-misses 8,473,939
```

What to take from this honestly:

- The counters move **900x**: ~8.9M TLB misses ≈ one per chase step with 4K pages, to ~10K with THP. The `AnonHugePages` line proves the kernel really used 2 MiB pages for that second run.
- Page faults show up too: the initial `memset` pays 262,457 faults in 4K mode vs 1,336 when the same 1 GiB is 512 huge pages. Even *populating* memory is a TLB/fault story.
- But wall time only improves ~7-8%, because this chase is already **DRAM-latency-dominated**: every step is a cache miss into a 1 GiB working set (~135 ns of memory latency), and the page-walk cost just rides on top. LLC misses are unchanged (~8.5M = misses per step either way). That's the framing the note doesn't spell out: **TLB hits are additive to, not multiplicative of, the memory wall — huge pages matter most when accesses are *not* already guaranteed misses, or when the working set straddles the TLB-reach boundary** (E6b shows how sharp that cliff can be).

## 9. False sharing, and why the naive demo under-reports (E8)

The note's §12 example, but with a trap I didn't expect: the naive one-counter-per-thread version *hides most of its own effect*.

**How to read this program (mental model).**

The program tests four 64-byte-aligned counter layouts:

```text
shared_one / shared_many:    all threads' counters on the SAME cache line
strided_one / strided_many:  each thread's counters on their OWN cache line
```

There are two parts:

```text
Part 1 (one counter per thread):
    for i = 0 .. iters-1:
        (*c)++                # long dependent chain

Part 2 (eight counters per thread):
    for i = 0 .. sweeps-1:
        for u = 0 .. 7:
            counter[u]++     # independent stores, throughput-bound
```

When two threads share a line, every `++` invalidates the other core's copy. In Part 1 that penalty is hidden behind the 5-cycle dependency chain, so the slowdown is small. In Part 2 the core is store-throughput-limited, so the coherence traffic dominates and the shared-line case is much slower.

```c
// e8_falseshare.c  (abridged comments; full file on the laptop)
#define _GNU_SOURCE
#include "common.h"
#include <pthread.h>
#include <sched.h>

#define MAXT 4
#define U 8

static volatile uint64_t shared_one[MAXT]     __attribute__((aligned(64)));
static volatile uint64_t strided_one[MAXT][8] __attribute__((aligned(64)));
static volatile uint64_t shared_many[MAXT * U]     __attribute__((aligned(64)));
static volatile uint64_t strided_many[MAXT][U * 8] __attribute__((aligned(64)));

static long iters = 150000000, sweeps = 8000000;
static int use_shared;

static void pin(int cpu)
{
    cpu_set_t s; CPU_ZERO(&s); CPU_SET(cpu, &s);
    if (sched_setaffinity(0, sizeof s, &s) != 0) perror("sched_setaffinity");
}

/* part 1: one dependent counter per thread */
static void *w_one(void *arg)
{
    long id = (long)arg;
    pin((int)id);
    volatile uint64_t *c = use_shared ? &shared_one[id] : &strided_one[id][0];
    for (long i = 0; i < iters; i++) (*c)++;
    return NULL;
}

/* part 2: U independent counters per thread */
static void *w_many(void *arg)
{
    long id = (long)arg;
    pin((int)id);
    for (long i = 0; i < sweeps; i++)
        for (int u = 0; u < U; u++) {
            if (use_shared) shared_many[u * MAXT + id]++;  /* every line: all threads */
            else            strided_many[id][u * 8]++;     /* every line: one thread  */
        }
    return NULL;
}

static double run(void *(*fn)(void *), int shared, int nthreads)
{
    pthread_t t[MAXT];
    use_shared = shared;
    double t0 = now();
    for (long i = 0; i < nthreads; i++)
        pthread_create(&t[i], NULL, fn, (void *)i);
    for (long i = 0; i < nthreads; i++)
        pthread_join(t[i], NULL);
    return now() - t0;
}

int main(int argc, char **argv)
{
    iters  = argc > 1 ? atol(argv[1]) : iters;
    sweeps = argc > 2 ? atol(argv[2]) : sweeps;

    printf("part 1: 1 counter/thread (dependent chain)\n");
    printf("%8s %12s %12s %14s\n", "threads", "shared", "own-line", "slowdown");
    printf("%8d %12.3f %12.3f %13.2fx\n", 1, run(w_one, 1, 1), run(w_one, 0, 1), 1.0);
    for (int n = 2; n <= MAXT; n++) {
        double a = run(w_one, 1, n), b = run(w_one, 0, n);
        printf("%8d %12.3f %12.3f %13.2fx\n", n, a, b, a / b);
    }

    printf("\npart 2: %d independent counters/thread (throughput-bound)\n", U);
    printf("%8s %12s %12s %14s\n", "threads", "shared", "own-line", "slowdown");
    printf("%8d %12.3f %12.3f %13.2fx\n", 1, run(w_many, 1, 1), run(w_many, 0, 1), 1.0);
    for (int n = 2; n <= MAXT; n++) {
        double a = run(w_many, 1, n), b = run(w_many, 0, n);
        printf("%8d %12.3f %12.3f %13.2fx\n", n, a, b, a / b);
    }
    return 0;
}
```

Threads are pinned to cpus 0–3, which are one logical CPU per physical core on this box (no HT co-tenancy noise).

**Observed:**

```text
part 1: 1 counter/thread (dependent chain)
 threads       shared     own-line       slowdown
       1        0.243        0.245          1.00x
       2        0.345        0.243          1.42x
       3        0.349        0.243          1.44x
       4        0.348        0.243          1.43x

part 2: 8 independent counters/thread (throughput-bound)
 threads       shared     own-line       slowdown
       1        0.065        0.045          1.00x
       2        0.617        0.096          6.41x
       3        0.837        0.138          6.06x
       4        1.074        0.173          6.22x
```

Two things to internalize:

1. **The effect is real and huge**: with 8 independent counters per thread (so the store port runs flat-out), the shared-line case is ~6x slower, and it degrades as more cores fight over the line. Same 64-byte line, separate variables, zero logical sharing.
2. **The naive single-counter demo shows only 1.4x** — and this is *itself* the Lab 1 lesson. A dependent `(*c)++` chain is store → forward → next add, ~5 cycles per hop; while a core sits inside its own dependency chain, coherence transfers flow in the background and get *hidden* behind chain latency. Memory costs hide anywhere there's slack — ILP, OOO window, store-to-load forwarding. To expose a memory-system cost you must make the core *throughput-limited*, the same dependency-chain insight as `e1_depchain` in Lab 1, now applied to coherence.

(The fix remains the note's: pad to 64 B, as `strided_*` does. If you ever need to *find* it: `perf c2c record ./e8_falseshare` + `perf c2c report` on supported kernels.)

## 10. Naive vs blocked matmul, and the N=512/513 cliff (E9)

The note's standalone blocking example (§16) plus, standing in for its question #6, the classic power-of-two cliff:

**How to read this program (mental model).**

`A`, `B`, `C` are flat `float[N*N]` matrices. The naive kernel computes `C[i][j]` by walking a fixed column of `B`:

```text
for i:
    for j:
        s = 0
        for k:
            s += A[i][k] * B[k][j]     # B is read column-wise
        C[i][j] += s
```

The inner loop reads `B[k][j]` with stride `N*4` bytes. At `N=512` that stride is 2048 bytes, which maps the column walk onto only two L1 sets; at `N=513` the stride is 2052 bytes and the walk spreads across all 64 sets.

The blocked kernel tiles the loops:

```text
for ii in steps of BS:
    for kk in steps of BS:
        for jj in steps of BS:
            for i in tile:
                for k in tile:
                    a = A[i][k]
                    for j in tile:
                        C[i][j] += a * B[k][j]
```

A small tile of `B` stays in cache while its rows are reused, which dramatically cuts misses.

```c
// e9_matmul.c — kernels only; driver allocates A, B, C, times each once
static void naive(void)
{
    for (long i = 0; i < N; i++)
        for (long j = 0; j < N; j++) {
            float s = 0.0f;
            for (long k = 0; k < N; k++)
                s += A[i * N + k] * B[k * N + j];   /* B read column-wise: stride N*4 B */
            C[i * N + j] += s;
        }
}

static void blocked(int bs)
{
    for (long ii = 0; ii < N; ii += bs)
        for (long kk = 0; kk < N; kk += bs)
            for (long jj = 0; jj < N; jj += bs)
                for (long i = ii; i < ii + bs && i < N; i++)
                    for (long k = kk; k < kk + bs && k < N; k++) {
                        float a = A[i * N + k];
                        for (long j = jj; j < jj + bs && j < N; j++)
                            C[i * N + j] += a * B[k * N + j];
                    }
}
```

**Observed** (with `perf stat` in a warm run; note laptop thermal variance between cold and warm invocations: naive came in at 3.38 s on a cold run):

```text
N=1024  naive   1.82 s (1.18 GFLOP/s)   blocked  0.63 s (3.41 GFLOP/s)   →  2.9x (5.3x cold)
-- LLC-load-misses:  naive 1,525,431    blocked 16,763    (~90x fewer)
N=512:  naive 0.23 s (1.15 GFLOP/s)    L1-dcache-load-misses 135,131,313
N=512 blocked 0.07 s (3.67 GFLOP/s)    L1-dcache-load-misses  11,505,710
```

And the N=512 vs 513 pathology, naive kernel:

```text
N=512   naive   0.23 s ( 1.15 GFLOP/s)
N=513   naive   0.15 s ( 1.76 GFLOP/s)     <-- MORE work, LESS time
```

**Why N=513 wins despite more flops.** The naive inner loop walks `B[k * N + j]` — a fixed column of B, one element per row. At N=512 the step is `512 * 4 B = 2048 B`. Cache set index bits are 6–11, so 2048-byte steps toggle exactly one set-index bit: the whole column walk (512 lines, 2 MiB) smashes into **two L1 sets**, which have 16 ways total — thrash. At N=513 the step is 2052 B; `2052 mod 4096` distributes successive accesses around all 64 sets and the L1 can actually hold the working window. This is §9's "power-of-two strides can be pathological" in one raw number and a direct answer (one flavor of it) to the note's question 6: for column-style access to B, *bigger-N can be faster when N−1 breaks the stride's alignment to the cache's set geometry.* (At N=768 the naive loop also hits capacity limits, 0.67 s for 4x the flops of 512^3 ≈ 1.35 GFLOP/s — conflict then capacity.)

## 11. Software prefetch done right (E10)

The note (§10) says SW prefetch helps when the hardware prefetcher can't see the pattern. The hardest pattern of all is E1's random pointer chase — and it *can't* be prefetched, because the next address is what you're loading. The case SW prefetch *can* help: a gather whose future addresses are known in advance (e.g. hash probes, index-array traversal). That's this experiment: 4 M random-index lookups into a 256 MiB table, with `_mm_prefetch` issued `dist` iterations ahead.

**How to read this program (mental model).**

`node` is a 256 MiB table of 64-byte nodes. `idx` is a shuffled list of which node to read next. The plain loop is a gather:

```text
for k:
    sum += node[idx[k]]
```

The prefetched loop issues a software prefetch for the node that will be used `dist` iterations later:

```text
for k:
    if k + dist < NODES:
        prefetch node[idx[k + dist]]   # start the miss early
    sum += node[idx[k]]
```

Because future addresses are known from `idx[]`, the CPU can launch misses ahead of time. Without prefetch, only about four misses fit in the out-of-order window, so the loop is latency-bound; with prefetch, more misses overlap and throughput rises.

```c
// e10_sw_prefetch.c
#include <immintrin.h>
#include "common.h"

#define NODES (4UL << 20)          /* 4 M nodes x 64 B = 256 MiB */

static uint64_t  node[NODES * 8];  /* node i at node[i*8] */
static uint32_t  idx[NODES];

static void shuffle(void)
{
    uint64_t seed = 123;
    for (uint32_t i = 0; i < NODES; i++) idx[i] = i;
    for (uint32_t i = NODES - 1; i > 0; i--) {
        uint32_t j = rng(&seed) % (i + 1);
        uint32_t t = idx[i]; idx[i] = idx[j]; idx[j] = t;
    }
}

__attribute__((noinline))
static uint64_t gather_plain(void)
{
    uint64_t s = 0;
    for (uint32_t k = 0; k < NODES; k++) s += node[(size_t)idx[k] * 8];
    return s;
}

__attribute__((noinline))
static uint64_t gather_prefetch(int dist)
{
    uint64_t s = 0;
    for (uint32_t k = 0; k < NODES; k++) {
        if (k + dist < NODES)
            _mm_prefetch((const void *)&node[(size_t)idx[k + dist] * 8], _MM_HINT_T0);
        s += node[(size_t)idx[k] * 8];
    }
    return s;
}

int main(void)
{
    memset(node, 1, sizeof node);
    shuffle();

    for (int w = 0; w < 2; w++) gather_plain();   /* warm page tables/TLB */

    double t = now(); uint64_t s0 = gather_plain();  double t0 = now() - t;
    printf("plain gather          %8.3f ns/node\n", t0 * 1e9 / NODES);

    static const int dists[] = {4, 8, 16, 32};
    for (size_t i = 0; i < sizeof(dists)/sizeof(dists[0]); i++) {
        int d = dists[i];
        t = now(); uint64_t s1 = gather_prefetch(d); double td = now() - t;
        if (s1 != s0) printf("WARNING: sums differ\n");
        printf("prefetch distance %-3d %8.3f ns/node  (%.2fx)\n", d, td * 1e9 / NODES, t0 / td);
    }
    return 0;
}
```

**Observed:**

```text
plain gather            29.505 ns/node
prefetch distance 4     19.362 ns/node  (1.52x)
prefetch distance 8     14.791 ns/node  (1.99x)
prefetch distance 16    12.937 ns/node  (2.28x)
prefetch distance 32    10.170 ns/node  (2.90x)
```

The view that makes this click: memory parallelism = per-miss latency ÷ misses in flight. Without prefetch, ~30 ns/node is roughly `110 ns latency / ~4 misses in flight` — E1 showed raw latency is ~110 ns out here. Each OOO window only fits a handful of outstanding L1 misses, so the gather is **latency-bound, not bandwidth-bound**. Explicit prefetches move misses further ahead of use; distance 32 ≈ 3x. Notably, on this core there is no distance-32 plateaus-above cliff: the loop's 256 MiB footprint beats up the TLB either way, and bigger distances mostly help (tune on your machine; the note's warning that SW prefetch is fragile stands — if the table fit in L3, every prefetch is pure overhead).

## 12. Bonus: 4K aliasing — loud in counters, quiet on the stopwatch (E11)

A cache-adjacent curiosity not in the note: when a load's **low 12 address bits** match a recent store's but the full addresses differ, the memory disambiguator assumes the load might be reading the store's data and conservatively stalls/replays it. No data was ever written there; it's a *false* dependence. The classic example is a memcpy-style copy whose source is exactly 4096 bytes ahead of its destination.

**How to read this program (mental model).**

`buf` is a 1 Mi int array. The program creates two pointers into it and copies:

```text
src = buf
dst = buf + delta        # delta = 1024 or 1040 ints

for i:
    dst[i] = src[i]
```

When `delta = 1024` ints, the distance between `src` and `dst` is exactly 4096 bytes. For every `i`, `src[i]` and `dst[i]` have the **same low 12 address bits**. The CPU's memory disambiguator conservatively assumes the load might read from the recent store and stalls/replays it. The counter `LD_BLOCKS_PARTIAL.ADDRESS_ALIAS` records these events; wall time may not move if the loop has enough other work to hide the replays.

```c
// e11_4k_alias.c
#include "common.h"

#define N (1UL << 20)          /* 1 Mi ints */
static int buf[N + 2048];

int main(int argc, char **argv)
{
    long reps = argc > 1 ? atol(argv[1]) : 400;
    for (long i = 0; i < N + 2048; i++) buf[i] = (int)i;

    static const int deltas[] = {1024, 1040};  /* 4096 B and 4160 B */
    for (size_t d = 0; d < sizeof(deltas)/sizeof(deltas[0]); d++) {
        volatile int *src = buf;
        volatile int *dst = buf + deltas[d];
        long n = N - deltas[d];

        double t0 = now();
        for (long r = 0; r < reps; r++)
            for (long i = 0; i < n; i++)
                dst[i] = src[i];               /* load src, store dst */
        double dt = now() - t0;

        printf("src - dst = %5zu bytes (%s)  %8.3f ns/elem\n",
               deltas[d] * 4L,
               deltas[d] * 4 % 4096 == 0 ? "4K-alias  " : "no alias  ",
               dt * 1e9 / (reps * n));
    }
    printf("guard: %d\n", buf[12345]);
    return 0;
}
```

**Observed:**

```text
src - dst =  4096 bytes (4K-alias  )     0.380 ns/elem
src - dst =  4160 bytes (no alias  )     0.381 ns/elem
```

No timing difference on this copy — but look what the counters say:

```text
perf stat -e LD_BLOCKS_PARTIAL.ADDRESS_ALIAS ./e11_4k_alias
       413,834,843      LD_BLOCKS_PARTIAL.ADDRESS_ALIAS      (~1 event per load!)
```

Every load in the aliased variant *did* trip the hazard (400M loads, 414M events), and the machine's memory-ordering machinery simply absorbed it — `machine_clears.memory_ordering` was ~100, and the store-throughput loop hides the ~few-cycle replays behind other work. This is the memory-system version of E8's discovery, and a good closer for the lab: **on modern out-of-order cores, individual memory hazards are real and countable long before they are slow.** (To make it more visible in timing you have to force the alias onto a latency-critical path — a first variant of this file that made each load dependent on the previous store showed ~0.71 vs 0.68 ns/iter. Even that is only ~4%.)

## 13. Cheat sheet

| Want to see | Run | Look for |
|---|---|---|
| Latency of each level | `./e1_staircase` | plateaus at 2/4/13/110+ ns |
| The 64 B line | `./e2_linesize` | knee at stride 64 |
| Spatial locality + prefetcher | `./e3_seqrand seq` vs `rand` | 8x time gap, `LLC-load-misses` |
| Access order kills | `./e4_rowcol 4096` | col: 1 LLC miss + 1 dTLB miss per element |
| Layout halves traffic | `./e5_aos_soa` | LLC misses 6:1, time 1.33x (not 2x) |
| L1 is 8-way | `./e6_assoc 4096` | knee at K=9; control `./e6_assoc 4160` flat |
| **DTLB is 4-way × 16 sets** | `./e6_assoc 65536` + E6b | knee at K=5, `DTLB_LOAD_MISSES.STLB_HIT` ≈ steps; gone under THP |
| TLB capacity vs huge pages | `./e7_tlb` vs `./e7_tlb thp` | dTLB misses 900x down; time −8% (DRAM-bound) |
| False sharing | `./e8_falseshare` | 6x (throughput); only 1.4x dependent — hazards hide in chains |
| Blocking beats conflicts | `./e9_matmul 1024 64`; N=512 vs 513 | 90x fewer LLC misses; N+1 faster than N |
| When SW prefetch works | `./e10_sw_prefetch` | 2.9x at distance 32, known future addresses only |
| 4K aliasing exists (predictor eats it) | `./e11_4k_alias` | `LD_BLOCKS_PARTIAL.ADDRESS_ALIAS` ≈ every load |

## 14. Try next

1. **Find the L2 knee for real.** E6 punts it (64 KiB thrashes DTLB long before L2's 4 ways show up — and E6b tells you why). Can you construct a stride pattern that conflicts in L2 (4-way, 1024 sets, index over bits 6–15) but *not* in the DTLB? Hint: the L2 is physically indexed and page bits 12+ are, for big anonymous pages, effectively physical.
2. **Prefetched E1.** Re-run `e1_staircase` with one extra prefetch of the link target one iteration ahead. Predict what will and won't change, then check.
3. **False sharing via scaling.** Extend E8: perf counter `c2c` or the coherence-related events (`MEM_TRANS_RETIRED...`) and re-plot part 2. Where does the curve bend as you approach 8 threads (hyperthreads included)?
4. **Sequential THP.** E7's walk was random and DRAM-bound. Re-do it with *sequential* 64-byte-step traversal over the same 1 GiB: where does wall time land for 4K vs THP, and which counter moved the most?

The theory note's §18 question list overlaps this lab's answers on several points (Q2 ↔ E6's 4 KiB stride knee, Q4 ↔ E8, Q6 ↔ E9). If you can explain each measured table above without looking at the closing summary line of each section, you've got it.
