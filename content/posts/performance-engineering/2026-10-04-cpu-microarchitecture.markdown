---
title:  "Performance Engineering: CPU Microarchitecture for the Practitioner"
date:   2026-10-04
categories: ["performance-engineering"]
tags: ["performance", "cpu", "microarchitecture", "perf", "pipelines"]

---

# Performance Engineering: CPU Microarchitecture for the Practitioner

This note explains what a modern CPU actually does while your program runs, and how to read that behavior through hardware performance counters. The goal is not to memorize every unit in a specific core design, but to build a mental model that makes `perf` output meaningful.

If the previous note asked "where does the time go," this note answers "what is the CPU doing with the cycles it consumes."

## 1. The CPU is a latency-hiding machine

Your program is written as a sequence of instructions. The CPU does not execute them one at a time. It reorders, overlaps, and speculates so that the *observable result* is sequential, while the *physical execution* is parallel.

```text
program view          hardware view
    I1                  I1  I2  I3  I4  I5
    I2                    I2  I3  I4  I5  I6
    I3                      I3  I4  I5  I6  I7
    I4                        ...
```

The CPU tries to keep many instructions in flight simultaneously. Its only purpose is to retire useful instructions as fast as possible, while hiding the latency of memory, branches, and dependencies.

A CPU is not fast because each instruction is fast. It is fast because it overlaps work. When it cannot overlap, it stalls. Those stalls are where performance is lost.

## 2. The pipeline: the basic mental model

The classic five-stage pipeline is still the right place to start:

```text
IF → ID → EX → MEM → WB

IF   = Instruction Fetch
ID   = Instruction Decode
EX   = Execute
MEM  = Memory access
WB   = Write Back
```

Each stage handles one instruction at a time, but different stages handle different instructions simultaneously. In a perfect pipeline, one instruction completes every cycle. In reality, instructions have dependencies and the pipeline must wait.

Three kinds of hazards cause waits:

| Hazard | Cause | Example |
|--------|-------|---------|
| **Structural** | Two instructions need the same unit at the same time | two divides in the same cycle |
| **Data** | An instruction needs a result not yet produced | `add r1, r2` followed by `mul r3, r1` |
| **Control** | The next instruction depends on a branch decision | an `if` statement where the target is unknown |

Modern CPUs have much deeper pipelines than five stages and many parallel copies of each stage, but the same hazards still appear in `perf` output as stalls.

## 3. Superscalar execution and instruction-level parallelism

A superscalar CPU can issue **multiple instructions per cycle**. It looks for instructions that are independent and sends them down parallel pipelines.

```text
sequential:    I1 → I2 → I3 → I4 → I5
superscalar:   I1 I2 → I3 I4 → I5 I6
```

The amount of independence available in a region of code is called **instruction-level parallelism (ILP)**. Code with high ILP runs fast on a wide core. Code with long dependency chains cannot use the width.

Consider two versions of a loop that both add numbers:

```c
// version A: long dependency chain
float sum = 0;
for (int i = 0; i < n; i++) {
    sum += a[i];   // each add needs the previous result
}

// version B: four independent chains
float s0 = 0, s1 = 0, s2 = 0, s3 = 0;
for (int i = 0; i < n; i += 4) {
    s0 += a[i];
    s1 += a[i+1];
    s2 += a[i+2];
    s3 += a[i+3];
}
float sum = s0 + s1 + s2 + s3;
```

Version A has a chain of `n` dependent additions. Version B has four chains of `n/4` additions. The second version runs much faster on modern CPUs because the CPU can overlap the four independent chains. This is the same trick used inside compilers for loop unrolling with multiple accumulators.

The dependencies that limit ILP are:

- **RAW (read after write):** true dependency; one instruction needs the result of another.
- **WAR (write after read):** an instruction writes a register that a later instruction reads. Modern CPUs rename registers to remove this.
- **WAW (write after write):** two instructions write the same register. Renaming removes this too.

RAW dependencies are the real ones. WAR and WAW are bookkeeping artifacts that register renaming eliminates.

## 4. Out-of-order execution

In-order CPUs execute instructions in program order. Out-of-order (OoO) CPUs execute instructions when their operands are ready and the execution unit is free, even if earlier instructions are still waiting.

```text
program order:     I1  I2  I3  I4  I5  I6
ready to execute:  I1  I3  I2  I6  I4  I5
actual dispatch:   I1  I3      I2  I6  I4  I5
```

This requires three key structures:

| Structure | Role |
|-----------|------|
| **Reorder buffer (ROB)** | Tracks all in-flight instructions and commits results in program order. |
| **Reservation station / scheduler** | Holds instructions waiting for operands and free execution units. |
| **Register renaming / physical register file** | Removes false dependencies by mapping architectural registers to a larger physical register set. |

The CPU fetches and decodes instructions in order, places them in the ROB and reservation station, executes them out of order when ready, and then commits results in order. If an exception or misprediction occurs, the ROB lets the CPU discard speculative work cleanly.

The size of the ROB and the reservation station determines how far ahead the CPU can look for independent work. A larger window can hide more latency, but costs power and area.

## 5. Speculative execution and branch prediction

Branches are a problem because they break sequential fetch. The CPU does not know which path to fetch until the branch resolves. Waiting is unacceptable for performance, so the CPU predicts the outcome and executes speculatively.

```text
        ┌── taken? → fetch path A
 if ---┤
        └── not taken? → fetch path B

CPU picks one path based on prediction, executes it,
then rolls back if it was wrong.
```

A correct prediction costs almost nothing. A misprediction is expensive: the CPU must flush speculative state from the front-end and the ROB, then restart from the correct path. The penalty can be 10-20 cycles on modern cores.

Branch predictors learn patterns:

- **Conditional branches:** is the `if` usually taken?
- **Indirect branches:** where does this function pointer call go?
- **Returns:** call/return pairs are tracked on a return-address stack.

Patterns that are hard to predict hurt performance: random data, state machines with irregular transitions, polymorphic virtual calls, long chains of dependent branches.

Code that wants predictable branches often sorts data first so that `if (x > threshold)` sees long runs of the same outcome, or replaces branches with branchless conditionals.

```c
// branchy
int x = (a > b) ? 100 : 0;

// branchless on x86: cmov
int x = (a > b) * 100;   // compiler may use cmov or bitwise select
```

Not all branches should be removed — predictable branches are nearly free — but unpredictable branches are one of the first things to eliminate in hot loops.

## 6. The memory subsystem from the core's perspective

Memory is far slower than the CPU. A load that misses all caches can take 200-300 cycles. OoO execution and speculation cannot hide that if the load is on the critical path.

Between the execution units and DRAM sits a hierarchy:

```text
CPU core
   L1 data cache
   L1 instruction cache
   L2 cache (often private to core)
   L3 cache (shared across cores)
   DRAM
```

There are also specialized buffers:

| Buffer | Role |
|--------|------|
| **Load queue / store queue** | Track in-flight memory operations. |
| **Memory order buffer (MOB)** | Maintain correct load/store ordering while allowing reordering. |
| **Line fill buffers (LFBs)** | Buffers for outstanding cache misses. |
| **Translation lookaside buffer (TLB)** | Cache for virtual-to-physical address translations. |

Loads are particularly important because they feed dependent instructions. A load that misses L1 but hits L2 costs ~12 cycles. A load that misses L3 costs ~200 cycles. A load that triggers a page walk costs much more.

The CPU can execute loads and stores out of order, but it must preserve the memory model visible to software. On x86, loads cannot pass earlier loads, and stores cannot pass earlier stores. The MOB ensures this while still allowing loads to execute early when safe.

```text
store A
load B
store C
load D

The CPU may reorder loads and stores internally,
but the final result must look as if they executed in program order.
```

Memory disambiguation is the mechanism that lets a load execute before an earlier store whose address is not yet known. If the addresses turn out to alias, the load must be replayed.

## 7. Execution ports and instruction throughput

A modern core has multiple **execution ports**. Each cycle, the scheduler can dispatch ready micro-operations (uops) to available ports. Each port can execute a subset of operations.

A typical Intel core might have ports like this (simplified):

```text
port 0:  ALU, shift, mul, div, SIMD
port 1:  ALU, shift, branch, SIMD
port 5:  ALU, branch, SIMD
port 2:  load
port 3:  load
port 4:  store
port 6:  ALU, branch
port 7:  store address
```

The exact layout varies by microarchitecture, but the principle is constant: **throughput is limited by port pressure and latency is limited by dependencies.**

If a loop contains one load per iteration and the CPU has two load ports, the loop cannot go faster than one load every 0.5 cycles on average, assuming the loads are independent. If the loads are dependent, latency dominates instead.

Every instruction is decoded into one or more **uops**. Complex instructions like `idiv` or `rep movsb` may produce many uops. The CPU retires uops, not raw instructions, so high-uop code can be slower than instruction count suggests.

| Term | Meaning |
|------|---------|
| **Latency** | Cycles from input ready to output ready |
| **Throughput** | How many per cycle the core can sustain |
| **Uops** | Micro-operations the CPU actually executes |
| **Port pressure** | How many uops compete for the same execution port |

Two operations with the same latency can have very different throughput. A 32-bit integer add might have latency 1 and throughput 0.25 (four per cycle). A 64-bit integer division might have latency 25 and throughput one every several cycles.


> ### What is CPU Frontend and Backend? 
> 
> The CPU frontend is the section of the processor responsible for fetching program instructions from memory and translating them into micro-operations, whereas the CPU backend is the section that takes those micro-operations, figures out when they are ready, runs them through the execution units, and completes them in order.
> 
> Think of the frontend as the intake department of a factory that unpacks and prepares the raw materials, and the backend as the workshop floor where the actual building and assembly take place.
> 
> ### The CPU Frontend (The Preparation Engine)
> 
> The frontend does not actually calculate math or change data values. Its only job is to stay ahead of the program, guess where the code is going next, and translate instructions into a clean format.
> 
> * Fetch: The instruction pointer tells the CPU where to look in memory. The fetch unit pulls raw instruction bytes into the processor from the L1 instruction cache.
> * Branch Prediction: Code constantly hits "if/else" decisions and loops. The predictor guesses which path the code will take before the math is even done, so the CPU doesn't waste time waiting.
> * Decode: Raw instructions (whether complex x86 or simple ARM) are turned into standardized, bite-sized pieces called micro-operations or uops.
> * Register Renaming: The CPU maps the variable names used in the code to physical storage slots inside the chip, ensuring different tasks don't accidentally step on each other's data.
>
> ### The CPU Backend (The Execution Engine)
> 
> Once the frontend hands over a steady stream of ready uops, the backend takes full control to do the heavy lifting.
>
> * Scheduler (Reservation Station): A temporary holding area where uops wait until the data they need is calculated and finished by previous instructions.
> * Execution Ports and Units: The actual calculation hardware (such as ALUs for math and load/store units for memory) that we covered earlier. The scheduler pushes uops through the ports into these units.
> * Reorder Buffer (ROB) and Retirement: Because the backend executes instructions out of order to go faster, the ROB keeps track of everything and commits the results back to the system memory in the strict, original sequence required by the program.
>
> ### How They Work Together
>
> The speed of a processor relies on the balance between these two halves. If the backend has 16 execution ports but the frontend can only decode 4 instructions per cycle, the execution units will sit idle and starve. If the frontend is super fast but the backend has too few execution ports, the uops will pile up and bottleneck. Apple's M-series chips excel because both their wide 8-wide frontend and their massive 15+ port backend are scaled up equally.


> Understaning execution ports as its bit contradicting with pipeline analogy.
> It is completely natural to feel a contradiction here! When we first learn about pipelining, we are usually taught a simple, linear model: instructions move down a single conveyor belt one after another (Fetch → Decode → Execute → Writeback).
>
> **If the CPU is a single pipeline, why do we suddenly need execution ports?**
> The contradiction disappears when you realize that modern CPUs do not use a single conveyor belt. Instead, they use a hybrid architecture called Superscalar Out-of-Order Execution.
>
> Here is how to merge execution ports into your mental model of pipelining.
>
> ### The Factory Analogy: The "Split" Assembly Line
> 
> Think of a modern CPU core as a large, highly efficient custom manufacturing factory.
> 
> #### 1. The Frontend (The Shared Pipeline)
> 
> The beginning of the pipeline is a wide, shared conveyor belt. Instructions are Fetched from the program and Decoded into micro-operations (uops). At this stage, everything is in a strict, sequential line.
> 
> #### 2. The Reservation Station (The Waiting Room)
> 
> Once instructions are decoded, they enter a "waiting room" (the Reservation Station / Scheduler). They sit here until two conditions are met:
> * The data they need is ready (dependencies are resolved).
> * A physical tool is available to do the work.
>
> #### 3. The Execution Ports (The Specialist Workshops)
> 
> This is where your single pipeline splits. The factory floor has multiple distinct workshops, each containing specialized machinery:
>
> * Workshop A has adding machines (ALUs).
> * Workshop B has heavy machinery for multiplication and division.
> * Workshop C has forklifts for fetching data from the warehouse (Loads).
> * Workshop D has conveyor belts for shipping data out (Stores).
> 
> An execution port is the literal doorway or intake slot to one of these specific workshops.
> The scheduler looks at the waiting room, sees which uops are ready, and pushes them through the available doors (ports) simultaneously.
> 

## 8. Reading the machine with perf counters

`perf` exposes hardware counters that map directly to the concepts above. The most important starting counters are:

```bash
perf stat -e cycles,instructions,cycles:instructions,
               branch-misses,cache-misses,stall-cycles-frontend,stall-cycles-backend \
          ./your_program
```

| Counter | What it tells you |
|---------|-------------------|
| `cycles` | Total CPU cycles consumed. |
| `instructions` | Number of retired instructions. |
| `instructions/cycles` | IPC — instructions per cycle. Higher is better. |
| `cycles/instructions` | CPI — cycles per instruction. Lower is better. |
| `branch-misses` | Control-flow speculation failures. |
| `cache-misses` | LLC misses, usually DRAM traffic. |
| `stall-cycles-frontend` | Pipeline bubbles because the front end could not feed the back end. |
| `stall-cycles-backend` | Pipeline bubbles because the back end could not execute uops. |

A healthy CPU-bound loop often has IPC above 2 or 3. A stalled loop can have IPC below 1.

The ratio is directional, not absolute. A memory-bound program can have low IPC because the CPU spends most cycles waiting for loads. A compute-bound program can have high IPC if it is wide and independent.

More specific counters exist for each microarchitecture. The names vary between Intel and AMD, and between generations. `perf list` shows what your machine supports. Common advanced counters include:

```text
L1-dcache-load-misses      → L1 data cache misses
L1-icache-load-misses      → instruction cache misses
llc-load-misses            → last-level cache load misses
dTLB-load-misses           → data TLB misses
uops_issued.any            → uops sent to execution
uops_retired.retire_slots  → uops actually retired
```

## 9. Top-down microarchitecture analysis (TMA)

TMA is a structured way to classify CPU pipeline slots. A pipeline slot is one opportunity to retire one uop each cycle. If the CPU is 4-wide, there are 4 slots per cycle. TMA asks: what happened to each slot?

```text
100% of pipeline slots
   ├── Retiring            → useful work actually completed
   ├── Bad speculation     → work thrown away (mispredicts)
   ├── Front-end bound     → slots empty because fetch/decode could not keep up
   └── Back-end bound      → slots empty because execution could not keep up
        ├── Memory bound   → stalls waiting for memory hierarchy
        │      ├── L1 bound
        │      ├── L2 bound
        │      ├── L3 bound
        │      └── DRAM bound
        └── Core bound     → stalls due to execution port pressure, dependencies, etc.
```

This tree is powerful because it tells you which subsystem to fix:

| TMA bucket | Typical cause |
|------------|---------------|
| **Front-end bound** | I-cache misses, branchy code, instruction decode limits, poor code layout. |
| **Bad speculation** | Branch mispredictions, indirect calls, returns, overly speculative loads. |
| **Memory bound** | Cache misses, TLB misses, memory bandwidth saturation. |
| **Core bound** | Divider, serializing instructions, long dependency chains, port pressure. |
| **Retiring** | This is good — useful work is completing. |

You can get TMA-style output from tools like `toplev`, which is part of `pmu-tools`. It samples counters and walks the tree automatically.

```bash
# requires pmu-tools
./toplev.py -l1 -- ./your_program
```

Do not treat TMA as a magic answer. It is a classifier. It tells you whether the problem is in the front end, back end, speculation, or retirement, and then you still have to read the code and form a hypothesis.

> Top-down Microarchitecture Analysis (TMA) is a powerful diagnostic framework used by software engineers to figure out exactly why a program is running slowly on a CPU.
> Instead of guessing, TMA treats the CPU's processing capacity as a budget and tracks how every single ounce of that budget is spent.
> 
> ### The Core Concept: Pipeline Slots
> 
> To understand TMA, you must first understand a pipeline slot.
> Think of a CPU core like a train station. Every single clock cycle, a train pulls up to the platform.
>
> * If a CPU is 4-wide (like many Intel/AMD cores), the train has 4 seats (slots) per cycle.
> * If a CPU is 8-wide (like Apple M-series cores), the train has 8 seats (slots) per cycle.
> 
> In a perfect world, every single seat on every single train would be filled with a micro-operation (uop) that successfully completes its journey. TMA looks at the total number of available seats over time and categorizes them into four main buckets.

> ### The Four High-Level Buckets (Level 1)
> 
> If your program takes 1 billion clock cycles to run on a 4-wide CPU, you had 4 billion total pipeline slots available. TMA breaks down what happened to those 4 billion slots:
> 
> ### 1. Retiring (The "Good" Bucket)
>
> * What it means: A uop filled the slot, executed successfully, and its results were saved to memory.
> * The Goal: You want this number as high as possible. If a program is 70% Retiring, it is running highly efficiently.
>
> ### 2. Bad Speculation (The "Wasted Effort" Bucket)
>
> * What it means: The CPU frontend guessed which way a branch (an if/else statement) would go and filled pipeline slots with uops from that path. The guess turned out to be wrong.
> * The Result: The CPU has to slam on the brakes, throw away all the uops in those slots, and flush the pipeline. Those slots were completely wasted.
>
> ### 3. Front-End Bound (The "Starvation" Bucket)
>
> * What it means: The backend execution units were sitting ready, spinning their wheels, but the train arrived empty. The frontend (Fetch/Decode) failed to deliver uops to fill the slots.
> * Why it happens: Usually because the CPU couldn't find the next instruction in its fast L1 Instruction cache (I-cache miss), or it took too long to decode a messy, complex x86 instruction.
>
> ### 4. Back-End Bound (The "Traffic Jam" Bucket)
>
> * What it means: The frontend did its job perfectly and flooded the scheduler with uops, but the backend execution engine was completely clogged up. The slots remained empty because no new work could be accepted.
> 
> ### Drilling Deeper into the Backend: Memory vs. Core (Level 2)
> 
> When a program is Back-End Bound, TMA splits the problem into two distinct sub-categories to tell you exactly where the traffic jam is:
>
> Back-end bound
>     ├── Memory bound   → Stalls waiting for data to arrive from RAM/caches
>     └── Core bound     → Stalls because the execution units themselves are overwhelmed
>
> ### A. Memory Bound
> 
> The CPU is incredibly fast, but physics dictates that retrieving data from system RAM is painstakingly slow. If a uop needs data that isn’t in the processor, it stalls.
>
> * L1/L2/L3 Bound: The CPU had to wait a few cycles because the data wasn't in the ultra-fast L1 cache, forcing it to look deeper into the slower L2 or L3 caches.
> * DRAM Bound: The worst-case scenario. The data wasn't in any cache. The CPU had to go all the way out to main system memory (DRAM). To a CPU, waiting for DRAM feels like a human waiting days for a package in the mail.
>
> ### B. Core Bound
> The data is available, but the execution units themselves are bottlenecked.
>
> * Port Pressure: As you learned previously, if a loop requires four multiplication operations every cycle, but the CPU only has one multiplication port, uops will pile up fighting for that single entryway.
> * Dependency Chains: If Instruction B needs the result of Instruction A, and Instruction C needs the result of Instruction B, they cannot be executed out-of-order. The pipeline stalls waiting for the math to finish sequentially.
>
> ### Why Engineers Use TMA
> 
> Before TMA, if a program was slow, engineers would just look at general CPU usage (e.g., "CPU is at 100%"). However, a CPU can report 100% usage even when it is completely stalled waiting for memory.
> TMA changes the game. By running a tool like toplev, an engineer gets an exact diagnosis:
> 
> * If the tool reports 55% Memory Bound (DRAM) $\rightarrow$ The engineer stops optimizing the math algorithms and instead rewrites the code to make data structures smaller so they fit into the L3 cache.
> * If the tool reports 40% Bad Speculation $\rightarrow$ The engineer rewrites unpredictable if/else statements into predictable logic or flat math expressions.

> ### How does a tool like this work internally? 
>
> To understand how a tool like toplev or Intel VTune calculates these percentages internally, you have to look at the dedicated hardware hidden inside the CPU itself called the Performance Monitoring Unit (PMU).
> Tools don't actually sit inside the pipeline counting uops one by one in software—that would slow the CPU down to a crawl. Instead, the CPU hardware does the counting automatically, and the profiling tool simply reads the scores.
> Here is the step-by-step breakdown of how it works internally.
> 
> #### 1. The Hardware Level: Hardware Performance Counters
> 
> Inside the silicon of every modern core (Intel, AMD, and Apple Silicon), engineers build dozens of special registers called Performance Counters.
> Think of these as digital tripwires or turnstiles placed at critical bottlenecks in the pipeline. Every time a specific event happens in the hardware, the counter clicks up by 1. Examples of these hardware events include:
> 
> * CPU_CLK_UNHALTED: Total clock cycles spent working.
> * UOPS_RETIRED: Micro-ops that successfully completed.
> * BACLEARS: The frontend realized a branch prediction was wrong and cleared the pipeline.
> * MEM_LOAD_RETIRED.L3_MISS: A memory request had to go past the L3 cache out to DRAM.
>
>
> #### 2. Translating Counters into the TMA Tree (The Mathematical Formulas)
> 
> A single raw number (like "15 million L3 cache misses") doesn't tell you the whole story. The magic of a TMA tool is that it takes these raw counters and Plugs them into carefully engineered algebraic formulas provided by the CPU manufacturer (like Intel's official architecture optimization manuals).
> Let's look at how the tool calculates the top 4 buckets using these turnstile counts:
>
>* Retiring % = $\frac{\text{UOPS\_RETIRED}}{\text{Total Pipeline Slots}}$
(How many seats on the train actually finished the journey?)
>* Bad Speculation % = $\frac{\text{UOPS\_ISSUED} - \text{UOPS\_RETIRED} + (\text{Width} \times \text{BACLEARS})}{\text{Total Pipeline Slots}}$
> (How many uops were sent out but never finished, plus the slots lost while flushing the pipeline?)
> * Front-End Bound % = $\frac{\text{IDQ\_UOPS\_NOT\_DELIVERED.CORE}}{\text{Total Pipeline Slots}}$
> (A special counter tracking cycles where the instruction queue was empty, meaning the backend was starved.)
> * Back-End Bound % = 100% - (Retiring + Bad Speculation + Front-End Bound)
> (Whatever slots are left over must have been blocked by a clogged backend.)
>
> #### 3. Gathering the Data: Sampling vs. Counting Mode
> 
> How does the software tool get these numbers from the hardware? It can operate in two ways:
> 
> #### A. Counting Mode (Global View)
> 
> The tool tells the CPU: "Start counting when the program begins, and stop when it ends." At the very end, the tool reads the final register values, plugs them into the formulas, and prints out a single report card for the entire execution.
> 
> #### B. Sampling Mode (Line-by-Line View)
> If you want to know which exact line of code is causing the problem, the tool uses Interrupt-Based Sampling:
>
>   1. The tool programs a counter (e.g., BR_MISP_RETIRED for branch mispredictions) to trigger an alert every 10,000 counts.
>   2. When the counter hits 10,000, the PMU sends a hardware interrupt that freezes the processor for a split second.
>   3. The tool looks at the Instruction Pointer (IP) to see exactly what line of source code the CPU was executing at that exact millisecond.
>   4. It logs the location, resets the counter to zero, and lets the CPU continue. Over millions of cycles, a statistical map emerges showing exactly which lines of code are hot-spots for memory stalls or bad speculation.
>
> ### Summary of the Pipeline
>
> ```
> [CPU Hardware Events] 
>       │ (e.g., Cache miss, branch flush)
>       ▼
> [PMU Hardware Counters] ───► [Kernel Driver (perf)] ───► [TMA Tool (toplev)]
>  (Silicon registers click)     (Reads the registers)       (Applies math formulas
> ```                                                          & prints the tree)


## 10. A worked example: dependency chains in a reduction

Consider summing an array of floats. The naive version has a dependency chain:

```c
float sum = 0;
for (int i = 0; i < n; i++) {
    sum += a[i];
}
```

The loop body is one floating-point add per iteration, and each add depends on the previous `sum`. The CPU can overlap iterations of the loop control logic, but the actual floating-point adds must serialize. The throughput is bounded by the latency of the add instruction, not by how many add ports exist.

On a modern x86 core, a vector `vaddss` might have latency ~3-4 cycles. The loop cannot go faster than one element per 3-4 cycles.

Now split into four independent accumulators:

```c
float s0 = 0, s1 = 0, s2 = 0, s3 = 0;
for (int i = 0; i < n; i += 4) {
    s0 += a[i];
    s1 += a[i+1];
    s2 += a[i+2];
    s3 += a[i+3];
}
float sum = s0 + s1 + s2 + s3;
```

Now four adds can be in flight at once. The critical path is one add every 3-4 cycles, but four elements are processed in that time. Effective throughput rises toward four elements per 3-4 cycles, though memory bandwidth may become the next bottleneck.

```text
naive:    s0 += a[0]; s0 += a[1]; s0 += a[2]; s0 += a[3]; ...
          critical path length = n × add_latency

unrolled: s0 += a[0]; s1 += a[1]; s2 += a[2]; s3 += a[3]; ...
          critical path length = n/4 × add_latency
```

The compiler may apply this transformation automatically, but it cannot always prove that floating-point reassociation is safe. With `-ffast-math`, the compiler is allowed to reorder floating-point operations and may produce the unrolled version for you.

This example captures a recurring theme in performance engineering: **the shape of the data dependencies often matters more than the instruction count.**

## 11. Common patterns that waste CPU cycles

These patterns show up repeatedly in real code. Each one maps to a specific bottleneck category.

**Pointer chasing.** Linked lists, trees, hash tables with separate chaining, and graphs with scattered nodes produce dependent loads. The CPU cannot hide memory latency because each load reveals the address of the next load.

**Unpredictable branches.** `if` statements driven by random data cause branch mispredictions and pipeline flushes. Sorting the data or using branchless code is often faster.

**False sharing.** Threads write to different variables that share a cache line. The coherence protocol serializes what should be independent work.

**Long integer division.** Integer divide has much higher latency and lower throughput than add/mul/shift. Replacing division with multiplication by reciprocal or bit tricks often helps.

**Frequent system calls.** Each syscall is a mode switch. In a tight loop, even "cheap" syscalls dominate cost.

**Mixed hot/cold data.** If a struct contains frequently accessed fields and rarely accessed fields, and you iterate over an array of these structs, the rarely accessed fields waste cache lines. Splitting hot and cold data improves spatial locality.

## 12. What comes next

This note covered the CPU core. The next notes will build outward:

- **Memory and caches in depth:** cache mapping, prefetching, NUMA, TLB mechanics, huge pages, and how the Linux kernel manages the page tables.
- **The Linux kernel path:** how a syscall actually works, scheduler behavior, block IO, page cache, and how to measure kernel overhead.
- **Concurrency and synchronization:** atomics, memory ordering, locks, lock-free structures, and the cost of sharing state across cores.
- **Compiler interactions:** what the compiler can optimize, when it fails, and how to read the assembly it produces.
- **Rigorous benchmarking:** distributions, variance, timer precision, pinning, frequency control, and statistical methods.

Each of these depends on the model from this note: the CPU retires instructions as fast as it can, stalls when it cannot overlap work, and exposes those stalls through counters.

## 13. Questions to think about

1. A loop runs at one iteration per 4 cycles despite the loop body containing only a single-cycle integer add. You unroll the loop and use four independent accumulators. The throughput improves to nearly four iterations per 4 cycles. What exactly in the CPU architecture caused the original loop to be limited to one iteration per 4 cycles, and why did unrolling bypass it?

2. You compile two versions of a function. Version A has `instructions/cycles` (IPC) of 0.4. Version B has IPC of 2.8. Both produce the same correct result on the same input. Version A actually runs faster in wall-clock time. How is this possible, and what counter or TMA category would you look at first to understand it?

3. A tight loop has a branch inside it. With sorted input it runs 3x faster than with random input, even though the total number of executed instructions is the same. Explain the hardware mechanism behind the speedup and describe an alternative code transformation that might achieve a similar effect without sorting.

4. You issue two independent loads in the same cycle. One hits L1 and the other misses L3 and goes to DRAM. Can the CPU retire instructions that depend on the L1 hit while waiting for the DRAM miss? What hardware structure makes this possible, and what would prevent it from doing so indefinitely?

5. A function pointer is called in a loop. The targets alternate between two functions unpredictably. Throughput is much lower than calling either function alone. Which CPU structure is involved, and what code change would likely restore performance?

6. You observe `stall-cycles-frontend` is high while `instructions` is relatively low. The program is not I/O bound. List three different code-level causes that could produce this pattern, and for each give a `perf` counter you would check to confirm it.
