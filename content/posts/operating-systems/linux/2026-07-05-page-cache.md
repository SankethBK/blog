---
title: "The Page Cache and Page Writeback"
date: 2026-07-05
categories: ["operating systems", "linux"]
tags: ["page cache", "writeback"]
---

## The Linux Page Cache & Page Writeback

**The Core Concept:** Disk access is measured in milliseconds; RAM access is measured in nanoseconds. To bridge this massive performance gap, Linux dynamically uses free physical RAM to cache blocks of disk data.

This relies on **temporal locality**: the computing principle that if data is accessed once, it is highly likely to be accessed again very soon.

### 1. Reading from Disk

The cache is granular; Linux caches specific pages of files based on what you actually access, not whole files by default.

* **Cache Hit:** A process requests data $\rightarrow$ the kernel finds it in the Page Cache $\rightarrow$ data is read instantly from RAM.
* **Cache Miss:** The data isn't in RAM $\rightarrow$ the kernel fetches it from the physical disk $\rightarrow$ loads it into the Page Cache $\rightarrow$ returns it to the process.

### 2. Writing to Disk (Write Strategies)

When a process modifies data, the OS must decide how to handle the cache. Linux uses the **Write-back** strategy because it allows the OS to batch multiple disk writes together for massive performance gains.

| Strategy | Mechanism | Pros & Cons | Used by Linux? |
| --- | --- | --- | --- |
| **No-Write** | Writes go directly to disk; cache is invalidated. | Terrible performance. Makes writes expensive. | No |
| **Write-Through** | RAM cache and physical disk are updated simultaneously. | Simple and keeps data perfectly synchronized. Slower. | No |
| **Write-Back** | Writes instantly to RAM. Page is marked **Dirty**. Written to disk later. | Extremely fast. Complex, risks data loss on power failure. | **Yes** |

**What is a "Dirty" Page?**
It is a counter-intuitive term. A dirty page contains the *newest, most accurate* data in RAM. It is called "dirty" because it is temporarily out-of-sync with the older data sitting on the physical disk. **Writeback** is the background process of flushing these dirty pages to disk so they become "clean" again.

---

### 3. Cache Eviction & The Two-List Strategy

When RAM fills up, the kernel must evict clean pages to make room. If it runs out of clean pages, it forces a writeback of dirty pages to create clean ones.

The hardest part of caching is predicting which pages to evict.

#### The Problem with standard LRU (Least Recently Used)

Standard LRU tracks access times and evicts the oldest pages. It works well, but it has a fatal flaw: **Read-Once files**. If a process reads a massive file exactly once, a standard LRU puts all those pages at the top of the "safe" list, evicting genuinely useful data, even though that big file will never be touched again.

#### The Linux Solution: LRU/2 (The Two-List Strategy)

To fix this, Linux splits the cache into two lists managed like queues (new items at the tail, evicted from the head):

1. **The Inactive List:** Pages here are available to be evicted.
2. **The Active List ("Hot"):** Pages here are safe and cannot be evicted.

**The Rule of Promotion:** When a new page is read from disk, it goes to the *Inactive* list. It is only promoted to the *Active* list if it is accessed a **second time** while sitting on the Inactive list.

This perfectly solves the read-once problem: massive files read one time sit on the Inactive list and naturally fall off the head to be evicted, while files you edit continuously stay hot on the Active list.

## The Linux Page Cache

### 1. The Problem: Indexing the Cache

If the kernel wants to cache a file, the simplest approach seems to be indexing it by [`Device Name] + [Block Number]`.

However, this fails in reality for two reasons:

1. **Non-contiguous blocks:** A standard memory page is 4KB, but a disk block might only be 512 bytes. One page in RAM could represent 8 scattered, non-contiguous blocks on the physical hard drive.

The problem is simpler: disk blocks are smaller than pages, so one page spans multiple disk blocks. And those disk blocks might not be physically adjacent on disk (because files get fragmented).

```
ile "notes.txt" on disk:

Page offset 0 (first 4KB of file)
  → needs disk blocks 47, 48, 49, 50, 51, 52, 53, 54
  → but on disk these might be at sectors 1000, 1001, 2500, 2501, 890, 891, 3200, 3201
  → physically scattered, but logically they form the first 4KB of the file
```

So the mapping you need isn't "random blocks within a page" — it's "file offset → which physical disk blocks hold that data, wherever they happen to be on disk." The filesystem (ext4's block allocator) knows this mapping. `address_space` doesn't solve this part — `bmap()` in the operations table does (translates file offset → disk block number), and the filesystem implements it.

What `address_space` solves is different: **"is the page at file offset X already in RAM?"** — so you don't re-read from disk what you already have cached.

2. **Beyond Files:** Linux doesn't just cache files. It caches memory-mapped pages, swap space, and block device data.

Older Unix systems (like SVR4) tied their page cache directly to the `inode` (the file representation). Linux wanted a universally generic cache that could hold any page-based object, whether it was a real file or not.

To achieve this, Linux introduced a new abstraction layer: the `address_space` object.

### 2. The Core Structure: The address_space Object

**The Naming Quirk:** Do not let the name fool you. The `address_space` object has nothing to do with a process's virtual address space. As the author notes, a much better name for this structure would be `physical_pages_of_a_file` or `page_cache_entity`.

The `address_space` object is the physical anchor for cached data. It tracks all the physical pages in RAM that belong to a specific cached object (like a file).

The `address_space` object is created 1 per file at kernel side however many times the file may be open in space space. If 5 processes each `mmap()` the same file twice, you get 10 `vm_area_struct` objects (one per virtual mapping, per process) but only 1 `address_space` (one per file, in physical memory). Many virtual views, one physical reality — same insight as "multiple VAs can point to the same PA" from your memory notes, now expressed as kernel data structures.

#### Fields worth keeping

| Field | Why it matters |
|---|---|
| `host` | Back-pointer to the owning inode. NULL if not inode-backed (e.g. swapper's anonymous pages) |
| `page_tree` | Radix tree of all cached pages for this file — this is the actual data structure the page cache *is*, the thing `find_get_page()` searches |
| `nrpages` | Total pages currently cached for this file |
| `a_ops` | Operations table — the most important field, covered below |
| `i_mmap` | Priority search tree of all VMAs (both shared and private) that map this file — this is the **rmap** for file-backed pages your article described. Given a page cache page, the kernel can find every process's VMA that maps it, via this field |
| `writeback_index` | Where writeback left off — used to resume flushing dirty pages sequentially |

##### i_mmap

**The `i_mmap` ↔ `vm_area_struct` connection is the payoff of everything you've built:**

Because one physical file in the cache might be shared by dozens of processes, the kernel needs a way to find all those processes if the physical page changes. The `address_space` structure contains a field called `i_mmap` — a highly optimized Priority Search Tree that instantly links the single physical cache object back to all the various virtual vm_area_structs using it.

##### page_tree

**The `page_tree` Radix Tree — What It Actually Looks Like**

The radix tree is indexed by file page offset (in pages, not bytes). So for a file:

```
page_tree:
  index 0  →  struct page*  (first 4KB of file, if cached)
  index 1  →  struct page*  (second 4KB of file, if cached)
  index 2  →  NULL          (third 4KB — not cached yet)
  index 5  →  struct page*  (sixth 4KB — cached, maybe because someone read there)
  ...
```

When you call `find_get_page(mapping, index)`, index is just the page number within the file (byte offset ÷ 4096). The radix tree answers: "do I have a struct page already holding the contents of file offset index * 4096?"

**It does not track which disk blocks are inside that page.** That's the filesystem's job (via `bmap()`). The page cache only cares: "I have a 4KB chunk of RAM. It holds the file's bytes from offset X to X+4095. Here it is." The scattered-disk-blocks problem is solved before data enters the page cache — the filesystem reads the right sectors off disk and assembles them into one 4KB page, then hands that page to the page cache. Once it's in RAM, the scattering is irrelevant.

```
Disk (scattered blocks) → filesystem assembles them → one clean 4KB page → page_tree[index]
```

The radix tree's value is sparseness — same reasoning as your 4-level page table discussion. A file might be 10GB but you've only accessed 3 pages of it. A flat array would waste enormous space for the unaccessed pages. The radix tree only allocates nodes for indices that actually have cached pages — same sparsity trick, same O(log n) lookup.

##### writeback_index

**`writeback_index` — Not What It Looks Like**

Your instinct is right that a single index can't track "pages 1, 5, 3 are all dirty." It doesn't try to.

**Dirty page tracking** is a completely separate mechanism — dirty pages go onto the LRU dirty list and are tracked individually per `struct page` via the `PG_dirty` flag on each page. `writeback_index` doesn't track which pages are dirty.

What `writeback_index` tracks is: **"where in the file should the next writeback pass start scanning from?"**


The writeback algorithm works cyclically — it scans the file's pages starting from `writeback_index`, writes whatever dirty pages it finds, and updates `writeback_index` to where it stopped. Next time writeback fires, it continues from there, eventually wrapping around.

```
File pages:    0    1    2    3    4    5    6    7
Dirty:         -    D    -    D    -    D    -    -

writeback_index = 1

First pass:  starts at 1, finds dirty pages 1, 3, 5, writes them, sets writeback_index = 6
Next pass:   starts at 6, finds nothing dirty, wraps to 0, scans again
```

It's a **cursor for the writeback scanner**, not a "list of dirty pages." The dirty pages list is maintained separately. This design avoids always hammering the beginning of large files — by remembering where it left off, writeback distributes I/O more evenly across the whole file over time.

#### The Clean Mental Model

```
address_space answers:  "which pages of this file are currently in RAM?"
page_tree answers:      "give me the RAM page for file offset N"
PG_dirty flag answers:  "is this specific page modified and needs flushing?"
writeback_index tracks: "where should the writeback scanner look next?"
bmap() answers:         "file offset N maps to which physical disk sectors?"
```

### 3. The Operations Table: `address_space_operations`

Just like the Virtual File System (VFS), the Page Cache uses object-oriented C design.

Because the cache can hold data from an ext3 filesystem, an ext4 filesystem, or a swap device, the kernel cannot hardcode how to read and write pages. Instead, the `address_space` object contains a pointer (`a_ops`) to a table of function pointers.

When the kernel needs to read a page, it doesn't care where it comes from. It simply calls `mapping->a_ops->readpage()`. The specific filesystem (like ext3) provides the actual code implementation for that function.


### 4. The Anatomy of Page I/O

Because of this architecture,** all page I/O in Linux is guaranteed to go through the Page Cache**. The cache acts as the ultimate staging ground.


#### The Read Path

When a user process calls `read()`, the kernel executes this exact sequence:

- **Check the Cache:** The kernel calls `find_get_page(mapping, index)`. It looks inside the `address_space` (mapping) at the specific page offset (index).
- **Cache Hit:** If it returns the page, the kernel copies it to user space. Done.
- **Cache Miss:** If it returns `NULL`, the kernel must fetch it from disk:
    - It allocates a new, empty page in RAM: `page_cache_alloc_cold()`.
    - It inserts this new page into the cache's LRU tracking list: `add_to_page_cache_lru()`.
    - It commands the specific filesystem to fill that page with disk data: `mapping->a_ops->readpage()`.

```c
// 1. Check page cache
page = find_get_page(mapping, index);

// 2. Cache miss — allocate a new page
page = page_cache_alloc_cold(mapping);
add_to_page_cache_lru(page, mapping, index, GFP_KERNEL);

// 3. Read from disk into the page cache
mapping->a_ops->readpage(file, page);
```

`readpage()` is the filesystem-specific hook — ext4 has its own implementation in `fs/ext4/inode.c` that knows how to translate a file offset into actual disk blocks and issue the I/O. The page cache machinery is generic; only this one function pointer is filesystem-specific.

Notice `add_to_page_cache_lru()` — the page goes onto the LRU immediately on allocation, which directly feeds into the active/inactive LRU reclaim your article described. Not a separate step — it's built into the cache insertion.


##### The Two Read Paths

Before understanding the write paths, let's see what happens when we open the file with `mmap` and `read`.

**Reading a file normally (`read()`)**

Suppose your program does

```c
char buf[4096];

read(fd, buf, 4096);
```

We're asking the kernel **“Copy the file’s contents into MY buffer.”**

That “my buffer” part is extremely important.

Your process already owns

```
Process

Stack
Heap
buf[4096]
```

The kernel’s job is to fill it.

The flow is

```
            Disk
              │
              ▼
        Page Cache
              │
              ▼
        User Buffer
```

The final destination is **`buf`**.

which belongs to our process.

Visually

```
           Kernel

        Page Cache
      +------------+
      | hello      |
      +------------+
            │
            │ memcpy()
            ▼
        Userspace

      +------------+
buf ->| hello      |
      +------------+
```

Notice something: There are now two copies. One in the page cache. One in your buffer.

**mmap()**

Now suppose instead

```c
char *p = mmap(...);
```

You’re NOT saying “Copy file into my buffer.”

You’re saying something much stronger. You’re saying “Pretend this file IS my memory.” That’s a completely different request.


The kernel responds by creating

```
VMA
↓
Page Table
↓
Page Cache
```

No user buffer exists.

Initially `p` points to… Nothing. The pages aren’t even allocated yet.

When you first do 

```c
printf("%c", p[0]);
```

Page fault. Kernel loads the page from disk. Builds a PTE.

Now

```
Process VA

0x7f....

     │
     ▼

Page Cache Page
```

Notice There is no `memcpy()`. The page itself became your memory.

**The page cache exists independently of `read()` or `mmap()`. Both access the same `address_space` and the same cached pages. The difference is that `read()` copies data between the page cache and a userspace buffer, whereas `mmap()` maps the page cache pages directly into the process’s virtual address space, eliminating the copy.**

#### The Write Path

Writes are slightly more complex depending on how the data is being accessed:

- **For Memory-Mapped (`mmap`) files:**
    The process modifies the memory directly in RAM. The Virtual Memory system catches this and calls `SetPageDirty(page)`. The kernel's background writeback threads will eventually notice the dirty flag and flush it to disk via `writepage()`.
- For Standard File Writes (`write()` system call):
  - **Locate/Allocate:** The kernel finds the page in the cache, or allocates a new one if it isn't there (`__grab_cache_page()`).
  - Prepare: It tells the filesystem to prepare the disk for incoming data (`a_ops->prepare_write()` / `write_begin`).
  - **Copy:** Data is safely copied from the user's application buffer into the kernel's Page Cache (`filemap_copy_from_user()`).
  - **Commit:** The kernel tells the filesystem the data is ready to be written to the physical disk (`a_ops->commit_write()` / `write_end`).

Two cases, different triggers:

**File mappings (mmap() writes):**

```c
SetPageDirty(page);   // just mark it, actual write happens later
// ... kernel flushes via writepage() asynchronously
```

**Direct file writes (write() syscall):**

```c
page = __grab_cache_page(mapping, index, ...);
a_ops->prepare_write(file, page, offset, offset+bytes);
filemap_copy_from_user(page, offset, buf, bytes);  // copy from userspace
a_ops->commit_write(file, page, offset, offset+bytes);
```

The write always goes through the page cache first — data lands in the page cache, page is marked dirty, and writeback flushes it to disk later. This is why closing without `fsync()` can lose writes if the system crashes — the data made it to the page cache but writeback hadn't fired yet.

##### Why the Two Write Path Differs?

Similar to two read paths, while writing via `mmap` writes go directly to page caches, kernel marks them dirty and they're eventually flushed. 

But when file is opened via `open`, writes will first go to userspace buffer and then copied to page caches via `memcpy`, then its the same process. 

#### Other operations — brief

| Operation | One-liner |
|---|---|
| `writepages()` | Batch writeback of multiple dirty pages — more efficient than one-at-a-time `writepage()` |
| `set_page_dirty()` | Override for marking a page dirty (some filesystems need special handling) |
| `invalidatepage()` | Called when a page is being removed from the cache (e.g. file truncation) |
| `direct_IO()` | Handles `O_DIRECT` reads/writes — **bypasses the page cache entirely**, the case your article's aside covered for database buffer pools |
| `bmap()` | Maps a file offset to a physical block number — the bridge between "page at offset X" and "disk block N" |
| `migratepage()` | Move a page to a different physical frame (used by NUMA balancing and memory compaction) |

### Bypassing the Page Cache

In the Linux world, this "secret passage" around the page cache is called **Direct I/O**, and developers trigger it by passing the `O_DIRECT` flag when they open a file.

When you use `O_DIRECT`, the kernel's entire page cache apparatus steps aside. The data travels directly from the user-space application's memory buffer straight to the physical disk controller, completely skipping the RAM staging ground we just learned about.

```c
int fd = open("data.db", O_DIRECT | O_RDWR);
```

you’re telling Linux: “Don’t involve the page cache. I’ll manage caching myself.”

The path becomes:

```
read()

Userspace Buffer
      ▲
      │
      │
     Disk
```

or for writes:

```
Userspace Buffer
      │
      ▼
     Disk
```
The kernel still performs the I/O, but it does not populate or consult the page cache.

Here is the architectural breakdown of why this exists, who uses it, and the massive catch involved.

#### 1. Who wants to bypass the Page Cache?

If the page cache is so fast, why ignore it? The answer is almost always Database Management Systems (DBMS) like PostgreSQL, Oracle, or MySQL.

Databases are incredibly complex and generally believe they are smarter than the operating system when it comes to their own data.

- **The Double Caching Problem:** A database typically allocates a massive chunk of RAM to maintain its own internal cache (e.g., PostgreSQL's "shared buffers"). If Linux also caches that same file data in the OS Page Cache, the system wastes gigabytes of physical RAM storing the exact same data twice.

- **Algorithmic Superiority:** Remember how Linux uses the LRU/2 strategy because it has to guess what you will read next? A database query planner doesn't have to guess—it actually knows what it will read next based on the SQL query execution plan. It wants to run its own highly tuned cache eviction algorithms without Linux's general-purpose cache interfering.

- No address_space lookup.
- No page cache insertion.
- No dirty page.
- No writeback daemon.

But there are tradeoffs

Because Linux isn’t helping anymore.

You lose:

- read-ahead
- write coalescing
- caching
- delayed writeback

#### 2. The Catch: Brutal Hardware Constraints

Bypassing the kernel's memory management means you also lose the kernel's help. Using `O_DIRECT` is notoriously difficult because you must interface much more closely with the raw hardware.

If you want to write to the disk directly, your data must be strictly block-aligned.

- Your memory buffer in RAM must start at an address that is an exact multiple of the disk's logical block size (usually 512 bytes or 4KB).
- The size of the data payload you are writing must be an exact multiple of that block size.
- The destination offset on the physical disk must also be a multiple of the block size.

If you are off by a single byte, the hardware simply rejects the I/O, and your read/write fails. You can no longer just say "write 14 bytes here."

#### 3. The Creator's Regret

As a piece of kernel lore, Linus Torvalds famously hates `O_DIRECT`. He has publicly called the interface "brain-damaged."

His argument is that applications shouldn't bypass the OS entirely. Instead, they should use system calls like `posix_fadvise()` to give the kernel "hints" about their caching needs (e.g., telling the kernel, "I am about to read this 10 GB file exactly once, please drop it from the cache immediately after").

Despite Torvalds's dislike of it, `O_DIRECT` remains completely essential for modern database architecture to achieve maximum I/O performance.

Here are your detailed, architectural notes on the Buffer Cache.

To really grasp this, you have to remember the fundamental mismatch between RAM and Hard Drives: **RAM thinks in "Pages" (usually 4KB), but Hardware Disks think in "Blocks" (often 512 bytes).**

Here is how the kernel bridges that gap.


## The Buffer Cache

**The Core Concept:** A "buffer" is simply the in-memory representation of a single physical disk block. If a disk block is 512 bytes, its corresponding buffer in RAM is 512 bytes.

Buffers act as translation descriptors: they map a specific, low-level disk block to a specific location inside a standard 4KB RAM page.

### 1. The Historical Nightmare (Pre-Linux 2.4)

In older versions of Linux, the kernel maintained two completely separate caches:

1. **The Page Cache:** Cached file data (operating on RAM pages).
2. **The Buffer Cache:** Cached physical disk blocks (operating on raw disk sectors).

**The flaw:** If a user process read a file, the raw blocks were pulled off the disk into the Buffer Cache, and then assembled into file data in the Page Cache. A single piece of data existed in RAM **twice**.
This caused two massive problems:

* **Memory Waste:** Duplicate data ate up precious physical RAM.
* **Synchronization Hell:** If a process modified the file in the Page Cache, the kernel had to burn CPU cycles ensuring the raw block in the Buffer Cache was also updated, otherwise the disk would write corrupted data.

### 2. The Modern Solution: The Unified Cache

Starting in Linux 2.4, the developers merged them. **Today, there is no separate Buffer Cache.** It is entirely absorbed by the Page Cache.

Here is how the modern architecture works:

* The kernel still uses buffers, but purely as **descriptors** (metadata).
* Instead of holding duplicate data, the buffer simply points to an offset *inside* an existing page in the Page Cache.
* If a 4KB page holds file data, and the underlying disk uses 512-byte blocks, that single page will have exactly **8 buffers** associated with it, mapping out exactly where those 8 blocks live on the physical disk.

### 3. When are Buffers actually used?

While normal file reads/writes just use the Page Cache, the kernel still needs to perform raw **Block I/O operations**—manipulating a single disk block at a time without caring about "files."

The most common use case is reading filesystem metadata, like **inodes**.
When the kernel needs to look up file permissions or file sizes, it uses a low-level function called `bread()` (Block Read) to fetch that exact block off the disk. The kernel wraps that block in a buffer, tucks it into a page, and caches it in the unified Page Cache so the next inode lookup is instantaneous.

Here are your detailed, architectural notes on the Flusher Threads and how Linux handles dirty memory.


## The Flusher Threads (Page Writeback Mechanics)

**The Core Concept:** When a process writes data, it is written to the Page Cache in RAM and marked as **dirty**. Because RAM is volatile, this dirty data must eventually be synchronized with the physical backing store (the hard drive). This synchronization process is called **Writeback**, and it is executed by a gang (a parallel-operating group) of kernel threads called the **Flusher Threads**.

The kernel triggers Writeback in exactly three situations.

### Trigger 1: Memory Pressure (Low Free Memory)

When the system starts running out of RAM, it needs to evict pages. However, the kernel can *only* evict clean pages.

* **The Mechanism:** When dirty memory exceeds a strict percentage of total memory (`dirty_background_ratio`), the kernel calls `wakeup_flusher_threads()`.
* **The Execution:** The threads run `bdi_writeback_all()` to aggressively flush dirty pages to disk.
* **The Stop Condition:** They do not stop until either a specified minimum number of pages are written, or the dirty memory drops safely below the threshold again.

### Trigger 2: Data Age (The Time Limit)

Even if you have plenty of free RAM, dirty data cannot sit in memory forever. If the power goes out, any data not written to the disk is permanently lost.

* **The Mechanism:** A kernel timer routinely wakes up the flusher threads (determined by `dirty_writeback_interval`).
* **The Execution:** The threads run `wb_writeback()`. They scan the cache and write out *only* the pages that have been dirty for longer than the safety limit (`dirty_expire_interval`).
* **The Stop Condition:** The threads go back to sleep until the timer goes off again.

### Trigger 3: On-Demand (User Space Request)

A user-space application doesn't want to wait for the kernel's timers. It wants a guarantee that its data is safe *right now*.

* **The Mechanism:** The application calls the `sync()` or `fsync()` system calls.
* **The Execution:** The kernel immediately forces the flusher threads to write that specific data to disk before returning control to the application.

---

## The Writeback Tunables (Sysctls)

System administrators can heavily modify how the kernel handles dirty memory by tweaking values in `/proc/sys/vm/`.

| Variable | What it controls |
| --- | --- |
| `dirty_background_ratio` | **(The Flusher Trigger):** % of total memory that can become dirty before the *background flusher threads* wake up to start writing. |
| `dirty_ratio` | **(The Process Trigger):** % of total memory that can become dirty before the *process generating the writes* is forced to stop and write the data itself. |
| `dirty_expire_interval` | **(The Age Limit):** Time (in ms) a page can sit dirty before it is legally required to be flushed on the next timer tick. |
| `dirty_writeback_interval` | **(The Timer):** Time (in ms) between regular flusher thread wakeups. |

---

## Laptop Mode (Battery Optimization)

Hard drives (especially spinning mechanical disks) consume massive amounts of battery power when they spin up from a sleep state. **Laptop Mode** is a specialized writeback strategy designed to keep the disk asleep as long as possible.

**How it changes the rules:**
Normally, flusher threads wake up on a strict timer to write out old pages, which forces the disk to spin up constantly.
When Laptop Mode is enabled (`/proc/sys/vm/laptop_mode = 1`):

1. Administrators massively increase the `dirty_expire_interval` (e.g., to 10 minutes), allowing dirty data to sit in RAM much longer.
2. If the disk *does* spin up for any unrelated reason (e.g., you open a new application, causing a cache miss and a disk read), the flusher threads **piggyback** on that I/O.
3. They instantly flush *all* dirty buffers to the disk while it is already awake.

**The Trade-off:** You gain significantly longer battery life by minimizing disk spin-ups, but you take on a massive risk of data loss. If the system crashes, you could lose up to 10 minutes of written data.

Here are your architectural notes on the history and evolution of Linux writeback threads.

The evolution of these threads is a perfect case study in how kernel architecture has had to adapt to changing hardware realities—specifically, moving away from low-level buffers toward memory pages, and solving the bottleneck of modern, congested hard drives.

## The Evolution of Writeback Threads

* Pre-2.6: bdflush and kupdated
In early kernels, writeback duties were split between two separate single-thread systems:

* **`bdflush` (Memory Pressure):** Woke up only when free RAM dropped below a specific threshold. There was only one global daemon.
* **`kupdated` (Time Limit):** Woke up periodically to flush old, dirty data to prevent data loss.

**The Architectural Limit:** `bdflush` was strictly **buffer-based**. It managed and wrote back individual low-level disk buffers rather than whole memory pages, which was complex and inefficient as the unified Page Cache became the standard.


* Early 2.6: pdflush (Page Dirty Flush)
The kernel merged the duties of `bdflush` and `kupdated` into a single, dynamic pool of threads (usually 2 to 8, scaling based on system I/O load).

* **The Upgrade:** It shifted from buffer-based to **page-based** writebacks. Writing entire pages at once was significantly easier to manage and align with the Page Cache.
* **The Fatal Flaw:** The thread pool was **global**. The threads were not tied to any specific disk. If a system had four hard drives and one of them became heavily congested, all the `pdflush` threads could get stuck waiting on that one slow disk, completely stalling writebacks for the three healthy disks.


* Linux 2.6.32+: Modern Flusher Threads
To solve the global congestion bottleneck of `pdflush`, Linux moved to a **per-spindle (per-disk)** architecture.

Instead of a global pool, the kernel now spins up dedicated flusher threads for *each individual physical disk* (each "spindle").

**The Result:** I/O congestion is completely isolated. A slow, congested USB drive will only block its own dedicated flusher thread, allowing the main NVMe or SSD flusher threads to continue writing back pages synchronously at maximum speed.

### Avoiding Disk Congestion

**The Core Concept:** Processor speed scales exponentially (Moore’s Law), but physical hard drive throughput scales at a crawl. Because disks are the slowest component in the system, their I/O request queues fill up rapidly, causing **congestion**. If the kernel's memory management isn't carefully designed, the entire system can stall waiting on a single slow disk queue.

Here is how the kernel evolved to keep multiple disks fully saturated without blocking.

#### The Single-Threaded Bottleneck (`bdflush`)

In early kernels, a single `bdflush` thread handled all writebacks.

* **The Flaw:** If the system had three hard drives, and Disk A became congested, the `bdflush` thread would get stuck waiting in Disk A's queue.
* **The Result:** Even if Disks B and C were completely idle and ready to accept data, they received nothing. A single congested disk bottlenecked the entire machine's I/O.

#### The "Congestion Avoidance" Hack (`pdflush`)

To fix this, Linux introduced `pdflush`, a dynamic pool of multiple global threads. This allowed different threads to write to different disks simultaneously.

* **The New Threat:** What if all the global `pdflush` threads accidentally tried to write to Disk A at the same time? They would all get stuck in the same congested queue.
* **The Workaround:** The kernel engineers introduced **Congestion Avoidance**. The `pdflush` threads actively monitored the device queues. If a queue looked busy, the thread would artificially back off and look for a different disk's dirty pages to write instead.
* **The Flaw:** Congestion avoidance was a complex, imperfect hack. Because it actively avoided busy disks, a heavily congested disk could end up being ignored for dangerously long periods (a phenomenon called **starvation**).

#### The Modern Solution: Per-Spindle Flushing (Linux 2.6.32+)

Kernel developers realized that global threads were the wrong abstraction. Modern Linux solves congestion by associating threads directly with the physical block devices (the "spindles").

* **The Mechanism:** Every block device gets its own dedicated flusher thread. Thread A pulls exclusively from Disk A's dirty list; Thread B pulls exclusively from Disk B's dirty list.
* **Why this is brilliant:** It completely eliminates the need for complex Congestion Avoidance algorithms in the software layer.
* **The Result:** Writebacks are entirely synchronous and strictly isolated. If Disk A is severely congested, Thread A blocks, but Thread B continues hammering Disk B at maximum throughput. Starvation is eliminated, fairness is guaranteed, and the OS can saturate an unlimited number of disks in parallel.


#### Summary of Writeback Architectures

| Architecture | Thread Mapping | Handles Congestion By | Primary Flaw |
| --- | --- | --- | --- |
| **`bdflush`** | 1 Global Thread | Getting stuck (Blocking) | Wastes idle disks. |
| **`pdflush`** | 2-8 Global Threads | Software Congestion Avoidance | Risks starving busy disks. |
| **Flusher Threads** | 1 per Block Device | Hardware Isolation (Per-queue) | None (Current standard). |