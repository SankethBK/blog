---
title:  "Lab 1: CPU Internals"
date:   2026-10-06
categories: ["performance-engineering"]
tags: ["performance", "cpu", "microarchitecture", "perf", "pipelines"]

---

# Lab 1: CPU Internals

This is a hands-on report for the lab in `/home/sanketh/cpu-lab` on your Linux x86 laptop. It ties each experiment back to the ideas in `content/posts/performance-engineering/2026-10-04-cpu-microarchitecture.markdown`.

> **Important note about this laptop:** the CPU is an **Intel Core i5-8250U** (15 W mobile part, base 1.6 GHz, max 3.4 GHz). Under sustained load it thermally throttles, so **absolute nanoseconds vary between runs**. The conclusions come from **ratios** and **TMA buckets**, not from chasing the exact ns.


## 0. Quick start 

```bash
ssh sanketh@192.168.1.14
cd /home/sanketh/cpu-lab
make
```

```sh
sudo sysctl kernel.perf_event_paranoid=-1
sudo cpupower frequency-set -g performance
```

Machine summary (from `lscpu`):

| Item | Value |
|------|-------|
| CPU | Intel Core i5-8250U (Kaby Lake R) |
| Cores / threads | 4 / 8 |
| L1d per core | 32 KiB (128 KiB total) |
| L2 per core | 256 KiB (1 MiB total) |
| L3 shared | 6 MiB |
| GCC | 9.4.0 |
| Kernel | 5.15.0 |

Setting `kernel.perf_event_paranoid=-1` is necessary for CPU labs because it grants your profiling tools unprivileged access to performance counters, allowing you to capture critical hardware data like cache misses, branch mispredictions, and TMA metrics without running every profiling command as sudo. 

By default, Linux restricts access to hardware performance counters for security reasons. Here is how the strictness levels break down:

### 🛡️ The Paranoid Levels Explained

| Value | Restrictions Placed on Unprivileged Users |
|---|---|
| 2 (Default) | Maximum restrictions. You can only sample CPU clock time. You cannot capture hardware events (like cache misses) or profile kernel space. |
| 1 | Medium restrictions. You can capture hardware events, but only for user-space programs. You cannot profile the Linux kernel itself. |
| 0 | Low restrictions. You can sample both user-space and kernel-space execution, but you still cannot access raw tracepoints. |
| -1 | No restrictions. Completely opens up the performance counters. You can collect any hardware metric, tracepoint, and raw sample across both user and kernel space. |

### 🛠️ Why Your CPU Labs Specifically Need -1

1. Unlocking Advanced Hardware Events: Accurate TMA (Top-Down Microarchitecture Analysis) requires reading specialized core architectural counters. The default setting completely blocks access to these registers.
2. Eliminating sudo Profiling Overhead: If you don't change this setting, you have to run commands like sudo perf stat or sudo perf record. Running profilers as root is dangerous for system stability and can inject unwanted OS-level noise into your benchmark results.
3. Capturing Kernel Interactions: Many bottlenecks occur because a program is waiting on the operating system (e.g., page faults, memory allocation, or context switches). Setting the value to -1 lets your profiler see across the boundary between your code and the Linux kernel.

### What taskset Does
`taskset` sets a process's CPU affinity. It forces the Linux operating system to run your program only on the specific CPU core(s) you choose.

In your command (`taskset -c 2`), you pinned your CPU lab benchmark strictly to Core 2.

#### How It Manages to Pin the Core

`taskset` does not directly control the hardware. Instead, it relies on a Linux system call named `sched_setaffinity`.

1. **The Mask:** Under the hood, Linux tracks CPU availability using a bitmask (a series of 0s and 1s). For an 8-thread CPU, a mask of `00000100` means only Core 2 is allowed.
2. **The Enforcement:** When taskset calls `sched_setaffinity` with that mask, the Linux kernel scheduler registers this rule for your process.
3. **No Migration:** Every time the OS scheduler schedules your program to run, it strictly selects Core 2. It will never "migrate" (move) your process to Core 0, 1, 3, or any other core, even if Core 2 becomes heavily loaded.

#### Is It Used to Reduce Scheduler Overhead?

While reducing scheduler overhead is a small bonus, that is not the primary reason it is used in CPU microarchitecture labs. In your specific lab, taskset is vital for three main reasons:

##### 1. 🛑 Eliminating "Cache Thrashing" (The Main Reason)

If you do not pin the process, the Linux scheduler might move your program from Core 2 to Core 3 halfway through execution. When a process jumps to a new core, it leaves behind all its cached data in the old core's L1 and L2 caches. It must then fetch everything from the slow L3 cache or DRAM again. This completely ruins your profiling data and TMA memory metrics.

##### 2. 📊 Getting Clean TMA / PMU Metrics

Hardware Performance Monitors (PMUs) count events (like instructions, clock cycles, and cache misses) per core. If your benchmark hops across different cores while perf or toplev is trying to read Core 2's counters, your data will become fragmented, inaccurate, or heavily multiplexed.

##### 3. 🌡️ Managing Thermals on your i5-8250U

Because you have a 15W mobile processor that throttles easily, pinning your code to one single core ensures that the rest of the cores can drop into low-power idle states. This keeps the overall chip temperature cooler for longer, giving you a slightly more stable window to measure your dependency chains before the clock speed drops.

### What does `sudo cpupower frequency-set -g performance` do? 

Yes, running this command is highly recommended before starting your CPU microarchitecture labs, though it serves a slightly different purpose on your 15W i5-8250U mobile processor compared to a desktop chip.
The command `sudo cpupower frequency-set -g performance` switches your Linux CPU scaling governor to the performance profile.

Here is exactly why it is necessary for your lab environment:

#### 1. It Eliminates DVFS Ramp-Up Latency

By default, Ubuntu uses a power-saving governor (like `powersave` or `schedutil`). When your CPU is idling, it drops to its lowest frequency (e.g., 800 MHz). When you kick off your ./run.sh 1 benchmark, it takes the operating system several milliseconds to realize a heavy workload has started and ramp the clock up to full speed.

* Because micro-benchmarks often execute in fractions of a second, a significant portion of your run will finish before the CPU even reaches its full clock speed.
* The performance governor forces the CPU to sit at its maximum base frequency immediately, ensuring the entire benchmark runs at full throttle.

#### 2. It Stabilizes the Baseline Clock

For Top-Down Microarchitecture Analysis (TMA), you want the clock frequency to remain as flat and predictable as possible during the run. The performance governor prevents the OS from constantly micro-managing and fluctuating the clock speed between minor execution stalls.


#### ⚠️ The Mobile CPU Catch: "Performance" vs. Thermal Throttling
While this command is crucial for getting clean data on desktops, your Intel Core i5-8250U has strict physical limits:

 1. It won't stop thermal throttling: The performance governor tells the operating system scheduler, "Give this chip maximum power and frequency." However, the hardware embedded power controller (firmware) inside your laptop always has the final say. Once the chip hits its 15W limit or thermal ceiling, the hardware will override the governor and pull the frequency down anyway.
 2. It actually speeds up thermal saturation: Because the performance governor keeps the CPU pinned at high frequencies even when you are idling between lab runs, your laptop will heat up faster.

#### 💡 Best Practice for Your Lab

Definitely run the command to ensure your benchmark starts at peak speed and doesn't suffer from ramp-up lag. However, to keep your results as consistent as possible on that 15W mobile chip, give the laptop 5 to 10 seconds to cool down between benchmark runs.
Would you like to check what your current active frequencies and governor states look like right now using cpupower frequency-info?


## 1. Dependency chains / instruction-level parallelism (E1)

**Concept:** A long chain of dependent operations limits performance to one result per `latency` cycles, no matter how wide the CPU is. Splitting the work into independent chains lets the core overlap them.

Let's consider this program

```c
// Exp 1 (readable version): ILP via independent floating-point accumulators.
// Compile WITHOUT -ffast-math so the compiler cannot reorder the adds.
#include "common.h"

#define N 4096  /* 16 KiB: fits in L1, so we measure the core, not memory */

static float a[N];

/* One accumulator: every add depends on the previous one. */
__attribute__((noinline))
float sum_1(long reps)
{
    float s0 = 0.0f;

    for (long r = 0; r < reps; r++) {
        for (int i = 0; i < N; i++) {
            s0 += a[i];
        }
    }

    return s0;
}

/* Two independent accumulators. */
__attribute__((noinline))
float sum_2(long reps)
{
    float s0 = 0.0f;
    float s1 = 0.0f;

    for (long r = 0; r < reps; r++) {
        for (int i = 0; i < N; i += 2) {
            s0 += a[i];
            s1 += a[i + 1];
        }
    }

    return s0 + s1;
}

/* Four independent accumulators. */
__attribute__((noinline))
float sum_4(long reps)
{
    float s0 = 0.0f;
    float s1 = 0.0f;
    float s2 = 0.0f;
    float s3 = 0.0f;

    for (long r = 0; r < reps; r++) {
        for (int i = 0; i < N; i += 4) {
            s0 += a[i];
            s1 += a[i + 1];
            s2 += a[i + 2];
            s3 += a[i + 3];
        }
    }

    return s0 + s1 + s2 + s3;
}

/* Eight independent accumulators. */
__attribute__((noinline))
float sum_8(long reps)
{
    float s0 = 0.0f, s1 = 0.0f, s2 = 0.0f, s3 = 0.0f;
    float s4 = 0.0f, s5 = 0.0f, s6 = 0.0f, s7 = 0.0f;

    for (long r = 0; r < reps; r++) {
        for (int i = 0; i < N; i += 8) {
            s0 += a[i];
            s1 += a[i + 1];
            s2 += a[i + 2];
            s3 += a[i + 3];
            s4 += a[i + 4];
            s5 += a[i + 5];
            s6 += a[i + 6];
            s7 += a[i + 7];
        }
    }

    return s0 + s1 + s2 + s3 + s4 + s5 + s6 + s7;
}

/* Sixteen independent accumulators. */
__attribute__((noinline))
float sum_16(long reps)
{
    float s0  = 0.0f, s1  = 0.0f, s2  = 0.0f, s3  = 0.0f;
    float s4  = 0.0f, s5  = 0.0f, s6  = 0.0f, s7  = 0.0f;
    float s8  = 0.0f, s9  = 0.0f, s10 = 0.0f, s11 = 0.0f;
    float s12 = 0.0f, s13 = 0.0f, s14 = 0.0f, s15 = 0.0f;

    for (long r = 0; r < reps; r++) {
        for (int i = 0; i < N; i += 16) {
            s0  += a[i];
            s1  += a[i + 1];
            s2  += a[i + 2];
            s3  += a[i + 3];
            s4  += a[i + 4];
            s5  += a[i + 5];
            s6  += a[i + 6];
            s7  += a[i + 7];
            s8  += a[i + 8];
            s9  += a[i + 9];
            s10 += a[i + 10];
            s11 += a[i + 11];
            s12 += a[i + 12];
            s13 += a[i + 13];
            s14 += a[i + 14];
            s15 += a[i + 15];
        }
    }

    return s0 + s1 + s2 + s3 + s4 + s5 + s6 + s7 +
           s8 + s9 + s10 + s11 + s12 + s13 + s14 + s15;
}

int main(int argc, char **argv)
{
    long reps = (argc > 1) ? atol(argv[1]) : 100000;

    for (int i = 0; i < N; i++) {
        a[i] = 1.0f;
    }

    struct {
        const char *name;
        float (*fn)(long);
        int k;
    } tests[] = {
        {"sum_1",  sum_1,  1},
        {"sum_2",  sum_2,  2},
        {"sum_4",  sum_4,  4},
        {"sum_8",  sum_8,  8},
        {"sum_16", sum_16, 16},
    };
    int ntests = sizeof(tests) / sizeof(tests[0]);

    for (int t = 0; t < ntests; t++) {
        double t0 = now();
        volatile float r = tests[t].fn(reps);
        double dt = now() - t0;
        (void)r;

        double ns_per_elem = dt * 1e9 / (reps * (double)N);
        double gelem_per_s = reps * (double)N / dt / 1e9;

        printf("accumulators=%-2d  %.3f ns/element  (%.2f Gelem/s)\n",
               tests[t].k, ns_per_elem, gelem_per_s);
    }

    return 0;
}
```

The idea of this program is to demnstrate the speedup achieved by parallel operations specifically **Instruction Level Parallelism.**

Imagine in x86, an addition loop for single accumulator looks roughly like this

```asm
; xmm0 = s0
loop:
    vaddss xmm0, xmm0, [a + i*4]  ; s0 = s0 + a[i]
    add    i, 1
    cmp    i, N
    jne    loop
```

Two new things here

**vaddss**

`vaddss` is an x86 instruction that adds **one pair of 32-bit floating-point numbers**.

The name breaks down roughly like this:

- `v` — the newer AVX-style instruction encoding
- `add` — add
- `ss` — scalar single-precision: one `float`, rather than several values at once

So:

```asm
vaddss xmm0, xmm0, [address]
```

means “add the `float` at `[address]` to the `float` in `xmm0`, and store the result in `xmm0`.” In this loop, `xmm0` holds the running sum.

**xmm0**

Yes. `xmm0` is a **register**—a small, very fast storage location inside the CPU. In this example it holds the running total `s0`.

```asm
vaddss xmm0, xmm0, [a + i*4]
```

Read it roughly as:

> Add the single-precision float at memory address `a + i*4` to the value in `xmm0`, then put the result back in `xmm0`.

The pieces:

- `vaddss` means a scalar (one value) single-precision floating-point addition.
- The first `xmm0` is the destination register.
- The second `xmm0` is the current accumulator value.
- `[a + i*4]` means “read a value from memory at this address.” Since each `float` is 4 bytes, `i*4` selects `a[i]`.

So it represents:

```c
s0 += a[i];
```

The square brackets mean “the value stored at this memory address.” Unlike `s0`, which the compiler may keep in `xmm0` throughout the loop, `a[i]` is read from memory (likely the CPU cache in this lab).

Now coming to single accumulator version, let's see why CPU executes it slower compared to others

The dependency is `xmm0 → vaddss → xmm0 → next vaddss`. Even if the CPU has room to do other work, this chain limits how quickly it can produce the next sum.

**Four accumulators:** each addition updates a different register, so the additions are independent. The loop handles four elements per iteration:

```asm
; xmm0 = s0, xmm1 = s1, xmm2 = s2, xmm3 = s3
loop:
    vaddss xmm0, xmm0, [a + i*4]       ; s0 += a[i]
    vaddss xmm1, xmm1, [a + (i+1)*4]   ; s1 += a[i+1]
    vaddss xmm2, xmm2, [a + (i+2)*4]   ; s2 += a[i+2]
    vaddss xmm3, xmm3, [a + (i+3)*4]   ; s3 += a[i+3]
    add    i, 4
    cmp    i, N
    jne    loop
```

The CPU can overlap work on `xmm0` with work on `xmm1`, `xmm2`, and `xmm3`. Each register still has its own dependency chain, but the chains don’t depend on one another.

That’s the key difference in this lab: more independent chains give the CPU more opportunities to keep its execution units busy. Loop unrolling also cuts down on loop-control instructions, but that’s secondary here.

> So the way i am understanding it
> 
> A cpu will have multiple execution ports: let's say 4 ports for ALU
> one problem with only 1 accumator right away is only 1 addition can be done at a time (ok might be 2 if we consider add i, 1) but that's capped. others are sitting idle and it has to add no-ops till the result of adder is written back to register because until then what will it do? 
> 
> But with 4 accumators, 4 adders can be busy at once, of course each next corresponding addition requires writeback, but assuming its like addition 1 starts first, next cycle addition 2 starts, ... addition 1 will complete first and starts writeback while others are still adding, so we increase the throughput
> 
> So there must be a sweet spot somewhere because if we overshoot number of adders than additions have to wait (but i am guessing its not that bad because adders are still running at full capacity)

Next we compile the code with 

```sh
gcc -O2 -g -fno-omit-frame-pointer -march=native e1_depchain_1.c -o e1_depchain
```

We'll see why each of the flags are used
 
- `-O2`: Enables a moderate-to-high level of code optimization. The compiler reorganizes and optimizes your code to make it run significantly faster without increasing the binary size excessively or breaking standards compliance.
- `-g`: Generates debugging information. It includes extra metadata (like variable names and line numbers) inside the binary so tools like gdb or profilers can map the executable machine code back to your original source code lines.
- `-fno-omit-frame-pointer`: Forces the compiler to keep the frame pointer register (like RBP on x86_64 architectures). By default, -O2 turns this off to free up a register for extra speed. Keeping it ensures that diagnostic tools and profilers (like Linux perf or bpftrace) can instantly and reliably unwind the call stack to see exactly which functions are calling each other.
- `-march=native`: Tells the compiler to look at the local CPU architecture of the machine you are building on. It enables every instruction set extension your hardware supports (like AVX2, AVX-512, etc.). While this yields maximum hardware performance, the resulting binary will likely crash if you try to run it on an older or different processor.

It seems like if we enable compiler optimizations with `-O2` won't compiler optimize our loops by unrolling it? We can compile it with `-O0` flag and inspect the assembly.

At `-O0` the compiler is literal: every accumulator lives in a stack slot. Each `+=` becomes a **load-from-stack → add → store-to-stack** round-trip. You are no longer measuring the CPU’s add latency/throughput; you are mostly measuring stack traffic.

**`-O0`, `sum_1` — accumulator lives on the stack:**

```asm
vmovss xmm0, DWORD PTR [rbp-0x10]   ; load s0 from stack
vaddss xmm0, xmm0, DWORD PTR [a+...]; add a[i]
vmovss DWORD PTR [rbp-0x10], xmm0   ; store s0 back to stack
```

**`-O0`, `sum_8` — eight accumulators, all on the stack:**

```asm
vmovss xmm0, DWORD PTR [a+...]
vmovss xmm1, DWORD PTR [rbp-0x2c]
vaddss xmm0, xmm1, xmm0
vmovss DWORD PTR [rbp-0x2c], xmm0
; ... repeated for s1..s7, each reload/store from its own stack slot
```

No register reuse between iterations. The CPU has to do a memory round-trip for every accumulator, every time.

At `-O2` the compiler keeps the accumulators in `xmm` registers. Now the loop runs entirely inside the execution units, so the dependency-chain effect is visible.


**`-O2`, `sum_1` — one accumulator in `xmm0`:**

```asm
vxorps xmm0, xmm0, xmm0
loop:
  vaddss xmm0, xmm0, DWORD PTR [rax]
  add rax, 0x4
  cmp rax, rdx
  jne loop
ret
```

**`-O2`, `sum_8` — eight accumulators in `xmm0`..`xmm7`, kept live across the loop:**

```asm
vxorps xmm1, xmm1, xmm1
vmovaps xmm2, xmm1
vmovaps xmm3, xmm1
...
vmovaps xmm0, xmm1          ; s0..s7 now in xmm0..xmm7
loop:
  vaddss xmm0, xmm0, DWORD PTR [rax]
  vaddss xmm7, xmm7, DWORD PTR [rax+0x4]
  vaddss xmm6, xmm6, DWORD PTR [rax+0x8]
  ...
  vaddss xmm1, xmm1, DWORD PTR [rax+0x1c]
  add rax, 0x20
  cmp rdx, rax
  jne loop
; horizontal reduce at the end
```

That is exactly why `-O2` scales and `-O0` barely does.

**`-O2`, `sum_16` — uses all sixteen `xmm` registers (`xmm0`..`xmm15`):**

No spills, so the 16-accumulator case still runs well. It stops improving because the core has only two FP add ports; after about 8 independent adds/cycle there is nothing left to win.

**But important thing is: reading for `O0` still won't be as bad as it looks, because remember the array is designed to fit entirely in L1 cache!**

This is how we run the program, it will run each loop 20000 times. 

```sh
$ ./e1_depchain 20000
accumulators=1   1.180 ns/element  (0.85 Gelem/s)
accumulators=2   0.590 ns/element  (1.69 Gelem/s)
accumulators=4   0.295 ns/element  (3.39 Gelem/s)
accumulators=8   0.173 ns/element  (5.78 Gelem/s)
accumulators=16  0.169 ns/element  (5.91 Gelem/s)
```

```sh
$ taskset -c 2  ./e1_depchain 20000
accumulators=1   1.180 ns/element  (0.85 Gelem/s)
accumulators=2   0.590 ns/element  (1.70 Gelem/s)
accumulators=4   0.295 ns/element  (3.39 Gelem/s)
accumulators=8   0.173 ns/element  (5.79 Gelem/s)
accumulators=16  0.169 ns/element  (5.90 Gelem/s)
```

(Gelem = Giga elements)

We can see the results are close with or without pinning it to a CPU core, it means the program is not being moved to different CPU's midway by scheduler anyways.

### Running `perf stat`

```sh
sanketh@ubuntu20:~/cpu-lab$ taskset -c 2 perf stat  ./e1_depchain 20000
accumulators=1   1.180 ns/element  (0.85 Gelem/s)
accumulators=2   0.590 ns/element  (1.69 Gelem/s)
accumulators=4   0.887 ns/element  (1.13 Gelem/s)
accumulators=8   0.503 ns/element  (1.99 Gelem/s)
accumulators=16  0.474 ns/element  (2.11 Gelem/s)

 Performance counter stats for './e1_depchain 20000':

            298.13 msec task-clock                #    0.999 CPUs utilized
                 0      context-switches          #    0.000 /sec
                 0      cpu-migrations            #    0.000 /sec
                62      page-faults               #  207.966 /sec
     1,011,264,599      cycles                    #    3.392 GHz
     2,546,475,385      instructions              #    2.52  insn per cycle
       481,632,935      branches                  #    1.616 G/sec
           137,954      branch-misses             #    0.03% of all branches

       0.298409393 seconds time elapsed

       0.298429000 seconds user
       0.000000000 seconds sys
```

**`perf stat` results**
These counters cover all five benchmark variants together, not just one row:
- **298.13 msec task-clock; 0.999 CPUs utilized:** the process ran for about 0.298 seconds, using roughly one CPU core the whole time.
- **0 context-switches; 0 cpu-migrations:** it wasn’t switched out or moved to another CPU during the measured run. taskset -c 2 pins it to CPU 2.
- **62 page-faults:** memory-management events, often from starting the program or first touching memory. This small count isn’t the same as 62 slow disk reads.
- **1,011,264,599 cycles; 3.392 GHz:** roughly 1.01 billion cycles were counted, with an average effective clock rate of 3.392 GHz.
- **2,546,475,385 instructions; 2.52 insn per cycle:** across the whole run, the CPU retired about 2.52 instructions per cycle on average. That is not the number of floating-point additions per cycle.
- **481,632,935 branches; 137,954 branch-misses:** only about 0.03% of branches were mispredicted, so branch prediction wasn’t a major issue in this run.

All this data is exposed as counters by the CPU which the `perf stat` program will read. This is the data for the entire program, not for specific accumulator. 

### Running TMA

```sh
$ taskset -c 2 ./pmu-tools/toplev.py -l2 ./e1_depchain 20000
Consider disabling nmi watchdog to minimize multiplexing
(echo 0 | sudo tee /proc/sys/kernel/nmi_watchdog or
 echo kernel.nmi_watchdog=0 >> /etc/sysctl.conf ; sysctl -p as root)
Will measure complete system.
accumulators=1   1.183 ns/element  (0.85 Gelem/s)
accumulators=2   0.591 ns/element  (1.69 Gelem/s)
accumulators=4   0.296 ns/element  (3.38 Gelem/s)
accumulators=8   0.173 ns/element  (5.77 Gelem/s)
accumulators=16  0.170 ns/element  (5.90 Gelem/s)
# 5.1-full on Intel(R) Core(TM) i5-8250U CPU @ 1.60GHz [kblr/skylake]
C2    BE               Backend_Bound               % Slots                       70.8   [ 8.0%]
C2    BE/Mem           Backend_Bound.Memory_Bound  % Slots                       39.2   [ 8.0%]<==
	This metric represents fraction of slots the Memory
	subsystem within the Backend was a bottleneck...
C2    BE/Core          Backend_Bound.Core_Bound    % Slots                       31.6   [ 8.0%]
	This metric represents fraction of slots where Core non-
	memory issues were of a bottleneck...
C2-T0 MUX                                          %                              8.03
C2-T1 MUX                                          %                              8.04
Run toplev --describe Memory_Bound^ to get more information on bottleneck
Add --run-sample to find locations
Add --nodes '!+Memory_Bound*/3,+MUX' for breakdown.
Idle CPUs 0-1,3-5,7 may have been hidden. Override with --idle-threshold 100
```

The TMA lines summarize the **whole run across all five variants**:

- **Backend_Bound: 71.2% of slots** — the backend was the main bottleneck overall.
- **Memory_Bound: 39.1%** and **Core_Bound: 32.1%** — toplev splits that backend-bound share into memory-related and core-execution bottlenecks. These are nested categories, not extra percentages to add to 71.2%.
- **MUX: 8%** — the counters were multiplexed to some extent. The warning suggests disabling the NMI watchdog may reduce that, but it requires a system setting change.
- **“Will measure complete system”** — treat the counters as system-wide, so other activity could affect them. Pinning your program to CPU 2 doesn’t make the TMA results per accumulator variant.

A “Memory_Bound” result doesn’t by itself mean the program is waiting on DRAM; the benchmark’s 16 KiB array is intended to fit in L1, and this TMA report doesn’t identify a specific memory level. Intel describes top-down results as shares of pipeline slots, and `toplev` reports aggregate metrics rather than locating the bottleneck in a particular function. [Intel’s top-down method](https://www.intel.com/content/www/us/en/docs/vtune-profiler/cookbook/2024-0/top-down-microarchitecture-analysis-method.html), [`toplev` documentation](https://github.com/andikleen/pmu-tools/blob/master/toplev.man)


## 2. Branch Prediction

**Concept:** A correctly predicted branch is almost free. A mispredicted branch flushes speculative state and costs ~10–20 cycles.

```c
// Exp 2: branch prediction.
// Same arithmetic on sorted vs unsorted data, branchy vs branchless.
// Build WITHOUT -ffast-math; the branchless trick does not need it anyway.
#include "common.h"
#include <string.h>
#include <stdlib.h>

#define N (1 << 16)          /* 256 KiB of data, bigger than L2 */
static int d[N];             /* random 0..255 values */
static int sorted[N];        /* the same data, sorted */

static int cmp(const void *a, const void *b)
{
    return *(const int *)a - *(const int *)b;
}

/* Branchy version.
 * The empty asm volatile("") inside the if-body stops GCC from converting
 * the branch into a conditional move (cmov), so we keep the real
 * data-dependent branch and can measure branch-misprediction cost.
 */
__attribute__((noinline))
long branchy_sum(const int *x, long reps)
{
    long s = 0;
    for (long r = 0; r < reps; r++) {
        for (int i = 0; i < N; i++) {
            if (x[i] >= 128) {
                s += x[i];
                asm volatile("");
            }
        }
    }
    return s;
}

/* Branchless version using a bit-mask select.
 * (v >= 128) is 1 or 0, so -(v >= 128) is -1 or 0.
 * v & -1 == v, v & 0 == 0. No branch, no mispredict.
 */
__attribute__((noinline))
long branchless_sum(const int *x, long reps)
{
    long s = 0;
    for (long r = 0; r < reps; r++) {
        for (int i = 0; i < N; i++) {
            int v = x[i];
            s += v & -(v >= 128);
        }
    }
    return s;
}

static void bench(const char *name, long (*fn)(const int *, long), const int *x, long reps)
{
    double t0 = now();
    volatile long r = fn(x, reps);
    double dt = now() - t0;
    (void)r;

    printf("%-20s %.3f ns/element\n", name, dt * 1e9 / (reps * (double)N));
}

int main(int argc, char **argv)
{
    long reps = (argc > 1) ? atol(argv[1]) : 2000;
    uint64_t st = 88172645463325252ULL;

    for (int i = 0; i < N; i++) {
        d[i] = (int)(rng(&st) & 255);
    }
    memcpy(sorted, d, sizeof(d));
    qsort(sorted, N, sizeof(int), cmp);

    bench("branchy   unsorted", branchy_sum, d, reps);
    bench("branchy   sorted  ", branchy_sum, sorted, reps);
    bench("branchless unsorted", branchless_sum, d, reps);
    bench("branchless sorted  ", branchless_sum, sorted, reps);

    return 0;
}
```

We compile it with same flags as e1

```sh
$ taskset -c 2 ./e2_branch
branchy   unsorted   4.655 ns/element
branchy   sorted     0.739 ns/element
branchless unsorted  0.816 ns/element
branchless sorted    0.815 ns/element
```

Same arithmetic, **6.3× difference** between branchy-unsorted and branchy-sorted. The absolute numbers are lower than earlier because the CPU was cooler for this run, but the ratio is the point.

### Perf Counters

```sh
$ taskset -c 2 perf stat  ./e2_branch
branchy   unsorted   4.653 ns/element
branchy   sorted     0.739 ns/element
branchless unsorted  0.814 ns/element
branchless sorted    0.816 ns/element

 Performance counter stats for './e2_branch':

            926.32 msec task-clock                #    1.000 CPUs utilized
                 2      context-switches          #    2.159 /sec
                 0      cpu-migrations            #    0.000 /sec
               250      page-faults               #  269.884 /sec
     3,142,145,000      cycles                    #    3.392 GHz
     4,613,170,142      instructions              #    1.47  insn per cycle
       791,997,278      branches                  #  854.990 M/sec
        65,877,015      branch-misses             #    8.32% of all branches

       0.926625104 seconds time elapsed

       0.926623000 seconds user
       0.000000000 seconds sys
```

We can see the overall brnahc misses is about 8.32%. Let's see where the branch misses are coming from

`perf stat` counts events and prints a summary; it doesn’t save the samples that `perf annotate` needs.

```sh
$ taskset -c 2 perf record -e branch-misses:p -g -o /tmp/e2-branch.data -- ./e2_branch
WARNING: Kernel address maps (/proc/{kallsyms,modules}) are restricted,
check /proc/sys/kernel/kptr_restrict and /proc/sys/kernel/perf_event_paranoid.

Samples in kernel functions may not be resolved if a suitable vmlinux
file is not found in the buildid cache or in the vmlinux path.

Samples in kernel modules won't be resolved at all.

If some relocation was applied (e.g. kexec) symbols may be misresolved
even with a suitable vmlinux or kallsyms file.

Couldn't record kernel reference relocation symbol
Symbol resolution may be skewed if relocation was used (e.g. kexec).
Check /proc/kallsyms permission or run as root.
branchy   unsorted   4.717 ns/element
branchy   sorted     0.739 ns/element
branchless unsorted  0.817 ns/element
branchless sorted    0.816 ns/element
[ perf record: Woken up 1 times to write data ]
[ perf record: Captured and wrote 0.198 MB /tmp/e2-branch.data (2568 samples) ]
```

```sh
Samples: 2K of event 'branch-misses:p', Event count (approx.): 65917256
  Children      Self  Command    Shared Object     Symbol
+   99.46%     0.00%  e2_branch  libc-2.31.so      [.] __libc_start_main
+   99.46%     0.00%  e2_branch  e2_branch         [.] main
+   99.45%    99.45%  e2_branch  e2_branch         [.] branchy_sum
+    0.50%     0.50%  e2_branch  libc-2.31.so      [.] msort_with_tmp.part.0
     0.02%     0.02%  e2_branch  libc-2.31.so      [.] __memmove_avx_unaligned_erms
     0.02%     0.00%  e2_branch  [unknown]         [k] 0xffffffffa1e00124
     0.02%     0.00%  e2_branch  [unknown]         [k] 0xffffffffa1d8d894
     0.01%     0.00%  e2_branch  [unknown]         [k] 0x00007f9b8b92217b
     0.01%     0.00%  e2_branch  [unknown]         [k] 0xffffffffa1002e00
     0.01%     0.00%  e2_branch  [unknown]         [k] 0xffffffffa139c3f7
     0.01%     0.00%  e2_branch  [unknown]         [k] 0xffffffffa139c127
     0.01%     0.00%  e2_branch  [unknown]         [k] 0xffffffffa139bb6d
     0.01%     0.00%  e2_branch  [unknown]         [k] 0xffffffffa139a447
     0.01%     0.01%  e2_branch  [unknown]         [k] 0xffffffffa1295830
     0.01%     0.00%  e2_branch  [unknown]         [k] 0xffffffffa1417aef
     0.01%     0.00%  e2_branch  [unknown]         [k] 0xffffffffa1415a8f
     0.01%     0.00%  e2_branch  [unknown]         [k] 0xffffffffa12dc56d
     0.01%     0.00%  e2_branch  [unknown]         [k] 0xffffffffa12dc4a8
     0.01%     0.00%  e2_branch  [unknown]         [k] 0xffffffffa130b125
     0.01%     0.00%  e2_branch  [unknown]         [k] 0xffffffffa130ad40
     0.01%     0.00%  e2_branch  [unknown]         [k] 0xffffffffa130a98a
     0.01%     0.00%  e2_branch  [unknown]         [k] 0xffffffffa12a2497
     0.01%     0.01%  e2_branch  e2_branch         [.] branchless_sum
```

We can see self at 99.45% for `e2_branch`.

To inspect annotated assembly in the terminal:

```sh
sanketh@ubuntu20:~/cpu-lab$ perf annotate -i /tmp/e2-branch.data --stdio
 Percent |      Source code & Disassembly of e2_branch for branch-misses:p (2477 samples, percent: local period)
----------------------------------------------------------------------------------------------------------------
         :
         :
         :
         : 3    Disassembly of section .text:
         :
         : 5    0000000000001330 <branchy_sum>:
         : 6    branchy_sum():
         : 24   * the branch into a conditional move (cmov), so we keep the real
         : 25   * data-dependent branch and can measure branch-misprediction cost.
         : 26   */
         : 27   __attribute__((noinline))
         : 28   long branchy_sum(const int *x, long reps)
         : 29   {
    0.00 :   1330:   endbr64
    0.00 :   1334:   mov    %rsi,%r9
         : 26   long s = 0;
         : 27   for (long r = 0; r < reps; r++) {
    0.00 :   1337:   test   %rsi,%rsi
    0.00 :   133a:   jle    1370 <branchy_sum+0x40>
    0.00 :   133c:   xor    %esi,%esi
         : 25   long s = 0;
    0.00 :   133e:   xor    %r8d,%r8d
    0.00 :   1341:   lea    0x40000(%rdi),%rcx
    0.00 :   1348:   mov    %rdi,%rax
    0.00 :   134b:   nopl   0x0(%rax,%rax,1)
         : 28   for (int i = 0; i < N; i++) {
         : 29   if (x[i] >= 128) {
    0.00 :   1350:   movslq (%rax),%rdx
    0.00 :   1353:   cmp    $0x7f,%edx
    0.00 :   1356:   jle    135b <branchy_sum+0x2b>
         : 29   s += x[i];
   45.43 :   1358:   add    %rdx,%r8
         : 27   for (int i = 0; i < N; i++) {
   54.57 :   135b:   add    $0x4,%rax
    0.00 :   135f:   cmp    %rcx,%rax
```

**Why is it showing branch misses at `add` instruction?**

`perf annotate` is showing **where it attributes the sampled branch-miss events**, not how often each instruction executes.

The branch being measured is:

```asm
cmp    $0x7f, %edx
jle    135b
```

That `jle` implements `if (x[i] < 128)`. The hardware detects a misprediction when its prediction for that branch was wrong. But the sampled instruction address can land just after the branch, so `perf annotate` displays the samples on the following instructions:

```asm
add    %rdx, %r8     ; taken path: value was >= 128
add    $0x4, %rax    ; loop continues
```

So **45.43% and 54.57% are the shares of samples attributed to those instruction addresses**. They do not mean the `add` instructions caused branch mispredictions or were executed those percentages of the time. The conditional `jle` is still the branch of interest; the nearby attribution reflects the limits of locating a sampled hardware event to one exact instruction.

Let's remove the `asm volatile("")` and see what happens

```sh
cp e2_branch.c /tmp/e2_branch_no_barrier.c
sed -i '/asm volatile("");/d' /tmp/e2_branch_no_barrier.c
gcc -O2 -g -fno-omit-frame-pointer -march=native -I. \
    /tmp/e2_branch_no_barrier.c -o /tmp/e2_branch_no_barrier

objdump -d -M intel --disassemble=branchy_sum /tmp/e2_branch_no_barrier
```

```sh

sanketh@ubuntu20:~/cpu-lab$ r2 -q -c 's sym.branchy_sum; pd 25' /tmp/e2_branch_no_barrier
            ;-- branchy_sum:
            0x00001330      f3             invalid                     ; e2_branch_no_barrier.c:24 {
            0x00001331      0f             invalid
            0x00001332      1e             invalid
            0x00001333      fa             cli
            0x00001334      4989f9         mov r9, rdi                 ; e2_branch_no_barrier.c:25     long s = 0;
            0x00001337      4989f2         mov r10, rsi
            0x0000133a      4885f6         test rsi, rsi               ; e2_branch_no_barrier.c:26     for (long r = 0; r < reps; r++) {
        ┌─< 0x0000133d      7e36           jle 0x1375
        │   0x0000133f      31ff           xor edi, edi
        │   0x00001341      4531c0         xor r8d, r8d
        │   0x00001344      498db1000004.  lea rsi, qword [r9 + 0x40000]
       ┌──> 0x0000134b      4c89c8         mov rax, r9                 ; e2_branch_no_barrier.c:25     long s = 0;
       ╎│   0x0000134e      6690           nop
      ┌───> 0x00001350      486310         movsxd rdx, dword [rax]     ; e2_branch_no_barrier.c:28             if (x[i] >= 128) {
      ╎╎│   0x00001353      4889d1         mov rcx, rdx
      ╎╎│   0x00001356      4c01c2         add rdx, r8                 ; e2_branch_no_barrier.c:29                 s += x[i];
      ╎╎│   0x00001359      83f97f         cmp ecx, 0x7f
      ╎╎│   0x0000135c      4c0f4fc2       cmovg r8, rdx
      ╎╎│   0x00001360      4883c004       add rax, 4                  ; e2_branch_no_barrier.c:27         for (int i = 0; i < N; i++) {
      ╎╎│   0x00001364      4839f0         cmp rax, rsi
      └───< 0x00001367      75e7           jne 0x1350
       ╎│   0x00001369      48ffc7         inc rdi                     ; e2_branch_no_barrier.c:26     for (long r = 0; r < reps; r++) {
       ╎│   0x0000136c      4939fa         cmp r10, rdi
       └──< 0x0000136f      75da           jne 0x134b
        │   0x00001371      4c89c0         mov rax, r8                 ; e2_branch_no_barrier.c:34 }
sanketh@ubuntu20:~/cpu-lab$ r2 -q -c 's sym.branchy_sum; pd 25' e2_branch
            ;-- branchy_sum:
            0x00001330      f3             invalid                     ; e2_branch.c:24 {
            0x00001331      0f             invalid
            0x00001332      1e             invalid
            0x00001333      fa             cli
            0x00001334      4989f1         mov r9, rsi                 ; e2_branch.c:25     long s = 0;
            0x00001337      4885f6         test rsi, rsi               ; e2_branch.c:26     for (long r = 0; r < reps; r++) {
        ┌─< 0x0000133a      7e34           jle 0x1370
        │   0x0000133c      31f6           xor esi, esi
        │   0x0000133e      4531c0         xor r8d, r8d
        │   0x00001341      488d8f000004.  lea rcx, qword [rdi + 0x40000]
       ┌──> 0x00001348      4889f8         mov rax, rdi                ; e2_branch.c:25     long s = 0;
       ╎│   0x0000134b      0f1f440000     nop dword [rax + rax]
      ┌───> 0x00001350      486310         movsxd rdx, dword [rax]     ; e2_branch.c:28             if (x[i] >= 128) {
      ╎╎│   0x00001353      83fa7f         cmp edx, 0x7f
     ┌────< 0x00001356      7e03           jle 0x135b
     │╎╎│   0x00001358      4901d0         add r8, rdx                 ; e2_branch.c:29                 s += x[i];
     └────> 0x0000135b      4883c004       add rax, 4                  ; e2_branch.c:30                 asm volatile("");
      ╎╎│   0x0000135f      4839c8         cmp rax, rcx                ; e2_branch.c:27         for (int i = 0; i < N; i++) {
      └───< 0x00001362      75ec           jne 0x1350
       ╎│   0x00001364      48ffc6         inc rsi
       ╎│   0x00001367      4939f1         cmp r9, rsi                 ; e2_branch.c:26     for (long r = 0; r < reps; r++) {
       └──< 0x0000136a      75dc           jne 0x1348
        │   0x0000136c      4c89c0         mov rax, r8                 ; e2_branch.c:35 }
        │   0x0000136f      c3             ret
        └─> 0x00001370      4531c0         xor r8d, r8d                ; e2_branch.c:25     long s = 0;
```

In the **no-barrier** build, GCC uses a conditional move:

```asm
cmp   ecx, 0x7f
cmovg r8, rdx
```

That means it computes the candidate sum, then updates `r8` only when the value is greater than 127—without a data-dependent jump.

In the original build, the same condition uses a conditional jump:

```asm
cmp   edx, 0x7f
jle   0x135b
add   r8, rdx
```

So removing `asm volatile("");` had the effect you expected: it let GCC replace the branch with `cmovg`. The `jne` instructions still present in both versions are loop-control branches; the one removed is the branch on `x[i] >= 128`.

## 3. Memory latency staircase + MLP (section 6)

**Concept:** A load that misses L3 can take ~100 ns. The CPU has a limited number of line-fill buffers; if you issue multiple independent misses, they overlap and the *effective* latency per load drops.


```c
// Exp 3: measure pointer-chasing latency and memory-level parallelism.
// Usage: ./e3_chase [chains=1]
// Reports average nanoseconds per dependent load for working sets from 4 KiB to 1 GiB.
#include "common.h"

#define MIN_WORKING_SET_BYTES 4096
#define MAX_WORKING_SET_BYTES (1UL << 30)
#define MAX_CHAINS 16
#define TARGET_LOADS 20000000L
#define MIN_STEPS 100000L
#define PAGE_ALIGNMENT 4096

/*
 * Make next[] a random permutation containing one cycle through every entry.
 * Following next[index] repeatedly therefore visits the whole working set
 * before returning to the starting index.
 */
static void make_single_cycle(size_t *next, size_t count, uint64_t *random_state)
{
    for (size_t i = 0; i < count; i++) {
        next[i] = i;
    }

    // Sattolo's shuffle creates one cycle rather than several smaller cycles.
    for (size_t i = count - 1; i > 0; i--) {
        size_t j = rng(random_state) % i;
        size_t temporary = next[i];
        next[i] = next[j];
        next[j] = temporary;
    }
}

int main(int argc, char **argv)
{
    int chain_count = (argc > 1) ? atoi(argv[1]) : 1;
    if (chain_count < 1 || chain_count > MAX_CHAINS) {
        chain_count = 1;
    }

    uint64_t random_state = 1234567;

    printf("chains=%d\n%10s %12s\n", chain_count, "size", "ns/load");

    for (size_t working_set_bytes = MIN_WORKING_SET_BYTES;
         working_set_bytes <= MAX_WORKING_SET_BYTES;
         working_set_bytes *= 2) {
        size_t element_count = working_set_bytes / sizeof(size_t);
        size_t *next = aligned_alloc(PAGE_ALIGNMENT, working_set_bytes);
        if (next == NULL) {
            perror("aligned_alloc");
            return 1;
        }

        make_single_cycle(next, element_count, &random_state);

        // Start each chain at a different point in the cycle.
        size_t current[MAX_CHAINS];
        for (int chain = 0; chain < chain_count; chain++) {
            current[chain] = (element_count / chain_count) * (size_t)chain;
        }

        // Touch every entry once before timing, so page faults and first-touch
        // setup do not dominate the measured pointer-chasing loop.
        for (size_t i = 0; i < element_count; i++) {
            current[0] = next[current[0]];
        }

        // Keep roughly the same total number of loads as the working set grows.
        long steps_per_chain = TARGET_LOADS / chain_count
                             + (long)(element_count / (size_t)chain_count);
        if (steps_per_chain < MIN_STEPS) {
            steps_per_chain = MIN_STEPS;
        }

        double start_time = now();
        for (long step = 0; step < steps_per_chain; step++) {
            for (int chain = 0; chain < chain_count; chain++) {
                // Each load depends on the previous load in this chain.
                current[chain] = next[current[chain]];
            }
        }
        double elapsed_seconds = now() - start_time;

        // Consume the final indexes so the traversal remains observable.
        size_t checksum = 0;
        for (int chain = 0; chain < chain_count; chain++) {
            checksum += current[chain];
        }
        if (checksum == 42) {
            puts("");
        }

        double total_loads = (double)steps_per_chain * chain_count;
        double nanoseconds_per_load = elapsed_seconds * 1e9 / total_loads;
        printf("%8zuKB %12.2f\n",
               working_set_bytes >> 10, nanoseconds_per_load);
        fflush(stdout);

        free(next);
    }

    return 0;
}
```

The program visits array elements in a **random order**. It’s set up so that each step tells the program which element to visit next.

For example, it might follow this path:

```text
element 12 → element 403 → element 7 → element 91 → ...
```

The key idea is that the program can’t know the next element until it has read the current one. That makes each chain a little like following directions one at a time. With one chain, it has to wait for each answer before continuing. With several chains, it can follow several separate paths and make progress on another while one is waiting.

The program repeats this with arrays of different sizes to see how the computer’s memory affects the time per step.

`aligned_alloc` asks the system for a block of memory that starts at a particular kind of address boundary. Here, `aligned_alloc(4096, working_set_bytes)` asks for the array to start on a **4096-byte boundary**, which is the size of a typical memory page. This gives the allocation a predictable alignment; it doesn’t make the array’s contents ordered or automatically make the accesses faster.

The experiment tests two related things: **how memory access time changes as the data gets larger**, and **whether several independent memory requests can overlap**.

The program builds a randomly ordered path through an array. Each array entry points to the index of the next entry, so it follows a chain like:

```text
index 12 → index 403 → index 7 → ...
```

Because the next index isn’t known until the current load finishes, one chain forces the CPU to wait for each load before starting the next one. That makes it useful for measuring **memory latency**.

The program tries different array sizes, from 4 KiB to 1 GiB. Small arrays may fit in fast CPU caches; larger arrays may need slower caches or main memory. It times the pointer chasing and reports average nanoseconds per load.

The `chains` argument tests **memory-level parallelism**:

- With `1` chain, each load depends on the previous one, limiting overlap.
- With several independent chains, the CPU can work on loads from other chains while one is waiting.

If multiple chains reduce the average time per load, it shows that the CPU can overlap independent memory accesses. That doesn’t make any single load faster; it increases the number of loads completed while others are in flight.

In short: the size sweep shows the memory hierarchy’s effect on latency, and the chain-count sweep shows how independent work can hide some of that latency.

```sh
$ taskset -c 2 ./e3_chase
chains=1
      size      ns/load
       4KB         2.76
       8KB         2.76
      16KB         2.76
      32KB         2.77
      64KB         3.88
     128KB         4.65
     256KB         5.77
     512KB         9.97
    1024KB        12.43
    2048KB        13.84
    4096KB        17.28
    8192KB        38.43
   16384KB        64.90
   32768KB        79.37
   65536KB        87.76
  131072KB        93.64
  262144KB        97.32
  524288KB        99.38
 1048576KB       101.03
```

```sh
$ taskset -c 2 ./e3_chase 4
chains=4
      size      ns/load
       4KB         0.74
       8KB         0.74
      16KB         0.74
      32KB         0.74
      64KB         1.01
     128KB         1.15
     256KB         1.48
     512KB         2.70
    1024KB         3.36
    2048KB         3.68
    4096KB         4.35
    8192KB         9.61
   16384KB        15.68
   32768KB        18.82
   65536KB        20.78
  131072KB        23.03
  262144KB        23.64
  524288KB        23.73
 1048576KB        24.07
[ble: elapsed 43.682s (CPU 100.0%)] taskset -c 2 ./e3_chase 4
```

```sh
$ taskset -c 2 ./e3_chase 10
chains=10
      size      ns/load
       4KB         0.41
       8KB         0.41
      16KB         0.41
      32KB         0.41
      64KB         0.52
     128KB         0.61
     256KB         0.74
     512KB         1.31
    1024KB         1.59
    2048KB         1.71
    4096KB         2.24
    8192KB         5.00
   16384KB         7.64
   32768KB         9.22
   65536KB        10.07
  131072KB        10.72
  262144KB        11.12
  524288KB        12.75
 1048576KB        12.73
[ble: elapsed 38.913s (CPU 100.0%)] taskset -c 2 ./e3_chase 10
```


The rough steps match your cache sizes:
- flat until ~32 KB → **L1d**
- jump around 64–256 KB → **L2** (256 KB private)
- slower through 1–6 MB → **L3**
- >6 MB → **DRAM**

The DRAM numbers are noisy because of thermal throttling and OS background noise, but the shape is right.

**MLP effect:**

| size | 1 chain | 4 chains | 10 chains |
|------|--------:|---------:|----------:|
| 1 GB | 101.03 | 24.07 | 12.73 |

Going from 1 to 10 independent chains drops the *perceived* DRAM latency by **7.93×**. That is the “latency-hiding machine” from the post: the memory subsystem overlaps many outstanding misses.

**Perf counters (1 chain, whole walk):**

```text
cycles               178,485,837,207
instructions        16,724,164,329    # IPC 0.09
L1-dcache-load-misses 2,055,000,865
LLC-load-misses        916,471,923
dTLB-load-misses       875,041,639
```

IPC collapses to 0.09 — the core is just waiting on memory.

**TMA (pinned core 2, level-3):**

```text
Backend_Bound                         79.4%
Backend_Bound.Memory_Bound            68.8%
Backend_Bound.Memory_Bound.DRAM_Bound 47.9%
Backend_Bound.Memory_Bound.L3_Bound   14.4%
Backend_Bound.Memory_Bound.L1_Bound   13.2%
Backend_Bound.Core_Bound             10.5%
```

This is the textbook “memory-bound” fingerprint.


## 4. False sharing (E4)

**Concept:** When two threads write different variables that happen to live on the same cache line, the line bounces between cores even though no data is logically shared. Padding each variable to its own line fixes it.

```c
// Exp 4: compare packed counters with cache-line-padded counters.
// Usage: ./e4_falseshare [threads=4]
#include "common.h"
#include <pthread.h>

#define MAX_THREADS 16
#define INCREMENTS_PER_THREAD 200000000L
#define CACHE_LINE_BYTES 64

typedef enum {
    PACKED_COUNTERS,
    PADDED_COUNTERS
} counter_layout_t;

typedef struct {
    volatile long value;
    char padding[CACHE_LINE_BYTES - sizeof(volatile long)];
} padded_counter_t;

_Static_assert(sizeof(padded_counter_t) == CACHE_LINE_BYTES,
               "each padded counter should occupy one cache line");

typedef struct {
    int thread_id;
    counter_layout_t layout;
} worker_args_t;

_Alignas(CACHE_LINE_BYTES) static volatile long packed_counters[MAX_THREADS];
_Alignas(CACHE_LINE_BYTES) static padded_counter_t padded_counters[MAX_THREADS];

static void *increment_counter(void *argument)
{
    const worker_args_t *args = argument;

    if (args->layout == PACKED_COUNTERS) {
        for (long i = 0; i < INCREMENTS_PER_THREAD; i++) {
            packed_counters[args->thread_id]++;
        }
    } else {
        for (long i = 0; i < INCREMENTS_PER_THREAD; i++) {
            padded_counters[args->thread_id].value++;
        }
    }

    return NULL;
}

static void run_benchmark(int thread_count, counter_layout_t layout)
{
    pthread_t threads[MAX_THREADS];
    worker_args_t worker_args[MAX_THREADS];
    const char *layout_name =
        (layout == PACKED_COUNTERS) ? "packed" : "padded";

    // Include thread startup and joining in the timed interval, as before.
    double start_time = now();

    for (int thread_id = 0; thread_id < thread_count; thread_id++) {
        worker_args[thread_id].thread_id = thread_id;
        worker_args[thread_id].layout = layout;
        pthread_create(&threads[thread_id], NULL,
                       increment_counter, &worker_args[thread_id]);
    }

    for (int thread_id = 0; thread_id < thread_count; thread_id++) {
        pthread_join(threads[thread_id], NULL);
    }

    double elapsed_seconds = now() - start_time;
    printf("%-7s %d threads: %.3f s\n",
           layout_name, thread_count, elapsed_seconds);
}

int main(int argc, char **argv)
{
    int thread_count = (argc > 1) ? atoi(argv[1]) : 4;
    if (thread_count < 1 || thread_count > MAX_THREADS) {
        fprintf(stderr, "thread count must be between 1 and %d\n", MAX_THREADS);
        return 1;
    }

    run_benchmark(thread_count, PACKED_COUNTERS);
    run_benchmark(thread_count, PADDED_COUNTERS);

    return 0;
}
```