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
---

## 1. Power‑On & Hardware Reset

### 1. Power‑Good Signal

The power supply stabilizes voltages and asserts a “Power‑Good” (PWR_OK) line to the motherboard. All devices receive power and begin to initialize themselves. The Central Processing Unit (CPU) is initially held in a reset mode, meaning it's not yet executing instructions. The memory layout is powered up, although the RAM itself has no content since it's volatile.

### 2. CPU Reset Vector

The reset vector is a predetermined memory address where the CPU begins execution after being powered on or reset. On x86 processors, this address is typically 0xFFFFFFF0 (near the top of the 4GB address space). When the CPU comes out of reset, its program counter (instruction pointer) is automatically set to this address. The motherboard's memory mapping ensures that this address points to the BIOS/UEFI firmware ROM chip, so the very first instruction the CPU executes comes from the firmware.

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
- Partition type (1 byte) - identifies the file system (0x83 for Linux, 0x07 for NTFS, etc.)
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

[^pci-pcie]: **PCI (Peripheral Component Interconnect) and PCIe (Peripheral Component Interconnect Express)** are both interface standards for connecting hardware components to a computer's motherboard, but PCIe is a newer, faster, and more flexible version of PCI. 

[^network-boot]: **Network booting (PXE - Preboot Execution Environment)** allows a computer to boot an operating system directly from a network server rather than local storage. When enabled, the network card's Option ROM takes control during the boot process and broadcasts a DHCP request that includes PXE-specific information. A PXE-enabled DHCP server responds with an IP address for the client plus the location of a TFTP (Trivial File Transfer Protocol) server and the filename of a network boot loader. The client then downloads this small boot loader over the network and executes it, which in turn can download a kernel, initial ramdisk, or even a complete operating system image. This technology is commonly used in corporate environments for automated OS deployment, diskless workstations, and system recovery scenarios, as it allows administrators to boot and manage hundreds of computers from a central server without needing individual storage devices or manual intervention on each machine.

[^logical-access-block]: **Logical Block Address 0** refers to the first addressable unit of storage on a device. Think of LBA as a simple numbering system that starts from 0 and counts up sequentially. Modern storage devices use LBA as an abstraction layer that hides the physical complexity of how data is actually stored. Whether it's a traditional hard drive with physical cylinders, heads, and sectors, or a solid-state drive with flash memory cells arranged in pages and blocks, the operating system and firmware see everything as a linear sequence of logical blocks.