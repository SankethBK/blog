---
title: "CTF Learnings: Matryoshka"
date: 2025-11-04
categories: ["cheatsheet", "ctf"]
tags: ["reverse-engineering", "elf", "gdb", "radare2"]
author: "Gemini"
---

# Learnings from CTF Challenge: Matryoshka

This document summarizes the key tools, commands, and concepts from the Matryoshka crackme challenge.

## 1. Static Analysis

Commands to gather information without executing the binary.

| Command | Description |
| :--- | :--- |
| `file ./binary` | Identifies file type, architecture, and if it's stripped. |
| `strings ./binary` | Extracts human-readable strings. Use `-n <length>` for longer strings. |
| `checksec ./binary` | Checks for security mitigations like Canary, PIE, NX, and RELRO. |
| `readelf -h ./binary` | Displays the ELF header. Good for finding the entry point. |
| `readelf -l ./binary` | Displays the program headers. Can find the `INTERP` segment. |
| `readelf -r ./binary` | Shows relocation entries, revealing which library functions are used. |

## 2. Dynamic Analysis & Debugging

### strace

Traces system calls made by a process.

```bash
# Trace the program, follow forks (-f), show long strings (-s 200), and output to a file (-o)
strace -f -s 200 -o trace.log ./binary <args>
```
Look for failed `execve` calls or other errors (`-1 EFAULT`).

### GDB (GNU Debugger)

Powerful for inspecting a program's state at runtime.

| GDB Command | Description |
| :--- | :--- |
| `gdb ./binary` | Start debugging. |
| `break <address/symbol>` | Set a breakpoint (e.g., `break execve`). |
| `run <args>` | Execute the program with arguments. |
| `info inferiors` | List the processes being debugged to get the PID. |
| `p/x $register` | Print the value of a register in hex (e.g., `p/x $rsi`). |
| `x/[N][F][S] <address>` | Examine memory. `x/8gx $rsi` (examine 8 giant words in hex from RSI). |
| `x/s <address>` | Examine memory as a null-terminated string. |

**GDB Workflow Example:**
1. `gdb ./matryoshka`
2. `break execve`
3. `run f`
4. `info inferiors` (get PID)
5. `printf "argv_ptr = 0x%lx\n", $rsi` (inspect `execve` arguments)
6. `x/8gx $rsi` (examine the `argv` array)
7. `x/s <address_from_above>` (examine the string content of an `argv` entry)

## 3. Reverse Engineering with Radare2

A powerful framework for reverse engineering.

### Core Analysis Commands
| r2 Command | Description |
| :--- | :--- |
| `r2 ./binary` | Open the binary for analysis. |
| `aaa` | **A**nalyze **A**ll **A**utomatically. Finds functions, symbols, etc. |
| `afl` | **A**nalyze **F**unction **L**ist. Shows all identified functions. |
| `s <address/name>` | **S**eek to a specific address or function name (e.g., `s main`). |
| `pdf` | **P**rint **D**isassembled **F**unction. Shows assembly code. |
| `pdg` | **P**rint **D**ecompiled **G**hidra. Shows decompiled C-like code. |
| `afv` | **A**nalyze **F**unction **V**ariables. Shows local variables, arguments, and their stack offsets. |

### Additional Useful Commands
| r2 Command | Description |
| :--- | :--- |
| `i` | Show general information about the binary (imports, exports, strings). |
| `ps` | Print a summary of the binary's sections. |
| `V` | Enter visual mode for interactive navigation. |
| `VV` | Enter visual graph mode to see the control flow graph. |
| `?` / `??` | Get help on commands. |


## 4. Key Syscalls & Library Functions

| Function | Purpose & Relevance |
| :--- | :--- |
| `memfd_create()` | **Creates an anonymous file descriptor in RAM.** The file behaves like a regular file (it can be written to, mapped, etc.) but lives in volatile memory. It is automatically released when all references are dropped. The file path shows up in `/proc/self/fd/` with a `memfd:` prefix, which is a strong indicator of in-memory execution. |
| `execve()` | Executes a program. The arguments are `(path, argv, envp)`. A common target for breakpoints to see what new process is being spawned. |
| `__libc_start_main()` | A standard C library function that sets up the environment and calls `main`. |
| `__stack_chk_fail()` | Called when a stack canary detects a buffer overflow. |

## 5. Core Concepts

| Concept | Description |
| :--- | :--- |
| **Nested/Packed Binary** | An executable hidden inside another. The outer binary's job is to decrypt or unpack the inner one and execute it. |
| **XOR Cipher** | A simple symmetric encryption. If you know part of the plaintext (like the ELF magic `\x7fELF`), you can XOR it with the ciphertext to find the key. |
| **/proc Filesystem** | A virtual filesystem in Linux that exposes kernel and process information. Crucial for forensics and debugging. |
| **/proc/[pid]/fd/[fd]** | A special path to access the content of a process's open file descriptors. Used to extract the in-memory ELF file. |
| **PIE (Position-Indep. Executable)** | The binary's memory addresses are randomized at runtime. This means you work with offsets, not absolute addresses. |

## 6. CTF Pattern: In-Memory Execution

1.  **Identify**: The program uses `memfd_create`, `write`, and `execve`.
2.  **Intercept**: Set a breakpoint in GDB on `execve`.
3.  **Run**: Run the program with the correct input to trigger the decryption.
4.  **Extract**: When the breakpoint hits, get the process PID (`info inferiors`). Copy the in-memory file to disk: `cp /proc/<PID>/fd/<FD_NUM> ./extracted_binary`.
5.  **Repeat**: Analyze the `extracted_binary`. Repeat the process if it's another layer.

```