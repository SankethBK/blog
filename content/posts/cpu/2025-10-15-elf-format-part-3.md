---
title:  "ELF Format: Part 3"
date:   2025-10-15
categories: ["elf"]
tags: ["elf", "reverse engineering"]
author: Sanketh
references:
  
---

# ELF Format: Sections and Section Header Table

In the previous post, we explored Program Headers and Segments - the runtime view of an ELF file. Now we'll look at Section Headers and Sections - the link-time and debugging view.


## What Are Sections?

Sections are the link-time view of an ELF file. While segments tell the operating system how to load and execute a program, sections organize the file's contents for:

- **Linkers** - combining object files into executables
- **Debuggers** - finding symbols, source code mappings
- **Analysis tools** - examining specific parts of the binary

**Key distinction from segments:**

Segments = Required at runtime (OS needs them to execute)
Sections = Optional at runtime (can be stripped from executables)

You can strip all section headers and the program will still run:

```bash
$ readelf -S main | wc -l
68

$ objcopy --strip-section-headers main  main2

$ readelf -S main2
There are no sections in this file.

$ ./main2
Hi there!
```

## Sections vs Segments: The Relationship

- Sections (like `.text`, `.data`, `.bss`, `.rodata`)
Represent logical divisions of code and data within the file.
Used by linkers and debuggers — they organize how functions, variables, and symbols are stored in the file.

- Segments (`PT_LOAD`, `PT_DYNAMIC`, `PT_INTERP`, etc.)
Represent runtime mappings — how parts of the file are placed into memory by the OS loader when the program runs.

**How They Relate**

During linking, the linker groups related sections into loadable segments based on their flags (`R`, `W`, `X`) and alignment requirements.

| Segment (Type)           | Typical Sections              | Permissions |
| ------------------------ | ----------------------------- | ----------- |
| Text Segment (`PT_LOAD`) | `.interp`, `.text`, `.rodata` | **R-X**     |
| Data Segment (`PT_LOAD`) | `.data`, `.bss`               | **RW-**     |

So, a segment is usually a contiguous chunk of the file containing one or more sections that share similar memory attributes.


**Key Facts**

- **A section can exist outside any segment.**
These are used only at link or debug time and are not mapped into memory.
Examples: `.symtab`, `.strtab`, `.debug_*`, `.comment`.

- **A section can never belong to more than one segment.**
Each section appears in at most one segment, as each piece of data is loaded into a single memory region.

- **A segment can exist without any section.**
Some segments (like `PT_INTERP`, `PT_PHDR`, or `PT_NOTE`) describe runtime structures or metadata not represented as regular sections.

## Section Header Table

The Section Header Table is an array of section header entries, each describing one section.

### Section Header Table Location

The ELF Header tells us where to find it:

- Location (file offset): `e_shoff` field in ELF Header
- Entry size: `e_shentsize` (40 bytes for 32-bit, 64 bytes for 64-bit)
- Number of entries: `e_shnum`
- String table index: `e_shstrndx` (which section contains section names)

Total table size = `e_shentsize × e_shnum`

```bash
$ readelf -h main | grep section
  Start of section headers:          14176 (bytes into file)
  Size of section headers:           64 (bytes)
  Number of section headers:         31
  Section header string table index: 30
```

This means:

- Section Header Table starts at offset 0x3760 (14176 bytes)
- Each entry is 64 bytes
- There are 31 entries
- Section #30 contains the string table with section names

### Section Header Entry Structure

Each entry describes one section. Here's the structure from the Linux kernel:

```c
typedef struct elf32_shdr {
  Elf32_Word	sh_name;       // Section name (string table offset)
  Elf32_Word	sh_type;       // Section type
  Elf32_Word	sh_flags;      // Section flags
  Elf32_Addr	sh_addr;       // Virtual address in memory
  Elf32_Off	sh_offset;     // File offset
  Elf32_Word	sh_size;       // Section size
  Elf32_Word	sh_link;       // Link to another section
  Elf32_Word	sh_info;       // Additional information
  Elf32_Word	sh_addralign;  // Alignment constraints
  Elf32_Word	sh_entsize;    // Entry size if section holds table
} Elf32_Shdr;

typedef struct elf64_shdr {
  Elf64_Word	sh_name;       // Section name (string table offset)
  Elf64_Word	sh_type;       // Section type
  Elf64_Xword	sh_flags;      // Section flags
  Elf64_Addr	sh_addr;       // Virtual address in memory
  Elf64_Off	sh_offset;     // File offset
  Elf64_Xword	sh_size;       // Section size
  Elf64_Word	sh_link;       // Link to another section
  Elf64_Word	sh_info;       // Additional information
  Elf64_Xword	sh_addralign;  // Alignment constraints
  Elf64_Xword	sh_entsize;    // Entry size if section holds table
} Elf64_Shdr;
```

### Section Header Fields Explained

#### 1. sh_name - Section Name

This is NOT a string! It's an offset into the section header string table.

How section names work:

Step 1: ELF Header's `e_shstrndx` tells us which section contains names

```bash
$ readelf -h main | grep "string table index"
  Section header string table index: 30
```

Step 2: Section #30 is a string table (.shstrtab)

```bash
Offset 0:    \0
Offset 1:    .symtab\0
Offset 9:    .strtab\0
Offset 17:   .text\0
Offset 23:   .data\0
...
```

Step 3: Each section's sh_name is an offset into this table

```bash
Section #1: sh_name = 1  → ".symtab"
Section #2: sh_name = 9  → ".strtab"
Section #3: sh_name = 17 → ".text"
```

**ELF String Tables**

In ELF, strings are stored in dedicated tables rather than repeated everywhere. This design keeps the binary compact and makes parsing easier. There are two main types of string tables:

**1. Section Header String Table (.shstrtab)**

`.shstrtab` is also a type of section, it holds the names of other sections, other sections just refer to the index from this table

```bash
$ readelf -S main | grep .shstrtab
  [28] .shstrtab         STRTAB           0000000000000000  0000303b
```

It means 28th index of section header table is section header string table. ELF header's `e_shstrndx` also indicates same

We can inspect the contents of `.shstrtab` by 

```bash
$ readelf -p .shstrtab main

String dump of section '.shstrtab':
  [     1]  .shstrtab
  [     b]  .interp
  [    13]  .note.gnu.property
  [    26]  .note.gnu.build-id
  [    39]  .note.ABI-tag
  [    47]  .gnu.hash
  [    51]  .dynsym
  [    59]  .dynstr
  [    61]  .gnu.version
  [    6e]  .gnu.version_r
  [    7d]  .rela.dyn
  [    87]  .rela.plt
  [    91]  .init
  [    97]  .plt.got
  [    a0]  .plt.sec
  [    a9]  .text
  [    af]  .fini
  [    b5]  .rodata
  [    bd]  .eh_frame_hdr
  [    cb]  .eh_frame
  [    d5]  .init_array
  [    e1]  .fini_array
  [    ed]  .dynamic
  [    f6]  .data
  [    fc]  .bss
  [   101]  .comment
```


**2. Symbol String Table (`.strtab`)**

- Purpose: Stores symbol names used by the linker and debugger.
- Symbols (like function and variable names) in `.symtab` point to offsets in .strtab.
- This separation of symbols and section names allows the ELF format to handle linking and debugging information efficiently.

#### 2. sh_type - Section Type

Each section in an ELF file has a type, defined by the `sh_type` field in its section header.
This tells the linker or loader what kind of data the section holds and how it should be treated.

| Value | Name        | Description                               |
|-------|------------|-------------------------------------------|
| 0     | SHT_NULL   | Inactive section (placeholder)            |
| 1     | SHT_PROGBITS | Program data (code, data, anything)     |
| 2     | SHT_SYMTAB | Symbol table (for linking)                |
| 3     | SHT_STRTAB | String table                               |
| 4     | SHT_RELA   | Relocation entries with addends           |
| 5     | SHT_HASH   | Symbol hash table                          |
| 6     | SHT_DYNAMIC | Dynamic linking information               |
| 7     | SHT_NOTE   | Auxiliary information                      |
| 8     | SHT_NOBITS | Section occupies no file space (.bss)     |
| 9     | SHT_REL    | Relocation entries without addends        |
| 11    | SHT_DYNSYM | Dynamic symbol table                       |


##### 1. SHT_NULL — Inactive Section

This is a placeholder entry that marks an unused section header. It has no data and is typically found as the first entry in the section header table (index 0). Every ELF file starts with this null section.

##### 2. SHT_PROGBITS — Program Data

This is the most common section type. It holds actual program content — like executable instructions (`.text`), initialized data (`.data`), or read-only constants (`.rodata`). These sections are loaded into memory when the program runs.

##### 3. SHT_SYMTAB — Symbol Table

Contains a full list of symbols defined or referenced in the program.
This table is mainly used by the linker during relocation and symbol resolution.
Each entry describes a symbol’s name, address, size, and type (function, variable, etc.).
It’s usually found in relocatable (`.o`) files.

##### 4. SHT_STRTAB — String Table

Stores strings used by other sections — for example, section names (.shstrtab) or symbol names (`.strtab`).
Other sections don’t store names directly; instead, they store an offset into this string table.

##### 5. SHT_RELA — Relocation Entries with Addends

Holds relocation information that includes explicit addends (extra constant values).
Used by the linker to adjust symbol references when combining multiple object files.
You’ll see this in files targeting architectures like x86-64, where addends are stored in the relocation entry itself.

##### 6. SHT_HASH — Symbol Hash Table

Provides a quick way for the dynamic linker to find symbols at runtime using a hash lookup.
This section speeds up symbol resolution for shared libraries.

##### 7. SHT_DYNAMIC — Dynamic Linking Information

Contains metadata needed for dynamic linking — such as shared library names, symbol dependencies, and relocation entries.
This section appears only in dynamically linked executables and shared objects (`.so` files).

##### 8. SHT_NOTE — Auxiliary Information

Stores extra information such as build IDs, ABI tags, or core dump metadata.
Notes are often used by debuggers or by the kernel when generating core dumps.

##### 9. SHT_NOBITS — No File Storage (e.g., `.bss`)

Represents sections that occupy memory at runtime but take no space in the file.
A classic example is `.bss`, which holds uninitialized global or static variables.
The loader allocates and zero-initializes it in memory.

##### 10. SHT_REL — Relocation Entries without Addends

Similar to `SHT_RELA`, but here addends are stored in the section being relocated, not in the relocation entry.
Used on architectures like x86 (32-bit ELF).

##### 11. SHT_DYNSYM — Dynamic Symbol Table

A smaller, optimized version of the symbol table used at runtime by the dynamic linker.
It lists only the symbols needed for dynamic linking, unlike `.symtab`, which includes all symbols.


#### 3. sh_flags - Section Flags

Attributes of the section:

| Flag          | Value  | Meaning                                  |
|---------------|--------|------------------------------------------|
| SHF_WRITE     | 0x1    | Section is writable at runtime           |
| SHF_ALLOC     | 0x2    | Section occupies memory during execution |
| SHF_EXECINSTR | 0x4    | Section contains executable code         |
| SHF_MERGE     | 0x10   | Section may be merged                    |
| SHF_STRINGS   | 0x20   | Section contains null-terminated strings |
| SHF_TLS       | 0x400  | Section contains thread-local data       |

**Flag combinations tell you about the section:**

- `.text`: `SHF_ALLOC | SHF_EXECINSTR` (AX) - loaded, executable
- `.data`: `SHF_WRITE | SHF_ALLOC` (WA) - loaded, writable
- `.rodata`: `SHF_ALLOC` (A) - loaded, read-only
- `.symtab`: No flags - not loaded at runtime!


**Important: SHF_ALLOC flag**

- Sections WITH `SHF_ALLOC` are part of segments (loaded to memory)
- Sections WITHOUT `SHF_ALLOC` are not loaded (debugging/linking only)

#### 4. sh_addr - Virtual Address

Virtual memory address where the section appears at runtime.

- For sections with `SHF_ALLOC`: actual runtime address
- For sections without `SHF_ALLOC`: usually 0 (not loaded)

```bash
$ readelf -S main
  [Nr] Name      Type      Address          Off    Size   Flg
  [14] .text     PROGBITS  0000000000001060  001060 000185 AX
  [24] .symtab   SYMTAB    0000000000000000  002c48 000690
```

`.text` has address `0x1060` (will be at this address in memory)
`.symtab` has address `0x0` (not loaded, address irrelevant)

#### 5. sh_offset - File Offset

Byte offset from the beginning of the file where the section's data starts.
Example: `sh_offset = 0x1060` means section data begins at byte 4192 in the file.


#### 6. sh_size - Section Size

Size of the section in bytes.
Special case: For `SHT_NOBITS` sections (like `.bss`), this is the size in memory, but there are 0 bytes in the file!

#### 7. sh_link — Linking One Section to Another

The `sh_link` field in a section header holds a reference (index) to another section in the same ELF file.

But what it points to depends on the type of the section.

In other words, the ELF spec reuses `sh_link` for different purposes depending on the `sh_type`.

**How sh_link is interpreted**

| Section Type                | `sh_link` Meaning                                                                           |
| --------------------------- | ------------------------------------------------------------------------------------------- |
| `SHT_SYMTAB` / `SHT_DYNSYM` | Index of the **string table** section that holds the names of symbols in this symbol table. |
| `SHT_REL` / `SHT_RELA`      | Index of the **symbol table** that the relocation entries refer to.                         |
| `SHT_DYNAMIC`               | Index of the **string table** used by entries in the `.dynamic` section.                    |
| `SHT_HASH`                  | Index of the **symbol table** to which the hash applies.                                    |

#### 8. sh_info - Additional Information

Extra information, meaning depends on section type:

| Section Type | sh_info Meaning | 
|--------------|------------------|
| SHT_SYMTAB / SHT_DYNSYM | Index of first non-local symbol
| SHT_REL / SHT_RELA | Section index to which relocations apply

#### 9. sh_addralign - Alignment

Alignment constraint for the section.

- Value must be 0 or power of 2
- 0 or 1 means no alignment
- `sh_addr` must be aligned: `sh_addr % sh_addralign == 0`

Example: `sh_addralign = 16` means section must start at 16-byte boundary.

#### 10. sh_entsize - Entry Size

If section contains a table of fixed-size entries, this is the size of each entry.

- For .`symtab`: size of symbol table entry (24 bytes for 64-bit)
- For .`rela.text`: size of relocation entry
- For non-table sections: 0

Calculate number of entries:

`num_entries = sh_size / sh_entsize`

## Broad Classifications of Sections

| Category                      | Purpose                             | Examples                                |
| ----------------------------- | ----------------------------------- | --------------------------------------- |
| **Code**                      | Executable instructions             | `.text`, `.plt`, `.init`                |
| **Data**                      | Program variables                   | `.data`, `.bss`, `.rodata`              |
| **Linking / Loader Metadata** | Linking, relocation, symbol info    | `.symtab`, `.rel.*`, `.dynamic`, `.got` |
| **Debugging / Profiling**     | Developer tools                     | `.debug_*`, `.note.*`                   |
| **Special / Misc**            | Constructors, ABI info, interpreter | `.init_array`, `.interp`                |



## Code Sections

### 1. .text - Executable Code

**Type:** `SHT_PROGBITS`
**Flags:** `SHF_ALLOC | SHF_EXECINSTR` (AX)
**Contains:** Machine code instructions
This is where your compiled functions live:

Let's inspect the `.text` section of a simple C program

```c
// main.c
#include <stdio.h>

void greet() {
    printf("Hello, ELF!\n");
}

int main() {
    greet();
    return 0;
}
```

```bash
$ gcc -g -O0 -o main main.c
```

- `-g`: tells compiler to include debugging symbols in the output: variable names, function names, line numbers, file names, etc.
- `-O0`: optimization level 0 means: No optimization (keeps code structure close to source)


```bash
$ readelf -S main | grep .text

  [16] .text             PROGBITS         0000000000001060  00001060
```

We can see `.text` section is at offset 1060 bytes.

To get the raw dump of `.text` section:

```bash
$ objdump -s -j .text main

main:     file format elf64-x86-64

Contents of section .text:
 1060 f30f1efa 31ed4989 d15e4889 e24883e4  ....1.I..^H..H..
 1070 f0505445 31c031c9 488d3de4 000000ff  .PTE1.1.H.=.....
 1080 15532f00 00f4662e 0f1f8400 00000000  .S/...f.........
 1090 488d3d79 2f000048 8d05722f 00004839  H.=y/..H..r/..H9
 10a0 f8741548 8b05362f 00004885 c07409ff  .t.H..6/..H..t..
 10b0 e00f1f80 00000000 c30f1f80 00000000  ................
 10c0 488d3d49 2f000048 8d35422f 00004829  H.=I/..H.5B/..H)
 10d0 fe4889f0 48c1ee3f 48c1f803 4801c648  .H..H..?H...H..H
 10e0 d1fe7414 488b0505 2f000048 85c07408  ..t.H.../..H..t.
 10f0 ffe0660f 1f440000 c30f1f80 00000000  ..f..D..........
 1100 f30f1efa 803d052f 00000075 2b554883  .....=./...u+UH.
 1110 3de22e00 00004889 e5740c48 8b3de62e  =.....H..t.H.=..
 1120 0000e819 ffffffe8 64ffffff c605dd2e  ........d.......
 1130 0000015d c30f1f00 c30f1f80 00000000  ...]............
 1140 f30f1efa e977ffff fff30f1e fa554889  .....w.......UH.
 1150 e5488d05 ac0e0000 4889c7e8 f0feffff  .H......H.......
 1160 905dc3f3 0f1efa55 4889e5b8 00000000  .].....UH.......
 1170 e8d4ffff ffb80000 00005dc3           ..........].
 ```

 (main refers to file name in above command, not the main function)

 To get the disassembled output of `.text` section:

 ```bash
$  objdump -d -j .text main

main:     file format elf64-x86-64


Disassembly of section .text:

0000000000001060 <_start>:
    1060:	f3 0f 1e fa          	endbr64
    1064:	31 ed                	xor    %ebp,%ebp
    1066:	49 89 d1             	mov    %rdx,%r9
    1069:	5e                   	pop    %rsi
    106a:	48 89 e2             	mov    %rsp,%rdx
    106d:	48 83 e4 f0          	and    $0xfffffffffffffff0,%rsp
    1071:	50                   	push   %rax
    1072:	54                   	push   %rsp
    1073:	45 31 c0             	xor    %r8d,%r8d
    1076:	31 c9                	xor    %ecx,%ecx
    1078:	48 8d 3d e4 00 00 00 	lea    0xe4(%rip),%rdi        # 1163 <main>
    107f:	ff 15 53 2f 00 00    	call   *0x2f53(%rip)        # 3fd8 <__libc_start_main@GLIBC_2.34>
    1085:	f4                   	hlt
    1086:	66 2e 0f 1f 84 00 00 	cs nopw 0x0(%rax,%rax,1)
    108d:	00 00 00

0000000000001090 <deregister_tm_clones>:
    1090:	48 8d 3d 79 2f 00 00 	lea    0x2f79(%rip),%rdi        # 4010 <__TMC_END__>
    1097:	48 8d 05 72 2f 00 00 	lea    0x2f72(%rip),%rax        # 4010 <__TMC_END__>
    109e:	48 39 f8             	cmp    %rdi,%rax
    10a1:	74 15                	je     10b8 <deregister_tm_clones+0x28>
    10a3:	48 8b 05 36 2f 00 00 	mov    0x2f36(%rip),%rax        # 3fe0 <_ITM_deregisterTMCloneTable@Base>
    10aa:	48 85 c0             	test   %rax,%rax
    10ad:	74 09                	je     10b8 <deregister_tm_clones+0x28>
    10af:	ff e0                	jmp    *%rax
    10b1:	0f 1f 80 00 00 00 00 	nopl   0x0(%rax)
    10b8:	c3                   	ret
    10b9:	0f 1f 80 00 00 00 00 	nopl   0x0(%rax)

00000000000010c0 <register_tm_clones>:
    10c0:	48 8d 3d 49 2f 00 00 	lea    0x2f49(%rip),%rdi        # 4010 <__TMC_END__>
    10c7:	48 8d 35 42 2f 00 00 	lea    0x2f42(%rip),%rsi        # 4010 <__TMC_END__>
    10ce:	48 29 fe             	sub    %rdi,%rsi
    10d1:	48 89 f0             	mov    %rsi,%rax
    10d4:	48 c1 ee 3f          	shr    $0x3f,%rsi
    10d8:	48 c1 f8 03          	sar    $0x3,%rax
    10dc:	48 01 c6             	add    %rax,%rsi
    10df:	48 d1 fe             	sar    $1,%rsi
    10e2:	74 14                	je     10f8 <register_tm_clones+0x38>
    10e4:	48 8b 05 05 2f 00 00 	mov    0x2f05(%rip),%rax        # 3ff0 <_ITM_registerTMCloneTable@Base>
    10eb:	48 85 c0             	test   %rax,%rax
    10ee:	74 08                	je     10f8 <register_tm_clones+0x38>
    10f0:	ff e0                	jmp    *%rax
    10f2:	66 0f 1f 44 00 00    	nopw   0x0(%rax,%rax,1)
    10f8:	c3                   	ret
    10f9:	0f 1f 80 00 00 00 00 	nopl   0x0(%rax)

0000000000001100 <__do_global_dtors_aux>:
    1100:	f3 0f 1e fa          	endbr64
    1104:	80 3d 05 2f 00 00 00 	cmpb   $0x0,0x2f05(%rip)        # 4010 <__TMC_END__>
    110b:	75 2b                	jne    1138 <__do_global_dtors_aux+0x38>
    110d:	55                   	push   %rbp
    110e:	48 83 3d e2 2e 00 00 	cmpq   $0x0,0x2ee2(%rip)        # 3ff8 <__cxa_finalize@GLIBC_2.2.5>
    1115:	00
    1116:	48 89 e5             	mov    %rsp,%rbp
    1119:	74 0c                	je     1127 <__do_global_dtors_aux+0x27>
    111b:	48 8b 3d e6 2e 00 00 	mov    0x2ee6(%rip),%rdi        # 4008 <__dso_handle>
    1122:	e8 19 ff ff ff       	call   1040 <__cxa_finalize@plt>
    1127:	e8 64 ff ff ff       	call   1090 <deregister_tm_clones>
    112c:	c6 05 dd 2e 00 00 01 	movb   $0x1,0x2edd(%rip)        # 4010 <__TMC_END__>
    1133:	5d                   	pop    %rbp
    1134:	c3                   	ret
    1135:	0f 1f 00             	nopl   (%rax)
    1138:	c3                   	ret
    1139:	0f 1f 80 00 00 00 00 	nopl   0x0(%rax)

0000000000001140 <frame_dummy>:
    1140:	f3 0f 1e fa          	endbr64
    1144:	e9 77 ff ff ff       	jmp    10c0 <register_tm_clones>

0000000000001149 <greet>:
    1149:	f3 0f 1e fa          	endbr64
    114d:	55                   	push   %rbp
    114e:	48 89 e5             	mov    %rsp,%rbp
    1151:	48 8d 05 ac 0e 00 00 	lea    0xeac(%rip),%rax        # 2004 <_IO_stdin_used+0x4>
    1158:	48 89 c7             	mov    %rax,%rdi
    115b:	e8 f0 fe ff ff       	call   1050 <puts@plt>
    1160:	90                   	nop
    1161:	5d                   	pop    %rbp
    1162:	c3                   	ret

0000000000001163 <main>:
    1163:	f3 0f 1e fa          	endbr64
    1167:	55                   	push   %rbp
    1168:	48 89 e5             	mov    %rsp,%rbp
    116b:	b8 00 00 00 00       	mov    $0x0,%eax
    1170:	e8 d4 ff ff ff       	call   1149 <greet>
    1175:	b8 00 00 00 00       	mov    $0x0,%eax
    117a:	5d                   	pop    %rbp
    117b:	c3                   	ret
```

It converts raw bytes back to assembly mnemonics.

Each line in the disassembly follows this pattern:

```
ADDRESS: MACHINE_CODE    ASSEMBLY_INSTRUCTION    COMMENTS
```

We can see the `_start` label is at address 1060, which matches with the start address mentioned in ELF header.

```bash
$ readelf -h main | grep "Entry point address:"
  Entry point address:               0x1060
```

We can see the definitions of `main` and `greet` functions in assembly. 


We can see `main()` calls `greet()`
`1170: call 1149 <greet>`

`greet()` calls `puts@plt`
`115b: call 1050 <puts@plt>`

`puts@plt` is in `.plt` section (dynamic linking)

`greet()` references string in `.rodata`
`1151: lea 0xeac(%rip),%rax # Points to 0x2004 in .rodata`

(%rip) means RIP-relative addressing. RIP-relative addressing means the address is computed relative to the current instruction pointer.

```
effective_address = current_instruction_address + displacement
effective_address = 0x1151 + 0xEAC = 0x2004
```

We can verify that address falls in the range of `.rodata` section.

```
 [18] .rodata           PROGBITS         0000000000002000  00002000
       0000000000000010  0000000000000000   A       0     0     4
  [19] .eh_frame_hdr     PROGBITS         0000000000002010  00002010
       000000000000003c  0000000000000000   A       0     0     4
```

We can also inspect the `.rodata` section to confirm it

```bash
$  readelf -x .rodata main

Hex dump of section '.rodata':
  0x00002000 01000200 48656c6c 6f2c2045 4c462100 ....Hello, ELF!.
```

### 2. .plt (Procedure Linkage Table)

- **Type:** `SHT_PROGBITS`
- **Flags:** `SHF_ALLOC | SHF_EXECINSTR` (AX)
- **Contains:** Stubs for calling shared library functions

The Procedure Linkage Table (PLT) is a section in ELF executables and shared libraries that enables lazy binding — meaning, external (shared library) functions like printf, puts, or malloc are resolved only when first called, not when the program starts.

When your program calls puts("hi");, the compiler doesn’t know where puts actually lives — it’s defined in the C library (libc.so.6).
So instead of a direct call, it generates a call to a stub in `.plt`.
This stub is responsible for eventually reaching the real puts function in memory.

To inspect the PLT of our program

```bash
$ objdump -d -j .plt main

main:     file format elf64-x86-64


Disassembly of section .plt:

0000000000001020 <.plt>:
    1020:	ff 35 9a 2f 00 00    	push   0x2f9a(%rip)        # 3fc0 <_GLOBAL_OFFSET_TABLE_+0x8>
    1026:	ff 25 9c 2f 00 00    	jmp    *0x2f9c(%rip)        # 3fc8 <_GLOBAL_OFFSET_TABLE_+0x10>
    102c:	0f 1f 40 00          	nopl   0x0(%rax)
    1030:	f3 0f 1e fa          	endbr64
    1034:	68 00 00 00 00       	push   $0x0
    1039:	e9 e2 ff ff ff       	jmp    1020 <_init+0x20>
    103e:	66 90                	xchg   %ax,%ax
```

- The first instruction jumps via the GOT (Global Offset Table).
- The push+jump sequence helps the dynamic linker resolve the symbol the first time it’s used

### 3. .plt.got

- **Type**: `SHT_PROGBITS`
- **Flags**: `SHF_ALLOC | SHF_EXECINSTR` (AX)
- **Contains**: PLT entries for GOT references
  
The `.plt.got` section is an extension of the traditional `.plt`, used primarily in position-independent executables (PIE) and shared libraries.

When the compiler generates smaller or more optimized PLT entries, it sometimes places them in `.plt.got` instead of `.plt`.

These entries rely more directly on the GOT (Global Offset Table) for function address lookups, reducing the indirection and improving performance slightly.

You’ll usually see `.plt.got` in binaries built with:

- GCC’s newer toolchains
- PIE (Position Independent Executable) enabled
- Or with RELRO and lazy binding disabled (`-Wl,-z,now`)

```bash
$ readelf -S main | grep .plt
  [11] .rela.plt         RELA             0000000000000610  00000610
  [13] .plt              PROGBITS         0000000000001020  00001020
  [14] .plt.got          PROGBITS         0000000000001040  00001040
  [15] .plt.sec          PROGBITS         0000000000001050  00001050

```

```bash
$ objdump -d -j .plt.got main

main:     file format elf64-x86-64


Disassembly of section .plt.got:

0000000000001040 <__cxa_finalize@plt>:
    1040:	f3 0f 1e fa          	endbr64
    1044:	ff 25 ae 2f 00 00    	jmp    *0x2fae(%rip)        # 3ff8 <__cxa_finalize@GLIBC_2.2.5>
    104a:	66 0f 1f 44 00 00    	nopw   0x0(%rax,%rax,1)
```

You’ll find shorter stubs, sometimes just a single indirect jump via the GOT — because by this point, all symbols are already resolved.

### 4. .plt.sec

- **Type:** `SHT_PROGBITS`
- **Flags:** `SHF_ALLOC | SHF_EXECINSTR` (AX)
- **Contains:** Secure PLT stubs (used in hardened binaries)

The `.plt.sec` section is a **security-enhanced variant** of the traditional `.plt`.
It’s introduced in **modern toolchains** (GCC ≥ 9, binutils ≥ 2.31) to support **Control Flow Integrity (CFI)** and **Intel’s Indirect Branch Tracking (IBT)** features.

Each entry in `.plt.sec` is similar to a normal PLT stub, but with additional instructions or metadata to **prevent malicious redirection of function calls** — protecting against attacks like **Return-Oriented Programming (ROP)** or **GOT overwrite exploits**.

You’ll usually see `.plt.sec` when your binary is built with flags like:

```bash
-fpie -fcf-protection=full -O2
```

---


```bash
$ readelf -S main | grep .plt
  [13] .plt              PROGBITS         0000000000001030  00001030
  [14] .plt.got          PROGBITS         0000000000001060  00001060
  [15] .plt.sec          PROGBITS         0000000000001080  00001080
```

Disassembly (simplified example):

```bash
$ objdump -d -j .plt.sec main

main:     file format elf64-x86-64


Disassembly of section .plt.sec:

0000000000001050 <puts@plt>:
    1050:	f3 0f 1e fa          	endbr64
    1054:	ff 25 76 2f 00 00    	jmp    *0x2f76(%rip)        # 3fd0 <puts@GLIBC_2.2.5>
    105a:	66 0f 1f 44 00 00    	nopw   0x0(%rax,%rax,1)
```

The `endbr64` instruction (added by GCC for IBT) is used to mark safe entry points for indirect jumps — the CPU validates that control flow only transfers to legitimate call targets.

## Data Sections

### 1. .rodata - Read-Only Data

- **Type**: `SHT_PROGBITS`
- **Flags**: `SHF_ALLOC` (A)
- **Contains**: Constants, string literals

```c
const char *msg = "Hello, World!";  // String stored in .rodata
const int max = 100; 
```

```bash
$ readelf -x .rodata main

Hex dump of section '.rodata':
  0x00002000 01000200 48656c6c 6f2c2045 4c462100 ....Hello, ELF!.
```

The `.rodata` section stores data that should never be modified at runtime.
Typical contents include:
- String literals ("Hello, ELF!")
- const variables in C/C++
- Floating-point constants
- Lookup or jump tables generated by the compiler

Because it’s read-only, this section is usually mapped into memory with read-only permissions (R-) by the OS loader.

This prevents accidental modification and improves security — if a program tries to modify it, it will trigger a segmentation fault.

### 2. .data - Initialized Data

- **Type**: `SHT_PROGBITS`
- **Flags**: `SHF_WRITE | SHF_ALLOC` (WA)
- **Contains**: Initialized global and static variables

The `.data` section stores all read–write variables whose initial values are known at compile time.
These variables are part of the executable image — the compiler embeds their initial values directly into the ELF file.
When the program loads into memory, the loader copies these values into writable memory so your program can modify them at runtime.

```c
int global_var = 42;           // Stored in .data
static int static_var = 100;   // Stored in .data
```



### 3. .bss — Uninitialized Data

* **Type:** `SHT_NOBITS`
* **Flags:** `SHF_WRITE | SHF_ALLOC` (WA)
* **Contains:** Uninitialized global and static variables (default-initialized to zero)

The `.bss` section holds **variables that exist for the lifetime of the program** (global or static), but **don’t have explicit initial values** in your source code.
Unlike `.data`, this section **does not occupy any space in the ELF file itself** — only the *size* is recorded.
When the program loads, the OS automatically allocates memory for `.bss` and **fills it with zeros**.

---

Example

```c
int global_uninit;          // Goes into .bss
static int static_uninit;   // Goes into .bss

int main() {
    return global_uninit;   // Initially 0
}
```

Inspect:

```bash
$ gcc -o main main.c
$ readelf -S main | grep .bss
  [25] .bss              NOBITS           0000000000004000  00003010
```

Notice the **`NOBITS`** type — that means no bytes are actually stored in the file; only the *size* (number of bytes required) is recorded.

If you dump it:

```bash
$ readelf -x .bss main
readelf: Warning: Section '.bss' has no data to dump.
```

That’s because `.bss` doesn’t exist in the binary — it’s just a placeholder for the loader.

---

**What Happens at Runtime**

1. The loader allocates memory for `.bss` variables.
2. It initializes all bytes to **zero** (per the C standard).
3. The variables behave like normal globals at runtime.

## Dynamic Linking Sections

### 1. .got (Global Offset Table)

- **Type**: `SHT_PROGBITS`
- **Flags**: `SHF_WRITE | SHF_ALLOC` (WA)
- **Contains**: Addresses of global variables and dynamically linked functions

The Global Offset Table (GOT) is a key structure used in Position-Independent Code (PIC).
When your program accesses a global variable or calls an external function, it doesn’t use a hardcoded address — instead, it looks it up through the GOT.

Each GOT entry holds the actual runtime address of a symbol (variable or function).
This indirection allows the program to be loaded at any memory address, which is essential for shared libraries and modern systems using ASLR (Address Space Layout Randomization).
  
Used for position-independent code to access global variables.

```bash
$ readelf -r main

Relocation section '.rela.dyn' at offset 0x550 contains 8 entries:
  Offset          Info           Type           Sym. Value    Sym. Name + Addend
000000003db8  000000000008 R_X86_64_RELATIVE                    1140
000000003dc0  000000000008 R_X86_64_RELATIVE                    1100
000000004008  000000000008 R_X86_64_RELATIVE                    4008
000000003fd8  000100000006 R_X86_64_GLOB_DAT 0000000000000000 __libc_start_main@GLIBC_2.34 + 0
000000003fe0  000200000006 R_X86_64_GLOB_DAT 0000000000000000 _ITM_deregisterTM[...] + 0
000000003fe8  000400000006 R_X86_64_GLOB_DAT 0000000000000000 __gmon_start__ + 0
000000003ff0  000500000006 R_X86_64_GLOB_DAT 0000000000000000 _ITM_registerTMCl[...] + 0
000000003ff8  000600000006 R_X86_64_GLOB_DAT 0000000000000000 __cxa_finalize@GLIBC_2.2.5 + 0

Relocation section '.rela.plt' at offset 0x610 contains 1 entry:
  Offset          Info           Type           Sym. Value    Sym. Name + Addend
000000003fd0  000300000007 R_X86_64_JUMP_SLO 0000000000000000 puts@GLIBC_2.2.5 + 0
```

The entries there correspond to addresses stored in .got that are updated by the dynamic linker when the program starts.

**What are these `.rela.dyn` and `.rela.plt` sections?**

Both are their own types of ELF sections that hold relocation entries.

| Section     | Type       | Purpose                                                                    |
| ----------- | ---------- | -------------------------------------------------------------------------- |
| `.rela.dyn` | `SHT_RELA` | Relocations for global/static **data** (in `.data`, `.got`, etc.)          |
| `.rela.plt` | `SHT_RELA` | Relocations for **function calls** (entries in `.got.plt`, used by `.plt`) |


In short:

- `.rela.dyn` → data relocations
- `.rela.plt` → function relocations

Both are processed by the dynamic linker (`ld.so`) at program startup or during lazy binding.

All the offsets shown in `.rela.dyn` and `.rela.plt` refer to memory locations that will be part of the Global Offset Table (GOT) in your process at runtime.

The GOT is just a table of addresses.
Before relocation, entries may be zero or placeholders.
After relocation, the dynamic linker fills them with real addresses of variables or functions.

### 2. Here’s a nicely written section for your blog on **`.got.plt`**, consistent with your other ELF notes 👇

---

### 2. .got.plt — Global Offset Table for PLT

* **Type:** `SHT_PROGBITS`
* **Flags:** `SHF_WRITE | SHF_ALLOC` (WA)
* **Contains:** Addresses of dynamically linked functions used by the PLT

The `.got.plt` section is a special part of the **Global Offset Table (GOT)** that works hand-in-hand with the **Procedure Linkage Table (PLT)**.

When your program calls an external function (like `puts`, `printf`, or `malloc`), it doesn’t know their real addresses at compile time. Instead, it goes through a small trampoline in `.plt`, which uses the `.got.plt` entries to eventually reach the actual function in the shared library.

**How It Works**

- Each entry in `.got.plt` holds the **runtime-resolved address** of an external function.
- Initially, these entries point to the **PLT stubs** (so the dynamic linker can intercept the first call).
- After the function is resolved, the dynamic linker **updates the GOT entry** with the real function address — so the next call goes directly there.

This mechanism enables **lazy binding** — external symbols are resolved only when first used, improving startup performance.

Example

```bash
$ readelf -x .got.plt main

Hex dump of section '.got.plt':
  0x00003fb8  00000000 00000000 00000000 00000000  ................
  0x00003fc8  00000000 00000000 b5110000 00000000  ................
```

And from the relocation table:

```bash
$ readelf -r main | grep plt

000000003fd0  000300000007 R_X86_64_JUMP_SLOT  puts@GLIBC_2.2.5 + 0
```

This means:

- The entry at address `0x3fd0` in `.got.plt` corresponds to the symbol `puts`.
- The relocation type `R_X86_64_JUMP_SLOT` tells the dynamic linker to fill this slot with the runtime address of `puts()` when first called.

### 3. .dynamic

- **Type**: `SHT_DYNAMIC`
- **Flags**: `SHF_WRITE | SHF_ALLOC` (WA)
- **Contains**: Dynamic linking information

When you compile a dynamically linked program (default in Linux), the compiler embeds a `.dynamic` section in your binary.
This section acts as a directory of pointers and configuration values that tell the dynamic linker:
  
Array of `Elf64_Dyn` structures containing tags like:
- `DT_NEEDED`: Required shared libraries
- `DT_SYMTAB`: Address of symbol table
- `DT_STRTAB`: Address of string table
- `DT_RELA`: Address of relocation table


```bash

$ readelf -d main

Dynamic section at offset 0x2dc8 contains 27 entries:
  Tag        Type                         Name/Value
 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]
 0x000000000000000c (INIT)               0x1000
 0x000000000000000d (FINI)               0x117c
 0x0000000000000019 (INIT_ARRAY)         0x3db8
 0x000000000000001b (INIT_ARRAYSZ)       8 (bytes)
 0x000000000000001a (FINI_ARRAY)         0x3dc0
 0x000000000000001c (FINI_ARRAYSZ)       8 (bytes)
 0x000000006ffffef5 (GNU_HASH)           0x3b0
 0x0000000000000005 (STRTAB)             0x480
 0x0000000000000006 (SYMTAB)             0x3d8
 0x000000000000000a (STRSZ)              141 (bytes)
 0x000000000000000b (SYMENT)             24 (bytes)
 0x0000000000000015 (DEBUG)              0x0
 0x0000000000000003 (PLTGOT)             0x3fb8
 0x0000000000000002 (PLTRELSZ)           24 (bytes)
 0x0000000000000014 (PLTREL)             RELA
 0x0000000000000017 (JMPREL)             0x610
 0x0000000000000007 (RELA)               0x550
 0x0000000000000008 (RELASZ)             192 (bytes)
 0x0000000000000009 (RELAENT)            24 (bytes)
 0x000000000000001e (FLAGS)              BIND_NOW
 0x000000006ffffffb (FLAGS_1)            Flags: NOW PIE
 0x000000006ffffffe (VERNEED)            0x520
 0x000000006fffffff (VERNEEDNUM)         1
 0x000000006ffffff0 (VERSYM)             0x50e
 0x000000006ffffff9 (RELACOUNT)          3
 0x0000000000000000 (NULL)               0x0
 ```

At runtime, the loader (`ld-linux.so`) reads these entries to correctly link your program with shared libraries before it starts executing `main()`.

## Symbol and String Tables

### 1. .symtab - Symbol Table

- Type: `SHT_SYMTAB`
- Flags: None (not loaded)
- Contains: All symbols (functions, global/static variables) used for linking and debugging

The `.symtab` section holds a table of symbols that represent every significant entity in your program — functions, variables, and sections.

Each entry is an `Elf64_Sym` structure:

```c
typedef struct {
  Elf64_Word    st_name;   // Symbol name (string table offset)
  unsigned char st_info;   // Type and binding
  unsigned char st_other;  // Visibility
  Elf64_Half    st_shndx;  // Section index
  Elf64_Addr    st_value;  // Symbol value (address)
  Elf64_Xword   st_size;   // Symbol size
} Elf64_Sym;
```

**How it’s used**

- The linker uses `.symtab` to match symbol definitions (e.g., `int x`;) with their references (e.g., `extern int x`;) across multiple object files.
- Each symbol name in `.symtab` corresponds to an offset in the `.strtab` (string table) section, where actual names are stored.

```bash
$ readelf -s main | head

Symbol table '.dynsym' contains 7 entries:
   Num:    Value          Size Type    Bind   Vis      Ndx Name
     0: 0000000000000000     0 NOTYPE  LOCAL  DEFAULT  UND
     1: 0000000000000000     0 FUNC    GLOBAL DEFAULT  UND _[...]@GLIBC_2.34 (2)
     2: 0000000000000000     0 NOTYPE  WEAK   DEFAULT  UND _ITM_deregisterT[...]
     3: 0000000000000000     0 FUNC    GLOBAL DEFAULT  UND puts@GLIBC_2.2.5 (3)
     4: 0000000000000000     0 NOTYPE  WEAK   DEFAULT  UND __gmon_start__
     5: 0000000000000000     0 NOTYPE  WEAK   DEFAULT  UND _ITM_registerTMC[...]
     6: 0000000000000000     0 FUNC    WEAK   DEFAULT  UND [...]@GLIBC_2.2.5 (3)
```

**Interpretation:**

- **Type**: Describes what the symbol is (FUNC, OBJECT, etc.)
- **Bind**: Whether it’s LOCAL (visible only in file) or GLOBAL (visible to linker)
- **Ndx**: Section index where the symbol is defined (e.g., .text, .data)
- **Value**: Its address (if defined)
- **Name**: Symbol name (resolved from .strtab)


Here’s the detailed explanation for **`.strtab` (String Table)**:

### 2. .strtab – String Table

* **Type**: `SHT_STRTAB`
* **Flags**: *(none)* (not loaded into memory)
* **Contains**: Null-terminated strings used by other sections like `.symtab` and relocation entries.

Each symbol in `.symtab` doesn’t store its name directly — instead, the `st_name` field holds an **offset** into `.strtab`, where the actual string (symbol name) is stored.

Example

Suppose you have these symbols:

```c
int var;
void func() {}
```

The `.symtab` entries might look like this:

| Symbol | st_name (offset) | st_value | ... |
| ------ | ---------------- | -------- | --- |
| var    | 0x00             | 0x601000 | ... |
| func   | 0x04             | 0x401020 | ... |

And the `.strtab` will actually contain:

```
0x00: "var\0func\0"
```

Notes

- `.strtab` appears **alongside `.symtab`**, used mainly by the **linker and debugger**, not at runtime.
- It’s **not loaded into memory** (unlike `.rodata` or `.data`).
- There’s often also a **`.shstrtab`** — the *section header string table*, which stores **section names** (like `.text`, `.data`, `.bss`).


### 3. .dynstr – Dynamic String Table

* **Type**: `SHT_STRTAB`
* **Flags**: `SHF_ALLOC` (A) — loaded into memory
* **Contains**: Null-terminated strings used **by dynamic linking sections** such as `.dynsym`, `.rela.plt`, and `.dynamic`.


**Purpose**

`.dynstr` serves the same purpose as `.strtab`, but only for **symbols needed at runtime** — i.e., dynamic symbols that the loader (`ld.so`) must resolve when the program is loaded.



**Example**

If your program uses shared libraries like:

```c
printf("Hi");
```

Then the **dynamic symbol table (`.dynsym`)** will contain an entry for `printf`,
and its `st_name` field will point to an offset inside `.dynstr`:

| Symbol | st_name (offset) | st_value | ... |
| ------ | ---------------- | -------- | --- |
| printf | 0x00             | 0x0000   | ... |

And `.dynstr` will contain:

```
0x00: "printf\0libc.so.6\0"
```

Comparison

| Section   | Used By                  | Loaded? | Contains        | Purpose                          |
| --------- | ------------------------ | ------- | --------------- | -------------------------------- |
| `.strtab` | Linker / Debugger        | ❌       | All symbols     | For static linking and debugging |
| `.dynstr` | Runtime linker (`ld.so`) | ✅       | Dynamic symbols | For dynamic linking              |

