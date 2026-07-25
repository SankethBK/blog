---
title: "Kernel Lab 1: Observing Process and VFS Structs"
date: 2026-07-16
categories: ["operating systems", "linux"]
tags: ["process", "task_struct", "mm_struct"]
---

# Kernel Lab 1: Observing Process and VFS Structs

![Kernel Data structures Map](/images/kernel-data-structures-summary.png)

## Primer on Kernel Data Structures

### 1. Process & Memory Management (MM)


| Struct | Description | Noteworthy Fields |
| --- | --- | --- |
| `task_struct` | The kernel's representation of a thread/process. | `mm` (memory space), `files` (open files), `fs` (cwd/root), `pid`, `comm` (name). |
| `mm_struct` | The descriptor for an entire memory address space. | `mm_mt` (the Maple Tree of VMAs), `pgd` (page global directory for hardware MMU). |
| `vm_area_struct` | A contiguous range of virtual memory with shared permissions (a VMA). | `vm_start`, `vm_end`, `vm_file` (if it's a memory-mapped file), `vm_flags`. |

### 2. Virtual File System (VFS)

The VFS bridges the gap between user-space file operations (like `open()` and `read()`) and the underlying hardware.

| Struct | Description | Noteworthy Fields |
| --- | --- | --- |
| `files_struct` | The per-process table of all open files. | `fdt` (the file descriptor table arrays linking `fd` ints to `file` structs). |
| `fs_struct` | Tracks the process's current filesystem location. | `pwd` (current working dir), `root` (root dir for the process). |
| `file` | Represents an *open* file instance. Created on `open()`. | `f_pos` (current read/write offset), `f_path` (points to dentry), `f_mapping`. |
| `dentry` | Directory entry. Maps a path name component to an inode. | `d_name`, `d_parent`, `d_inode`. Held in the dcache. |
| `inode` | The actual file metadata on disk (permissions, size). | `i_size`, `i_mapping`, `i_sb` (pointer to filesystem instance). |
| `super_block` | Represents a mounted filesystem instance. | `s_magic` (fs type), `s_root` (root dentry of the mount). |

### 3. The Page Cache Bridge

The Page Cache is how the kernel avoids hitting the slow disk on every read. It caches file data in memory.

| Struct | Description | Noteworthy Fields |
| --- | --- | --- |
| `address_space` | The crucial link between a VFS `inode` and MM pages. | `host` (owning inode), `i_pages` (an XArray holding the cached folios/pages), `a_ops` (methods like `read_folio`). |
| `folio` / `page` | The physical memory holding the cached file data. | `mapping` (points back to address_space), `index` (the offset within the file). |

![Kernel data Structures Map](/images/linux-kernel-data-structures-1.svg)

## Experiment 1: Observing Lazy allocation 

```c
// mm_lab1.c
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#define SMALL_SIZE (8 * 1024)                     // 8 KB
#define LARGE_SIZE (256UL * 1024 * 1024)          // 256 MB

int main(void)
{
    printf("\n========== State 1 ==========\n");
    printf("Program just started.\n");
    printf("Observe task_struct -> mm_struct.\n");
    printf("Note the initial map_count, brk, start_brk, total_vm, etc.\n");
    getchar();

    /* --------------------------------------------------------- */
    /* Small malloc (typically served from the heap via brk())   */
    /* --------------------------------------------------------- */

    void *small = malloc(SMALL_SIZE);

    printf("\n========== State 2 ==========\n");
    printf("Small malloc(%d KB) returned %p\n",
           SMALL_SIZE / 1024, small);
    printf("Observe whether map_count changed.\n");
    printf("Small allocations are typically served from the existing heap VMA.\n");
    printf("No pages have been touched yet.\n");
    getchar();

    /* --------------------------------------------------------- */
    /* Large malloc (typically served using mmap())              */
    /* --------------------------------------------------------- */

    void *large = malloc(LARGE_SIZE);

    printf("\n========== State 3 ==========\n");
    printf("Large malloc(%lu MB) returned %p\n",
           LARGE_SIZE / (1024 * 1024), large);
    printf("Observe that a new anonymous VMA usually appears.\n");
    printf("malloc() often uses mmap() internally for large allocations.\n");
    printf("Still, no pages have been touched yet.\n");
    getchar();

    /* --------------------------------------------------------- */
    /* First page fault                                          */
    /* --------------------------------------------------------- */

    ((char *)large)[0] = 1;

    printf("\n========== State 4 ==========\n");
    printf("Touched the FIRST byte.\n");
    printf("This should have caused the first page fault.\n");
    printf("Only one page should have been allocated.\n");
    getchar();

    /* --------------------------------------------------------- */
    /* Last page fault                                           */
    /* --------------------------------------------------------- */

    ((char *)large)[LARGE_SIZE - 1] = 2;

    printf("\n========== State 5 ==========\n");
    printf("Touched the LAST byte.\n");
    printf("Another page fault should have occurred.\n");
    getchar();

    /* --------------------------------------------------------- */
    /* Explicit anonymous mmap                                   */
    /* --------------------------------------------------------- */

    void *region = mmap(NULL,
                        LARGE_SIZE,
                        PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS,
                        -1,
                        0);

    if (region == MAP_FAILED) {
        perror("mmap");
        return 1;
    }

    printf("\n========== State 6 ==========\n");
    printf("Anonymous mmap() returned %p\n", region);
    printf("Observe that map_count increased.\n");
    printf("No pages have been touched yet.\n");
    getchar();

    /* --------------------------------------------------------- */
    /* First touch of mmap region                                */
    /* --------------------------------------------------------- */

    ((char *)region)[0] = 1;

    printf("\n========== State 7 ==========\n");
    printf("Touched first byte of mmap() region.\n");
    printf("This should allocate the first anonymous page.\n");
    getchar();

    /* --------------------------------------------------------- */
    /* Remove mmap region                                        */
    /* --------------------------------------------------------- */

    munmap(region, LARGE_SIZE);

    printf("\n========== State 8 ==========\n");
    printf("munmap() completed.\n");
    printf("Observe that the anonymous VMA disappeared.\n");
    getchar();

    /* --------------------------------------------------------- */
    /* Free large allocation                                     */
    /* --------------------------------------------------------- */

    free(large);

    printf("\n========== State 9 ==========\n");
    printf("Freed the large malloc allocation.\n");
    printf("If it was mmap-backed, its VMA should disappear now.\n");
    getchar();

    /* --------------------------------------------------------- */
    /* Cleanup                                                   */
    /* --------------------------------------------------------- */

    free(small);

    printf("\n========== Done ==========\n");
    getchar();

    return 0;
}
```

### What's the point of using mmap without any file backing?

Calling `mmap` on "nothing" might feel like a weird hack if you view `mmap` solely as a file-mapping utility. But in reality, **this exact line of code is how operating systems allocate raw, clean memory.**

When you run:

```c
void *region = mmap(NULL, SIZE, PROT_READ | PROT_WRITE, 
                    MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);

```

You are asking the kernel: *"Don't link this to any file on disk (`-1`). Just reserve a region of clean, zeroed-out virtual address space for me, and give me a pointer to it."*

In fact, whenever you call `malloc()` in C for large allocations (typically $\ge 128 \text{ KB}$ by default in `glibc`), **`malloc` turns around and calls this exact `mmap` line under the hood.**

Here is what you actually achieve by creating a raw VMA like this:

---

#### 1. You Avoid the `brk` Heap Fragmentation Trap

Traditionally, a process expands its heap memory sequentially using the `brk()` / `sbrk()` system calls. The heap grows as one contiguous block.

* **The `brk` Problem:** If you allocate 100 MB on the heap using `brk`, and then allocate a tiny 4 KB chunk right above it, you **cannot give the 100 MB back to the OS** until that top 4 KB chunk is freed. The memory gets trapped on the heap.
* **The Anonymous `mmap` Solution:** `mmap` creates an isolated, standalone `vm_area_struct` (VMA) anywhere in the process's address space. When you are done with that 100 MB buffer, you call `munmap(region, SIZE)`, and the kernel instantly destroys that VMA and returns the physical pages straight back to the OS—no matter what else your program allocated before or after it.

---

#### 2. Instant Allocation via "Zero-Fill-on-Demand"

If you request a 10 GB buffer with `mmap(MAP_ANONYMOUS)`, the call returns almost instantly and consumes virtually zero physical RAM.

Why? Because creating a VMA only updates the kernel's internal page-tracking structures (the Maple Tree we discussed earlier).

* The kernel points all virtual pages in that new VMA to a **single global Zero Page** in physical RAM, marked read-only.
* The moment your code actually writes to a page in `region`, a Page Fault triggers. The kernel intercepts it, allocates a single real 4 KB frame of physical RAM, zeros it, and updates your page table entry.

You get precise, hardware-enforced lazy memory allocation out of the box.

---

#### 3. Page Alignment & Custom Allocator Foundations

Functions like `malloc()` overheads can fragment memory when allocating huge buffers for databases, game engines, or matrix math.

Anonymous `mmap` allocations are **always strictly aligned to page boundaries** (typically 4 KB or 2 MB huge pages). If you are building a custom Arena Allocator or a JIT compiler that needs to mark pages as executable (`PROT_EXEC`) later via `mprotect()`, anonymous `mmap` is the standard tool to get raw, aligned memory direct from the hardware layer.

---

#### 4. IPC Without Touching the Disk

If you change `MAP_PRIVATE` to `MAP_SHARED` while keeping `MAP_ANONYMOUS`:

```c
void *shared_ram = mmap(NULL, SIZE, PROT_READ | PROT_WRITE, 
                        MAP_SHARED | MAP_ANONYMOUS, -1, 0);

```

Now, if your process calls `fork()`, both the parent and child processes will read and write to the **exact same physical RAM pages** without ever needing to create or clean up a temporary file on a disk partition.

---

#### Summary: How `mmap` Roles Split

| Feature | File-Backed `mmap` | Anonymous `mmap` (`MAP_ANONYMOUS`) |
| --- | --- | --- |
| **Backing Store** | Disk File / Storage Device | Swap Space (or pure RAM) |
| **Primary Use Case** | Fast file I/O, shared libraries (`.so`) | Raw memory allocation, custom allocators |
| **Paging Behavior** | Flushed to disk on eviction | Written to swap space on memory pressure |
| **Initial Content** | The file's byte contents | Guaranteed to be all zeroes |

So far from being unethical, anonymous `mmap` is the foundational primitive that powers modern user-space memory management!

### Observing the task_struct

First let's statically compile the program, as kernel doesn't have full blown dynamic loader. 

```sh
gcc -static mm_lab1.c -o mm_lab1
```

#### 1. Get the process's task_struct's address

```sh
(gdb) lx-ps
      TASK          PID    COMM
0xffffffff82a0e900   0   swapper/0
0xffff888003988000   1   sh
0xffff888003988ec0   2   kthreadd
0xffff888003989d80   3   pool_workqueue_
0xffff88800398ac40   4   kworker/R-rcu_g
0xffff88800398bb00   5   kworker/R-sync_
0xffff88800398c9c0   6   kworker/R-kvfre
0xffff88800398d880   7   kworker/R-slub_
0xffff88800398e740   8   kworker/R-netns
0xffff888003998000   9   kworker/0:0
0xffff888003998ec0  10   kworker/0:0H
0xffff88800399ac40  12   kworker/u4:0
0xffff88800399bb00  13   kworker/R-mm_pe
0xffff88800399c9c0  14   ksoftirqd/0
...
0xffff88800404d880  47   kworker/R-mld
0xffff88800404e740  48   kworker/R-ipv6_
0xffff888004359d80  57   sh
0xffff888004358000  59   mm_lab1
```

The lx-ps command is a GDB Python script provided in the Linux kernel source tree (scripts/gdb/linux/tasks.py).

It works by starting at the global root task (init_task) and walking the kernel's circular doubly-linked list of processes using the tasks member:

```
init_task (swapper/0)
   └───► tasks.next ──► struct task_struct (PID 1: sh)
                            └───► tasks.next ──► struct task_struct (PID 2: kthreadd)
                                                     └───► ... ──► (PID 61: mm_lab1)
```

#### 2. Print the task_struct

```sh
set $task = (struct task_struct *)0xffff888004358000

(gdb) p *$task
$1 = {thread_info = {flags = 16384, syscall_work = 0, status = 0, cpu = 0}, __state = 1, saved_state = 0, stack = 0xffffc900001d0000, usage = {refs = {counter = 1}}, flags = 4194304,
  ptrace = 0, on_cpu = 0, wake_entry = {llist = {next = 0x0}, {u_flags = 48, a_flags = {counter = 48}}, src = 0, dst = 0}, wakee_flips = 0, wakee_flip_decay_ts = 0, last_wakee = 0x0,
  recent_used_cpu = 0, wake_cpu = 0, on_rq = 0, prio = 120, static_prio = 120, normal_prio = 120, rt_priority = 0, se = {load = {weight = 1048576, inv_weight = 4194304}, run_node = {
      __rb_parent_color = 1, rb_right = 0x0, rb_left = 0x0}, deadline = 2592418359, min_vruntime = 2591935855, min_slice = 700000, group_node = {next = 0xffff8880043580c0,
      prev = 0xffff8880043580c0}, on_rq = 0 '\000', sched_delayed = 0 '\000', rel_deadline = 0 '\000', custom_slice = 0 '\000', exec_start = 851364620257, sum_exec_runtime = 38648232,
    prev_sum_exec_runtime = 38276678, vruntime = 2592307409, {vlag = 0, vprot = 0}, slice = 700000, nr_migrations = 0, depth = 0, parent = 0x0, cfs_rq = 0xffff88807dc28a80, my_q = 0x0,
    runnable_weight = 0, avg = {last_update_time = 851364619264, load_sum = 40847, runnable_sum = 33057136, util_sum = 29157447, period_contrib = 585, load_avg = 882, runnable_avg = 695,
      util_avg = 614, util_est = 2147484262}}, rt = {run_list = {next = 0xffff888004358180, prev = 0xffff888004358180}, timeout = 0, watchdog_stamp = 0, time_slice = 100, on_rq = 0,
    on_list = 0, back = 0x0}, dl = {rb_node = {__rb_parent_color = 18446612682140647856, rb_right = 0x0, rb_left = 0x0}, dl_runtime = 0, dl_deadline = 0, dl_period = 0, dl_bw = 0,
    dl_density = 0, runtime = 0, deadline = 0, flags = 0, dl_throttled = 0, dl_yielded = 0, dl_non_contending = 0, dl_overrun = 0, dl_server = 0, dl_server_active = 0, dl_defer = 0,
    dl_defer_armed = 0, dl_defer_running = 0, dl_server_idle = 0, dl_timer = {node = {node = {__rb_parent_color = 18446612682140647944, rb_right = 0x0, rb_left = 0x0}, expires = 0},
      _softexpires = 0, function = 0xffffffff812e7530 <dl_task_timer>, base = 0xffff88807dc1bb00, state = 0 '\000', is_rel = 0 '\000', is_soft = 0 '\000', is_hard = 1 '\001'},
    inactive_timer = {node = {node = {__rb_parent_color = 18446612682140648008, rb_right = 0x0, rb_left = 0x0}, expires = 0}, _softexpires = 0,
      function = 0xffffffff812e4760 <inactive_task_timer>, base = 0xffff88807dc1bb00, state = 0 '\000', is_rel = 0 '\000', is_soft = 0 '\000', is_hard = 1 '\001'}, rq = 0x0,
    server_has_tasks = 0x0, server_pick_task = 0x0, pi_se = 0xffff8880043581b0}, dl_server = 0x0, sched_class = 0xffffffff82882480 <fair_sched_class>,
  sched_task_group = 0xffffffff83557c00 <root_task_group>, stats = {wait_start = 0, wait_max = 0, wait_count = 0, wait_sum = 0, iowait_count = 0, iowait_sum = 0, sleep_start = 0,
    sleep_max = 0, sum_sleep_runtime = 0, block_start = 0, block_max = 0, sum_block_runtime = 0, exec_max = 0, slice_max = 0, nr_migrations_cold = 0, nr_failed_migrations_affine = 0,
    nr_failed_migrations_running = 0, nr_failed_migrations_hot = 0, nr_forced_migrations = 0, nr_wakeups = 0, nr_wakeups_sync = 0, nr_wakeups_migrate = 0, nr_wakeups_local = 0,
    nr_wakeups_remote = 0, nr_wakeups_affine = 0, nr_wakeups_affine_attempts = 0, nr_wakeups_passive = 0, nr_wakeups_idle = 0}, btrace_seq = 0, policy = 0, max_allowed_capacity = 1024,
  nr_cpus_allowed = 1, cpus_ptr = 0xffff8880043583e8, user_cpus_ptr = 0x0, cpus_mask = {bits = {1}}, migration_pending = 0x0, migration_disabled = 0, migration_flags = 0,
  rcu_read_lock_nesting = 0, rcu_read_unlock_special = {b = {blocked = 0 '\000', need_qs = 0 '\000', exp_hint = 0 '\000', need_mb = 0 '\000'}, s = 0}, rcu_node_entry = {
    next = 0xffff888004358408, prev = 0xffff888004358408}, rcu_blocked_node = 0x0, rcu_tasks_nvcsw = 0, rcu_tasks_holdout = 0 '\000', rcu_tasks_idx = 0 '\000', rcu_tasks_idle_cpu = -1,
  rcu_tasks_holdout_list = {next = 0xffff888004358430, prev = 0xffff888004358430}, rcu_tasks_exit_cpu = 0, rcu_tasks_exit_list = {next = 0xffff888004358448, prev = 0xffff888004358448},
  trc_reader_nesting = 0, trc_ipi_to_cpu = 0, trc_reader_special = {b = {blocked = 0 '\000', need_qs = 0 '\000', exp_hint = 0 '\000', need_mb = 0 '\000'}, s = 0}, trc_holdout_list = {
    next = 0xffff888004358468, prev = 0xffff888004358468}, trc_blkd_node = {next = 0xffff888004358478, prev = 0xffff888004358478}, trc_blkd_cpu = 0, sched_info = {pcount = 139,
    run_delay = 6799048, max_run_delay = 429864, min_run_delay = 13420, last_arrival = 851364248703, last_queued = 0}, tasks = {next = 0xffffffff82a0edc0 <init_task+1216>,
    prev = 0xffff88800435a240}, pushable_tasks = {prio = 140, prio_list = {next = 0xffff8880043584d8, prev = 0xffff8880043584d8}, node_list = {next = 0xffff8880043584e8,
      prev = 0xffff8880043584e8}}, pushable_dl_tasks = {__rb_parent_color = 18446612682140648696, rb_right = 0x0, rb_left = 0x0}, mm = 0xffff88800384c5c0, active_mm = 0xffff88800384c5c0,
  faults_disabled_mapping = 0x0, exit_state = 0, exit_code = 0, exit_signal = 17, pdeath_signal = 0, jobctl = 0, personality = 0, sched_reset_on_fork = 0, sched_contributes_to_load = 0,
  sched_migrated = 0, sched_task_hot = 0, sched_remote_wakeup = 0, sched_rt_mutex = 0, in_execve = 0, in_iowait = 0, restore_sigmask = 0, no_cgroup_migration = 0, frozen = 0,
  use_memdelay = 0, in_eventfd = 0, pasid_activated = 0, reported_split_lock = 0, in_thrashing = 0, in_nf_duplicate = 0, atomic_flags = 0, restart_block = {arch_data = 0,
    fn = 0xffffffff812a1150 <do_no_restart_syscall>, {futex = {uaddr = 0x0, val = 0, flags = 0, bitset = 0, time = 0, uaddr2 = 0x0}, nanosleep = {clockid = 0, type = TT_NONE, {rmtp = 0x0,
          compat_rmtp = 0x0}, expires = 0}, poll = {ufds = 0x0, nfds = 0, has_timeout = 0, tv_sec = 0, tv_nsec = 0}}}, pid = 59, tgid = 59, stack_canary = 15981912377558717184,
  real_parent = 0xffff888003988000, parent = 0xffff888003988000, children = {next = 0xffff8880043585b0, prev = 0xffff8880043585b0}, sibling = {next = 0xffff8880039885b0,
    prev = 0xffff88800435a340}, group_leader = 0xffff888004358000, ptraced = {next = 0xffff8880043585d8, prev = 0xffff8880043585d8}, ptrace_entry = {next = 0xffff8880043585e8,
    prev = 0xffff8880043585e8}, thread_pid = 0xffff8880043cfa80, pid_links = {{next = 0x0, pprev = 0xffff8880043cfac0}, {next = 0x0, pprev = 0xffff8880043cfac8}, {next = 0xffff88800404ed60,
      pprev = 0xffffffff82a547d0 <init_struct_pid+80>}, {next = 0xffff88800404ed70, pprev = 0xffffffff82a547d8 <init_struct_pid+88>}}, thread_node = {next = 0xffff888003be9f90,
--Type <RET> for more, q to quit, c to continue without paging--
    prev = 0xffff888003be9f90}, vfork_done = 0x0, set_child_tid = 0x0, clear_child_tid = 0x0, worker_private = 0x0, utime = 5000000, stime = 37000000, gtime = 0, prev_cputime = {utime = 0,
    stime = 0, lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}, nvcsw = 63, nivcsw = 76, start_time = 851272958373,
  start_boottime = 851272962422, min_flt = 18, maj_flt = 57, posix_cputimers = {bases = {{nextevt = 18446744073709551615, tqhead = {rb_root = {rb_root = {rb_node = 0x0},
            rb_leftmost = 0x0}}}, {nextevt = 18446744073709551615, tqhead = {rb_root = {rb_root = {rb_node = 0x0}, rb_leftmost = 0x0}}}, {nextevt = 18446744073709551615, tqhead = {
          rb_root = {rb_root = {rb_node = 0x0}, rb_leftmost = 0x0}}}}, timers_active = 0, expiry_active = 0}, posix_cputimers_work = {work = {next = 0x0,
      func = 0xffffffff81360cf0 <posix_cpu_timers_work>}, mutex = {owner = {counter = 0}, wait_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {
              locked_pending = 0, tail = 0}}}}, osq = {tail = {counter = 0}}, wait_list = {next = 0xffff888004358740, prev = 0xffff888004358740}}, scheduled = 0}, ptracer_cred = 0x0,
  real_cred = 0xffff888003959000, cred = 0xffff888003959000, cached_requested_key = 0x0, comm = "mm_lab1\000\000\000\000\000\000\000\000", nameidata = 0x0, sysvsem = {undo_list = 0x0},
  sysvshm = {shm_clist = {next = 0xffff888004358798, prev = 0xffff888004358798}}, fs = 0xffff8880043fe280, files = 0xffff8880039dc580, io_uring = 0x0,
  nsproxy = 0xffffffff82a548c0 <init_nsproxy>, signal = 0xffff888003be9f80, sighand = 0xffff88800433a100, blocked = {sig = {0}}, real_blocked = {sig = {0}}, saved_sigmask = {sig = {0}},
  pending = {list = {next = 0xffff8880043587f0, prev = 0xffff8880043587f0}, signal = {sig = {0}}}, sas_ss_sp = 0, sas_ss_size = 0, sas_ss_flags = 2, task_works = 0x0, audit_context = 0x0,
  loginuid = {val = 4294967295}, sessionid = 4294967295, seccomp = {mode = 0, filter_count = {counter = 0}, filter = 0x0}, syscall_dispatch = {selector = 0x0, offset = 0, len = 0,
    on_dispatch = false}, parent_exec_id = 2, self_exec_id = 3, alloc_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0,
              tail = 0}}}}}}, pi_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, wake_q = {next = 0x0}, pi_waiters = {
    rb_root = {rb_node = 0x0}, rb_leftmost = 0x0}, pi_top_task = 0x0, pi_blocked_on = 0x0, blocked_on = 0x0, journal_info = 0x0, bio_list = 0x0, plug = 0x0, reclaim_state = 0x0,
  io_context = 0x0, capture_control = 0x0, ptrace_message = 0, last_siginfo = 0x0, ioac = {rchar = 816, wchar = 146, syscr = 2, syscw = 5, read_bytes = 234288, write_bytes = 0,
    cancelled_write_bytes = 0}, acct_rss_mem1 = 534178, acct_vm_mem1 = 10264638, acct_timexpd = 42000000, mems_allowed = {bits = {1}}, mems_allowed_seq = {seqcount = {sequence = 0}},
  cpuset_mem_spread_rotor = -1, cgroups = 0xffffffff82b4d2c0 <init_css_set>, cg_list = {next = 0xffffffff82b4d350 <init_css_set+144>, prev = 0xffff88800435a6d8}, robust_list = 0x0,
  compat_robust_list = 0x0, pi_state_list = {next = 0xffff888004358978, prev = 0xffff888004358978}, pi_state_cache = 0x0, futex_exit_mutex = {owner = {counter = 0}, wait_lock = {raw_lock = {
        {val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, osq = {tail = {counter = 0}}, wait_list = {next = 0xffff8880043589a0,
      prev = 0xffff8880043589a0}}, futex_state = 0, perf_recursion = "\000\000\000", perf_event_ctxp = 0x0, perf_event_mutex = {owner = {counter = 0}, wait_lock = {raw_lock = {{val = {
            counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, osq = {tail = {counter = 0}}, wait_list = {next = 0xffff8880043589d0,
      prev = 0xffff8880043589d0}}, perf_event_list = {next = 0xffff8880043589e0, prev = 0xffff8880043589e0}, perf_ctx_data = 0x0, mempolicy = 0x0, il_prev = 0, il_weight = 0 '\000',
  pref_node_fork = 0, rseq = 0x0, rseq_len = 0, rseq_sig = 0, rseq_event_mask = 1, mm_cid = -1, last_mm_cid = 0, migrate_from_cpu = -1, mm_cid_active = 1, cid_work = {
    next = 0xffff888004358a30, func = 0xffffffff812cc0f0 <task_mm_cid_work>}, tlb_ubc = {arch = {cpumask = {bits = {0}}, unmapped_pages = false}, flush_required = false, writable = false},
  splice_pipe = 0x0, task_frag = {page = 0x0, offset = 0, size = 0}, delays = 0x0, nr_dirtied = 0, nr_dirtied_pause = 32, dirty_paused_when = 0, timer_slack_ns = 50000,
  default_timer_slack_ns = 50000, trace_recursion = 0, throttle_disk = 0x0, utask = 0x0, kmap_ctrl = {<No data fields>}, rcu = {next = 0x0, func = 0x0}, rcu_users = {refs = {counter = 2}},
  pagefault_disabled = 0, oom_reaper_list = 0x0, oom_reaper_timer = {entry = {next = 0x0, pprev = 0x0}, expires = 0, function = 0x0, flags = 0}, stack_vm_area = 0xffff8880043fcea0,
  stack_refcount = {refs = {counter = 1}}, security = 0x0, bpf_net_context = 0x0, mce_vaddr = 0x0, mce_kflags = 0, mce_addr = 0, mce_ripv = 0, mce_whole_page = 0, __mce_reserved = 0,
  mce_kill_me = {next = 0x0, func = 0x0}, mce_count = 0, kretprobe_instances = {first = 0x0}, rethooks = {first = 0x0}, l1d_flush_kill = {next = 0x0, func = 0x0}, thread = {tls_array = {{
        limit0 = 0, base0 = 0, base1 = 0, type = 0, s = 0, dpl = 0, p = 0, limit1 = 0, avl = 0, l = 0, d = 0, g = 0, base2 = 0}, {limit0 = 0, base0 = 0, base1 = 0, type = 0, s = 0, dpl = 0,
        p = 0, limit1 = 0, avl = 0, l = 0, d = 0, g = 0, base2 = 0}, {limit0 = 0, base0 = 0, base1 = 0, type = 0, s = 0, dpl = 0, p = 0, limit1 = 0, avl = 0, l = 0, d = 0, g = 0,
        base2 = 0}}, sp = 18446683600571939768, es = 0, ds = 0, fsindex = 0, gsindex = 0, fsbase = 552933504, gsbase = 0, ptrace_bps = {0x0, 0x0, 0x0, 0x0}, virtual_dr6 = 0, ptrace_dr7 = 0,
    cr2 = 0, trap_nr = 0, error_code = 0, io_bitmap = 0x0, iopl_emul = 0, iopl_warn = 0, pkru = 0}}
(gdb)
```

```sh
(gdb) p $task->comm
$2 = "mm_lab1\000\000\000\000\000\000\000\000"
(gdb) p $task->pid
$3 = 59
```

`$task->comm` is the command with which the process was started, padded to 16 chars. 

```sh
(gdb) p $task->mm
$4 = (struct mm_struct *) 0xffff88800384c5c0
(gdb) p $task->active_mm
$5 = (struct mm_struct *) 0xffff88800384c5c0
(gdb) p $task->files
$6 = (struct files_struct *) 0xffff8880039dc580
(gdb) p $task->fs
$7 = (struct fs_struct *) 0xffff8880043fe280
(gdb)
```

```sh
(gdb) p $task->stack
$8 = (void *) 0xffffc900001d0000
```

This is the address of kernel stack. 

**Why it matters:** Every process in Linux has two stacks: a user-space stack (managed by rsp) and a dedicated kernel-space stack (typically 16 KB on x86_64).

**How it works:** When mm_lab1 executes a system call (like mmap() or read()), the CPU hardware automatically switches execution from the user stack to this exact address space in kernel memory. The top of this stack holds the pt_regs structure, which saves user-space CPU registers during system calls or interrupts.

### Observing the mm_struct

#### 1. Printing the mm_struct

```sh
(gdb) set $mm = $task->mm
(gdb) p *$mm
$9 = {{{mm_count = {counter = 2}}, mm_mt = {{ma_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}},
        ma_external_lock = {<No data fields>}}, ma_flags = 779, ma_root = 0xffff888004587f1e}, mmap_base = 139639653347328, mmap_legacy_base = 47993141821440, mmap_compat_base = 4159954944,
    mmap_compat_legacy_base = 1432440832, task_size = 140737488351232, pgd = 0xffff8880045ce000, membarrier_state = {counter = 0}, mm_users = {counter = 1}, pcpu_cid = 0xffffffff835389e0,
    mm_cid_next_scan = 4295518540, nr_cpus_allowed = 1, max_nr_cid = {counter = 1}, cpus_allowed_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {
            locked_pending = 0, tail = 0}}}}, pgtables_bytes = {counter = 40960}, map_count = 11, page_table_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000',
                pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}}, mmap_lock = {count = {counter = 0}, owner = {counter = -131391568904191}, osq = {tail = {counter = 0}},
      wait_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, wait_list = {next = 0xffff88800384c690,
        prev = 0xffff88800384c690}}, mmlist = {next = 0xffff88800384c6a0, prev = 0xffff88800384c6a0}, vma_writer_wait = {task = 0x0}, mm_lock_seq = {sequence = 28}, futex_hash_lock = {
      owner = {counter = 0}, wait_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, osq = {tail = {counter = 0}},
      wait_list = {next = 0xffff88800384c6d0, prev = 0xffff88800384c6d0}}, futex_phash = 0x0, futex_phash_new = 0x0, futex_batches = 776, futex_rcu = {next = 0x0, func = 0x0},
    futex_atomic = {counter = 0}, futex_ref = 0x0, hiwater_rss = 0, hiwater_vm = 0, total_vm = 272, locked_vm = 0, pinned_vm = {counter = 0}, data_vm = 39, exec_vm = 151, stack_vm = 33,
    def_flags = 0, write_protect_seq = {sequence = 0}, arg_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}},
    start_code = 4198400, end_code = 4805745, start_data = 4972736, end_data = 4993552, start_brk = 552931328, brk = 553074688, start_stack = 140733994124432, arg_start = 140733994127288,
    arg_end = 140733994127298, env_start = 140733994127298, env_end = 140733994127342, saved_auxv = {33, 139639653339136, 51, 1440, 16, 126614525, 6, 4096, 17, 100, 3, 4194368, 4, 56, 5,
      10, 7, 0, 8, 0, 9, 4201536, 11, 0, 12, 0, 13, 0, 14, 0, 23, 0, 25, 140733994124873, 26, 0, 31, 140733994127342, 15, 140733994124889, 27, 28, 28, 32, 0, 0, 0, 0, 0, 0, 0, 0},
    rss_stat = {{lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, count = 32, list = {next = 0xffff88800384d568,
          prev = 0xffff88800384c998}, counters = 0xffffffff835389f0}, {lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}},
        count = 0, list = {next = 0xffff88800384c970, prev = 0xffff88800384c9c0}, counters = 0xffffffff835389f4}, {lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000',
                pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, count = 0, list = {next = 0xffff88800384c998, prev = 0xffff88800384c9e8}, counters = 0xffffffff835389f8}, {lock = {
          raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, count = 0, list = {next = 0xffff88800384c9c0,
          prev = 0xffffffff82bd7c20 <percpu_counters>}, counters = 0xffffffff835389fc}}, binfmt = 0xffffffff82b7ce20 <elf_format>, context = {ctx_id = 21, tlb_gen = {counter = 4},
      next_trim_cpumask = 4295519431, ldt_usr_sem = {count = {counter = 0}, owner = {counter = 0}, osq = {tail = {counter = 0}}, wait_lock = {raw_lock = {{val = {counter = 0}, {
                locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, wait_list = {next = 0xffff88800384ca38, prev = 0xffff88800384ca38}}, ldt = 0x0, flags = 2, lock = {
        owner = {counter = 0}, wait_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, osq = {tail = {counter = 0}},
        wait_list = {next = 0xffff88800384ca68, prev = 0xffff88800384ca68}}, vdso = 0x7f0063ef1000, vdso_image = 0xffffffff82201140 <vdso_image_64>, perf_rdpmc_allowed = {counter = 0},
      pkey_allocation_map = 0, execute_only_pkey = 0, global_asid = 0, asid_transition = false}, flags = 2147483853, ioctx_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {
                locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}}, ioctx_table = 0x0, user_ns = 0xffffffff82a534a0 <init_user_ns>, exe_file = 0xffff888004200480,
    notifier_subscriptions = 0x0, tlb_flush_pending = {counter = 0}, tlb_flush_batched = {counter = 0}, uprobes_state = {xol_area = 0x0}, hugetlb_usage = {counter = 0}, async_put_work = {
      data = {counter = 0}, entry = {next = 0x0, prev = 0x0}, func = 0x0}, iommu_mm = 0x0}, cpu_bitmap = 0xffff88800384cb40}
(gdb)
$10 = {{{mm_count = {counter = 2}}, mm_mt = {{ma_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}},
        ma_external_lock = {<No data fields>}}, ma_flags = 779, ma_root = 0xffff888004587f1e}, mmap_base = 139639653347328, mmap_legacy_base = 47993141821440, mmap_compat_base = 4159954944,
    mmap_compat_legacy_base = 1432440832, task_size = 140737488351232, pgd = 0xffff8880045ce000, membarrier_state = {counter = 0}, mm_users = {counter = 1}, pcpu_cid = 0xffffffff835389e0,
    mm_cid_next_scan = 4295518540, nr_cpus_allowed = 1, max_nr_cid = {counter = 1}, cpus_allowed_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {
            locked_pending = 0, tail = 0}}}}, pgtables_bytes = {counter = 40960}, map_count = 11, page_table_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000',
                pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}}, mmap_lock = {count = {counter = 0}, owner = {counter = -131391568904191}, osq = {tail = {counter = 0}},
      wait_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, wait_list = {next = 0xffff88800384c690,
        prev = 0xffff88800384c690}}, mmlist = {next = 0xffff88800384c6a0, prev = 0xffff88800384c6a0}, vma_writer_wait = {task = 0x0}, mm_lock_seq = {sequence = 28}, futex_hash_lock = {
      owner = {counter = 0}, wait_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, osq = {tail = {counter = 0}},
      wait_list = {next = 0xffff88800384c6d0, prev = 0xffff88800384c6d0}}, futex_phash = 0x0, futex_phash_new = 0x0, futex_batches = 776, futex_rcu = {next = 0x0, func = 0x0},
    futex_atomic = {counter = 0}, futex_ref = 0x0, hiwater_rss = 0, hiwater_vm = 0, total_vm = 272, locked_vm = 0, pinned_vm = {counter = 0}, data_vm = 39, exec_vm = 151, stack_vm = 33,
    def_flags = 0, write_protect_seq = {sequence = 0}, arg_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}},
    start_code = 4198400, end_code = 4805745, start_data = 4972736, end_data = 4993552, start_brk = 552931328, brk = 553074688, start_stack = 140733994124432, arg_start = 140733994127288,
    arg_end = 140733994127298, env_start = 140733994127298, env_end = 140733994127342, saved_auxv = {33, 139639653339136, 51, 1440, 16, 126614525, 6, 4096, 17, 100, 3, 4194368, 4, 56, 5,
      10, 7, 0, 8, 0, 9, 4201536, 11, 0, 12, 0, 13, 0, 14, 0, 23, 0, 25, 140733994124873, 26, 0, 31, 140733994127342, 15, 140733994124889, 27, 28, 28, 32, 0, 0, 0, 0, 0, 0, 0, 0},
    rss_stat = {{lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, count = 32, list = {next = 0xffff88800384d568,
          prev = 0xffff88800384c998}, counters = 0xffffffff835389f0}, {lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}},
        count = 0, list = {next = 0xffff88800384c970, prev = 0xffff88800384c9c0}, counters = 0xffffffff835389f4}, {lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000',
                pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, count = 0, list = {next = 0xffff88800384c998, prev = 0xffff88800384c9e8}, counters = 0xffffffff835389f8}, {lock = {
          raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, count = 0, list = {next = 0xffff88800384c9c0,
          prev = 0xffffffff82bd7c20 <percpu_counters>}, counters = 0xffffffff835389fc}}, binfmt = 0xffffffff82b7ce20 <elf_format>, context = {ctx_id = 21, tlb_gen = {counter = 4},
      next_trim_cpumask = 4295519431, ldt_usr_sem = {count = {counter = 0}, owner = {counter = 0}, osq = {tail = {counter = 0}}, wait_lock = {raw_lock = {{val = {counter = 0}, {
                locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, wait_list = {next = 0xffff88800384ca38, prev = 0xffff88800384ca38}}, ldt = 0x0, flags = 2, lock = {
        owner = {counter = 0}, wait_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, osq = {tail = {counter = 0}},
        wait_list = {next = 0xffff88800384ca68, prev = 0xffff88800384ca68}}, vdso = 0x7f0063ef1000, vdso_image = 0xffffffff82201140 <vdso_image_64>, perf_rdpmc_allowed = {counter = 0},
      pkey_allocation_map = 0, execute_only_pkey = 0, global_asid = 0, asid_transition = false}, flags = 2147483853, ioctx_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {
                locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}}, ioctx_table = 0x0, user_ns = 0xffffffff82a534a0 <init_user_ns>, exe_file = 0xffff888004200480,
    notifier_subscriptions = 0x0, tlb_flush_pending = {counter = 0}, tlb_flush_batched = {counter = 0}, uprobes_state = {xol_area = 0x0}, hugetlb_usage = {counter = 0}, async_put_work = {
      data = {counter = 0}, entry = {next = 0x0, prev = 0x0}, func = 0x0}, iommu_mm = 0x0}, cpu_bitmap = 0xffff88800384cb40}
(gdb)
```

#### 2. Printing the segment related fields

```sh
(gdb) p $mm->start_code
$11 = 4198400
(gdb) p $mm->end_code
$12 = 4805745
(gdb) p $mm->start_data
$13 = 4972736
(gdb) p $mm->end_data
$14 = 4993552
(gdb) p $mm->start_brk
$15 = 552931328
(gdb) p $mm->brk
$16 = 553074688
(gdb) p $mm->start_stack
$17 = 140733994124432
(gdb) p $mm->arg_start
$18 = 140733994127288
(gdb) p $mm->arg_end
$19 = 140733994127298
(gdb) p $mm->env_start
$20 = 140733994127298
(gdb) p $mm->env_end
$21 = 140733994127342
(gdb)
```

These addresses are directly stored as part of `mm_struct` even though they are already part of VMA maple tree because they are are accessed frequently and kernel can't afforf logartihmic traversal everytime

Storing raw start/end pointers in `mm_struct` looks like duplicate accounting. However, the kernel keeps these explicit fields for three critical reasons: micro-second lookup speed, OS/POSIX contract guarantees, and fast  `/proc` reporting.

- `brk` and `start_brk` (The Heap): Every time your program calls `sbrk()` or `malloc()` asks for more heap space, the kernel evaluates `sys_brk()`. Instead of searching the VMA tree to find where the heap ends, it does a fast O(1) scalar check against $mm->brk.
- `start_stack` (Stack Growth): When a page fault occurs near the bottom of the user stack, the page fault handler needs to immediately answer: "Is this fault a legitimate stack expansion, or a segment fault crash?" Checking` $mm->start_stack` instantly provides the anchor point to calculate if the faulting address is within the allowed stack limit (e.g., 8 MB down from `start_stack`).

**POSIX Standards & Kernel-User ABI Contracts**

These specific segments aren't arbitrary—they represent the C Execution Environment guaranteed by the POSIX standard and Executable and Linkable Format (ELF) specifications.

- Command Line & Environment (`arg_start` to `env_end`):
  When your process starts, the kernel loads argv and envp onto the initial stack. If a tool like ps aux or top runs, or if a program reads `/proc/self/cmdline` or `/proc/self/environ`, the kernel reads these exact pointers in $mm.

- Program Name Rewriting: 
  Programs like redis-server or postgres dynamically rewrite their command-line name in memory so that ps shows status updates (e.g., postgres: writer process). The kernel checks `$mm->arg_start` and `$mm->arg_end` to safely allow or clamp those memory reads.

Modern Linux has added new specialized segments over time, but instead of adding endless new raw fields to `mm_struct`, the kernel handles them cleanly using VMA Flags and Special VMAs:

1. **The vDSO and vvar** ([vdso], [vvar]): Kernel-provided virtual dynamic shared objects mapped into userspace to accelerate system calls like gettimeofday(). They do not get dedicated pointers in mm_struct; they are standard VMAs flagged with special architecture hooks.

2. **Memory Guard Pages & Anonymous Mappings**: Managed entirely via flags (`VM_READ`, `VM_WRITE`, `VM_EXEC`, `VM_GROWSDOWN`, `VM_DONTCOPY`).

3. **Guard Regions & Memory Protection Keys (PKEYS)**: Handled via bitmasks within the individual `vm_area_struct`.

**The virtual addresses**

 Every address you printed from `$mm` is a **User-Space Virtual Address** as seen from the perspective of your running `mm_lab1` process.

And if you inspect `/proc/[pid]/maps` (or `/proc/self/maps` from within the program itself), you will see those exact same hex ranges!

##### 1. Connecting `$mm` to `/proc/[pid]/maps`

When you run `cat /proc/59/maps` in the terminal, the kernel handles that read request by taking the process's `mm_struct` and walking its Maple Tree (`mm_mt`).

It formats each `vm_area_struct` entry into a line of text. If you convert the decimal numbers GDB gave you into hexadecimal, you can match them up 1:1 with `/proc/61/maps`:

* **`start_code`** = `4198400` $\rightarrow$ **`0x400000`** (The classic non-PIE base ELF entry point on x86_64).
* **`brk`** = `621027328` $\rightarrow$ **`0x2509b000`** (Top of the heap).
* **`start_stack`** = `140728151635392` $\rightarrow$ **`0x7ffcd36de000`** (Top of user-space stack).


##### 2. The "Big Hole" Between Heap and Stack

Your mental model is spot on! On 64-bit x86 Linux, the CPU uses a **48-bit canonical virtual address space** for user processes. That gives every single process a colossal **128 Terabytes** of virtual memory (ranging from `0x0000000000000000` to `0x00007FFFFFFFFFFF`).

When your program loads, the layout looks sparse like this:

```text
Virtual Address Space (128 TB Canonical User Space)
0x0000000000000000 ┌─────────────────────────────────────────┐
                   │  Reserved / Null pointer guard (Page 0) │
0x0000000000400000 ├─────────────────────────────────────────┤
                   │  .text / .data / .bss  (start_code)     │
0x000000002509b000 ├─────────────────────────────────────────┤ ◄── brk (Heap top)
                   │  ▲ Grows UPWARD                         │
                   │                                         │
                   │                                         │
                   │          THE HUGE "HOLE"                │
                   │     (100+ Terabytes of Empty Space)     │
                   │                                         │
                   │  Shared Libraries (.so), Anonymous      │
                   │  mmap() areas, Thread stacks live here  │
                   │                                         │
                   │                                         │
                   │  ▼ Grows DOWNWARD                       │
0x00007FFCD36DE000 ├─────────────────────────────────────────┤ ◄── start_stack
                   │  Main Thread Stack                      │
                   ├─────────────────────────────────────────┤
                   │  ARGV & ENVP Strings                    │
0x00007FFFFFFFFFFF └─────────────────────────────────────────┘

```


##### What Actually Lives in That "Hole"?

That multi-terabyte gap isn't wasted physical RAM—remember, virtual addresses cost nothing until backed by physical page frames.

The kernel leaves this gap intentionally huge for two reasons:

1. **The `mmap` Allocation Area:** When you call `mmap()` (or when dynamically linked programs load shared libraries like `libc.so`), the kernel places those VMAs smack in the middle of this gap (typically growing downward starting from somewhere around `0x7f...`).
2. **ASLR (Address Space Layout Randomization):** Security hardening relies on unpredictability. The kernel uses that massive vacant space to add random offsets to where the stack, heap, and `mmap` regions start on every execution, making buffer overflow exploits vastly harder to land.

Because your test program `mm_lab1` was compiled with `-static`, there are no dynamic `.so` libraries loaded into that middle region, making the gap look even more dramatic!

#### 3. Printing the Page Table Root (pgd)

```sh
(gdb) p $mm->pgd
$22 = (pgd_t *) 0xffff8880045ce000
(gdb)
```

- **What it is**: Pointer to the process's Page Global Directory (the top-level 4-level or 5-level page table).

- **Significance**: During a context switch, the kernel loads the physical address corresponding to pgd into the x86 CPU's CR3 control register. This instantly changes the active hardware translation table to this process's virtual address space.

#### 4. Memory Accounting Counters

Number of VMA's

```sh
(gdb) p $mm->map_count
$23 = 11
```

Two tier ref counting

```sh
(gdb) p $mm->mm_users
$30 = {counter = 1}
(gdb) p $mm->mm_count
$31 = {counter = 2}
```

Memory usage stats

```sh
(gdb) p $mm->total_vm
$25 = 272
(gdb) p $mm->locked_vm
$26 = 0
(gdb) p $mm->pinned_vm
$27 = {counter = 0}
(gdb) p $mm->data_vm
$28 = 39
(gdb) p $mm->exec_vm
$29 = 151
(gdb)
```

#### 5. RSS stats

```sh
(gdb) p $mm->rss_stat
$30 = {{lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, count = 32, list = {next = 0xffff88800384d568,
      prev = 0xffff88800384c998}, counters = 0xffffffff835389f0}, {lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}},
    count = 0, list = {next = 0xffff88800384c970, prev = 0xffff88800384c9c0}, counters = 0xffffffff835389f4}, {lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000',
            pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, count = 0, list = {next = 0xffff88800384c998, prev = 0xffff88800384c9e8}, counters = 0xffffffff835389f8}, {lock = {
      raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, count = 0, list = {next = 0xffff88800384c9c0,
      prev = 0xffffffff82bd7c20 <percpu_counters>}, counters = 0xffffffff835389fc}}
(gdb)
```

| Index | Enum Constant | Meaning |
| --- | --- | --- |
| 0 | MM_FILEPAGES | Physical pages backing file-backed mappings (executables, libraries). |
| 1 | MM_ANONPAGES | Physical pages backing anonymous memory (heap, stack, MAP_ANONYMOUS). |
| 2 | MM_SWAPENTS | Swap entries (pages currently swapped out to disk). |
| 3 | MM_SHMEMPAGES | Physical pages backing shared memory / tmpfs. |

 calculate the total RSS in pages, sum up indices 0, 1, and 
 
 ```
 Total RSS Pages = MM_FILEPAGES + MM_ANONPAGES + MM_SHMEMPAGES
 ```

Multiply the page count by 4096 (or 4 KB) to convert to bytes:

**Kernel Nuance (Per-Task Batching):**

To prevent CPU cacheline bouncing on multi-core systems, modern kernels do not update `$mm->rss_stat` on every single page fault. Instead, each thread (task_struct) buffers local RSS changes inside` task->rss_stat` and syncs them periodically to `$mm->rss_stat`. On idle or single-threaded tasks like mm_lab1, `$mm->rss_stat` is exact.

Here is the breakdown of your `rss_stat` array formatted into a Markdown table for your notes:

`mm_struct` RSS Breakdown (`0xffff88800384cb80`)

Here is the formatted table for your `$30` dump:


| Index | Stat Type | Pages (`count`) | Size (KB) | Per-CPU Counter Pointer | Description |
| --- | --- | --- | --- | --- | --- |
| **0** | `MM_FILEPAGES` | **32** | 128 KB | `0xffffffff835389f0` | File-backed memory (executable code, shared libraries, pagecache) |
| **1** | `MM_ANONPAGES` | **0** | 0 KB | `0xffffffff835389f4` | Anonymous memory (process heap, stacks, non-file `mmap`) |
| **2** | `MM_SWAPENTS` | **0** | 0 KB | `0xffffffff835389f8` | Swapped out entries (stored on disk swap space) |
| **3** | `MM_SHMEMPAGES` | **0** | 0 KB | `0xffffffff835389fc` | Shared memory / `tmpfs` allocations |

**From Userspace**

```sh
/ $ grep -i rss /proc/59/status
VmRSS:	     260 kB
RssAnon:	      44 kB
RssFile:	     216 kB
RssShmem:	       0 kB
```

VmRSS stands for Virtual Memory Resident Set Size. It represents the total amount of physical RAM currently mapped into the process's page tables.It is always the exact sum of three sub-categories:

```
VmRSS =  RssAnon + RssFile + RssShmem
```

We can see they don't match 

**Why Are They Different?**

There are two distinct reasons for this mismatch:

**Unsynced Per-CPU Counter Buffers (The Technical Reason)**

As seen in your GDB printout, your kernel uses `struct percpu_counter` for `rss_stat`.

When a process takes a page fault, the kernel updates a **local per-CPU buffer** (the address pointed to by `counters = 0xffffffff835389f0`) rather than updating `$mm->rss_stat[i].count` directly. This avoids CPU cacheline locking on multi-core systems.

* **In GDB:** Printing `$mm->rss_stat[0].count` directly reads only the **global base value** (`32`), ignoring any un-synced page counts sitting in the per-CPU buffers.
* **In `/proc/62/status`:** When you read `/proc/62/status`, the kernel calls `get_mm_rss(mm)`. This helper function actively walks all CPUs and sums up the per-CPU delta buffers, returning the **exact aggregate RSS**.

**Summary**

`/proc/62/status` is providing the **true real-time picture** because it flushes/aggregates the `percpu_counter` buffers and reflects memory accessed after page faults occurred.

In GDB, reading `$mm->rss_stat[i].count` directly only gives you the stale global counter value before those per-CPU updates were committed.

#### 6. Printing VMA's

Printing VMA's from kernel space is not an easy task as it involves walking maple tree and there are no easy utilities. So the best way is to print it from userspace. 

```sh
/ #  cat /proc/59/maps
00400000-00401000 r--p 00000000 00:15 37619537                           /mnt/mm_lab1
00401000-00496000 r-xp 00001000 00:15 37619537                           /mnt/mm_lab1
00496000-004bd000 r--p 00096000 00:15 37619537                           /mnt/mm_lab1
004be000-004c1000 r--p 000bd000 00:15 37619537                           /mnt/mm_lab1
004c1000-004c4000 rw-p 000c0000 00:15 37619537                           /mnt/mm_lab1
004c4000-004c5000 rw-p 00000000 00:00 0
20f51000-20f74000 rw-p 00000000 00:00 0                                  [heap]
7f0063eeb000-7f0063eef000 r--p 00000000 00:00 0                          [vvar]
7f0063eef000-7f0063ef1000 r--p 00000000 00:00 0                          [vvar_vclock]
7f0063ef1000-7f0063ef3000 r-xp 00000000 00:00 0                          [vdso]
7fff2fb84000-7fff2fba5000 rw-p 00000000 00:00 0                          [stack]
ffffffffff600000-ffffffffff601000 --xp 00000000 00:00 0                  [vsyscall]
```

```sh
/ # cat /proc/59/smaps
00400000-00401000 r--p 00000000 00:15 37619537                           /mnt/mm_lab1
Size:                  4 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                   4 kB
Pss:                   4 kB
Pss_Dirty:             0 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         4 kB
Private_Dirty:         0 kB
Referenced:            4 kB
Anonymous:             0 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
VmFlags: rd mr mw me
00401000-00496000 r-xp 00001000 00:15 37619537                           /mnt/mm_lab1
Size:                596 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                 176 kB
Pss:                 176 kB
Pss_Dirty:             0 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:       176 kB
Private_Dirty:         0 kB
Referenced:          176 kB
Anonymous:             0 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
VmFlags: rd ex mr mw me
00496000-004bd000 r--p 00096000 00:15 37619537                           /mnt/mm_lab1
Size:                156 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                  28 kB
Pss:                  28 kB
Pss_Dirty:             0 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:        28 kB
Private_Dirty:         0 kB
Referenced:           28 kB
Anonymous:             0 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
VmFlags: rd mr mw me
004be000-004c1000 r--p 000bd000 00:15 37619537                           /mnt/mm_lab1
Size:                 12 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                   8 kB
Pss:                   8 kB
Pss_Dirty:             4 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         4 kB
Private_Dirty:         4 kB
Referenced:            8 kB
Anonymous:             4 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
VmFlags: rd mr mw me ac
004c1000-004c4000 rw-p 000c0000 00:15 37619537                           /mnt/mm_lab1
Size:                 12 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                  12 kB
Pss:                  12 kB
Pss_Dirty:            12 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         0 kB
Private_Dirty:        12 kB
Referenced:           12 kB
Anonymous:            12 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
VmFlags: rd wr mr mw me ac
004c4000-004c5000 rw-p 00000000 00:00 0
Size:                  4 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                   4 kB
Pss:                   4 kB
Pss_Dirty:             4 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         0 kB
Private_Dirty:         4 kB
Referenced:            4 kB
Anonymous:             4 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
VmFlags: rd wr mr mw me ac
20f51000-20f74000 rw-p 00000000 00:00 0                                  [heap]
Size:                140 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                  16 kB
Pss:                  16 kB
Pss_Dirty:            16 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         0 kB
Private_Dirty:        16 kB
Referenced:           16 kB
Anonymous:            16 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
VmFlags: rd wr mr mw me ac
7f0063eeb000-7f0063eef000 r--p 00000000 00:00 0                          [vvar]
Size:                 16 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                   0 kB
Pss:                   0 kB
Pss_Dirty:             0 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         0 kB
Private_Dirty:         0 kB
Referenced:            0 kB
Anonymous:             0 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
VmFlags: rd mr pf io de dd
7f0063eef000-7f0063ef1000 r--p 00000000 00:00 0                          [vvar_vclock]
Size:                  8 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                   0 kB
Pss:                   0 kB
Pss_Dirty:             0 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         0 kB
Private_Dirty:         0 kB
Referenced:            0 kB
Anonymous:             0 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
VmFlags: rd mr pf io de dd
7f0063ef1000-7f0063ef3000 r-xp 00000000 00:00 0                          [vdso]
Size:                  8 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                   4 kB
Pss:                   4 kB
Pss_Dirty:             0 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         4 kB
Private_Dirty:         0 kB
Referenced:            4 kB
Anonymous:             0 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
VmFlags: rd ex mr mw me de
7fff2fb84000-7fff2fba5000 rw-p 00000000 00:00 0                          [stack]
Size:                132 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                   8 kB
Pss:                   8 kB
Pss_Dirty:             8 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         0 kB
Private_Dirty:         8 kB
Referenced:            8 kB
Anonymous:             8 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
VmFlags: rd wr mr mw me gd ac
ffffffffff600000-ffffffffff601000 --xp 00000000 00:00 0                  [vsyscall]
Size:                  4 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                   0 kB
Pss:                   0 kB
Pss_Dirty:             0 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         0 kB
Private_Dirty:         0 kB
Referenced:            0 kB
Anonymous:             0 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
VmFlags: ex
/ #
```

**Special Kernel Regions:**

- **[vdso] / [vvar]**: Allows user space to read kernel clock data (like gettimeofday()) directly from RAM without suffering the context-switch overhead of a full syscall.
- **[vsyscall]**: Fixed high virtual address mapped for ancient x86_64 ABI compatibility.


**Essential `smaps` Metrics Explained**

| Field | Meaning |
| --- | --- |
| **`Size`** | Total virtual memory reserved for this VMA. |
| **`Rss`** | **Resident Set Size:** Real physical RAM currently backing this VMA. |
| **`Pss`** | **Proportional Set Size:** RSS adjusted for pages shared with other processes. |
| **`Private_Clean`** | Pages in RAM loaded from disk that **have not** been modified (e.g., executable code). Can be safely dropped by kernel if RAM is tight. |
| **`Private_Dirty`** | Pages modified in RAM that **differ** from disk (e.g., written data, heap, stack). Must be written to swap before freeing. |
| **`Anonymous`** | Memory allocated without any backing file (heap, stack, `MAP_ANONYMOUS`). |
| **`VmFlags`** | Kernel VMA behavior flags (`rd`=read, `wr`=write, `ex`=exec, `gd`=grows down for stack). |


### State 2: After malloc (8 KB)

```
========== State 2 ==========
Small malloc(8 KB) returned 0x20f54b90
Observe whether map_count changed.
Small allocations are typically served from the existing heap VMA.
No pages have been touched yet.
```

#### Changes in VMA

```sh
(gdb) p $mm->map_count
$31 = 11
```

No new VMA is created

#### Changes in RSS

```sh
/ # grep -i rss /proc/59/status
VmRSS:	     292 kB
RssAnon:	      48 kB
RssFile:	     244 kB
RssShmem:	       0 kB
```

We can see +32 KB increase in `VmRSS`, although malloc hasn't touched any pages yet, +4 KB for `RssAnon` and + 28 KB for `RssFile`.

While we can't say if a part of that increase was because of malloc (even though we haven't touched those pages yet). The most plausible explanation is 

our kernel loads executable code and shared libraries into RAM on-demand (demand paging).

When calling malloc(), your CPU had to execute code inside the C library's heap manager routines that hadn't been run yet in this process's lifecycle.

Executing those new instructions triggered page faults on the binary file (/mnt/mm_lab1 or libc), causing the kernel to load 7 additional code pages (28 KB) from disk/storage into RAM.

```sh
(gdb) p $mm->total_vm
$32 = 272
```

No change in `total_vm` whch indicates promised memory. Which means kernel hasnt allocated space for our malloc yet. 

### State 3: After malloc (256 MB)

```
========== State 3 ==========
Large malloc(256 MB) returned 0x7f0053eea010
Observe that a new anonymous VMA usually appears.
malloc() often uses mmap() internally for large allocations.
Still, no pages have been touched yet.
```

```sh
(gdb) p $mm->map_count
$37 = 12
```

We can see increase in VMA count. 

We can see the details about new VMA

```sh
/ #  cat /proc/59/maps
00400000-00401000 r--p 00000000 00:15 37619537                           /mnt/mm_lab1
00401000-00496000 r-xp 00001000 00:15 37619537                           /mnt/mm_lab1
00496000-004bd000 r--p 00096000 00:15 37619537                           /mnt/mm_lab1
004be000-004c1000 r--p 000bd000 00:15 37619537                           /mnt/mm_lab1
004c1000-004c4000 rw-p 000c0000 00:15 37619537                           /mnt/mm_lab1
004c4000-004c5000 rw-p 00000000 00:00 0
20f51000-20f74000 rw-p 00000000 00:00 0                                  [heap]
7f0053eea000-7f0063eeb000 rw-p 00000000 00:00 0               # <--- This One
7f0063eeb000-7f0063eef000 r--p 00000000 00:00 0                          [vvar]
7f0063eef000-7f0063ef1000 r--p 00000000 00:00 0                          [vvar_vclock]
7f0063ef1000-7f0063ef3000 r-xp 00000000 00:00 0                          [vdso]
7fff2fb84000-7fff2fba5000 rw-p 00000000 00:00 0                          [stack]
ffffffffff600000-ffffffffff601000 --xp 00000000 00:00 0                  [vsyscall]
```

```sh
/ # cat /proc/59/smaps
7f0053eea000-7f0063eeb000 rw-p 00000000 00:00 0
Size:             262148 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                   4 kB
Pss:                   4 kB
Pss_Dirty:             4 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         0 kB
Private_Dirty:         4 kB
Referenced:            4 kB
Anonymous:             4 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
```

We can see only 4 KB is allocated out of 256 MB.

### State 4: Touched First Byte

```sh
========== State 4 ==========
Touched the FIRST byte.
This should have caused the first page fault.
Only one page should have been allocated.
```

It seems to allocate only 1 page

```sh
/ # grep -i rss /proc/59/status
VmRSS:	     296 kB
RssAnon:	      52 kB
RssFile:	     244 kB
RssShmem:	       0 kB
```

Or it might have done it previously already, as there is no difference here

```sh
7f0053eea000-7f0063eeb000 rw-p 00000000 00:00 0
Size:             262148 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                   4 kB
Pss:                   4 kB
Pss_Dirty:             4 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         0 kB
Private_Dirty:         4 kB
Referenced:            4 kB
Anonymous:             4 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
VmFlags: rd wr mr mw me ac
```

### State 5: Page Fault on Last Byte

```
========== State 5 ==========
Touched the LAST byte.
Another page fault should have occurred.
```

```sh
/ # grep -i rss /proc/59/status
VmRSS:	     300 kB
RssAnon:	      56 kB
RssFile:	     244 kB
RssShmem:	       0 kB
```

Seems like just 1 more page extra again

Yes! its clearly visible here

```sh
7f0053eea000-7f0063eeb000 rw-p 00000000 00:00 0
Size:             262148 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                   8 kB
Pss:                   8 kB
Pss_Dirty:             8 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         0 kB
Private_Dirty:         8 kB
Referenced:            8 kB
Anonymous:             8 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
VmFlags: rd wr mr mw me ac
```

### Step 6: Memry allocated via mmap

```
========== State 6 ==========
Anonymous mmap() returned 0x7f0043eea000
Observe that map_count increased.
No pages have been touched yet.
```

Although our previous mmalloc used `mmap` internally, the difference with using `mmap` ourselves is we have to bookkeep it and its our responsibility to `munmap` it, malloc would've done it for us on calling `free`. On the contrary we get more control on type of flags passed to `mmap`, etc.

```sh
(gdb) p $mm->map_count
$39 = 12
```

Wait! it didn't increase?

```sh
/ # cat /proc/59/maps
00400000-00401000 r--p 00000000 00:15 37619537                           /mnt/mm_lab1
00401000-00496000 r-xp 00001000 00:15 37619537                           /mnt/mm_lab1
00496000-004bd000 r--p 00096000 00:15 37619537                           /mnt/mm_lab1
004be000-004c1000 r--p 000bd000 00:15 37619537                           /mnt/mm_lab1
004c1000-004c4000 rw-p 000c0000 00:15 37619537                           /mnt/mm_lab1
004c4000-004c5000 rw-p 00000000 00:00 0
20f51000-20f74000 rw-p 00000000 00:00 0                                  [heap]
7f0043eea000-7f0063eeb000 rw-p 00000000 00:00 0
7f0063eeb000-7f0063eef000 r--p 00000000 00:00 0                          [vvar]
7f0063eef000-7f0063ef1000 r--p 00000000 00:00 0                          [vvar_vclock]
7f0063ef1000-7f0063ef3000 r-xp 00000000 00:00 0                          [vdso]
7fff2fb84000-7fff2fba5000 rw-p 00000000 00:00 0                          [stack]
ffffffffff600000-ffffffffff601000 --xp 00000000 00:00 0                  [vsyscall]
/ #
```
Nothing new here also?

But if we look carefully here

After the large malloc():

```sh
7f0053eea000-7f0063eeb000 rw-p
```

After your explicit mmap():

```sh
7f0043eea000-7f0063eeb000 rw-p
```

The kernel did not create a second VMA. Instead, it extended the existing anonymous VMA downward and merged the two adjacent mappings because they have identical attributes:

* MAP_PRIVATE
* MAP_ANONYMOUS
* PROT_READ | PROT_WRITE
* same flags
* adjacent virtual addresses

Linux tries to keep the number of VMAs small. Creating a new vm_area_struct is unnecessary if two neighboring mappings are indistinguishable.

A VMA does not represent one mmap() call. It represents one contiguous region of virtual memory with identical attributes. Multiple mmap() calls can end up sharing the same vm_area_struct if the kernel merges them.

If we want to force a new VMA for the experiment, make the mappings differ in some way. 

**Change in RSS**

```sh
/ # grep -i rss /proc/59/status
VmRSS:	     300 kB
RssAnon:	      56 kB
RssFile:	     244 kB
RssShmem:	       0 kB
```

```sh
7f0043eea000-7f0063eeb000 rw-p 00000000 00:00 0
Size:             524292 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                   8 kB
Pss:                   8 kB
Pss_Dirty:             8 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         0 kB
Private_Dirty:         8 kB
Referenced:            8 kB
Anonymous:             8 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
```

### Step 7: Touched First byte of mmap

We can see another page being allocated

```sh
7f0043eea000-7f0063eeb000 rw-p 00000000 00:00 0
Size:             524292 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                  12 kB
Pss:                  12 kB
Pss_Dirty:            12 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         0 kB
Private_Dirty:        12 kB
Referenced:           12 kB
Anonymous:            12 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
VmFlags: rd wr mr mw me ac
```

### Step 8: munmap

```
========== State 8 ==========
munmap() completed.
Observe that the anonymous VMA disappeared.
```

```sh
(gdb) p $mm->map_count
$40 = 12
```

VMA didn't disappear, we expect it to be reduced, let's see. 

```sh
7f0053eea000-7f0063eeb000 rw-p 00000000 00:00 0
Size:             262148 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                   8 kB
Pss:                   8 kB
Pss_Dirty:             8 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         0 kB
Private_Dirty:         8 kB
Referenced:            8 kB
Anonymous:             8 kB
KSM:                   0 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
THPeligible:           0
VmFlags: rd wr mr mw me ac
```

Yes!

### Step 9: Free the malloc'd region

```
========== State 9 ==========
Freed the large malloc allocation.
If it was mmap-backed, its VMA should disappear now.
```

```sh
(gdb) p $mm->map_count
$41 = 11
```

We can see VMA count going down, no further check needed. 

