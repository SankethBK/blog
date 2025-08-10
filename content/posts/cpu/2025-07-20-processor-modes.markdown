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

```
     20-bit physical address space   (1 MB total)
     ─────────────────────────────────────────────────────────
     00000h                                                      FFFFFh
        ↑                                                         ↑
        │                                                         │
        │<────────── 64 KB window (Segment N) ───────────>│
        │                                                 │
        │          │<────────── 64 KB window (Segment N+1) ───────────>│
        │          │                                      │
        │          └───────────  overlap  ────────----────┘
        │
   base = N × 16 bytes                base = (N+1) × 16 bytes
   address = (segment × 16) + offset  address = (segment × 16) + offset
```

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



[^address-bus]: An address bus is a collection of wires (or electrical pathways) that carries memory addresses from the processor to memory and other components. Think of it as the "postal system" of the computer - when the CPU wants to read from or write to a specific location in memory, it sends that location's address through the address bus. Each wire in the address bus represents one bit of the address. The CPU sets each wire to either high voltage (representing binary 1) or low voltage (representing binary 0) to form the complete binary address.

[^COM1-4]:  (Serial Ports) Communication ports for devices like modems, mice, or serial printers. Each COM port has a base I/O address (COM1 typically at 3F8h, COM2 at 2F8h, etc.). The BIOS Data Area stores these addresses so software knows where to find each serial port.

[^LPT1-3]:  (Parallel Ports) "Line Printer" ports primarily used for parallel printers. LPT1 typically uses I/O address 378h. These were the standard way to connect printers before USB existed. The BIOS stores the base addresses of installed parallel ports.

[^Modifier-key-states]: Whether Shift, Ctrl, Alt, Caps Lock, Num Lock, or Scroll Lock are currently pressed or toggled. This is stored as bit flags in memory location 0040:0017h.

[^Keyboard-buffer]: A circular buffer (usually 15-16 characters) that stores keystrokes when they're typed faster than the program can process them. This prevents losing keystrokes during busy periods.