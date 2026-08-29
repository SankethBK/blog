---
title:  "CPU Pipelining"
date:   2026-08-19
categories: ["cpu"]
tags: ["cpu", "pipelining", "risc-v"]

---

# Pipelining — First Principles

## What is pipelining?

**Pipelining is the technique of overlapping the execution of multiple instructions.**

An instruction consists of multiple pieces of work. Instead of completing one instruction entirely before starting the next, we divide the work into **stages** and let different instructions occupy different stages simultaneously.

For a simple example:

```text
             IF    ID    EX    MEM    WB

Instruction 1  →    →     →     →      →
Instruction 2       →     →     →      →
Instruction 3             →     →      →
Instruction 4                   →      →
```

At any moment, several instructions are being worked on, but each is at a different stage.

This is similar to an assembly line: different cars are being worked on simultaneously, but at different stations.

---

## Why does pipelining improve performance?

The main benefit is **throughput**, not necessarily the latency of an individual instruction.

Suppose an instruction requires 5 stages:

```text
IF → ID → EX → MEM → WB
```

Without pipelining:

```text
I1: IF ID EX MEM WB
I2:              IF ID EX MEM WB
I3:                           ...
```

With pipelining:

```text
Cycle 1: I1 IF
Cycle 2: I1 ID   I2 IF
Cycle 3: I1 EX   I2 ID   I3 IF
Cycle 4: I1 MEM  I2 EX   I3 ID   I4 IF
Cycle 5: I1 WB   I2 MEM  I3 EX   I4 ID
...
```

Once the pipeline is full, an instruction can potentially **complete every cycle**.

So pipelining doesn't magically make each instruction's work smaller. It allows the processor to work on **multiple instructions at once**.

---

## Pipeline cycle ≠ instruction latency

This was initially confusing to me.

When the book says:

> "The processor cycle is almost always 1 clock cycle"

it means:

**The pipeline advances from one stage to the next on each clock cycle.**

It does **NOT** mean:

> Every operation takes one clock cycle.

For example:

```text
ADD       → may have short latency
DIV       → may take many cycles
L1 access → several cycles
DRAM      → potentially hundreds of cycles
```

Those operations can have multi-cycle latency even though the pipeline's basic timing interval is one clock cycle.

So keep these concepts separate:

```text
Clock cycle
    = basic timing tick / pipeline advancement

Operation latency
    = how long until that operation's result is available

Pipeline throughput
    = how frequently instructions can complete
```

---

## The slowest pipeline stage determines the clock

All pipeline stages advance together, so the clock period must be long enough for the **slowest stage**.

For example:

```text
IF   = 200 ps
ID   = 150 ps
EX   = 100 ps
MEM  = 300 ps  ← slowest
WB   = 100 ps
```

The pipeline can't advance every 100 ps because MEM needs 300 ps.

Therefore:

```text
Pipeline cycle ≈ 300 ps
```

This is why pipeline designers try to make the stages **balanced**.

### Assembly-line intuition

If four workers take:

```text
1 min
1 min
1 min
4 min
```

the whole assembly line can only move a car forward every 4 minutes.

The 1-minute workers don't help much because everyone has to move together.

---

## Ideal speedup

If the work can be divided into `N` perfectly balanced stages, the ideal throughput improvement approaches **N×**.

Example:

```text
Unpipelined:
20 ns/instruction

5-stage perfectly balanced pipeline:
20 / 5 = 4 ns per instruction
```

So the ideal speedup is:

```text
20 / 4 = 5×
```

This is an **ideal throughput speedup**.

Real processors get less because of:

* Unequal stage lengths
* Pipeline-register/clocking overhead
* Data dependencies
* Control hazards
* Stalls
* Cache misses
* Other resource conflicts

---

## CPI: another way to view pipelining

If an unpipelined processor takes multiple cycles per instruction, pipelining can reduce the **average CPI (cycles per instruction)**.

In an ideal pipeline:

```text
CPI ≈ 1
```

But this initially sounds misleading.

**CPI ≈ 1 does NOT mean every instruction takes one cycle.**

It means:

> Once the pipeline is full and assuming ideal conditions, the processor can complete roughly one instruction per cycle.

An individual instruction can still have a latency of several cycles.

For example, conceptually:

```text
Instruction A: ─────────────→ result
                 5 cycles

Instruction B:    ───────────→ result
                   5 cycles

Instruction C:      ─────────→ result
                     5 cycles
```

The individual instructions take several cycles, but their execution overlaps, allowing approximately one completion per cycle.

---

## What parallelism is being exploited?

The processor exploits **parallelism between instructions in a sequential instruction stream**.

The program may look sequential:

```text
I1 → I2 → I3 → I4 → I5
```

but the hardware overlaps their execution:

```text
I1: IF  ID  EX  MEM WB
I2:     IF  ID  EX  MEM WB
I3:         IF  ID  EX  MEM WB
I4:             IF  ID  EX  MEM WB
```

This is a form of **instruction-level parallelism (ILP)**.

## RISC Principes (From MIPS Notes)

MIPS is built on RISC principles, which embrace simplicity and efficiency, making it an ideal choice for learning about CPU architecture in general. Some principles of RISC are: 

1. **Simple Instructions:** RISC architectures use a small, highly optimized set of instructions. Each instruction is designed to be simple and execute in a single clock cycle (under ideal conditions in a pipelined processor).
2. **Load/Store Architecture:** RISC separates memory access and data processing instructions. Only load and store instructions can access memory, while all other operations are performed on registers. This simplifies the instruction set and execution.
3. **Fixed-Length Instructions:** Instructions in RISC architectures are of uniform length, typically 32 bits. This uniformity simplifies instruction decoding and pipeline design.
4. **Simple Addressing Modes:** RISC architectures use a small number of simple addressing modes to keep instruction execution fast and efficient. Common addressing modes include register, immediate, and displacement.
5. **Pipelining:** RISC architectures are designed to efficiently support pipelining. Instructions are broken down into stages (fetch, decode, execute, memory access, write-back) that can be processed simultaneously for different instructions.

Only difference is RISC-V is base instructions are 32-bit, but RISC-V also has optional 16-bit compressed instructions.

