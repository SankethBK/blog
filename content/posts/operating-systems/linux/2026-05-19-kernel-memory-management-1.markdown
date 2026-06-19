---
title: "Memory Management in Kernel"
date: 2026-05-19T00:00:00Z
categories: ["operating systems", "linux"]
tags: ["memory", "pages"]
draft: false
ShowToc: true
TocOpen: false
hidemeta: false
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

## Low Level API's for Memory Management

These APIs are the direct interface to the **Buddy Allocator**. When you use these, you are bypassing the higher-level slab/slub allocators (`kmalloc`) and asking the kernel for raw, contiguous blocks of physical memory.

Before looking at the functions, you need to know about **`order`**.
The low-level allocator does not take a "size in bytes." It takes an `order`, which dictates the number of pages based on powers of two: **2^order**.

* `order = 0` → 1 page (2^0)
* `order = 1` → 2 contiguous pages (2^1)
* `order = 3` → 8 contiguous pages (2^3)

Here are the compressed notes for the core low-level page APIs.

---

### 1. APIs that return a `struct page` (Physical Tracking)

These functions return a pointer to the `struct page` metadata object, **not** a memory address you can directly read/write to. You use these when you are doing low-level memory manipulation (like mapping hardware or editing page tables).

* `alloc_pages(gfp_mask, order)`
* **The Big One.** Allocates 2^order physically contiguous pages.
* Returns a pointer to the `struct page` of the *first* page in the block (the "head" page). Returns `NULL` on failure.


* `alloc_page(gfp_mask)`
* A shortcut macro for `alloc_pages(gfp_mask, 0)`. Gets exactly one page.



### 2. APIs that return a Virtual Address (Usable Memory)

These functions allocate the pages *and* automatically return the virtual memory address pointing to the actual data. You use these when your C code actually needs to store data in the pages. *(Note: They return an `unsigned long` that you cast to a pointer).*

* `__get_free_pages(gfp_mask, order)`
* Allocates 2^order contiguous pages and returns a logical virtual address to the start of the block.


* `__get_free_page(gfp_mask)`
* Shortcut for `__get_free_pages(gfp_mask, 0)`. Gets one page.

#### How is Getting Virtual Address from __get_free_page Useful?

`alloc_pages()` returns `struct page *` which is metadata describing the physical pages. 

But we can't do

```c
struct page *page = alloc_pages(...);

page[0] = 42;
```

because `page` is only metadata about the actual emmory allocated, the the memory itself. 

`__get_free_page()` returns the actual start of the allocated memory as kernel virtual address (unsigned long).

So kernel can do

```c
unsigned long addr = __get_free_page(...);

char *buf = (char *)addr;

buf[0] = 'A';
```

### 3. APIs for Getting ZEROED Pages

**Why zero them?** If the kernel allocates a recycled page and gives it to a userspace process without clearing it, the new process might be able to read residual passwords, crypto keys, or data left behind by the previous owner.

* `get_zeroed_page(gfp_mask)`
* Allocates a single page, fills it entirely with zeros, and returns the virtual address.
* *Note:* There is no `get_zeroed_pages()` for multiple pages.


* **The `__GFP_ZERO` Flag**
* If you need multiple zeroed pages, or if you need the `struct page *` instead of the virtual address, you simply add the `__GFP_ZERO` flag to your `gfp_mask`.
* *Example:* `alloc_pages(GFP_KERNEL | __GFP_ZERO, 2)` → Returns 4 zeroed pages.



### 4. APIs for Freeing the Pages

You must free pages using the exact same `order` you used to allocate them, or the Buddy Allocator will severely corrupt its internal tracking.

* `__free_pages(struct page *page, order)`
* Frees a block of pages if you hold the `struct page` pointer.


* `free_pages(unsigned long addr, order)`
* Frees a block of pages if you hold the virtual memory address.


* `__free_page(struct page *page)` / `free_page(unsigned long addr)`
* Shortcuts for freeing a single page (`order = 0`).



---

### Cheat Sheet Summary

| Function | Returns | Number of Pages | Zeroed? |
| --- | --- | --- | --- |
| `alloc_pages(mask, order)` | `struct page *` | 2^order | No |
| `alloc_page(mask)` | `struct page *` | 1 | No |
| `__get_free_pages(mask, order)` | Virtual Address | 2^order | No |
| `__get_free_page(mask)` | Virtual Address | 1 | No |
| `get_zeroed_page(mask)` | Virtual Address | 1 | **Yes** |
| *(Any above) +* `__GFP_ZERO` | Depends on func | Depends on func | **Yes** |

## The Kernel's Virtual Address Space

### Why does Kernel Uses Virtual Addresses in First Place?

We noticed that `__get_free_page` returns the virtual address in kernel's address space. It raises the question, why is kernel using the virtual addresses in the first place?

The whole idea of virtual address space was to provide user space processes a notion that they are running independently. It also simplifies how user space accesses memory and adds a layer of security b/w user psace processes. But why does kernel also uses the same virtual address concept? Since the kernel obviously can see the actual physical address frames, and in fact it is the one to build and maintain page tables, why can't it just use the actual physical addresses?

The easier answer is MMU, all the memory accesses have to go via MMU and MMU can only receive VA as input, it will search the PA using 4 level page tables and return it. But if kernel passes PA, then it's not going to be present in the page table which results in failure. 

**The Real Reason: The Kernel Doesn't Want to Use Physical Addresses**

Even if kernel could magically bypass the MMU, the kernel would still choose virtual addresses. Here's why.

#### Problem 1: Physical Memory is Discontinuous

When you boot a machine with 16GB RAM, the physical address space is not a clean `0x0` to `0x3FFFFFFF` slab. It looks more like this:

```
0x00000000 - 0x0009FFFF  →  Usable RAM
0x000A0000 - 0x000BFFFF  →  VGA framebuffer (HOLE)
0x000C0000 - 0x000FFFFF  →  BIOS ROM (HOLE)
0x00100000 - 0x3FFFFFFF  →  Usable RAM
0x40000000 - 0x403FFFFF  →  MMIO for some device (HOLE)
...
```


ACPI tables, MMIO regions, firmware reservations — all punching holes in physical memory. If the kernel used raw physical addresses, every single subsystem would need to know about this map and dance around the holes. Virtual addresses let the kernel present a clean, contiguous view over a physically fragmented landscape.

#### Problem 2: The Kernel Has to Map Hardware Too

The kernel doesn't just manage RAM — it talks to device registers, framebuffers, PCIe BARs. These live at physical addresses outside RAM entirely.

With virtual addresses, the kernel can map a GPU framebuffer at some sane virtual address like `0xFFFF880040000000` and just treat it like memory. Without that abstraction, you'd need to constantly distinguish "is this a RAM address or a device address" at every layer of the stack.

#### Problem 3: vmalloc — The Killer Use Case

This is the one that really shows why virtual addresses are necessary by design, not just convenience.
The Buddy Allocator gives you physically contiguous pages. But physical contiguity is rare and expensive — fragmentation eats it up. For large kernel allocations (driver buffers, module code), there often aren't enough contiguous physical pages.

`vmalloc()` solves this by allocating physically scattered pages and mapping them into a virtually contiguous region:

```
Physical:                     Virtual (kernel):
Page at 0x1000  ──────────►  0xFFFF000000000000
Page at 0x9000  ──────────►  0xFFFF000000001000
Page at 0x3000  ──────────►  0xFFFF000000002000
```

The code using this memory sees a flat buffer. Without virtual addresses, this is simply impossible — you can't make scattered physical pages look contiguous to anyone.

## The Full Kernel Virtual Address Layout

```
0xFFFF888000000000  →  Direct map        (all physical RAM, linear)
0xFFFF000000000000  →  vmalloc area       (scattered pages, contiguous VA)
0xFFFFFFFF80000000  →  Kernel text/data   (the kernel image itself)
0xFFFFFFFFFF000000  →  Fixmap             (special fixed-purpose slots)
+ per-CPU areas, KASAN shadow, module space, vsyscall page, etc.
```

### 1. The Direct Map Region (The Fast Lane)

The Direct Map is a massive, contiguous region in the kernel's top-half virtual address space where the kernel maps all physical RAM directly, byte-for-byte.

Instead of scattering memory randomly, the kernel creates a perfectly parallel virtual mirror of the physical hardware.

#### 1. The Golden Formula

Because the mapping is perfectly linear, the kernel can bypass complex page-table lookups entirely when it needs to translate between physical and virtual addresses. It uses basic arithmetic:

```
 - Virtual Address = Physical Address + PAGE_OFFSET

 - Physical Address = Virtual Address - PAGE_OFFSET
```

(Note: `PAGE_OFFSET` is a hardcoded constant in the kernel architecture code. On modern x86_64, it is typically a massive number like `0xffff888000000000`).

It's a permanent, boot-time mapping of all physical RAM into the kernel's virtual address space, starting at `0xFFFF888000000000`.

```
Physical RAM          Direct Map (kernel virtual)

0x0000_0000     ───►  0xFFFF888000000000
0x0000_1000     ───►  0xFFFF888000001000
0x0000_2000     ───►  0xFFFF888000002000
...
0x4000_0000     ───►  0xFFFF8884_00000000
(1GB physical)        (1GB offset into direct map)
```

The math is just: `virtual = physical + 0xFFFF888000000000`
This is what `__va()` and `__pa()` do in the kernel source:

```c
#define __va(x)  ((void *)((unsigned long)(x) + PAGE_OFFSET))
#define __pa(x)  ((unsigned long)(x) - PAGE_OFFSET)
// PAGE_OFFSET = 0xFFFF888000000000
```

So when the kernel has a physical address — say from a struct page or a DMA report — it can reach the actual memory in one line, no page table manipulation needed.

#### 2. How the Kernel Builds It (Boot Time)

When the computer turns on, the CPU is running in physical memory mode. Before turning on the MMU (Memory Management Unit) to enable virtual memory, the kernel must set up its own page tables:

1. Hardware Discovery: The kernel asks the BIOS/UEFI, "Where are the physical RAM chips located?" (This is called the e820 memory map).

2. The Loop: The kernel writes a simple loop iterating over every available physical page frame (starting from physical address `0x0`).

3. Sequential Mapping: For every physical page it finds, it creates a Page Table Entry (PTE) mapping it directly to `PAGE_OFFSET + current_physical_address`.

4. Flipping the Switch: Once the loop finishes mapping all RAM, the kernel turns on the MMU. From that microsecond forward, the CPU only uses virtual addresses, but the kernel retains a perfect mathematical shortcut to physical hardware.

#### 3. Why the Direct Map Exists?

Remember that once MMU is enabled, it expects only VA's as input. The direct map is the cheapest form of virtual address translation for kernel's virtual address space. Because the way its setup is VA is always at a constant offset from PA, so kernel can easily derive one from another with simple math. Morever it sets up actual page table entries mapping these VA's to PA's because MMU is not aware of this cheap trick, it always refers to the page table and gets the corresponding PA from there. 

So in the end, its a win-win scenario for both kernel and MMU. The kernel's hypothetical direct map allows is to translate VA's to PA's and vice verse through simple math and MMU gets proper page table entries.

#### 4. Advanced Optimization: HugePages

Mapping 16GB of RAM in 4KB chunks would require creating 4 million Page Table Entries, wasting a massive amount of RAM just to hold the map itself.

To solve this, the kernel does not use 4KB pages for the Direct Map. It tells the hardware MMU to use HugePages (usually 2MB or 1GB pages) for this specific region. This drastically shrinks the size of the kernel's page tables and makes the hardware TLB (Translation Lookaside Buffer) extremely efficient.

### 2. The vmalloc Region

#### 1. The Problem It Solves

The Direct Map is fast and simple, but it has one hard constraint: **the physical pages it exposes are in whatever order the hardware placed them.** You cannot rearrange them through the direct map.

When the kernel needs a large buffer — say 32MB for a driver — the Buddy Allocator has to find 32MB of *physically contiguous* pages. On a system that's been running for hours, physical memory is fragmented. Those 32MB of contiguous pages may simply not exist, even if 512MB of free RAM is available scattered across thousands of small gaps.

`vmalloc()` solves this by decoupling two things that don't actually need to be coupled: **physical contiguity** and **virtual contiguity**.

#### 2. The Golden Trick

vmalloc takes physically scattered pages and maps them to a *new*, artificially contiguous virtual region:

```
Physical (scattered)          vmalloc region (contiguous VA)

Page at 0x1000  ──────────►  0xFFFF000000000000
Page at 0x9000  ──────────►  0xFFFF000000001000   (adjacent in VA, not PA)
Page at 0x3000  ──────────►  0xFFFF000000002000
```

Code using the buffer sees a flat, contiguous address range. It can increment a pointer across the whole thing freely. The physical reality underneath is irrelevant.

#### 3. Why These Pages Already Have Direct Map Addresses

Here is the part that seems contradictory: every physical page vmalloc uses is *already* accessible via the direct map. A page at physical `0x9000` is permanently reachable at `0xFFFF888000009000`.

So a vmalloc'd page genuinely has **two valid virtual addresses simultaneously** — one from the direct map, one from the vmalloc region. This is fine. Page tables are just data structures. Nothing stops two PTEs in different parts of the table from pointing to the same physical page frame.

```
Physical page at 0x9000
        │
        ├──► 0xFFFF888000009000   (direct map — always there, arithmetic-derived)
        └──► 0xFFFF000000001000   (vmalloc — explicitly constructed PTE)
```

#### 4. Why Not Just Use the Direct Map Addresses?

Because the direct map *mirrors physical layout*. The three pages at `0x1000`, `0x9000`, `0x3000` have direct map addresses `0xFFFF888000001000`, `0xFFFF888000009000`, `0xFFFF888000003000` — which are also not adjacent. You cannot pointer-walk across them as a single buffer. The direct map gives you *access* to every page. It cannot give you *contiguity* that doesn't exist physically.

#### 5. The Cost: Real Page Table Walks

The direct map's speed comes from its regularity — VA = PA + constant, so the kernel can skip the page table entirely and just do arithmetic.

vmalloc has no such shortcut. Its mappings are *genuinely irregular* — each virtual page points to a different, unrelated physical page. Every access to a vmalloc address requires the MMU to do a real 4-level page table walk.

This is not a bug. It is exactly what the MMU was built for. You pay the full hardware cost because you are using the full hardware capability.

```
Direct map access:   __va(phys)     → just addition, no walk
vmalloc access:      buf[1000] = x  → MMU walks 4 levels on every access
```

This is why vmalloc is used only for large, infrequent allocations — drivers, module code, large temporary buffers — never for hot-path kernel data structures.

#### 6. `__pa()` on a vmalloc Address is Undefined

`__pa()` subtracts `PAGE_OFFSET` and assumes the result is a valid physical address. This is only true inside the direct map. On a vmalloc address, `__pa()` returns garbage — a physical address that has nothing to do with where the memory actually is.

This is a real class of kernel bug. If you ever hold a vmalloc'd pointer, never pass it to `__pa()` or `virt_to_phys()`. The compiler won't stop you.

Right — that "multiple VAs to one PA" insight is the key that unlocks the rest of this. Once you accept that page tables are just flexible mappings with no exclusivity rule, the rest of the kernel's virtual address layout stops looking mysterious and starts looking like "different regions, each built for a different job."

Here's the rest of the map you need on x86-64.

### 3. Kernel Text/Data Region (`0xFFFFFFFF80000000`)

This is where the **kernel image itself** lives — the compiled code of the kernel, its global variables, `.bss`, `.rodata`, all of it.

Why a separate region instead of just using the direct map? Because this needs to be at a **fixed, predictable address** decided at link time, so that function calls inside the kernel resolve to constant addresses baked into the compiled binary. The direct map shifts depending on how much RAM you have and where it's physically laid out; the kernel's own code can't depend on that.

```
movq $0xFFFFFFFF81234560, %rax   ; call some_kernel_function
```

This only works if the kernel's code address is fixed and known at compile/link time, not computed at boot.

(Syscalls depend on interrupt tables mapping numbers to fixed memory addresses)

### 4. Module Space

Kernel modules (`insmod`'d drivers, filesystems) get loaded into a region adjacent to kernel text, **not** the direct map and **not** vmalloc.

Why not vmalloc? Because module code needs to be **executable**, and historically vmalloc regions had different protection defaults. Also, module addresses need to be close enough to kernel text for certain relocation types (some CPU architectures have limited branch-offset ranges, so "near" placement matters for performance and correctness).

So: another purpose, another carved-out region.

### 5. Fixmap (`0xFFFFFFFFFF000000`-ish)

This is a small set of **fixed virtual address slots**, set up very early at boot (before normal page table machinery is even fully running), used for things like:

- the APIC (interrupt controller) registers
- early consoles
- ACPI tables before the rest of memory management is online

The whole point: these are addresses you need to *know at compile time*, before you can dynamically allocate or look anything up. Fixmap exists because at certain points during boot, "dynamically map something" isn't an option yet — you need a hardcoded slot that's guaranteed to exist.

### 6. Per-CPU Areas

Each CPU core gets its **own private copy** of certain kernel data — scheduler run queues, statistics counters, local caches. The *same* per-CPU variable name resolves to a **different physical page** depending on which CPU is currently executing.

```c
DEFINE_PER_CPU(int, my_counter);

// On CPU 0, this resolves to one physical page
// On CPU 3, this resolves to a different physical page
this_cpu_inc(my_counter);
```

This is the wildest case of "same virtual concept, different physical backing" — except here it's not even the *same* virtual address; the kernel uses a base + per-CPU offset trick (stored in a CPU register) so the *same source code* transparently lands on different memory per core. This avoids cache-line contention between cores hammering the same counter.

### 7. KASAN Shadow Memory (debug builds)

If you've compiled a kernel with KASAN (Kernel Address Sanitizer) — which you might, since you're doing kernel debugging — there's a **shadow region** that mirrors the entire address space at 1/8th scale, tracking which bytes are valid to access. Every real memory access gets an extra check against its shadow byte to catch use-after-free and out-of-bounds bugs.

This is relevant to you specifically: if you ever build a debug kernel for your CVE-2026-31431 work and see addresses in the `0xFFFFEC00...` range in a crash dump, that's KASAN shadow memory, not "real" data — it's metadata about memory, not memory being used by the bug itself.

**The Pattern Across All of These**

Every region answers the same two questions differently:

| Region | "What goes here?" | "Why not just direct map?" |
|---|---|---|
| Direct map | All physical RAM | — (this is the baseline) |
| vmalloc | Large scattered allocations | Needs *contiguous* VA from non-contiguous PA |
| Kernel text | The kernel binary | Needs a *fixed, link-time-known* address |
| Modules | Loadable driver code | Needs proximity to kernel text + execute permissions |
| Fixmap | Boot-critical hardware | Needs to exist *before* dynamic mapping works |
| Per-CPU | Per-core private data | Needs *different* physical backing per CPU, same source |
| KASAN shadow | Memory-safety metadata | Needs a parallel universe mirroring all of memory |

Each one exists because the direct map's one good trick — "VA = PA + constant" — is only useful when you actually want a linear, permanent, 1:1 mirror of physical layout. Everything else needs some other property (fixed address, contiguity from chaos, per-core identity, execute permission, pre-boot availability), and the only way to get a different property is to build a different mapping with different rules.

## High Level (Byte) Allocators 

### kmalloc() and vmalloc()

#### kmalloc() — the everyday allocator

The go-to for almost all kernel allocations. Returns a **physically and virtually contiguous** chunk of memory, carved out of the direct map region. This is why `__pa()` works on kmalloc'd pointers — the memory genuinely lives in the direct map.

```c
struct dog *p = kmalloc(sizeof(struct dog), GFP_KERNEL);
if (!p)
    /* always check — never assume */
```

One subtlety: kmalloc may give you *more* than you asked for, because the underlying allocator is page/slab-based and rounds up. You'll never get less, but you can't know how much extra you got, so don't use it.

Free with `kfree()`. Calling `kfree(NULL)` is safe. Calling it on a non-kmalloc'd pointer, or double-freeing, is a kernel bug.

#### vmalloc() — when you just need the VA to be contiguous

Physically scattered pages, virtually contiguous. Slower than kmalloc because every access triggers a real 4-level page table walk and causes TLB pressure. Use it only when you need a large region and can't guarantee physical contiguity — the canonical example in the kernel itself is loading modules at runtime.

```c
buf = vmalloc(16 * PAGE_SIZE);
/* ... */
vfree(buf);   /* can sleep, don't call from interrupt context */
```

Never call `__pa()` on a vmalloc pointer. The result is garbage.

#### GFP flags — the ones that actually matter

Three categories exist (action, zone, type) but in practice you almost always reach for a **type flag**, which bundles the right action + zone combination for your context.

The decision tree is simple:

| Where are you? | Flag |
|---|---|
| Process context, can sleep | `GFP_KERNEL` — default choice, highest success probability |
| Interrupt handler / softirq / tasklet / holding spinlock | `GFP_ATOMIC` — cannot sleep, uses emergency reserves, more likely to fail |
| Block I/O code, must not recurse into more I/O | `GFP_NOIO` |
| Filesystem code, must not recurse into more FS ops | `GFP_NOFS` — classic deadlock prevention flag |
| DMA-able memory | `GFP_DMA | GFP_KERNEL` (or `GFP_ATOMIC` if no sleep) |

`GFP_KERNEL` vs `GFP_ATOMIC` is the axis that matters most. `GFP_KERNEL` can put the caller to sleep, swap pages, flush dirty data — it will fight hard to get you memory. `GFP_ATOMIC` cannot do any of that; it grabs from emergency reserves or fails immediately. This is why interrupt handlers are stuck with it and why it fails more often under memory pressure.

`GFP_NOFS` is worth internalizing separately — it exists entirely to prevent the deadlock where a filesystem allocation triggers more filesystem operations, which trigger more allocations, which loop forever. If you ever write filesystem or block layer code, this flag is why you don't just use `GFP_KERNEL` everywhere.

Here's the consolidated slab allocator section, written to slot into your existing notes — concise, conceptual, same style as your direct map / vmalloc sections.

---

## The Slab Layer

### Why It Exists

Kernel code constantly allocates and frees the same kinds of structs — `task_struct`, `struct inode`, `struct dentry` — thousands of times per second. Two problems with doing this via plain `kmalloc`/`kfree`:

1. **Re-initialization cost.** Every fresh object needs its fields zeroed, locks set up, defaults applied — redone every single time even though you just freed an identical object microseconds ago.
2. **No global coordination.** Before the slab layer, subsystems built their own ad-hoc "free lists" (a pool of reusable pre-built objects). The kernel had no visibility into these — it couldn't tell any of them to shrink under memory pressure.

The slab layer replaces all of that with one disciplined, kernel-wide object cache.

### The Three Layers

```
Cache  →  one per object type (inode_cachep, task_struct_cachep...)
Slab   →  one or more physically contiguous pages, owned by a cache
Object →  individual struct instances packed inside a slab
```

- **Cache**: one per type. Not multiple — just one pool per struct.
- **Slab**: a chunk of pages (often just one), sliced into equal-size slots. Exists because memory only comes from the page allocator in page-sized units, and object size rarely divides page size evenly — the slab absorbs that mismatch as small, bounded waste per page (vs. unbounded fragmentation).
- **Object**: the actual struct instance living in a slot.

Each slab is **full**, **partial**, or **empty**. Allocation preference: partial → empty → only ask the buddy allocator for fresh pages if neither exists. This means the buddy allocator is invoked once per *slab*, not once per *object* — that's the performance win.

### The Bookkeeping (skip the internals, keep this)

```
kmem_cache (the cache)
├── slabs_full
├── slabs_partial
├── slabs_empty

struct slab (one per slab)
├── s_mem   → first object
├── inuse   → how many allocated right now
├── free    → first free slot
```

Slab descriptors live inside the slab itself if there's enough leftover slack space, otherwise externally. The descriptor allocation logic itself goes through `__get_free_pages()` — i.e., down to the buddy allocator — only when a cache needs to grow.

### The API (this is the part you'll actually type)

```c
// Create once, typically at boot or module init
cachep = kmem_cache_create("name", sizeof(struct foo), align, flags, ctor);

// Alloc / free instead of kmalloc / kfree
obj = kmem_cache_alloc(cachep, GFP_KERNEL);
kmem_cache_free(cachep, obj);

// Destroy (rare — only if cache is fully empty and unused)
kmem_cache_destroy(cachep);
```

`create`/`destroy` can sleep — never call from interrupt context.

### Flags Worth Remembering

| Flag | One-liner |
|---|---|
| `SLAB_HWCACHE_ALIGN` | Cache-line align objects, avoids false sharing — use for hot paths |
| `SLAB_POISON` | Fills freed memory with `a5a5a5a5` — catches use of uninitialized memory |
| `SLAB_RED_ZONE` | Padding around objects — catches buffer overruns |
| `SLAB_PANIC` | Panic if allocation fails — for objects the kernel can't live without (e.g. `task_struct`) |
| `SLAB_CACHE_DMA` | Forces slab into `ZONE_DMA` — only if objects need DMA |

`SLAB_POISON`/`SLAB_RED_ZONE` are the conceptual ancestors of what KASAN does today.

### Where kmalloc Fits In

`kmalloc()` itself is built on the slab layer — it rides on a small ladder of general-purpose, size-bucketed caches (32B, 64B, 128B...). Dedicated named caches (`task_struct_cachep`, `inode_cachep`) exist for high-frequency, fixed-size structs where the overhead of a dedicated cache pays for itself. Everything else goes through `kmalloc`'s generic buckets.

### The One Rule to Carry Forward

If you're repeatedly creating/destroying objects of the same type — use `kmem_cache_*`. Never hand-roll your own free list.