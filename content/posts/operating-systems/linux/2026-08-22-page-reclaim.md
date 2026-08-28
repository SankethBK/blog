---
title: "Page Frame Reclaiming"
date: 2026-08-22
categories: ["operating systems", "linux"]
tags: ["page reclaim", "mm_struct", "address_space", "reverse map", "page"]
---

# Page Frame Reclaiming

## The Page Frame Reclaiming Algorithm

### 1. Unified Page Cache & Dual-Caching Edge Case

* **Unified Page Cache:** Linux no longer separates the "disk/buffer cache" from the "page cache." All file and block I/O goes through a **single unified Page Cache** indexed by `(address_space, offset)`.
* **The Dual-Caching Exception:**
* Reading via a regular path (e.g., `/app/data.db`) uses the **file inode's** `address_space`.
* Reading via the raw disk node (e.g., `/dev/sda1`) uses the **block device inode's** `address_space`.
* **Result:** The exact same physical 4 KB block on disk can reside twice in RAM under two different `address_space` objects.


* **Practical Impact:** Rare in normal operation because accessing raw block nodes requires root privileges, and system tools handle raw access using unbuffered I/O (`O_DIRECT`).

---

### 2. Memory Allocation & Control (Modern vs. Historical)

* **Legacy Behavior:** Historical kernels applied loose checks on RAM allocation, allowing caches and processes to grow untamed until memory pressure triggered reclamation.
* **Modern Control (cgroups v2 / `memcg`):**
* Modern Linux uses **Memory Control Groups (`memcg`)** to enforce strict limits per container, systemd service, or user.
* System administrators can limit process memory, swap usage, and page cache footprint deterministically.

---

### 3. Demand Paging vs. Page Frame Reclaiming (PFRA)

* **Demand Paging (Page Allocation / Inbound):**
* **Reactive:** Triggers only on a Page Fault when unmapped virtual memory is accessed.
* **One-Way Allocation:** Maps physical pages into Page Table Entries (PTEs) on demand, but has **no built-in feedback mechanism** to detect when an application stops using a page.


* **Voluntary vs. Involuntary Release:**
* **Voluntary:** A process explicitly frees memory via `munmap()`, `madvise(MADV_DONTNEED)`, or process termination.
* **Involuntary (PFRA / `kswapd`):** Because demand paging cannot "force" processes to give up inactive pages, the kernel relies on `kswapd` and the Page Frame Reclaiming Algorithm:
* **File-backed pages:** Clean pages are dropped instantly; dirty pages are flushed to disk before reclamation.
* **Anonymous pages (Heap/Stack):** Unmapped from PTEs and swapped out to disk/swap space.

---

### 4. Low-Memory Deadlock Prevention

* **Watermark Reserves:** To avoid deadlocks during page reclamation (e.g., needing memory to allocate I/O buffers just to write a dirty page to disk), the kernel enforces strict memory watermarks (`min`, `low`, `high`).
* **Emergency Allocations:** Allocations required for page reclamation use dedicated `mempools` and the `PF_MEMALLOC` flag, guaranteeing a reserved memory floor so I/O operations always complete safely under heavy memory pressure.


### What Are Memory Watermarks?

Memory watermarks are predefined thresholds of free memory that the kernel uses to decide **when to start reclaiming memory**, **when to stop**, and **who gets to allocate memory when RAM runs low**.

They prevent a classic **"chicken-and-egg" deadlock**: To free a page, the kernel often has to write dirty data to disk. But writing to disk requires allocating new memory (for I/O requests, scatter-gather lists, and block drivers). If the kernel waited until free RAM hit absolute zero (0 bytes), it couldn't allocate the memory needed to do the disk write, locking up the system entirely.

---

### The Three Watermarks (`min`, `low`, `high`)

The kernel calculates these three thresholds per memory NUMA node/zone on boot (configurable via `/proc/sys/vm/min_free_kbytes`):

```
High Memory
  ▲
  │   [ Normal Zone: Asynchronous allocation allowed ]
──┼── High Watermark   ◄── kswapd goes to sleep (Reclamation Target)
  │   [ Background Reclamation: kswapd is actively waking up ]
──┼── Low Watermark    ◄── kswapd is woken up in the background
  │   [ Direct Reclaim: Allocating processes MUST help free pages ]
──┼── Min Watermark    ◄── Normal allocations fail; ONLY emergency threads allowed
  │   [ Emergency Pool: Reserved for PF_MEMALLOC / reclaim I/O ]
──┴── 0 KB Free RAM

```

#### 1. `High` Watermark (The Safe Zone)

* **Status:** System is healthy; plenty of free memory.
* **Behavior:** Processes allocate memory instantaneously with zero delay. If `kswapd` was running to free memory, reaching this mark signals it to go back to sleep.

#### 2. `Low` Watermark (Background `kswapd` Trigger)

* **Status:** Free memory is getting noticeably low.
* **Behavior:** The kernel wakes up the background daemon **`kswapd`**. `kswapd` works asynchronously in the background to reclaim pages (flushing dirty pages, evicting clean page cache pages) to push free memory back up to the `High` watermark. User processes are **not blocked** yet.

#### 3. `Min` Watermark (Direct Reclaim & Reserved Emergency Pool)

* **Status:** Memory is dangerously low.
* **Behavior:**
* **Direct Reclaim:** Normal user processes attempting to allocate memory are **stalled**. Instead of allocating immediately, the allocating process itself is forced to synchronously reclaim pages on the spot before it gets its allocation.
* **Emergency Reserve (`0` to `Min`):** The remaining memory between 0 and `Min` is **strictly off-limits** to normal processes. It is reserved exclusively for kernel threads performing page reclamation (flagged with `PF_MEMALLOC`).



---

### How This Solves the Deadlock

When memory drops below the `Min` watermark, a disk driver or I/O thread needing memory to write out a dirty page presents the **`PF_MEMALLOC`** flag.

The kernel recognizes this thread as an "emergency worker trying to free memory," allows it to dip directly into the **`0` to `Min` reserved pool**, grants the I/O allocation, completes the write to disk, and successfully frees up RAM for the rest of the system.


## PFRA Page Classification & Reclamation Strategies

When memory runs low, the PFRA evaluates physical page frames and categorizes them by content to determine how (or if) they can be freed and returned to the **Buddy System**.

```
                           ┌─────────────────────────┐
                           │   PFRA Memory Scan      │
                           └────────────┬────────────┘
                                        │
         ┌──────────────────┬───────────┴───────────┬──────────────────┐
         ▼                  ▼                       ▼                  ▼
  [Unreclaimable]      [Discardable]           [Syncable]         [Swappable]
  • Kernel Code/Data   • Clean File Pages      • Dirty File Pages • Heap / Stack
  • Active Slabs       • Clean Page Cache      • Dirty Page Cache • tmpfs / SHM
  • VM_LOCKED Pages    • Reclaimable Slabs     • Mapped Execs     • Anonymous mmap
         │                  │                       │                  │
         ▼                  ▼                       ▼                  ▼
     (Pinned)        (Dropped Instantly)    (Flush to Disk)    (Compress / Swap)

```

---

### Page Categories & Reclamation Actions

| Category | Page Types Included | Reclamation Action / Strategy |
| --- | --- | --- |
| **Unreclaimable** | Kernel code/data, Kernel stacks (`CONFIG_VMAP_STACK`), Active Slab allocations (`kmalloc`), Pages with `PG_reserved` or `VM_LOCKED` (`mlock`). | **Pinned in RAM.** The kernel cannot reclaim these under any circumstances without risking system instability or kernel panics. |
| **Discardable** | Clean page cache pages, clean file-backed executable mappings, unused dentries/inodes in Slab caches. | **Freed Instantly.** Since identical data exists on disk, the page is unmapped from Page Table Entries (PTEs) and immediately returned to the Buddy System without I/O. |
| **Syncable** | Dirty page cache pages, dirty file-backed `mmap` regions, modified block device metadata. | **Flushed to Disk.** Data must be written back to the underlying filesystem before the physical page frame can be safely evicted and freed. |
| **Swappable** | Anonymous pages (Heap, Stack, `mmap(MAP_ANONYMOUS)`), `tmpfs` mounts, and POSIX Shared Memory (`shmget`). | **Swapped Out.** Written to physical swap partitions/files, or compressed in RAM (`zswap`/`zram`), then unmapped from process PTEs. |

---

### Modern Kernel Improvements vs. Legacy LK 2.6

* **Unified Page Cache (No Independent Buffer Pages):**
* *Legacy:* Treated raw disk block buffers and file page caches as separate entities.
* *Modern:* Everything routes through a **single, unified Page Cache**. Metadata structures (`buffer_head`) merely reference page cache pages rather than maintaining distinct buffer memory.


* **Slab Shrinkers (`register_shrinker`):**
* *Legacy:* PFRA directly attempted to sweep unused dentry/inode caches.
* *Modern:* PFRA delegates kernel memory reclamation to modular **Slab Shrinkers**. Shrinkers clean up unused objects (dentries, inodes) to collapse entire slab pages, returning them to the Buddy System.


* **In-Memory Compressed Swap (`zswap` / `zram`):**
* *Legacy:* Swappable pages were always forced out to slow physical storage (HDD/SSD).
* *Modern:* Swappable pages are compressed on-the-fly and stored in RAM pools (`zswap`/`zram`), drastically reducing swap latencies and avoiding disk I/O bottlenecks.


* **Reverse Mapping (Anon-RMAP & File-RMAP):**
* *Legacy:* Finding all process PTEs pointing to a shared page frame was expensive and unoptimized.
* *Modern:* Interval trees and `anon_vma` hierarchies allow the kernel to quickly identify every PTE referencing a physical page frame, unmapping shared pages efficiently during reclamation.


---

## PFRA Design Heuristics & Modern Evolution

The PFRA relies on empirical heuristics to balance performance across diverse workloads (from desktop responsiveness to heavy database servers).

### 1. Invariant Core Design Rules (Still 100% True Today)

* **Free "Harmless" Pages First:** Unreferenced page cache and file-backed pages are prioritized over anonymous process memory because they can be evicted without altering Page Table Entries (PTEs) or writing to swap.
* **Universal Process Reclaimability:** Aside from locked pages (`VM_LOCKED`), all User Mode process memory—including sleeping process heaps and stacks—is eligible for reclamation.
* **Atomic Shared-Page Unmapping:** To free a physical shared page frame, the kernel must locate and unmap **all** referencing PTEs across every process before releasing the frame.
* **Locality & Aging Heuristics:** Reclaims only "unused" pages by leveraging the hardware **Accessed/Referenced bit** in x86 PTEs combined with age-based page tracking.

---

### 2. Modern Engine Upgrades vs. Classical Linux 2.6

| Mechanism | ULK Book Era (Linux 2.6) | Modern Linux Kernel (5.x / 6.x+) |
| --- | --- | --- |
| **Tracking Algorithm** | Binary Dual-LRU Lists (**Active** / **Inactive**). | **Multi-Generational LRU (MGLRU):** Tiers pages into multiple generation buckets, reducing CPU overhead and scan errors. |
| **Data Unit** | Individual `struct page` tracking. | **Memory Folios (`struct folio`):** Groups contiguous pages to reduce compound page management overhead during reclaim. |
| **Reclaim Balance** | Global `swap_tendency` formula via `/proc/sys/vm/swappiness`. | **Cgroup v2 Hierarchical Control:** `memory.swappiness` and reclaim tuning are applied per container/service. |
| **Reverse Mapping** | Early object-based RMAP. | High-performance **`anon_vma` interval trees** for instant, low-overhead shared page PTE lookups. |

---

### 3. Study Strategy for ULK Chapter 17

* **Focus on Concepts:** The architectural invariants (LRU aging, PTE unmapping, dirty-vs-clean handling, swappiness tradeoffs) remain the foundational baseline for OS memory design.
* **Ignore C Function Details:** Skip memorizing specific 2.6 internal function names (e.g., `shrink_zone()`, `refill_inactive_zone()`) as internal APIs undergo frequent refactoring.

**TLDR of reverse mapping**

1. A VMA describes a process’s virtual-address range; it is not the physical memory itself.
2. Reverse mapping (rmap) means starting from a physical page/folio and finding the userspace mappings that refer to it.
3. The PFN alone cannot tell us which userspace virtual address maps to the page, so Linux maintains additional reverse-mapping metadata.
4. For anonymous memory, anon_vma is the central structure connecting anonymous pages to the VMAs that may map them; anon_vma_chain represents the relationship between a particular VMA and an anon_vma.
5. Once rmap identifies the relevant VMA/process and mapping information, the kernel can locate and operate on the corresponding page-table mapping instead of searching every process’s page tables.
6. There can be many VMAs associated with an anon_vma, especially after operations such as fork() and VMA splitting, which is why efficiently searching those relationships matters.

```
Page/Folio
    │
    │ reverse mapping
    ▼
anon_vma
    │
    │ anon_vma_chain
    ▼
VMA
    │
    ▼
mm_struct / process
    │
    ▼
page tables
    │
    ▼
PTE → Page
```

## The Problem anon_vma Solves

To understand `anon_vma`, you first need to understand reverse mapping (`rmap`) for anonymous pages.

**Forward mapping** is easy: given a virtual address, walk the page table to get the physical page. The kernel does this constantly.

**Reverse mapping** is the hard direction: given a physical page frame, find all the virtual addresses (across all processes) that map to it. The kernel needs this for:

- **Page reclaim** (swapping): to unmap a page from all processes before evicting it
- **Page migration** (NUMA balancing, memory compaction)

You can think of modern rmap as having two major paths:

```
                         Page/Folio
                             │
                    "who maps me?"
                             │
                 ┌───────────┴───────────┐
                 │                       │
          file-backed                 anonymous
                 │                       │
          address_space               anon_vma
                 │                       │
                 ▼                       ▼
               VMA(s)                  VMA(s)
                 │                       │
                 ▼                       ▼
              page tables             page tables
```

**File-backed case**

Suppose:

```
Process A                  Process B
    │                          │
  VMA A                      VMA B
    │                          │
    └──────────┐  ┌───────────┘
               ▼  ▼
           address_space
               │
               ▼
          page cache
               │
               ▼
           Page X
```

`address_space` represents the relationship between a file and its cached pages.

The main takeaway from this should be ***"`address_space` is a centralized store for pages of a particular file regardless of how many process's have it open. But in case of `mmap` opens, `address_space` also tracks the VMA's of individual processes (Because of these pages gets reclaimed by kernel, it needs to set present bit of those PTE's to 0)***

So if Linux has: Page X and wants to find who maps it, it can go through the page’s file-backed mapping:

```
Page X
  ↓
address_space
  ↓
VMAs
  ↓
page tables
  ↓
PTEs
```

We will look into this path in more detail.

**Anonymous case**

There’s no file/address_space:

```
Page X
  ↓
anon_vma
  ↓
VMAs
  ↓
page tables
  ↓
PTEs
```

So your mental model can be:

> address_space is the reverse-mapping hub for file-backed memory, while anon_vma is the reverse-mapping hub for anonymous memory.

That’s a very useful thing to remember going forward.

### Naive Approach: Just Store the VMA

The simplest idea: when a process faults in an anonymous page, store a pointer to the VMA in the page's metadata (`struct page`).

This works fine until **fork()**.

After `fork()`, parent and child share the same physical pages (copy-on-write). Now one physical page is mapped by **two different VMAs** — one in the parent, one in the child. If you store only one VMA pointer in the page, you've lost the other.

And it gets worse: the child can fork again. You can have an arbitrarily deep tree of processes all sharing the same page.

**But how does storing pointer to VMA is going to help?**

Assuming we somehow solved the above limitation: let's say we store to a structure which is like array of VMA's in `struct page`. So that `struct page` can remain 64 bytes as promised while maintaining multiple reverse mappings (a hypothetical data structure) - how is reverse mapping to a raw VMA going to help? Because a VMA contains a range of virtual addresses, which cna be comprised of multiple pages. How will we know which is the page we want? 

It can be solved in a siple brute force way to begin with. Sicne VMA is a range of continuous virtual addresses, we can walk the page table for those virtual addresses and get the **PFN**. Since `struct page` also stores **PFN**, we can compare them, but remember its not the virtual addresses itself we're interested in, its the corresponding PTEs. But as we see this approach is certainly not feasible to implement. 

*What if we store an offset along with the VMA in our hypothetical reverse map?*

Now all we have to do is jump to `start of VMA` + `offset` and set its PTE's present bit to 0. This is hypothetical so far to explain why a reverse mapping to VMA can be useful, but this idea will help later. 

### Struct Page's Reverse Mapping

The `mapping` field in `struct page` (or `folio->mapping` in modern kernels) serves a dual purpose depending on whether the page is anonymous or file-backed:

```c
struct page {
    ...
    struct address_space *mapping; /* Also points to anon_vma if PAGE_MAPPING_ANON is set */
    ...
};
```

To tell the two apart, the kernel uses the **Least Significant Bit (LSB)** of the pointer:

1. **If LSB == 0 (`PageAnon(page) == 0`):**
* The page is **file-backed**.
* `page->mapping` points directly to a `struct address_space`.


2. **If LSB == 1 (`PageAnon(page) == 1`):**
* The page is **anonymous**.
* `page->mapping` points to a `struct anon_vma` (with the lowest bit set to 1 as a flag).

#### Accessing `anon_vma` in Kernel Code

Because the lowest bit is set to `1` to signal an anonymous page, the pointer address itself is slightly "off" (e.g., `0xffff880100000001` instead of `0xffff880100000000`).

To get the actual, valid C pointer to `struct anon_vma`, the kernel clears bit 0 using a mask macro (`PAGE_MAPPING_ANON`):

```c
// How the kernel retrieves the clean anon_vma pointer:
struct anon_vma *page_anon_vma(struct page *page)
{
    if (!PageAnon(page))
        return NULL;
    
    // Strip the lowest bit (PAGE_MAPPING_ANON flag) to get the raw pointer
    return (struct anon_vma *)((unsigned long)page->mapping - PAGE_MAPPING_ANON);
}

```

### Why do `address_space` and `anon_vma` feel so similar yet different, and how do they relate to each other?

#### 1. `address_space` vs. `anon_vma`: The Core Mental Bridge

The reason they feel similar is that **they serve the exact same structural purpose**: both are intermediate lookup hubs that map a **Physical Page Frame** back to a list of **Process VMAs**.

The key difference comes down to **Who owns the metadata anchor?**

```
                       REVERSE MAPPING HUBS
  
   File-Backed Memory                     Anonymous Memory
  ┌──────────────────┐                   ┌──────────────────┐
  │  address_space   │                   │     anon_vma     │
  └────────┬─────────┘                   └────────┬─────────┘
           │ Anchor:                              │ Anchor:
           │ The File Inode                       │ Process Hierarchy
           │ (Exists on disk,                     │ (Created during fork(),
           │  shared globally)                    │  private to process tree)
           ▼                                      ▼
  ┌──────────────────┐                   ┌──────────────────┐
  │  i_mmap Tree     │                   │ anon_vma_chain   │
  │  (Tracks VMAs)   │                   │  (Tracks VMAs)   │
  └──────────────────┘                   └──────────────────┘

```

#### Why `address_space` is "Easy":

For file-backed memory, the relationship between the physical page and the file is fixed. Page 5 of `/usr/lib/libc.so` is *always* offset index `5` of that file.

* If Process A and Process B both `mmap()` `libc.so`, the kernel attaches both Process A's VMA and Process B's VMA to the file's `address_space->i_mmap` tree.
* When Page 5 needs to be unmapped, the kernel looks at `page->mapping` (which points to `address_space`), asks the tree for all VMAs mapping offset `5`, calculates `vma->vm_start + (5 - vma->vm_pgoff)`, and targets the exact PTE instantly (`vm_pgoff` is the Offset into the file where this mapping starts, this works because if the mapping has begun at page 4, then page 4 is page 0 for that VMA and page 1 is actually page 5).

#### Why `anon_vma` had to be invented?

Anonymous memory (Heap, Stack, `malloc`) has no file backing it on disk. There is no global file inode to act as the anchor.

- When Process A allocates a heap page, it has no file offset.
- When Process A calls `fork()`, Process B shares that exact physical page via Copy-On-Write (COW).
- `anon_vma` was invented to act as an "artificial address_space" for file-less memory. It anchors the shared anonymous pages to the tree of processes that inherited them through `fork()`.

### `anon_vma` And `anon_vma_chain`

The kernel's answer is to introduce an intermediary object — `struct anon_vma` — that acts as a hub connecting physical pages to all the VMAs that map them.

Here's the structure relationship:

```
struct page
    └─> anon_vma  (via page->mapping)
           │
           └─> anon_vma_chain entries
                    │
                    ├─> VMA of parent process
                    ├─> VMA of child process
                    └─> VMA of grandchild process
```

The key types:

```c
struct anon_vma {
    struct anon_vma *root;      // root of the AV tree (for locking)
    struct rw_semaphore rwsem;  // protects the interval tree
    atomic_t refcount;
    struct rb_root_cached rb_root; // interval tree of anon_vma_chains
    ...
};

struct anon_vma_chain {
    struct vm_area_struct *vma;  // the VMA this chain entry belongs to
    struct anon_vma *anon_vma;   // the AV hub
    struct list_head same_vma;   // links all AVCs for this VMA
    struct rb_node rb;           // node in AV's interval tree (by vma address range)
    ...
};
```

Each `vm_area_struct` has:

```c
struct vm_area_struct {
    struct anon_vma *anon_vma;       // the AV this VMA is attached to
    struct list_head anon_vma_chain; // list of AVCs linking this VMA to AVs
    ...
};
```

#### What Happens at fork()

##### Step 1: Process A allocates an anonymous page (no fork yet)

A calls `mmap(MAP_ANONYMOUS)`, then accesses the memory → page fault → kernel faults the page in.


```
Process A
│
└── mm_struct_A
        │
        └── VMA_A  [0x7f000, 0x7f001)
                │
                │  (at fault time, kernel creates anon_vma)
                │
                ▼
            anon_vma_A   ←─────────────── page_A->mapping
                │
                └── AVC_1
                        ├── vma       = VMA_A
                        └── anon_vma  = anon_vma_A
```

**What just happened:**

- Kernel created anon_vma_A and attached it to `VMA_A`
- Created one `anon_vma_chain (AVC_1)` linking `VMA_A ↔ anon_vma_A`
- The faulted page's `page->mapping` now points to `anon_vma_A`
- AVC_1 is inserted into `anon_vma_A`'s interval tree, keyed by VMA_A's address 

##### Step 2: A forks → child B is created

`fork()` calls `dup_mmap()`, which walks every VMA in the parent and calls `anon_vma_fork()` for each.

```
Process A                          Process B
│                                  │
└── mm_struct_A                    └── mm_struct_B
        │                                  │
        └── VMA_A [0x7f000, 0x7f001)       └── VMA_B [0x7f000, 0x7f001)
                │                                  │
                │                        anon_vma_fork() runs
                │                                  │
                ▼                                  ▼
            anon_vma_A ◄──────────────── anon_vma_B
                │         (B's AV's          │
                │          root = A's AV)    │
                │                            │
                ├── AVC_1                    └── AVC_2 (B linked to its own AV)
                │     ├── vma      = VMA_A           ├── vma      = VMA_B
                │     └── anon_vma = anon_vma_A      └── anon_vma = anon_vma_B
                │
                └── AVC_3  ◄─── NEW (B's VMA also registered into A's AV)
                      ├── vma      = VMA_B
                      └── anon_vma = anon_vma_A


page_A->mapping ──────────────────────────────────► anon_vma_A
```

**What just happened:**

- Kernel created `anon_vma_B` for the child, but its `root` pointer points to `anon_vma_A`
- Created `AVC_2`: links `VMA_B ↔ anon_vma_B` (B's own club membership)
- Created `AVC_3`: links `VMA_B ↔ anon_vma_A` (B also registers into parent's club)
- `VMA_B` now has two AVCs on its `anon_vma_chain` list
- The page still points to `anon_vma_A` — unchanged


**Why does VMA_B register into `anon_vma_A`?**

Because `page->mapping = anon_vma_A`. The rmap walk starts there. If VMA_B isn't registered in `anon_vma_A`'s interval tree, the walk will never find B's mapping of the page.


##### Step 3: B forks → child C is created

Same process repeats. `anon_vma_fork()` runs for C.

```
Process A          Process B               Process C
│                  │                       │
└── VMA_A          └── VMA_B               └── VMA_C
        │                  │                       │
        ▼                  ▼                       ▼
    anon_vma_A ◄────── anon_vma_B ◄────── anon_vma_C
    (root)              (root=A)            (root=A)
        │                  │                       │
        │                  │                       │
        ├── AVC_1          ├── AVC_2               └── AVC_4
        │  VMA_A→AV_A      │  VMA_B→AV_B               VMA_C→AV_C
        │                  │                       
        ├── AVC_3          └── AVC_5               
        │  VMA_B→AV_A         VMA_C→AV_B            
        │
        └── AVC_6
           VMA_C→AV_A


page_A->mapping ──────────────────────────────────────► anon_vma_A
```


VMA_C ends up with three AVCs:

```
VMA_C->anon_vma_chain:
    AVC_4:  VMA_C ↔ anon_vma_C   (C's own club)
    AVC_5:  VMA_C ↔ anon_vma_B   (registered in B's club)
    AVC_6:  VMA_C ↔ anon_vma_A   (registered in A's club)
```

This is the key pattern: **a VMA gets one AVC per ancestor.**

**Now the rmap walk makes sense**

Page needs to be reclaimed. `page->mapping = anon_vma_A`.

```
start at anon_vma_A
    │
    query interval tree for page's address
    │
    ├── finds AVC_1 → VMA_A → walk A's page tables → clear PTE
    ├── finds AVC_3 → VMA_B → walk B's page tables → clear PTE
    └── finds AVC_6 → VMA_C → walk C's page tables → clear PTE
```

One lock (on `anon_vma_A->root`), one interval tree query, finds all three processes. Done.

The pattern in one line
> Every time you fork, the child's VMA registers itself into every ancestor's anon_vma. So the root `anon_vma` always has a complete membership list of everyone who could possibly be mapping pages originally faulted there.

These kind of data structures are common in systems programming. The broader idea here is intrusive **linked lists / intrusive trees**.

In a normal (non-intrusive) linked list:

```c
// the container owns the node
struct node {
    void *data;
    struct node *next;
};
```

In an intrusive linked list (what Linux uses everywhere):

```c
// the node is embedded inside the data
struct anon_vma_chain {
    struct list_head same_vma;   // embedded list node
    struct rb_node rb;           // embedded tree node
    struct vm_area_struct *vma;
    struct anon_vma *anon_vma;
};
```

The object is the node. No separate allocation, no pointer indirection. This is common in:

- Linux kernel (used absolutely everywhere — list_head is iconic)
- Embedded systems / RTOS (FreeRTOS, Zephyr)
- Game engines (where allocation overhead matters)
- Windows kernel (LIST_ENTRY is the same idea)

**The specific trick: one object, two data structures simultaneously**

This is where it gets more specialized. AVC sits in both an interval tree and a linked list at the same time:

```c
struct anon_vma_chain {
    struct rb_node rb;           // node in AV's interval tree
    struct list_head same_vma;   // node in VMA's linked list
};
```

This idea — embedding multiple membership handles inside one struct so it can belong to multiple collections at once — does appear outside the kernel, but it's rare in application code because:

- Most application code uses `std::vector,` `HashMap` etc. where the container owns the memory
- The performance pressure that justifies this complexity usually doesn't exist at application level

**On a Closing note: this is the summary**

- 1 AVC holds 1 VMA 
- 1 VMA can be attached to multiple AVs, with one AVC per attachment
- AVs form a tree across fork generations, each storing a `root` pointer
- AVCs actually sit in two linked lists simultaneously, not one:
```
AVC
├── rb node        → sits in anon_vma's interval tree (the AV side)
└── same_vma list  → sits in VMA's anon_vma_chain list (the VMA side)
```
  - **VMA side view** — walking `VMA->anon_vma_chain` gives you all AVCs for that VMA, and each AVC tells you which AV that VMA is registered in.
  - **AV side view** — walking `anon_vma->rb_root` (the interval tree) gives you all AVCs registered in that AV, and each AVC tells you which VMA is mapped there.

```
AV tree        — across fork generations, root pointer for locking
AVC rb node    — sits inside AV's interval tree (AV → find VMAs)
AVC same_vma   — sits inside VMA's chain list  (VMA → find AVs)
```

### The `index` field of `struct page` (The final piece of puzzle)

Yes, the Linux kernel's ``struct page`` has a field named `index`. It is declared as a type of `pgoff_t` (page offset type). Because `struct page` is heavily optimized to save memory, it consists of nested unions. The meaning of the index field changes dramatically depending on what the physical page is currently being used for.

#### 1. File-Backed Pages (Page Cache)

When a page is used to cache data from a file on disk (the page cache), index represents the offset of this page within that file, measured in page-sized units.
- **Example**: If you are reading a file and the kernel loads the block of data spanning from bytes 4096 to 8191 (on a standard 4KB page system), this is the second page of the file. The index field will be set to 1 (0-indexed).
- **Purpose**: It allows the kernel to quickly identify exactly which part of a file the physical page represents when searching through the file's `address_space` structure.

#### 2. Anonymous Memory (Process Heap / Stack)

When a page is allocated for anonymous memory (such as a program's heap, stack, or private data that doesn't map to a file on disk), `index` represents the virtual page offset within the process's Virtual Memory Area (`vm_area_struct`).

- **Purpose**: If the operating system runs low on memory and needs to swap this anonymous page out to disk, the `index` tells the kernel exactly where this data belongs in the process's virtual address space when it needs to be brought back (swapped in) later.

**But wait, a page can belong to multiple VMA's after `fork()` right? How can a single `index` represent both?**

This is the genius thing, when `fork` happens VMA's are cloned exactly 1:1, addresses ranges, everything remains same, so yes a page can simulatenously represent both VMA's. 

**What if a forked process changes its VMA?**

Then CoW kicks in and clones all the pages, so a same page no longer represents the two VMA's. 

**This `index` is the hypothetical `offset` for anonymous pages we arlier talked about.**

### The Full walk process to mark all PTE's as absent 

#### The setup

Say process A faulted in a page at virtual address `0x7f000000`. That page has:

```c
page->anon_vma = anon_vma_A
page->index    = 5        ← page number 5 within this anon_vma's space
```

A then forked B, B forked C. So `anon_vma_A`'s interval tree has AVC entries for all three VMAs as we discussed.

Now the kernel wants to reclaim this page. It needs to find and clear every PTE mapping it.


#### The walk

Kernel starts at `page->anon_vma` — that's `anon_vma_A`.

It locks `anon_vma_A->root` (which is itself, since it's the ancestor). One lock for the entire family tree.

Now it queries the interval tree: "give me all AVCs whose VMA covers `page->index = 5`."

This is where the interval tree earns its keep. Each AVC in the tree is keyed by its VMA's range expressed in `pgoff` space — not raw virtual addresses, but page offsets. So the query is essentially: which VMAs have `vm_pgoff <= 5 < vm_pgoff + vma_length_in_pages`.

Say it finds AVC_1 (VMA_A), AVC_3 (VMA_B), AVC_6 (VMA_C). For each one:


#### The offset arithmetic — your hypothetical made concrete

For each AVC, the kernel has the VMA. Now it needs the exact virtual address of the page within that VMA. This is exactly the "VMA + offset" idea you had earlier, just expressed precisely:

```c
va = vma->vm_start + (page->index - vma->vm_pgoff) * PAGE_SIZE
```

Breaking that down:

- `page->index` is the page's position (5 in our example)
- `vma->vm_pgoff` is where this VMA starts in that same offset space
- the difference is how many pages into the VMA our page sits
- multiply by `PAGE_SIZE` to get bytes, add `vm_start` to get the virtual address

So if VMA_A starts at `0x7f000000` and `vm_pgoff = 3`:

```
va = 0x7f000000 + (5 - 3) * 4096
   = 0x7f000000 + 8192
   = 0x7f002000
```

Now the kernel knows the exact virtual address. It goes into that process's `mm_struct`, walks the page table at `0x7f002000`, finds the PTE, and clears the present bit.

#### The forked VMA wrinkle you asked about

Here's the interesting part. After fork, VMA_B covers the same virtual address range as VMA_A — they're copies. So `vm_start` and `vm_pgoff` are identical in both. The arithmetic gives the same virtual address `0x7f002000` for both processes, which is correct — each process independently maps the same physical page at the same virtual address in their own address space.

But if B later called `munmap()` on part of its range, or `mremap()`, its `vm_start` and `vm_pgoff` shift. The same arithmetic still works — it adapts automatically because it uses each VMA's own numbers, not the parent's. This is the whole reason the interval tree query uses `page->index` against each VMA's own range rather than storing a raw virtual address in the page — raw virtual addresses would break the moment a child process reshuffled its memory layout.


### What "offset" concretely is

So to directly answer your earlier question — `page->index` is the offset. It's not a byte offset or a virtual address offset. It's the page's logical position within the anon_vma's namespace, set when the page is first faulted in and never changes. Every VMA that maps this page knows its own `vm_pgoff`, so any VMA can independently compute "where in my virtual address range does this page sit" without needing to talk to any other VMA or store anything extra.

That's the elegance of it — the offset is universal (stored once in the page), and each VMA localizes it to its own address space on the fly.