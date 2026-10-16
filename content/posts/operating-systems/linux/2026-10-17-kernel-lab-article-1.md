---
title: "Inside a Linux Process: My First Kernel Lab"
date: 2026-10-17
categories: ["operating systems", "linux"]
tags: ["kernel", "qemu", "gdb", "task_struct"]
---

# Inside a Linux Process: My First Kernel Lab

I wanted to understand what Linux actually keeps track of when a process runs. So I built a small kernel lab: boot a Linux kernel in QEMU, start a tiny userspace program, pause it at useful moments, and inspect its kernel data structures with GDB.

This is the first article in a series where I’ll use that lab to explore Linux one subsystem at a time. I’ll start with the task and its address space, then follow the connections into virtual memory, the page cache, the VFS, and other parts of the kernel. The goal is to pair the concepts with observations from a running system.

The first structure I looked at was `task_struct`—the kernel's record for a schedulable task. It connects details that user-space programs usually see through separate interfaces: the task's ID and name, its address space, open files, current filesystem context, and scheduler state.

## Why run the kernel in QEMU?

QEMU gives me a disposable virtual machine to boot a kernel I built myself. If I make a mistake, I can restart the VM without disturbing the host. More importantly for this experiment, QEMU's GDB stub lets a debugger on the host stop the virtual machine and inspect the guest kernel's memory and CPU state.

The basic setup has three pieces:

- **`bzImage`**: the bootable kernel image.
- **`vmlinux`**: the matching kernel build with debug symbols for GDB.
- **An initramfs**: a small root filesystem that starts a shell and the lab program.

I boot the guest with QEMU's x86-64 system emulator, pass it the kernel and initramfs, and use a serial console so the shell appears in my terminal. My setup uses `-s` to expose the GDB stub on TCP port 1234. I also pass `nokaslr` while debugging so the kernel's address randomization doesn't move symbols away from the addresses GDB expects. The important detail is that `vmlinux` and `bzImage` must come from the same build: GDB needs symbols that match the code actually running.

My initramfs is intentionally small. I compile the test program statically so it can run there without a full dynamic loader and shared-library tree. Once the guest is up, I can start the program and leave it waiting for input while I inspect it from GDB.

### Connecting GDB and stopping the guest

In one host terminal, I boot QEMU. In another, from the kernel source directory, I load the matching debug-symbol file and connect to QEMU:

```bash
gdb vmlinux
```

```gdb
(gdb) target remote :1234
(gdb) continue
```

`continue` lets the guest run. My test program uses `getchar()` between experiment stages, so it can wait at a known point while I decide what to inspect next. If I want to freeze the whole guest at its current instruction, I press **Ctrl-C in the GDB terminal**. The virtual CPUs stop, and I can examine kernel memory; `continue` resumes the VM. This is different from attaching GDB to the userspace test binary: this GDB session controls the guest kernel through QEMU's system-level stub.

I can also start QEMU with `-S` in addition to `-s` when I want it paused before the kernel begins booting. In that case, connecting GDB and issuing `continue` starts the guest. For this lab I usually let it boot, then interrupt it when the process is at the experiment checkpoint.

## Start with `task_struct`: what is a process to the kernel?

In userspace, I think of a process as a running program with a PID, memory, open files, and a current directory. Tools such as `ps` and files under `/proc` expose parts of that view. Inside the kernel, the central record for each schedulable task is `struct task_struct`.

Linux schedules threads. Each thread has a `task_struct`; threads that belong to the same userspace process can share resources such as the address space and file descriptor table. So `task_struct` is the natural bridge from the familiar process idea to the kernel's implementation: it has identity and scheduling state, plus pointers to the structures that manage memory, files, and filesystem context.

This makes it a useful first structure to inspect. It gives me a stable starting point in the graph of kernel objects. Rather than search memory for an `mm_struct` or a file table, I can find my task and follow the pointers that connect it to those objects.

The real structure is large and changes as Linux evolves. I don't need to memorize every member to get value from it. For this first pass, I focused on a few pointers and identifiers that lead to other parts of the kernel:

```text
task_struct
├── pid / tgid       task ID / thread-group ID
├── comm             short task name
├── mm               user address space (mm_struct)
├── files            open file descriptors (files_struct)
├── fs               filesystem context, including cwd and root
└── parent           parent task
```

This is a map of the fields I chose to inspect, not a declaration copied from the kernel header. In my single-threaded test program, the PID and TGID are both 59. `comm` is the short task name GDB showed as `mm_lab1`.

The distinction between `mm` and `active_mm` is useful too. A normal userspace task has an `mm` for its address space. Kernel threads generally have `mm == NULL`; `active_mm` supports the kernel's use of an address space while such a thread runs. So `active_mm` is not simply another name for the task's own userspace memory.

## Finding the task

The kernel's GDB helpers include `lx-ps`, which lists tasks and their addresses. I used it to find my program by its command name, then asked GDB to interpret that address as a `struct task_struct`. Here's a shortened excerpt from my run:

```gdb
(gdb) lx-ps
      TASK          PID    COMM
...
0xffff888004358000  59   mm_lab1

(gdb) set $task = (struct task_struct *)0xffff888004358000
(gdb) p $task->pid
$1 = 59
(gdb) p $task->comm
$2 = "mm_lab1"
(gdb) p $task->mm
$3 = (struct mm_struct *) 0xffff88800384c5c0
(gdb) p $task->files
$4 = (struct files_struct *) 0xffff8880039dc580
(gdb) p $task->fs
$5 = (struct fs_struct *) 0xffff8880043fe280
```

These addresses are from my run; yours will differ. `lx-ps` walks the kernel's task list and gives me the address I need. From there, GDB can print selected fields. Printing all of `*task` is possible, but it produces pages of scheduler, locking, accounting, and architecture-specific state. Selecting a handful of fields makes the relationships easier to see.

That pointer chain was the useful part for me. Instead of treating a process as one opaque entry in `ps`, I could start from the kernel's task record and follow the links to the subsystems that manage its memory and files. In the next inspection, I followed `mm` into `mm_struct` and looked at fields such as `map_count`, `total_vm`, and the page-table root.

## Follow `mm` into `mm_struct`

The userspace idea of “this process's memory” is not one flat allocation. A program sees a virtual address space: addresses for its code, data, heap, stack, shared libraries, and memory mappings. The kernel's `struct mm_struct` describes that address space and keeps the data needed to manage it.

Here are a few useful landmarks in the structure:

```text
mm_struct
├── mm_mt       index of the address space's VMAs (Maple Tree)
├── map_count   number of VMAs
├── total_vm    total mapped virtual pages
├── pgd         root of the page-table hierarchy
├── start_brk   start of the process heap range
├── brk         current end of the heap range
└── start_stack address marking the user stack's initial location
```

The names connect the high-level picture to specific kernel data. `mm_mt` lets the kernel find the VMA describing a virtual address. `map_count` and `total_vm` summarize that address space in different ways: one counts VMA regions, the other counts virtual pages. `pgd` anchors the page tables used for address translation. The `brk` fields record the traditional heap boundary, while `start_stack` records the stack's initial location. These are only a few fields from a much larger structure.

In my run, the `task_struct`'s `mm` pointer was `0xffff88800384c5c0`. I followed it in GDB:

```gdb
(gdb) set $mm = $task->mm
(gdb) p $mm->map_count
$6 = 11
(gdb) p $mm->total_vm
$7 = 272
(gdb) p $mm->pgd
$8 = (pgd_t *) 0xffff8880045ce000
```

These are values from my run. `map_count` is the number of VMAs currently describing this address space. `total_vm` is measured in pages, not bytes; with the 4 KiB pages in this setup, 272 pages is about 1.06 MiB of virtual memory. That is a measure of mapped virtual space, not proof that all those pages are resident in RAM. `pgd` points to the top-level page-table structure used to translate this process's virtual addresses.

### VMAs describe ranges; page tables translate addresses

An `mm_struct` needs to represent many separate ranges with different purposes and permissions. Linux uses `struct vm_area_struct` (a VMA) for each mapped range with a consistent set of properties. A VMA can describe, for example, the executable code, stack, heap, a shared library, or an `mmap()` region. The `mm_struct` indexes these ranges—in the kernel version I inspected, through a Maple Tree—while the page tables track the translations used by the MMU.

That distinction gave me a path through the memory subsystem:

```text
task_struct
  └── mm → mm_struct
             ├── mm_mt → VMAs (which virtual ranges exist and their permissions)
             └── pgd   → page-table hierarchy (how virtual addresses translate)
```

This is why starting from `task_struct` worked well for me. I began with a concrete userspace process, followed its `mm` pointer to the address-space descriptor, then used the VMA count and page-table root to ask more specific questions. That gives me a starting map for the virtual-memory subsystem articles to come.

## What's next

This first inspection gives me a starting point: a userspace process maps to a task record, and that task points to the structure describing its address space. In the next set of articles, I’ll explore the virtual-memory subsystem in more detail, following how Linux represents memory regions and translates virtual addresses.

---

*Full setup and experiment notes: add link to the lab write-up here.*
