---
title:  "The Fetch Decode Execute Cycle"
draft: false
date:   2024-06-30 
categories: ["cpu"]
tags: ["cpu"]
author: Sanketh
---

The Fetch-decode-execute cycle or instruction cycle is how CPU executes programs. During this cycle, the CPU retrieves an instruction from memory (fetch), interprets what action is required (decode), and then carries out the necessary operations to complete the instruction (execute). This cycle is crucial for the CPU to perform any computational tasks, and it repeats continuously while the computer is powered on. 

## What is Machine Code?

Machine code is the lowest-level programming language that consists of binary instructions directly executed by a CPU. Any program is compiled to a binary executable is transformed into machine code. Machine code consists of set of instructions which varies for each CPU architecture and is decided by the CPU manufacturer, eg: ARM, MIPS, x86, etc. Machine code consists of a set of instructions defined by the Instruction Set Architecture (ISA) of each CPU. The ISA, determined by the CPU manufacturer, varies across different architectures such as ARM, MIPS, and x86. This architecture-specific design means that machine code written for one type of CPU cannot be directly executed on another without translation or emulation. 

Machine code is loaded into RAM before execution and stored in code segment of the process. Machine code instructions typically follow a specific format that is closely related to the architecture's Instruction Set Architecture (ISA). Depending on the processor, a computer's instruction sets might either be of uniform length or vary in length, eg: In MIPS all instructions are 32 bits long, x86 instructions can range from 1 to 15 bytes. Machine code instructions typically follow a specific format that is closely related to the architecture's Instruction Set Architecture (ISA). While the exact format can vary between different ISAs, a general pattern for machine code instructions can be described as follows:

```
<opcode> <destination register>, <source register 1>, <source register 2>
```
- opcode: The operation code specifies the operation to be performed (e.g., ADD, SUB, LOAD, STORE). This is the mnemonic representation of the binary code that the CPU understands.
- destination register: The register where the result of the operation will be stored.
- source register 1: The first operand register.
- source register 2: The second operand register (if applicable)

### Assembly

Machine code is difficult for humans to read and interpret. To bridge this gap, a disassembler converts machine code into assembly language. Assembly language provides a direct mapping between numerical machine code and a human-readable version, replacing numerical opcodes and operands with readable strings. Additionally, programmers can write code in assembly language, which an assembler then converts back into machine code for the CPU to execute.

## The Fetch, Decode, Execute Cycle

Different components of the CPU work together in order to execute a program each performing a distinct function. By dividing the work into separate stages, multiple instructions can be processed simultaneously at different stages of the cycle, this is called **pipelining**.  Pipelining increases the throughput of the CPU, as one instruction can be fetched while another is decoded, another is executed, and another is writing back.

### 1. Fetch

The Program Counter (PC) is a special purpose register that always holds the address of the next instruction to be executed. During the fetch stage, the address stored in the PC is copied to the Memory Address Register (MAR). The PC is then incremented to point to the memory address of the subsequent instruction. The CPU retrieves the instruction at the memory address specified by the MAR and copies it into the Memory Data Register (MDR). The instruction is copied to Instruction Register (IR) at the end of fetch cycle.

The PC is incremented immediately after the address stored in it is copied to the MAR and doesn't wait for the current instruction to complete because in a pipelined CPU, multiple instructions are processed simultaneously at different stages of the instruction cycle. Incrementing the PC right away allows the next instruction to enter the fetch stage while the current instruction is moving through the decode and execute stages. This overlap increases overall instruction throughput.

The control unit orchestrates the entire process, sending signals to the other components to ensure they operate in the correct sequence. It ensures the address is sent to memory, the instruction is fetched, and the PC is incremented. 

The initial instruction cycle starts immediately when the system is powered on, using a predefined PC value specific to the system's architecture (for example, in Intel IA-32 CPUs, the predefined PC value is 0xfffffff0). This address usually points to a set of instructions stored in read-only memory (ROM), which initiates the loading or booting of the operating system.


### 2. Decode

The decode stage involves interpreting the fetched instruction and preparing the necessary components of the CPU for the execution stage. The Instruction Decoder interprets the opcode and determines the type of operation to be performed (e.g., addition, subtraction, load, store), opcode is also used to decide number of operands to be fetched. If the instruction is a memory operation, the decoder also identifies the addressing mode and determines the effective memory address to be used in the following execute stage. 


### 3. Execute

In the execute stage, the CPU carries out the instruction decoded in the previous stage. Depending on the type of instruction, different components of the CPU are involved: If the instruction is an arithmetic or logic operation (such as addition, subtraction, or bitwise operations), the Arithmetic Logic Unit (ALU) is activated. If the instruction involves data transfer (such as loading data from memory into a register or storing data from a register into memory), the CPU will interact with the memory unit. For a load instruction, the CPU sends the memory address to the Memory Address Register (MAR) and retrieves the data from that address into the Memory Data Register (MDR). For a store instruction, it writes the data from the register to the specified memory address. If the instruction is a control operation (such as a jump, branch, or call), the Program Counter (PC) is updated to reflect the new address for the next instruction. This may involve adding an offset to the current PC value or directly loading a new address into the PC.






