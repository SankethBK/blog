---
title:  "How does CPU Communicates With Peripheral Devices"
date:   2025-08-09
draft: true
categories: ["cpu"]
tags: ["cpu", "x86"]
author: Sanketh
references:
---

# Introduction: The Communication Challenges

At its core, a CPU is designed for one primary task: processing data and executing instructions at incredible speed. But this processing power becomes meaningful only when it can interact with the rich ecosystem of peripheral devices that extend its capabilities. 

## Why CPUs Need to Talk to Many Different Devices?

Your CPU must read input from your mouse or keyboard, process that input to understand your intent, communicate with memory to load the browser application, send rendering commands to your graphics card, request data from your network interface to load the webpage, and potentially write temporary files to your storage device. Each of these interactions involves a different type of peripheral device, each with its own communication requirements, data formats, and timing constraints.

The challenge becomes even more complex when you consider that modern computers might simultaneously manage dozens of different peripheral devices: USB devices, audio interfaces, wireless adapters, sensors, cameras, printers, and countless others. Each device has its own personality - some need constant attention, others work independently for long periods, some transfer massive amounts of data, while others send occasional small signals.

## The Fundamental Problem: CPU Only Understands Memory

Processors are fundamentally designed as memory-centric devices. A CPU's natural language consists of loading data from memory addresses, processing that data, and storing results back to memory locations. It thinks in terms of addresses, data buses, and memory operations.

Peripheral devices, however, don't naturally fit this memory-centric worldview. A keyboard doesn't have a memory address where keypress data magically appears. A graphics card isn't just another chunk of RAM waiting to be read from. A network card can't simply be treated as a memory location that contains incoming internet packets.

This creates a fundamental abstraction gap: how do you make diverse, complex peripheral devices appear as simple memory locations to a processor that only knows how to read and write memory? How do you bridge the gap between a CPU that wants to execute predictable memory operations and peripheral devices that operate with their own timing, their own data formats, and their own operational requirements?

## How CPU and RAM are Connected?

RAM is the only component the CPU must be able to talk to almost directly, because instructions and data for execution live there. In modern processors, the The Integrated Memory Controller (IMC) is built directly into the CPU die itself. The IMC handles all the complex protocols needed to communicate with different types of RAM (DDR4, DDR5, etc.) and manages the timing, voltage, and signaling requirements that RAM modules need.

The logical connection between CPU and RAM comprises of three main "highways" called buses:

### Three Buses Connecting CPU and RAM

#### 1. Address Bus

The address bus is the set of signals used by the CPU to tell the memory controller (and eventually the RAM) which memory location it wants to access. It is a one-way channel that always flows from the CPU to the RAM. For example, if the CPU wants to read or write the data stored at memory location 0x1000, it places that address on the address bus, and the memory hardware decodes it to find the correct physical cell in RAM.

The width of the address bus determines how much memory the CPU can directly address. A 32-bit CPU has a 32-bit wide address bus, meaning it can generate 2^32  unique addresses—equivalent to 4 GB of addressable memory space. In contrast, a 64-bit CPU can theoretically generate 2^64
unique addresses, which is an astronomically large number (16 exabytes), a 32-bit wide address bus literally means 32 separate parallel signal lines (wires or traces on the motherboard), each carrying a binary 0 or 1 at the same time. Together, these 32 signals form one complete address in binary.

#### Data Bus

The data bus is the pathway that carries the actual information being transferred between the CPU and RAM. Unlike the address bus, which is strictly one-way, the data bus is bidirectional: data can flow from the CPU to memory during a write, or from memory back to the CPU during a read. For example, if the CPU is storing a value, the bits of that value are placed on the data bus and sent to RAM; if it is retrieving a value, the RAM places the bits on the data bus and sends them back to the CPU.

The width of the data bus determines how many bits can be transferred in a single operation. An 8-bit data bus can transfer only one byte at a time, whereas a 32-bit data bus can transfer four bytes (4 × 8 bits) at once, and a 64-bit data bus can transfer eight bytes in one operation. A wider bus means more data can be moved per clock cycle, which directly improves memory bandwidth. For this reason, modern processors use data buses that are 64 bits or even wider.

It’s important to note that the data bus width is not always the same as the CPU’s register size. For example, a CPU might support 64-bit registers but still connect to RAM through multiple 64-bit memory channels to increase throughput. This is why modern systems often advertise features like dual-channel or quad-channel memory—they effectively combine multiple 64-bit data buses in parallel, allowing the CPU to transfer larger chunks of data per cycle.

#### Control Bus

The control bus is a set of signals that coordinates and manages the operations between the CPU and memory (and other components). While the address bus specifies where to look in memory and the data bus transfers the actual information, the control bus tells the system what action to perform. It carries control signals such as Read/Write (to indicate whether the CPU wants to read from or write to memory), Clock (to synchronize data transfers), and Enable or Chip Select signals (to activate specific memory modules or devices).

Unlike the address and data buses, which deal with values and information, the control bus deals with timing and intent. For example, when the CPU wants to read from address 0x1000, it places 0x1000 on the address bus, asserts the Read signal on the control bus, and then waits for RAM to place the requested data on the data bus. Similarly, when writing, it asserts the Write signal so the RAM knows to store the incoming data.

The number of control signals is not fixed like the width of the address or data bus; instead, it depends on the processor’s design. Different CPU architectures may use different sets of control lines, but all serve the same purpose: to ensure that the CPU, memory, and peripherals are synchronized and understand what action is taking place.

## How is CPU Connected to Peripheral Components?

The CPU doesn’t talk to most peripherals (disk, keyboard, GPU, NIC, USB, etc.) as “directly” as it does with RAM. Instead, it uses interconnects and buses. Here’s how it works in modern systems:

### 1. CPU ↔ Chipset / Interconnect

- In older PCs, the CPU connected to two chips called northbridge (handled memory and GPU) and southbridge (handled I/O like USB, disk, etc.).
- Today, most of the northbridge has been integrated inside the CPU (e.g., the memory controller and PCIe lanes) [^PCIe].
- What remains is a chipset (Intel calls it PCH – Platform Controller Hub, AMD calls it chipset) that connects slower peripherals.
-  The CPU communicates with the main chipset component through high-speed links. Modern Intel processors use DMI (Direct Media Interface), while AMD uses Infinity Fabric/HyperTransport. These links can transfer multiple gigabytes per second.

### 2. Direct CPU Connections

- RAM → via the memory controller inside the CPU.
- GPU (dedicated graphics card) → via PCI Express lanes coming straight from the CPU.
- NVMe SSDs (high-speed storage) → often connected directly via CPU PCIe lanes too.

### 3. Indirect CPU Connections (through Chipset/PCH)

- SATA drives (HDDs/SSDs), USB devices, Ethernet cards, Wi-Fi, Audio, etc. connect to the chipset.
- The chipset then communicates with the CPU using a special high-speed link.

### 4. The Buses / Protocols

- PCI Express (PCIe): Used for GPUs, NVMe SSDs, high-speed NICs. Point-to-point, high bandwidth.
- SATA / NVMe: Storage devices. SATA goes through the chipset; NVMe often connects directly to CPU via PCIe.
- USB: For external peripherals. Always goes through chipset.
- Ethernet / Wi-Fi: Usually via PCIe lanes from chipset.
- Legacy (still around): I²C, SPI, LPC for low-speed devices like embedded controllers.


## FUnctions of Memory Controller

- Role: Manages all communication between the CPU and RAM.
- Functions:
  - Translates CPU requests (like “read address 0x1000”) into signals RAM understands (row/column selects, CAS/RAS, etc.).
  - Handles addressing: maps CPU’s logical/physical addresses to actual DRAM cells.
  - Controls timing: DRAM is not plug-and-play like registers; the controller ensures signals are sent in the correct order (activate row, access column, refresh cycle).
  - Manages multiple memory channels (dual/quad-channel DDR).
  - Oversees refresh operations required by DRAM to prevent data loss.
- Why inside CPU now? Putting the controller on-die reduces latency and increases memory bandwidth (AMD did it first with Athlon 64 in 2003; Intel followed later with Nehalem in 2008).

## Functions of PCH (Platform Controller Hub, aka Chipset)

- Role: Acts as the hub for all I/O devices that aren’t directly connected to the CPU.
- Functions:
  - Connects slower peripherals: USB ports, SATA drives, audio, networking, legacy I/O.
  - Provides extra PCIe lanes (lower bandwidth than CPU PCIe lanes) for expansion cards.
  - Bridges communication: talks to the CPU over a high-speed link (Intel’s DMI, AMD’s Infinity Fabric).
  - Integrates controllers for:
    - USB (2.0/3.x/4)
    - SATA (HDD/SSD)
    - Networking (Ethernet, Wi-Fi, Bluetooth)
    - Audio
    - Sometimes integrated graphics support (on certain platforms).
  - Manages power states and hardware features (sleep, wake, thermal management).

# Port Mapped and Memory Mapped I/O

Modern CPUs need to communicate not only with RAM but also with various peripheral devices like keyboards, displays, disks, and network cards. Since these devices are not memory in the usual sense, the CPU requires special mechanisms to send commands, read status, and exchange data with them. Two common approaches are used for this interaction: Port-Mapped I/O (PMIO) and Memory-Mapped I/O (MMIO).

## Port Mapped I/O

In PMIO, the CPU and peripherals use a separate address space for I/O, distinct from the normal memory address space. The CPU issues special I/O instructions (IN, OUT on x86) to read from or write to these ports. Each device is assigned one or more I/O port numbers (like addresses, but for devices).

The CPU communicates with these ports using specialized I/O instructions that are distinct from regular memory load and store operations. Instead of using standard MOV instructions that work with memory, the processor uses dedicated I/O instructions like `IN` (input from port) and `OUT` (output to port). 

### Real-World Example: Keyboard Communication

Consider how a CPU communicates with your keyboard using port-mapped I/O. The keyboard controller (which handles keyboard input) might be assigned a small block of port addresses starting at 0x60. Different ports serve different functions:

- **Port 0x60**: Data port - where the actual key press codes appear when you type.
- **Port 0x64**: Status/command port - tells the CPU if new key data is available and accepts configuration commands.
  
**When you press a key on your keyboard, here's what happens:**

- The keyboard sends a scan code (a number representing which key was pressed) to the keyboard controller.
- The controller stores this scan code and signals the CPU that new data is available.
- Your operating system uses an `IN` instruction to read from port `0x60` to get the scan code.
- The system converts this scan code into the actual character (like 'A' or 'Enter') and sends it to your active application.

### Who maintains the mapping of ports to devices?

The CPU does not decide which device gets which port. The mapping is determined by a combination of:
1. Hardware design (chipset + device controller):
    - Standardized by industry bodies (like IBM PC compatibility standards).
    - Each I/O device is wired or configured to “listen” on a certain port address (or a small range).
    - Example: the old IBM PC keyboard controller was hardwired to port `0x60`.
2. Firmware/BIOS/UEFI setup:
    - At boot, the firmware can configure chipset registers to assign port ranges to devices.
    - Example: configuring legacy COM ports (0x3F8 for COM1).
3. Operating System (OS):
    - The OS maintains a table of which device drivers own which ports.
    - When a program issues an I/O instruction, the OS ensures only the correct driver can talk to that port (protected mode prevents random user programs from messing with hardware).

### The Complete Hardware Pathway: Port-Mapped I/O Instruction Execution

Let's trace exactly what happens when your CPU executes an instruction like `IN AL, 0x60` (read a byte from keyboard port `0x60` into the `AL` register). We'll follow every electrical signal and hardware component involved.

#### Step 1: Instruction Fetch and Decode

**CPU Instruction Cache:** The CPU first fetches the `IN AL, 0x60` instruction from memory through its normal memory access pathway. This instruction might be encoded as bytes 0xE4 0x60 in machine code.

**Instruction Decoder:** The CPU's instruction decoder examines these bytes and recognizes this as an I/O input instruction. Critically, the decoder sets internal control signals differently than it would for a memory operation - it prepares the CPU for an I/O cycle rather than a memory cycle.

#### Step 2: I/O Address Generation and Control Signal Preparation

**Address Calculation:** The CPU loads the port address (0x60) into its address generation unit. However, unlike memory operations, this address will be driven onto the address bus with special I/O control signals.

**Control Signal Generation:** Here's where port-mapped I/O shows its distinct nature. The CPU generates several critical control signals:
 - **IO/M# signal:** Set to indicate this is an I/O operation, not a memory operation (this is a dedicated pin on the CPU).
 - **Read/Write signal:** Set to indicate this is a read operation.
 - **Address Enable Strobe (ADS#):** Indicates when the address is valid on the bus.
 - **Bus cycle definition signals:** Tell the system what type of bus cycle is starting

#### Step 3: Bus Cycle Initiation

**Address Bus:** The CPU drives the port address (0x60) onto the address bus, but with the IO/M# signal asserted to indicate this is I/O addressing, not memory addressing.

**Control Bus Signals:** The control bus carries the I/O-specific signals generated in step 2. These signals are electrically different from memory operation signals - the chipset will examine these control lines to determine how to handle this bus cycle.

**Bus Arbitration:** If other devices are using the bus, the CPU's bus arbitration logic ensures it gains control before proceeding. This might involve waiting for other bus masters to complete their operations.

#### Step 4: Chipset Recognition and Routing

**Platform Controller Hub (PCH) Detection:** The chipset examines the control bus signals and recognizes this as an I/O operation by checking the IO/M# signal state. This is the critical moment where the hardware decides this request won't go to memory.

**Address Decoding:** The PCH's address decoder examines the port address (0x60) and determines which internal controller should handle this request. Port 0x60 is typically decoded as belonging to the keyboard controller (also called the 8042 controller in x86 systems).

**I/O Address Space Mapping:** The chipset consults its internal I/O address mapping table to route the request. Unlike memory addresses that go to the memory controller, I/O addresses are routed to specific peripheral controllers based on predetermined address ranges.

#### Step 6: Data Retrieval and Processing

**Buffer Access:** If keyboard data is available, the controller accesses its internal data buffer where the most recent key press scan code is stored. This buffer is internal to the keyboard controller, completely separate from system memory.

**Data Preparation:** The controller prepares the data for transmission back to the CPU. This might involve format conversion, error checking, or clearing internal status flags to indicate the data has been read.

**Controller Status Update:** The keyboard controller updates its internal status registers to reflect that the data has been read and the buffer is now empty (if this was the last byte available).

#### Step 7: Data Return Path

**Data Bus Drive:** The keyboard controller drives the scan code data onto the data bus. Unlike memory operations where the memory controller drives the data bus, here it's the peripheral controller providing the data.

**Bus Control Coordination:** The chipset coordinates the timing of this data transfer, ensuring that the data is stable on the bus when the CPU expects to read it. This involves precise timing coordination between multiple hardware components.

**Ready Signal Generation:** The controller generates a "data ready" signal back to the CPU, indicating that valid data is now available on the data bus. This signal travels back through the chipset to the CPU.

#### Step 8: CPU Data Reception and Completion

**Data Latch:** The CPU's input buffers latch the data from the data bus when the ready signal is received. The timing of this latch operation is critical - it must happen when the data is stable and valid.

**Register Update:** The CPU moves the received data (the keyboard scan code) into the specified destination register (AL in our example). This completes the data transfer portion of the operation.

**Status Flag Updates:** The CPU may update internal status flags to indicate the success or failure of the I/O operation. Some processors provide flags that software can check to verify that I/O operations completed successfully.

**Bus Cycle Termination:** The CPU terminates the I/O bus cycle by deasserting control signals, freeing the bus for other operations. This involves clearing the IO/M# signal, address enable signals, and other control lines.


## Memory Mapped I/O

If port-mapped I/O creates a separate communication channel for peripherals, memory-mapped I/O takes the opposite approach: make peripheral devices appear as if they're just another part of system memory. Rather than forcing the CPU to learn a new way of communicating, memory-mapped I/O extends the familiar memory addressing model to encompass all peripheral communication. The result is an elegant solution where a single set of instructions - the same load and store operations used for regular memory access - can handle both memory operations and peripheral control. This creates a unified addressing model where there's no fundamental difference between accessing data in RAM and communicating with a graphics card, network interface, or audio controller.

In memory-mapped I/O systems, the system's memory address space is divided between actual RAM and peripheral device registers. For example, in a system with 4GB of address space, you might find:

- 0x00000000 - 0xBFFFFFFF: System RAM (3GB)
- 0xC0000000 - 0xEFFFFFFF: Graphics card memory and registers
- 0xF0000000 - 0xF0FFFFFF: Network card registers
- 0xF1000000 - 0xF1FFFFFF: Audio controller registers
- 0xF2000000 - 0xFFFFFFFF: Other peripheral devices

When the CPU executes an instruction like `MOV EAX, [0xF0000000]`, the memory management hardware examines the address and recognizes that 0xF0000000 falls within the network card's assigned range. Instead of sending this request to the memory controller and RAM, the system routes it to the network controller. The network controller responds as if it were a memory location, providing data back to the CPU through the same pathways used for regular memory access.

### Why Allocate a Range of Addresses?

In memory-mapped I/O (MMIO), a device usually gets a range of memory addresses, not just one, and here’s why:

1. Devices have multiple registers / control points
    - A device is rarely controlled with a single bit or byte.
    - Example: A disk controller might need:
      - Status register (ready/busy, error flags)
      - Command register (read/write/start/stop instructions)
      - Data register (where you actually read/write data words)
      - Configuration registers (mode, DMA settings, etc.)
    - Each of these needs its own distinct address.
2. Some devices expose internal memory or buffers
    - Example: A video card might map its framebuffer (VRAM) directly into the CPU’s address space.
    - The CPU then just writes to that range as if it were RAM, but it’s actually updating pixels in the GPU.
    - This can require megabytes of address space, not just a few bytes.
3. Future extensibility
    - Even if today only 4 registers are used, the designers might reserve a whole block (e.g., 4 KB) so they can add new registers/features without redesigning the memory map.

### Who decides which device gets what range of address range?

#### 1. Who decides the address ranges?

- CPU does not “magically know” what device is at what address.
- It’s the system designer / hardware vendor / platform firmware (BIOS/UEFI, device tree, ACPI tables, or chipset designers) who decide which ranges of physical memory are reserved for which devices.
- Example:
  - 0x3F8–0x3FF reserved for the UART (serial port).
  - 0xF0000000–0xF0FFFFFF reserved for GPU registers.
  - 0xC0000000–0xCFFFFFFF for PCI devices’ MMIO regions.

#### 2. How does the CPU know a given address is I/O vs RAM?

At the electrical level:
 - CPU just puts the physical address on the address bus.
 - The memory controller & chipset (or interconnect like PCIe) decide where the request goes.
 - If address ∈ DRAM range → routed to RAM.
 - If address ∈ reserved I/O range → routed to that device’s bus.
So the CPU doesn’t need to “know” in the instruction itself — the system’s address map handles it.

#### 3. Who tells the driver what address range belongs to a device?

- Old systems: fixed by convention (e.g., COM1 = 0x3F8).
- Modern systems (PCI/PCIe, SoCs):
  - During boot, firmware (BIOS/UEFI/Device Tree/ACPI) enumerates devices.
  - Each device advertises how much MMIO space it needs.
  - The system allocates a physical address range to it and tells the OS.
  - OS maps that range into the driver’s virtual memory space.
  - The driver then uses these addresses knowing the register layout.

# Interrupts

So far, we looked at how the CPU can initiate communication with peripheral devices. But devices also need a way to notify the CPU when they have something important to share. For example, when you press a key or click the mouse, the CPU must respond immediately instead of waiting for the next scheduled check. This is where interrupts come in — a mechanism that lets devices signal the CPU to temporarily pause its current work, handle the event, and then continue from where it left off.

## History

Early computers like ENIAC (1945) could only do one job at a time, start to finish. No multitasking, no real-time response. You'd submit your job on punch cards and come back hours later for results. Believe it or not, humans were often the "interrupt system"! Operators would manually intervene when something needed attention - physically stopping the machine, changing tapes, or handling errors. The concept emerged in the mid-1950s during the transition from first to second-generation computers.

**Key pioneers:**

- **IBM System/360 team (mid-1960s)** - First widely successful interrupt system
- **Manchester Mark 1 (early 1950s)** - Had primitive interrupt-like mechanisms
- **UNIVAC 1103 (1953)** - Early implementation of interrupt concepts

Before interrupts became standard, many computers relied on polling (also called programmed I/O). In this model, the CPU repeatedly checked device status registers in a loop to see if input/output was ready.
- **UNIVAC I (1951)** – used programmed I/O; the CPU wasted cycles constantly checking peripherals like tape drives and printers.
- **IBM 701 (1952)** – also relied on polling for I/O operations.
- This approach was simple but inefficient: the CPU spent much of its time waiting rather than doing useful work.

## The Basic Idea

At the most basic level, an interrupt is just an electrical signal - a voltage change on a wire. But the magic is in how the CPU is designed to detect and respond to these signals.

### The Basic Hardware Setup

Picture a simple computer with these components:

```
[CPU] ←── interrupt wire ←── [Keyboard Controller]
  ↑
  └── interrupt wire ←── [Timer Chip]  
  └── interrupt wire ←── [Disk Controller]
```

Each device that wants to interrupt the CPU has a dedicated wire (called an **IRQ line** - Interrupt Request line) connected to the CPU.

### What Happens Inside the CPU: The Interrupt Cycle

The CPU has a built-in process that runs constantly, called the **fetch-decode-execute cycle**:

**Normal operation:**
**1. Fetch:** Get the next instruction from memory.
**2. Decode:** Figure out what the instruction means.
**3. Execute:** Perform the operation.
**4. Repeat:** Go back to step 1.

**With interrupt checking added:**

- Fetch: Get the next instruction from memory.
- Decode: Figure out what the instruction means.
- Execute: Perform the operation.
- 🔍 CHECK FOR INTERRUPTS: New step!
- Repeat: Go back to step 1.

### The Interrupt Detection Circuit

Inside the CPU, there's dedicated hardware that monitors the interrupt lines:

```
Interrupt Lines (IRQs) → [Interrupt Controller] → [CPU Core]
     IRQ0 (Timer)              ↓
     IRQ1 (Keyboard)      Priority Logic
     IRQ2 (Mouse)              ↓
     IRQ3 (Serial)        Interrupt Flag
```

**The Interrupt Controller** (like the 8259 PIC in early PCs) does several jobs:
- **Listens:** Constantly monitors all IRQ lines for voltage changes.
- **Prioritizes:** Decides which interrupt is most important if multiple arrive.
- **Signals:** Sets an "interrupt pending" flag that the CPU checks.

### The Moment of Interruption

Here's what happens in the nanoseconds when you press a key:

**Step 1: The Signal**

- Keyboard detects keypress.
- Keyboard controller sends electrical pulse down IRQ1 wire.
- This changes voltage from 0V to +5V (or similar).

**Step 2: Hardware Detection**

Interrupt controller detects voltage change on IRQ1.
Controller determines this is highest priority pending interrupt.
Controller asserts the main "INTR" (interrupt) line to CPU.

**Step 3: CPU Response**

- CPU finishes current instruction (atomic operation)
- CPU checks interrupt flag - finds it's set!
- CPU enters "interrupt acknowledgment" cycle

### The Interrupt Acknowledgment Cycle

```
1. CPU → Interrupt Controller: "I see your interrupt, which one is it?"
2. Controller → CPU: "It's interrupt number 1 (keyboard)"
3. CPU: "Got it, I'll handle interrupt 1"
```

This happens via special electrical signals on the bus - the CPU literally asks "what interrupt number?" and gets a response.

### The Vector Table: Hardware-Software Bridge

Now the CPU needs to know what code to run for this interrupt. This is where hardware meets software:

**The Interrupt Vector Table** is a special area in memory (usually at a fixed location) that contains addresses:

```
Memory Address | Contents (Address of handler)
0x0000        | Timer interrupt handler address
0x0004        | Keyboard interrupt handler address  
0x0008        | Mouse interrupt handler address
0x000C        | Serial port interrupt handler address
```

### What Happens After the Vector Lookup?

Once the CPU fetches the handler address from the interrupt vector table, it needs to actually run the code for that interrupt. This involves several precise steps to ensure the CPU can pause its current work, handle the interrupt, and then resume smoothly:

#### 1. Save CPU State

- The CPU automatically pushes critical information onto the stack:
  - Current Program Counter (instruction address)
  - Flags (status register)
  - Some or all general-purpose registers (depending on architecture)
- This ensures the CPU can later return to the exact point where it was interrupted.

#### 2. Jump to Interrupt Handler

Using the address retrieved from the vector table, the CPU transfers control to the appropriate Interrupt Service Routine (ISR).

#### 3. Interrupt Service Routine (ISR) Executes

- The ISR is usually part of the device driver code in the OS kernel.
- It performs the necessary work, such as reading the key code from the keyboard controller, acknowledging the interrupt, or queuing data for higher-level processing.

#### 4. Restore CPU State

- Once the ISR finishes, it executes a special return-from-interrupt instruction (e.g., IRET on x86).
- This pops the saved program counter, flags, and registers back from the stack.

#### 5. Resume Normal Execution

The CPU continues running the interrupted program as if nothing happened, with full context restored.


## Evolution of Interrupts

### 8086: The Foundation (1978)

The Intel 8086 established the basic interrupt architecture that influences CPUs to this day:

**Hardware Setup:**

```
[8086 CPU] ←── INTR pin ←── [8259 PIC] ←── 8 IRQ lines
                                ↑
                               IRQ0: Timer
                               IRQ1: Keyboard  
                               IRQ2: Cascade (for 2nd PIC)
                               IRQ3-7: Various devices
```

#### Key Characteristics:

- **256 interrupt vectors (0-255)**, each 4 bytes long
- **Interrupt Vector Table** at fixed location (0x0000-0x03FF)
- **Single 8259 PIC** could handle only 8 devices [^PIC]
- **No privilege levels** - any code could modify interrupt table
- **Simple priority**: Lower IRQ numbers had higher priority

#### The Interrupt Process:

- Device asserts IRQ line to 8259 PIC
- PIC sends interrupt signal to CPU's INTR pin [^INTR_Pin]
- CPU finishes current instruction
- CPU sends interrupt acknowledge (INTA) back to PIC
- PIC responds with interrupt vector number (0-255)
- CPU automatically: pushes flags, pushes return address, jumps to handler

#### Types of Hardware Interrupts

- **Maskable (via INTR pin):** controlled by IF flag.
- **Non-maskable (via NMI pin):** higher priority, cannot be disabled. Typically used for hardware errors (e.g., memory parity errors).

#### Software interrupts:

Triggered by the `INT n` instruction. Widely used by DOS and BIOS (e.g., `INT 10h` for video, `INT 21h` for DOS services).

#### Hardware vs Software Interrupts

- **Source**
  - Hardware interrupts come from external devices (keyboard, timer, disk, etc.) through CPU pins (INTR, NMI).
  - Software interrupts are triggered by program instructions (INT n).
- **Purpose**
  - Hardware interrupts let devices grab CPU attention asynchronously, even if the CPU is busy.
  - Software interrupts act like a function call into the OS/BIOS, providing services without dealing with raw hardware.
- **Control**
  - Maskable hardware interrupts can be enabled/disabled by the CPU (IF flag).
  - Non-maskable hardware interrupts always get through (used for critical errors).
  - Software interrupts are always executed when the program issues them.
- **Use in 8086 era**
  - Hardware interrupts: handled events like timer ticks (IRQ0), key presses (IRQ1).
  - Software interrupts: provided system calls, e.g., INT 10h (screen output), INT 13h (disk), INT 21h (DOS services).

#### Why did 8086 use Software Interrupts to Communicate with Peripheral Devices Even though Port Mapped I/O was available?

**Why Software Interrupts were used for peripheral services:**

The 8086 could talk to devices directly using port-mapped I/O (IN/OUT instructions), but software interrupts were used on top of that for several reasons:

- **Abstraction / Convenience:** Writing INT 21h is much easier than remembering all the port numbers and bit meanings for every device. DOS/BIOS hid the hardware details.
- **Standardization:** Different PCs (and peripherals) might have slightly different I/O mappings. But calling INT 10h (video service) or INT 13h (disk service) gave you a uniform API, regardless of the hardware.
- **Flexibility:** A software interrupt just jumps into a predefined handler routine (in BIOS or DOS). That routine can itself use port-mapped I/O under the hood. If hardware changes, only the handler changes, not every user program.
- **Privilege / Safety:** In real mode there wasn’t much privilege enforcement, but still—BIOS/DOS routines ensured users didn’t directly poke at critical ports incorrectly.
- **Bootstrapping:** Early in boot, before an OS is loaded, you still need keyboard, display, and disk I/O. The BIOS provides these services through software interrupts, so your bootloader/OS can rely on them without writing device drivers immediately.

#### Security Concern in Interrupt Vector Table (IVT)

On the 8086:
- The Interrupt Vector Table (IVT) lived at a fixed physical address range in memory: 0x0000–0x03FF.
- Each entry was just 4 bytes (2 for segment, 2 for offset), so any code running in real mode could write directly to those memory locations.
- There was no concept of privilege levels (rings) or memory protection — all programs had the same rights as the OS.
- That meant:
  - A buggy program could overwrite vectors (crash system).
  - A malicious program could hook vectors (e.g., replace INT 21h DOS services) to intercept file access, keystrokes, etc.
  - In fact, this is exactly how many DOS viruses worked — they installed themselves by modifying the vector table.

### 80286: Protected Mode Revolution (1982)

The Intel 80286 (286) marked a turning point in CPU architecture, introducing protected mode. This directly impacted how interrupts worked by addressing the security and flexibility limitations of the 8086.

Key Advancements in 80386:

#### Interrupt Descriptor Table (IDT):

- Replaced the fixed IVT of the 8086.
- Could be placed anywhere in memory (its base and limit stored in the IDTR register).
- Each entry (descriptor) was now 8 bytes, holding more info than just an address.

#### Privilege Levels (Rings 0–3):

- Allowed separation of kernel (Ring 0) and user programs (Ring 3).
- Interrupts could only call handlers at the same or more privileged levels.
- Prevented user programs from hijacking system interrupts.

#### Interrupt Gates / Trap Gates:

- Introduced different types of interrupt descriptors:
  - **Interrupt Gate:** disables further interrupts while handling.
  - **Trap Gate:** leaves interrupts enabled, useful for exceptions/debugging.

#### More Vectors:

- Still 256 interrupt vectors, but the descriptors were richer (segment selectors, privilege info).

#### Exception Handling:

- CPU introduced dedicated exception interrupts (like divide-by-zero, invalid opcode, segment fault).
- These weren’t tied to external devices — they came from within the CPU itself.

#### The Interrupt Process (80286 Protected Mode)

1. Device raises IRQ → PIC → INTR pin (same as 8086).
2. CPU acknowledges and gets vector number.
3. CPU looks up the vector in the IDT (not fixed memory).
4. Hardware checks descriptor: type of gate, privilege level, target code segment.
5. If privilege checks pass: CPU pushes state, switches stack if needed (to kernel stack), jumps to handler.
6. Handler runs safely at Ring 0.
7. IRET restores full state and privilege level, resuming program.

#### Why It Was Revolutionary

- **Security:** User programs could no longer overwrite interrupt entries — only the OS (ring 0) could.
- **Flexibility:** IDT could be relocated anywhere, making memory management easier.
- **Stability:** Built-in exception interrupts caught common bugs (e.g., division by zero crash
- **Foundation:** Established the basic interrupt model still used today in x86 (with refinements in 386 and beyond).

### 80386: Virtual Memory and Exceptions (1985)

The Intel 80386 took the protected mode ideas of the 80286 and extended them into a 32-bit architecture with much richer interrupt handling. This CPU made interrupts not just a hardware feature, but a core part of operating system design.

#### Key Advancements

##### 1. 32-bit Protected Mode

- Interrupt Descriptor Table (IDT) entries expanded to support full 32-bit offsets.
- Handlers could be located anywhere in the 4 GB address space.

##### 2. Exceptions Added

- New interrupt types defined for CPU-detected faults:
  - **#PF (Page Fault, vector 14):** triggered when memory access violates paging rules.
  - **#GP (General Protection Fault):** illegal access across privilege levels.
  - **#DE (Divide Error):** divide by zero or overflow.
- Gave the OS a way to handle memory protection and recovery gracefully.

##### 3. Privilege Levels (Rings 0–3)

- Interrupts could only enter more privileged rings (e.g., user → kernel).
- Prevented user programs from hijacking kernel-level interrupt handlers.

##### 4. Task Gates and TSS (Task State Segment)

- The 80386 supported hardware-based task switching.
- An interrupt could automatically switch to another task using a TSS descriptor.
- In practice, OSes avoided this (too slow), but it showed Intel’s push to make multitasking easier.

#### Interrupt Handling Flow (80386 Protected Mode)

1. Interrupt occurs (device IRQ, CPU exception, or software INT n).
2. CPU looks up IDT entry for the interrupt vector.
  - IDT can now reside anywhere in linear memory (pointed to by IDTR).
3. Privilege checks are enforced:
  - User-space cannot directly install or jump to kernel-level handlers.
  - Interrupts automatically switch to a kernel stack if needed.
4. State saving: CPU pushes EFLAGS, CS:EIP, and possibly an error code (for faults).
5. Jump to handler: CPU transfers control to the handler address in IDT.

#### Why It Mattered?

- **Paging + Page Faults:** Interrupts became the backbone of virtual memory. Every time a program accessed memory not in RAM, the CPU raised a page fault, letting the OS load data from disk.
- **True Multitasking:** Interrupts and exceptions combined with privilege levels enabled safe, preemptive multitasking.
- **System Call Refinement:** Software interrupts (INT 0x80 in Unix-like systems) became the standard way to enter the kernel from user space.

### Pentium Era

#### APICs

- The old 8259 PIC design (used since 8086/286 PCs) was fine for single-CPU systems.
- But with Pentium (and Pentium Pro), multiprocessor systems became common.
- Needed:
  - More interrupt lines (beyond 16 of the PIC).
  - Smarter interrupt routing to multiple CPUs.
  - Support for inter-processor interrupts (IPI).

##### Local APIC (LAPIC)

- Each CPU core got its own Local APIC unit.
- Functions:
  - Receives interrupts and delivers them to its CPU.
  - Priority management (masking, nesting, vector priorities).
  - Timer (each LAPIC had its own timer, often used by OS).
  - Accepts Inter-Processor Interrupts (IPIs) → CPUs can signal each other (e.g., “reschedule,” “TLB shootdown”).

##### I/O APIC

- A separate chip, replacing the old 8259 PIC.
- Connects external interrupt sources (like devices, PCI slots, NICs) to the system.
- Supports:
  - More than 16 interrupt lines (scalable, often 24, 64, or more).
  - Redirection table: an interrupt can be routed to any CPU’s LAPIC, not just CPU0.
  - Level-triggered interrupts (important for PCI devices).

```
[CPU 0] ←── Local APIC ←──┐
[CPU 1] ←── Local APIC ←──┼── System Bus ←── I/O APIC ←── Devices
[CPU 2] ←── Local APIC ←──┘
[CPU 3] ←── Local APIC ←──┘
```

##### Advanced Features

- **Interrupt Redirection:** Instead of all interrupts hitting the “bootstrap CPU,” the OS can balance them across multiple CPUs.
- **Inter-Processor Interrupts (IPI):** CPUs can generate interrupts to each other via the APIC bus. Crucial for multiprocessing OS (Linux, Windows NT, BSD).
- **Priority & Vectoring:** Each LAPIC has its own task-priority register; APIC ensures higher-priority interrupts are handled first.

##### OS Impact

- Required new OS support: Windows NT, Linux, Solaris adapted for APICs.
- Allowed true **SMP (Symmetric Multi-Processing)**, with multiple CPUs handling interrupts and scheduling work.
- Old DOS/Win9x mostly ignored APIC, stayed in 8259 compatibility mode.

#### Advanced Exception Handling – Precise Exceptions

- Pentium introduced precise exceptions, meaning:
  - When an exception (e.g., divide-by-zero, page fault) occurs, the CPU guarantees that all instructions before the faulting instruction have completed, and no later instructions have modified state.
  - This property is called the “precise exception model.”
- Why it mattered:
  - Pentium had pipelines and early forms of out-of-order execution. Without precise exceptions, the CPU could trigger a page fault after executing later instructions, leaving machine state inconsistent.
  - With precise exceptions, the OS/debugger sees a clean, restartable point.
  - Essential for:
    - Reliable OS scheduling.
    - Virtual memory (page faults).
    - Debugging/traps (single step, breakpoints).


#### Impact on OS & Software

- OS could now depend on restartable faults → page fault handler could resume the instruction safely.
- Debuggers became more powerful — they could trap and restart instructions deterministically.
- Hardware exceptions became a core mechanism for system calls, copy-on-write, lazy allocation.


### x86-64 Era (2003, AMD Opteron/Athlon64)

#### Syscall / Sysret vs. INT Instruction

- Software interrupts (INT n) became too slow for frequent system calls.
- AMD introduced SYSCALL / SYSRET instructions (fast, direct transition between user and kernel mode).
  - Avoids IDT lookup overhead.
  - Uses MSRs (Model-Specific Registers) to store kernel entry points.
- Intel later copied this with SYSENTER / SYSEXIT, then adopted AMD’s SYSCALL/SYSRET for 64-bit mode.
- This split the world:
  - Hardware/Device interrupts → IDT/ISR.
  - System calls → SYSCALL (fast path).

[^PCIe]: Peripheral Component Interconnect Express, is a high-speed interface standard used to connect various components within a computer, such as graphics cards, SSDs, and network adapters, to the motherboard. It uses a point-to-point connection with dedicated data lanes (e.g., x1, x16) to provide high bandwidth and low-latency communication, replacing older bus-based standards like PCI.


[^PIC]: On the 8086 (and many early x86 systems), the CPU itself could recognize an interrupt request (through the INTR pin), but it had no built-in logic to handle multiple devices, prioritize them, or decide which device’s interrupt to service first. That’s where the 8259 PIC (Intel 8259A) came in.

[^INTR_Pin]: On the 8086 CPU, the INTR pin (Interrupt Request) is the main hardware input line for maskable interrupts.. It’s a single physical pin on the 8086 package. Used by external devices (via the 8259 PIC) to request the CPU’s attention. "Maskable" means the CPU can ignore (mask) requests on this pin if interrupts are disabled (via the IF flag in the FLAGS register).