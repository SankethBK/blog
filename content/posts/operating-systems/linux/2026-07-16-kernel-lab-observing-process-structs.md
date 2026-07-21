---
title: "Kernel Lab 1: Observing Process and VFS Structs"
date: 2026-07-16
categories: ["operating systems", "linux"]
tags: ["process", "vfs"]
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

#define SIZE (256UL * 1024 * 1024)   // 256 MB

int main(void)
{
    printf("\n=== State 1 ===\n");
    printf("Program just started.\n");
    printf("Observe task_struct -> mm_struct.\n");
    getchar();

    void *heap = malloc(SIZE);

    printf("\n=== State 2 ===\n");
    printf("malloc() returned %p\n", heap);
    printf("Observe the heap VMA and mm_struct.\n");
    printf("Notice that malloc() itself has NOT touched the memory.\n");
    getchar();

    ((char *)heap)[0] = 1;

    printf("\n=== State 3 ===\n");
    printf("Touched first page.\n");
    printf("A page fault should already have occurred.\n");
    getchar();

    ((char *)heap)[SIZE - 1] = 2;

    printf("\n=== State 4 ===\n");
    printf("Touched the last page.\n");
    getchar();

    void *region = mmap(NULL,
                        SIZE,
                        PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS,
                        -1,
                        0);

    printf("\n=== State 5 ===\n");
    printf("Anonymous mmap() returned %p\n", region);
    printf("Observe that a NEW VMA has appeared.\n");
    printf("Still no pages allocated yet.\n");
    getchar();

    ((char *)region)[0] = 1;

    printf("\n=== State 6 ===\n");
    printf("Touched mmap() region.\n");
    printf("Anonymous page should now exist.\n");
    getchar();

    munmap(region, SIZE);

    printf("\n=== State 7 ===\n");
    printf("munmap() completed.\n");
    printf("Observe that the VMA disappeared.\n");
    getchar();

    free(heap);

    printf("\n=== Done ===\n");
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
0xffff888003998ec0  10   kworker/0:1
0xffff888003999d80  11   kworker/0:0H
0xffff88800399ac40  12   kworker/u4:0
...
0xffff88800404c9c0  46   kworker/0:2
0xffff88800404d880  47   kworker/R-mld
0xffff88800404e740  48   kworker/R-ipv6_
0xffff888004358ec0  59   mm_lab1
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
set $task = (struct task_struct *)0xffff888004349d80

(gdb) p *$task
$1 = {thread_info = {flags = 16384, syscall_work = 0, status = 0, cpu = 0}, __state = 1, saved_state = 0, stack = 0xffffc900001c4000, usage = {refs = {counter = 1}}, flags = 4194304,
  ptrace = 0, on_cpu = 0, wake_entry = {llist = {next = 0x0}, {u_flags = 48, a_flags = {counter = 48}}, src = 0, dst = 0}, wakee_flips = 0, wakee_flip_decay_ts = 0, last_wakee = 0x0,
  recent_used_cpu = 0, wake_cpu = 0, on_rq = 0, prio = 120, static_prio = 120, normal_prio = 120, rt_priority = 0, se = {load = {weight = 1048576, inv_weight = 4194304}, run_node = {
      __rb_parent_color = 1, rb_right = 0x0, rb_left = 0x0}, deadline = 2251603598, min_vruntime = 2251595149, min_slice = 700000, group_node = {next = 0xffff888004358f80,
      prev = 0xffff888004358f80}, on_rq = 0 '\000', sched_delayed = 0 '\000', rel_deadline = 0 '\000', custom_slice = 0 '\000', exec_start = 84723195397, sum_exec_runtime = 96198134,
    prev_sum_exec_runtime = 95553533, vruntime = 2251595149, {vlag = 0, vprot = 0}, slice = 700000, nr_migrations = 0, depth = 0, parent = 0x0, cfs_rq = 0xffff88807dc28a80, my_q = 0x0,
    runnable_weight = 0, avg = {last_update_time = 84723221504, load_sum = 30676, runnable_sum = 30651394, util_sum = 26780840, period_contrib = 369, load_avg = 666, runnable_avg = 650,
      util_avg = 568, util_est = 2147484300}}, rt = {run_list = {next = 0xffff888004359040, prev = 0xffff888004359040}, timeout = 0, watchdog_stamp = 0, time_slice = 100, on_rq = 0,
    on_list = 0, back = 0x0}, dl = {rb_node = {__rb_parent_color = 18446612682140651632, rb_right = 0x0, rb_left = 0x0}, dl_runtime = 0, dl_deadline = 0, dl_period = 0, dl_bw = 0,
    dl_density = 0, runtime = 0, deadline = 0, flags = 0, dl_throttled = 0, dl_yielded = 0, dl_non_contending = 0, dl_overrun = 0, dl_server = 0, dl_server_active = 0, dl_defer = 0,
    dl_defer_armed = 0, dl_defer_running = 0, dl_server_idle = 0, dl_timer = {node = {node = {__rb_parent_color = 18446612682140651720, rb_right = 0x0, rb_left = 0x0}, expires = 0},
      _softexpires = 0, function = 0xffffffff812e7530 <dl_task_timer>, base = 0xffff88807dc1bb00, state = 0 '\000', is_rel = 0 '\000', is_soft = 0 '\000', is_hard = 1 '\001'},
    inactive_timer = {node = {node = {__rb_parent_color = 18446612682140651784, rb_right = 0x0, rb_left = 0x0}, expires = 0}, _softexpires = 0,
      function = 0xffffffff812e4760 <inactive_task_timer>, base = 0xffff88807dc1bb00, state = 0 '\000', is_rel = 0 '\000', is_soft = 0 '\000', is_hard = 1 '\001'}, rq = 0x0,
    server_has_tasks = 0x0, server_pick_task = 0x0, pi_se = 0xffff888004359070}, dl_server = 0x0, sched_class = 0xffffffff82882480 <fair_sched_class>,
  sched_task_group = 0xffffffff83557c00 <root_task_group>, stats = {wait_start = 0, wait_max = 0, wait_count = 0, wait_sum = 0, iowait_count = 0, iowait_sum = 0, sleep_start = 0,
    sleep_max = 0, sum_sleep_runtime = 0, block_start = 0, block_max = 0, sum_block_runtime = 0, exec_max = 0, slice_max = 0, nr_migrations_cold = 0, nr_failed_migrations_affine = 0,
    nr_failed_migrations_running = 0, nr_failed_migrations_hot = 0, nr_forced_migrations = 0, nr_wakeups = 0, nr_wakeups_sync = 0, nr_wakeups_migrate = 0, nr_wakeups_local = 0,
    nr_wakeups_remote = 0, nr_wakeups_affine = 0, nr_wakeups_affine_attempts = 0, nr_wakeups_passive = 0, nr_wakeups_idle = 0}, btrace_seq = 0, policy = 0, max_allowed_capacity = 1024,
  nr_cpus_allowed = 1, cpus_ptr = 0xffff8880043592a8, user_cpus_ptr = 0x0, cpus_mask = {bits = {1}}, migration_pending = 0x0, migration_disabled = 0, migration_flags = 0,
  rcu_read_lock_nesting = 0, rcu_read_unlock_special = {b = {blocked = 0 '\000', need_qs = 0 '\000', exp_hint = 0 '\000', need_mb = 0 '\000'}, s = 0}, rcu_node_entry = {
    next = 0xffff8880043592c8, prev = 0xffff8880043592c8}, rcu_blocked_node = 0x0, rcu_tasks_nvcsw = 0, rcu_tasks_holdout = 0 '\000', rcu_tasks_idx = 0 '\000', rcu_tasks_idle_cpu = -1,
  rcu_tasks_holdout_list = {next = 0xffff8880043592f0, prev = 0xffff8880043592f0}, rcu_tasks_exit_cpu = 0, rcu_tasks_exit_list = {next = 0xffff888004359308, prev = 0xffff888004359308},
  trc_reader_nesting = 0, trc_ipi_to_cpu = 0, trc_reader_special = {b = {blocked = 0 '\000', need_qs = 0 '\000', exp_hint = 0 '\000', need_mb = 0 '\000'}, s = 0}, trc_holdout_list = {
    next = 0xffff888004359328, prev = 0xffff888004359328}, trc_blkd_node = {next = 0xffff888004359338, prev = 0xffff888004359338}, trc_blkd_cpu = 0, sched_info = {pcount = 160,
    run_delay = 16052084, max_run_delay = 841109, min_run_delay = 13356, last_arrival = 84722550796, last_queued = 0}, tasks = {next = 0xffffffff82a0edc0 <init_task+1216>,
    prev = 0xffff88800404ec00}, pushable_tasks = {prio = 140, prio_list = {next = 0xffff888004359398, prev = 0xffff888004359398}, node_list = {next = 0xffff8880043593a8,
      prev = 0xffff8880043593a8}}, pushable_dl_tasks = {__rb_parent_color = 18446612682140652472, rb_right = 0x0, rb_left = 0x0}, mm = 0xffff88800384cb80, active_mm = 0xffff88800384cb80,
  faults_disabled_mapping = 0x0, exit_state = 0, exit_code = 0, exit_signal = 17, pdeath_signal = 0, jobctl = 0, personality = 0, sched_reset_on_fork = 0, sched_contributes_to_load = 0,
  sched_migrated = 0, sched_task_hot = 0, sched_remote_wakeup = 0, sched_rt_mutex = 0, in_execve = 0, in_iowait = 0, restore_sigmask = 0, no_cgroup_migration = 0, frozen = 0,
  use_memdelay = 0, in_eventfd = 0, pasid_activated = 0, reported_split_lock = 0, in_thrashing = 0, in_nf_duplicate = 0, atomic_flags = 0, restart_block = {arch_data = 0,
    fn = 0xffffffff812a1150 <do_no_restart_syscall>, {futex = {uaddr = 0x0, val = 0, flags = 0, bitset = 0, time = 0, uaddr2 = 0x0}, nanosleep = {clockid = 0, type = TT_NONE, {rmtp = 0x0,
          compat_rmtp = 0x0}, expires = 0}, poll = {ufds = 0x0, nfds = 0, has_timeout = 0, tv_sec = 0, tv_nsec = 0}}}, pid = 59, tgid = 59, stack_canary = 14143545020011660800,
  real_parent = 0xffff888003988000, parent = 0xffff888003988000, children = {next = 0xffff888004359470, prev = 0xffff888004359470}, sibling = {next = 0xffff8880039885b0,
    prev = 0xffff8880039885b0}, group_leader = 0xffff888004358ec0, ptraced = {next = 0xffff888004359498, prev = 0xffff888004359498}, ptrace_entry = {next = 0xffff8880043594a8,
    prev = 0xffff8880043594a8}, thread_pid = 0xffff88800457dc00, pid_links = {{next = 0x0, pprev = 0xffff88800457dc40}, {next = 0x0, pprev = 0xffff88800457dc48}, {next = 0xffff88800404ed60,
      pprev = 0xffffffff82a547d0 <init_struct_pid+80>}, {next = 0xffff88800404ed70, pprev = 0xffffffff82a547d8 <init_struct_pid+88>}}, thread_node = {next = 0xffff888003bea410,
    prev = 0xffff888003bea410}, vfork_done = 0x0, set_child_tid = 0x0, clear_child_tid = 0x0, worker_private = 0x0, utime = 16000000, stime = 62000000, gtime = 0, prev_cputime = {utime = 0,
--Type <RET> for more, q to quit, c to continue without paging--
    stime = 0, lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}, nvcsw = 63, nivcsw = 97, start_time = 84486717184,
  start_boottime = 84486719203, min_flt = 18, maj_flt = 56, posix_cputimers = {bases = {{nextevt = 18446744073709551615, tqhead = {rb_root = {rb_root = {rb_node = 0x0},
            rb_leftmost = 0x0}}}, {nextevt = 18446744073709551615, tqhead = {rb_root = {rb_root = {rb_node = 0x0}, rb_leftmost = 0x0}}}, {nextevt = 18446744073709551615, tqhead = {
          rb_root = {rb_root = {rb_node = 0x0}, rb_leftmost = 0x0}}}}, timers_active = 0, expiry_active = 0}, posix_cputimers_work = {work = {next = 0x0,
      func = 0xffffffff81360cf0 <posix_cpu_timers_work>}, mutex = {owner = {counter = 0}, wait_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {
              locked_pending = 0, tail = 0}}}}, osq = {tail = {counter = 0}}, wait_list = {next = 0xffff888004359600, prev = 0xffff888004359600}}, scheduled = 0}, ptracer_cred = 0x0,
  real_cred = 0xffff88800457d840, cred = 0xffff88800457d840, cached_requested_key = 0x0, comm = "mm_lab1\000\000\000\000\000\000\000\000", nameidata = 0x0, sysvsem = {undo_list = 0x0},
  sysvshm = {shm_clist = {next = 0xffff888004359658, prev = 0xffff888004359658}}, fs = 0xffff8880043f8200, files = 0xffff8880039dc2c0, io_uring = 0x0,
  nsproxy = 0xffffffff82a548c0 <init_nsproxy>, signal = 0xffff888003bea400, sighand = 0xffff8880043398c0, blocked = {sig = {0}}, real_blocked = {sig = {0}}, saved_sigmask = {sig = {0}},
  pending = {list = {next = 0xffff8880043596b0, prev = 0xffff8880043596b0}, signal = {sig = {0}}}, sas_ss_sp = 0, sas_ss_size = 0, sas_ss_flags = 2, task_works = 0x0, audit_context = 0x0,
  loginuid = {val = 4294967295}, sessionid = 4294967295, seccomp = {mode = 0, filter_count = {counter = 0}, filter = 0x0}, syscall_dispatch = {selector = 0x0, offset = 0, len = 0,
    on_dispatch = false}, parent_exec_id = 2, self_exec_id = 3, alloc_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0,
              tail = 0}}}}}}, pi_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, wake_q = {next = 0x0}, pi_waiters = {
    rb_root = {rb_node = 0x0}, rb_leftmost = 0x0}, pi_top_task = 0x0, pi_blocked_on = 0x0, blocked_on = 0x0, journal_info = 0x0, bio_list = 0x0, plug = 0x0, reclaim_state = 0x0,
  io_context = 0x0, capture_control = 0x0, ptrace_message = 0, last_siginfo = 0x0, ioac = {rchar = 816, wchar = 73, syscr = 2, syscw = 4, read_bytes = 230192, write_bytes = 0,
    cancelled_write_bytes = 0}, acct_rss_mem1 = 408202, acct_vm_mem1 = 18578072, acct_timexpd = 78000000, mems_allowed = {bits = {1}}, mems_allowed_seq = {seqcount = {sequence = 0}},
  cpuset_mem_spread_rotor = -1, cgroups = 0xffffffff82b4d2c0 <init_css_set>, cg_list = {next = 0xffffffff82b4d350 <init_css_set+144>, prev = 0xffff88800404f098}, robust_list = 0x0,
  compat_robust_list = 0x0, pi_state_list = {next = 0xffff888004359838, prev = 0xffff888004359838}, pi_state_cache = 0x0, futex_exit_mutex = {owner = {counter = 0}, wait_lock = {raw_lock = {
        {val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, osq = {tail = {counter = 0}}, wait_list = {next = 0xffff888004359860,
      prev = 0xffff888004359860}}, futex_state = 0, perf_recursion = "\000\000\000", perf_event_ctxp = 0x0, perf_event_mutex = {owner = {counter = 0}, wait_lock = {raw_lock = {{val = {
            counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, osq = {tail = {counter = 0}}, wait_list = {next = 0xffff888004359890,
      prev = 0xffff888004359890}}, perf_event_list = {next = 0xffff8880043598a0, prev = 0xffff8880043598a0}, perf_ctx_data = 0x0, mempolicy = 0x0, il_prev = 0, il_weight = 0 '\000',
  pref_node_fork = 0, rseq = 0x0, rseq_len = 0, rseq_sig = 0, rseq_event_mask = 1, mm_cid = -1, last_mm_cid = 0, migrate_from_cpu = -1, mm_cid_active = 1, cid_work = {
    next = 0xffff8880043598f0, func = 0xffffffff812cc0f0 <task_mm_cid_work>}, tlb_ubc = {arch = {cpumask = {bits = {0}}, unmapped_pages = false}, flush_required = false, writable = false},
  splice_pipe = 0x0, task_frag = {page = 0x0, offset = 0, size = 0}, delays = 0x0, nr_dirtied = 0, nr_dirtied_pause = 32, dirty_paused_when = 0, timer_slack_ns = 50000,
  default_timer_slack_ns = 50000, trace_recursion = 0, throttle_disk = 0x0, utask = 0x0, kmap_ctrl = {<No data fields>}, rcu = {next = 0x0, func = 0x0}, rcu_users = {refs = {counter = 2}},
  pagefault_disabled = 0, oom_reaper_list = 0x0, oom_reaper_timer = {entry = {next = 0x0, pprev = 0x0}, expires = 0, function = 0x0, flags = 0}, stack_vm_area = 0xffff8880043f79c0,
  stack_refcount = {refs = {counter = 1}}, security = 0x0, bpf_net_context = 0x0, mce_vaddr = 0x0, mce_kflags = 0, mce_addr = 0, mce_ripv = 0, mce_whole_page = 0, __mce_reserved = 0,
  mce_kill_me = {next = 0x0, func = 0x0}, mce_count = 0, kretprobe_instances = {first = 0x0}, rethooks = {first = 0x0}, l1d_flush_kill = {next = 0x0, func = 0x0}, thread = {tls_array = {{
        limit0 = 0, base0 = 0, base1 = 0, type = 0, s = 0, dpl = 0, p = 0, limit1 = 0, avl = 0, l = 0, d = 0, g = 0, base2 = 0}, {limit0 = 0, base0 = 0, base1 = 0, type = 0, s = 0, dpl = 0,
        p = 0, limit1 = 0, avl = 0, l = 0, d = 0, g = 0, base2 = 0}, {limit0 = 0, base0 = 0, base1 = 0, type = 0, s = 0, dpl = 0, p = 0, limit1 = 0, avl = 0, l = 0, d = 0, g = 0,
        base2 = 0}}, sp = 18446683600571890616, es = 0, ds = 0, fsindex = 0, gsindex = 0, fsbase = 620886144, gsbase = 0, ptrace_bps = {0x0, 0x0, 0x0, 0x0}, virtual_dr6 = 0, ptrace_dr7 = 0,
    cr2 = 0, trap_nr = 0, error_code = 0, io_bitmap = 0x0, iopl_emul = 0, iopl_warn = 0, pkru = 0}}
(gdb)
```

```sh
(gdb) p $task->comm
$2 = "mm_lab1\000\000\000\000\000\000\000\000"
(gdb) p $task->pid
$3 = 61
```

`$task->comm` is the command with which the process was started, padded to 16 chars. 

```sh
(gdb) p $task->mm
$2 = (struct mm_struct *) 0xffff88800384cb80
(gdb) p $task->active_mm
$3 = (struct mm_struct *) 0xffff88800384cb80
(gdb)  p $task->files
$4 = (struct files_struct *) 0xffff8880039dc2c0
(gdb) p $task->fs
$5 = (struct fs_struct *) 0xffff8880043f8200
(gdb)
```

```sh
(gdb) p $task->stack
$6 = (void *) 0xffffc900001c4000
```

This is the address of kernel stack. 

**Why it matters:** Every process in Linux has two stacks: a user-space stack (managed by rsp) and a dedicated kernel-space stack (typically 16 KB on x86_64).

**How it works:** When mm_lab1 executes a system call (like mmap() or read()), the CPU hardware automatically switches execution from the user stack to this exact address space in kernel memory. The top of this stack holds the pt_regs structure, which saves user-space CPU registers during system calls or interrupts.

### Observing the mm_struct

#### 1. Printing the mm_struct

```sh
(gdb) set $mm = $task->mm
(gdb) p *$mm
$8 = {{{mm_count = {counter = 2}}, mm_mt = {{ma_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}},
        ma_external_lock = {<No data fields>}}, ma_flags = 779, ma_root = 0xffff888004501b1e}, mmap_base = 140066625462272, mmap_legacy_base = 47566169706496, mmap_compat_base = 4160397312,
    mmap_compat_legacy_base = 1431998464, task_size = 140737488351232, pgd = 0xffff888004597000, membarrier_state = {counter = 0}, mm_users = {counter = 1}, pcpu_cid = 0xffffffff835389c0,
    mm_cid_next_scan = 4294751879, nr_cpus_allowed = 1, max_nr_cid = {counter = 1}, cpus_allowed_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {
            locked_pending = 0, tail = 0}}}}, pgtables_bytes = {counter = 40960}, map_count = 11, page_table_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000',
                pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}}, mmap_lock = {count = {counter = 0}, owner = {counter = -131391568900415}, osq = {tail = {counter = 0}},
      wait_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, wait_list = {next = 0xffff88800384cc50,
        prev = 0xffff88800384cc50}}, mmlist = {next = 0xffff88800384cc60, prev = 0xffff88800384cc60}, vma_writer_wait = {task = 0x0}, mm_lock_seq = {sequence = 28}, futex_hash_lock = {
      owner = {counter = 0}, wait_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, osq = {tail = {counter = 0}},
      wait_list = {next = 0xffff88800384cc90, prev = 0xffff88800384cc90}}, futex_phash = 0x0, futex_phash_new = 0x0, futex_batches = 920, futex_rcu = {next = 0x0, func = 0x0},
    futex_atomic = {counter = 0}, futex_ref = 0x0, hiwater_rss = 0, hiwater_vm = 0, total_vm = 271, locked_vm = 0, pinned_vm = {counter = 0}, data_vm = 39, exec_vm = 150, stack_vm = 33,
    def_flags = 0, write_protect_seq = {sequence = 0}, arg_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}},
    start_code = 4198400, end_code = 4803921, start_data = 4968640, end_data = 4989456, start_brk = 620883968, brk = 621027328, start_stack = 140728151635392, arg_start = 140728151637944,
    arg_end = 140728151637954, env_start = 140728151637954, env_end = 140728151637998, saved_auxv = {33, 140066625454080, 51, 1440, 16, 126614525, 6, 4096, 17, 100, 3, 4194368, 4, 56, 5,
      10, 7, 0, 8, 0, 9, 4201536, 11, 0, 12, 0, 13, 0, 14, 0, 23, 0, 25, 140728151635833, 26, 0, 31, 140728151637998, 15, 140728151635849, 27, 28, 28, 32, 0, 0, 0, 0, 0, 0, 0, 0},
    rss_stat = {{lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, count = 32, list = {next = 0xffff8880042d5150,
          prev = 0xffff88800384cf58}, counters = 0xffffffff835389d0}, {lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}},
        count = 0, list = {next = 0xffff88800384cf30, prev = 0xffff88800384cf80}, counters = 0xffffffff835389d4}, {lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000',
                pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, count = 0, list = {next = 0xffff88800384cf58, prev = 0xffff88800384cfa8}, counters = 0xffffffff835389d8}, {lock = {
          raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, count = 0, list = {next = 0xffff88800384cf80,
          prev = 0xffffffff82bd7c20 <percpu_counters>}, counters = 0xffffffff835389dc}}, binfmt = 0xffffffff82b7ce20 <elf_format>, context = {ctx_id = 20, tlb_gen = {counter = 4},
      next_trim_cpumask = 4294752646, ldt_usr_sem = {count = {counter = 0}, owner = {counter = 0}, osq = {tail = {counter = 0}}, wait_lock = {raw_lock = {{val = {counter = 0}, {
                locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, wait_list = {next = 0xffff88800384cff8, prev = 0xffff88800384cff8}}, ldt = 0x0, flags = 2, lock = {
        owner = {counter = 0}, wait_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, osq = {tail = {counter = 0}},
        wait_list = {next = 0xffff88800384d028, prev = 0xffff88800384d028}}, vdso = 0x7f63cd748000, vdso_image = 0xffffffff82201140 <vdso_image_64>, perf_rdpmc_allowed = {counter = 0},
      pkey_allocation_map = 0, execute_only_pkey = 0, global_asid = 0, asid_transition = false}, flags = 2147483853, ioctx_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {
                locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}}, ioctx_table = 0x0, user_ns = 0xffffffff82a534a0 <init_user_ns>, exe_file = 0xffff88800408c180,
    notifier_subscriptions = 0x0, tlb_flush_pending = {counter = 0}, tlb_flush_batched = {counter = 0}, uprobes_state = {xol_area = 0x0}, hugetlb_usage = {counter = 0}, async_put_work = {
      data = {counter = 0}, entry = {next = 0x0, prev = 0x0}, func = 0x0}, iommu_mm = 0x0}, cpu_bitmap = 0xffff88800384d100}
(gdb)
```

#### 2. Printing the segment related fields

```sh
(gdb) p $mm->start_code
$9 = 4198400
(gdb) p $mm->end_code
$10 = 4803921
(gdb) p $mm->start_data
$11 = 4968640
(gdb) p $mm->end_data
$12 = 4989456
(gdb) p $mm->start_brk
$13 = 620883968
(gdb) p $mm->brk

$14 = 621027328
(gdb) p $mm->start_stack
$15 = 140728151635392
(gdb) p $mm->arg_start
$16 = 140728151637944
(gdb) p $mm->arg_end
$17 = 140728151637954
(gdb) p $mm->env_start
$18 = 140728151637954
(gdb) p $mm->env_end
$19 = 140728151637998
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