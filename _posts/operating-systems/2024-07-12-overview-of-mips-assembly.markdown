---
layout: post_with_categories
title:  "Overview of MIPS Assembly"
date:   2024-07-12 20:38:05 +0530
categories: cpu assembly
author: Sanketh
references: 
   - https://en.wikipedia.org/wiki/MIPS_architecture
   - https://mathcs.holycross.edu/~csci226/MIPS/summaryHO.pdf
   - https://profile.iiita.ac.in/bibhas.ghoshal/COA_2021/lecture_slides/MIPS_Programming.pdf
   - https://ablconnect.harvard.edu/files/ablconnect/files/mips_instruction_set.pdf
   - https://www.comp.nus.edu.sg/~adi-yoga/CS2100/ch08/
   - https://en.wikibooks.org/wiki/MIPS_Assembly/Instruction_Formats
   - https://stackoverflow.com/questions/48509093/using-different-registers-in-mips
   - https://stackoverflow.com/questions/18024672/what-registers-are-preserved-through-a-linux-x86-64-function-call
   - https://stackoverflow.com/questions/9609721/how-far-can-the-jjump-instruction-jump-in-memory-mips
   - https://electronics.stackexchange.com/questions/162976/range-of-mips-j-instruction
   - https://stackoverflow.com/questions/6950230/how-to-calculate-jump-target-address-and-branch-target-address
   - https://stackoverflow.com/questions/44694957/the-difference-between-logical-shift-right-arithmetic-shift-right-and-rotate-r
---

MIPS (Microprocessor without Interlocked Pipeline Stages) assembly is one of the RISC ISA's. It was developed in the early 1980s at Stanford University by Professor John L. Hennessy. MIPS is widely used in academic research and industry, particularly in computer architecture courses due to its straightforward design and in various embedded systems applications for its efficiency and performance.

## History

The first MIPS processor, the R2000, was introduced. It implemented the MIPS I architecture, which was one of the earliest commercial RISC processors. There are multiple versions of MIPS: including MIPS I, II, III, IV, and V; as well as five releases of MIPS32/64. MIPS I had 32-bit architecture with basic instruction set and addressing modes. MIPS III introduced 64-bit architecture in 1991, increasing the address space and register width.

MIPS32 and MIPS64 are modern versions of the architecture, maintaining backward compatibility while introducing enhancements for modern computing needs. MicroMIPS is a compact version of the MIPS instruction set, designed for embedded systems with limited memory. MIPS processors are commonly used in embedded systems, such as routers, printers, and smart home devices, where their efficiency and performance are crucial. In the automotive industry, MIPS processors are employed in various control systems and infotainment systems, benefiting from their reliable and efficient processing capabilities. MIPS processors are increasingly found in IoT devices, providing the necessary computational power and energy efficiency for smart sensors, wearables, and other connected devices.

MIPS is built on RISC principles, which embrace simplicity and efficiency, making it an ideal choice for learning about CPU architecture in general. Some principles of RISC are: 

1. **Simple Instructions:** RISC architectures use a small, highly optimized set of instructions. Each instruction is designed to be simple and execute in a single clock cycle (under ideal conditions in a pipelined processor).
2. **Load/Store Architecture:** RISC separates memory access and data processing instructions. Only load and store instructions can access memory, while all other operations are performed on registers. This simplifies the instruction set and execution.
3. **Fixed-Length Instructions:** Instructions in RISC architectures are of uniform length, typically 32 bits. This uniformity simplifies instruction decoding and pipeline design.
4. **Simple Addressing Modes:** RISC architectures use a small number of simple addressing modes to keep instruction execution fast and efficient. Common addressing modes include register, immediate, and displacement.
5. **Pipelining:** RISC architectures are designed to efficiently support pipelining. Instructions are broken down into stages (fetch, decode, execute, memory access, write-back) that can be processed simultaneously for different instructions.


## MIPS32 and MIPS64

MIPS32 and MIPS64 are ISAs designed for 32-bit and 64-bit CPUs, respectively. The primary distinctions between modern MIPS32 and MIPS64 architectures are found in their register size, memory addressing capabilities, and support for larger data and address spaces. Unlike ARM and x86, both MIPS32 and MIPS64 utilize 32-bit-wide instructions, regardless of whether they are operating on 32-bit or 64-bit processors. 

MIPS32 is designed for 32-bit applications, with 32-bit registers and a 32-bit address space suitable embedded systems, microcontrollers, and other applications where 32-bit processing capabilities are sufficient. MIPS64 extends the architecture to 64-bit, offering larger 64-bit registers and a 64-bit address space, suitable for high-performance computing and large-scale applications.

Softwares written for MIPS32 can often run on MIPS64 processors without modification due to their shared instruction set, facilitating a smooth transition to 64-bit computing, while the reverse is not possible. MIPS is very efficient ISA for compiler to target because in most cases it can be well predicted how much time a sequence of instructions will take.


## Registers 

### General Purpose Registers

General Purpose registers are meant to be used by programmers and compilers for whatever operations required and has no special meaning to CPU. General-purpose registers are versatile storage locations within the CPU used for a wide range of tasks like holding intermediate data, operands and results of computations, and store temporary values during program execution. They are meant to be utilized by programmers and compilers as needed, without any special significance to the CPU itself.

MIPS has 32 general purpose registers (R0 - R31), 32 floating point registers (F0 - F31) that can hold either a 32-bit single-precision number or a 64-bit double-precision number. General Purpose Registers (GPRs) in MIPS architectures are used for storing immediate values, temporary data, function arguments, and return values. They also facilitate address calculation for memory operations and control flow in branching and jumping instructions.

In MIPS, most registers are truly general-purpose, meaning they can be used for any purpose. MIPS programmers adhere to agreed-upon guidelines specifying how registers should be utilized. For instance, the stack pointer `($sp)`, global pointer `($gp)`, and frame pointer `($fp)` are conventions rather than hardware-enforced roles, unlike in other Assembly languages like x86. The stack pointer is purely a software convention; no push instruction implicitly uses it. Using `$t0` instead of `$t3` as a temporary register isn't inherently faster or better. However, there's one notable exception: the `jal` instruction implicitly writes the return address to `$31` (the link register).


| Register | Name  | Description                                                                                                                             | Preserved Across Function Calls? |
| -------- | ----- | --------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| $0       | zero  | This register is hardwired to the value 0. It always returns 0 regardless of what is written to it.                                     | No                               |
| $1       | at    | Reserved for the assembler. It is used for pseudo-instructions and not typically used by programmers.                                   | No                               |
| $2-$3    | v0-v1 | Used to hold function return values.                                                                                                    | No                               |
| $4-$7    | a0-a3 | Used to pass the first four arguments to functions.                                                                                     | No                               |
| $8-$15   | t0-t7 | Temporary registers used for holding intermediate values. They are not preserved across function calls.                                 | No                               |
| $16-$23  | s0-s7 | Saved registers, which must be preserved across function calls. They are used to store values that should not be changed by a function. | Yes                              |
| $24-$25  | t8-t9 | More temporary registers, similar to t0-t7.                                                                                             | No                               |
| $26-$27  | k0-k1 | Reserved for the operating system kernel.                                                                                               | No                               |
| $28      | gp    | Global pointer, used to access static data.                                                                                             | Yes                              |
| $29      | sp    | Stack pointer, used to point to the top of the stack.                                                                                   | Yes                              |
| $30      | fp    | Frame pointer, used to manage stack frames in some calling conventions.                                                                 | Yes                              |
| $31      | ra    | Return address, used to store the return address for function calls.                                                                    | Yes                              |


When we say that saved registers must be "preserved across function calls," it means that the values in these registers should remain unchanged when a function (subroutine) returns to its caller. In other words, if a function uses these registers, it must ensure that any values stored in them before the function call are restored when the function completes. This is typically enforced through a process called "register saving" and "register restoring". The callee function first identifies which registers it uses that need to be preserved across function calls. These are known as "callee-saved" or "non-volatile" registers. The callee then saves the values of these registers by pushing them onto the stack. After the callee subroutine completes its task, it pops the saved register values off the stack, restoring the registers to their original state before returning control to the caller.


### Special Purpose Registers

Special purpose register's values are closely tied to the working of processor. For this purpose they may not be directly writeable by normal instructions like add, move, etc. Instead, some special registers in some processor architectures require special instructions to modify them. For instance, in many architectures, modifying the program counter necessitates instructions such as return from subroutine, jump, or branch. Similarly, condition code registers are typically updated exclusively through compare instructions, eg: CPSR register in ARM. This design ensures precise control over essential processor operations and status updates, safeguarding against unintended modifications that could disrupt program execution or system stability.

In MIPS architecture, several special registers play crucial roles in managing the CPU's state, controlling operations, and handling exceptions. Here are the main special registers used in MIPS:

- **Program Counter (PC):** Holds the address of the next instruction to be executed.
- **Hi and Lo Registers:** Store the results of multiplication and division operations. If the result of an operation involving 32-bit operands is more than 32-bits, MIPS processors store the lower 32 bits of the result in the Lo register and the upper 32 bits in the Hi register.
- **CP0:** CP0 refers to the control processor, which handles various system control and status registers (CSRs) that are crucial for system operation and control.
  - **Status Register (SR):** Controls the operating mode of the processor (user mode, kernel mode) and enables/disables interrupts.
  - **Cause Register (Cause):** Stores exception cause information.
  - **EPC (Exception Program Counter):** Holds the address of the instruction that caused an exception.
  - **EntryHi and EntryLo Registers:** Used for managing TLB (Translation Lookaside Buffer) entries.

## Data Types in MIPS

1. **Byte (8-bit):** Represented as `.byte` in MIPS assembly. Each byte consists of 8 bits.
2. **Halfword (16-bit):** Represented as `.half` or `.hword` in MIPS assembly. Each halfword consists of 16 bits or 2 bytes.
3. **Word (32-bit):** Represented as `.word` in MIPS assembly. Each word consists of 32 bits or 4 bytes. This is the default data type for many operations in MIPS32.
4. **Doubleword (64-bit):** Represented as `.dword` in MIPS assembly. Each doubleword consists of 64 bits or 8 bytes. This is especially relevant in MIPS64 architecture.
5. **Float (32-bit floating-point):** Represented as `.float` in MIPS assembly. This follows the IEEE 754 standard for single-precision floating-point numbers.
6. **Double (64-bit floating-point):** Represented as `.double` in MIPS assembly. This follows the IEEE 754 standard for double-precision floating-point numbers.

## Addressing Modes in MIPS

Addressing mode refers to the way in which the operand of an instruction is specified. Different addressing modes provide different ways to access operands, allowing for more flexible and efficient programming.

MIPS supports several addressing modes:

1. **Immediate Addressing:** The operand is a constant value embedded within the instruction itself.
```
addi $t0, $t1, 5  # $t0 = $t1 + 5
```

2. **Register Direct Addressing:** The operand is stored in a register.
```
add $t0, $t1, $t2  # $t0 = $t1 + $t2
```

3. **Register Indirect with Displacement** The operand is a memory location and the address of that memory location is given by the sum of the register and a constant displacement encoded in the ins. This is commonly used for loading and storing the array elements.
```
lw $t0, 8($t1), $t0 = MEM[Rt1 + 8]
```

4. **PC-Relative Addressing:** The operand's address is the sum of the program counter (PC) and a constant displacement.
```
beq $t0, $t1, label  # branches to the label if the values in registers $t0 and $t1 are equal, with the address computed relative to the current value of the PC.
```

5. **Pseudo-Direct Addressing:** Used in jump instructions where the target address is partially specified in the instruction and partially from the PC. To form the full 32-bit address, the 26-bit address from the instruction is combined with the upper 4 bits of the current program counter (PC). This is because, in a 32-bit address, the upper 4 bits are often the same for instructions within a relatively small range (within the same 256MB segment).
```
j target # jumps to an address formed by combining the upper bits of the current PC with the target address specified in the instruction.
```

## Memory Alignment and Endianness

Memory alignment refers to the arrangement of data in memory according to specific boundaries. Proper memory alignment means that data is stored at memory addresses that are multiples of the data's size. In MIPS, data must be properly aligned in memory to be accessed correctly. Attempting to access misaligned data in MIPS can lead to alignment exceptions, causing the program to crash or behave unpredictably. In contrast, x86 architecture is more flexible with memory alignment. While aligned data access is more efficient and generally recommended, x86 CPUs can handle misaligned data access without causing exceptions. The CPU might perform additional internal operations to handle the misaligned access, potentially resulting in a slight performance penalty compared to aligned accesses.

**Data Types and Alignment:**

- 1-byte (char): No alignment requirement.
- 2-byte (short): Must be aligned to 2-byte boundaries. Eg: valid addresses are 0, 2, 4,..
- 4-byte (int, float): Must be aligned to 4-byte boundaries. Eg: valid addresses are 0, 4, 8,..
- 8-byte (double, long long): Must be aligned to 8-byte boundaries. Eg: valid addresses are 0, 8, 16,..

MIPS instructions are 32 bits (4 bytes) long and must be word-aligned. This means that the address of any instruction must be a multiple of 4. For example, valid instruction addresses in MIPS could be 0, 4, 8, and so on. 


The `.align` directive in the MIPS assembler is used to specify the alignment of data in memory. While the assembler does automatically align data to the proper boundaries, the `.align` directive gives programmers explicit control over alignment, which can be useful for various reasons:

**Endianness:** When the data stored to be stored is more than 1 byte, the sequence of bytes forming the data can be stored in two possible orders in memory:
1. **Big-endian:** The most significant byte (MSB) is stored at the lowest memory address.
Example: For a 32-bit integer 0x12345678, the byte order in memory would be:
```
Address:   0x00   0x01   0x02   0x03
Value:     0x12   0x34   0x56   0x78
```
2. **Little-endian:**  The least significant byte (LSB) is stored at the lowest memory address.
Example: For a 32-bit integer 0x12345678, the byte order in memory would be:
```
Address:   0x00   0x01   0x02   0x03
Value:     0x78   0x56   0x34   0x12
```

Endianness affects how data is interpreted and exchanged between systems. If two systems with different endianness exchange data without proper handling, the data can be misinterpreted, leading to errors. Therefore, it is crucial to ensure that data is correctly converted between different endian formats when necessary.

Most modern personal computers, including those using x86 and x86-64 architectures, use little-endian format. MIPS processors can operate in both big-endian (BE) and little-endian (LE) modes. The Status register in CP0 has a bit called RE (Reverse Endian) which, when set, changes the endianness mode for user mode, such processors are called Bi-endian processors, some other examples for Bi-endian processors are ARM, PowerPC, Alpha, SPARC V9, etc. 

## Instruction Formats in MIPS

MIPS uses three main instruction formats: R-type, I-type, and J-type. Each format is designed to accommodate different types of instructions and their operands. 

### 1. R-type

R-type instructions are used for operations that involve only registers, such as arithmetic and logical operations.

| 31-26  | 25-21 | 20-16 | 15-11 | 10-6  | 5-0    |
| ------ | ----- | ----- | ----- | ----- | ------ |
| opcode | rs    | rt    | rd    | shamt | funct  |

- **Opcode: 6 bits** - The operation code that specifies the operation to be performed.
- **rs: 5 bits** - The first source register.
- **rt: 5 bits** - The second source register.
- **rd: 5 bits** - The destination register.
- **shamt: 5 bits**- The shift amount (used in shift instructions).
- **funct: 6 bits** - The function code that specifies the exact operation (used in conjunction with the opcode).

Each of the register field is 5 bits as there are 32 (2<sup>5</sup>) registers. 

Eg: `add $t1, $t2, $t3` 

### 2. I-type

| 31-26  | 25-21 | 20-16 |  15-0      |
| ------ | ----- | ----- | ---------- | 
| opcode |   rs  |   rt  | immediate  |


I-type instructions are used for operations that involve an immediate value (a constant), as well as for memory access and branches.

- **Opcode: 6 bits** - The operation code.
- **rs: 5 bits** - The source register.
- **rt: 5 bits** - The destination register (or another source register for branches).
- **Immediate: 16 bits** - The immediate value, which can be a constant, address offset, or immediate operand.

Eg: 
```
addi $t1, $t2, 10    # $t1 = $t2 + 10
lw $t0, 4($t1)       # $t0 = Memory[$t1 + 4]
andi $t0, $t1, 0xFF  # $t0 = $t1 & 0xFF
```

### 3. J-type

| 31-26 | 25-0    |
| ----- | ------- |
| opcode| address |                   

J-type instructions are used for jump instructions that require a target address.

- **Opcode: 6 bits** - The operation code.
- **Address: 26 bits** - The target address for the jump. This address is combined with the upper bits of the program counter (PC) to form the full jump address.

In MIPS32, we observe that only 26 bits are used for the target address of jump instructions, even though the address space of MIPS32 spans 4GB (2<sup>32</sup>). Because all MIPS instructions are 32 bits wide, they are word-aligned. This word alignment means the last 2 bits of any instruction address are always 00. Thus, only 28 bits are effectively used to form the target address. To construct the full 32-bit address, the upper 4 bits of the current program counter (PC) — which is the address of the instruction following the jump — are combined with the 28-bit target address. This results in a maximum addressable jump distance of 256MB (2<sup>28</sup>).

However, within a 4GB address space, it’s possible that the target instruction may be farther away than this 256MB limit. Modern assemblers employ various strategies to address this limitation, some of which we will explore later.


## Pros and Cons of Uniform Instruction Width and Dedicated Opcode Spots in MIPS

### Pros

1. **Simplicity in Instruction Fetching:** With a uniform instruction width (32 bits) for an implementation that fetches a single instruction per cycle, a single aligned memory/cache access of the fixed size is guaranteed to provide one (and only one) instruction, so no buffering or shifting is required. There is also no concern about crossing a cache line or page boundary within a single instruction.

2. **Predictable Instruction Fetching:** With a uniform instruction width, the instruction pointer increments by a fixed amount (32 bits) for each instruction (except for control flow instructions like jumps and branches). This predictability allows the CPU to know the location of the next instruction early, reducing the need for partial decoding. It also simplifies the process of fetching and parsing multiple instructions per cycle, enhancing overall efficiency. (The need for partial decoding arises when the length of instructions varies. The CPU must determine the length of each instruction before it can identify where the next instruction begins. This requires the CPU to decode at least part of the current instruction to find out its length, a process known as partial decoding. This extra step can complicate the instruction fetching process and introduce additional overhead.)

3. **Simplified Parsing and Early Register Reading:** The uniform instruction format in MIPS enables straightforward parsing of instruction components, such as immediate values, opcodes, and register names. This is particularly beneficial for timing-critical tasks like parsing source register names. With fixed positions for these components, the CPU can begin reading register values immediately after fetching the instruction, even before fully determining the instruction type. This speculative register reading does not require special recovery if incorrect, although it consumes extra energy. In the MIPS R2000's classic 5-stage pipeline, this approach allows register values to be read right after instruction fetch, providing ample time to compare values and resolve branches, thus avoiding stalls without needing branch prediction. Parsing out the opcode is slightly less timing-critical than parsing source register names, but extracting the opcode sooner accelerates the start of execution. Simple parsing of the destination register name facilitates dependency detection across instructions, particularly beneficial when executing multiple instructions per cycle. 

4. **Usage of Fewer Bits for Target Addresses:** In uniform instruction sets, the alignment of instructions allows the use of fewer bits to specify target addresses. For example, in a 32-bit wide instruction set, the last 2 bits of any instruction address are always 0 due to word alignment. This means that only 30 bits are needed to represent the address instead of 32. This reduction in required bits can be exploited in certain ISAs, such as MIPS/MIPS16, to provide additional storage space for other purposes, like indicating a mode with smaller or variable-length instructions. This efficient use of addressing allows for more compact encoding of instructions and can enhance the flexibility of the instruction set by supporting different modes.

## Cons

1. **Low Code Density:** Uniform instruction width can lead to inefficient use of memory when instructions are shorter than the fixed width. For example, if you have a 32-bit instruction width but some instructions only require a few bits, the extra bits in each instruction are wasted. This can lead to larger code sizes and increased memory consumption.

2. **Decreased Flexibility due to Implicit Operands:** Strict uniform formatting tends to exclude the use of implicit operands, which are operands not explicitly specified in the instruction but implied by the operation. For instance, even though MIPS mostly avoids implicit operands, it still uses an implicit destination register for the link register (`$ra`), which stores the return address for function calls. (When a function call is made in MIPS, the jal (jump and link) instruction is used. This instruction not only jumps to the target function address but also implicitly stores the return address (the address of the instruction following the `jal`) in the link register `$ra` (which is register `$31`). This behavior is implicit in the sense that the `jal` instruction does not need to specify that the return address should be stored in `$ra`; it is automatically understood and handled by the instruction.)

3. **Cannot Handle Large Values of Immediate:** Fixed-length instructions present challenges when dealing with large immediate values (constants embedded directly within instructions). In MIPS immediate values can be upto 16-bits within a single instruction. If a constant exceeds this 16-bit limit, additional steps are required to handle the larger value.
   1. **Loading as Data:** One method to handle large constants is to load them from memory. This approach involves:
      - An extra load instruction.
      - Overhead associated with address calculation, register usage, address translation, and tag checking.
   2. **Multiple Instructions:** MIPS provides two instructions `lui` (load upper immediate) to load the upper 16 bits of a constant and `ori` (or immediate) which performs bitwise OR on lower 16 bits this effectively loading a 32-bit immediate. These instructions do not involve memory access. The 32-bit immediate value is constructed directly within the CPU using two instructions. This is faster and avoids the overhead of accessing memory. Using two instructions to handle a large immediate introduces more overhead compared to a single instruction. Modern processor designs can mitigate some of this overhead. For example, Intel's macro-op fusion combines certain pairs of instructions at the front-end of the pipeline, effectively reducing the execution overhead.

4. **Challenges in Extending the ISA:** New features may require addition of new instructions to the ISA. Fixed-length instructions present a significant challenge when it comes to extending an instruction set. The number of distinct operations (opcodes) that can be represented is limited. For example, with a 6-bit opcode field (as in MIPS), there are only 64 possible opcodes. It also poses a challenge when we have to increase number of available registers as adding more registers requires more bits to encode the register addresses. To extend the instruction set without breaking compatibility, additional modes or instruction formats might be needed. This can complicate the CPU design and increase the complexity of the instruction decoder.

5. **Limited Address Bound for Branching Instructions:** In MIPS, the jump instruction uses only 26 bits to specify the immediate target address. Due to memory alignment, the last 2 bits are always zero, effectively giving 28 bits for the target address. The upper 4 bits of the Program Counter (PC) are combined with these 28 bits to form a full 32-bit address, which limits the addressable range to 256 MB. Consequently, the assembly programmer or compiler must ensure that the target address of the jump instruction lies within this 256 MB boundary. If the target address exceeds this limit, other options must be employed, such as using the `jr` (jump to the address stored in register) instruction, which can specify a full 32-bit address by storing the address in a register. In some versions, the assembler will issue a warning if the target address of a `j` instruction exceeds the 256 MB bound. In other cases, the assembler might automatically replace the `j` instruction with a `jr` instruction to handle the full address space correctly.

## Coprocessors in MIPS

MIPS is a modular architecture supporting up to four coprocessors (CP0/1/2/3). Coprocessors are specialized processing units that work alongside the main CPU to handle specific types of operations, such as floating-point arithmetic, system control, or other specialized tasks. MIPS typically defines up to four coprocessors, though not all are always implemented in every MIPS processor. These coprocessors are numbered CP0 through CP3.

1. **Coprocessor 0 (CP0) - System Control Coprocessor:** CP0 is responsible for managing system control functions, including exception handling, memory management, and processor status. It plays a critical role in configuring and controlling the behavior of the MIPS processor. CP0 contains a set of special-purpose registers used for various control tasks, such as the Status Register, Cause Register, EPC (Exception Program Counter), and TLB (Translation Lookaside Buffer) management registers.

2. **Coprocessor 1 (CP1) - Floating-Point Unit (FPU):**  CP1 is dedicated to handling floating-point arithmetic operations, such as addition, subtraction, multiplication, division, and square root operations on floating-point numbers. This offloads complex calculations from the main CPU, improving overall performance for tasks requiring floating-point computations. CP1 includes 32 floating-point registers (`$f0` to `$f31`), which are used to store floating-point operands and results. 

3. **Coprocessor 2 and 3 (Optional):** CP2 and CP3 are optional coprocessors that can be used for application-specific purposes, such as vector processing, digital signal processing (DSP), or other specialized tasks. For example, in the PlayStation video game console, CP2 is the Geometry Transformation Engine (GTE), which accelerates the processing of geometry in 3D computer graphics.


## Overview of MIPS Instructions

### 1. Memory Access Instructions

Memory access instructions in MIPS facilitate moving data between registers and memory, as well as between general purpose, floating-point (FP), or special registers. Most of the memory access instructions are I-type and use register indirect with displacement as addressing mode. 

#### 1. Load Family of Instructions

All of the load instructions in MIPS are I-type instructions, and they follow this general format:
```
LOAD <rt>, offset(base)
```

- **LOAD** is the opcode for the specific load instruction (e.g., LB, LBU, LH, LHU, LW, LWU, LD, L.S, L.D).
- **\<rt\>** is the target register where the data will be loaded.
- **offset** is a 16-bit signed immediate value representing the displacement.
- **base** is the base register whose contents are added to the offset to form the effective memory address.


| Instruction | Meaning                     | Description                                                                    |
| ----------- | --------------------------- | ------------------------------------------------------------------------------ |
| **LB**      | Load Byte                   | Loads a byte from memory into a register, sign-extended.                       |
| **LBU**     | Load Byte Unsigned          | Loads a byte from memory into a register, zero-extended.                       |
| **LH**      | Load Halfword               | Loads a halfword from memory into a register, sign-extended.                   |
| **LHU**     | Load Halfword Unsigned      | Loads a halfword from memory into a register, zero-extended.                   |
| **LW**      | Load Word                   | Loads a word from memory into a register.                                      |
| **LWU**     | Load Word Unsigned          | Loads a word from memory into a register, zero-extended (MIPS64).              |
| **LD**      | Load Doubleword             | Loads a doubleword from memory into a register (MIPS64).                       |
| **L.S**     | Load Single Precision Float | Loads a single precision floating-point value from memory into an FP register. |
| **L.D**     | Load Double Precision Float | Loads a double precision floating-point value from memory into an FP register. |
| **LUI**     | Load Upper Immediate        | Loads a 16-bit immediate value into the upper 16 bits of a register, with the lower 16 bits set to zero. Unlike other load instructions, LUI does not interact with memory. |


#### 2. Store Family of Instructions

The store family of instructions in MIPS transfers data from a register to a specified memory location. All of the store instructions in MIPS are I-type instructions, and they follow this general format:

```
STORE <rt>, offset(base)
```

- **STORE** is the opcode for the specific store instruction (e.g., SB, SH, SW, SD, S.S, S.D).
- **\<rt\>** is the source register whose data will be stored in memory.
- **offset** is a 16-bit signed immediate value representing the displacement.
- **base** is the base register whose contents are added to the offset to form the effective memory address.


| Instruction | Meaning                      | Description                                                                     |
| ----------- | ---------------------------- | ------------------------------------------------------------------------------- |
| **SB**      | Store Byte                   | Stores a byte from a register into memory.                                      |
| **SH**      | Store Halfword               | Stores a halfword from a register into memory.                                  |
| **SW**      | Store Word                   | Stores a word from a register into memory.                                      |
| **SD**      | Store Doubleword             | Stores a doubleword from a register into memory (MIPS64).                       |
| **S.S**     | Store Single Precision Float | Stores a single precision floating-point value from an FP register into memory. |
| **S.D**     | Store Double Precision Float | Stores a double precision floating-point value from an FP register into memory. |

#### 3. Register Data Transfer Instructions

These instructions facilitate the transfer of data between different types of registers, such as general-purpose registers (GPRs), floating-point registers (FPRs), and special-purpose registers. These instructions are critical in operations where data needs to be moved from one part of the CPU to another, enabling interaction between different processing units.


These instructions facilitate the transfer of data between two general-purpose registers.

- **MFHI:** Move From HI register. Transfers the content from the HI special register to a GPR.
```
MFHI $d  # $d = HI
```

- **MFLO:** Move From LO register. Transfers the content from the LO special register to a GPR.
```
MFLO $d  # $d = LO
```

- **MOV.S:** Move single-precision floating-point value.
```
MOV.S $f1, $f2  # $f1 = $f2
```

- **MOV.D:** Move double-precision floating-point value.
```
MOV.D $f1, $f2  # $f1 = $f2
```


- **MFC0 (Move From Coprocessor 0):** This instruction moves data from a specific CP0 register to a general-purpose register (GPR). It's often used to read system control information, such as the contents of the status register, exception handling registers, or memory management configuration.
```
MFC0 $t, $c0_reg, $sel
```

- $t: The destination general-purpose register.
- $c0_reg: The CP0 register number.
- $sel: The select field, which allows accessing different parts or subsets of the CP0 register.
Example:
```
MFC0 $t0, $12  # Move the contents of CP0 Status register (register 12) to $t0
```

- **MTC0 (Move To Coprocessor 0):** This instruction moves data from a general-purpose register (GPR) to a specific CP0 register. 
```
MTC0 $t0, $13  # Move the contents of $t0 into CP0 Cause register (register 13)
```

- **MFC1:**  Move From Coprocessor 1 (FPR) to GPR.
```
MFC1 $t, $f  # $t = $f
```

- **MTC1:** Move To Coprocessor 1 (FPR) from GPR.
```
MTC1 $f, $t  # $f = $t
```

### 2. Arithmetic instructions (Integers)

Arithmetic instructions in MIPS perform basic mathematical operations such as addition, subtraction, multiplication, and division. These instructions operate on values stored in general-purpose registers (GPRs) and often involve signed and unsigned integers.

Majority of arithmetic instructions are R-type, they follow this general format: 

```
ARITHMETIC $rd, $rs, $rt
```
- **ARITHMETIC** is the opcode for the specific arithmetic instruction (e.g., ADD, ADDU, SUB, MULT).
- **$rd** is the destination register where the result of the operation will be stored.
- **$rs** is the source register containing the first operand.
- **$rt** is the source register containing the second operand.

(Note: The storage format for R-type instructions is `<opcode> <rs> <rt> <rd> <shamt> <funct>`. However, when writing the instruction in assembly language, it is written as `<opcode> $rd, $rs, $rt.`)

Immediate operations follow I-type, the format is slightly different:

```
ARITHMETIC_IMM $rt, $rs, immediate
```

- **ARITHMETIC_IMM** is the opcode for the specific arithmetic instruction that uses an immediate value (e.g., ADDI, ADDIU).
- **$rt** is the destination register where the result will be stored.
- **$rs** is the source register containing the first operand.
- **immediate** is a 16-bit signed value that is added to the contents of `$rs`.



| Instruction | Syntax                      | Description                                                                                        | Example                                                     |
| ----------- | --------------------------- | -------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| **ADD**     | `ADD $rd, $rs, $rt`         | Adds the contents of `$rs` and `$rt`, stores the result in `$rd`. Raises an exception on overflow. | `ADD $t0, $t1, $t2  # $t0 = $t1 + $t2`                      |
| **ADDU**    | `ADDU $rd, $rs, $rt`        | Adds the contents of `$rs` and `$rt` without checking for overflow.                                | `ADDU $t0, $t1, $t2  # $t0 = $t1 + $t2 (no overflow check)` |
| **ADDI**    | `ADDI $rt, $rs, immediate`  | Adds an immediate value to `$rs`, stores the result in `$rt`. Raises an exception on overflow.     | `ADDI $t0, $t1, 10  # $t0 = $t1 + 10`                       |
| **ADDIU**   | `ADDIU $rt, $rs, immediate` | Adds an immediate value to `$rs` without checking for overflow.                                    | `ADDIU $t0, $t1, 10  # $t0 = $t1 + 10 (no overflow check)`  |
| **SUB**     | `SUB $rd, $rs, $rt`         | Subtracts `$rt` from `$rs`, stores the result in `$rd`. Raises an exception on overflow.           | `SUB $t0, $t1, $t2  # $t0 = $t1 - $t2`                      |
| **SUBU**    | `SUBU $rd, $rs, $rt`        | Subtracts `$rt` from `$rs` without checking for overflow.                                          | `SUBU $t0, $t1, $t2  # $t0 = $t1 - $t2 (no overflow check)` |
| **MULT**    | `MULT $rs, $rt`             | Multiplies `$rs` and `$rt`, result stored in `HI` and `LO` registers.                              | `MULT $t1, $t2  # Result in HI:LO = $t1 * $t2`              |
| **MULTU**   | `MULTU $rs, $rt`            | Multiplies unsigned integers `$rs` and `$rt`, result stored in `HI` and `LO` registers.            | `MULTU $t1, $t2  # Unsigned result in HI:LO`                |
| **DIV**     | `DIV $rs, $rt`              | Divides `$rs` by `$rt`, quotient stored in `LO`, remainder in `HI`.                                | `DIV $t1, $t2  # LO = $t1 / $t2; HI = $t1 % $t2`            |
| **DIVU**    | `DIVU $rs, $rt`             | Divides unsigned integers `$rs` by `$rt`, quotient stored in `LO`, remainder in `HI`.              | `DIVU $t1, $t2  # Unsigned LO = $t1 / $t2; HI = $t1 % $t2`  |

The above instructions are for MIPS32. MIPS64 has similar instructions with a prefix letter "D" added to each instruction. The "D" indicates "Doubleword," e.g., DADD, DADDI, DADDU, DADDIU.

### 3. Logical instructions (Integers)

Logical instructions in MIPS are used to perform bitwise operations on the binary representations of data stored in registers. 

Logical Instructions follow the R-type format. In this format, the instructions operate on registers and involve three operands: two source registers and one destination register.

```
LOGICAL $rd, $rs, $rt
```
- **LOGICAL:** is the opcode for logical instruction (e.g., AND, OR, XOR, NOR)
- **$rd** is the destination register.
- **$rs** and **$rt** are the source registers.


Some instructions have immediate variants as well, which follow the I-type format.
```
LOGICAL_IMM $rd, $rs, $rt
```

- **LOGICAL_IMM:** is the opcode for logical instruction (e.g., ANDI, ORI, XORI)
- **$rd** is the destination register.
- **$rs** and **$rt** are the source registers.

| Instruction | Meaning     | Description                                                                                             |
| ----------- | ----------- | ------------------------------------------------------------------------------------------------------- |
| **AND**     | Bitwise AND | Performs a bitwise AND operation between the values in `$rs` and `$rt`, and stores the result in `$rd`. |
| **OR**      | Bitwise OR  | Performs a bitwise OR operation between the values in `$rs` and `$rt`, and stores the result in `$rd`.  |
| **XOR**     | Bitwise XOR | Performs a bitwise XOR operation between the values in `$rs` and `$rt`, and stores the result in `$rd`. |
| **NOR**     | Bitwise NOR | Performs a bitwise NOR operation between the values in `$rs` and `$rt`, and stores the result in `$rd`. |
| **ANDI**     | Bitwise AND Immediate | Performs a bitwise AND operation between the value in `$rs` and an immediate value, and stores the result in `$rt`. |
| **ORI**      | Bitwise OR Immediate  | Performs a bitwise OR operation between the value in `$rs` and an immediate value, and stores the result in `$rt`.  |
| **XORI**     | Bitwise XOR Immediate | Performs a bitwise XOR operation between the value in `$rs` and an immediate value, and stores the result in `$rt`. |

### 4. Shift Instructions

Shift instructions in MIPS perform bitwise shifts on operands stored in registers. Shift instructions are all R-type and follow this general format:

```
SHIFT $rd, $rt, shamt 
```

- **SHIFT** is the opcode for the specific variable shift instruction (e.g., SLL, SRL, SRA).
- **$rd** is the destination register.
- **$rt** is the source register that contains the value to be shifted.
- **shamt** (shift amount) is the number of bit positions to shift the value in `$rt`.

Another type of shift instruction follows this format:

```
SHIFT $rd, $rt, $rs
```

- **SHIFT** is the opcode for the specific variable shift instruction (e.g., SLLV, SRLV, SRAV).
- **$rd** is the destination register.
- **$rt** is the source register that contains the value to be shifted.
- **$rs** is the register that specifies the shift amount.


| Instruction | Syntax                | Description                                                                                                        | Example                                  |
| ----------- | --------------------- | ------------------------------------------------------------------------------------------------------------------ | ---------------------------------------- |
| **SLL**     | `SLL $rd, $rt, shamt` | Shifts the contents of `$rt` left by `shamt` bits, stores the result in `$rd`.                                     | `SLL $t0, $t1, 2 # $t0 = $t1 << 2`      |
| **SRL**     | `SRL $rd, $rt, shamt` | Shifts the contents of `$rt` right by `shamt` bits (logical), stores the result in `$rd`. It does not preserve the sign bit (MSB). It treats the value as an unsigned number, so the MSB is replaced with a zero.                          | `SRL $t0, $t1, 2 # $t0 = $t1 >> 2`      |
| **SRA**     | `SRA $rd, $rt, shamt` | Shifts the contents of $rt right by shamt bits (arithmetic) and stores the result in $rd. It preserves the sign bit (MSB), meaning the sign bit remains unchanged during the shift operation. | `SRA $t0, $t1, 2 # $t0 = $t1 >> 2`      |
| **SLLV**    | `SLLV $rd, $rt, $rs`  | Shifts the contents of `$rt` left by the value in `$rs` (variable shift), stores the result in `$rd`.              | `SLLV $t0, $t1, $t2 # $t0 = $t1 << $t2` |
| **SRLV**    | `SRLV $rd, $rt, $rs`  | Shifts the contents of `$rt` right by the value in `$rs` (logical, variable shift), stores the result in `$rd`.    | `SRLV $t0, $t1, $t2 # $t0 = $t1 >> $t2` |
| **SRAV**    | `SRAV $rd, $rt, $rs`  | Shifts the contents of `$rt` right by the value in `$rs` (arithmetic, variable shift), stores the result in `$rd`. | `SRAV $t0, $t1, $t2 # $t0 = $t1 >> $t2` |

In a left shift operation, the sign bit (MSB) is treated like any other bit. The intuition behind a logical left shift is that each shift operation corresponds to multiplication by 2. For example: `0000 1111 << 1 = 0001 1110`, which is 15 * 2 = 30.

Similarly, a logical right shift corresponds to division by 2. For example: `0001 1110 >> 1 = 0000 1111`, which is 30 / 2 = 15. However, when applying logical right shift to negative numbers (in two's complement representation), such as `1110 0010` (which represents -30), performing a logical right shift results in `0111 0001` (113), which is not intuitive. In contrast, applying an arithmetic right shift, which preserves the sign bit, results in `1111 0001` (-15), which is more intuitive and useful.

### 5. Comparision Instruction

These instructions compare the values in registers (or between a register and an immediate value) and set the destination register based on whether the condition is met.

Comparision instructions follow the R-type format, they follow this general format:
```
COMPARISION $rd, $rs, $rt
```
- **COMPARISION:** is the opcode for logical instruction (e.g., SLT, SLTU)
- **$rd:** Destination register where the result (1 or 0) will be stored.
- **$rs:** First source register.
- **$rt:** Second source register.

They also have I-type variants
```
COMPARISION_IMM $rt, $rs, immediate
```
- **COMPARISION_IMM:** is the opcode for logical instruction (e.g., SLTI, SLTIU)
- **$rt:** Destination register where the result (1 or 0) will be stored
- **$rs:** Source register.
- **immediate:** 16-bit signed or unsigned immediate value.

| **Instruction** | **Syntax**                  | **Description**                                                                                     | **Example**                               |
| --------------- | --------------------------- | --------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| **SLT**         | `SLT $rd, $rs, $rt`         | Sets `$rd` to `1` if the value in `$rs` is less than the value in `$rt`, otherwise sets it to `0`.  | `SLT $t0, $t1, $t2`  # `$t0 = $t1 < $t2`  |
| **SLTI**        | `SLTI $rt, $rs, immediate`  | Sets `$rt` to `1` if the value in `$rs` is less than the immediate value, otherwise sets it to `0`. | `SLTI $t0, $t1, 10`  # `$t0 = $t1 < 10`   |
| **SLTU**        | `SLTU $rd, $rs, $rt`        | Sets `$rd` to `1` if the unsigned value in `$rs` is less than the unsigned value in `$rt`.          | `SLTU $t0, $t1, $t2`  # `$t0 = $t1 < $t2` |
| **SLTIU**       | `SLTIU $rt, $rs, immediate` | Sets `$rt` to `1` if the unsigned value in `$rs` is less than the unsigned immediate value.         | `SLTIU $t0, $t1, 10`  # `$t0 = $t1 < 10`  |

### 6. Control Instructions

Control instructions in MIPS manage the flow of execution by altering the program counter (PC) based on conditions, performing unconditional jumps, and handling exceptions. These instructions are crucial for implementing loops, conditional execution, and function calls. 

Control instructions in MIPS can be either I-type or J-type and follow these general formats:

**I-Type Branch Instructions**
```
BRANCH $rs, $rt, offset
```
- **BRANCH:** is the opcode for the specific branch instruction (e.g., `BEQ`, `BNE`, `BEQZ`, `BNEZ`).
- **$rs:** The first source register.
- **$rt:** The second source register (or immediate zero for `BEQZ`/`BNEZ`).
- **offset:** The 16-bit signed offset from `PC + 4` to which the program will branch if the condition is met.

**J-Type Jump Instructions**
```
JUMP target
```
- **JUMP:** is the opcode for the specific jump instruction (e.g., `J`, `JAL`).
- **target:** The 26-bit immediate value specifying the address to jump to, relative to `PC + 4`. It can also be the source register containing the target address.

| **Instruction** | **Syntax**             | **Description**                                                                                               | **Example**           |
| --------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------- | --------------------- |
| **BEQZ**        | `BEQZ $rs, offset`     | Branches if the value in `$rs` is equal to zero. Offset is 16-bit signed and relative to `PC + 4`.            | `BEQZ $t0, label`     |
| **BNEZ**        | `BNEZ $rs, offset`     | Branches if the value in `$rs` is not equal to zero. Offset is 16-bit signed and relative to `PC + 4`.        | `BNEZ $t0, label`     |
| **BEQ**         | `BEQ $rs, $rt, offset` | Branches if the values in `$rs` and `$rt` are equal. Offset is 16-bit signed and relative to `PC + 4`.        | `BEQ $t0, $t1, label` |
| **BNE**         | `BNE $rs, $rt, offset` | Branches if the values in `$rs` and `$rt` are not equal. Offset is 16-bit signed and relative to `PC + 4`.    | `BNE $t0, $t1, label` |
| **BC1T**        | `BC1T offset`          | Branches if the floating-point comparison bit is true. Offset is 16-bit signed and relative to `PC + 4`.      | `BC1T label`          |
| **BC1F**        | `BC1F offset`          | Branches if the floating-point comparison bit is false. Offset is 16-bit signed and relative to `PC + 4`.     | `BC1F label`          |
| **MOVN**        | `MOVN $rd, $rs, $rt`   | Copies the value in `$rs` to `$rd` if the value in `$rt` is not zero.                                         | `MOVN $t0, $t1, $t2`  |
| **MOVZ**        | `MOVZ $rd, $rs, $rt`   | Copies the value in `$rs` to `$rd` if the value in `$rt` is zero.                                             | `MOVZ $t0, $t1, $t2`  |
| **J**           | `J target`             | Unconditionally jumps to the target address. The target is a 26-bit immediate value relative to `PC + 4`.     | `J label`             |
| **JR**          | `JR $rs`               | Unconditionally jumps to the address contained in `$rs`.                                                      | `JR $t0`              |
| **JAL**         | `JAL target`           | Jumps to the target address and stores the return address (`PC + 4`) in `$ra` (register 31).                  | `JAL label`           |
| **JALR**        | `JALR $rd, $rs`        | Jumps to the address in `$rs` and stores the return address (`PC + 4`) in `$rd` (usually `$ra`).              | `JALR $ra, $t0`       |
| **TRAP**        | `TRAP code`            | Triggers a software interrupt, transferring control to the operating system at a predefined vectored address. | `TRAP 0x7`            |
| **ERET**        | `ERET`                 | Returns from an exception, restoring the state and returning to user mode.                                    | `ERET`                |