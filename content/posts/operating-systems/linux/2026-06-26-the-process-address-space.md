---
title: "The Process Address Space"
date: 2026-06-26
categories: ["operating systems", "linux"]
tags: ["process", "virtual memory"]
---

## The Process Address Space — Intro

Same flat (single contiguous range) address space model you already have from the article — nothing new conceptually. Key term to lock in: a **memory area** (this book's name for what the article calls a **VMA**) is a permission-tagged interval within that address space. Access outside any valid area, or against an area's permissions (write to read-only, execute non-executable) → segfault.

The list of "what memory areas contain" is just a slightly different cut of the same segments from the article: text, data, bss, stack, shared library mappings, mmap'd files, shared memory, anonymous mappings (`malloc`). All non-overlapping — every valid address belongs to exactly one area.


**Your Question**

You're right to flag this, and your instinct is correct: **threads sharing an address space was already standard by the time this book was written** (kernel 2.6 era, pthreads have existed since the 90s). The book isn't describing something that didn't exist yet — it's just using that line as the *definition* of what a thread is, from the kernel's point of view.

Here's the actual distinction the book is drawing:

```
fork()  → new process, new address space (copy-on-write, per the article)
clone() with CLONE_VM → new thread, SAME address space
```

A "thread" in Linux, at the kernel level, isn't a fundamentally different kind of entity from a process — it's a `task_struct` (same as any process) that happens to **share its `mm_struct`** (the memory descriptor — you'll meet this struct shortly in this chapter) with another `task_struct`, instead of getting its own.

So the line means: when the kernel says "two tasks share an address space," that sharing relationship *is* what makes them threads of the same process, rather than two independent processes. It's not "threads were added later and now processes can optionally share" — it's "the kernel doesn't have a separate 'thread' concept at all; sharing the address space is the mechanism, and we call the result threads."

This is worth keeping in mind for when `mm_struct` shows up in this chapter: you'll likely see `task_struct->mm` pointing to a shared `mm_struct` for threads, versus each process getting its own.

Here are your notes for the memory descriptor.

---

## The Memory Descriptor (`mm_struct`)

### What It Represents

One per address space. Multiple threads sharing an address space share this single struct (same idea as your earlier note — sharing this struct is *what makes them threads* at the kernel level). This is the kernel's anchor for everything about a process's virtual memory: where the segments are, the page tables, the bookkeeping counters.

mm_struct describes the virtual address space, not the physical memory.

It answers questions like:

- What VMAs exist?
- What are this process’s page tables?
- What virtual addresses are valid?

It does not answer:

- Which physical pages are shared with other processes?

One `mm_struct` per address space. Threads created with `CLONE_VM` share this single `mm_struct`, which is what makes them share an address space. Independent processes always have separate `mm_structs`, even if some of their VMAs ultimately map the same physical pages (e.g., shared libraries or shared mmaped files).

When threads are created using `pthread_create(...);` 

Let's say we have three threads A, B and C. All of them point to the same:

```
            mm_struct
                │
     ┌──────────┼──────────┐
     │          │          │
 Thread A   Thread B   Thread C
 ```

That one `mm_struct` contains:

- same VMA list
- same page tables (pgd)
- same heap
- same stack mappings (each thread has its own stack VMA, but those VMAs live inside the same mm_struct)
- same shared libraries

This is what your note is describing.


### Fields worth keeping

| Field | Why it matters |
|---|---|
| `mmap` / `mm_rb` | **Same data, two structures** — covered below, this is the most interesting field in the struct |
| `pgd` | Pointer to the page global directory — this is the kernel's handle on the actual page tables for this address space (`CR3` material, from the article you read) |
| `mm_users` / `mm_count` | Two-tier refcounting — covered below |
| `start_code` / `end_code` | Bounds of the text segment |
| `start_data` / `end_data` | Bounds of the data segment |
| `start_brk` / `brk` | Heap bounds — `brk` is the current upper boundary, exactly the "program break" from the article |
| `start_stack` | Where the stack begins, It is the start of the `main` thread’s (initial thread’s) user stack. |
| `rss` | Resident Set Size — pages of this process *actually in physical RAM* right now (not just promised via VMA) |
| `total_vm` | Total pages of virtual memory mapped, promised or not |
| `map_count` | How many memory areas (VMAs) this process currently has |

The gap between `rss` and `total_vm` is worth sitting with: `total_vm` is everything in the VMA list — the article's "promise." `rss` is everything with an actual present PTE — the article's "reality." Same VMA/page-table distinction from yesterday, now visible as two counters on this one struct.

`start_stack` only represents the stack address of intial thread. In case of multiple threads, each thread will have its own `task_struct` which contains its own `RSP` register. But the thread's stack space will be part of one of the VMA's referred by `mmap` of `mm_struct`. Each `task_struct` will have a pointer to its corresponding `mm_struct`. 

### The Two-Tier Refcount — `mm_users` vs `mm_count`

This is genuinely a new wrinkle, worth getting precise on:

- **`mm_users`** — how many *tasks* (threads) are currently using this address space. 9 threads sharing one address space → `mm_users = 9`.
- **`mm_count`** — the actual reference count that decides whether the struct gets freed. All of `mm_users` collectively counts as **one** increment to `mm_count`.

```
9 threads sharing an mm_struct:
  mm_users = 9   (nine threads referencing it)
  mm_count = 1   (one "address space is in use" reference)
```

`mm_count` only decrements when `mm_users` hits zero — i.e., when *every* thread sharing this address space has exited. The struct is only actually freed when `mm_count` itself then reaches zero.

**Why two counters instead of one?** Because the kernel sometimes needs to temporarily pin an `mm_struct` in memory for reasons that have nothing to do with any specific thread using it — e.g., another part of the kernel inspecting it, or a lazy TLB switch scenario. That code increments `mm_count` directly without touching `mm_users`. If there were only one counter, the kernel couldn't distinguish "a thread is using this" from "something else needs this struct to stay alive a moment longer." Splitting them lets the *user count* (threads) and the *existence count* (struct lifetime) move independently.

### `mmap` vs `mm_rb` — Same Data, Two Shapes

This is the one really interesting design decision in this struct, and it directly answers something you'll care about once you're profiling: **why store the same VMA list twice?**

- **`mmap`** — a plain linked list of all VMAs. Good for: "give me every VMA, in order" (e.g. dumping `/proc/pid/maps`).
- **`mm_rb`** — the same VMAs, organized as a red-black tree. Good for: "which VMA contains this address?" — O(log n) instead of O(n).

The book calls this a **threaded tree** — not duplicated `vm_area_struct` objects, just two different *indexing structures* pointing at the same underlying objects. Same pattern you've seen before (cache + slab indexing, dentry hash table + LRU list) — one data set, multiple access structures, each optimized for a different query pattern.

**Why this specifically matters for you:** the article's entire page fault story hinges on "find which VMA contains the faulting address." That lookup is exactly what `mm_rb` exists for — it's the concrete data structure behind `find_vma()`, which you'll meet shortly. The linked list (`mmap`) wouldn't cut it for that lookup at scale — O(n) on every single page fault would be a real cost on a process with thousands of mappings.


Every VMA (vm_area_struct) has something like:

```c
struct vm_area_struct {
    unsigned long vm_start;
    unsigned long vm_end;

    struct vm_area_struct *vm_next;
    struct vm_area_struct *vm_prev;   // older kernels differ slightly
    ...
};
```

Conceptually:
```
mm_struct

         mmap
          │
          ▼
+----------------------+
| Text VMA             |
| 0x400000-0x410000    |
+----------------------+
          │
          ▼
+----------------------+
| Data VMA             |
+----------------------+
          │
          ▼
+----------------------+
| Heap VMA             |
+----------------------+
          │
          ▼
+----------------------+
| mmap() region        |
+----------------------+
          │
          ▼
+----------------------+
| Thread1 Stack VMA    |
+----------------------+
          │
          ▼
+----------------------+
| Thread2 Stack VMA    |
+----------------------+
          │
          ▼
+----------------------+
| Thread3 Stack VMA    |
+----------------------+
          │
          ▼
         NULL
```

The `mmap` linked list and `mm_rb` red-black tree shown in your book are from Linux 2.6 and are historically accurate. In modern Linux (6.x), the RB tree has been replaced by the Maple Tree, but the conceptual model is identical: `mm_struct` still owns a collection of VMAs; only the indexing data structure changed. So your mental model from the book remains correct.


### `mmlist`

All `mm_struct`s in the system, strung together in one global doubly-linked list, starting from `init_mm` (the address space of PID 1). Protected by `mmlist_lock`. Mostly bookkeeping — not something you'll need to reason about deeply, but worth knowing it exists if you ever see it walked in a crash dump.


### Allocating / Destroying a Memory Descriptor

#### The Allocation Path

`current->mm` — this is how any kernel code accesses "the address space of whoever's running right now." Worth memorizing this idiom; you'll see it constantly in kernel source.

**Normal fork:** `allocate_mm()` pulls a fresh `mm_struct` from `mm_cachep` — this is a direct, concrete instance of the slab layer you already know cold. Same shape as `task_struct_cachep`.

**Thread creation (`CLONE_VM`):** `allocate_mm()` is skipped entirely. Instead:

```c
atomic_inc(&current->mm->mm_users);
tsk->mm = current->mm;
```

This is the two-tier refcount from your last notes, now seen in the actual code path that triggers it. No new `mm_struct` — just bump `mm_users` and point the new task's `mm` field at the parent's existing struct. This *is* the mechanical definition of "thread" you already worked out: same struct, incremented user count.

### The Teardown Path

```
process exits
  → exit_mm()                    (housekeeping)
    → mmput()                    decrements mm_users
      → if mm_users == 0:
        → mmdrop()                decrements mm_count
          → if mm_count == 0:
            → free_mm()           returns mm_struct to mm_cachep
```

This is the exact mirror of allocation — the struct goes back into the slab cache it came from via `kmem_cache_free()`, not freed arbitrarily. Confirms the two-tier counter logic precisely: `mm_users` has to hit zero (every thread sharing it has exited) before `mm_count` even gets touched.

---

## Kernel Threads and `mm`

### The Core Fact

Kernel threads have `mm == NULL`. This isn't an edge case to handle — **it's the actual definition of a kernel thread**: a task with no user-space context. There's nothing to point `mm` at, because there's no user-space memory to describe.

### The Clever Part: `active_mm`

Here's the problem this solves: even though a kernel thread has no user-space pages, it still needs to execute — meaning it still needs *some* page tables loaded, at minimum to access kernel memory (which, recall from your direct map notes, is mapped identically into every address space's upper half).

Rather than burn memory creating a degenerate `mm_struct` just for kernel-only mappings, or pay the cost of a full address space switch when scheduling a kernel thread, the kernel does this:

```
task_struct->mm          → NULL for kernel threads
task_struct->active_mm   → points at whatever mm was active before this kernel thread ran
```

When the scheduler picks a kernel thread to run, it checks `mm`. NULL means "don't bother switching address spaces — just keep whatever was loaded, and remember it via `active_mm`." The kernel thread then borrows the previous process's page tables purely to resolve kernel-memory addresses, since those are identical across every address space anyway.

### Why This Matters

This is a genuine optimization, not just bookkeeping — it avoids:
1. Allocating a throwaway `mm_struct` + page tables for something that will never use user-space memory
2. The CPU cost of an actual address space switch (reloading `CR3`, flushing TLB entries) just to schedule a kernel thread that only touches kernel memory anyway

The mechanism only works *because* kernel memory mappings are universal across all address spaces — borrowing someone else's page tables for kernel-only access is safe precisely because every process's page tables agree on what kernel memory looks like.

### pgd — The Root of the Page Tables

`mm_struct->pgd` points to the root of the page-table hierarchy (the Page Global Directory on x86). This is the page table the CPU uses when this address space is active (`CR3` points here).

Every process has its own `pgd`, because every process has its own virtual address space.

Conceptually, each process’s page tables contain two regions:

```
                Page Tables (pgd)

+----------------------------------------+
| Userspace Mappings                     |
|  Text                                  |
|  Data                                  |
|  Heap                                  |
|  Stack                                 |
|  Shared libraries                      |
|  mmap() regions                        |
+----------------------------------------+
| Kernel Mappings (same for everyone)    |
|  Kernel text                           |
|  Direct map                            |
|  vmalloc                               |
|  Modules                               |
|  fixmap                                |
+----------------------------------------+
```

The userspace half is unique to each process. The kernel half is (mostly) identical across all processes. 

Processes do not contain mappings for other processes’ userspace memory.

### Why Every Process Contains Kernel Mappings

The kernel executes using kernel virtual addresses, so those addresses must be translatable by the MMU. Instead of switching to a separate “kernel page table” on every syscall, Linux simply includes the kernel mappings in every process’s page tables.

A syscall therefore looks like:

```
Userspace
    |
    | syscall
    v
Kernel Mode (Ring 0)
    |
    | same page tables
    v
Kernel virtual addresses
```

Only the CPU privilege level changes; the page tables remain the same.

### Why Can’t Userspace Access Kernel Memory?

Although the kernel mappings exist in every process’s page tables, their PTEs are marked Supervisor-only (User/Supervisor bit cleared).

So when userspace attempts:

```
Kernel VA
    |
    v
MMU finds valid PTE
    |
    v
Permission check fails (Ring 3 accessing Supervisor page)
    |
    v
Page Fault (#PF) → SIGSEGV
```

The mapping exists, but userspace lacks permission to use it.

### Kernel Threads and active_mm

Kernel threads have:

```c
task->mm == NULL
```

because they have no userspace address space.

However, the MMU always requires page tables to translate kernel virtual addresses. Instead of allocating a separate `mm_struct`, kernel threads temporarily borrow the previously running process’s page tables via `active_mm`.

This works because the kernel mappings are identical in every process.

```
Process A
    mm
     │
     ▼
    pgd
     │
     ▼
Kernel mappings
     ▲
     │
Kernel thread (active_mm)
```

This avoids allocating unnecessary page tables and avoids expensive CR3 switches when scheduling kernel threads.

```
kworker

task_struct
    |
    +--> mm = NULL
    |
    +--> active_mm ----+
                        |
                        ▼
                   mm_struct A
```


## Virtual Memory Areas (`struct vm_area_struct`)

**The Core Concept:** A VMA represents a single, contiguous interval of virtual memory addresses within a process's address space that shares the **exact same attributes** (same permissions, same backing file, same behavior).

The kernel treats the process address space as a patchwork quilt of these distinct memory objects.


### Fields worth keeping

| Field | Why it matters |
|---|---|
| `vm_start` / `vm_end` | Half-open interval `[vm_start, vm_end)` — inclusive start, exclusive end. `vm_end - vm_start` = size in bytes |
| `vm_mm` | Back-pointer to the owning `mm_struct` |
| `vm_next` / `vm_rb` | The same linked-list-and-red-black-tree dual-indexing pattern from `mm_struct` itself, applied at the per-VMA level |
| `vm_page_prot` | Permission bits — the readable/writable/executable flags from the article, in concrete kernel form |
| `vm_ops` | Operations table — covered below |
| `vm_file` | The mapped file, if this is a file-backed VMA (NULL for anonymous) |
| `vm_pgoff` | Offset into the file where this mapping starts |


### The One Thing Worth Sitting With: VMAs Are Per-Address-Space, Not Per-File

This is the precise statement of something you might otherwise gloss over: **two processes mapping the same file each get their own separate `vm_area_struct`.** The VMA isn't "the mapping of this file" — it's "this specific interval, in this specific address space." Same file, same physical pages potentially, but two distinct VMA objects, because each process has its own view of where things sit in *its* address space.

Conversely — and this is the direct payoff of yesterday's "threads share `mm_struct`" insight — if two threads share an `mm_struct`, they automatically share every VMA inside it too. Not duplicated, not synced — literally the same `vm_area_struct` objects, because there's only one address space between them. This single fact is the explanation for why one thread calling `mmap()` makes the new mapping instantly visible to every other thread in that process: there's no separate VMA list to update, just the one shared `mm_struct`'s VMA tree.

### 1. The Mathematical Boundaries

A VMA defines an address interval represented as:
`[vm_start, vm_end)`

* **`vm_start`:** The inclusive starting address (lowest).
* **`vm_end`:** The exclusive ending address (the first byte *after* the highest address).
* **VMA Length:** Calculated simply as `vm_end - vm_start`.
* **The Golden Rule:** Intervals of different VMAs within the same address space **cannot overlap**. If a process requests a new memory mapping that overlaps an existing one, the kernel will either split, merge, or reject it.

---

### 2. Deep Dive: Key Fields & Expanded Mechanisms

The text provides the raw struct; here is what those fields actually do under the hood:

#### A. Hardware vs. Software Permissions

The kernel splits memory protection into two separate fields:

* **`vm_page_prot` (Hardware-level):** This holds the exact architecture-specific bits that are written directly into the CPU's Page Table Entries (PTEs). It tells the MMU (Memory Management Unit) whether to trigger a hardware fault on read/write/execute.
* **`vm_flags` (Kernel-level):** This tracks the kernel’s high-level intent for the memory area.
* Examples include `VM_READ`, `VM_WRITE`, `VM_EXEC`.
* Special flags like `VM_GROWSDOWN` tell the kernel, *"If the process hits the edge of this specific VMA, don't crash it—it's the stack, so dynamically expand it downward."*

##### What does `vm_flags` (Kernel level) protection flags actually do?

`vm_flags` is kernel’s semantic understanding of what this VMA is supposed to behave like.

The easiest way to understand it is by looking at what the MMU knows versus what the kernel knows.

**What the MMU Knows**

The MMU only sees page tables.

A PTE contains things like:

```
Present
Writable
Executable (NX bit)
User/Supervisor
Dirty
Accessed
...
```

The MMU has no idea:

- whether this is a stack
- whether this came from malloc
- whether it’s mmap()
- whether it should grow
- whether it’s a shared mapping

It only knows:

“Can I allow this read/write/execute?”

**What the Kernel Knows**

When you call `mmap(...)` or `malloc(...)`, the kernel knows much richer information. For example:

```
This is:

- stack
- anonymous memory
- shared mapping
- executable
- locked in RAM
- huge page
- etc.
```

That information lives in `vm_flags`

**Example 1 — Stack**

Suppose the kernel creates your stack VMA. It might have:

```c
vm_flags =
    VM_READ |
    VM_WRITE |
    VM_GROWSDOWN
```

The MMU can understand `READ`, `WRITE` but `VM_GROWSDOWN` is meaningless to hardware.

The CPU has no instruction saying: “Oh, this page is a stack.” Only the kernel understands that.

When your stack overflows slightly:

```
Current Stack

+------------+
|            |
|            |
+------------+
 ^
 RSP moves here
```

CPU raises a page fault. Kernel sees: `VM_GROWSDOWN` and says: “Ah, that’s a legitimate stack expansion.”. It allocates another page. Without that flag: same page fault would become: `SIGSEGV`

**Example 2 — Shared `mmap()`**

Suppose:

```c
mmap(..., MAP_SHARED)
```

Kernel records: `VM_SHARED`. The MMU has absolutely no concept of Shared mapping. Later, when one process writes: kernel checks: `VM_SHARED` and knows: propagate changes to the backing file. Hardware cannot do that.

**Example 3 — Locked Memory**

Suppose: 

```c
mlock(ptr);
```

Kernel sets: `VM_LOCKED` The MMU doesn’t care. Later the memory reclaim code asks: "Can I evict this page?" Kernel checks: `VM_LOCKED` and answers: "No" Again: pure software policy.


#### B. What Backs the Memory? (File vs. Anonymous)

A VMA can represent two fundamentally different kinds of memory:

| VMA Type | Primary Field Used | Description | Example |
| --- | --- | --- | --- |
| **File-Backed** | `struct file *vm_file` | Points to a real file on disk via the VFS. `vm_pgoff` tracks the exact offset inside that file. | Executable code (binary), shared libraries (`.so`), or files mapped via `mmap()`. |
| **Anonymous Memory** | `struct anon_vma *anon_vma` | Points to an internal kernel tracking structure. `vm_file` stays `NULL`. | The Heap (`malloc`), the Stack, and uninitialized variables (BSS). |

> **Advanced Note (`anon_vma`):** The `anon_vma` structure handles **Reverse Mapping (rmap)**. If the kernel is running out of physical RAM and wants to reclaim a physical page, it uses `anon_vma` to track down every single process currently using that page so it can clear their page tables before swapping the page out to disk.

#### C. VMA Operations (`struct vm_operations_struct *vm_ops`)

Like the VFS, VMAs use an object-oriented approach in C. The `vm_ops` pointer contains methods for managing this specific memory block.

The most critical function pointer in this structure is **`fault()`**:

```c
int (*fault)(struct vm_area_struct *vma, struct vm_fault *vmf);

```

* **How it works:** When a process requests memory (like via `malloc` or mapping a file), the kernel is lazy. It creates the VMA but doesn't actually allocate physical RAM right away.
* When the process first tries to read or write to that address, the CPU triggers a **Page Fault**.
* The kernel looks up the VMA, finds its `vm_ops->fault()` method, and executes it. If it’s a file-backed VMA, the `fault()` function reads the missing data from the hard drive into RAM on the fly.

### 3. How VMAs Behave Across Processes and Threads

* **Threads:** Because threads share a single `mm_struct`, they share the exact same list and tree of `vm_area_struct` objects.
* **Processes (Shared Memory):** If two entirely separate processes map the same shared library file into memory, they **do not** share a VMA.
* Process A has its own `mm_struct` pointing to a unique `vm_area_struct`.
* Process B has its own `mm_struct` pointing to a different unique `vm_area_struct`.
* Both unique VMAs will have their `vm_file` fields pointing to the *exact same VFS file object*, allowing them to share the underlying physical RAM pages while keeping their process structures completely independent.


---

## VMA Flags (`vm_flags`)

### The Core Distinction Worth Understanding

`vm_flags` is **software policy**, not hardware permission. This is subtle but matters: `vm_page_prot` (from yesterday's notes) is what the MMU actually checks on every access — the hardware-level read/write/execute bits. `vm_flags` is the kernel's own bookkeeping about what's *allowed to happen* to this VMA as a whole — copying, growing, swapping — decisions the kernel makes in software, never the hardware. Two related but distinct layers.

### Flags worth remembering

| Flag | What it means |
|---|---|
| `VM_READ` / `VM_WRITE` / `VM_EXEC` | The permission triad — same W^X logic from your article notes. Code: `READ+EXEC`, no `WRITE`. Data: `READ+WRITE`, no `EXEC` |
| `VM_SHARED` | Set → shared mapping (multiple processes observe writes — your article's `MAP_SHARED`). Unset → private mapping (`MAP_PRIVATE`, COW on write) |
| `VM_GROWSDOWN` | This is the literal flag behind the **stack guard page mechanism** from your article — the stack VMA is marked growable, and this flag is how the kernel knows to extend it downward on a fault instead of treating it as invalid |
| `VM_IO` | Marks a device I/O mapping (driver-created via `mmap()` on device memory) — excluded from core dumps |
| `VM_RESERVED` | Pages here must never be swapped — used by device driver mappings, conceptually related to the `mlock()`/pinned-memory case from your article (GPU DMA buffers), though this is the VMA-level flag rather than the userspace API |
| `VM_SEQ_READ` / `VM_RAND_READ` | Hints set via `madvise(MADV_SEQUENTIAL/MADV_RANDOM)` — directly controls the **readahead** behavior your article covered in the `mmap()` vs `read()` aside. Sequential hint → kernel reads ahead more aggressively; random hint → readahead gets throttled down |
| `VM_DONTCOPY` | This VMA is skipped during `fork()`'s COW setup — not inherited by the child at all |

**Safe to skim past**

`VM_MAYREAD`/`VM_MAYWRITE`/`VM_MAYEXEC`/`VM_MAYSHARE` — these just track whether a permission *could* be granted later (relevant to `mprotect()` validity checks), not whether it currently is. `VM_SHM`, `VM_DENYWRITE`, `VM_EXECUTABLE`, `VM_DONTEXPAND`, `VM_ACCOUNT`, `VM_HUGETLB`, `VM_NONLINEAR` — narrow, situational flags (shared memory segments, hugepage-backed VMAs, legacy nonlinear file mappings). Not worth memorizing; recognize the names if you see them in a crash dump, look up the specific one then.

**The thread to pull forward**

`VM_GROWSDOWN` is your strongest connection point — it's the mechanism, not just the concept, behind something you already understand deeply from the article (stack growth + guard page). Worth remembering this flag exists the next time you're tracing a stack-related fault.


## The VMA Operations Table (`struct vm_operations_struct`)

**The Core Concept:** This structure acts as the **Virtual Method Table (vtable)** for virtual memory. It allows the kernel to treat all memory regions generically while letting individual backends (like `ext4`, anonymous memory, or device drivers) define their own behavior for memory access.


### A. `int (*fault)(struct vm_area_struct *vma, struct vm_fault *vmf)`

This is the most heavily executed function pointer in the entire Linux memory management subsystem. It drives **Demand Paging**.

* **The Reality:** When a process allocates memory, the kernel allocates *zero* physical RAM; it only creates a VMA wrapper. Physical memory is assigned when the CPU triggers a Page Fault upon initial access.
* **Under the Hood:** The page fault handler determines which VMA contains the faulting address and calls its specific `fault()` method.
* *File-backed VMA (`ext4`):* The `fault()` method reads the required page from disk cache (or physical storage) into RAM and maps it into the process's page tables.
* *Anonymous VMA:* Relies on a generic kernel handler to allocate a zeroed page of physical RAM (the zero page).


* **Crucial Return Codes:** The `fault()` function doesn't just return a simple integer error code. It returns specific kernel flags encoded as bitmasks:
* `VM_FAULT_MINOR`: The page was already in the kernel's page cache; it just needed to be mapped to this process's page table. (Incredibly fast).
* `VM_FAULT_MAJOR`: The page had to be fetched from physical disk or swap. (Extremely slow disk I/O).
* `VM_FAULT_OOM`: The system is completely out of memory.
* `VM_FAULT_SIGBUS`: Bad memory access; results in a segmentation fault/bus error.

Every page fault path your article walked through in detail — demand paging zero-fill, file-backed mmap reading from the page cache, the four-quadrant table of (anonymous/file-backed) × (first-access/evicted) — all of it funnels through this one function pointer, dispatched per-VMA-type.

```

MMU finds present=0 PTE
  → CPU raises page fault
    → kernel's fault handler runs
      → finds the VMA covering the faulting address (via mm_rb)
        → calls vma->vm_ops->fault(vma, vmf)
```

This is the concrete mechanism behind the article's "the kernel's page fault handler" — it's not one monolithic function, it's dispatched per memory-area-type through this operations table. An anonymous VMA's fault() does the zero-fill-a-fresh-frame path. A file-backed VMA's fault() does the "read from page cache, or load from disk if not cached" path. Same calling convention, different backing implementation — exactly the polymorphism-via-function-pointers pattern you've now seen in VFS, slab, and here.

The same hardware exception: `#PF` handled:

- lazy allocation
- mmap()
- executable loading
- swap-in
- COW
- stack growth
- illegal access

The CPU doesn’t distinguish them. The kernel does.

**My Mental Model**

I don’t think of fault() as: “Page fault handler.”

I think of it as: “Given a VMA and a faulting address, teach the kernel how to make this virtual address usable.”

That’s why it’s part of `vm_operations_struct`.

Each VMA type has a different answer to: “How do I materialize this page?” and `fault()` is where that knowledge lives.

### B. `int (*page_mkwrite)(struct vm_area_struct *vma, struct vm_fault *vmf)`

This method handles what happens when a page that was previously marked **Read-Only** is suddenly written to.

* **Scenario 1: Copy-on-Write (COW):** When a process calls `fork()`, the kernel doesn't duplicate the memory. It marks the parent's memory pages as Read-Only and shares them with the child. The moment either process tries to modify a page, `page_mkwrite` kicks in, duplicates the physical page in RAM, marks it writable, and breaks the tie.
* **Scenario 2: Shared File Mappings (`mmap` with `MAP_SHARED`):** If a process maps a file to memory and changes a byte, that change must eventually go back to the disk. `page_mkwrite` intercepts the write, marks the physical page as **Dirty** in the kernel's radix tree, and alerts the filesystem filesystem driver (like `ext4`) that this page needs to be scheduled for *writeback* to physical storage.

### C. `void (*open)(struct vm_area_struct *)` & `void (*close)(struct vm_area_struct *)`

These track the lifecycle of a VMA, but they do not execute during basic allocation/deallocation (`malloc`/`free`). Instead, they track **VMA Splitting, Merging, and Cloning**.

* **`open()`:** Invoked whenever a VMA is cloned (like during `fork()`) or when a single VMA is split into two because you changed permissions on a tiny subset of its memory range.
* **`close()`:** Invoked when a VMA is destroyed via `munmap()`, when a process exits, or when two adjacent VMAs merge into one, destroying the old individual wrappers.


## Lists and Trees of Memory Areas

**The Core Concept:** To manage a process's virtual memory areas (VMAs), the kernel overlays two completely distinct data structures—a **singly linked list** and a **red-black tree**—over the exact same `vm_area_struct` instances.

This design choice maximizes performance by matching the right data structure to the right operational workload.

---

### 1. Data Structure #1: The Singly Linked List (`mmap`)

The `mmap` field inside the memory descriptor (`mm_struct`) points to the first VMA in a linear chain.

* **How it links:** Every `vm_area_struct` has a `vm_next` pointer that points to the next VMA in line. The final VMA points to `NULL`.
* **Sorting Rule:** The list is strictly sorted by **ascending memory addresses**. The VMA handling the lowest virtual memory address is always at the head of the list.
* **The Use Case:** **Complete Traversal.** When the kernel needs to read through every single memory area sequentially—like when a process terminates and its entire address space must be wiped—walking a flat linked list is incredibly clean and fast.

### 2. Data Structure #2: The Red-Black Tree (`mm_rb`)

The `mm_rb` field points to the root of a highly optimized, self-balancing binary search tree.

* **How it links:** Each `vm_area_struct` is anchored into the tree using its `vm_rb` node field.
* **Sorting Rule:** Left children have lower memory address intervals; right children have higher memory address intervals.
* **The Use Case:** **Targeted Search.** When a process page-faults at a specific random address, the kernel needs to find the exact VMA containing that address instantly. Searching a flat list of hundreds of VMAs would be too slow. The red-black tree guarantees that lookups, insertions, and deletions take **$O(\log n)$** time.

---

> ⚠️ **Peer Review: Spotting a Textbook Typo**
> Just a heads-up on a sneaky error in this excerpt! The text says: *"The root node is always red."* >
> Standard computer science rules for Red-Black trees actually dictate the exact opposite: **The root node is always black.** Robert Love's book is legendary, but this is a well-known slip of the pen. Keep that in mind if you have to implement or explain an RB-tree in an assignment or interview!

---

### Comparison: Dual-Wielding Design

| Metric | Linked List (`mmap`) | Red-Black Tree (`mm_rb`) |
| --- | --- | --- |
| **Pointer Field Used** | `vm_next` | `vm_rb` |
| **Search Time** | Linear: $O(n)$ | Logarithmic: $O(\log n)$ |
| **Best Used For** | Iterating through all regions sequentially | Instantly finding a specific address region during a Page Fault |
| **Sorting Criterion** | Linear ascending address space | Binary tree branching (Left < Node < Right) |

By paying a tiny penalty in memory to store a few extra tracking pointers inside the VMA structure, the kernel completely eliminates the performance trade-off between searching and traversing.

## Manipulating Memory Areas

### `find_vma()` — the function the article called "checking the VMA"

This is, literally, the kernel code behind the step in your article's page fault walkthrough where the kernel "checks if the faulting address falls inside a valid VMA." Worth seeing it concretely now that you understand both pieces it depends on (the cache and the tree).

**What it actually finds:** not "the VMA containing `addr`" — more precisely, "the first VMA whose `vm_end > addr`." This subtlety matters: if `addr` falls in a gap between VMAs, `find_vma()` still returns *something* — the next VMA after the gap — not NULL. You have to additionally check `vma->vm_start <= addr` yourself to know whether `addr` is actually *inside* that VMA, or just before it.

This is exactly the check the fault handler needs to make per your article: "is this address legitimately covered by a VMA" vs "this is a genuine segfault."

### The Cache (`mmap_cache`) — One-Entry, But Earns Its Keep

```c
vma = mm->mmap_cache;
if (!(vma && vma->vm_end > addr && vma->vm_start <= addr)) {
    // cache miss — fall through to tree walk
}
```

Just the last VMA that was looked up, remembered as a single pointer on `mm_struct`. The hit rate (30-40%) comes from **temporal locality of operations** — same idea as cache lines and TLB locality from your article, just one level up the stack: if you just touched a VMA, you'll probably touch it again soon (a process scribbling across the same buffer repeatedly, for instance).

Note the cache check is *stricter* than the tree-walk's matching logic — it explicitly checks both `vm_end > addr` AND `vm_start <= addr`, i.e., "addr is actually inside this VMA," not just "VMA ends after addr." That's because the cache has no fallback story for "close but not quite" — it's a binary hit or miss.

### The Tree Walk — Mechanically Matches Your Red-Black Tree Notes

```c
if (vma_tmp->vm_end > addr)
    vma = vma_tmp;        // candidate — remember it, look left for something tighter
    if (vma_tmp->vm_start <= addr) break;  // found it exactly, stop
else
    rb_node = rb_node->rb_right;  // not even ending past addr, go right
```

Standard binary search shape: go left when this node already overshoots `addr` (looking for a tighter/earlier match), go right when this node doesn't even reach `addr` yet. The "found it" condition is exactly `vm_start <= addr < vm_end` — `addr` actually inside this VMA's interval.

### `find_vma_prev()` and `find_vma_intersection()` — thin wrappers, skip deep attention

- `find_vma_prev()` — same as `find_vma()`, but also hands back the preceding VMA via an out-parameter. Useful when you're about to *insert* a new VMA and need to know its neighbors (you'll likely see this used in `mmap()`'s implementation).
- `find_vma_intersection()` — "does any VMA overlap this *range*" rather than "does any VMA cover this *point*." Built trivially on top of `find_vma()` — if the VMA it finds starts after your range ends, there's no overlap, return NULL.

Neither introduces new mechanics — both are just `find_vma()` with slightly different framing for different callers.

## `mmap()` / `do_mmap()` — Creating an Address Interval

### What `do_mmap()` Actually Does

The kernel-side implementation of `mmap()` — this is the function that, given everything you've already studied, just wires it all together:

```
do_mmap(file, addr, len, prot, flag, offset)
  1. Validate parameters
  2. Find a suitable free interval in the address space
  3. Try to MERGE with an adjacent VMA of the same permissions (if possible)
     — otherwise —
     Allocate a fresh vm_area_struct from vm_area_cachep (slab cache — same pattern as task_struct_cachep)
  4. Link it into BOTH the linked list and red-black tree via vma_link()
  5. Update mm->total_vm
  6. Return the starting address of the new interval
```

Worth noting explicitly: **`do_mmap()` doesn't always create a new VMA.** If your new mapping is adjacent to an existing one and shares the same permissions, the kernel just *extends* the existing VMA instead of creating a second one. This is a quiet but sensible optimization — avoids VMA-list/tree bloat when a process repeatedly maps small adjacent regions with identical permissions (e.g. growing a heap-like region piece by piece).

### `prot` → `vm_flags` — The Direct Mapping You Already Know

```
PROT_READ   → VM_READ
PROT_WRITE  → VM_WRITE
PROT_EXEC   → VM_EXEC
PROT_NONE   → no access
```

This is just the userspace-facing names for the exact same `VM_READ`/`VM_WRITE`/`VM_EXEC` flags from yesterday's notes — `prot` is literally the argument you pass to `mmap()` that becomes those VMA flags.

### `flags` — Where Your Article's Vocabulary Becomes Literal Code

This is the satisfying part: every term your article used narratively now has a concrete flag name.

| Flag | Connects to |
|---|---|
| `MAP_SHARED` | → `VM_SHARED` — your article's "writes visible to other mappers" |
| `MAP_PRIVATE` | → unset `VM_SHARED` — your article's COW-on-write private mapping |
| `MAP_ANONYMOUS` | → no file backing — your article's anonymous memory (heap/stack-style) |
| `MAP_FIXED` | → forces the mapping to start exactly at `addr`, no searching for free space |
| `MAP_GROWSDOWN` | → `VM_GROWSDOWN` — yesterday's stack-growth flag, now visible as the actual `mmap()` flag the kernel uses internally when setting up the stack VMA |
| `MAP_POPULATE` | → **prefault** the page tables immediately, rather than waiting for the first access to fault. This is the explicit opt-out of demand paging's laziness — useful when you want to pay the fault cost upfront instead of on first touch |
| `MAP_LOCKED` | → `VM_LOCKED` — pages pinned, won't be swapped. This is the kernel-internal flag behind userspace's `mlock()`/pinned-memory story from your article (the GPU DMA case) |
| `MAP_NORESERVE` | → skip the overcommit accounting check for this mapping — directly related to your article's overcommit aside |


### MAP_NORESERVE

Skip commit reservation for this mapping. The VMA is still created immediately and pages are still allocated lazily on page faults, but the kernel does not promise up front that enough RAM+swap exists for the entire mapping. If memory runs out later when pages are actually faulted in, allocation may fail or the OOM killer may intervene.

> So without MAP_NORESERVE linux doesn't commit anything blindly? it keeps accounting? but this seems to defeat the purpose of lazy allocation?

#### Overcommit Policies of Linux

There is a sysctl:

```bash
cat /proc/sys/vm/overcommit_memory
```
 You’ll probably see: 0


##### Mode 0 (Default): Heuristic overcommit

Linux says: “Realistically, nobody touches all the memory they ask for.”

It keeps a rough heuristic instead of a strict limit. So `malloc(100 GB);` often succeeds on an 8 GB laptop.

##### Mode 1: Always overcommit

Linux keeps no accounting at all, and every allocation succeeds lazily. If reality catches up later… it spins up OOM killer and starts reclaiming memory.

##### Mode 2: Strict accounting

This is the behavior you were imagining. Linux says: `Commit limit = 16 GB`. Once committed reaches 16 GB future allocations fail immediately.

#### Then What Does MAP_NORESERVE Mean?

It mainly matters in strict accounting. 

Suppose in mode 2. Process A asks for `mmap(10 GB)`. Linux would normally increase committed memory to `10 GB`. Now if Process B asks `mmap(10 GB)` it fails. But with `MAP_NORESERVE` Process A says “Don’t count me.” So Committed = 0 even though the VMA exists. Now Process B succeeds. Later if Process a actually needs that memory Linux will invoke OOM killer.

### `mmap2()` — a small historical footnote, skip past

```c
void * mmap2(void *start, size_t length,
int prot, int flags, int fd, off_t pgoff)
```

The only thing worth retaining: offset is in **pages**, not bytes, in the modern syscall — this is why you'll sometimes see `pgoff` instead of a byte offset in kernel-level mmap code, and it's purely there to let large files use larger offsets without overflowing a 32-bit byte-offset field.

Imagine you map a file. Suppose you want: offset = 8192 bytes. Old syscall: `mmap(fd, offset=8192)`. The problem was `off_t` was only 32 bits on many systems. Maximum: 2^32 bytes ≈ 4 GB. Large files became impossible.

Kernel noticed something. Offsets are always page-aligned anyway. Nobody writes: offset = 13 bytes because mappings must begin on page boundaries. 

Short one — straightforward mirror of `mmap()`, plus one small but useful new detail.


## `munmap()` / `do_munmap()` — Removing an Address Interval

The complement to yesterday's `do_mmap()`. Same shape, opposite direction:

```
do_munmap(mm, start, len)
  → removes the [start, start+len) interval from the address space
  → returns 0 on success, negative on error
```

### The Detail Worth Keeping: `mmap_sem`

The actual syscall wrapper shows something not explicit in your earlier notes:

```c
mm = current->mm;
down_write(&mm->mmap_sem);
ret = do_munmap(mm, addr, len);
up_write(&mm->mmap_sem);
```

`mmap_sem` is the field you noted as "memory area semaphore" on `mm_struct` back when you first wrote up that struct — here's it actually in use. Any modification to the VMA list/tree (`mmap`/`mm_rb`) needs this lock held in write mode, since `do_munmap()` is mutating both structures. This matters once you start thinking about threads sharing an `mm_struct`: if two threads in the same process called `mmap()`/`munmap()` concurrently without this lock, you'd get a race on the same red-black tree — exactly the kind of corruption your earlier slab/refcount notes have trained you to watch for. `current->mm` is the same idiom from your memory descriptor notes — get the calling process's own address space, lock it, mutate it, unlock.

### One Implicit Detail Worth Noticing

Removing an interval doesn't necessarily mean removing exactly one VMA. If `[start, start+len)` only covers the *middle* of an existing VMA, `do_munmap()` has to **split** that VMA into two — this is the VMA-split scenario your `vm_ops->open()` notes mentioned in passing a couple days ago. Worth connecting now that you're seeing the actual removal path: split happens here, and `open()` is the hook that fires on the resulting fragment(s).

That's the whole function — genuinely simple once `mmap()`'s machinery is understood, since it's just removing the same kind of interval rather than adding one.
