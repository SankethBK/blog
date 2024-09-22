---
layout: post_with_categories
title:  "Execution Flow of an Assembly Program"
date:   2024-08-17 01:30:00 +0530
categories: assembly
author: Sanketh
references: 
    - [Linkers and Loaders by John R. Levine](https://books.google.co.in/books/about/Linkers_and_Loaders.html?id=Id9cYsIdjIwC)
    - https://www.cs.cornell.edu/courses/cs3410/2019sp/schedule/slides/11-linkload-notes.pdf
    - 
---

High-level compiled languages like C, Go, and Rust are translated into low-level assembly language by their respective compilers. However, the journey of an assembly program doesn't end there. Although developers typically write code in high-level languages, assembly language remains the go-to choice in specialized fields such as embedded systems, operating system kernels, firmware development, and other areas where performance is crucial. Unlike high-level languages, where much of the complexity is abstracted away, assembly language offers developers a detailed view of what happens under the hood. In this blog post, we will go through the complete lifecycle of an assembly program from writing and assembling the code to linking, loading, and finally executing it on the hardware.

<div style="text-align: center;">
    <strong>Execution Flow of an Assembly Program: From Source Code to Execution</strong>
</div>
<br/>

<img src="/blog/assets/images/execution-flow.png" alt="Execution Cycle of an Assembly Program" height="800" />


#### 'Hello World' Program in MIPS Assembly

```
.data
message: .asciiz "Hello, World!\n"

.text
.globl main

main:
    li $v0, 4         # syscall for printing a string
    la $a0, message   # load address of message into $a0
    syscall           # make syscall

    li $v0, 10        # syscall for exiting the program
    syscall           # make syscall
```

Breaking down the above program

**1. Data Segment**

```
.data
message: .asciiz "Hello, World!\n"
```

- `.data:` This directive starts the data segment of the program. The data segment is where you define and store data that your program will use, such as strings, integers, etc.
- `message:` This is a label that serves as a reference to the memory location where the string "Hello, World!\n" is stored. Labels are used to access data or instructions.
- `.asciiz "Hello, World!\n":` This directive stores a null-terminated ASCII string in memory. The `\n` at the end of the string adds a newline character, which moves the cursor to the next line after printing the string.

**2. Text Segment**

```
.text
.globl main
```

- `.text:` This directive starts the text segment of the program. The text segment is where the actual code (instructions) of the program is written.
- `.globl main:` This directive declares the label main as a global symbol, meaning it can be accessed from outside the file (useful when linking multiple files). The label main is typically used as the entry point of the program, similar to the `main()` function in C.

**3. Main Procedure**

```
main:
    li $v0, 4         # syscall for printing a string
    la $a0, message   # load address of message into $a0
    syscall           # make syscall
```

- `main:` This is a label marking the start of the main procedure.
- `li $v0, 4:` The instruction li stands for "load immediate." It's a pseudo instruction that loads the immediate value 4 into register `$v0`. In MIPS, the value 4 in `$v0` indicates a system call for printing a string.
- `la $a0, message:` The instruction la stands for "load address." It loads the address of the label message into register `$a0`. In MIPS, the `$a0` register is used to pass the first argument to system calls, which in this case is the address of the string we want to print.
- `syscall:` This instruction triggers a system call. The system call number (in `$v0`) and arguments (in `$a0`, `$a1`, etc.) tell the operating system what service to perform. Here, it prints the string pointed to by `$a0`.

**4. Exit Program**

```
li $v0, 10        # syscall for exiting the program
syscall           # make syscall
```

- `li $v0, 10:` This pseudo-instruction loads the immediate value 10 into register `$v0`. The value 10 is the system call code for terminating the program.
- `syscall:` This makes a system call to exit the program.


## Components Involved in Execution of a Program

### 1. Compiler

A compiler is responsible for translating high-level source code written in languages like C, Go, or Rust into a lower-level language, typically assembly language. Beyond simple translation, a compiler performs several important tasks:

- **Preprocessing:** Handles directives like #include and #define, expanding macros and including header files.
- **Lexical Analysis:** Converts the source code into tokens, which are the basic elements of the programming language (keywords, identifiers, symbols).
- **Parsing:** Analyzes the tokens to ensure they adhere to the language's grammar rules, constructing a syntax tree.
- **Semantic Analysis:** Ensures that the syntax tree follows the semantic rules of the language, checking for type errors, scope resolution, and other logical aspects.
- **Intermediate Code Generation:** Converts the syntax tree into an intermediate representation, which is easier to optimize and translate into machine code.
- **Code Optimization:** Refines the intermediate code to improve performance and reduce resource usage, such as minimizing instruction count or memory usage.
- **Code Generation:** Translates the optimized intermediate code into assembly code specific to the target CPU architecture (e.g., MIPS).

Let's consider the hello world program in C

{% highlight C %}
#include <stdio.h>

int main() {
   printf("Hello, world!");
   return 0;
}
{% endhighlight %}

Since I don't have a CPU with MIPS architecture, I am using a cross compiler to convert C code to MIPS Assembly. The cross compiler I am using is mips-linux-gnu-gcc on Ubuntu. Other options include SPIM, MARS, QEMU, mips-none-elf-gcc, or websites like [Godbolt](https://godbolt.org/).

This is the MIPS Assembly generated from the above C code, using the following command:


```
mips-linux-gnu-gcc -S hello_world.c -o hello_world.s
```

```
.file	1 "hello.c"
	.section .mdebug.abi32
	.previous
	.nan	legacy
	.module	fp=xx
	.module	nooddspreg
	.module	arch=mips32r2
	.abicalls
	.text
	.rdata
	.align	2
$LC0:
	.ascii	"Hello, World!\000"
	.text
	.align	2
	.globl	main
	.set	nomips16
	.set	nomicromips
	.ent	main
	.type	main, @function
main:
	.frame	$fp,32,$31		# vars= 0, regs= 2/0, args= 16, gp= 8
	.mask	0xc0000000,-4
	.fmask	0x00000000,0
	.set	noreorder
	.set	nomacro
	addiu	$sp,$sp,-32
	sw	$31,28($sp)
	sw	$fp,24($sp)
	move	$fp,$sp
	lui	$28,%hi(__gnu_local_gp)
	addiu	$28,$28,%lo(__gnu_local_gp)
	.cprestore	16
	lui	$2,%hi($LC0)
	addiu	$4,$2,%lo($LC0)
	lw	$2,%call16(puts)($28)
	move	$25,$2
	.reloc	1f,R_MIPS_JALR,puts
1:	jalr	$25
	nop

	lw	$28,16($fp)
	move	$2,$0
	move	$sp,$fp
	lw	$31,28($sp)
	lw	$fp,24($sp)
	addiu	$sp,$sp,32
	jr	$31
	nop

	.set	macro
	.set	reorder
	.end	main
	.size	main, .-main
	.ident	"GCC: (Ubuntu 12.3.0-17ubuntu1) 12.3.0"
	.section	.note.GNU-stack,"",@progbits
```

Although this is lot of code just for printing the "hello world", let's look at the code directly responsible for printing hello world and decode it.

```
$LC0:
    .ascii  "Hello, World!\000"
```

This section defines the string "Hello, World!" as a null-terminated string in the program's data segment.

```
lui    $2, %hi($LC0)
addiu  $4, $2, %lo($LC0)
```

- These two instructions load the address of the string "Hello, World!" into register `$4` (which is $a0), used as the first argument to the `puts` function. 
- The `lui` (Load Upper Immediate) instruction is used to load a 16-bit immediate value into the upper 16 bits of a register. In this case, `$2` (which is $v0) is loaded with the upper 16 bits of the address of the string "Hello, World!", labeled as `$LC0`.
- The `%lo($LC0)` macro extracts the lower 16 bits of the address of `$LC0`.
- The `addiu` (Add Immediate Unsigned) instruction adds an immediate value to a register and stores the result in another register. Here, it combines the upper 16 bits (already stored in `$2`) with the lower 16 bits of the address of `$LC0`.




```
lw     $2, %call16(puts)($28)
move   $25, $2
jalr   $25
nop
```

These instructions load the address of the `puts` function into register `$25`, then jump to this function using `jalr $25`, effectively calling `puts` to print the string.

### 2. Assembler

The assembler takes the assembly language code produced by the compiler and translates it into machine code (binary format) that the CPU can execute directly. During this process, the assembler converts symbolic labels into actual memory addresses and translates mnemonic instructions into binary opcodes.