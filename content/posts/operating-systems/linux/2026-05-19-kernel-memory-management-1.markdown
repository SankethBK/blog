---
title:  "Memory Maangement in Kernel"
date:   2026-05-19
categories: ["operating systems", "linux"]
tags: ["memory", "pages"]

---

# Memory Management in Kernel

## Why Kernel Space Memory Management is Harder?

**Userspace** can fail safely and wait patiently. **Kernel-space** cannot, making its allocation fundamentally harder.


### Key Differences in Kernel Memory Allocation

* **Sleeping is often banned:** Userspace can block while waiting for memory. Kernel contexts (interrupts, spinlocks) cannot, requiring instant success or failure flags like `GFP_ATOMIC`.
* **Failure is catastrophic:** App failures just kill the app; kernel allocation failures crash the entire system. The kernel must rely on emergency reserves, reclaim, and the OOM killer to survive.
* **Dangerous recursion:** The kernel manages memory using memory. A reclaim operation can trigger filesystem actions that need more memory, causing deadlocks (prevented by flags like `GFP_NOFS`).
* **Strict physical constraints:** Userspace only worries about virtual memory. The kernel must manage physical pages, DMA limits, and NUMA locality.
* **Physical fragmentation matters:** The kernel frequently requires physically contiguous pages, making fragmentation a critical, system-halting roadblock.
* **Interrupt context is brutal:** Interrupt handlers need immediate memory without sleeping or waiting on locks, relying heavily on per-CPU caches and lockless structures.
* **High deadlock risk:** Allocators interact with reclaim, writebacks, and system locks. `GFP` flags are essential to dictate exactly what an allocator is safely allowed to do.
* **Predictable latency is required:** Kernel subsystems (networking, real-time workloads) cannot tolerate unpredictable allocation pauses, necessitating highly optimized allocators like SLAB/SLUB.


**The Mental Shift**

* **Userspace optimizes for:** Convenience, general throughput, and managing virtual fragmentation.
* **Kernel optimizes for:** Strict correctness, deadlock avoidance, latency guarantees, system survivability, and rigid hardware constraints.

## Pages

The kernel treats physical pages as the basic unit of memory management.Although the processor’s smallest addressable unit is a byte or a word, the memory management unit (MMU, the hardware that manages memory and performs virtual to physical address translations) typically deals in pages.

### CPU Access vs. MMU Management: Bytes vs. Pages

If kernel treats pages as the smallest unit of memory, then the next question that comes to mind is "Are all emmory read/write operations happens in units of pages? Then what's the point of CPU being capable of byte addressable?".

- **Memory Access (The CPU):** Happens at byte granularity.
- **Memory Management (The MMU & Kernel):** Happens at page granularity (typically 4KB).


### Layer 1: Memory Access (The CPU)

The CPU absolutely reads and writes individual bytes.

- When code executes `char x = buf[123]`, the CPU targets a specific virtual byte address.
- The hardware supports fine-grained operations: 1-byte, 2-byte, 4-byte, 8-byte, or vector reads/writes.

The CPU does not read a whole page just to pick out one byte; hardware directly accesses the requested byte once located.

```
read byte
write byte
read 8 bytes
write 4 bytes
```

### Layer 2: Memory Management (The MMU & Kernel)

The Memory Management Unit (MMU) does not care about the specific value being read or written; it only cares about the page that the value lives inside.

```
allocate page
map page
protect page
evict page
swap page
writeback page
```

**What happens when we read a byte from virtual address let's say `0x1234`**

- CPU requests a virtual byte address.
- MMU checks if the address is valid.
- MMU translates the virtual page to a physical page frame.

At this point, the kernel checks if the physical page actually exists in memory or should it be loaded from disk?

If the page is already present in memory then
- Hardware computes: Physical Address = Physical Frame Base + Byte Offset.
- Only the requested byte is read and returned to the CPU.

If the page is not present in memory:

- It triggers a page fault and kernel loads the entire page (typically 4 KB) from the disk.
- MMU translates the address and data is returned to CPU.

**What happens we write to a byte?**

- Address translation happens in similar way as for reads
- CPU writes the data to the specific byte address, if the data is supposed to be persisted to the disk the hardware marks the entire page as dirty and kernel later flushes the entire page to th disk.

### Why "Pages Are the Smallest Unit That Matters"

When textbooks say this, they mean pages are the smallest unit of management, not access. The kernel and MMU handle the following strictly on a per-page basis:

- **Permissions:** You cannot make byte 100 read-only and byte 101 writable. Memory protection (readable, writable, executable) is applied to the entire 4KB page.

- **Page Faults:** If a requested byte is in a page that isn't mapped in RAM, the MMU faults. The kernel cannot load a single byte from disk; it loads the entire page into RAM, and then the CPU reads the required byte.

- **mmap() & Disk I/O:** Reading a single byte from a mapped file pulls the whole 4KB page from disk into memory.

- **Writebacks:** Writing a single byte (e.g., buf[0] = 'A') writes exactly one byte in RAM. However, the MMU marks the entire page as "dirty." When it's time to sync with the disk, the writeback occurs at page granularity.

### Can Kernel Stil Access Raw Bytes?

Yes.

Very low-level code:

* DMA
* boot code
* page-table setup
* architecture code

sometimes manipulates physical addresses directly.

## struct Page

For absolutely every single physical page frame of RAM in your system, the kernel maintains one `struct page` to track its status. If you have 16GB of RAM, and each page is 4KB, you have about 4 million physical pages. That means the kernel has an array of 4 million `struct page` instances.

Here is a breakdown of why `struct page` is one of the most important, complex, and notoriously difficult data structures in the Linux kernel.

### 1. The Size Problem (Why it looks so messy)

Because there is one `struct page` for every physical page, the size of this structure is critical.

Imagine if `struct page` was just 100 bytes large. For a server with 1 Terabyte of RAM (which has ~268 million 4KB pages), the array of `struct page` structures alone would consume 26.8 GB of RAM just for metadata!

To prevent the kernel from eating all your RAM just to track your RAM, kernel developers fight over every single byte in this structure. To keep it as small as possible (typically 64 bytes on 64-bit systems), they use massive, deeply nested C `union`s.

Because a physical page can only be used for one purpose at a time (e.g., it’s either a file cache page OR a process's anonymous memory OR a Slab allocator chunk), `struct page` overlaps the data fields for all these different uses into the same memory space.

### 2. What struct page Actually Tracks

Despite the intense union nesting, conceptually, `struct page` tracks a few core pieces of metadata:

- **flags**: This is the most important field. It is a bitmask that tells the kernel the current state of the page. Are you locked? Are you dirty (modified and needs writing to disk)? Are you part of the Slab allocator? Are you on an LRU (Least Recently Used) list?

- **_refcount (Reference Count)**: How many different parts of the system are currently using this page? If this drops to 0, the page is truly free and can be given back to the Buddy Allocator.

- **_mapcount**: How many process page tables map to this physical page? (A shared library page might be mapped by 50 different processes, so its mapcount would be 50).

- **mapping**: If this page is holding file data (Page Cache) or swapped-out process memory, this pointer points to the address space object that owns it.

- **lru (or slab_list)**: A list head. If the page is active or inactive, this strings the page onto the kernel's LRU lists so the reclaim system knows which pages to evict when RAM gets low.

#### `_refcount` vs `_mapcount`

* **`_mapcount`:** "How many userspace **page tables** point directly here?" (Userspace visibility)
* **`_refcount`:** "How many total entities (userspace + kernel) require this page to **exist**?" (System-wide tracking)

> 💡 **The Rule:** A physical page cannot be freed unless its `_refcount` drops to **0**. `_mapcount` only tracks a subset of those references.

---

##### Quick Analogy: The Library Book

A book cannot be discarded from the library inventory if:

* It is sitting on a reference shelf (**Page Cache**)
* Patrons have checked it out (**Page Tables / Mapcount**)
* Staff are actively repairing the spine (**Kernel I/O / Drivers**)


##### Three Core Scenarios

###### 1. Idle Page Cache (e.g., `/bin/bash` cached but not running)

* `_mapcount == 0`  No active process page tables are mapping this page.
* `_refcount > 0` The kernel's page-cache data structures hold a reference to keep the file data in RAM.
* *Why:* Prevents the reclaim subsystem from evicting the page while the cache expects it to be there.

###### 2. Shared Library (e.g., `libc.so` used by 50 processes)

* `_mapcount == 50` Exactly 50 individual process page tables translate to this page.
* `_refcount > 50` Holds the 50 page table references *plus* the persistent page-cache tracking reference, along with any transient kernel operations.
* *Why:* `_refcount` will always be greater than or equal to `_mapcount`.

###### 3. Active Disk Write (Writeback I/O)

* When a dirty page is being flushed to disk, the writeback engine temporarily increments the reference count:

* *Why:* Ensures the memory frame is pinned in RAM and cannot be reclaimed midway through a hardware DMA transfer.

**Kernel Convention**

A lot of Linux naming is designed around this:

```c
get_*()
    acquires reference

put_*()
    releases reference
```

Example

```c
get_page()
put_page()

get_task_struct()
put_task_struct()

get_file()
fput()

kobject_get()
kobject_put()
```

### 3. The "God Object" Problem

Because physical memory is used for literally everything, `struct page` became what software engineers call a "God Object."

If you look at the source code (include/linux/mm_types.h), you will see fields dedicated to:

- The Buddy Allocator
- The SLUB Allocator
- Page Cache / Filesystems
- Page Table fragmentation
- RCU (Read-Copy-Update) mechanisms

It became so overloaded and confusing that developers often didn't know which fields were safe to read or write depending on what the page was currently being used for.

### 4. The Future: struct folio

Because `struct page` became too confusing—especially when dealing with "Compound Pages" (blocks of contiguous pages glued together to act as one huge page)—a major rewrite has been sweeping through the Linux kernel recently, led by developer Matthew Wilcox.

They introduced a new concept called `struct folio`.

A folio represents a memory allocation that is guaranteed not to be a random tail page of a larger block. The kernel community is currently in the multi-year process of converting hundreds of thousands of lines of code from using struct page to struct folio to make memory management safer and easier to reason about.


## Zones

### The Big Concept: Hardware Inequality

Imagine a computer with 16GB of RAM.

* The CPU can access all 16GB perfectly.
* An old sound card might only have a 24-bit address bus. It can physically only "see" and transfer data (DMA) to the first **16 Megabytes** of RAM.
* A modern 32-bit graphics card might only be able to see the first **4 Gigabytes** of RAM.

If the kernel accidentally gave that old sound card a memory page located at the 10GB mark, the sound card literally couldn't reach it. The system would crash or corrupt data. **Zones prevent this.**


### The Primary Zones (x86 Architecture)

Here are the main zones you will encounter in the Linux kernel:

#### 1. `ZONE_DMA` (The Bottom 16 MB)

* **What it is:** The lowest 16 Megabytes of physical RAM.
* **Why it exists:** Reserved exclusively for ancient ISA hardware and legacy devices that have severely limited Direct Memory Access (DMA) capabilities.
* **Usage:** Extremely rare in modern systems, but kept for backward compatibility.

#### 2. `ZONE_DMA32` (Up to 4 GB)

* **What it is:** Physical RAM from 16 MB up to 4 GB.
* **Why it exists:** Used for 32-bit devices (like older PCI cards) that can only address up to 4GB of physical memory.
* **Usage:** If a driver requests memory with the `GFP_DMA32` flag, the allocator guarantees the returned page lives below the 4GB physical boundary.

#### 3. `ZONE_NORMAL` (The "Everything Else" Zone)

* **What it is:** All physical RAM above 4 GB (on modern 64-bit systems).
* **Why it exists:** This is the standard, unrestricted memory. The kernel and CPU can access it perfectly, and modern 64-bit hardware can DMA into it without issue.
* **Usage:** This is where the vast majority of your applications, page cache, and standard kernel allocations live.

#### 4. `ZONE_HIGHMEM` (The 32-bit Nightmare)

* **What it is:** A historical zone for memory that the CPU cannot permanently map into the kernel's virtual address space.
* **Why it exists:** On old 32-bit CPUs, the kernel only had ~1GB of virtual address space. If you had 4GB of physical RAM, the kernel couldn't see it all at once. It had to temporarily "map" a window to high memory, read it, and unmap it.
* **Usage:** Mostly irrelevant on modern 64-bit CPUs (since a 64-bit kernel can map petabytes of RAM simultaneously), but you will still see it referenced everywhere in the kernel source code.


### Two Special Modern Zones

As systems evolved, developers added logical zones to solve software problems, rather than just hardware limits:

* **`ZONE_MOVABLE`:** A fake, logical zone used to fight fragmentation. It is populated only by memory that can be easily moved (like anonymous userspace pages or the Page Cache). By keeping movable pages isolated here, the kernel ensures that large, contiguous blocks of RAM are always available when a hardware device suddenly needs them.
* **`ZONE_DEVICE`:** Used for persistent memory (like Intel Optane PMEM) or memory that lives directly on a device (like a GPU) but is being mapped into the CPU's address space.


### How it connects to your `GFP` Flags

Earlier, we talked about how kernel allocators use `GFP` (Get Free Page) flags. This is exactly where they intersect!

When a kernel developer writes:
`page = alloc_pages(GFP_DMA32, order);`

They are telling the Buddy Allocator: *"I need a block of pages, but you MUST pull them from `ZONE_DMA32` or lower, because my hardware cannot reach `ZONE_NORMAL`."*

The Buddy Allocator maintains a separate free list for *each* zone. It will check the `ZONE_DMA32` list. If that zone is out of memory, the allocation fails, even if `ZONE_NORMAL` has 10 GB of free space.

