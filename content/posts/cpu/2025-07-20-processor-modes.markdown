---
title:  "Processor Modes in x86"
date:   2025-07-18
draft: true
categories: ["cpu"]
tags: ["cpu", "x86"]
author: Sanketh
references:
    - title:  Virtual Memory in the x86 
      url: https://www.youtube.com/watch?v=jkGZDb3100Q

    - title:  How a Single Bit Inside Your Processor Shields Your Operating System's Integrity 
      url: https://www.youtube.com/watch?v=H4SDPLiUnv4

    - title: From 0 to 1 MB in DOS
      url: https://blogsystem5.substack.com/p/from-0-to-1-mb-in-dos

    - title: Intel 80286 Manual
      url: https://ragestorm.net/downloads/286intel.txt

    - title: Task State Segment
      url: https://pdos.csail.mit.edu/6.828/2017/readings/i386/s07_01.htm

    - title: Intel 80386 Manual
      url: https://pdos.csail.mit.edu/6.828/2017/readings/i386/toc.htm

    - title: Global Descriptor Table
      url: https://wiki.osdev.org/Global_Descriptor_Table

    - title: Task State Segment
      url: https://wiki.osdev.org/Task_State_Segment
---

# The 8086 Processor

## A Brief History

The Intel 8086, released in 1978, marked a pivotal moment in computing history as Intel's first 16-bit microprocessor. Designed by a team led by Stephen Morse, the 8086 was Intel's answer to the growing demand for more powerful processors that could handle larger programs and address more memory than the existing 8-bit chips of the era.

The processor introduced the x86 architecture that would become the foundation for decades of computing evolution. With its 16-bit registers and 20-bit address bus [^address-bus], the 8086 could access up to 1 megabyte of memory—a massive improvement over the 64KB limitation of 8-bit processors. However, it retained backward compatibility concepts that would prove both beneficial and constraining for future generations.

### Why 20-bit Address Bus in the 8086?

The 8086 used a 20-bit address bus, which was a deliberate design decision based on several factors:

- **Memory Capacity:** With 20 address lines, the processor could address 2^20 = 1,048,576 locations, or exactly 1 megabyte of memory. In 1978, this was considered enormous - most computers had only 4KB to 64KB of memory.

- **Economic Considerations:** Adding more address lines would have increased the chip's pin count, making it more expensive to manufacture and requiring more expensive motherboards. Intel balanced capability with cost-effectiveness.

## The Segmented Memory Model

Intel's previous 8-bit processors contained 8-bit wide registers and 16-bit wide address bus, which can enable addressing of 2^16 = 64KB of memory. So thoeretically a program could use 64KB of memory. 

Intel's main goal was to maintain programming familiarity while expanding addressable memory. They wanted programmers to continue thinking in terms of 16-bit addresses (which they were already comfortable with from 8-bit processors) while secretly accessing a larger memory space. The segmentation model essentially says: "You can still write programs using 16-bit addresses, but we'll automatically map these into different 64KB 'segments' of the larger 1MB space."

The physical address was divided into 2 parts: selector/segment and offset. 
- **Selector (Segment):** 16-bit value stored in one of CS, DS, ES, SS, etc.
- **Offset:** 16-bit value (e.g., in SI, DI, BP, SP, or an immediate/displacement).
- **Physical Address Calculation:** physical_address = (selector × 16) + offset

The idea is to express a 20-bit address using 2 16-bit registers. A selector register (CS, DS, ES, SS) indicates the starting address of the segment and the offset register (SI, DI, BP, SP) indicates the boundary of the segment. Since the offset is 16-bits, the boundary can be at a maximum of 64KB thus maintaining backward compatibility.

![Segmentation Model](/images/segmentation-memory-model.png)

**What the diagram shows**

1.  A *segment* is not a fixed block—it’s a **sliding 64 KB window** that can start on **any 16-byte paragraph**.  
    *Segment value = paragraph number; multiplying by 16 shifts the window left or right in 16-byte steps.*
    
2.  **Segment N** and **Segment N+1** start only 16 bytes apart, so their two 64 KB windows overlap almost completely.  
    Any physical byte inside that overlap can be reached with two (or many more) different *segment:offset* pairs.
    
3.  Because the window can slide to **65,536** different paragraph positions (0000h–FFFFh), the segment register must be **16 bits** wide—not just 4 bits.
    
4.  The **offset** (0–65535) always selects the byte inside the current 64 KB window.  
    Together, *segment* and *offset* build the 20-bit physical address:


### Disadvantages of the Segmentation Model

1.  **64 KB Segment Limit:**

    - Each selector covers only 64 KB (the 16-bit offset range). Although it was theoretically possible to support a higher offset which means larger segment memory for a program.
    - Large programs or data structures must be split across multiple segments.
    - Switching segments (e.g., changing CS or DS) adds overhead and complexity.
        
2.  **Alias Addresses:**
    
    - The same physical byte can be addressed by many segment:offset pairs.     
    - Example: physical 04808₁₆ = 047C:0048 = 047D:0038 = 047E:0028 = 047B:0058     
    - Makes comparing or normalizing pointers tricky.

3. **Wrap Around after 20 bits:**

    - All segments after 0xF000 reference memory positions above the 1 MB address space that don’t exist, which the 8086 chose to wrap around by ignoring the 21st bit of an address. After all, there is no 21st line in the address bus.

### The Real Mode

Real mode is the operating mode that all x86 processors boot into, providing direct hardware access and backward compatibility with the original 8086 processor. Named "real" because it provides direct, unsupervised access to real physical memory addresses without any protection mechanisms or virtual memory translation.

When an x86 processor powers on, it starts in real mode regardless of whether it's a modern 64-bit CPU or the original 8086. This ensures that decades-old software can still run and that the boot process remains consistent across the entire x86 family.

#### Contents of 1MB memory layout in 8086 real mode


```

FFFFFh ┌─────────────────────────────────────────────────────────┐
       │ System ROM BIOS (64KB)                                  │
       │ • Boot code and POST routines                           │
       │ • Hardware initialization                               │
       │ • Interrupt handlers (INT 10h, 13h, 16h, etc.)          │
       │ • System services and utilities                         │
F0000h ├─────────────────────────────────────────────────────────┤
       │ Expansion ROM Area (192KB)                              │
       │ • Network card ROM                                      │
       │ • SCSI controller ROM                                   │
       │ • Other adapter ROM                                     │
       │ • Often partially unused                                │
C0000h ├─────────────────────────────────────────────────────────┤
       │ Video BIOS ROM (128KB)                                  │
       │ • VGA/EGA BIOS routines                                 │
       │ • Graphics mode setup                                   │
       │ • Character font data                                   │
       │ • Display adapter firmware                              │
A0000h ├─────────────────────────────────────────────────────────┤
       │ Video RAM (128KB)                                       │
       │ A0000h-AFFFFh: EGA/VGA graphics memory (64KB)           │
       │ B0000h-B7FFFh: Monochrome text memory (32KB)            │
       │ B8000h-BFFFFh: Color text memory (32KB)                 │
90000h ├─────────────────────────────────────────────────────────┤
       │ Extended Conventional Memory (576KB)                    │
       │ • Available for programs if installed                   │
       │ • Many early systems had less RAM                       │
       │ • Could be used for disk buffers, RAM disks             │
       │ • Upper portion often used by DOS itself                │
A0000h ├─────────────────────────────────────────────────────────┤ ← 640KB barrier
       │                                                         │
       │ Conventional Memory (640KB)                             │
       │ Main user program area                                  │
       │                                                         │
       │ ┌─────────────────────────────────────────────────────┐ │
       │ │ User Program Area                                   │ │ 
       │ │ • Application programs                              │ │
       │ │ • Program data and variables                        │ │
       │ │ • Dynamic memory allocation                         │ │
       │ │ • TSR (Terminate and Stay Resident) programs        │ │
       │ └─────────────────────────────────────────────────────┘ │
       │ ┌─────────────────────────────────────────────────────┐ │
       │ │ DOS Kernel and System Files                         │ │
       │ │ • COMMAND.COM                                       │ │
       │ │ • Device drivers                                    │ │
       │ │ • File allocation tables                            │ │
       │ │ • Directory buffers                                 │ │
       │ └─────────────────────────────────────────────────────┘ │
00500h ├─────────────────────────────────────────────────────────┤
       │ BIOS Data Area (256 bytes)                              │
       │ • Hardware configuration data                           │
       │ • Equipment list                                        │
       │ • Keyboard buffer                                       │
       │ • Video mode information                                │
       │ • Serial/parallel port addresses                        │
       │ • Timer tick count                                      │
       │ • Memory size information                               │
003FFh ├─────────────────────────────────────────────────────────┤
       │ Interrupt Vector Table (1024 bytes)                     │
       │ • 256 interrupt vectors × 4 bytes each                  │
       │ • Each vector: segment:offset (2 bytes:2 bytes)         │
       │ • INT 00h-FFh handler addresses                         │
       │ • Hardware and software interrupts                      │
       │ • Critical for system operation                         │
00000h └─────────────────────────────────────────────────────────┘
```

##### Key Memory Regions

1. **Interrupt Vector Table (00000h-003FFh)**
- Size: 1024 bytes (256 vectors × 4 bytes each)
- Structure: Each entry contains segment:offset pointer (YYYY:XXXX format)
- Purpose: The system's "phone book" for interrupt handlers
- Function: When hardware or software triggers an interrupt (like pressing a key), the CPU looks up the handler address here
- Critical vectors:
  - INT 08h: System timer (18.2 times per second)
  - INT 09h: Keyboard interrupt
  - INT 10h: Video services
  - INT 13h: Disk services
  - INT 16h: Keyboard services
  - INT 21h: DOS system calls
- Why it's at address 0: The CPU automatically multiplies the interrupt number by 4 to find the handler address, so INT 09h handler is at 0×4×9 = 36 (0024h).

2. **BIOS Data Area (00400h-004FFh) - 256 bytes**
 - Purpose: System configuration and status information
 - Hardware ports: COM1-4 [^COM1-4] and LPT1-3 [^LPT1-3] base addresses
 - Video info: Current video mode, screen dimensions, cursor position
 - Keyboard: Shift/Ctrl/Alt key states [^Modifier-key-states], keyboard buffer [^Keyboard-buffer]
 - System info: Installed memory size, equipment flags
 - Timers: System tick count since boot

3. **Conventional Memory (00500h-9FFFFh) - ~640KB**
  - Purpose: Main workspace for operating system and applications
  - **DOS Kernel Area (lower portion)**
    - COMMAND.COM: The DOS command interpreter
    - DOS kernel: File system, memory management, process control
    - Device drivers: Disk drivers, printer drivers, etc.
    - System buffers: File allocation table cache, directory buffers
  - **User Program Area (upper portion)**   
    - Application programs: Your actual software
    - Program data: Variables, arrays, user data
    - Dynamic allocation: Heap memory for runtime allocation
    - TSR programs: Background utilities (like antivirus, print spoolers)
  - Why 640KB limit: IBM reserved the upper 384KB for hardware, creating the famous "640KB ought to be enough" barrier.

4. **Video RAM (A0000h-BFFFFh) - 128KB**
    - Purpose: Direct access to display memory
    - **A0000h-AFFFFh: Graphics Memory (64KB)**
      - EGA/VGA framebuffer: Each byte represents pixel data
      - Direct pixel control: Writing here immediately changes screen pixels
      - Mode-dependent: Layout changes based on resolution and color depth
  
5. **B0000h-B7FFFh: Monochrome Text (32KB)**
   - Character display: For monochrome monitors
   - Text mode: 80×25 characters, 2 bytes per character (char + attribute)

6. **B8000h-BFFFFh: Color Text (32KB)**
   - Color character display: Standard color text mode
   - Format: Byte pairs (character, attribute)
   - Example: Writing 'A' (65) + 0x07 (white on black) to B8000h displays 'A' at top-left

7. **Video BIOS ROM (C0000h-C7FFFh) - 32KB**
   - Purpose: Graphics card firmware and services
   - Font data: Character sets for text modes
   - Hardware control: Register programming for graphics chips
   - BIOS extensions: Additional video services beyond basic BIOS
   - Memory-mapped: This is ROM on the graphics card, not system RAM.

8. **Expansion ROM Area (C8000h-EFFFFh) - 160KB**
   - Purpose: Additional adapter card firmware
   - Network cards: Boot ROM for network booting
   - SCSI controllers: Disk controller firmware
   - Sound cards: Audio processing firmware
   - Other adapters: Any card that needs ROM space
   - Often unused: Many systems had empty areas here.

9. **System ROM BIOS (F0000h-FFFFFh) - 64KB**
   - Purpose: Core system firmware
   - Power-On Self Test (POST): Hardware diagnostics at boot
   - Bootstrap loader: Loads operating system from disk
   - Hardware drivers: Low-level hardware access routines
   - System services: INT 10h (video), INT 13h (disk), INT 16h (keyboard)
   - Reset vector: CPU starts execution at FFFF:0000 on power-up

##### Why This Layout?

- Hardware Requirements: Different devices need different address ranges
- ROM needs upper memory: BIOS must be at top (reset vector at FFFFFh)
- Video needs fast access: Memory-mapped for performance
- Programs need contiguous space: Large conventional memory block

# The 80286 and protected mode

## Introduction to the 80286

The Intel 80286, released in 1982, represented a revolutionary leap in x86 architecture. While maintaining backward compatibility with the 8086, it introduced protected mode - a sophisticated operating environment that broke free from real mode's limitations and laid the foundation for modern computing.

The 80286 was Intel's answer to the growing demands for multitasking operating systems, memory protection, and the ability to address more than 1MB of memory. It powered the IBM PC/AT and became the processor that truly enabled the transition from simple DOS machines to powerful workstations.

## Key Innovations of the 80286

### 16MB Address Space

- **24-bit address bus** (compared to 8086's 20-bit)
- **16MB maximum memory** (2^24 = 16,777,216 bytes)
- **Maintained real mode compatibility** for existing 

### Hardware Memory Protection

- **Privilege levels** preventing user programs from corrupting system memory
- **Segment-level protection** with access rights and bounds checking
- **Hardware-enforced security** that software cannot bypass

### Virtual Memory Foundation

- **Segment descriptors** containing detailed memory management information
- **Global and Local Descriptor Tables** for memory organization
- **Task switching support** enabling true multitasking

## The Protected Mode

### Addressing 24-Bit Memory

The 80286 processor had 24 address bus compared to 20-Bit address bus of 8086. It had to implement the addressing in such a way that its backward compatible with 8086 processor's addressing. Instead of extending the logic used in 8086's real mode addressing, 80286 took an entirely different approach. The memory was still addressed with `selector (16-Bit): offset (16-Bit)` pairs. In real mode, a selector value was a paragraph number of physical memory. In protected mode, a selector value is an index into a descriptor table. In both modes, programs are divided into segments. In real mode, these segments are at fixed positions in physical memory and the selector value denotes the paragraph number of the beginning of the segment. 

While we are storing the actual physical address of the segment in descriptor table, the descriptor table entry can store other information related to the segment as well. For eg: length of the segment which can be used to check if the memory accessed by the program is within the segment, read/write flags which can be used to enforce protection, etc.

![Descriptor Table](/images/descriptor-table.png)

### The Virtual Memory

The idea of virtual memory is provide an illusion to a program that it is the only program running and it has access to all the memory. The 80286 introduced the foundational concepts of virtual memory to the x86 architecture, though it implemented a more limited form compared to modern processors. Understanding the 80286's approach helps clarify why virtual memory became essential and how it evolved.

Virtual memory creates an abstraction layer between what programs think they're accessing (virtual addresses) and what actually exists in physical memory. The 80286 achieved this through segmentation-based virtual memory.

![Virtual Memory](/images/virtual-memory-80286.png)

#### Simplified Programming Model with Virtual Memory

Before virtual memory, programmer had to directly manage physical addresses which is error prone and there's a possibility of overwriting other program's data. This also means the programmer has to know where the segments will be loaded in memory beforehand. Virtual Memory solves this issue as each segment will be under the illusion that it starts at memory address 0 and can access upto 64KB of memory. 

### The Memory Management Unit (MMU)

The MMU in the 80286 is a hardware component integrated into the CPU chip itself. THe main purpose of MMU is to translate virtual addresses into physical addresses, along with checking bounds, enforcing privileges, etc. 

### Global and Local Descriptor Tables (GDT and LDT)

#### What Are Descriptor Tables?

Think of descriptor tables as address books for the computer's memory system. Just like you use a phone book to look up someone's address when you only know their name, the 80286 processor uses descriptor tables to look up memory information when it only knows a selector (a kind of memory "name").

#### The Basic Problem They Solve

In real mode, programs had to deal with physical memory addresses directly:

```
Real Mode Problem:
Program says: "I want to access memory at 0x12345"
CPU responds: "OK, accessing physical memory at 0x12345"

Issues:
- Programs must know exact physical addresses
- No protection between programs  
- Programs can corrupt each other's memory
- Hard to relocate programs in memory
```

Protected mode solves this with an indirection layer:

```
Protected Mode Solution:
Program says: "I want to access selector 0x0008, offset 0x1234"
CPU responds: "Let me look up selector 0x0008 in the descriptor table..."
CPU finds: "Selector 0x0008 points to base address 0x100000"
CPU calculates: "Physical address = 0x100000 + 0x1234 = 0x101234"
CPU verifies: "Access allowed? Yes. Accessing physical memory at 0x101234"
```

#### Understanding Selectors

A selector is a 16-bit value that acts like a "memory ID card." Instead of using physical addresses, programs use selectors to identify memory segments.

![Selector Format](/images/selector-format.png)

- **Index (bits 15-3):** Which entry in the descriptor table (0-8191)
- **TI (bit 2):** Table Indicator - 0 = GDT, 1 = LDT
- **RPL (bits 1-0):** Requested Privilege Level (0-3)

#### What Is a Descriptor?

A descriptor is an 8-byte data structure that contains all the information the CPU needs to access a memory segment safely.

![Descriptor Format](/images/descriptor-format.png)

**Base Address (24 bits total in 80286):** (Base[23..16] + Base[15..0])
- Bits 15..0 from the lower section
- Bits 23..16 from the upper section

**Limit (20 bits total, but 80286 only uses 16 bits):** 
- Limit 15..0 (16 bits) - from Lower 32 bits
- Limit 19..16 (4 bits) - from Upper 32 bits (but not used in 80286)

The descriptor format was designed to be forward-compatible. The 80386 later extended it to use:
- Full 32-bit base address (adding Base 31..24)
- Full 20-bit limit (adding Limit 19..16 with granularity bit)


**Final physical address calculation:**

```
Physical Address = 24-bit Base (from descriptor) + 16-bit Offset (from instruction)
```

**Access Byte Format**

![Access Byte](/images/access-byte-format.png)

- **P (Present) - Bit 7:** Indicates whether the segment is currently loaded in memory. When P=1, the segment is valid and can be accessed. When P=0, any attempt to access this segment generates a segment-not-present exception, allowing the OS to load the segment from disk (virtual memory support).
- **DPL (Descriptor Privilege Level) - Bits 6-5:** Defines the privilege level required to access this segment (0-3, where 0 is most privileged). Code running at privilege level 3 (user mode) cannot access segments with DPL=0 (kernel mode). This enforces memory protection between kernel and user space.
- **S (System) - Bit 4:** Distinguishes between application segments and system segments. When S=1, this is an application segment (code/data used by programs). When S=0, this is a system segment (like Task State Segment or LDT descriptor) used by the processor for special operations.
- **E (Executable) - Bit 3:** Determines if this segment contains executable code or data. When E=1, this is a code segment that can be executed (instructions fetched from here). When E=0, this is a data segment used for storing variables and cannot be executed.
- **D (Direction/Conforming) - Bit 2:** For data segments: D=0 means segment grows upward (normal), D=1 means grows downward (stack). For code segments: D=0 means non-conforming (strict privilege checking), D=1 means conforming (can be called from lower privilege levels without changing CPL).
- **R (Read/Write) - Bit 1:** For data segments: R=1 allows write access, R=0 makes it read-only. For code segments: R=1 allows reading the code (useful for debuggers), R=0 makes it execute-only. Code segments are never writable regardless of this bit.
- **A (Accessed) - Bit 0:** Automatically set by the CPU whenever the segment is accessed (loaded into a segment register or used). Never cleared by hardware - only software can clear it. Used by operating systems to implement virtual memory algorithms by tracking which segments are actively being used.

#### Global Descriptor Table (GDT)

The Global Descriptor Table is a system-wide table containing descriptors that all tasks can potentially access. Think of it as the "public directory" of memory segments.

##### GDT Structure and Location

```
Physical Memory Layout:
┌─────────────────────────────────────────────────────────────┐
│                    System RAM                               │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                 GDT                                 │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ Entry 0: NULL Descriptor (required)                 │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ Entry 1: Kernel Code Segment                        │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ Entry 2: Kernel Data Segment                        │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ Entry 3: User Code Segment                          │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ Entry 4: User Data Segment                          │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ Entry 5: Task A's LDT Descriptor                    │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ Entry 6: Task A's TSS Descriptor                    │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ Entry 7: Task B's LDT Descriptor                    │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ Entry 8: Task B's TSS Descriptor                    │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘

GDTR Register (inside CPU):
┌─────────────────────────────────────────────────────────────┐
│ Base Address: Points to start of GDT in memory              │
│ Limit: Size of GDT - 1                                      │
└─────────────────────────────────────────────────────────────┘
```

##### What Goes in the GDT?

**System-wide resources that multiple tasks might need:**

**1. Operating System Segments**
- Kernel code segment (Ring 0)
- Kernel data segment (Ring 0)
- System service segments

**2. Common User Segments**
- Standard user code segment (Ring 3)
- Standard user data segment (Ring 3)

**3. Task Management Descriptors**
- Task State Segments (TSS) for each task
- Local Descriptor Table (LDT) descriptors for each task

**4. Device Driver Segments**
- Driver code segments
- Shared system libraries


##### Example GDT Layout

```
┌─────┬───────────────────┬──────────┬─────────┬─────────────────┐
│Index│ Description       │ Base     │ Limit   │ Access Rights   │
├─────┼───────────────────┼──────────┼─────────┼─────────────────┤
│  0  │ NULL (required)   │ 00000000 │ 00000   │ 00000000        │
├─────┼───────────────────┼──────────┼─────────┼─────────────────┤
│  1  │ Kernel Code       │ 00000000 │ FFFFF   │ 9A (Ring 0, X/R)│
├─────┼───────────────────┼──────────┼─────────┼─────────────────┤
│  2  │ Kernel Data       │ 00000000 │ FFFFF   │ 92 (Ring 0, R/W)│
├─────┼───────────────────┼──────────┼─────────┼─────────────────┤
│  3  │ User Code         │ 00000000 │ FFFFF   │ FA (Ring 3, X/R)│
├─────┼───────────────────┼──────────┼─────────┼─────────────────┤
│  4  │ User Data         │ 00000000 │ FFFFF   │ F2 (Ring 3, R/W)│
├─────┼───────────────────┼──────────┼─────────┼─────────────────┤
│  5  │ Text Editor LDT   │ 00200000 │ 01000   │ 82 (LDT, Ring 0)│
├─────┼───────────────────┼──────────┼─────────┼─────────────────┤
│  6  │ Text Editor TSS   │ 00201000 │ 00068   │ 89 (TSS, Ring 0)│
├─────┼───────────────────┼──────────┼─────────┼─────────────────┤
│  7  │ Web Browser LDT   │ 00300000 │ 01000   │ 82 (LDT, Ring 0)│
├─────┼───────────────────┼──────────┼─────────┼─────────────────┤
│  8  │ Web Browser TSS   │ 00301000 │ 00068   │ 89 (TSS, Ring 0)│
└─────┴───────────────────┴──────────┴─────────┴─────────────────┘
```

#### Local Descriptor Table (LDT)

A Local Descriptor Table is a task-specific table containing descriptors that are private to one particular task. Think of it as each task's "private address book."

##### Key Differences: GDT vs LDT

```
GDT (Global - Shared):           LDT (Local - Private):
┌─────────────────────┐         ┌─────────────────────┐
│ • One per system    │         │ • One per task      │
│ • Shared by all     │         │ • Private to task   │
│ • System resources  │         │ • Task resources    │
│ • Always available  │         │ • Only when task    │
│                     │         │   is running        │
└─────────────────────┘         └─────────────────────┘
```
##### How LDTs Work

**Step 1: LDT Descriptor in GDT**
The GDT contains a descriptor that points to each task's LDT:

```
GDT Entry 5 (Text Editor's LDT):
┌─────────────────────────────────────────────────────────────┐
│ Base: 0x200000  ← Physical address where LDT is stored      │
│ Limit: 0x1000   ← LDT can hold up to 512 descriptors        │
│ Type: LDT       ← This is an LDT descriptor                 │
│ DPL: 0          ← Ring 0 (system manages LDTs)              │
└─────────────────────────────────────────────────────────────┘
```

**Step 2: LDT Contains Task's Private Descriptors**

```
At physical address 0x200000 (Text Editor's LDT):
┌─────────────────────────────────────────────────────────────┐
│ Entry 0: NULL                                               │
│ Entry 1: Text Editor Code Segment                           │
│ Entry 2: Text Editor Data Segment                           │
│ Entry 3: Text Editor Stack Segment                          │
│ Entry 4: Document Buffer Segment                            │
│ Entry 5: Font Library Segment                               │
└─────────────────────────────────────────────────────────────┘
```

##### LDT Entries

LDT entries follow the exact same 8-byte descriptor format as GDT entries. An LDT is a block of (linear) memory up to 64K in size, just like the GDT. The difference from the GDT is in the Descriptors that it can store, and the method used to access it.

Both use the same:
- 64-bit (8-byte) descriptor structure
- Same Base/Limit/Access byte/Flags layout
- Same bit positions for all fields


However, there are content restrictions for LDT:
- LDT cannot hold system segments (Task State Segments and Local Descriptor Tables) 
- LDT can only contain application segments (code/data) and some gates
- GDT can contain everything (application segments, system segments, LDT descriptors, TSS descriptors)

#### What Are Gates?

Gates are special descriptors that act as "doorways" for controlled transfers of execution. Unlike regular segment descriptors that point to memory regions, gates contain entry points (addresses) where execution should transfer to.

##### Types of Gates in x86:

**1. Call Gates**
- **Purpose:** Allow controlled calls from lower privilege code to higher privilege code
- **Function:** Like a "secure function pointer" - lets user code (Ring 3) safely call kernel functions (Ring 0)
- **Contains:** Target code segment selector + offset where to jump
- **Security:** CPU automatically checks privilege levels and switches stacks if needed

**2. Task Gates**
- **Purpose:** Trigger hardware task switches
- **Function:** Points to a TSS descriptor to switch to a different task
- **Contains:** TSS selector that identifies which task to switch to
- **Usage:** Can be placed in IDT for task-switching interrupts

**3. Interrupt Gates**
- **Purpose:** Handle interrupts and exceptions
- **Function:** Similar to call gates but for interrupt handling
- **Contains:** Target code segment + interrupt handler address
- **Behavior:** Automatically disables interrupts when called

**4. Trap Gates**
- **Purpose:** Handle exceptions and software interrupts
- **Function:** Like interrupt gates but doesn't disable interrupts
- **Contains:** Target code segment + exception handler address
- **Usage:** For system calls and debugging exceptions

**Why Gates Can Be in LDT:**

While LDT cannot contain system segments (TSS, LDT descriptors), it can contain gates because:
- **Call gates:** Allow process-specific entry points to system services
- **Task gates:** Could theoretically allow process-specific task switching (though rarely used)

**Example Use Case:**

```
Process A's LDT might contain:
├── Code Segment (Ring 3)
├── Data Segment (Ring 3) 
├── Call Gate → Kernel function for file I/O
└── Call Gate → Kernel function for memory allocation
```

This way, each process can have its own set of "approved" kernel entry points through call gates in their private LDT, while the kernel maintains control over exactly which functions can be called and how.

In practice: Modern operating systems rarely use LDTs or gates, preferring software-based system call mechanisms and paging-based memory protection. But the hardware still supports these features for compatibility and specialized use cases.

#### GDTR and LDTR

The processor locates the GDT and the current LDT in memory by means of the GDTR and LDTR registers. These registers store the base addresses of the tables in the linear address space and store the segment limits. 

##### GDTR (Global Descriptor Table Register):

```
┌─────────────────────────────────────────────────────────────┐
│ GDTR - Simple pointer structure                             │
├─────────────────────────────────┬───────────────────────────┤
│ Base Address (32-bit)           │ Limit (16-bit)            │
│ Linear address of GDT in memory │ Size of GDT - 1           │
└─────────────────────────────────┴───────────────────────────┘
```

- Direct pointer to GDT location in memory
- Loaded with `LGDT` instruction
- Contains actual memory address and size

##### LDTR (Local Descriptor Table Register):

```
┌─────────────────────────────────────────────────────────────┐
│ LDTR - Segment register with selector + cached descriptor   │
├─────────────────────────────────────────────────────────────┤
│ Visible: LDT Selector (16-bit)                              │
├─────────────────────────────────────────────────────────────┤
│ Hidden: Cached LDT Descriptor (64-bit)                      │
│ Base + Limit + Access Rights from GDT entry                 │
└─────────────────────────────────────────────────────────────┘
```

- Indirect reference through GDT selector
- The LDT is defined as a 'normal' memory Segment inside the GDT - simply with a Base memory address and Limit 
- Loaded with LLDT instruction using a selector
- CPU automatically fetches LDT descriptor from GDT and caches it

**The Relationship:**

- GDTR points directly to GDT in memory
- LDTR contains a selector that points to an entry within the GDT
- That GDT entry describes where the LDT is located
- CPU caches that LDT descriptor information from GDT in LDTR's hidden part

##### WHo can Read/Write into GDTR and LDTR registers?

**GDTR (Global Descriptor Table Register):**

- **Set by:** Operating system kernel (Ring 0 code only)
- **Instructions:** LGDT (Load GDT) and SGDT (Store GDT)
- **Privilege:** These instructions can only be executed in Ring 0 (kernel mode)
- **When:** During OS boot/initialization

**LDTR (Local Descriptor Table Register):**

- **Set by:** Operating system kernel (Ring 0 code only)
- **Instructions:** LLDT (Load LDT) and SLDT (Store LDT)
- **Privilege:** Ring 0 only
- **When:** During task/process creation or context switches


##### Initial Setup Process:

**1. System Boot Sequence:**

```
1. CPU starts in Real Mode (no GDTR/LDTR)
2. Bootloader loads OS kernel
3. Kernel creates initial GDT in memory
4. Kernel executes LGDT to set GDTR
5. Kernel switches to Protected Mode
6. Kernel can now create LDTs and set LDTR as needed
```

**2. GDT Creation (by OS Kernel):**

```C
// Kernel code (Ring 0) during boot
struct gdt_entry gdt[8];  // Array in kernel memory

// Set up null descriptor (entry 0)
gdt[0] = {0};

// Set up kernel code segment (entry 1) 
gdt[1] = {base: 0, limit: 0xFFFFF, access: 0x9A, flags: 0xC};

// Set up kernel data segment (entry 2)
gdt[2] = {base: 0, limit: 0xFFFFF, access: 0x92, flags: 0xC};

// Set up user code segment (entry 3)
gdt[3] = {base: 0, limit: 0xFFFFF, access: 0xFA, flags: 0xC};

// More entries...

// Load the GDT
struct gdt_ptr {
    uint16_t limit;
    uint32_t base;
} gdt_descriptor = {sizeof(gdt)-1, (uint32_t)gdt};

asm("lgdt %0" : : "m"(gdt_descriptor));
```

##### Who Can Read/Write GDT and LDT?

**Reading:**

GDT/LDT contents: Any code can read (they're just memory)
GDTR/LDTR values: SGDT/SLDT instructions (Ring 0 only)

**Writing:**

GDT/LDT contents: Only Ring 0 code should modify (by convention)
GDTR/LDTR registers: Only Ring 0 via LGDT/LLDT

**Memory Protection:**

GDT location: Kernel typically places GDT in kernel-only memory pages
LDT location: Can be in user-accessible memory (but user can't change LDTR)

##### Post 80386 Era

- SGDT/SLDT: Ring 3 accessible (any privilege level)
- LGDT/LLDT: Still Ring 0 only

**Why Intel Made This Change:**

**Practical Reasons:**

- Debugging tools: Debuggers and system utilities needed to examine system state
- Virtual machines: VM software needed to read GDT/IDT information
- System monitoring: Performance tools and diagnostics required access
- Compatibility: Some software had legitimate needs to read (not write) this info

**Security Analysis:**

- Reading GDTR/IDTR: Reveals memory layout but doesn't grant control
- Still protected: Only reading allowed - writing still requires Ring 0
- Limited exposure: Knowing GDT location doesn't directly compromise security

**Modern Usage:**

This change enabled:
- Hypervisors: VMware, VirtualBox can inspect guest OS descriptor tables
- Security tools: Rootkit detectors can examine system structures
- Debuggers: WinDbg, GDB can show detailed system state
- OS utilities: System information tools can display memory management details

### Task State Segment (TSS)

The Task State Segment (TSS) is a special data structure that contains the complete execution state of a task (program). Think of it as a "snapshot" that captures everything the CPU needs to know about a task - all its registers, memory settings, and execution context.

Before the 80286, task switching was a manual, error-prone process:

```
Manual Task Switching (8086 era):
┌─────────────────────────────────────────────────────────────┐
│ 1. Programmer saves all registers manually                  │
│    MOV [task_a_ax], AX                                      │
│    MOV [task_a_bx], BX                                      │
│    MOV [task_a_cx], CX                                      │
│    ... (save 20+ registers and flags)                       │
│                                                             │
│ 2. Programmer loads new task's registers manually           │
│    MOV AX, [task_b_ax]                                      │
│    MOV BX, [task_b_bx]                                      │
│    ... (load 20+ registers and flags)                       │
│                                                             │
│ 3. Programmer manages memory segments manually              │
│    MOV DS, [task_b_ds]                                      │
│    MOV ES, [task_b_es]                                      │
│                                                             │
│ Problems:                                                   │
│ ❌ 50+ instructions per task switch                         │
│ ❌ Easy to forget registers                                 │
│ ❌ No atomic operation                                      │
│ ❌ No protection                                            │
│ ❌ Very slow                                                │
└─────────────────────────────────────────────────────────────┘
```

#### TSS Solution:

```
Hardware Task Switching (80286):
┌─────────────────────────────────────────────────────────────┐
│ Single instruction: JMP task_selector                       │
│                                                             │
│ Hardware automatically:                                     │
│ ✅ Saves ALL current state to current TSS                   │
│ ✅ Loads ALL new state from target TSS                      │
│ ✅ Updates memory management (LDT switch)                   │
│ ✅ Atomic operation (cannot be interrupted)                 │
│ ✅ Hardware protection checks                               │
│ ✅ Extremely fast (few clock cycles)                        │
└─────────────────────────────────────────────────────────────┘
```

#### TSS Structure and Layout

The 80286 TSS is a 44-byte (104 bytes with I/O bitmap [^i/o-bitmap]) data structure containing every piece of information needed to resume a task:

```
TSS Layout (80286):
┌─────────────────────────────────────────────────────────────┐
│ Offset │ Size │ Field Name        │ Description             │
├────────┼──────┼───────────────────┼─────────────────────────┤
│   00h  │  2   │ Previous TSS Link │ Selector of previous    │
│        │      │                   │ task (for nested calls)│
├────────┼──────┼───────────────────┼─────────────────────────┤
│   02h  │  2   │ SP0 (Stack Ring 0)│ Stack pointer for Ring 0│
├────────┼──────┼───────────────────┼─────────────────────────┤
│   04h  │  2   │ SS0 (Stack Ring 0)│ Stack segment for Ring 0│
├────────┼──────┼───────────────────┼─────────────────────────┤
│   06h  │  2   │ SP1 (Stack Ring 1)│ Stack pointer for Ring 1│
├────────┼──────┼───────────────────┼─────────────────────────┤
│   08h  │  2   │ SS1 (Stack Ring 1)│ Stack segment for Ring 1│
├────────┼──────┼───────────────────┼─────────────────────────┤
│   0Ah  │  2   │ SP2 (Stack Ring 2)│ Stack pointer for Ring 2│
├────────┼──────┼───────────────────┼─────────────────────────┤
│   0Ch  │  2   │ SS2 (Stack Ring 2)│ Stack segment for Ring 2│
├────────┼──────┼───────────────────┼─────────────────────────┤
│   0Eh  │  2   │ IP                │ Instruction Pointer     │
├────────┼──────┼───────────────────┼─────────────────────────┤
│   10h  │  2   │ FLAGS             │ Processor flags         │
├────────┼──────┼───────────────────┼─────────────────────────┤
│   12h  │  2   │ AX                │ General register AX     │
├────────┼──────┼───────────────────┼─────────────────────────┤
│   14h  │  2   │ CX                │ General register CX     │
├────────┼──────┼───────────────────┼─────────────────────────┤
│   16h  │  2   │ DX                │ General register DX     │
├────────┼──────┼───────────────────┼─────────────────────────┤
│   18h  │  2   │ BX                │ General register BX     │
├────────┼──────┼───────────────────┼─────────────────────────┤
│   1Ah  │  2   │ SP                │ Stack Pointer           │
├────────┼──────┼───────────────────┼─────────────────────────┤
│   1Ch  │  2   │ BP                │ Base Pointer            │
├────────┼──────┼───────────────────┼─────────────────────────┤
│   1Eh  │  2   │ SI                │ Source Index            │
├────────┼──────┼───────────────────┼─────────────────────────┤
│   20h  │  2   │ DI                │ Destination Index       │
├────────┼──────┼───────────────────┼─────────────────────────┤
│   22h  │  2   │ ES                │ Extra Segment           │
├────────┼──────┼───────────────────┼─────────────────────────┤
│   24h  │  2   │ CS                │ Code Segment            │
├────────┼──────┼───────────────────┼─────────────────────────┤
│   26h  │  2   │ SS                │ Stack Segment           │
├────────┼──────┼───────────────────┼─────────────────────────┤
│   28h  │  2   │ DS                │ Data Segment            │
├────────┼──────┼───────────────────┼─────────────────────────┤
│   2Ah  │  2   │ LDT Selector      │ Local Descriptor Table  │
└─────────────────────────────────────────────────────────────┘
```

#### Memory Layout Visualization




[^address-bus]: An address bus is a collection of wires (or electrical pathways) that carries memory addresses from the processor to memory and other components. Think of it as the "postal system" of the computer - when the CPU wants to read from or write to a specific location in memory, it sends that location's address through the address bus. Each wire in the address bus represents one bit of the address. The CPU sets each wire to either high voltage (representing binary 1) or low voltage (representing binary 0) to form the complete binary address.

[^COM1-4]:  (Serial Ports) Communication ports for devices like modems, mice, or serial printers. Each COM port has a base I/O address (COM1 typically at 3F8h, COM2 at 2F8h, etc.). The BIOS Data Area stores these addresses so software knows where to find each serial port.

[^LPT1-3]:  (Parallel Ports) "Line Printer" ports primarily used for parallel printers. LPT1 typically uses I/O address 378h. These were the standard way to connect printers before USB existed. The BIOS stores the base addresses of installed parallel ports.

[^Modifier-key-states]: Whether Shift, Ctrl, Alt, Caps Lock, Num Lock, or Scroll Lock are currently pressed or toggled. This is stored as bit flags in memory location 0040:0017h.

[^Keyboard-buffer]: A circular buffer (usually 15-16 characters) that stores keystrokes when they're typed faster than the program can process them. This prevents losing keystrokes during busy periods.

[^i/o-bitmap]: This bitmap, usually set up by the operating system when a task is started, specifies individual ports to which the program should have access. The I/O bitmap is a bit array of port access permissions; if the program has permission to access a port, a "0" is stored at the corresponding bit index, and if the program does not have permission, a "1" is stored there. When a program issues an x86 I/O port instruction such as IN or OUT, the hardware will do an I/O privilege level (IOPL) check to see if the program has access to all I/O ports. If the Current Privilege Level (CPL) of the program is numerically greater than the I/O Privilege level (IOPL), the program does not have I/O port access to all ports. If the IOPL check fails, the CPU then consults the I/O bitmap to see if this specific port is allowed. It prevents malicious programs from accessing hardware directly by stopping user programs from interfering with system devices.