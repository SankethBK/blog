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


