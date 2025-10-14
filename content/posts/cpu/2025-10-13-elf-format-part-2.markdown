---
title:  "ELF Format: Part 2"
date:   2025-10-13
categories: ["elf"]
tags: ["elf", "reverse engineering"]
author: Sanketh
references:
  
---

# ELF Format: Segments and Program Header Table

After understanding the ELF Header, the next critical component is the Program Header Table. This table describes segments - the portions of the file that will be loaded into memory when the program executes.


## What Are Segments?

Segments are the runtime view of an ELF file. While sections (which we'll cover later) are used during linking and debugging, segments are what the operating system cares about when loading and executing a program.

### Key points about segments:

- Segments define what gets loaded into memory and where
- Each segment specifies permissions (read, write, execute)
- Only PT_LOAD segments actually allocate memory
- Other segment types provide metadata or point to data within PT_LOAD segments
- Segments can overlap with each other in the file and in memory

## Program Header Table

### Program Header Table Location

The ELF Header tells us everything we need to find the Program Header Table:

- Location (file offset): e_phoff field in ELF Header
- Entry size: e_phentsize (32 bytes for 32-bit ELF, 56 bytes for 64-bit ELF)
- Number of entries: e_phnum

Total table size = e_phentsize × e_phnum

```bash
$ readelf -h main | grep "program headers"
  Start of program headers:          64 (bytes into file)
  Size of program headers:           56 (bytes)
  Number of program headers:         13
```

This means:
- Program Header Table starts at offset 0x40 (64 bytes)
- Each entry is 56 bytes
- There are 13 entries
- Total table size: 56 × 13 = 728 bytes

### Program Header Entry Structure

Each entry in the Program Header Table describes one segment. Here's the structure defined in the Linux kernel:

```C
typedef struct elf32_phdr {
  Elf32_Word	p_type;      // Segment type
  Elf32_Off	    p_offset;    // File offset where segment begins
  Elf32_Addr	p_vaddr;     // Virtual address where segment is loaded
  Elf32_Addr	p_paddr;     // Physical address (rarely used)
  Elf32_Word	p_filesz;    // Size of segment in file
  Elf32_Word	p_memsz;     // Size of segment in memory
  Elf32_Word	p_flags;     // Segment permissions (R/W/X)
  Elf32_Word	p_align;     // Alignment requirement
} Elf32_Phdr;

typedef struct elf64_phdr {
  Elf64_Word p_type;       // Segment type
  Elf64_Word p_flags;      // Segment permissions (R/W/X)
  Elf64_Off p_offset;      // File offset where segment begins
  Elf64_Addr p_vaddr;      // Virtual address where segment is loaded
  Elf64_Addr p_paddr;      // Physical address (rarely used)
  Elf64_Xword p_filesz;    // Size of segment in file
  Elf64_Xword p_memsz;     // Size of segment in memory
  Elf64_Xword p_align;     // Alignment requirement
} Elf64_Phdr;
```

Note: The order of p_flags differs between 32-bit and 64-bit structures!

### Program Header Fields Explained

#### 1. p_type - Segment Type

Identifies the type of segment. Common types:

| Value | Name    | Description |
|-------|---------|-------------|
|  0    | PT_NULL | Unused entry |
|  1    | PT_LOAD | Loadable segment (actually loaded into memory) |
|  2    | PT_DYNAMIC | Dynamic linking information |
|  3    | PT_INTERP | Path to program interpreter (dynamic linker) | 
|  4    | PT_NOTE | Auxiliary information |
|  6    | PT_PHDR | Program header table itself |
|  7    | PT_TLS | Thread-local storage


#### 2. p_offset - File Offset

The byte offset from the beginning of the file where this segment's data begins. Example: p_offset = 0x1000 means the segment data starts at byte 4096 in the file.

#### 3. p_vaddr - Virtual Address

The virtual memory address where this segment will be loaded. Example: `p_vaddr = 0x400000` means this segment will appear at address `0x400000` in the process's virtual memory space.

#### 4. p_paddr - Physical Address

Physical memory address (mostly relevant for embedded systems and firmware). Usually ignored for regular executables and set to the same value as `p_vaddr`.

#### 5. p_filesz - Size in File

The number of bytes this segment occupies in the file. If `p_filesz = 0`, the segment has no data in the file (but may still occupy memory).

#### 6. p_memsz - Size in Memory

The number of bytes this segment will occupy in memory.

**Important: `p_memsz` can be larger than `p_filesz`!**

- Extra bytes are zero-initialized
- This is how `.bss` (uninitialized data) works
- Example: `p_filesz = 0x100`, `p_memsz = 0x300` → 256 bytes from file + 512 bytes of zeros

#### 7. p_flags - Permissions

Segment permissions, using these flags:

| Flag  | Value | Meaning    |
|-------|-------|------------|
| PF_X  | 0x1   | Executable |
| PF_W  | 0x2   | Writable   |
| PF_R  | 0x4   | Readable   |

Flags are combined with bitwise OR:

- `0x5 (PF_R | PF_X)` = Read + Execute (code segment)
- `0x6 (PF_R | PF_W)` = Read + Write (data segment)
- `0x4 (PF_R)` = Read-only (const data)

#### 8. p_align - Alignment

Specifies alignment requirements for the segment.

- Must be a power of 2
- Common values: 0x1000 (4 KB, page size on x86-64)
- `p_vaddr` and `p_offset` must be congruent modulo `p_align`


### Common Segment Types in Detail

#### 1. PT_LOAD - Loadable Segments

The most important segment type! These are the only segments that actually allocate memory and get loaded by the OS.
Typical PT_LOAD segments in an executable:

##### 1. Code Segment (Text)

- Contains executable code
- Flags: R-X (Read + Execute)
- Usually starts at `0x400000` (non-PIE) or a randomized address (PIE)
- Includes: `.text`, `.plt`, `.rodata` sections

##### 2. Data Segment

- Contains initialized and uninitialized data
- Flags: RW- (Read + Write)
- Includes: `.data`, `.bss`, `.got` sections
- `p_memsz > p_filesz` (size of segment in memory will be greater than size of segment in ELF file) for `.bss` (zero-initialized data)

**Why Code and Data Segments Are Separated in ELF?**

- Code pages are marked read + execute (r-x), while data pages are read + write (rw-). Separating them allows the OS to set page-level protections using the hardware’s memory management unit (MMU). This prevents bugs or exploits (like buffer overflows) from executing injected data.
- Read-only code can be shared across multiple processes, while writable data must be private to each process.
  
#### 2. PT_DYNAMIC - Dynamic Linking Information

`PT_DYNAMIC` is a program header segment that points to the `.dynamic` section of an ELF file.
This section contains metadata used by the dynamic linker (like `/lib64/ld-linux-x86-64.so.2`) to load and relocate shared libraries at runtime.

You can think of it as a “table of contents” for everything the dynamic loader needs to know about an executable or shared library.

Important: This segment does NOT allocate new memory - it points to data within a `PT_LOAD` segment.

```
ELF File
│
├── PT_LOAD (code + data)
│     ├── .text
│     ├── .rodata
│     └── .dynamic  ← PT_DYNAMIC points here
│
├── PT_INTERP       → Path to dynamic linker
├── PT_DYNAMIC      → Contains tags about dynamic linking
└── ...
```
**How the Dynamic Linker Uses `PT_DYNAMIC`?**

1. Program starts → kernel loads ELF → sees `PT_INTERP`.
2. The interpreter (dynamic linker) is loaded (e.g. `/lib64/ld-linux-x86-64.so.2`).
3. The linker reads the `PT_DYNAMIC` segment to find:
   - Which shared libraries to load (`DT_NEEDED`)
   - Where symbol tables and relocations are
4. The linker maps the required `.so` files, performs relocations, resolves symbols, and prepares the GOT/PLT.
5. Finally, control transfers to the program’s `_start`.

#### 3. PT_INTERP - Program Interpreter

The `PT_INTERP` segment tells the kernel which program should interpret and load this ELF file — usually the dynamic linker.

It contains a path string, typically something like: `/lib64/ld-linux-x86-64.so.2`. This string is null-terminated and stored inside the ELF file’s `.interp` section. The Program Header Table entry of type `PT_INTERP` points directly to it (via its offset).

**Key distinction:**

- PIE executables: Have `PT_INTERP` segment
- Shared libraries: Do NOT have `PT_INTERP` segment
- Both have type ET_DYN, but `PT_INTERP` tells them apart

##### Role during Program Startup

When you run an ELF executable:

1. The kernel reads the ELF header, finds a `PT_INTERP` entry.
2. The kernel does not run your program directly — instead, it:
    - Loads your ELF into memory.
    - Loads the specified interpreter (usually ld-linux.so).
    - Passes control to that interpreter, along with:
      - The program’s memory mappings.
      - The file descriptor.
      - Auxiliary vectors (system info).
3. The interpreter (dynamic linker) then:
   - Resolves shared library dependencies.
   - Performs relocations.
   - Finally jumps to the executable’s entry point.

**When does Control Transfer to Interpreter Happens?**

The control transfers immediately to the dynamic linker, before your program starts executing any of its own code.

Here’s what happens internally:

1. Kernel loads your ELF file.
    - Reads ELF header → finds `PT_INTERP` segment.
    - Sees that the program needs a dynamic linker.
2. Kernel loads the interpreter (`ld-linux.so`) into memory.
   - The path comes from the `PT_INTERP` string (e.g. `/lib64/ld-linux-x86-64.so.2`).
   - The linker itself is also an ELF executable.
3. Kernel sets up the process:
   - Maps your program’s `PT_LOAD` segments into memory (code, data, etc.).
   - Maps the dynamic linker (`ld-linux.so`) into memory.
   - Prepares stack and auxiliary vectors (program name, environment, etc.).
4. Kernel sets the entry point to the linker, not your program.
   - So the first instruction that runs in user space belongs to the dynamic linker, not to your program.
5. Dynamic linker (user-space loader) takes over:
   - Reads your program’s .dynamic section.
   - Finds all needed shared libraries (libc.so, etc.).
   - Loads them into memory.
   - Applies relocations.
   - Resolves symbol addresses.
6. After everything is ready...
   - The linker finally jumps to your program’s real entry point (the one shown in readelf -h).

#### 4. PT_NOTE - Auxiliary Information

Contains auxiliary information for the system:
- **Build ID**: Unique identifier for the binary
- **ABI tags**: Operating system version requirements
- **GNU properties**: Compiler flags, security features
- Used by debuggers, package managers, and system tools

Example:
```bash
$ readelf -n main

Displaying notes found in: .note.gnu.property
  Owner                Data size 	Description
  GNU                  0x00000020	NT_GNU_PROPERTY_TYPE_0
      Properties: x86 feature: IBT, SHSTK
	x86 ISA needed: x86-64-baseline

Displaying notes found in: .note.gnu.build-id
  Owner                Data size 	Description
  GNU                  0x00000014	NT_GNU_BUILD_ID (unique build ID bitstring)
    Build ID: 99eff4059570e3f6b152fcc4b3044bdbd9a3087f

Displaying notes found in: .note.ABI-tag
  Owner                Data size 	Description
  GNU                  0x00000010	NT_GNU_ABI_TAG (ABI version tag)
    OS: Linux, ABI: 3.2.0
```

#### 5. PT_PHDR - Program Header Table Location

Specifies where the program header table itself will be in memory.

**Self-referential:** This segment describes where to find the segment table!

**Why it exists:**
- The dynamic linker needs to access program headers at runtime
- This segment tells it the memory address where they're loaded
- Enables runtime introspection of the program structure

**But doesn't ELF header already specifies address of program header table?**

The ELF header has:
- `e_phoff`: file offset of the program header table
- `e_phnum`: number of entries
- `e_phentsize`: size of each entry

This helps the OS loader (like the kernel) find and load the segments from the file into memory.

e the executable is loaded, those headers are relocated into virtual memory.
The dynamic linker (and sometimes the program itself) might need to find them after relocation, i.e., in memory space — not the original file offset.

That’s where PT_PHDR comes in.
- It’s a runtime reference that tells where the program header table was loaded into memory.
- The kernel sets up this mapping when it loads the ELF.

#### 6. PT_TLS - Thread-Local Storage

Contains the initialization template for thread-local variables.

- Each thread gets its own copy of this data
- Used by `__thread` keyword in C/C++
- Managed by the threading library (e.g., pthread)

Example:
```c
__thread int my_thread_var = 42;  // Each thread has separate copy
```


