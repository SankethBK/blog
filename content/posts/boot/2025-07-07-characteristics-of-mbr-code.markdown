---
title: 'Characteristics of MBR Code'
date:   2025-07-12
categories: ["boot"]
tags: ["boot"]
author: Sanketh

---

# BIOS Boot Recap

Previously, we saw that after the BIOS firmware is loaded, it searches for a bootable device from a list of storage options, such as a hard drive, SSD, USB, or network interface. The BIOS identifies a valid bootable device by checking for the `0x55AA` signature at the end of the first sector. Once found, it loads the 512 bytes from this sector (LBA 0), which is known as the Master Boot Record (MBR).

**MBR Structure Breakdown:**

- **Bytes 0-445 (446 bytes):** The boot code, often called the "bootstrap" code. This is the small program that the BIOS executes.
- **Bytes 446-509 (64 bytes):** The partition table, which contains four 16-byte entries, each describing a primary partition.
- **Bytes 510-511 (2 bytes):** The boot signature (`0x55AA`), which validates the sector as bootable.

# What is this 446-byte code supposed to do?

## 1. Hardware Initialization:

The code initializes basic hardware components and sets up the processor to operate in a known state.

The hardware initialization performed by MBR code is quite limited but crucial for establishing a stable foundation for the boot process. Let me detail what actually happens:

### Processor State Setup:

#### Register Initialization:
- Sets up segment registers (CS, DS, ES, SS) to known values
- Initializes the stack pointer (SP) to create a small working stack
- Clears or sets specific CPU flags to ensure predictable behavior
- The BIOS typically loads MBR at physical address 0x7C00, so CS:IP points there

#### Interrupt Handling:

- May disable interrupts temporarily during critical operations
- Sets up or modifies interrupt vectors for basic hardware services
- Ensures the processor can handle hardware interrupts predictably

#### Memory Setup:

#### Stack Configuration:

- Establishes a small stack space (usually just a few hundred bytes)
- Sets SS (Stack Segment) and SP (Stack Pointer) registers
- This is essential since the code needs stack space for function calls and local variables

#### Memory Map Awareness:

- The code must work within the known memory layout established by BIOS
- Avoids overwriting critical BIOS data areas
- Understands where it can safely use memory for temporary storage

## 2. Partition Table Reading:

It reads and interprets the partition table (located in the remaining 66 bytes of the 512-byte MBR) to identify which partition is marked as active/bootable.

## 3. Active Partition Location:

The code searches through the four partition table entries to find the one marked with the boot flag (0x80), indicating it's the active partition.

## 4. Loading the Volume Boot Record:

Once the active partition is identified, the boot loader loads the first sector of that partition (called the Volume Boot Record or VBR) into memory.

## 5. Transfer Control:

After loading the VBR, the MBR code transfers execution control to the VBR, which then continues the boot process by loading the operating system.

## 6. Error Handling:

The code includes basic error handling to display messages like "Invalid partition table" or "Missing operating system" if problems are encountered.

# Capabilities and Constraints of MBR Code

## Capabilities

### Direct Hardware Access

You have unrestricted access to all hardware components including the CPU, memory, I/O ports, and peripherals. This exists because there's no operating system yet to provide protection or abstraction layers - you're running at the highest privilege level (Ring 0) with complete system control, giving you direct access to all processor features and hardware resources.

### BIOS Interrupt Services

Access to firmware-provided functions through software interrupts (INT 0x10 for video, INT 0x16 for keyboard, INT 0x13 for disk, etc.). These services exist because the BIOS firmware pre-loads basic hardware drivers and makes them available through standardized interrupt vectors, giving you a minimal but functional hardware abstraction layer.

### Real Mode Memory Access

Direct access to the first 1MB of system memory using segmented addressing (segment:offset pairs). This capability exists because the x86 processor boots into real mode by design, maintaining backward compatibility with the original 8086 processor from 1978.

### 16-bit Assembly Instructions

Full access to the 8086/8088 instruction set including arithmetic, logical, control flow, and string operations. These instructions are available because real mode provides the complete 16-bit instruction set that forms the foundation of x86 architecture.

### Processor Mode Control

Ability to read and modify CPU control registers (CR0, CR1, etc.) and potentially transition the processor from real mode to protected mode or other operating modes. This capability exists because you have unrestricted access to all processor control mechanisms - no operating system is preventing you from changing fundamental CPU behavior.

### Stack Operations

Ability to use PUSH, POP, CALL, and RET instructions with a manually configured stack. This works because you can set up the Stack Segment (SS) and Stack Pointer (SP) registers to create a small working stack in available memory space.

### String and Memory Manipulation

Direct string operations (MOVSB, STOSB, LODSB) and memory copying without bounds checking. These operations are possible because real mode provides direct memory access without protection mechanisms - you can read from and write to any memory location.

### Interrupt Control

Ability to enable/disable interrupts (CLI/STI) and define custom interrupt handlers. This capability exists because you're running at privilege level 0 with complete control over the interrupt system, allowing you to modify the Interrupt Vector Table.

### Port I/O Operations

Direct access to hardware ports using IN and OUT instructions for controlling devices like the keyboard controller, timer, or speaker. This works because real mode doesn't restrict port access, and these ports are how the processor communicates directly with hardware components. 

## Constraints

### No Standard Library Functions

No access to printf(), strlen(), malloc(), or any C standard library functions. This constraint exists because these functions are provided by the operating system's runtime library, which doesn't exist yet - you're running before any OS is loaded.

### No File System Operations

Cannot open, read, or write files using standard file operations. This limitation exists because file systems are managed by the operating system, and you're running at a level before any file system drivers are loaded. You can only access raw disk sectors through BIOS interrupts.

### No Memory Management

No dynamic memory allocation (malloc/free) or memory protection. This constraint exists because memory management is an operating system service, and you're limited to the simple segmented memory model of real mode with no virtual memory or heap management.

### No Multi-threading or Process Management

Cannot create threads, processes, or handle concurrent execution. This limitation exists because these are operating system abstractions that require kernel services, scheduler, and process management - none of which exist in the pre-boot environment.

### No 32-bit or 64-bit Operations

Limited to 16-bit registers and operations, cannot use extended 32-bit (EAX, EBX, etc.) or 64-bit registers. This constraint exists because the processor boots into 16-bit real mode for backward compatibility, and transitioning to protected mode or long mode requires explicit mode switching code.

### No Floating-Point Operations

Cannot perform floating-point arithmetic without manual FPU initialization. This limitation exists because the Floating-Point Unit requires explicit initialization and setup, which isn't done automatically in the minimal boot environment.

### No Exception Handling

No try/catch mechanisms or structured exception handling. This constraint exists because exception handling is a high-level language feature that requires runtime support and operating system services to manage exception contexts and handlers.

### No Network or Advanced I/O

Cannot access network interfaces, USB devices, or modern peripherals without writing complex driver code. This limitation exists because these devices require sophisticated drivers and initialization sequences that aren't provided by the basic BIOS services.


[^0x7C00]: The BIOS loads the 510‑byte sector to segment:offset 0000:7C00, which equals physical address 0x7C00. The lower 2 KB of RAM (0x0000–07FF) already hosts the interrupt‑vector table and the BIOS Data Area, so 0x7C00 was the first convenient free gap on the original IBM PC—and the convention stuck. Immediately on entry the stub usually copies itself downward to something like 0x0600 (or 0x0500). That frees 0x7C00 so it can be overwritten by the Volume Boot Record (VBR) from the active partition that the stub is about to load. The destination (0x0600–07BF) lies safely below 0x7C00 and above the BIOS Data Area, so nothing important is overwritten. It tansfers control (jmp 0x0000:0x7C00) so the OS-specific stage-1½/2 bootloader can continue.
