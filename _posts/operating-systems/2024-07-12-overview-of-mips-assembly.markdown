---
layout: post_with_categories
title:  "Overview of MIPS Assembly"
date:   2024-07-12 20:38:05 +0530
categories: cpu assembly
author: Sanketh
---

MIPS (Microprocessor without Interlocked Pipeline Stages) assembly is one of the RISC ISA's. It was developed in the early 1980s at Stanford University by Professor John L. Hennessy. MIPS is widely used in academic research and industry, particularly in computer architecture courses due to its straightforward design and in various embedded systems applications for its efficiency and performance.

## History

The first MIPS processor, the R2000, was introduced. It implemented the MIPS I architecture, which was one of the earliest commercial RISC processors. There are multiple versions of MIPS: including MIPS I, II, III, IV, and V; as well as five releases of MIPS32/64. MIPS I had 32-bit architecture with basic instruction set and addressing modes. MIPS III introduced 64-bit architecture in 1991, increasing the address space and register width.

MIPS32 and MIPS64 are modern versions of the architecture, maintaining backward compatibility while introducing enhancements for modern computing needs. MicroMIPS is a compact version of the MIPS instruction set, designed for embedded systems with limited memory. MIPS processors are commonly used in embedded systems, such as routers, printers, and smart home devices, where their efficiency and performance are crucial. In the automotive industry, MIPS processors are employed in various control systems and infotainment systems, benefiting from their reliable and efficient processing capabilities. MIPS processors are increasingly found in IoT devices, providing the necessary computational power and energy efficiency for smart sensors, wearables, and other connected devices.

MIPS is built on RISC principles, which embrace simplicity and efficiency, making it an ideal choice for learning about CPU architecture in general. Some principles of RISC are: 

1. Simple Instructions: RISC architectures use a small, highly optimized set of instructions. Each instruction is designed to be simple and execute in a single clock cycle (under ideal conditions in a pipelined processor).
2. Load/Store Architecture: RISC separates memory access and data processing instructions. Only load and store instructions can access memory, while all other operations are performed on registers. This simplifies the instruction set and execution.
3. Fixed-Length Instructions: Instructions in RISC architectures are of uniform length, typically 32 bits. This uniformity simplifies instruction decoding and pipeline design.
4. Simple Addressing Modes: RISC architectures use a small number of simple addressing modes to keep instruction execution fast and efficient. Common addressing modes include register, immediate, and displacement.
5. Pipelining: RISC architectures are designed to efficiently support pipelining. Instructions are broken down into stages (fetch, decode, execute, memory access, write-back) that can be processed simultaneously for different instructions.


## MIPS32 and MIPS64

MIPS32 and MIPS64 are ISAs designed for 32-bit and 64-bit CPUs, respectively. The primary distinctions between modern MIPS32 and MIPS64 architectures are found in their register size, memory addressing capabilities, and support for larger data and address spaces. Unlike ARM and x86, both MIPS32 and MIPS64 utilize 32-bit-wide instructions, regardless of whether they are operating on 32-bit or 64-bit processors. 

MIPS32 is designed for 32-bit applications, with 32-bit registers and a 32-bit address space suitable embedded systems, microcontrollers, and other applications where 32-bit processing capabilities are sufficient. MIPS64 extends the architecture to 64-bit, offering larger 64-bit registers and a 64-bit address space, suitable for high-performance computing and large-scale applications.

Softwares written for MIPS32 can often run on MIPS64 processors without modification due to their shared instruction set, facilitating a smooth transition to 64-bit computing, while the reverse is not possible. MIPS is very efficient ISA for compiler to target because in most cases it can be well predicted how much time a sequence of instructions will take.


## Registers 

### General Purpose Registers

General Purpose registers are meant to be used by programmers and compilers for whatver operations required and has no special meaning to CPU. General-purpose registers are versatile storage locations within the CPU used for a wide range of tasks like holding intermediate data, operands and results of computations, and store temporary values during program execution. They are meant to be utilized by programmers and compilers as needed, without any special significance to the CPU itself.

MIPS has 32 general purpose registers (R0 - R31), 32 floating point registers (F0 - F31) that can hold either a 32-bit single-precision number or a 64-bit double-precision number. General Purpose Registers (GPRs) in MIPS architectures are used for storing immediate values, temporary data, function arguments, and return values. They also facilitate address calculation for memory operations and control flow in branching and jumping instructions.

In MIPS, most registers are truly general-purpose, meaning they can be used for any purpose. MIPS programmers adhere to agreed-upon guidelines specifying how registers should be utilized. For instance, the stack pointer (\$sp), global pointer (\$gp), and frame pointer ($fp) are conventions rather than hardware-enforced roles, unlike in other Assembly languages like x86. The stack pointer is purely a software convention; no push instruction implicitly uses it. Using $t0 instead of $t3 as a temporary register isn't inherently faster or better. However, there's one notable exception: the jal instruction implicitly writes the return address to $31 (the link register).


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


When we say that saved registers must be "preserved across function calls," it means that the values in these registers should remain unchanged when a function (subroutine) returns to its caller. In other words, if a function uses these registers, it must ensure that any values stored in them before the function call are restored when the function completes. This is typically enforced through a process called "register saving" and "register restoring."


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

1. **Byte (8-bit):** Represented as .byte in MIPS assembly. Each byte consists of 8 bits.
2. **Halfword (16-bit):** Represented as .half or .hword in MIPS assembly. Each halfword consists of 16 bits or 2 bytes.
3. **Word (32-bit):** Represented as .word in MIPS assembly. Each word consists of 32 bits or 4 bytes. This is the default data type for many operations in MIPS32.
4. **Doubleword (64-bit):** Represented as .dword in MIPS assembly. Each doubleword consists of 64 bits or 8 bytes. This is especially relevant in MIPS64 architecture.
5. **Float (32-bit floating-point):** Represented as .float in MIPS assembly. This follows the IEEE 754 standard for single-precision floating-point numbers.
6. **Double (64-bit floating-point):** Represented as .double in MIPS assembly. This follows the IEEE 754 standard for double-precision floating-point numbers.

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

##

