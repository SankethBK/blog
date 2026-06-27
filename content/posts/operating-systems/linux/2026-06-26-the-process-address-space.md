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


