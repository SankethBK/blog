---
title:  "ELF Format"
date:   2025-10-01
categories: ["elf"]
tags: ["elf", "reverse engineering"]
author: Sanketh
references:
  
---

# ELF Format: ELF Header

## What is ELF?

ELF (Executable and Linkable Format) is the standard binary format used by Unix-like systems (Linux, BSD, etc.) for:
- Executable files (a.out, /bin/ls)
- Object files (.o)
- Shared libraries (.so)
- Core dumps

It’s a container format that describes:
- What parts of the file get loaded into memory,
- Where execution starts,
- How relocations and dynamic linking are handled.
- Contains useful information for the debuggers.

## General Structure of an ELF File

An ELF file is organized into several key components that serve different purposes during compilation, linking, and execution.

### The Big Picture

At a high level, every ELF file contains:
**1. ELF Header:** Always at the beginning (offset 0x0)
- Identifies the file as ELF
- Contains metadata about the file (architecture, entry point, etc.)
- Points to the Program Header Table and Section Header Table

**2. Program Header Table - Describes segments (runtime view)**
- Used by the operating system loader
- Tells the OS what to load into memory and where
- Each entry describes a segment

**3. Section Header Table - Describes sections (link-time view)**

- Used by the linker and debugger
- Contains metadata about each section
- Can be stripped from executables (not needed at runtime)

**Segments - Chunks of data loaded into memory at runtime**

- Defined by program headers
- Examples: code segment (executable), data segment (writable)

**Sections - Logical divisions of the file for linking/debuggin**g

- Defined by section headers
- Examples: .text (code), .data (initialized data), .symtab (symbols)

![ELF Strcture](/images/elf-structure-overview.png)


## ELF Header

The ELF Header is always located at the very beginning of an ELF file (offset 0x0) and serves as the "table of contents" for the entire file. It's a fixed-size structure that contains essential metadata about the binary.

### Size of ELF Header

- **32-bit ELF files**: 52 bytes
- **64-bit ELF files**: 64 bytes

The size difference accommodates larger address spaces in 64-bit architectures.

This is where the structure of ELF header si defined in linux kernel `include/uapi/linux/elf.h`.

```C
#define EI_NIDENT	16

typedef struct elf32_hdr {
  unsigned char	e_ident[EI_NIDENT];
  Elf32_Half	e_type;
  Elf32_Half	e_machine;
  Elf32_Word	e_version;
  Elf32_Addr	e_entry;  /* Entry point */
  Elf32_Off	e_phoff;
  Elf32_Off	e_shoff;
  Elf32_Word	e_flags;
  Elf32_Half	e_ehsize;
  Elf32_Half	e_phentsize;
  Elf32_Half	e_phnum;
  Elf32_Half	e_shentsize;
  Elf32_Half	e_shnum;
  Elf32_Half	e_shstrndx;
} Elf32_Ehdr;

typedef struct elf64_hdr {
  unsigned char	e_ident[EI_NIDENT];	/* ELF "magic number" */
  Elf64_Half e_type;
  Elf64_Half e_machine;
  Elf64_Word e_version;
  Elf64_Addr e_entry;		/* Entry point virtual address */
  Elf64_Off e_phoff;		/* Program header table file offset */
  Elf64_Off e_shoff;		/* Section header table file offset */
  Elf64_Word e_flags;
  Elf64_Half e_ehsize;
  Elf64_Half e_phentsize;
  Elf64_Half e_phnum;
  Elf64_Half e_shentsize;
  Elf64_Half e_shnum;
  Elf64_Half e_shstrndx;
} Elf64_Ehdr;
```

### ELF Header Components

The ELF Header can be divided into two main parts: the **identification bytes** (E_IDENT) and the **header fields**.

#### 1. E_IDENT - Identification Bytes (16 bytes)

The first 16 bytes of every ELF file contain identification information that describes how to interpret the rest of the file.

##### 1. Magic Number (4 bytes)

```
Offset 0-3: 0x7F 'E' 'L' 'F'
```

- **0x7F**: Non-printable byte to prevent misinterpretation as text
- **'E' 'L' 'F'**: ASCII characters spelling "ELF"
- This signature allows tools to quickly verify a file is ELF format

##### 2. Class (1 byte, offset 4)

Specifies whether this is a 32-bit or 64-bit ELF file:
- **1 (ELFCLASS32)**: 32-bit architecture
- **2 (ELFCLASS64)**: 64-bit architecture

This is crucial because some data types (addresses, offsets) have different sizes depending on the class.

##### 3. Data Encoding (1 byte, offset 5)

Specifies the byte order (endianness):
- **1 (ELFDATA2LSB)**: Little-endian (least significant byte first)
- **2 (ELFDATA2MSB)**: Big-endian (most significant byte first)

##### 4. Version (1 byte, offset 6)

ELF format version:
- **1 (EV_CURRENT)**: Current version
- This has been 1 since the late 1980s and has never changed!

##### 5. OS/ABI (1 byte, offset 7)

Identifies the target operating system and ABI (Application Binary Interface):
- **0 (ELFOSABI_SYSV)**: UNIX System V ABI (generic, most common)
- **3 (ELFOSABI_LINUX)**: Linux
- **9 (ELFOSABI_FREEBSD)**: FreeBSD
- Many others...

**Note:** Even Linux binaries often have this set to 0 (SYSV), which is perfectly valid. Statically compiled Linux binaries sometimes use 3.

##### 6. ABI Version (1 byte, offset 8)

Version of the OS/ABI:
- Almost never used in practice
- Usually set to 0

##### 7. Padding (7 bytes, offsets 9-15)

Reserved for future use, currently unused:
- All set to 0
- Allows for future extensions without changing the header size

You can see what the EI_IDENT field says by looking at the output of readelf -h.


### 2. Main Header Fields

After the 16-byte E_IDENT section, the remaining fields provide critical information about the file structure.

#### 1. e_type (2 bytes) - Object File Type

Specifies what kind of ELF file this is:

| Value | Name | Description |
|-------|------|-------------|
| 0 | ET_NONE | No file type (unknown/invalid) |
| 1 | ET_REL | Relocatable file (object file `.o`) |
| 2 | ET_EXEC | Executable file (no PIE/ASLR) |
| 3 | ET_DYN | Shared object file (`.so`) or PIE executable |
| 4 | ET_CORE | Core dump file |

**Important distinction:**
- **ET_EXEC**: Traditional executable with fixed load addresses (no ASLR support)
  - Compile with: `gcc -no-pie program.c`
- **ET_DYN**: Modern position-independent executable OR shared library
  - Executables: Have PT_INTERP segment
  - Libraries: No PT_INTERP segment
  - Compile with: `gcc program.c` (default on modern systems)

#### 2. e_machine (2 bytes) - Target Architecture

Specifies the required machine architecture:

| Value | Name | Architecture |
|-------|------|--------------|
| 0x02 | EM_SPARC | SPARC.    |
| 0x03 | EM_386 | Intel x86 (32-bit) |
| 0x08 | EM_MIPS | MIPS        |
| 0x14 | EM_PPC | PowerPC      |
| 0x28 | EM_ARM | ARM (32-bit) |
| 0x3E | EM_X86_64 | AMD/Intel x86-64 (64-bit) |
| 0xB7 | EM_AARCH64 | ARM 64-bit |
| 0xF3 | EM_RISCV | RISC-V     |

Over 200 architectures are defined in the ELF specification.

#### 3. e_version (4 bytes) - Version

ELF version number:
- **1 (EV_CURRENT)**: Current version
- Same as the version in E_IDENT, but 4 bytes instead of 1

#### 4. e_entry (4 or 8 bytes) - Entry Point Address

Virtual memory address where execution begins:
- For executables: Address of the first instruction to execute
- For shared libraries: Address of initialization/constructor function
- **Set to 0** if there's no entry point (e.g., relocatable object files)

Example: `0x0000000000401050` (typical entry point for x86-64)


**Important Note:** This is a **virtual address** (where the code will be in memory after loading), NOT a file offset (where the code is stored in the ELF file on disk). The OS uses program headers to map file contents to virtual memory addresses. We'll explore how to locate the actual file offset of the entry point code when we discuss program headers and segments in detail.

**Why not start at 0x0?** The bottom of the virtual address space (typically 0x0 to 0x10000 or higher) is intentionally left unmapped to catch NULL pointer dereferences - if your program tries to access address 0x0, it will immediately segfault rather than silently corrupting memory. Starting at addresses like 0x400000 is a security and debugging feature, not a waste of memory, since virtual address space is separate from physical RAM usage.

#### 5. e_phoff (4 or 8 bytes) - Program Header Offset

File offset (in bytes) to the Program Header Table:
- Tells the loader where to find segment descriptions
- Typically immediately after the ELF Header
- Example: `0x40` (64 bytes - right after 64-byte ELF header)

#### 6. e_shoff (4 or 8 bytes) - Section Header Offset

File offset (in bytes) to the Section Header Table:
- Tells linkers/debuggers where to find section descriptions
- Can be anywhere in the file (commonly at the end)
- **Can be 0** if no section headers present (stripped binary)

#### 7. e_flags (4 bytes) - Processor-Specific Flags

Architecture-specific flags:
- **x86/x86-64**: Usually 0 (no flags defined)
- **ARM**: Specifies ARM/Thumb mode, floating-point ABI, etc.
- **MIPS**: Specifies ABI version, ISA level, etc.
- **RISC-V**: Specifies extensions (RVC, floating-point, etc.)

Interpretation depends entirely on the target architecture.

#### 8. e_ehsize (2 bytes) - ELF Header Size

Size of the ELF Header itself:
- **52 bytes** for 32-bit ELF
- **64 bytes** for 64-bit ELF

Seems redundant (we already know the format), but allows for future extensibility.

#### 9. e_phentsize (2 bytes) - Program Header Entry Size

Size of one entry in the Program Header Table:
- **32 bytes** for 32-bit ELF
- **56 bytes** for 64-bit ELF

#### 10. e_phnum (2 bytes) - Program Header Count

Number of entries in the Program Header Table:
- Typical executables have 5-13 segments
- Maximum is 65,535 (though typically much fewer)
- **Can be 0** for object files (no segments)

**To find Program Header Table size:**

Table size = e_phentsize × e_phnum

#### 11. e_shentsize (2 bytes) - Section Header Entry Size

Size of one entry in the Section Header Table:
- **40 bytes** for 32-bit ELF
- **64 bytes** for 64-bit ELF

#### 12. e_shnum (2 bytes) - Section Header Count

Number of entries in the Section Header Table:
- Typical executables have 20-40 sections
- Object files can have many more
- **Can be 0** if sections stripped

#### 13. e_shstrndx (2 bytes) - Section Header String Table Index

Index of the section that contains section names:
- Points to the `.shstrtab` section
- This section is a string table containing all section names
- Used to look up section names (like ".text", ".data", etc.)
- **Special value 0 (SHN_UNDEF)**: No string table

**How section names work:**
1. Section header contains `sh_name` field (an offset)
2. Look up section at index `e_shstrndx`
3. That section contains a string table
4. `sh_name` is an offset into that string table
5. Read the null-terminated string at that offset = section name!

## ELF Data Types

ELF defines its own data types that vary based on the file class:

| Type | 32-bit Size | 64-bit Size | Description |
|------|-------------|-------------|-------------|
| Elf32_Half / Elf64_Half | 2 bytes | 2 bytes | Unsigned short |
| Elf32_Word / Elf64_Word | 4 bytes | 4 bytes | Unsigned int |
| Elf32_Addr / Elf64_Addr | 4 bytes | 8 bytes | Address |
| Elf32_Off / Elf64_Off | 4 bytes | 8 bytes | File offset |

## Viewing the ELF Header

You can inspect the ELF header of any binary using `readelf`:
```bash
readelf -h main
```

### Example output:

```
ELF Header:
  Magic:   7f 45 4c 46 02 01 01 00 00 00 00 00 00 00 00 00
  Class:                             ELF64
  Data:                              2's complement, little endian
  Version:                           1 (current)
  OS/ABI:                            UNIX - System V
  ABI Version:                       0
  Type:                              EXEC (Executable file)
  Machine:                           Advanced Micro Devices X86-64
  Version:                           0x1
  Entry point address:               0x401090
  Start of program headers:          64 (bytes into file)
  Start of section headers:          14048 (bytes into file)
  Flags:                             0x0
  Size of this header:               64 (bytes)
  Size of program headers:           56 (bytes)
  Number of program headers:         13
  Size of section headers:           64 (bytes)
  Number of section headers:         31
  Section header string table index: 30
```

