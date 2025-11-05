---
title: "CTF Walkthrough
: Matryoshka Challenge"
date: 2025-11-05
categories: ["cheatsheet", "ctf"]
tags: ["reverse-engineering", "elf", "gdb", "radare2"]
author: "Gemini"
---

# Matryoshka Crackme Solution (Detailed Walkthrough)

This is a detailed write-up for the "Matryoshka" crackme on crackmes.one.

## 1. Initial Static Analysis

First, we gather basic information about the binary.

```bash
$ file matryoshka
matryoshka: ELF 64-bit LSB pie executable, x86-64, version 1 (SYSV), dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2, for GNU/Linux 4.4.0, stripped

$ checksec matryoshka
RELRO           STACK CANARY      NX            PIE             RPATH      RUNPATH     Symbols      FORTIFY    Fortified    Fortifiable    FILE
Partial RELRO   Canary found      NX enabled    PIE enabled     No RPATH   No RUNPATH  No Symbols   No         0            1              matryoshka
```

The binary is a stripped 64-bit PIE executable with a stack canary. Looking at the strings gives a major clue about its functionality.

```bash
$ strings -n 10 matryoshka
...
memfd_create
...
execve
...
/proc/self/fd/%d
...
```

The presence of `memfd_create`, `execve`, and `/proc/self/fd/%d` strongly suggests the program will create a file in memory and then execute it.

## 2. Decompilation and Logic of Layer 1

Decompiling the `main` function (using Ghidra in this case) shows a simple argument check. If `argc` is not 2, it prints a usage message.

```c
// Decompiled main function
undefined8 main(int argc, long argv) {
  if (argc == 2) {
    // ... core logic ...
    operation(magicString, magic_int, **(char **)(argv + 8) + -0x57, &local_var);
  }
  else {
    puts("usage: ./matryoshka key");
  }
  return 0;
}
```

The interesting part is the `operation` function, which is called with a character from our input (`argv[1][0]`) minus the constant `0x57`.

This `operation` function contains the core logic:
1.  An XOR cipher is performed on a large data blob.
2.  The result is written to an in-memory file descriptor created by `memfd_create`.
3.  `execve` is called to execute the content of that file descriptor.

```c
// Decompiled operation() function
void operation(byte *magicString_data, uint data_size, byte key, ...) {
  // 1. XOR the data blob with the derived key
  xor_cypher(magicString_data, data_size, key);

  // 2. Write the result to an in-memory file
  FILE *file_stream = write_magicString_to_in_memory_file_and_return_stream(magicString_data, data_size, 1);

  // 3. Execute the in-memory file
  exec_memfd_stream(file_stream, ...);
  return;
}
```

## 3. Finding the XOR Key

The program is executing a data blob, which means the blob itself must be a valid ELF file. All ELF files start with the magic bytes `\x7fELF` (`0x7f 45 4c 46`).

The encrypted data blob in the binary starts with `0x70 4A 43 49`.

Since `encrypted_byte ^ key = decrypted_byte`, we can find the key with `key = encrypted_byte ^ decrypted_byte`.

```
0x70 ^ 0x7f = 0x0f
0x4a ^ 0x45 = 0x0f
0x43 ^ 0x4c = 0x0f
0x49 ^ 0x46 = 0x0f
```

The key is `0x0f`. The program calculates the key as `input_char - 0x57`. Therefore, `input_char = 0x0f + 0x57 = 0x66`, which is the ASCII character 'f'.

## 4. Investigating the Crash & Extracting the Payload

Running `./matryoshka f` produces no output. Using `strace` reveals why:

```bash
$ strace -f ./matryoshka f
...
execve("./matryoshka", ["./matryoshka", "f"], 0x7ffc...) = 0
memfd_create("...", MFD_CLOEXEC) = 3
ftruncate(3, 43488) = 0
write(3, "\177ELF\2\1\1\0\0\0\0\0\0\0\0\0\3\0>\0\1\0\0\0...", 43488) = 43488
execve("/proc/self/fd/3", ["", "", ...], 0x7ffc...) = -1 EFAULT (Bad address)
...
```
The `write` call successfully writes a valid ELF header to the file descriptor, but the subsequent `execve` fails with a "Bad address" error. The `argv` array passed to it looks corrupt.

We can confirm this with GDB. We set a breakpoint on `execve` and inspect the arguments, which are passed in registers `$rdi`, `$rsi`, and `$rdx` on x86-64.

```bash
$ gdb ./matryoshka
(gdb) break execve
Breakpoint 1 at 0x1080
(gdb) run f
Starting program: /path/to/matryoshka f

Breakpoint 1, 0x0000555555555080 in execve@plt ()
(gdb) # $rdi holds the path, $rsi holds argv
(gdb) x/s $rdi
0x5555555592a0: "/proc/self/fd/3"
(gdb) # The path is correct. Let's check argv.
(gdb) x/8gx $rsi
0x7fffffffdc90: 0x000055555555a01c  0x00007fffffffdd6b
0x7fffffffdca0: 0x00007fffffffde90  0x0000000000000000
...
```
The `argv` array at `$rsi` should be an array of pointers to null-terminated strings, ending with a `NULL` pointer. While `argv[3]` is `NULL`, the pointers themselves point to garbage or empty strings, causing `execve` to fail.

Since the `write` to the file descriptor succeeded, we can grab the decrypted binary from the `/proc` filesystem before the program crashes.

1.  Get the PID inside GDB:
    ```gdb
    (gdb) info inferiors
      Num  Description       Executable
    * 1    process 39550     /path/to/matryoshka
    ```

2.  In another shell, copy the file from the process's file descriptor table:
    ```bash
    # Use the PID from GDB (e.g., 39550)
    $ cp /proc/39550/fd/3 ./layer2.bin
    ```

## 5. Inner Layers and Final Solution

The extracted file, `layer2.bin`, is another nested ELF. The entire process is repeated two more times: analyze the binary, find the XOR key for its payload, and use GDB to extract the next layer.

After extracting the third and final binary, decompiling it reveals a very simple program:

```c
// Decompiled final layer
undefined8 main(int argc, long argv) {
  int input_num;

  input_num = atoi(*(char **)(argv + 8)); // atoi(argv[1])
  if (input_num == 9) {
    puts("u win good job!!!!");
  }
  return 0;
}
```

The program simply checks if the first argument is the number `9`.

**The final step is to run the last extracted binary with the argument `9`:**

```bash
$ ./final_layer.bin 9
u win good job!!!!
```
