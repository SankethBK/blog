---
title: "The Page Tables"
date: 2026-07-02
categories: ["operating systems", "linux"]
tags: ["4 level page tables", "tlb"]
---

## Modern Linux Page Tables (4-Level Architecture)

Modern 64-bit processors require much larger address spaces, and the Linux kernel adapted by shifting to a **4-level** (and more recently, a 5-level) page table architecture.

**The Core Concept:** Because a 64-bit address space is astronomically large and mostly empty, the kernel cannot use a single, massive translation array. Instead, it uses a hierarchical, multi-level tree of tables to map Virtual Addresses to Physical Addresses efficiently.

### 1. The 4 Levels of Translation

To support 64-bit architectures (like x86_64 and ARM64), Linux introduced the **PUD** (Page Upper Directory) to the hierarchy.

| Level | Name | Description |
| --- | --- | --- |
| **1 (Top)** | **PGD** (Page Global Directory) | The highest level. The process's `mm_struct` points here. On a context switch, the physical address of the PGD is loaded directly into a CPU hardware register (e.g., the `CR3` register on x86). |
| **2** | **PUD** (Page Upper Directory) | **The modern addition.** Entries in the PGD point to an array of PUDs. |
| **3** | **PMD** (Page Middle Directory) | Entries in the PUD point to an array of PMDs. |
| **4 (Bottom)** | **PTE** (Page Table Entry) | The final table. Entries here point directly to the base address of the physical page (Page Frame) in RAM. |


### 2. How the Virtual Address is Split (The x86_64 Example)

When a processor looks at a 64-bit virtual address, it doesn't see a single number. It sees a bitfield.

While pointers are 64 bits long, modern hardware typically only uses **48 bits** for actual memory addressing (the rest are reserved/unused). The kernel slices those 48 bits into chunks to navigate the tables:

* **Bits 39–47 (9 bits):** Index into the **PGD**
* **Bits 30–38 (9 bits):** Index into the **PUD**
* **Bits 21–29 (9 bits):** Index into the **PMD**
* **Bits 12–20 (9 bits):** Index into the **PTE**
* **Bits 0–11 (12 bits):** **Page Offset**. Once the physical page is found, these 12 bits point to the exact byte inside that standard 4KB page.

> **The Software Fallback:** Linux uses this 4-level structure in its C code universally. If the kernel is compiled for an older 32-bit hardware architecture that only supports 2 or 3 levels, the kernel compiler intelligently "folds" (bypasses) the unused directories (like the PUD) at compile time to keep the hardware happy without changing the core kernel source code.

### 3. Hardware Acceleration: The MMU and TLB

Because every single memory request requires translation, walking this 4-level tree in software for every operation would destroy system performance.

* **The MMU (Memory Management Unit):** The hardware component on the CPU that actually performs the physical page table walk. The kernel just sets up the tables in RAM; the MMU traverses them.
* **The TLB (Translation Lookaside Buffer):** An ultra-fast hardware cache located directly on the CPU die. It stores recent Virtual-to-Physical PTE translations.
* **TLB Hit:** The CPU skips the page tables entirely and accesses RAM instantly.
* **TLB Miss:** The hardware MMU must perform the expensive 4-level "page walk" through RAM to find the mapping, cache it in the TLB, and then fetch the data.


### 4. Beyond 4 Levels: The 5-Level Reality (P4D)

As enterprise servers surpassed terabytes of RAM, the 48-bit addressing limit (which caps out at 256 TB of virtual memory) became a bottleneck.

Starting in kernel 4.14 (late 2017), Linux merged support for **5-Level Paging**.

* **The P4D (Page 4th Directory)** was inserted between the PGD and the PUD.
* This expands the usable address space from 48 bits to **57 bits**, raising the maximum virtual memory space from 256 Terabytes to 128 Petabytes.

## How much Memory is Addressable by 4 Level Page Tables?

We saw that only 48 bits are used for addressing. So the overall addressable memory should be `2^48 = 256 TB`/ Let's verify if we're still able to address the same amount of memory with 4 level paging. 

1. A process will own exactly one page in PGD. If we consider the page size to be 4 KB and each entry will be 8 bytes (since it points to an address on another table, addresses are 8 bytes), it can hold `4096 / 64 (2^12 / 2^3 = 2^9)`, `2^9 = 512`. It means PGD can hold 512 entries. It adds up with the math that 9 bits are dedicated for a PGD entry. 

2. Each entry of PGD will fanout to 512 entries of PUD. An entry of PUD is 8 bytes long and contains 512 entries in a page. The PGD entry holds the physical address of the page of PUD and offset into that page is obtained by the offset (bits 30-38 of virtual address). 

3. Similarly each entry of PUD will fanout to 512 entries of PMD and index into PMD is obtained by bits 21-29 from virtual address. 

4. Each entry of PMD will fanout to 512 entries of PTEs.

5. Each entry of PTE will fanout to 512 entries of actual page table entries containing 

6. Bits 0-11 represent the offset. So the memory addressable by an offset is `2^12 = 4 KB`. 

Let's multiply the maximum capacity all the way up through the 4-level tree for a standard x86_64 architecture:

- 1 PTE entry points to a 4 KB physical page.
- 1 PMD table holds 512 PTEs -> 512 x 4 KB = 2 MB.
- 1 PUD table holds 512 PMDs -> 512 x 2 MB = 1 GB.
- 1 PGD entry points to a PUD table -> 1 GB x 512 = 512 GB

Since a single 4KB PGD page holds 512 of these entries, the total addressable virtual memory space for your process is:

- 512 x 512 GB = 262,144 GB (or 256 Terabytes)

### What does bits 48-64 bits represent in Virtual Address?

We saw the usages of bits 0 - 47 in virtual addresses. But VA's are actually 64 bits, so what does rest of the bits represent?

**The original problem**

A CPU has 64-bit registers. So in theory, pointers could range from `0x0000000000000000` to `0xFFFFFFFFFFFFFFFF` which is `2^64 bytes` or 16 Exabytes of virtual address space. That’s enormous.

Building page tables for 64 address bits would require another page-table level (or several), larger TLB tags, more transistors, etc.

When AMD designed x86-64 around 2000, they thought: “Nobody needs 16 exabytes of virtual memory today.”. So they chose 48 useful bits. Meaning only bits 0-47 participate in translation.

**Then what about bits 48-63?**

They could have simply said “Ignore them.” But that would create a disaster.

Suppose these two pointers:

```
0x0000123456789ABC

0xFFFF123456789ABC
```

If the upper bits were ignored… Both would translate to exactly the same address. Very dangerous.

**So AMD invented canonical addresses**

Instead they said: The upper bits must be sign extensions of bit 47.

Meaning:

```
bit47 = 0
↓
0000000000000000xxxxxxxxxxxxxxxx
```

or

```
bit47 = 1

↓

1111111111111111xxxxxxxxxxxxxxxx
```

Nothing else allowed.

So the address space becomes

```
0x0000000000000000
          │
          │
          │
0x00007FFFFFFFFFFF
```

This creates two valid canonical regions (lower and upper halves) separated by a massive invalid gap. Of the `2^16` possible values for bits 48–63, only two are legal: all zeros or all ones

Linux chooses to map:

- **Userspace** into the **lower canonical half** of the virtual address space
  (`0x0000...` → `0x00007fffffffffff`)

- **Kernel space** into the **upper canonical half**
  (`0xffff8000...` → `0xffffffffffffffff`)

```
+---------------------------+
| User space                |
| 0x0000....                |
+---------------------------+

xxxxxxxxxxxxxxxxxxxxxxxxxxxx
Huge INVALID GAP
xxxxxxxxxxxxxxxxxxxxxxxxxxxx

+---------------------------+
| Kernel space              |
| 0xffff....                |
+---------------------------+
```

Why?

Several reasons:

- User pointers tend to start near zero (malloc, code, heap).
- Kernel addresses all start with `0xffff...`, making them instantly recognizable in logs, crash dumps, and debuggers.
- The kernel can reserve the entire upper half for itself without worrying about user mappings.

So numerically, userspace is at the bottom and kernel space is at the top.

That’s what Linux documentation means when it says: “Kernel lives in the upper half of the address space.”

**Future Proofing**

Now imagine Intel comes along years later and says: “We now support 57 address bits.” Nothing changes conceptually. Now instead of bit 47 we use bit 56. Everything above bit56 copies bit56. The hole becomes much smaller.

## The Address Translation Process

### The Anchor: The CR3 Register

Before the CPU can start translating, it needs to know where the very first table lives in physical RAM.

When a process is scheduled to run on the CPU, the Linux kernel takes the physical address of that process's top-level directory (the PGD) and loads it directly into a special hardware register on the CPU called **`CR3`**.

The MMU now has its starting point.

### The 4-Level Hardware Walk

Assuming the TLB cache missed, the hardware MMU performs the translation entirely on its own by walking down the four tables.

**Level 1: PGD (Page Global Directory)**

1. The MMU goes to the physical address held in the `CR3` register. This points to the base of the PGD.
2. The MMU looks at **Bits 39–47** of your virtual address to get an index (a number between 0 and 511).
3. It jumps to that entry in the PGD.
4. That entry contains the physical base address of the next table: the PUD.

**Level 2: PUD (Page Upper Directory)**

1. The MMU goes to the physical base address of the PUD.
2. It looks at **Bits 30–38** of your virtual address to get the next index.
3. It jumps to that entry in the PUD.
4. That entry contains the physical base address of the next table: the PMD.

**Level 3: PMD (Page Middle Directory)**

1. The MMU goes to the physical base address of the PMD.
2. It looks at **Bits 21–29** of your virtual address to get the next index.
3. It jumps to that entry in the PMD.
4. That entry contains the physical base address of the final table: the PTE.

**Level 4: PTE (Page Table Entry)**

1. The MMU goes to the physical base address of the PTE.
2. It looks at **Bits 12–20** of your virtual address to get the final index.
3. It jumps to that entry.
4. **Bingo.** This entry does *not* point to another table. It points to the actual, physical base address of the 4KB **Page Frame** in your system's RAM.

### The Final Step: The Offset

The MMU has found the correct 4KB page of physical memory. But you didn't ask for a whole 4KB page; your code asked for a specific variable or instruction inside that page.

1. The MMU takes the physical base address it just found in the PTE.
2. It looks at the remaining **Bits 0–11 (12 bits)** of your virtual address.
3. 2^12 = 4096. These 12 bits represent the exact byte offset inside the 4KB page.
4. The MMU adds the offset to the base physical address.
5. The memory is successfully fetched and handed to the CPU.

## Contents of Page Table Entries

### Contents of Hierarchical Tables

The entries in the PGD, PUD, PMD, and PTE all hold strictly Physical Addresses (PA). The `CR3` register also holds the Physical Address of the PGD.

Otherwise it would lead to endless recursion when MMU tries to walk the page tables

You would enter an infinite loop:

- MMU: "I need to read the PUD at virtual address X."
- MMU: "To translate X, I need to check the PGD."
- MMU: "The PGD says the PUD is at virtual address X..."

The hardware MMU is the entity doing the page walk, and it is trying to solve a translation problem.

If the `CR3` register or the PGD held a Virtual Address (VA) for the next table, the MMU would have to translate that VA to find the physical RAM chip location. But how does it translate a VA? By looking at the PGD!

To break the loop, the hardware must completely bypass the translation mechanism during the page walk. When the MMU reads an entry in the PGD, it takes that 64-bit value, strips off the permission flags at the bottom, and sends that exact physical hex number directly over the motherboard's memory bus to the RAM sticks.

#### The Kernel's Dilemma (How software handles this)

The fact that hierarchical tables store PA's means that the kernel cannot walk the page tables in software  same way the MMU does, because once paging is enabled all memory access must be VA's.

For this kernel uses the direct map concept we saw earlier. Deriving VA's from PA's and vice versa in software is very cheap as its just a matter of adding/subtracing an offset. 

#### Structure of PGD, PUD, PUD entries

We saw that these entries contain physical addresses. But physical addresses are only 40 bits (12 bits offsets added later). Instead of storing 12 bits offsets as zeros, they store only the 40 bits which leaves room for 24 more bits. What are stored there?

The answer is that the format of a PGD, PUD, or PMD entry is almost identical to a PTE. The "extra" bits (0–11 and 52–63) hold hardware flags, just like the PTE.

However, instead of those flags applying to a single 4KB page of data, they apply to the entire branch of the tree below them.

Here is exactly what those non-address bits are doing in the upper-level directories.

**1. The Cascade Effect (Bits 0, 1, 2, and 63)**

The CPU's hardware MMU evaluates security from the top down. The rules set at the PGD level cascade down and override anything below them. The most restrictive permission always wins.

- **Bit 0 (Present):** If this is 0 in the PGD, the MMU stops immediately. The entire 512 GB region of memory simply does not exist. It doesn't matter what the PUD, PMD, or PTE say.
- **Bit 1 (Read/Write):** If a PGD or PUD entry is set to 0 (Read-Only), then every single page in that massive block of memory is strictly Read-Only. Even if a specific PTE at the bottom says 1 (Writable), the hardware will block the write and throw a fault.
- **Bit 2 (User/Supervisor):** If the kernel clears this bit to 0 at the PGD level, it instantly walls off that entire 512 GB chunk of the tree from User-Space programs. (This is exactly how Linux separates Kernel space from User space without having to check individual 4KB pages!).
- **Bit 63 (NX - No Execute):** If set to 1 at the top level, no code can be executed from anywhere in that entire branch.

By putting these flags in the upper directories, the OS can secure massive chunks of memory with a single bit flip, rather than having to update millions of individual PTEs.

**2. The Game Changer: Bit 7 (Page Size)**

This is where the upper-level directories have a superpower that the PTE does not.

In a standard PTE, Bit 7 is used for caching rules (PAT). But in a PMD or PUD entry, Bit 7 is the Page Size (PS) bit.

If the OS sets Bit 7 to 1 in a PMD or PUD entry, it tells the hardware MMU: "Stop walking the tree right now. Do not look for a next-level table."

Instead of pointing to another table, the Physical Address bits (12–51) point directly to a massive block of contiguous physical RAM:

- If **Bit 7** is 1 in a PMD entry: The MMU maps a single **2 Megabyte "Huge Page"** instead of 512 individual 4KB pages
- If **Bit 7** is 1 in a PUD entry: The MMU maps a colossal **1 Gigabyte "Huge Page"**.


**Why does this matter? The TLB!**

Remember the TLB (Translation Lookaside Buffer) cache on the CPU? It has a very limited number of slots (usually around 1,000).

- If a database maps 1 GB of memory using 4KB pages, it consumes 262,144 TLB slots (which causes massive TLB misses and slows down the CPU).
- If the OS uses a 1 GB Huge Page at the PUD level, it consumes exactly 1 TLB slot. Performance skyrockets.

**3. The "Ignored" Bits (Bits 9-11 and 52-62)**

Just like in the PTE, these bits are ignored by the CPU hardware.

- **Bits 52-62** are left alone by the CPU, allowing the Linux kernel to store internal software metadata (like memory encryption keys in secure VMs).
- **Bits 9-11** are often used by the hypervisor (like KVM or VMware) if you are running a virtual machine, to help manage nested page tables.

### Contents of 64-Bit PTE Layout

A Page Table Entry (PTE) is exactly **64 bits (8 bytes)** long. But it does not just hold a Physical Address. It holds the address *plus* a whole suite of security, caching, and state flags.

How is that possible? Because of **4KB Alignment**.
Every physical page in RAM starts at an address that is an exact multiple of 4KB 2^12. Because of this, the true physical address of *any* page frame always ends in exactly **12 zeroes**.

Hardware engineers realized: *"Why waste 12 bits storing zeroes? Let's chop off those zeroes and use the bottom 12 bits of the PTE to store hardware flags!"*

Here is the exact bit-by-bit breakdown of a 64-bit PTE on a modern x86_64 system.


| Bit Range | Name | What it does |
| --- | --- | --- |
| **63** | **NX / XD** | **No-Execute / Execute Disable.** If set to `1`, the CPU refuses to run code from this page. This stops buffer overflow attacks where hackers try to execute data. |
| **52–62** | **Available** | Ignored by the CPU. The Linux kernel uses these for internal tracking (like memory protection keys). |
| **12–51** | **Physical Address** | **The Payload.** This is the 40-bit physical base address of the 4KB page frame in RAM. (The CPU appends twelve `0`s to this to get the real address). |
| **9–11** | **OS Available** | Ignored by the CPU. Linux uses these to store software state (e.g., if a page is currently pinned in memory). |
| **8** | **G (Global)** | If `1`, this page is not flushed from the TLB when the `CR3` register changes. Used heavily for kernel memory so the OS doesn't slow down during context switches. |
| **7** | **PAT / PS** | Page Attribute Table. Used for advanced caching rules. |
| **6** | **D (Dirty)** | **Set by Hardware.** If `1`, the process has written to this page. The OS knows it must save this page to disk before reusing the RAM. |
| **5** | **A (Accessed)** | **Set by Hardware.** If `1`, the page has been read or written to recently. |
| **4** | **PCD** | **Page-Level Cache Disable.** If `1`, hardware caching is disabled for this page (used for memory-mapped hardware devices like GPUs). |
| **3** | **PWT** | **Page-Level Write-Through.** Controls CPU cache write policy. |
| **2** | **U / S** | **User / Supervisor.** `0` = Kernel access only. `1` = User-space applications can access this memory. |
| **1** | **R / W** | **Read / Write.** `0` = Read-Only. `1` = Writable. |
| **0** | **P (Present)** | **The Most Important Bit.** `1` = The page is in physical RAM. `0` = The page is not in RAM (triggers a Page Fault). |

#### Why Physical addresses are only represented by 40 bits?

We saw that virtual addresses are represented by 36 bits, but physical addresses are actually 40 bits. It means including offset physical addresses are otoal 52 bits. 

**Why the Mismatch?(48-bit VA vs. 52-bit PA)**

Think of it this way:

- **Virtual Address Space (48 bits = 256 TB):** This is the maximum amount of memory a single process is allowed to see or map at one time.
- **Physical Address Space (52 bits = 4 Petabytes):** This is the maximum amount of actual physical RAM sticks you could theoretically plug into the motherboard.Because the PTE allocates all the way up to bit 51 for the physical address (51 + 1) (offset tracking starts at 12) = 52 bits total, a 4-level paging system can physically support up to 4 Petabytes of physical RAM, even though any individual process running on that machine can only map 256 Terabytes of it into its own virtual view at a time.

---

#### How the Kernel and CPU interact with these bits

The PTE is a shared communication channel between the Linux Kernel (Software) and the MMU (Hardware). Here is how they use these bits in practice:

##### 1. Demand Paging (Bit 0)

When you call `malloc()`, Linux creates the VMA but writes a PTE with the **Present (P) bit set to `0**`.
When your program tries to use that memory, the MMU checks the PTE, sees a `0`, and immediately throws a Page Fault exception. Linux wakes up, allocates the physical RAM, writes the Physical Address into bits 12-51, flips the Present bit to `1`, and tells the CPU to try again.

##### 2. The LRU Swapping Magic (Bits 5 & 6)

When your system runs out of RAM, Linux needs to decide which pages to kick out to the Swap partition on your hard drive. It uses a "Least Recently Used" (LRU) algorithm.

* The **CPU hardware** automatically sets the **Accessed (A)** bit to `1` the millisecond a program reads a page.
* The **Linux kernel** periodically sweeps through the PTEs in the background, checking the Accessed bits. If it sees a `1`, it logs that the page is active, and then *resets the bit back to `0*`.
* If Linux comes back later and the bit is *still* `0`, it knows the process hasn't touched this memory in a while, making it a prime candidate to be swapped to disk!

##### 3. Copy-on-Write (Bit 1)

When a process forks, Linux copies the page tables but flips the **R/W (Bit 1)** to `0` (Read-Only) for both the parent and the child.
If either process tries to modify a variable, the hardware blocks the write and triggers a Page Fault. Linux then secretly copies the physical page to a new location in RAM, updates the PTE to point to the new address, flips the R/W bit back to `1`, and lets the process continue.

##### What happens if the Present Bit (Bit 0) is 0?

Here is a brilliant kernel trick: If Bit 0 is `0`, the MMU ignores bits 1-63 completely. It considers the entire entry invalid.
Because the hardware isn't looking at those bits anymore, the Linux Kernel steals that 63-bit space! If a page has been swapped to the hard drive, Linux stores the **disk sector address** inside those available bits. When the Page Fault happens, Linux reads those bits to know exactly where to find the data on your hard drive!

