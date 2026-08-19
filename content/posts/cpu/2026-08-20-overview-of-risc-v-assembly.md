---
layout: post_with_categories
title:  "Overview of RISC-V Assembly"
date:   2026-08-20
categories: ["cpu"]
tags: ["assembly", "risc-v"]

references:
- title: "RISC-V - Wikipedia"
  url: "https://en.wikipedia.org/wiki/RISC-V"

- title: "RISC-V Technical Specifications"
  url: "https://riscv.org/technical/specifications/"

- title: "RISC-V Instruction Set Manual"
  url: "https://github.com/riscv/riscv-isa-manual"

- title: "RISC-V ELF psABI (Calling Convention)"
  url: "https://github.com/riscv-non-isa/riscv-elf-psabi-doc"

---

RISC-V (pronounced "risk-five") is an open, royalty-free RISC ISA originally designed to support academic research and education, and now increasingly used in commercial silicon. Unlike MIPS, ARM, or x86, RISC-V is not owned by any single company — its specification is maintained by RISC-V International, and anyone is free to implement it without paying licensing fees. This openness, combined with a deliberately small and modular base ISA, has made it popular in everything from microcontrollers to research CPUs to (increasingly) high-performance application processors.

## History

RISC-V originated in 2010 at UC Berkeley, where a research group led by Krste Asanović, along with Yunsup Lee and Andrew Waterman, set out to design a clean, modern RISC ISA free of the legacy baggage and licensing restrictions of existing architectures. The name "V" refers to it being the fifth RISC ISA design out of Berkeley (following RISC-I through RISC-IV). The ISA specification was published openly in 2011, and RISC-V International (originally the RISC-V Foundation) was formed in 2015 to steward the standard going forward.

Because the base ISA is intentionally minimal and everything else is layered on top as optional extensions, RISC-V scales cleanly from tiny embedded microcontrollers (using just the base integer instructions) up to full application processors (adding multiply/divide, atomics, floating point, vector, and compressed-instruction extensions). This has led to rapid adoption: microcontrollers (e.g., ESP32-C3), storage controllers, academic and open-source cores (Rocket, BOOM, PicoRV32), and increasingly higher-performance commercial chips from vendors like SiFive.

RISC-V follows the same core RISC principles as MIPS — simple, fixed-width instructions; a load/store architecture where only load and store instructions touch memory; simple addressing modes; and a design that lends itself naturally to pipelining. Where RISC-V diverges most is in embracing modularity as a first-class design goal from the outset, rather than something bolted on later.

## RV32, RV64, and the Modular ISA

RISC-V isn't a single fixed instruction set — it's a base integer ISA plus a set of optional standard extensions that can be mixed and matched depending on what the target processor needs.

**Base integer ISAs:**
- **RV32I:** 32-bit base integer ISA, 32-bit registers and address space.
- **RV64I:** 64-bit base integer ISA, 64-bit registers and address space. Adds word-sized (32-bit) variants of arithmetic and shift instructions (suffixed `W`) for operating on the lower 32 bits.
- **RV128I:** A 128-bit variant exists in the spec for future-proofing but has no real-world implementations today.

Just like MIPS64 can run MIPS32 code unmodified, RV64I is a superset of RV32I's instruction encodings, so 32-bit RISC-V binaries can generally run unmodified reasoning on RV64 hardware, though the reverse isn't true.

**Standard extensions** (each identified by a single letter, appended to the base ISA name):

| Extension | Adds                                                                 |
| --------- | --------------------------------------------------------------------- |
| **M**     | Integer multiply and divide                                           |
| **A**     | Atomic memory operations (load-reserved/store-conditional, AMOs)      |
| **F**     | Single-precision floating point                                       |
| **D**     | Double-precision floating point                                       |
| **C**     | Compressed 16-bit instruction encodings for common operations         |
| **V**     | Vector operations                                                     |
| **Zicsr** | Control and Status Register instructions                              |
| **Zifencei** | Instruction-fetch fence (for self-modifying code / JIT support)    |

`RV32I` alone is a valid, complete ISA for a minimal embedded core. `RV64GC` (where `G` is shorthand for `IMAFD`, the "general-purpose" combination, plus `C` for compressed instructions) is the common configuration targeted by general-purpose operating systems like Linux. This is the sharpest contrast with MIPS: rather than shipping a handful of monolithic ISA revisions (MIPS I–V, MIPS32, MIPS64), RISC-V ships a tiny, stable base and lets implementers opt into exactly the capabilities they need.

## Registers

### General Purpose Registers

RISC-V has 32 general-purpose integer registers, `x0`–`x31`, each 32 bits wide on RV32 and 64 bits wide on RV64. If the F or D extension is present, there are an additional 32 floating-point registers, `f0`–`f31`, holding either single- or double-precision values.

As with MIPS, register roles beyond hardware-enforced behavior are purely a software (ABI) convention — the stack pointer, frame pointer, and argument registers are just regular registers that toolchains agree to use in a particular way. RISC-V goes a step further than MIPS in avoiding hardwired special-casing: the **only** register with hardware-defined behavior is `x0`, which is hardwired to the constant `0` (writes to it are discarded, reads always return `0`). Notably, RISC-V has **no** hardwired link register — `jal` and `jalr` take the destination register as an explicit operand, so any register can hold a return address, not just a fixed one (by convention, `x1`/`ra` is used).

| Register  | ABI Name  | Description                                                                 | Preserved Across Function Calls? |
| --------- | --------- | ---------------------------------------------------------------------------- | --------------------------------- |
| x0        | zero      | Hardwired to the constant 0. Writes to it are discarded.                     | N/A                                |
| x1        | ra        | Return address, implicitly written by `jal`/`jalr` when used as destination. | No (caller-saved)                 |
| x2        | sp        | Stack pointer.                                                               | Yes (callee-saved)                |
| x3        | gp        | Global pointer, used to access static data efficiently.                     | Unallocatable (fixed within a thread) |
| x4        | tp        | Thread pointer, points to thread-local storage.                             | Unallocatable (fixed within a thread) |
| x5-x7     | t0-t2     | Temporary registers.                                                        | No (caller-saved)                 |
| x8        | s0 / fp   | Saved register, or frame pointer by convention.                             | Yes (callee-saved)                |
| x9        | s1        | Saved register.                                                              | Yes (callee-saved)                |
| x10-x11   | a0-a1     | Function arguments / return values.                                         | No (caller-saved)                 |
| x12-x17   | a2-a7     | Function arguments.                                                          | No (caller-saved)                 |
| x18-x27   | s2-s11    | Saved registers.                                                             | Yes (callee-saved)                |
| x28-x31   | t3-t6     | Temporary registers.                                                        | No (caller-saved)                 |

One subtlety worth calling out: unlike the MIPS convention (where `$ra` is often listed as preserved across calls), the RISC-V ABI explicitly classifies `ra` as **caller-saved**. The callee is free to overwrite `ra` the moment it makes its own call via `jal`/`jalr`; it's the callee's job to spill `ra` onto the stack first if it is not a leaf function and needs to return correctly afterward. There's no hardware protection here — it's purely a software convention enforced by the compiler/assembler.

### Special Purpose Registers

- **Program Counter (PC):** Holds the address of the current instruction. It cannot be read or written by ordinary arithmetic instructions — only indirectly, via `auipc` (add upper immediate to PC, into a GPR), and via control-flow instructions (`jal`, `jalr`, branches) which update it directly.
- **Control and Status Registers (CSRs):** RISC-V has a large address space (12-bit, up to 4096) of CSRs used to configure and observe processor state — interrupt/exception handling, memory protection, performance counters, and privilege-mode state. They're accessed only through dedicated `Zicsr` instructions (`csrrw`, `csrrs`, `csrrc`, and their immediate variants), never through general-purpose load/store or arithmetic instructions. Notable CSRs include `mstatus` (machine status, holds interrupt-enable and privilege-mode bits), `mtvec` (trap-handler base address), `mepc` (exception program counter, saved PC at trap time), `mcause` (why a trap occurred), and `satp` (supervisor address translation and protection, used for paging).
- **Privilege Levels:** RISC-V defines Machine (M), Supervisor (S), and User (U) privilege modes. Every implementation supports M-mode; S and U modes are added as needed to support an OS with virtual memory and unprivileged user programs — analogous to the kernel/user mode distinction MIPS exposes via CP0's Status register.

Unlike MIPS, RISC-V has no `HI`/`LO` register pair for multiply/divide results. Instructions from the `M` extension write their result directly into any general-purpose register — a high-part and low-part multiply are simply two separate instructions (`mul` and `mulh`) rather than two halves of one implicit register pair.

## Data Types in RISC-V

1. **Byte (8-bit):** `.byte` — 8 bits.
2. **Halfword (16-bit):** `.half` (or `.hword`) — 16 bits / 2 bytes.
3. **Word (32-bit):** `.word` — 32 bits / 4 bytes.
4. **Doubleword (64-bit):** `.dword` — 64 bits / 8 bytes, natural on RV64.
5. **Float (32-bit floating-point):** `.float` — IEEE 754 single-precision, used with the F extension.
6. **Double (64-bit floating-point):** `.double` — IEEE 754 double-precision, used with the D extension.

## Addressing Modes in RISC-V

1. **Immediate Addressing:** The operand is a constant embedded in the instruction.
```asm
addi t0, t1, 5   # t0 = t1 + 5
```

2. **Register Direct Addressing:** The operand is held in a register.
```asm
add t0, t1, t2   # t0 = t1 + t2
```

3. **Base + Displacement Addressing:** The effective memory address is a base register plus a signed immediate offset. Used for all loads and stores.
```asm
lw t0, 8(t1)     # t0 = MEM[t1 + 8]
```

4. **PC-Relative Addressing:** The target address is the current PC plus a signed immediate. Used for branches and `jal`.
```asm
beq t0, t1, label   # branch to label (PC + offset) if t0 == t1
```

5. **No absolute/pseudo-direct addressing:** This is a deliberate departure from MIPS. MIPS's `j`/`jal` encode an absolute (pseudo-direct) target by combining bits from the instruction with the upper bits of the PC. RISC-V dropped this entirely — `jal` only encodes a PC-relative offset (±1MiB, since its immediate is 21 bits including the implicit trailing zero), and reaching anywhere in a full address space requires `auipc` (load PC + upper 20-bit immediate into a register) followed by `jalr` (jump to register + 12-bit immediate offset). This two-instruction sequence gives unlimited reach without ever needing an absolute address embedded in a single instruction, sidestepping the "jump range" problem MIPS runs into with its 256MB-limited `j` instruction.
```asm
auipc t0, %pcrel_hi(far_label)
jalr  ra, %pcrel_lo(far_label)(t0)
```

## Memory Alignment and Endianness

Alignment rules are essentially the same as MIPS: a 2-byte halfword should sit on a 2-byte boundary, a 4-byte word on a 4-byte boundary, and an 8-byte doubleword on an 8-byte boundary. Where RISC-V differs is in how strictly this is enforced — the spec explicitly allows implementations to either support misaligned accesses directly in hardware (at some performance cost) or trap into software emulation, and a given core may not support misaligned accesses at all. This is implementation-defined behavior rather than a single guaranteed exception-on-misalignment rule as in classic MIPS.

**Endianness:** The base RISC-V specification technically permits either byte order, but in practice essentially every RISC-V implementation you'll encounter — and every major software distribution (e.g., Linux on RISC-V) — uses **little-endian** ordering. This is unlike MIPS, which ships in both big-endian and little-endian variants roughly equally often, with a Status register bit to switch modes at runtime on bi-endian cores. RISC-V doesn't define an equivalent runtime-switchable bit; endianness is fixed per implementation.

## Instruction Formats in RISC-V

RISC-V's base ISA uses six instruction formats, all a uniform 32 bits wide (the optional `C` extension adds 16-bit compressed encodings on top, discussed below). Compared to MIPS's three formats (R/I/J), RISC-V has more formats, but a much stronger regularity guarantee: in every format, `rs1`, `rs2`, `rd`, and `opcode` sit at the **exact same bit positions**. A CPU can start reading `rs1`/`rs2` out of the register file before it has even determined which format the instruction is, since those fields never move.

### 1. R-type — register-register operations

| 31-25  | 24-20 | 19-15 | 14-12  | 11-7 | 6-0    |
| ------ | ----- | ----- | ------ | ---- | ------ |
| funct7 | rs2   | rs1   | funct3 | rd   | opcode |

Eg: `add t1, t2, t3`

### 2. I-type — immediate arithmetic, loads, `jalr`

| 31-20      | 19-15 | 14-12  | 11-7 | 6-0    |
| ---------- | ----- | ------ | ---- | ------ |
| imm[11:0]  | rs1   | funct3 | rd   | opcode |

Eg:
```asm
addi t1, t2, 10    # t1 = t2 + 10
lw   t0, 4(t1)     # t0 = Memory[t1 + 4]
andi t0, t1, 0xFF  # t0 = t1 & 0xFF
```

### 3. S-type — stores

Stores need to read *two* registers (the value and the base address) but write no destination register, so the format swaps `rd` for the low bits of the immediate:

| 31-25      | 24-20 | 19-15 | 14-12  | 11-7      | 6-0    |
| ---------- | ----- | ----- | ------ | --------- | ------ |
| imm[11:5]  | rs2   | rs1   | funct3 | imm[4:0]  | opcode |

Eg: `sw t0, 4(t1)   # Memory[t1 + 4] = t0`

### 4. B-type — conditional branches

Structurally a variant of S-type, but the immediate bits are reordered so the sign bit always lands in bit 31 and the encoded value is always even (the least-significant bit is implicit and always 0, since branch targets are 2-byte aligned):

| 31       | 30-25      | 24-20 | 19-15 | 14-12  | 11-8      | 7        | 6-0    |
| -------- | ---------- | ----- | ----- | ------ | --------- | -------- | ------ |
| imm[12]  | imm[10:5]  | rs2   | rs1   | funct3 | imm[4:1]  | imm[11]  | opcode |

Eg: `beq t0, t1, label`

### 5. U-type — 20-bit upper immediates (`lui`, `auipc`)

| 31-12       | 11-7 | 6-0    |
| ----------- | ---- | ------ |
| imm[31:12]  | rd   | opcode |

Eg: `lui t0, 0x12345   # t0 = 0x12345000`

### 6. J-type — unconditional jumps (`jal`)

A variant of U-type with the same "scrambled bits, sign always at 31, LSB implicit" trick as B-type, giving a ±1MiB PC-relative range:

| 31        | 30-21      | 20        | 19-12      | 11-7 | 6-0    |
| --------- | ---------- | --------- | ---------- | ---- | ------ |
| imm[20]   | imm[10:1]  | imm[11]   | imm[19:12] | rd   | opcode |

Eg: `jal ra, label`

The immediate-bit scrambling in B-type and J-type looks odd at first, but it's a deliberate hardware tradeoff: by keeping the sign bit pinned to bit 31 in *every* format, a single sign-extension circuit works for all instruction types, at the cost of slightly more complex immediate-assembly logic (the decoder has to reassemble the bits into order, rather than just slicing out a contiguous field).

### The C extension: compressed instructions

The `C` extension defines 16-bit encodings for the most frequently used instructions (register moves, small immediates, common loads/stores/branches involving the most popular registers). A `C`-enabled core mixes 16-bit and 32-bit instructions in the same stream, decoding a 16-bit unit first to determine whether it needs another 16 bits to complete a 32-bit instruction. This directly targets the "low code density" weakness that a rigid 32-bit-only encoding has (the same weakness MIPS's uniform-width design suffers from) — in exchange, it reintroduces the variable-length-decode complexity that a fixed-width ISA is otherwise designed to avoid.

## Pros and Cons of RISC-V's Instruction Encoding

### Pros

1. **Extremely regular register field placement:** `rs1`, `rs2`, and `rd` sit at the same bit offsets across every format (barring formats that omit one of them). This is a stronger guarantee than MIPS provides, since the CPU never has to wait on opcode decode to know where to find register operands.

2. **No hidden/implicit operands beyond `x0`:** MIPS's `jal` always writes to `$ra` implicitly. RISC-V's `jal`/`jalr` take the link register as an explicit destination operand — using `ra` is just a convention, not a hardware requirement. This makes the ISA more orthogonal: the same instruction can be used for a normal call (`jal ra, foo`), a call that doesn't need to return (`jal zero, foo`, i.e. a plain jump), or a lightweight call using a scratch register when `ra` must be preserved.

3. **No absolute-address jump limitation:** Since RISC-V never encodes an absolute jump target, it never runs into MIPS's 256MB pseudo-direct addressing ceiling. Far jumps are handled uniformly via `auipc` + `jalr`, at the cost of needing two instructions instead of one.

4. **Modularity keeps the base ISA tiny:** A minimal RV32I implementation needs to decode far fewer instructions than a full MIPS32 core, which is useful for tiny microcontrollers — while `RV64GC` still gets you everything a general-purpose OS needs.

### Cons

1. **Small immediates, same two-instruction workaround as MIPS:** I-type immediates are only 12 bits (vs MIPS's 16), so loading a large constant still takes two instructions: `lui` for the upper 20 bits, then `addi` for the lower 12. There's an extra subtlety here that MIPS's `lui`+`ori` doesn't have: because `addi`'s immediate is **sign-extended**, if the lower 12 bits have their sign bit set, adding them will subtract from the upper value. Assemblers compensate automatically by adding 1 to the upper 20-bit immediate loaded via `lui` whenever this would happen — a detail that has to be handled correctly by every assembler/compiler backend.

2. **Compressed instructions reintroduce variable length:** The `C` extension trades away one of the base ISA's central simplicities (fixed-width, easy-to-pipeline fetch) to fix code density, meaning a `C`-capable fetch unit is meaningfully more complex than a pure RV32I/RV64I one.

3. **Limited opcode space, same as any fixed-width ISA:** The base opcode field is only 7 bits, with most of the encoding space further subdivided by `funct3`/`funct7`. Extensions have to carefully carve out unused opcode/funct combinations, which is why RISC-V invests heavily in a formal extension-naming and encoding-reservation process.

4. **Two-instruction far jumps:** The flip side of "no absolute jump" is that every far call or jump costs two instructions (`auipc` + `jalr`) instead of MIPS's single (if range-limited) `j`/`jal`.

## Extensions in RISC-V

RISC-V has no coprocessor concept in the MIPS sense (there's no `CP0`/`CP1`/`MFC0`/`MTC1`-style separate coprocessor register space reached through dedicated move instructions). Instead, additional functionality is folded directly into the main instruction encoding space as **standard extensions**, each occupying reserved opcode/funct patterns:

1. **M — Integer Multiply/Divide:** Adds `mul`, `mulh`, `mulhu`, `mulhsu`, `div`, `divu`, `rem`, `remu`. Unlike MIPS's `mult`/`div`, which write into an implicit `HI:LO` pair, every RISC-V M-extension instruction writes its single result straight into an ordinary GPR.

2. **A — Atomics:** Adds load-reserved/store-conditional (`lr.w`/`sc.w`, and `.d` variants on RV64) plus a family of atomic memory operations (`amoadd`, `amoswap`, `amoor`, `amoand`, `amoxor`, `amomax`, `amomin`, ...) used to build lock-free data structures and synchronization primitives without OS-level locking.

3. **F / D — Floating Point:** F adds single-precision, D adds double-precision floating-point arithmetic, using a separate bank of 32 floating-point registers `f0`–`f31` — conceptually similar to MIPS's CP1, just without being labeled a "coprocessor." Floating-point comparisons write a `0`/`1` result directly into a general-purpose register rather than setting a hidden condition-code bit the way MIPS's FCSR comparison bit does, so a normal integer branch (`beq`/`bne` against `x0`) is used afterward.

4. **C — Compressed:** 16-bit encodings for common instructions, described above.

5. **V — Vector:** Adds SIMD-style vector registers and operations for data-parallel workloads, with a variable vector length model rather than fixed-width SIMD registers.

6. **Zicsr / Zifencei:** Small extensions adding CSR access instructions and instruction-fetch fences (needed for correctness when code is modified at runtime, e.g., JIT compilers).

## Overview of RISC-V Instructions

### 1. Memory Access Instructions

All loads and stores use base+displacement addressing exclusively — there's no other way to touch memory in RISC-V, consistent with the RISC load/store philosophy.

#### Load Family

All loads are I-type:
```asm
LOAD rd, offset(rs1)
```
- **LOAD** is the specific load opcode (LB, LBU, LH, LHU, LW, LWU, LD, FLW, FLD).
- **rd** is the destination register.
- **offset** is a 12-bit signed immediate.
- **rs1** is the base register.

| Instruction | Meaning                       | Description                                                        |
| ----------- | ----------------------------- | -------------------------------------------------------------------- |
| **lb**      | Load Byte                     | Loads a byte, sign-extended.                                         |
| **lbu**     | Load Byte Unsigned            | Loads a byte, zero-extended.                                         |
| **lh**      | Load Halfword                 | Loads a halfword, sign-extended.                                     |
| **lhu**     | Load Halfword Unsigned        | Loads a halfword, zero-extended.                                     |
| **lw**      | Load Word                     | Loads a word, sign-extended on RV64.                                 |
| **lwu**     | Load Word Unsigned            | Loads a word, zero-extended (RV64 only).                              |
| **ld**      | Load Doubleword                | Loads a doubleword (RV64 only).                                       |
| **flw**     | Load Single-Precision Float   | Loads a 32-bit float into an `f` register (F extension).             |
| **fld**     | Load Double-Precision Float   | Loads a 64-bit double into an `f` register (D extension).            |

#### Store Family

All stores are S-type:
```asm
STORE rs2, offset(rs1)
```
- **STORE** is the specific store opcode (SB, SH, SW, SD, FSW, FSD).
- **rs2** is the source register holding the value to store.
- **offset** is a 12-bit signed immediate.
- **rs1** is the base register.

| Instruction | Meaning                        | Description                                       |
| ----------- | ------------------------------- | ---------------------------------------------------- |
| **sb**      | Store Byte                      | Stores the low byte of `rs2`.                         |
| **sh**      | Store Halfword                   | Stores the low halfword of `rs2`.                     |
| **sw**      | Store Word                       | Stores the low word of `rs2`.                         |
| **sd**      | Store Doubleword                  | Stores a doubleword (RV64 only).                      |
| **fsw**     | Store Single-Precision Float     | Stores a 32-bit float from an `f` register.           |
| **fsd**     | Store Double-Precision Float     | Stores a 64-bit double from an `f` register.          |

#### Register / CSR / FP Data Transfers

Since multiply/divide results land directly in a GPR, RISC-V has no `MFHI`/`MFLO`-style transfer instructions. The transfer instructions that remain move data between the integer and floating-point register files, or to/from CSRs:

- **fmv.x.w / fmv.w.x:** Move raw bits between an `f` register and a GPR (single-precision).
```asm
fmv.x.w t0, f1   # t0 = raw bits of f1
```

- **fmv.x.d / fmv.d.x:** Same, for double-precision (RV64 only for the `.x` direction without a 32-bit split).

- **csrrw rd, csr, rs1:** Atomically swaps a CSR's value with `rs1`, writing the old CSR value into `rd`.
```asm
csrrw t0, mstatus, t1   # t0 = old mstatus; mstatus = t1
```

- **csrrs / csrrc:** Atomically set/clear bits in a CSR using `rs1` as a bitmask, returning the old value.

### 2. Arithmetic Instructions (Integers)

Register-register arithmetic is R-type:
```asm
ARITHMETIC rd, rs1, rs2
```
Immediate arithmetic is I-type:
```asm
ARITHMETIC_IMM rd, rs1, imm
```

A key divergence from MIPS: RISC-V has **no overflow-trapping arithmetic at all**. There's no `add`/`addu`-style distinction — `add` always wraps silently on overflow, full stop. If a program needs to detect overflow, it has to check for it explicitly with additional instructions; the hardware never raises an exception on its own.

| Instruction | Syntax                  | Description                                                                 | Example                                  |
| ----------- | ------------------------ | ------------------------------------------------------------------------------ | ------------------------------------------- |
| **add**     | `add rd, rs1, rs2`       | `rd = rs1 + rs2`. Always wraps silently on overflow.                          | `add t0, t1, t2  # t0 = t1 + t2`             |
| **addi**    | `addi rd, rs1, imm`      | `rd = rs1 + imm` (12-bit signed immediate).                                    | `addi t0, t1, 10 # t0 = t1 + 10`             |
| **sub**     | `sub rd, rs1, rs2`       | `rd = rs1 - rs2`.                                                             | `sub t0, t1, t2  # t0 = t1 - t2`             |
| **mul**     | `mul rd, rs1, rs2`       | `rd` = lower bits of `rs1 * rs2` (M extension).                                | `mul t0, t1, t2`                            |
| **mulh**    | `mulh rd, rs1, rs2`      | `rd` = upper bits of signed `rs1 * rs2` (M extension).                        | `mulh t0, t1, t2`                           |
| **mulhu**   | `mulhu rd, rs1, rs2`     | `rd` = upper bits of unsigned `rs1 * rs2` (M extension).                      | `mulhu t0, t1, t2`                          |
| **div**     | `div rd, rs1, rs2`       | `rd = rs1 / rs2` (signed, M extension).                                       | `div t0, t1, t2`                            |
| **divu**    | `divu rd, rs1, rs2`      | `rd = rs1 / rs2` (unsigned, M extension).                                     | `divu t0, t1, t2`                           |
| **rem**     | `rem rd, rs1, rs2`       | `rd = rs1 % rs2` (signed, M extension).                                       | `rem t0, t1, t2`                            |
| **remu**    | `remu rd, rs1, rs2`      | `rd = rs1 % rs2` (unsigned, M extension).                                     | `remu t0, t1, t2`                           |

On RV64, each of these has a `w`-suffixed variant (`addw`, `subw`, `mulw`, `divw`, `divuw`, `remw`, `remuw`) that operates on the lower 32 bits of its operands and sign-extends the 32-bit result into the full 64-bit destination register.

### 3. Logical Instructions

R-type register-register form:
```asm
LOGICAL rd, rs1, rs2
```
I-type immediate form:
```asm
LOGICAL_IMM rd, rs1, imm
```

| Instruction | Meaning                | Description                                                                 |
| ----------- | ----------------------- | ------------------------------------------------------------------------------ |
| **and**     | Bitwise AND              | `rd = rs1 & rs2`.                                                             |
| **or**      | Bitwise OR               | `rd = rs1 \| rs2`.                                                            |
| **xor**     | Bitwise XOR              | `rd = rs1 ^ rs2`.                                                             |
| **andi**    | Bitwise AND Immediate    | `rd = rs1 & imm`.                                                             |
| **ori**     | Bitwise OR Immediate     | `rd = rs1 \| imm`.                                                            |
| **xori**    | Bitwise XOR Immediate    | `rd = rs1 ^ imm`. `xori rd, rs1, -1` is also how bitwise NOT is synthesized.  |

Note there's no `nor` instruction in RISC-V, unlike MIPS.

### 4. Shift Instructions

Unlike MIPS, which uses separate mnemonics for immediate vs. register-specified shift amounts (`sll` vs `sllv`), RISC-V just uses the format to distinguish them — the same base mnemonic covers both.

Register-specified shift amount (R-type, low 5 bits of `rs2` used on RV32, low 6 on RV64):
```asm
SHIFT rd, rs1, rs2
```
Immediate shift amount (I-type, `shamt` encoded directly in the instruction):
```asm
SHIFT rd, rs1, shamt
```

| Instruction | Syntax                 | Description                                                                                                     | Example                            |
| ----------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------ | -------------------------------------- |
| **sll**     | `sll rd, rs1, rs2`       | Logical left shift of `rs1` by the amount in `rs2`.                                                                | `sll t0, t1, t2  # t0 = t1 << t2`       |
| **srl**     | `srl rd, rs1, rs2`       | Logical right shift (zero-fill).                                                                                  | `srl t0, t1, t2  # t0 = t1 >> t2`       |
| **sra**     | `sra rd, rs1, rs2`       | Arithmetic right shift (sign-preserving).                                                                          | `sra t0, t1, t2  # t0 = t1 >> t2`       |
| **slli**    | `slli rd, rs1, shamt`    | Logical left shift by an immediate amount.                                                                        | `slli t0, t1, 2  # t0 = t1 << 2`        |
| **srli**    | `srli rd, rs1, shamt`    | Logical right shift by an immediate amount.                                                                       | `srli t0, t1, 2  # t0 = t1 >> 2`        |
| **srai**    | `srai rd, rs1, shamt`    | Arithmetic right shift by an immediate amount.                                                                    | `srai t0, t1, 2  # t0 = t1 >> 2`        |

The same intuition from MIPS carries over directly: a logical left shift by `n` multiplies by 2ⁿ, a logical right shift divides by 2ⁿ for unsigned values, and arithmetic right shift is needed to divide signed (two's complement) negative values correctly, since it replicates the sign bit into the vacated high bits instead of filling with zero.

### 5. Comparison Instructions

R-type:
```asm
COMPARISON rd, rs1, rs2
```
I-type:
```asm
COMPARISON_IMM rd, rs1, imm
```

| Instruction | Syntax                    | Description                                                        | Example                            |
| ----------- | --------------------------- | ---------------------------------------------------------------------- | --------------------------------------- |
| **slt**     | `slt rd, rs1, rs2`           | `rd = 1` if `rs1 < rs2` (signed), else `0`.                          | `slt t0, t1, t2  # t0 = t1 < t2`         |
| **sltu**    | `sltu rd, rs1, rs2`          | `rd = 1` if `rs1 < rs2` (unsigned), else `0`.                        | `sltu t0, t1, t2 # t0 = t1 < t2`         |
| **slti**    | `slti rd, rs1, imm`          | `rd = 1` if `rs1 < imm` (signed), else `0`.                          | `slti t0, t1, 10 # t0 = t1 < 10`         |
| **sltiu**   | `sltiu rd, rs1, imm`         | `rd = 1` if `rs1 < imm` (unsigned), else `0`.                        | `sltiu t0, t1, 10`                      |

### 6. Control Instructions

Branches are B-type and, unlike MIPS, compare two registers with a rich set of conditions directly — there's no need to synthesize "branch if greater than" out of a `slt` + `bne` pair, since `blt`/`bge` exist natively:

```asm
BRANCH rs1, rs2, offset
```

| Instruction | Syntax                     | Description                                                        | Example              |
| ----------- | ---------------------------- | ---------------------------------------------------------------------- | ------------------------ |
| **beq**     | `beq rs1, rs2, offset`        | Branch if `rs1 == rs2`.                                               | `beq t0, t1, label`      |
| **bne**     | `bne rs1, rs2, offset`        | Branch if `rs1 != rs2`.                                               | `bne t0, t1, label`      |
| **blt**     | `blt rs1, rs2, offset`        | Branch if `rs1 < rs2` (signed).                                       | `blt t0, t1, label`      |
| **bge**     | `bge rs1, rs2, offset`        | Branch if `rs1 >= rs2` (signed).                                      | `bge t0, t1, label`      |
| **bltu**    | `bltu rs1, rs2, offset`       | Branch if `rs1 < rs2` (unsigned).                                     | `bltu t0, t1, label`     |
| **bgeu**    | `bgeu rs1, rs2, offset`       | Branch if `rs1 >= rs2` (unsigned).                                    | `bgeu t0, t1, label`     |

Jumps are handled by two instructions:

| Instruction | Syntax                  | Description                                                                                        | Example               |
| ----------- | ------------------------ | ------------------------------------------------------------------------------------------------------- | ------------------------- |
| **jal**     | `jal rd, offset`         | Jump to `PC + offset` (±1MiB, J-type), saving `PC + 4` into `rd`.                                       | `jal ra, label`           |
| **jalr**    | `jalr rd, rs1, offset`   | Jump to `rs1 + offset` (I-type), saving `PC + 4` into `rd`. Used for register-indirect jumps and returns. | `jalr ra, t0, 0`          |

Plain unconditional jumps and returns are pseudo-instructions built from these: `j label` is `jal x0, label` (no return address saved), and `ret` is `jalr x0, ra, 0` (jump to the address in `ra`, discard the new "return address" since `x0` swallows writes).

For floating-point comparisons, there's no hidden condition-code bit like MIPS's FCSR comparison flag — `feq.s`/`flt.s`/`fle.s` write a plain `0`/`1` straight into a GPR, which is then tested with an ordinary integer branch:
```asm
flt.s t0, f1, f2     # t0 = (f1 < f2) ? 1 : 0
bne   t0, zero, label # branch if f1 < f2
```

Traps and privilege transitions:

| Instruction | Description                                                                                                                                                                     |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **ecall**   | Triggers an environment call — a trap to the next-higher privilege level, used for system calls into the OS or the machine-mode firmware, analogous to MIPS's `trap`.          |
| **ebreak**  | Triggers a breakpoint trap, typically used by debuggers.                                                                                                                        |
| **mret**    | Returns from a trap taken in machine mode, restoring `PC` from `mepc` and privilege/interrupt state from `mstatus`.                                                             |
| **sret**    | Same as `mret`, but for a trap taken in supervisor mode (restores from `sepc`).                                                                                                 |

There's no single `eret` mnemonic as in MIPS — the return-from-trap instruction is specific to the privilege level being returned from, since each level has its own exception-PC and status CSRs.

### 7. Floating-Point Instructions (F/D extensions)

| Instruction Group   | Syntax                          | Description                                                                                     | Example                 |
| -------------------- | -------------------------------- | ----------------------------------------------------------------------------------------------------- | --------------------------- |
| **Addition**         | `fadd.[s/d] fd, fs1, fs2`         | `fd = fs1 + fs2`. `s` for single, `d` for double precision.                                            | `fadd.d f0, f1, f2`         |
| **Subtraction**      | `fsub.[s/d] fd, fs1, fs2`         | `fd = fs1 - fs2`.                                                                                       | `fsub.s f0, f1, f2`         |
| **Multiplication**   | `fmul.[s/d] fd, fs1, fs2`         | `fd = fs1 * fs2`.                                                                                       | `fmul.d f0, f1, f2`         |
| **Division**         | `fdiv.[s/d] fd, fs1, fs2`         | `fd = fs1 / fs2`.                                                                                       | `fdiv.s f0, f1, f2`         |
| **Fused Multiply-Add** | `fmadd.[s/d] fd, fs1, fs2, fs3` | `fd = (fs1 * fs2) + fs3`, computed with a single rounding step (more accurate than separate mul + add). | `fmadd.d f0, f1, f2, f3`    |
| **Square Root**      | `fsqrt.[s/d] fd, fs1`             | `fd = sqrt(fs1)`.                                                                                       | `fsqrt.s f0, f1`            |
| **Conversion**       | `fcvt.x.y rd/fd, fs1/rs1`         | Converts between formats `x` and `y` (`w`, `l`, `s`, `d`).                                              | `fcvt.d.s f0, f1`           |
| **Comparison**       | `f{eq,lt,le}.[s/d] rd, fs1, fs2`  | Compares `fs1` and `fs2`, writing `1`/`0` directly into integer register `rd`.                          | `feq.s t0, f1, f2`          |

## Pseudo-Instructions in RISC-V

Like MIPS, several commonly used RISC-V "instructions" are really assembler-expanded pseudo-instructions, translated into one or more real instructions at assembly time.

| Pseudo-Instruction      | Description                                              | Actual Instruction(s)                                                                  |
| ------------------------ | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `mv rd, rs`              | Copy `rs` into `rd`.                                       | `addi rd, rs, 0`                                                                            |
| `li rd, imm`             | Load an immediate into `rd`.                               | Small imm: `addi rd, zero, imm`. Large imm: `lui rd, upper(imm)` + `addi rd, rd, lower(imm)` |
| `la rd, symbol`          | Load the address of `symbol` into `rd`.                    | `auipc rd, %pcrel_hi(symbol)` + `addi rd, rd, %pcrel_lo(symbol)`                            |
| `nop`                    | No operation.                                              | `addi zero, zero, 0`                                                                        |
| `j label`                | Unconditional jump, no return address saved.               | `jal zero, label`                                                                            |
| `jr rs`                  | Unconditional jump to the address in `rs`.                 | `jalr zero, rs, 0`                                                                           |
| `ret`                    | Return from a function.                                     | `jalr zero, ra, 0`                                                                           |
| `call label`             | Call a (possibly far) function, saving the return address. | `auipc ra, %pcrel_hi(label)` + `jalr ra, ra, %pcrel_lo(label)`                               |
| `beqz rs, label`         | Branch if `rs == 0`.                                       | `beq rs, zero, label`                                                                        |
| `bnez rs, label`         | Branch if `rs != 0`.                                       | `bne rs, zero, label`                                                                        |
| `bgt rs1, rs2, label`    | Branch if `rs1 > rs2`.                                     | `blt rs2, rs1, label` (operands swapped)                                                    |
| `ble rs1, rs2, label`    | Branch if `rs1 <= rs2`.                                    | `bge rs2, rs1, label` (operands swapped)                                                    |
| `seqz rd, rs`            | `rd = 1` if `rs == 0`, else `0`.                           | `sltiu rd, rs, 1`                                                                            |
| `snez rd, rs`            | `rd = 1` if `rs != 0`, else `0`.                           | `sltu rd, zero, rs`                                                                          |
| `neg rd, rs`             | `rd = -rs`.                                                | `sub rd, zero, rs`                                                                           |
| `not rd, rs`             | `rd = ~rs` (bitwise NOT).                                  | `xori rd, rs, -1`                                                                            |

A notable simplification compared to MIPS: RISC-V has no reserved "assembler temporary" register equivalent to `$at`. Most pseudo-instruction expansions above don't need a scratch register at all — `li`/`la` simply reuse the destination register itself across both expanded instructions (load the upper bits into `rd`, then add the lower bits into the same `rd`). And since `blt`/`bge` exist as real instructions, pseudo-branches like `bgt`/`ble` are expanded by just swapping the two register operands, rather than needing an intermediate `slt` result stashed in a temp register the way MIPS's `bgt`/`ble` expansion does.

## Directives in RISC-V

RISC-V assemblers (notably the GNU `riscv64-unknown-elf-as`/`riscv64-linux-gnu-as` toolchains) use largely the same directive set as MIPS, since both ultimately build on the GNU assembler's common directive vocabulary:

- **`.text` / `.data` / `.bss`:** Introduce the code, initialized-data, and uninitialized-data sections respectively.
- **`.byte` / `.half` / `.word` / `.dword`:** Assemble 8-, 16-, 32-, and 64-bit integer values into the current section.
- **`.float` / `.double`:** Assemble IEEE 754 single- and double-precision floating-point values.
- **`.ascii` / `.asciiz` (or `.string`):** Assemble a string without or with a trailing null terminator.
- **`.space` / `.zero`:** Reserve a block of uninitialized (zero-filled) memory.
- **`.align n`:** Align the next value in the current section to a `2ⁿ`-byte boundary.
- **`.globl symbol`:** Make `symbol` visible to the linker for use across object files.
- **`.equ name, value`:** Define an assembler constant, similar to a `#define`.

```asm
.data
val1: .word 0x12345678

.text
.globl main
main:
    la   t0, val1
    lw   t1, 0(t0)
    li   a7, 93       # exit syscall number
    ecall
```
