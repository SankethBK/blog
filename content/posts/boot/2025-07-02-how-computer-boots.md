---
title:  "What happens when you turn on computer?"
date:   2025-07-02
draft: true
categories: ["boot"]
tags: ["boot"]
author: Sanketh
references:
    - title: Option ROM
      url: https://en.wikipedia.org/wiki/Option_ROM

    - title: Network Boot
      url: https://en.wikipedia.org/wiki/Network_booting

    - title: Bootloader Wiki
      url: https://wiki.osdev.org/Bootloader
---

## 1. Power‑On & Hardware Reset

### 1. Power‑Good Signal

The power supply stabilizes voltages and asserts a “Power‑Good” (PWR_OK) line to the motherboard. All devices receive power and begin to initialize themselves. The Central Processing Unit (CPU) is initially held in a reset mode, meaning it's not yet executing instructions. The memory layout is powered up, although the RAM itself has no content since it's volatile.

### 2. CPU Reset Vector

The reset vector is a predetermined memory address where the CPU begins execution after being powered on or reset. On x86 processors, this address is typically `0xFFFFFFF0` (near the top of the 4GB address space). When the CPU comes out of reset, its program counter (instruction pointer) is automatically set to this address. The motherboard's memory mapping ensures that this address points to the BIOS/UEFI firmware ROM chip, so the very first instruction the CPU executes comes from the firmware.

### 3. Microcode / Internal Init

Microcode is low-level firmware that lives inside the CPU itself. Microcode sits between the CPU's hardware and the instruction set architecture (ISA). It's a set of hardware-level instructions that implement the higher-level machine code instructions or control the finite-state machine within the processor. 
Modern CPUs may load or patch microcode from firmware to work around hardware errata before executing any instructions without changing the physical hardware.

## 2. Firmware Initialization 

### 1. POST (Power‑On Self Test)

When you press the power button, electricity flows to the motherboard and the Basic Input/Output System (BIOS) or Unified Extensible Firmware Interface (UEFI) stored in non-volatile memory springs to life. This firmware is the first code that runs, and it immediately begins the Power-On Self-Test. During POST, the system checks critical hardware components like RAM, CPU, storage devices, and peripheral connections. You'll often hear beeps or see LED indicators during this phase - these are diagnostic codes indicating whether hardware is functioning properly. Sets up basic text or graphic mode so you can see firmware messages.

### 2. Core Hardware Initialization

After POST completes successfully, the firmware initializes hardware components in a specific order. It configures the CPU, sets up memory controllers, initializes storage controllers, and establishes communication pathways between components. The firmware also detects and catalogs all connected hardware, building a map of available resources that will be passed to the operating system later.

### 3. Option ROMs & Plug‑In Cards

The firmware then scans all PCI and PCIe expansion slots [^pci-pcie], looking for add-in cards that have their own firmware called Option ROMs. These are small pieces of code stored on the expansion cards themselves - think of them as mini-BIOS programs for specific hardware components. 

Common examples include RAID controller cards (which need to initialize disk arrays), network interface cards (NICs) that might support network booting [^network-boot], graphics cards (which contain video BIOS for display initialization), and storage controllers for SCSI or SAS drives. When the firmware finds an Option ROM, it loads and executes this code, allowing the expansion card to initialize itself, register its services with the system, and make its capabilities available to both the firmware and the eventual operating system.

## 3. Boot Device Selection

### 1. Boot Order

The firmware consults its boot priority list (which you can modify in BIOS/UEFI settings) to determine which storage device to boot from. This could be a hard drive, SSD, USB drive, optical disc, or network location. It searches each device in order until it finds one with a valid boot sector or boot loader. The firmware examines each device for bootable signatures - on legacy BIOS systems, it looks for the magic number `0x55AA` at the end of the first sector, while UEFI systems search for valid EFI boot applications in the EFI System Partition. If a device fails to respond or lacks bootable content, the firmware moves to the next device in the priority list. This process continues until a valid boot device is found or all options are exhausted, at which point you'll see an error like "No bootable device found."

### 2. Secure Boot (UEFI only)

Secure Boot is a security feature that creates a chain of trust from firmware to operating system by using cryptographic signatures. When enabled, the firmware maintains a database of trusted cryptographic keys and will only execute boot loaders and OS kernels that are digitally signed with certificates matching these trusted keys. This prevents malicious software, rootkits, or unauthorized operating systems from loading during the boot process. 

## 4. Bootloader Stage: Master Boot Record (MBR) vs GUID Partition Table (GPT)

### 1. Master Boot Record (MBR) - Legacy BIOS Systems

The MBR is a 512-byte sector located at the very beginning of a storage device (Logical Block Address 0) [^logical-access-block]. This single sector contains everything needed to understand the disk's partition layout and begin the boot process.

#### MBR Structure Breakdown:

- **Bytes 0-445 (446 bytes):** Boot code area containing the Master Boot Record code, often called the "bootstrap" code. This is a tiny program that the BIOS loads and executes directly.
- **Bytes 446-509 (64 bytes):** Partition table containing four 16-byte entries, each describing a primary partition.
- **Bytes 510-511 (2 bytes):** Boot signature `0x55AA` that validates this as a bootable sector

**Each Partition Table Entry (16 bytes) contains:**

- Boot flag (1 byte) - indicates if this partition is active/bootable
- Starting CHS address (3 bytes) - Cylinder, Head, Sector in old addressing
- Partition type (1 byte) - identifies the file system (`0x83` for Linux, `0x07` for NTFS, etc.)
- Ending CHS address (3 bytes)
- Starting LBA address (4 bytes) - modern sector addressing
- Partition size in sectors (4 bytes)

#### MBR Boot Process:

When the BIOS finds a valid MBR, it loads all 512 bytes into memory at address `0x7C00` and jumps to that location. The MBR code then examines the partition table, finds the active partition (boot flag set), and loads the first sector of that partition (called the Partition Boot Record or Volume Boot Record) which contains the actual operating system boot loader.

#### MBR Limitations:

- Maximum of 4 primary partitions (workaround: extended partitions)
- Cannot handle disks larger than 2TB due to 32-bit LBA addressing
- Single point of failure - if MBR is corrupted, entire disk becomes unbootable
- No built-in redundancy or error correction

#### How MBR Supports booting multiple OSes

The MBR's job is simple and dumb. It scans the four entries in its partition table, finds the one and only one partition that has the "active" flag set, and then it loads the bootloader from that partition. It ignores the other three. That's it. The MBR boot code has no menu system, no user interface, no choice mechanism - it's too small and primitive for that.

The MBR itself doesn't load the operating system. Its sole job is to pass control to the next stage. This process is called **chain loading**.

1. BIOS/UEFI (in legacy mode) loads the MBR code (from the first sector of the boot device) into memory and executes it.
2.  MBR code finds the active partition and loads the boot code from that partition's first sector. This is known as the Partition Boot Record (PBR) or Volume Boot Record (VBR).
3.  PBR/VBR code contains the instructions needed to load the actual operating system files (like the Windows bootmgr or the Linux GRUB loader) from its own partition.
4. This creates a chain of trust, where each small program is responsible for loading and executing the next, slightly larger and more complex program, until the full OS kernel is running.

Example Multi-Boot Setup

```
Partition 1: /boot (active, contains GRUB) ← MBR points here
Partition 2: Ubuntu root filesystem
Partition 3: Windows NTFS
Partition 4: Shared data
```

Boot sequence:

1. MBR → finds active Partition 1 → loads GRUB
2. GRUB → shows menu: "Ubuntu or Windows?"
3. User selects → GRUB loads appropriate kernel or chain-loads Windows boot loader

#### Overcoming the 4-Partition Limit: Extended and Logical Partitions

The MBR's limit of four primary partitions was a significant constraint. To work around this, the concept of an extended partition was introduced.


- You can designate one of your four primary partitions as an "extended partition."
- This extended partition doesn't hold a filesystem directly. Instead, it acts as a container for multiple logical partitions.
- You can create many logical partitions inside this single extended partition, each with its own drive letter and filesystem.

A common disk layout might look like this:
- Primary Partition 1: Windows OS (C:)
- Primary Partition 2: Linux OS
- Primary Partition 3 (Extended Partition Container):
  - Logical Partition 1: Data Drive (D:)
  - Logical Partition 2: Backup Drive (E:)
  - Logical Partition 3: Shared Files (F:)
- Primary Partition 4: Empty/Unused

This system was a functional, if complex, workaround. However, it's a perfect example of the legacy baggage that led to the development of the much simpler and more powerful GUID Partition Table (GPT).

### GUID Partition Table (GPT) - Modern UEFI Systems

GPT is a much more sophisticated partitioning scheme that addresses all of MBR's limitations. It's part of the UEFI specification and provides better data integrity and flexibility.

- **LBA 0: Protective MBR:** For backward compatibility, the very first sector of a GPT disk still contains a 512 byte MBR styled memory called "protective" MBR. This MBR has a single partition entry of size same as disk's size and type `0xEE` (invalid partition type, to prevent legacy tools from misidentifying). This tricks the legacy MBR-only tools into thinking that the disk is already full so it can't create any new partitions from misidentifying the disk as unformatted and accidentally overwriting it.
- **LBA 1: Primary GPT Header:** This header defines the layout of the partition table itself. It contains:
   - A signature ("EFI PART") to identify it as a GPT disk.
   - The location of the partition entries.
   - The number of partition entries.
   - A unique GUID (Globally Unique Identifier) for the entire disk.
   - A CRC32 checksum for the header and the partition table, which allows the system to verify their integrity.
-  **LBA 2 to LBA 33 (typically):** Partition Entry Array: This is where the actual partition information is stored. By default, GPT allocates space for 128 partition entries (128 bytes each), though this can be changed.
- **Partition Data:** The rest of the disk is used for the actual partitions.
- **Last 33 LBAs:** Backup GPT header and partition entries (mirror of the beginning).

#### Each Partition Table Entry (128 bytes) contains:

- **Partition Type GUID (16 bytes):** A unique ID that specifies the partition's purpose (e.g., an EFI System Partition, a Microsoft basic data partition). This is far more
 specific than MBR's single-byte type code.
- **Unique Partition GUID (16 bytes):** Every single partition on the disk gets its own unique identifier.
- **Starting and Ending LBA address (8 bytes each):** Uses 64-bit addressing, allowing for astronomically large disk sizes.
- **Partition Attributes (8 bytes):** Flags that define properties like "read-only" or "bootable."
- **Partition Name (72 bytes):** A human-readable name (e.g., "Linux home") stored in Unicode.

#### GPT/UEFI Boot Process:

The boot process on a UEFI system with a GPT disk is fundamentally different and more robust than the legacy BIOS/MBR method.

1. The UEFI firmware initializes and scans the storage devices.
2. Instead of executing code from a boot sector, the UEFI firmware actively looks for a specific partition known as the EFI System Partition (ESP). The ESP is identified by its Partition Type GUID.
1. The UEFI firmware understands file systems (typically FAT32), so it can mount the ESP and browse its contents.
2. It looks for a bootloader application at a standardized file path, such as` \EFI\BOOT\BOOTX64.EFI` (for removable media) or a vendor-specific path like `\EFI\Microsoft\Boot\bootmgfw.efi` for Windows.
1. Once found, the firmware executes this `.efi` bootloader file directly, which then takes over to load the operating system kernel.


#### GPT Advantages over MBR:

- **Massive Disk Sizes:** Supports disks larger than 2TB (up to 9.4 ZB - zettabytes - in theory) thanks to 64-bit LBA addressing.
- **More Partitions:** Allows for 128 primary partitions by default, eliminating the need for the complex extended/logical partition scheme.
- **Redundancy and Reliability**: The backup GPT header and CRC32 checksums provide protection against data corruption in the partition table. If the primary header is damaged, the disk can be recovered from the backup.
- **No "Active" Partition:** The bootable partition is defined in the UEFI firmware's boot manager settings, not by a fragile flag on the partition itself, making multi-booting cleaner.
- **Unique IDs:** Using GUIDs for both the disk and partitions prevents potential conflicts and collisions that could occur with MBR systems.

## 5. Kernel Loading

Once the bootloader has been identified and loaded by either the BIOS/MBR or UEFI/GPT process, its one and only job is to find the operating system's kernel, load it into memory, and hand over control of the system. This is the moment the actual operating system begins to take charge.

### 1. Boot Loader to Kernel Handoff

The bootloader (like GRUB for Linux or the Windows Boot Manager) knows where to find the kernel file on the storage device (e.g., `vmlinuz` in Linux [^vmlinuz], `ntoskrnl.exe` in Windows [^ntoskrnl]). But the kernel alone isn't enough.

Modern kernels are modular and don't contain every possible hardware driver. To solve this chicken-and-egg problem—where the kernel needs drivers to access the disk, but the drivers are on the disk—the bootloader also loads an **initial RAM disk (initrd**) or **initial RAM filesystem (initramfs)** into memory alongside the kernel.

This `initrd` is a temporary, compressed filesystem that contains the essential drivers and tools needed for the kernel to access the main storage device and other critical hardware.

#### 1. Memory Layout Setup:

- The kernel is loaded at a specific memory address (typically around 1MB on x86 systems).
- Boot loader creates a memory map showing which areas are safe to use.
- Sets up initial page tables for virtual memory management.
- Preserves important boot information in memory that the kernel will need.

#### 2. CPU State Preparation:

- Switches CPU from 16-bit real mode to 32-bit protected mode (or 64-bit long mode).
- Disables interrupts temporarily.
- Sets up initial stack pointer.
- Prepares CPU registers with boot parameters.

**Boot Parameters:** The boot loader passes crucial information to the kernel through standardized protocols:

- Linux: Boot protocol with command line arguments, initrd location, memory map
- Windows: Boot Configuration Data (BCD) and hardware abstraction layer info
- Hardware details: Available RAM, CPU features, device tree (on ARM systems)

## 3. Kernel Initialization: Building the System

The moment the kernel begins executing, it runs in a highly constrained environment. It must bootstrap itself, initializing all its core subsystems to transform the raw hardware into a fully functional operating system.

### 1. Entry Point and Early Setup

The kernel's very first instructions are architecture-specific and focus on creating a stable environment for the rest of the initialization:

- **Initializes Core CPU Structures:** Sets up the Interrupt Descriptor Table (IDT) to handle hardware interrupts and exceptions, though interrupts remain disabled for now.
- **Processes Boot Information:** Parses the command-line arguments and memory map passed by the bootloader to understand its environment and available resources.
- **Validates Integrity:** If Secure Boot is enabled, the kernel validates its own digital signature to ensure it hasn't been tampered with.


### 2. Memory Management Initialization

The kernel immediately takes control of all system memory:

- **Virtual Memory Setup:** It creates a comprehensive set of page tables to map virtual addresses to physical RAM addresses, establishing the kernel's own protected address space.
- **Physical Memory Management:** Using the map from the bootloader, it builds a complete picture of physical memory, initializing allocators (like the buddy and slab allocators) to manage free and used memory frames.

### 3. Core Subsystem Initialization

With memory management active, the kernel brings its fundamental components online:

- **Process Management:** Creates the first process, the idle process (PID 0), and initializes the process scheduler, which is responsible for task switching.
- **Interrupt and Exception Handling:** Configures the system's interrupt controllers (PIC/APIC) and enables interrupts, allowing hardware to communicate with the CPU.
- **Synchronization Primitives:** Initializes the low-level mechanisms like mutexes, semaphores, and spinlocks that are essential for preventing data corruption on multiprocessor systems.

### 4. Device and Driver Infrastructure

The kernel sets up the framework for communicating with hardware:

- **Device Model Framework:** Initializes the device driver subsystem and parses hardware information from ACPI tables (on x86) or a device tree (on ARM) to discover what hardware is present.
- **Essential Driver Loading:** Loads the built-in drivers compiled directly into the kernel, focusing on those needed to access the root filesystem (e.g., SATA/NVMe drivers).
- **Hardware Abstraction:** Initializes platform-specific code and Hardware Abstraction Layers (HAL) to provide a consistent interface for the rest of the kernel to interact with the underlying hardware.

### 5. Filesystem and I/O Preparation

Before it can mount the root filesystem, the kernel prepares its I/O subsystems:

- **Virtual File System (VFS):** Initializes the VFS, an abstraction layer that allows the kernel to treat all filesystems (like ext4, NTFS, etc.) in a uniform way.
- **Block Device Layer:** Initializes the subsystem that manages block devices (like hard drives and SSDs) and sets up I/O schedulers to optimize disk requests.

### 6. Initial Process Creation

The kernel creates its own essential background threads (like kthreadd for managing other kernel threads) and then prepares to make the critical leap from kernel space to user space.

### 7. Transition to User Space

- **Mounting the Root Filesystem:** The kernel first mounts the initrd/initramfs as a temporary root filesystem. The drivers and tools in the initrd are used to mount the real root filesystem from the main storage device.
- **Launching the Init Process:** The kernel creates the very first user-space process, which is given Process ID 1 (PID 1). This process is the ancestor of all other user processes. On modern Linux systems, this is systemd; on Windows, it's smss.exe.


### 8. Handoff to the Init System


At this point, the kernel's primary initialization is complete. It has transformed into a fully preemptive, multitasking operating system kernel. While the kernel continues to run for the lifetime of the system—managing hardware, handling interrupts, and processing system calls—it now hands the responsibility of finishing the boot process to the **init system**. The init system is responsible for starting all the higher-level services, such as networking, background daemons, and ultimately, the user login screen.

[^pci-pcie]: **PCI (Peripheral Component Interconnect) and PCIe (Peripheral Component Interconnect Express)** are both interface standards for connecting hardware components to a computer's motherboard, but PCIe is a newer, faster, and more flexible version of PCI. 

[^network-boot]: **Network booting (PXE - Preboot Execution Environment)** allows a computer to boot an operating system directly from a network server rather than local storage. When enabled, the network card's Option ROM takes control during the boot process and broadcasts a DHCP request that includes PXE-specific information. A PXE-enabled DHCP server responds with an IP address for the client plus the location of a TFTP (Trivial File Transfer Protocol) server and the filename of a network boot loader. The client then downloads this small boot loader over the network and executes it, which in turn can download a kernel, initial ramdisk, or even a complete operating system image. This technology is commonly used in corporate environments for automated OS deployment, diskless workstations, and system recovery scenarios, as it allows administrators to boot and manage hundreds of computers from a central server without needing individual storage devices or manual intervention on each machine.

[^logical-access-block]: **Logical Block Address 0** refers to the first addressable unit of storage on a device. Think of LBA as a simple numbering system that starts from 0 and counts up sequentially. Modern storage devices use LBA as an abstraction layer that hides the physical complexity of how data is actually stored. Whether it's a traditional hard drive with physical cylinders, heads, and sectors, or a solid-state drive with flash memory cells arranged in pages and blocks, the operating system and firmware see everything as a linear sequence of logical blocks.

[^vmlinuz]: vmlinuz is the name of the Linux kernel executable file. The name is historical and descriptive:
      - vm: Stands for Virtual Memory, indicating the kernel supports this feature.
      - linuz: Refers to the Linux kernel, and the z at the end signifies that it is a zlib-compressed executable.
    When the bootloader loads this file, the first thing the kernel does is decompress itself into memory before it begins initializing the system.

[^ntoskrnl]: ntoskrnl.exe stands for Windows NT Operating System Kernel. It is the fundamental kernel space module for the Windows NT family of operating systems (including all modern versions like Windows 10/11 and Windows Server). This single executable file contains the Windows kernel, the executive, the memory manager, and other core components responsible for managing the system's hardware and software resources.
