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

