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

When your program calls `puts("hi");`, the compiler doesn’t know where puts actually lives — it’s defined in the C library (`libc.so.6`). So instead of a direct call, it generates a call to a stub in `.plt`.
This stub is responsible for eventually reaching the real puts function in memory.

Despite the name "Procedure Linkage Table", the PLT is NOT a table - it's continuous executable code (an array of small code stubs).

```
.plt section (executable code):
┌─────────────────────────────────┐
│ PLT[0]: Resolver stub (code)    │  ← 16 bytes of code
├─────────────────────────────────┤
│ PLT[1]: printf stub (code)      │  ← 16 bytes of code
├─────────────────────────────────┤
│ PLT[2]: malloc stub (code)      │  ← 16 bytes of code
├─────────────────────────────────┤
│ PLT[3]: free stub (code)        │  ← 16 bytes of code
└─────────────────────────────────┘
```

Each "entry" is a small function (code snippet), not a data structure.

#### PLT Entry "Format" 

Each PLT entry is 16 bytes of x86-64 assembly:

```
# Generic PLT entry format (16 bytes):
<function@plt>:
   0: endbr64              # 4 bytes - security feature
   4: jmp    *GOT[n]       # 6 bytes - indirect jump through GOT
  10: push   $index        # 5 bytes - push relocation index
  15: jmp    PLT[0]        # 5 bytes - jump to resolver
  (total: 16 bytes, but padding makes them aligned)
```

**Why It's Called a "Table"**

Historical reasons! It's organized like a table:
- **Fixed-size entries** (16 bytes each)
- **Array-like access** (PLT[0], PLT[1], PLT[2]...)
- **Indexed by relocation number**

Let's take this C program

```c
#include <stdio.h>
#include <stdlib.h>

int main() {
    printf("Before malloc\n");

    void *ptr = malloc(100);
    printf("Allocated at: %p\n", ptr);

    free(ptr);
    printf("After free\n");

    return 0;
}
```

We can get its `.plt` by 

```bash
$ objdump -d -j .plt demo

demo:     file format elf64-x86-64


Disassembly of section .plt:

0000000000401020 <.plt>:
  401020:	ff 35 ca 2f 00 00    	push   0x2fca(%rip)        # 403ff0 <_GLOBAL_OFFSET_TABLE_+0x8>
  401026:	ff 25 cc 2f 00 00    	jmp    *0x2fcc(%rip)        # 403ff8 <_GLOBAL_OFFSET_TABLE_+0x10>
  40102c:	0f 1f 40 00          	nopl   0x0(%rax)
  401030:	f3 0f 1e fa          	endbr64
  401034:	68 00 00 00 00       	push   $0x0
  401039:	e9 e2 ff ff ff       	jmp    401020 <_init+0x20>
  40103e:	66 90                	xchg   %ax,%ax
  401040:	f3 0f 1e fa          	endbr64
  401044:	68 01 00 00 00       	push   $0x1
  401049:	e9 d2 ff ff ff       	jmp    401020 <_init+0x20>
  40104e:	66 90                	xchg   %ax,%ax
  401050:	f3 0f 1e fa          	endbr64
  401054:	68 02 00 00 00       	push   $0x2
  401059:	e9 c2 ff ff ff       	jmp    401020 <_init+0x20>
  40105e:	66 90                	xchg   %ax,%ax
  401060:	f3 0f 1e fa          	endbr64
  401064:	68 03 00 00 00       	push   $0x3
  401069:	e9 b2 ff ff ff       	jmp    401020 <_init+0x20>
  40106e:	66 90                	xchg   %ax,%ax

$ readelf -r demo

Relocation section '.rela.dyn' at offset 0x518 contains 2 entries:
  Offset          Info           Type           Sym. Value    Sym. Name + Addend
000000403fd8  000200000006 R_X86_64_GLOB_DAT 0000000000000000 __libc_start_main@GLIBC_2.34 + 0
000000403fe0  000500000006 R_X86_64_GLOB_DAT 0000000000000000 __gmon_start__ + 0

Relocation section '.rela.plt' at offset 0x548 contains 4 entries:
  Offset          Info           Type           Sym. Value    Sym. Name + Addend
000000404000  000100000007 R_X86_64_JUMP_SLO 0000000000000000 free@GLIBC_2.2.5 + 0
000000404008  000300000007 R_X86_64_JUMP_SLO 0000000000000000 puts@GLIBC_2.2.5 + 0
000000404010  000400000007 R_X86_64_JUMP_SLO 0000000000000000 printf@GLIBC_2.2.5 + 0
000000404018  000600000007 R_X86_64_JUMP_SLO 0000000000000000 malloc@GLIBC_2.2.5 + 0
```



Let's analyze this output

```
PLT[0]: Resolver (0x401020)      ← Common trampoline
PLT[1]: free   (0x401030)        
PLT[2]: puts   (0x401040)     
PLT[3]: printf     (0x401050)
PLT[3]: malloc     (0x401050)     

```

#### PLT[0] - The Resolver Trampoline (0x401020)

```
0000000000401020 <.plt>:
  401020: ff 35 ca 2f 00 00    push   0x2fca(%rip)    # 403ff0 <_GLOBAL_OFFSET_TABLE_+0x8>
  401026: ff 25 cc 2f 00 00    jmp    *0x2fcc(%rip)   # 403ff8 <_GLOBAL_OFFSET_TABLE_+0x10>
  40102c: 0f 1f 40 00          nopl   0x0(%rax)
```

1. `push 0x2fca(%rip)` → Pushes `GOT[1]` (link_map structure)
  - Address: `0x401020 + 6 + 0x2fca = 0x403ff0`
  - This is `_GLOBAL_OFFSET_TABLE_+0x8` (GOT[1])
  - Contains runtime info about loaded libraries

2. `jmp *0x2fcc(%rip)` → Jumps to `GOT[2]` (resolver function)
  - Address: `0x401026 + 6 + 0x2fcc = 0x403ff8`
  - This is `_GLOBAL_OFFSET_TABLE_+0x10` (GOT[2])
  - Contains address of `_dl_runtime_resolve` in `ld.so`

3. `nopl` → Padding/alignment

#### The subsequent PLT entries (PLT1, PLT2, etc.)

Example: `PLT1` (for `free`):

```
401030: f3 0f 1e fa           endbr64
401034: 68 00 00 00 00        push   $0x0
401039: e9 e2 ff ff ff        jmp    401020 <.plt>
```

Breakdown:
- `endbr64` - security
- `push $0x0` — push the function index (here 0 → corresponds to first relocation entry).
- `jmp 401020` — jump back to `PLT0`, which will now use that index to find the corresponding GOT entry (GOT[3] onwards).
- `xchg %ax,%ax` - Padding (2-byte NOP)

Now let's track the entre process 

If we disassemble the code, we can see the call to printf jumps to address `0x401090`
```
  4011d5:	e8 b6 fe ff ff       	call   401090 <printf@plt>
```

The address `0x401090` falls inside `.plt.sec` section. Modern GCC uses .plt.sec (PLT secondary) for Intel CET (Control-flow Enforcement Technology).

```
sanketh@sanketh-81de:~/assembly/plt$ objdump -d -j .plt.sec demo

demo:     file format elf64-x86-64


Disassembly of section .plt.sec:

0000000000401070 <free@plt>:
  401070:	f3 0f 1e fa          	endbr64
  401074:	ff 25 86 2f 00 00    	jmp    *0x2f86(%rip)        # 404000 <free@GLIBC_2.2.5>
  40107a:	66 0f 1f 44 00 00    	nopw   0x0(%rax,%rax,1)

0000000000401080 <puts@plt>:
  401080:	f3 0f 1e fa          	endbr64
  401084:	ff 25 7e 2f 00 00    	jmp    *0x2f7e(%rip)        # 404008 <puts@GLIBC_2.2.5>
  40108a:	66 0f 1f 44 00 00    	nopw   0x0(%rax,%rax,1)

0000000000401090 <printf@plt>:
  401090:	f3 0f 1e fa          	endbr64
  401094:	ff 25 76 2f 00 00    	jmp    *0x2f76(%rip)        # 404010 <printf@GLIBC_2.2.5>
  40109a:	66 0f 1f 44 00 00    	nopw   0x0(%rax,%rax,1)

00000000004010a0 <malloc@plt>:
  4010a0:	f3 0f 1e fa          	endbr64
  4010a4:	ff 25 6e 2f 00 00    	jmp    *0x2f6e(%rip)        # 404018 <malloc@GLIBC_2.2.5>
  4010aa:	66 0f 1f 44 00 00    	nopw   0x0(%rax,%rax,1)
```

Our binary has **two PLT-related sections:**

 **1. `.plt` - Lazy binding resolver stubs**
```
0x401020: PLT[0] - Common resolver
0x401030: PLT[1] - free resolver stub
0x401040: PLT[2] - puts resolver stub  
0x401050: PLT[3] - printf resolver stub
0x401060: PLT[4] - malloc resolver stub
```

 **2. `.plt.sec` - Actual PLT entries (with CET security)**
```
0x401070: free@plt
0x401080: puts@plt
0x401090: printf@plt  ← Your code calls this!
0x4010a0: malloc@plt
```

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
- **Contains**: Holds addresses of global variables and dynamically linked functions used by position-independent code (PIC).


In Position-Independent Code (PIC) — used in shared libraries and ASLR-enabled executables, the compiler cannot assume any fixed address for globals or external functions. Instead of hardcoding addresses, the code goes through an indirect table of addresses called the Global Offset Table (GOT).

Each GOT entry holds the actual runtime address of a symbol (variable or function). At runtime, the dynamic linker (`ld.so`) fills in the correct addresses so that your program can access everything correctly no matter where it’s loaded in memory.

#### GOT Entry Format

The GOT is just a contiguous array of addresses.
Each entry is 8 bytes (on x86-64):

```c
typedef struct {
    Elf64_Addr address;   // The resolved runtime address of the symbol
} GOTEntry;
```

So effectively:

```bash
.got:
  +0x00 -> address of _DYNAMIC
  +0x08 -> address of __libc_start_main
  +0x10 -> address of puts
  ...
```

But logically we can think of GOT as 

```bash
| Symbol              | GOT Entry (before relocation) | GOT Entry (after relocation) |
| ------------------- | ----------------------------- | ---------------------------- |
| `puts@GLIBC_2.2.5`  | 0x0000000000000000            | 0x00007ffff7e2e6b0           |
| `__libc_start_main` | 0x0000000000000000            | 0x00007ffff7e1e170           |
| `global_var`        | 0x0000000000000000            | 0x0000555555556020           |
```

**If GOT is just a list of addresses, then how does linker know which address maps to which symbol?**

The relocation entries map GOT addresses to symbols.

Each relocation entry says:

```bash
Offset: 0x3fc0          ← GOT entry address
Symbol: malloc          ← What symbol this entry is for
Type: R_X86_64_JUMP_SLOT
```

So the dynamic linker knows: "GOT entry at address 0x3fc0 should contain the address of malloc"

We will dive deep into relocations in later parts. 

#### How the GOT Gets Filled?

1. **Compiler phase:** Generates code with placeholders referring to GOT offsets.
2. **Linker phase (`ld`):** Emits relocation entries:
   - `.rela.dyn` → global variables and data symbols
   - `.rela.plt` → functions called through the PLT
3. **Runtime (`ld.so`):** When the program loads:
   - Reads relocations from `.rela.dyn` and `.rela.plt`
   - Writes real addresses into `.got` and `.got.plt` entries



### 2. .got.plt — Global Offset Table for PLT

* **Type:** `SHT_PROGBITS`
* **Flags:** `SHF_WRITE | SHF_ALLOC` (WA)
* **Contains:** Addresses of dynamically linked functions used by the PLT

The `.got.plt` section is a special part of the **Global Offset Table (GOT)** that works hand-in-hand with the **Procedure Linkage Table (PLT)**. When the linker creates a PLT (Procedure Linkage Table), it also allocates a small .got.plt table alongside it.


When your program calls an external function (like `puts`, `printf`, or `malloc`), it doesn’t know their real addresses at compile time. Instead, it goes through a small trampoline in `.plt`, which uses the `.got.plt` entries to eventually reach the actual function in the shared library.

**How It Works**

- Each entry in `.got.plt` holds the **runtime-resolved address** of an external function.
- Initially, these entries point to the **PLT stubs** (so the dynamic linker can intercept the first call).
- After the function is resolved, the dynamic linker **updates the GOT entry** with the real function address — so the next call goes directly there.

This mechanism enables **lazy binding** — external symbols are resolved only when first used, improving startup performance.

The first 3 entries in `.got.plt` are reserved for the dynamic linker’s internal use:

| GOT Entry  | Initially Contains                                                        | Purpose / Explanation                                                                                                                                                                                                                                                                                 |
| ---------- | ------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **GOT[0]** | Address of `_DYNAMIC` section                                             | Points to the `.dynamic` section of the current ELF object. This section holds metadata like needed shared libraries, symbol tables, relocation info, etc. The dynamic linker uses this to locate all dynamic linking data for the object being relocated.                                            |
| **GOT[1]** | Address of the `link_map` structure (set at runtime by `ld.so`)           | Each loaded shared object (executable or `.so`) has a `link_map` entry describing it — base address, name, dependencies, relocation tables, etc. The dynamic linker uses GOT[1] to know *which object’s context* it’s resolving symbols for when a lazy PLT call happens.                             |
| **GOT[2]** | Address of `dl_runtime_resolve` (or `dl_runtime_resolve_xsave` on x86_64) | This is the resolver function inside `ld.so`. When a function call through the PLT occurs for the first time, control jumps through PLT[0], which uses GOT[2] to call the resolver. The resolver looks up the symbol, fixes the GOT entry for future calls, and finally jumps to the actual function. |

After these 3, the remaining GOT entries in `.got.plt` correspond to function symbols (e.g. `printf`, `malloc`, etc.), one per PLT entry.

#### How they’re used during lazy binding

When a program calls a function (say `printf`) for the first time:

1. The call goes through the **PLT** (Procedure Linkage Table).
2. The first PLT entry (`PLT[0]`) is special — it sets up a call like this (simplified):
   ```
   jmp *GOT[2]          # Jump to the dynamic resolver (ld.so)
   pushq $reloc_index   # Index of the relocation to resolve
   jmp *GOT[1]          # Linker uses link_map + reloc_index
   ```
3. The resolver (`dl_runtime_resolve`) uses:
  - **GOT[1]** → to find the `link_map` of the current object
  - **GOT[0]** → to access `_DYNAMIC` metadata if needed
4. It then patches the GOT entry for `printf` with its actual address.
5. Future calls to `printf` jump directly to the resolved address — no more resolver overhead.




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

## Relocations

Relocation sections follow the pattern:` .rela.<target_section>` or `.rel.<target_section>`

Each `.rela.*` section contains relocations that need to be applied to a specific target section. However, relocations serve different purposes depending on when and how they're resolved.

**Why do we need them?**

When compiling a single `.o` file, the compiler doesn't know:

- Where other functions will be located (like `printf`, `helper_function`)
- Where data from other files will be
- What the final memory layout will be after linking
- Where the code itself will be loaded in memory

So the compiler:

1. Puts placeholder values (usually zeros) in the machine code
2. Creates relocation entries that tell the linker how to fix these placeholders

### Anatomy of a relocation entry

Each entry has these fields:

```bash
Offset: 0x000000002f
Info: 000600000004
Type: R_X86_64_PLT32
Sym. Value: 0000000000000000
Sym. Name: add_numbers
Addend: -4
```

**1. Offset**
- **Where** in the target section to apply the patch
- For `.rela.text`: offset within `.text` section
- This is the location of the placeholder bytes

**2. Type**
- **How** to calculate the patch value
- Different types = different formulas

Common types

| Relocation           | Description                             | Typical Use                                                             |
| -------------------- | --------------------------------------- | ----------------------------------------------------------------------- |
| `R_X86_64_64`        | Absolute 64-bit address                 | Global/static data, function pointers                                   |
| `R_X86_64_PC32`      | 32-bit PC-relative address              | References to globals or functions (when in same module)                |
| `R_X86_64_PLT32`     | 32-bit PC-relative address to PLT entry | Function calls to external symbols                                      |
| `R_X86_64_GOT32`     | 32-bit offset to GOT entry              | Access via GOT (rare now, replaced by `GOTPCREL`)                       |
| `R_X86_64_GOTPCREL`  | 32-bit PC-relative offset to GOT entry  | Access to globals through GOT (PIC/PIE code)                            |
| `R_X86_64_GLOB_DAT`  | Set GOT entry to absolute address       | Used in dynamic linking (e.g. for globals)                              |
| `R_X86_64_JUMP_SLOT` | Set PLT entry to function address       | Used by dynamic linker for function calls                               |
| `R_X86_64_RELATIVE`  | Adjust by base address                  | Used by dynamic loader for position-independent executables             |
| `R_X86_64_COPY`      | Copy data from shared object            | Used for global variables defined in executable and shared in libraries |


**3. Symbol Name**
- **What** symbol this relocation refers to
- Could be a function name, section name, or variable name
- Linker looks up where this symbol ended up

**4. Addend**
- **Extra offset** to add to the calculation
- Often `-4` for PC-relative calls (compensates for instruction size)

**5. Info** (encoded field)
- Contains both the symbol table index and type
- You usually ignore this - `readelf` decodes it for you


### Relocation Categories

#### 1. Static/Link-Time Relocations

Resolved by the static linker (`ld`) when creating the executable.

These appear in `.o` (object) files and are resolved during the linking phase. Once linking is complete, these sections are removed from the final executable.

| Relocation Section     | Applies To       | Contains Relocations For                                | When Resolved |
|-------------------------|------------------|-----------------------------------------------------------|----------------|
| `.rela.text`            | `.text` section  | Function calls, data references in code                  | Link time      |
| `.rela.data`            | `.data` section  | Pointers in initialized global variables                 | Link time      |
| `.rela.rodata`          | `.rodata` section| Pointers in constant data (e.g., string arrays)           | Link time      |
| `.rela.eh_frame`        | `.eh_frame` section | Exception handling metadata, stack unwinding          | Link time      |
| `.rela.init_array`      | `.init_array` section | Constructor function pointers                        | Link time      |
| `.rela.fini_array`      | `.fini_array` section | Destructor function pointers                          | Link time      |

**What happens:**

- Compiler creates these when generating `.o` files
- Static linker (`ld`) reads these relocations
- Patches the placeholder bytes with calculated addresses
- Removes these sections from the final executable

#### 2. Runtime/Dynamic Relocations

Resolved by the dynamic linker (`ld.so`) when loading the program

These appear in dynamically linked executables and shared libraries. They are kept in the binary because they must be processed every time the program runs (due to ASLR and shared library loading).

| Relocation Section | Applies To             | Contains Relocations For                            | When Resolved                                   |
|--------------------|------------------------|-----------------------------------------------------|------------------------------------------------|
| `.rela.dyn`        | `.got`, `.data`, `.bss`| Global variables, data pointers, GOT entries        | Program startup                                |
| `.rela.plt`        | `.got.plt` (or merged `.got`) | Function calls through PLT/GOT               | Lazy binding (on first call) or at startup     |


**What happens:**
- Present in the final executable
- Dynamic linker (`ld.so`) processes them at runtime
- Adjusts for ASLR (random base address)
- Resolves symbols from shared libraries
- **Sections remain** (needed for every program execution)

#### 3. Complete Relocation Process

**Initial State (After Loading, Before Any Calls)**

- Each external function has three related components:
  - A `.plt.sec` entry (small code stub)
  - A `.plt` resolver stub (fallback code)
  - A `.got.plt` entry (8-byte address slot)
- All GOT entries initially point to the `.plt` (`PLT[0]`) resolver stubs, not to real functions
The dynamic linker has filled `GOT[1]` (link_map) and `GOT[2]` (`_dl_runtime_resolve`)

**First Call to an External Function**

1. Code calls `printf@plt` (jumps to `.plt.sec` entry)
2. `.plt.sec` stub contains the jump to `.got.plt` entry for that function (address in `.got.plt` is present in relocation for that function)
3. `.got.plt` still contains stub which takes it to the corresponding entry for that function in `.plt`
4. `.plt` entry will push the relocation index for that function and jump to PLT resolver at PLT[0]
5. Resolver stub pushes relocation index (identifies which function) and jumps to `PLT[0]` (common resolver trampoline)
6. `PLT[0]` pushes `GOT[1]` (context) and jumps through `GOT[2]` (to dynamic linker)
7. Dynamic linker receives control with relocation index and context
8. Dynamic linker looks up the function symbol in loaded shared libraries
9. Dynamic linker finds function address in appropriate library (e.g., libc.so)
10. Dynamic linker writes real function address into the `.got.plt` entry (key step!)
11. Dynamic linker jumps to the real function and returns to caller

**Subsequent Calls to Same function**

1. Code calls `printf@plt` (jumps to `.plt.sec` entry)
2. `.plt.sec` stub jumps to the entry in `.got.plt`
3. `.got.plt` now contains real function address → lands directly in the function
4.  Function executes and returns to call

```c
// demo.c
#include <stdio.h>
#include <stdlib.h>

int main() {
    printf("Before malloc\n");

    void *ptr = malloc(100);
    printf("Allocated at: %p\n", ptr);

    free(ptr);
    printf("After free\n");

    return 0;
}
```

This is the section header table

```
$ readelf -S demo
There are 31 section headers, starting at offset 0x36d0:

Section Headers:
  [Nr] Name              Type             Address           Offset
       Size              EntSize          Flags  Link  Info  Align
  [ 0]                   NULL             0000000000000000  00000000
       0000000000000000  0000000000000000           0     0     0
  [ 1] .interp           PROGBITS         0000000000400318  00000318
       000000000000001c  0000000000000000   A       0     0     1
  [ 2] .note.gnu.pr[...] NOTE             0000000000400338  00000338
       0000000000000030  0000000000000000   A       0     0     8
  [ 3] .note.gnu.bu[...] NOTE             0000000000400368  00000368
       0000000000000024  0000000000000000   A       0     0     4
  [ 4] .note.ABI-tag     NOTE             000000000040038c  0000038c
       0000000000000020  0000000000000000   A       0     0     4
  [ 5] .gnu.hash         GNU_HASH         00000000004003b0  000003b0
       000000000000001c  0000000000000000   A       6     0     8
  [ 6] .dynsym           DYNSYM           00000000004003d0  000003d0
       00000000000000a8  0000000000000018   A       7     1     8
  [ 7] .dynstr           STRTAB           0000000000400478  00000478
       000000000000005b  0000000000000000   A       0     0     1
  [ 8] .gnu.version      VERSYM           00000000004004d4  000004d4
       000000000000000e  0000000000000002   A       6     0     2
  [ 9] .gnu.version_r    VERNEED          00000000004004e8  000004e8
       0000000000000030  0000000000000000   A       7     1     8
  [10] .rela.dyn         RELA             0000000000400518  00000518
       0000000000000030  0000000000000018   A       6     0     8
  [11] .rela.plt         RELA             0000000000400548  00000548
       0000000000000060  0000000000000018  AI       6    24     8
  [12] .init             PROGBITS         0000000000401000  00001000
       000000000000001b  0000000000000000  AX       0     0     4
  [13] .plt              PROGBITS         0000000000401020  00001020
       0000000000000050  0000000000000010  AX       0     0     16
  [14] .plt.sec          PROGBITS         0000000000401070  00001070
       0000000000000040  0000000000000010  AX       0     0     16
  [15] .text             PROGBITS         00000000004010b0  000010b0
       000000000000014c  0000000000000000  AX       0     0     16
  [16] .fini             PROGBITS         00000000004011fc  000011fc
       000000000000000d  0000000000000000  AX       0     0     4
  [17] .rodata           PROGBITS         0000000000402000  00002000
       000000000000002f  0000000000000000   A       0     0     4
  [18] .eh_frame_hdr     PROGBITS         0000000000402030  00002030
       0000000000000034  0000000000000000   A       0     0     4
  [19] .eh_frame         PROGBITS         0000000000402068  00002068
       00000000000000a4  0000000000000000   A       0     0     8
  [20] .init_array       INIT_ARRAY       0000000000403df8  00002df8
       0000000000000008  0000000000000008  WA       0     0     8
  [21] .fini_array       FINI_ARRAY       0000000000403e00  00002e00
       0000000000000008  0000000000000008  WA       0     0     8
  [22] .dynamic          DYNAMIC          0000000000403e08  00002e08
       00000000000001d0  0000000000000010  WA       7     0     8
  [23] .got              PROGBITS         0000000000403fd8  00002fd8
       0000000000000010  0000000000000008  WA       0     0     8
  [24] .got.plt          PROGBITS         0000000000403fe8  00002fe8
       0000000000000038  0000000000000008  WA       0     0     8
  [25] .data             PROGBITS         0000000000404020  00003020
       0000000000000010  0000000000000000  WA       0     0     8
  [26] .bss              NOBITS           0000000000404030  00003030
       0000000000000008  0000000000000000  WA       0     0     1
  [27] .comment          PROGBITS         0000000000000000  00003030
       000000000000002b  0000000000000001  MS       0     0     1
  [28] .symtab           SYMTAB           0000000000000000  00003060
       0000000000000378  0000000000000018          29    18     8
  [29] .strtab           STRTAB           0000000000000000  000033d8
       00000000000001d7  0000000000000000           0     0     1
  [30] .shstrtab         STRTAB           0000000000000000  000035af
       000000000000011f  0000000000000000           0     0     1
Key to Flags:
  W (write), A (alloc), X (execute), M (merge), S (strings), I (info),
  L (link order), O (extra OS processing required), G (group), T (TLS),
  C (compressed), x (unknown), o (OS specific), E (exclude),
  D (mbind), l (large), p (processor specific)
```

We can see relocation entries for `free`, `puts`, `printf` and `malloc`.

```
$ readelf -r demo

Relocation section '.rela.dyn' at offset 0x518 contains 2 entries:
  Offset          Info           Type           Sym. Value    Sym. Name + Addend
000000403fd8  000200000006 R_X86_64_GLOB_DAT 0000000000000000 __libc_start_main@GLIBC_2.34 + 0
000000403fe0  000500000006 R_X86_64_GLOB_DAT 0000000000000000 __gmon_start__ + 0

Relocation section '.rela.plt' at offset 0x548 contains 4 entries:
  Offset          Info           Type           Sym. Value    Sym. Name + Addend
000000404000  000100000007 R_X86_64_JUMP_SLO 0000000000000000 free@GLIBC_2.2.5 + 0
000000404008  000300000007 R_X86_64_JUMP_SLO 0000000000000000 puts@GLIBC_2.2.5 + 0
000000404010  000400000007 R_X86_64_JUMP_SLO 0000000000000000 printf@GLIBC_2.2.5 + 0
000000404018  000600000007 R_X86_64_JUMP_SLO 0000000000000000 malloc@GLIBC_2.2.5 + 0
```

Let's dosassemble the `.text` section

```
$ objdump -d -j .text demo

demo:     file format elf64-x86-64


Disassembly of section .text:

00000000004010b0 <_start>:
  4010b0:	f3 0f 1e fa          	endbr64
  4010b4:	31 ed                	xor    %ebp,%ebp
  4010b6:	49 89 d1             	mov    %rdx,%r9
  4010b9:	5e                   	pop    %rsi
  4010ba:	48 89 e2             	mov    %rsp,%rdx
  4010bd:	48 83 e4 f0          	and    $0xfffffffffffffff0,%rsp
  4010c1:	50                   	push   %rax
  4010c2:	54                   	push   %rsp
  4010c3:	45 31 c0             	xor    %r8d,%r8d
  4010c6:	31 c9                	xor    %ecx,%ecx
  4010c8:	48 c7 c7 96 11 40 00 	mov    $0x401196,%rdi
  4010cf:	ff 15 03 2f 00 00    	call   *0x2f03(%rip)        # 403fd8 <__libc_start_main@GLIBC_2.34>
  4010d5:	f4                   	hlt
  4010d6:	66 2e 0f 1f 84 00 00 	cs nopw 0x0(%rax,%rax,1)
  4010dd:	00 00 00

00000000004010e0 <_dl_relocate_static_pie>:
  4010e0:	f3 0f 1e fa          	endbr64
  4010e4:	c3                   	ret
  4010e5:	66 2e 0f 1f 84 00 00 	cs nopw 0x0(%rax,%rax,1)
  4010ec:	00 00 00
  4010ef:	90                   	nop

00000000004010f0 <deregister_tm_clones>:
  4010f0:	b8 30 40 40 00       	mov    $0x404030,%eax
  4010f5:	48 3d 30 40 40 00    	cmp    $0x404030,%rax
  4010fb:	74 13                	je     401110 <deregister_tm_clones+0x20>
  4010fd:	b8 00 00 00 00       	mov    $0x0,%eax
  401102:	48 85 c0             	test   %rax,%rax
  401105:	74 09                	je     401110 <deregister_tm_clones+0x20>
  401107:	bf 30 40 40 00       	mov    $0x404030,%edi
  40110c:	ff e0                	jmp    *%rax
  40110e:	66 90                	xchg   %ax,%ax
  401110:	c3                   	ret
  401111:	66 66 2e 0f 1f 84 00 	data16 cs nopw 0x0(%rax,%rax,1)
  401118:	00 00 00 00
  40111c:	0f 1f 40 00          	nopl   0x0(%rax)

0000000000401120 <register_tm_clones>:
  401120:	be 30 40 40 00       	mov    $0x404030,%esi
  401125:	48 81 ee 30 40 40 00 	sub    $0x404030,%rsi
  40112c:	48 89 f0             	mov    %rsi,%rax
  40112f:	48 c1 ee 3f          	shr    $0x3f,%rsi
  401133:	48 c1 f8 03          	sar    $0x3,%rax
  401137:	48 01 c6             	add    %rax,%rsi
  40113a:	48 d1 fe             	sar    $1,%rsi
  40113d:	74 11                	je     401150 <register_tm_clones+0x30>
  40113f:	b8 00 00 00 00       	mov    $0x0,%eax
  401144:	48 85 c0             	test   %rax,%rax
  401147:	74 07                	je     401150 <register_tm_clones+0x30>
  401149:	bf 30 40 40 00       	mov    $0x404030,%edi
  40114e:	ff e0                	jmp    *%rax
  401150:	c3                   	ret
  401151:	66 66 2e 0f 1f 84 00 	data16 cs nopw 0x0(%rax,%rax,1)
  401158:	00 00 00 00
  40115c:	0f 1f 40 00          	nopl   0x0(%rax)

0000000000401160 <__do_global_dtors_aux>:
  401160:	f3 0f 1e fa          	endbr64
  401164:	80 3d c5 2e 00 00 00 	cmpb   $0x0,0x2ec5(%rip)        # 404030 <__TMC_END__>
  40116b:	75 13                	jne    401180 <__do_global_dtors_aux+0x20>
  40116d:	55                   	push   %rbp
  40116e:	48 89 e5             	mov    %rsp,%rbp
  401171:	e8 7a ff ff ff       	call   4010f0 <deregister_tm_clones>
  401176:	c6 05 b3 2e 00 00 01 	movb   $0x1,0x2eb3(%rip)        # 404030 <__TMC_END__>
  40117d:	5d                   	pop    %rbp
  40117e:	c3                   	ret
  40117f:	90                   	nop
  401180:	c3                   	ret
  401181:	66 66 2e 0f 1f 84 00 	data16 cs nopw 0x0(%rax,%rax,1)
  401188:	00 00 00 00
  40118c:	0f 1f 40 00          	nopl   0x0(%rax)

0000000000401190 <frame_dummy>:
  401190:	f3 0f 1e fa          	endbr64
  401194:	eb 8a                	jmp    401120 <register_tm_clones>

0000000000401196 <main>:
  401196:	f3 0f 1e fa          	endbr64
  40119a:	55                   	push   %rbp
  40119b:	48 89 e5             	mov    %rsp,%rbp
  40119e:	48 83 ec 10          	sub    $0x10,%rsp
  4011a2:	48 8d 05 5b 0e 00 00 	lea    0xe5b(%rip),%rax        # 402004 <_IO_stdin_used+0x4>
  4011a9:	48 89 c7             	mov    %rax,%rdi
  4011ac:	e8 cf fe ff ff       	call   401080 <puts@plt>
  4011b1:	bf 64 00 00 00       	mov    $0x64,%edi
  4011b6:	e8 e5 fe ff ff       	call   4010a0 <malloc@plt>
  4011bb:	48 89 45 f8          	mov    %rax,-0x8(%rbp)
  4011bf:	48 8b 45 f8          	mov    -0x8(%rbp),%rax
  4011c3:	48 89 c6             	mov    %rax,%rsi
  4011c6:	48 8d 05 45 0e 00 00 	lea    0xe45(%rip),%rax        # 402012 <_IO_stdin_used+0x12>
  4011cd:	48 89 c7             	mov    %rax,%rdi
  4011d0:	b8 00 00 00 00       	mov    $0x0,%eax
  4011d5:	e8 b6 fe ff ff       	call   401090 <printf@plt>
  4011da:	48 8b 45 f8          	mov    -0x8(%rbp),%rax
  4011de:	48 89 c7             	mov    %rax,%rdi
  4011e1:	e8 8a fe ff ff       	call   401070 <free@plt>
  4011e6:	48 8d 05 37 0e 00 00 	lea    0xe37(%rip),%rax        # 402024 <_IO_stdin_used+0x24>
  4011ed:	48 89 c7             	mov    %rax,%rdi
  4011f0:	e8 8b fe ff ff       	call   401080 <puts@plt>
  4011f5:	b8 00 00 00 00       	mov    $0x0,%eax
  4011fa:	c9                   	leave
  4011fb:	c3                   	ret
```

We can see calls to 

```
call   401080 <puts@plt>
call   401090 <printf@plt>
call   401070 <free@plt>
call   401080 <puts@plt>
```

We can see these addresses match to their corresponding stubs in `.plt.sec` section

```
$ objdump -d -j .plt.sec demo

demo:     file format elf64-x86-64


Disassembly of section .plt.sec:

0000000000401070 <free@plt>:
  401070:	f3 0f 1e fa          	endbr64
  401074:	ff 25 86 2f 00 00    	jmp    *0x2f86(%rip)        # 404000 <free@GLIBC_2.2.5>
  40107a:	66 0f 1f 44 00 00    	nopw   0x0(%rax,%rax,1)

0000000000401080 <puts@plt>:
  401080:	f3 0f 1e fa          	endbr64
  401084:	ff 25 7e 2f 00 00    	jmp    *0x2f7e(%rip)        # 404008 <puts@GLIBC_2.2.5>
  40108a:	66 0f 1f 44 00 00    	nopw   0x0(%rax,%rax,1)

0000000000401090 <printf@plt>:
  401090:	f3 0f 1e fa          	endbr64
  401094:	ff 25 76 2f 00 00    	jmp    *0x2f76(%rip)        # 404010 <printf@GLIBC_2.2.5>
  40109a:	66 0f 1f 44 00 00    	nopw   0x0(%rax,%rax,1)

00000000004010a0 <malloc@plt>:
  4010a0:	f3 0f 1e fa          	endbr64
  4010a4:	ff 25 6e 2f 00 00    	jmp    *0x2f6e(%rip)        # 404018 <malloc@GLIBC_2.2.5>
  4010aa:	66 0f 1f 44 00 00    	nopw   0x0(%rax,%rax,1)
```

PLT section

```
$ objdump -d -j .plt demo

demo:     file format elf64-x86-64


Disassembly of section .plt:

0000000000401020 <.plt>:
  401020:	ff 35 ca 2f 00 00    	push   0x2fca(%rip)        # 403ff0 <_GLOBAL_OFFSET_TABLE_+0x8>
  401026:	ff 25 cc 2f 00 00    	jmp    *0x2fcc(%rip)        # 403ff8 <_GLOBAL_OFFSET_TABLE_+0x10>
  40102c:	0f 1f 40 00          	nopl   0x0(%rax)
  401030:	f3 0f 1e fa          	endbr64
  401034:	68 00 00 00 00       	push   $0x0
  401039:	e9 e2 ff ff ff       	jmp    401020 <_init+0x20>
  40103e:	66 90                	xchg   %ax,%ax
  401040:	f3 0f 1e fa          	endbr64
  401044:	68 01 00 00 00       	push   $0x1
  401049:	e9 d2 ff ff ff       	jmp    401020 <_init+0x20>
  40104e:	66 90                	xchg   %ax,%ax
  401050:	f3 0f 1e fa          	endbr64
  401054:	68 02 00 00 00       	push   $0x2
  401059:	e9 c2 ff ff ff       	jmp    401020 <_init+0x20>
  40105e:	66 90                	xchg   %ax,%ax
  401060:	f3 0f 1e fa          	endbr64
  401064:	68 03 00 00 00       	push   $0x3
  401069:	e9 b2 ff ff ff       	jmp    401020 <_init+0x20>
  40106e:	66 90                	xchg   %ax,%ax
```

We can verify the initial addresses stored in `.got.plt` entries are references to corresponding entries in `.plt` (addresses are in little endian)

```
$ readelf -x .got.plt demo

Hex dump of section '.got.plt':
 NOTE: This section has relocations against it, but these have NOT been applied to this dump.
  0x00403fe8 083e4000 00000000 00000000 00000000 .>@.............
  0x00403ff8 00000000 00000000 30104000 00000000 ........0.@.....
  0x00404008 40104000 00000000 50104000 00000000 @.@.....P.@.....
  0x00404018 60104000 00000000                   `.@.....
```

Eg `404000` maps to `401030` (PLT[1]), `404008` maps to `401040` (PLT[2]), etc.

Let's run the program and see the addresses in `.got.plt` getting updated to actual values. I have disabled ASLR and compiled the binary as no-pie executable for simplicity.

```
$ gdb ./demo

(gdb) break main
Breakpoint 1 at 0x40119e
(gdb) run
Starting program: /home/sanketh/assembly/plt/demo
Downloading separate debug info for system-supplied DSO at 0x7ffff7fc3000
[Thread debugging using libthread_db enabled]
Using host libthread_db library "/lib/x86_64-linux-gnu/libthread_db.so.1".

Breakpoint 1, 0x000000000040119e in main ()

(initial got entries, its not showing puts and malloc as they don't span new rows)

(gdb) x/4gx 0x404000
0x404000 <free@got.plt>:	0x0000000000401030	0x0000000000401040
0x404010 <printf@got.plt>:	0x0000000000401050	0x0000000000401060

(gdb) next
Single stepping until exit from function main,

(gdb) x/4gx 0x404000
0x404000 <free@got.plt>:	0x00007ffff7cadd30	0x00007ffff7c87be0
0x404010 <printf@got.plt>:	0x00007ffff7c60100	0x00007ffff7cad650
```

We can see `.got.plt` section got updated with actual values.