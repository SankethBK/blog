---
title:  "Virtualization of the CPU - The Process"
date:   2026-03-03
categories: ["operating systems"]
tags: ["virtualization", "process", "fork", "exec", "wait"]

---

# Virtualizing the CPU — The Process

## The Core Idea

The OS virtualizes the CPU by running one process, stopping it, running another, and so on. Done fast enough, this creates the illusion that many programs run simultaneously on what might be a single CPU core.

The abstraction the OS exposes for this is the **Process** — simply put, a running program.

> A program is a lifeless set of instructions sitting on disk. A process is that program, brought to life by the OS.

---

## What Makes Up a Process?

To understand a process, you need to know what state it holds — what it would need to be paused and resumed perfectly:

**1. Address Space (Memory)**
- **Code (text)** — the program's instructions
- **Stack** — function calls, local variables, return addresses; grows/shrinks as functions are called and returned
- **Heap** — dynamically allocated memory (malloc/free); grows explicitly at runtime
- **Static/global data** — globals and constants

**2. CPU Registers**
The process's current computation state:
- **Program Counter (PC)** — which instruction to execute next
- **Stack Pointer (SP) & Frame Pointer (FP)** — track the current position in the stack
- **General-purpose registers** — intermediate computation values

**3. I/O State**
- Open files, network connections, devices the process is currently using
- In Unix, every process starts with three open by default: `stdin`, `stdout`, `stderr`

---

## How the OS Creates a Process

When you run a program, the OS follows these steps:

1. **Load** the program's code and static data from disk into memory (its address space)
2. **Allocate** memory for the stack and initialize it (push `argc`, `argv`)
3. **Allocate** memory for the heap (initially small, grows on demand)
4. **Set up I/O** — wire up stdin, stdout, stderr
5. **Jump to `main()`** — hand control over to the process

> **Eager vs Lazy Loading:** Early OSes loaded the entire program into memory upfront (eager). Modern OSes load only what's needed, on demand (lazy) — this is the foundation of paging and virtual memory.

---

## Process States

At any point, a process is in one of three states:

```
         scheduled
  Ready ──────────► Running
    ▲                  │
    │   descheduled    │  initiates I/O
    └──────────────────┘
                       │
                       ▼
                   Blocked ──► (I/O completes) ──► Ready
```

- **Running** — currently executing on the CPU
- **Ready** — able to run, but waiting for the OS to schedule it
- **Blocked** — waiting for an external event (I/O, timer, lock) — cannot run even if CPU is free

Key insight: a blocked process voluntarily gives up the CPU. The OS doesn't waste the CPU waiting — it runs another ready process instead. This is how overlap between computation and I/O is achieved.

---

## The Process Control Block (PCB)

The OS tracks every process using a data structure called the **Process Control Block (PCB)** — also called a *task struct* in Linux.

It stores everything about a process:
- Its current **state** (running, ready, blocked)
- Its saved **register values** (when not running)
- Its **memory mappings**
- Its **open files**
- Its **PID** (process identifier) and metadata (owner, priority, etc.)

The OS maintains a **process list** (or task list) — a collection of all PCBs for all currently existing processes.

---

## Context Switching — The Mechanism Behind the Illusion

When the OS switches from one process to another:

1. **Save** the current process's register state into its PCB
2. **Restore** the next process's register state from its PCB
3. **Switch** the PC to where that process left off

This is a **context switch**. It's cheap but not free — there's overhead in saving/restoring state and cache effects. Good OS design minimizes unnecessary switches.

---

## Key Takeaway

The process is the OS's answer to CPU virtualization:
- It wraps a program in its own execution environment (memory + registers + I/O)
- The OS time-shares the CPU across processes via context switching
- Each process is tracked via a PCB in the process list
- The three states (running, ready, blocked) capture the full lifecycle of a process's relationship with the CPU

> The OS is the magician. The process is the trick. The CPU is the single hand doing everything at once.

# Interlude: Process API

> This chapter is less about theory and more about *why* Unix designed process creation the way it did — and why it's actually a clever design despite feeling weird at first.

---

## The Unix Process API — Three Core Calls

| Call | What it does |
|---|---|
| `fork()` | Create a new process (clone of caller) |
| `exec()` | Replace current process image with a new program |
| `wait()` | Parent waits for child to finish |

The immediately strange thing: **why does creating a process take two calls?** Every other OS just has one — `CreateProcess()` on Windows, for example. Unix splits it into `fork()` + `exec()`. This is deliberate, and the reasoning is elegant.

---

## `fork()` — Cloning the Caller

```c
#include <stdio.h>
#include <unistd.h>

int main() {
    printf("hello from pid %d\n", getpid());

    int rc = fork();

    if (rc < 0) {
        // fork failed
        fprintf(stderr, "fork failed\n");
    } else if (rc == 0) {
        // child
        printf("child (pid %d)\n", getpid());
    } else {
        // parent — rc is child's pid
        printf("parent of %d (my pid %d)\n", rc, getpid());
    }
    return 0;
}
```

**What happens:**
- After `fork()`, two processes exist — both about to execute the line after `fork()`
- They are nearly identical: same code, same stack, same open files, same everything
- The **only difference** is the return value: parent gets child's PID, child gets `0`
- The order of execution (parent first or child first) is **non-deterministic** — up to the scheduler

> The child is not a blank process. It is a near-perfect clone of the parent at the moment `fork()` was called. This is the key to understanding why the design works.

---

## `wait()` — Synchronizing with the Child

```c
int rc = fork();
if (rc == 0) {
    printf("child\n");
} else {
    int wc = wait(NULL);  // parent blocks until a child exits
    printf("parent: child %d finished\n", wc);
}
```

- `wait()` blocks the parent until **one of its children exits**
- Returns the PID of the child that exited
- Without `wait()`, output order is non-deterministic. With it, child always prints first
- `waitpid(pid, &status, options)` is the more precise variant — wait for a *specific* child and retrieve its exit status

**The ZOMBIE state:** When a child exits, it doesn't immediately disappear. It becomes a **zombie** — its exit status is preserved until the parent calls `wait()` to collect it. Only then is the process fully cleaned up.

If the parent never calls `wait()`, zombies accumulate. If the parent exits first, the children become **orphans** — xv6 and Linux re-parent them to `init` (PID 1), which perpetually calls `wait()` to reap them.

---

## `exec()` — Becoming a New Program

```c
int rc = fork();
if (rc == 0) {
    // child: replace itself with /bin/ls
    char *args[] = { "ls", "-l", NULL };
    execvp("ls", args);
    // if exec returns, something went wrong
    fprintf(stderr, "exec failed\n");
}
```

- `exec()` loads a new program into the current process's address space
- It **does not create a new process** — same PID, same open files, same kernel state
- It **never returns on success** — the calling code is gone, replaced by the new program
- The new program starts fresh: new code, new stack, new heap — but inherits FDs, PID, etc.

**exec variants** (`unistd.h`):

| Variant | Args | Path search |
|---|---|---|
| `execv` | array | no |
| `execvp` | array | yes (uses PATH) |
| `execve` | array + env | no |
| `execl` | variadic | no |
| `execlp` | variadic | yes |

---

## The Weird Design — Why Two Calls?

This is the core question of the chapter. Why not one call like:

```c
createprocess("ls", args);  // Windows style
```

The answer: **the gap between `fork()` and `exec()` is intentional and powerful.**

In that gap, the child is a running process with full capabilities — but hasn't yet become the new program. The shell exploits this window to set up the environment before `exec()`:

### 1. I/O Redirection

```c
// shell implementing: ls > output.txt
int rc = fork();
if (rc == 0) {
    close(STDOUT_FILENO);               // close stdout
    open("output.txt", O_CREAT|O_WRONLY|O_TRUNC, 0644);  // fd 1 now points to file
    execvp("ls", args);
    // ls inherits fd 1 = output.txt — it never knew about the redirection
}
```

`ls` just writes to `stdout` (fd 1) like normal. The shell silently rewired where fd 1 points *before* exec. The program being run needs zero awareness of redirection. This is only possible because of the fork/exec gap.

### 2. Pipes

```c
// shell implementing: ls | wc
int pipefd[2];
pipe(pipefd);  // pipefd[0] = read end, pipefd[1] = write end

if (fork() == 0) {
    // child 1: ls — stdout → pipe write end
    close(STDOUT_FILENO);
    dup2(pipefd[1], STDOUT_FILENO);
    close(pipefd[0]); close(pipefd[1]);
    execvp("ls", ...);
}
if (fork() == 0) {
    // child 2: wc — stdin ← pipe read end
    close(STDIN_FILENO);
    dup2(pipefd[0], STDIN_FILENO);
    close(pipefd[0]); close(pipefd[1]);
    execvp("wc", ...);
}
close(pipefd[0]); close(pipefd[1]);
wait(NULL); wait(NULL);
```

Two children, each with their stdio rewired to opposite ends of the same pipe. Neither `ls` nor `wc` knows about the pipe — they just read/write stdio. Again, only possible in the fork/exec gap.

### 3. Environment setup, resource limits, signal masks...

The same pattern extends to: setting env variables, adjusting `ulimit`, setting up `chroot` jails, dropping privileges, closing sensitive FDs — all done in the child after `fork()`, before `exec()`.

---

## The Core Insight

> `fork()` + `exec()` separates **"create a process"** from **"load a program"**. The gap between them is where Unix composability lives.

A single `CreateProcess()` call would need hundreds of parameters to cover everything the shell can do in that gap — and it still wouldn't be as flexible. Windows `CreateProcess()` indeed takes 10 parameters and still requires separate mechanisms for redirection.

The Unix design instead gives you a programmable process in that gap — far more powerful than any parameter list.

---

## Summary

```
fork()                    exec()
  │                         │
  │   ← the gap →           │
  │                         │
clone of parent        new program image
same FDs               same PID
same env               same open FDs (inherited)
CPL=3                  fresh stack/heap/code
  │                         │
  └── set up stdio ─────────┘
      pipes, env,
      limits, etc.
```

- `fork()` clones. `exec()` replaces. `wait()` synchronizes.
- The fork/exec gap is not a quirk — it is the entire point of the design.
- Every Unix shell feature (pipes, redirection, backgrounding) is built on this gap.

# xv6 — Process Creation & Data Structures

xv6 is a clean, minimal Unix-like OS (~10k lines). It's ideal for reading because there's no noise — every line is doing real OS work.


## The `proc` Struct — xv6's PCB

```c
struct proc {
  uint sz;                     // Size of process memory (bytes)
  pde_t* pgdir;                // Page table
  char *kstack;                // Bottom of kernel stack for this process
  enum procstate state;        // Process state
  int pid;                     // Process ID
  struct proc *parent;         // Parent process
  struct trapframe *tf;        // Trap frame for current syscall
  struct context *context;     // swtch() here to run process
  void *chan;                  // If non-zero, sleeping on chan
  int killed;                  // If non-zero, have been killed
  struct file *ofile[NOFILE];  // Open files
  struct inode *cwd;           // Current directory
  char name[16];               // Process name (debugging)
};
```

This is xv6’s Process Control Block (PCB).

Conceptually a process consists of:

```
Address space
Registers
Kernel stack
Open files
Process state
```

Think of it as containing three categories of data:

```
1) Memory management
2) CPU execution state
3) OS bookkeeping
```

### 1. sz

```c
uint sz;
```

Size of the process’s user memory in bytes.

If a process has:

```
code + data + heap + stack
```

their total size is stored here.

**Where it’s used?**

In memory allocation:

```c
growproc()
```

which expands process memory when `sbrk()` is called.

Relevant code:

```c
proc->sz = newsz;
```

### 2. pgdir

```c
pde_t *pgdir;
```

`pde_t` is a typedef to unsigned integer

```c
typedef unsigned int   uint;
typedef unsigned short ushort;
typedef unsigned char  uchar;
typedef uint pde_t;
```

The first 3 are just convenience aliasing. These are pure shorthand. uint means nothing more than "unsigned int, but shorter to type." Purely cosmetic.

`pde_t` says: "this isn't just any uint — it's specifically a Page Directory Entry."

**Why It Matters**
`pde_t` is a `uint` underneath, but the typedef communicates:

- **Intent** — when you see `pde_t *pgdir`, you immediately know this is a page directory, not a random integer array
- **Grep-ability** — search `pde_t` in the codebase and find every place page directory entries are touched. Search uint and you get noise
- **Future-proofing** — if xv6 ever moved to 64-bit, you change one line (`typedef uint64 pde_t`) and everything using `pde_t` updates automatically. Everything using raw uint breaks

**What it is**

Pointer to the page directory (top-level page table).

This defines the virtual address space of the process.

Each process has its own page table.

**Where used**

When switching processes:

```c
switchuvm(p)
```

This loads the process’s page table into CR3.

### 3. kstack

```c
char *kstack;
```

**What it is**

Pointer to the bottom of the kernel stack for this process.

Important idea:

A process has two stacks:

```
User stack
Kernel stack
```

Kernel stack is used when the process enters the kernel via:

```
syscall
interrupt
trap
```

**Why per-process kernel stack?**

Because while a process is inside kernel code it still needs stack space.

**Where created**

In:

```c
allocproc()
p->kstack = kalloc();
```

#### Why do we need kernel stack?

It's just a normal stack — grows downward, holds stack frames, return addresses, local variables — but it only gets used when that process is executing kernel code. Same mechanics, different privilege level.

**Per-process kernel stack (what xv6 does)**

Each process gets its own private kernel stack, allocated with `kalloc()` — one page (4096 bytes). When process A makes a syscall, it uses A's kernel stack. When process B makes a syscall, it uses B's kernel stack. They never share.

Imagine two processes:

```
Process A
Process B
```

Timeline:

```
A enters kernel (syscall)
A executing in kernel
Scheduler switches to B
B enters kernel
```

If both used the same stack, A’s stack frames would be overwritten.

So each process must have its own kernel stack.

Since multiple process can trigger syscalls at the same time, kernel needs to keep track of all of them. Thus, we need per-process kernel stacks. 

Kernel stack holds things like:

```
local variables
function calls
return addresses
trapframe
context
```

Example stack during syscall:

```
| local variables      |
| kernel function call |
| trapframe            |
| context              |
```

All inside that process’s kernel stack.

#### The Kernel Is Also a Program - Does it has its own stack?

The kernel is a C program. Does it have its own stack while executing code independent of any process?

**Yes — but kernel execution always happens in the context of something.**

There are two possibilities:

##### Case 1 — Kernel Running On Behalf of a Process

Example:

```c
write()
fork()
read()
```

Kernel runs using the process’s kernel stack.

So stack used is:

```c
proc->kstack
```

##### Case 2 — Kernel Running Its Own Threads

Example:

```c
scheduler()
interrupt handlers
```

In xv6, these run using a CPU scheduler stack.

Each CPU has its own structure:

```c
struct cpu {
  struct context *scheduler;
};
```

The scheduler has its own stack.

So:

```
scheduler stack
process kernel stacks
```

both exist.

### 4. state

```c
enum procstate state;
```

**What it is**

The current state of the process.

Possible values:

```c
enum procstate { UNUSED, EMBRYO, SLEEPING, RUNNABLE, RUNNING, ZOMBIE };
```

Example transitions

```c
fork()
UNUSED → EMBRYO

scheduler picks it
RUNNABLE → RUNNING

sleep()
RUNNING → SLEEPING

exit()
RUNNING → ZOMBIE
```

Scheduler decisions depend on this field.

### 5. pid

```c
int pid;
```

**What it is**

Unique process identifier.

Assigned when process is created.

Example:

```
init = PID 1
shell = PID 2
```

Generated by:

```c
nextpid++
```

in allocproc().

### 6. parent

```c
struct proc *parent;
```

**What it is**

Pointer to the parent process.

Example:

```
shell
 └── fork()
      └── child process
```

**Why needed?**

Used for:

```c
wait()
exit()
```

When child exits:

```
parent must reap it
```

This pointer helps locate parent.

### 7. tf

```c
struct trapframe *tf;
```

**What it is**

Saved CPU register state during trap/syscall.

When a process enters kernel:

```
user mode → kernel mode
```

CPU registers must be saved.

Trapframe contains:

```
eax
ebx
ecx
edx
esp
eip
eflags
etc
```

**Used for**

Returning to user space.

Example:

```
trapret
```

restores registers from trapframe.

**Important in fork()**

```c
*np->tf = *proc->tf;
```

Child inherits parent’s register state.

### 8. context

```c
struct context *context;
```

**What it is**

Saved CPU registers during context switch.

Different from trapframe.

Trapframe = user ↔ kernel transition

Context = kernel thread switch.

Context contains:

```
edi
esi
ebx
ebp
eip
```

Used by:

```c
swtch()
```

### 9. chan

```c
void *chan;
```

**What it is**

Sleep channel.

Used when a process blocks.

Example:

```c
read() waiting for data
wait() waiting for child
pipe() waiting for writer
```

Process sleeps on a channel.

```c
sleep(chan)
```

Later:

```c
wakeup(chan)
```

Kernel wakes processes sleeping on that channel.

Example code:

```c
p->chan = chan;
p->state = SLEEPING;
```

`chan` (channel) is just a void * — an arbitrary pointer used purely as an identifier. It's not a queue, not a data structure. It's an agreed-upon address that both the sleeper and the waker use to find each other.

The convention is: sleep on the address of the thing you're waiting for.

```c
sleep(&disk_buf, &lock);    // waiting for this specific buffer
sleep(&ticks, &tickslock);  // waiting for the next timer tick
sleep(&p, &wait_lock);      // parent waiting for this child process
```

Any pointer works — as long as the waker calls `wakeup()` with the same address. There's no registration, no subscription. It's a pure rendezvous by address.

`wakeup` scans the entire process table. Any process that is SLEEPING on this exact chan gets marked RUNNABLE. That's it — no direct hand-off, no immediate switch. The scheduler will pick it up in its next pass.

### 10. killed

```c
int killed;
```

Set to 1 when a process is signaled to die (e.g. someone calls kill(pid)). The process isn't immediately terminated — the kernel just sets this flag and lets the process notice it on its own at a safe point.

**Why not kill immediately?**

The process might be mid-kernel execution — holding locks, mid-syscall, mid-filesystem write. Killing it instantly would leave shared state corrupt. So xv6 uses a deferred check pattern.

### 11. ofile

```c
struct file *ofile[NOFILE];
```

**What it is**

Table of open file descriptors.

Equivalent to UNIX file descriptor table.

Example:

```
fd 0 → stdin
fd 1 → stdout
fd 2 → stderr
```

Each entry points to:

```c
struct file
```

Which contains:

```
offset
inode
mode
```

And in `exec()` — open files survive across `exec()` because `ofile` is in the PCB, not the address space. This is the mechanism behind shell I/O redirection — the shell rewires `ofile[1]` to a file after fork(), before `exec()`, and the executed program inherits it transparently.

`ofile` is where the Unix "everything is a file" abstraction lives in the process. A pipe, a device, a regular file — all behind the same `ofile[fd]` pointer.

### 12. cwd

```c
struct inode *cwd;
```

**What it is**

Current working directory.

Example:

```
cd /home
```

Kernel stores inode pointer here.

Used when resolving relative paths.

Example:

```c
open("file.txt")
```

Kernel resolves relative to cwd.

### 13. name

```c
char name[16];
```

**What it is**

Process name (debugging).

Example:
```
init
sh
ls
cat
```

Used for debugging prints.

Example:

```c
cprintf("%s\n", proc->name);
```

