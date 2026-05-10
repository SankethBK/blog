---
title:  "Setting up Linux Kernel in Local"
date:   2026-03-01
categories: ["operating systems", "linux"]
tags: ["local-setup"]

---

# Kernel Lab Setup Checklist
## CVE-2026-31431 (Copy Fail) — Debug Environment

This checklist covers everything needed to go from zero to a running kernel inside
QEMU with GDB attached and a breakpoint set in the vulnerable function. Follow in
order — each step depends on the previous one.

---

## Theory: What We're Building and Why

```
Your Ubuntu laptop
├── QEMU  ←  virtual machine running your custom kernel
│     └── bzImage  ←  the compiled kernel (compressed, no debug symbols)
└── GDB   ←  debugger attached to QEMU via TCP port 1234
      └── vmlinux  ←  same kernel with full debug symbols (used by GDB only)
```

**Why two kernel files?**
- `bzImage` is what actually boots — compressed, stripped, ~10MB
- `vmlinux` is the same code but with DWARF debug info — ~500MB, used only by GDB
  to resolve function names and line numbers. They must always be built together.

**Why QEMU and not a real machine?**
- You can freeze the entire OS with GDB — impossible on real hardware without KGDB
- Safe environment — crashes don't affect your laptop
- `nokaslr` boot flag disables address randomization so GDB symbols match exactly

**Why custom kernel and not the installed one?**
- Debug symbols (`CONFIG_DEBUG_INFO`) are stripped from distro kernels
- You need `CONFIG_CRYPTO_AUTHENCESN=y` compiled in, not as a module
- You want `nokaslr` — distro kernels always have KASLR enabled

---

## Prerequisites

Install all build dependencies on Ubuntu before anything else.

```bash
# Run from anywhere — installs system packages
sudo apt install -y \
  qemu-system-x86 \
  gdb \
  build-essential bc bison flex \
  libssl-dev libelf-dev libncurses-dev \
  gcc binutils python3 dwarves cpio \
  tmux
```

**What each package does:**
- `qemu-system-x86` — the virtual machine
- `gdb` — debugger that attaches to QEMU
- `build-essential` — gcc, make, libc headers
- `bison flex` — parser generators used by kernel's Kconfig system
- `libssl-dev libelf-dev` — headers needed by kernel build scripts
- `dwarves` — provides `pahole`, needed for BTF debug info generation
- `cpio` — for packing the root filesystem

---

## Step 1 — Get the Kernel Source

**Theory:** The Linux kernel source is one git repo with 1.1 million commits and
~35,000 files. We clone from Linus Torvalds' mainline tree on kernel.org.
We want the version *before* the patch (v6.12 or v6.17-rc6) because we want
the vulnerable code.

```bash
# Run from your home directory
cd ~
mkdir kernel-lab
cd ~/kernel-lab

# Full clone — takes 30-60 mins depending on connection
# Full history lets you git log, git blame, git show any commit
git clone \
  https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git \
  linux-vulnerable

# Verify — should show v6.17-rc6 or similar, NOT a patched version
cd ~/kernel-lab/linux-vulnerable
git log --oneline -3
```

**If you already have a clone** (like we did), just use it:
```bash
# Check it's intact
cd ~/linux    # or wherever your clone lives
git log --oneline -3
git remote -v   # should point to kernel.org
```

---

## Step 2 — Configure the Kernel

**Theory:** The kernel has ~20,000 config options. `defconfig` gives you a
sensible baseline for x86_64 (about 2,000 options enabled). Then we add the
specific options needed for this CVE:
- `CONFIG_DEBUG_INFO` + `CONFIG_DEBUG_INFO_DWARF4` — embed debug symbols in vmlinux
- `CONFIG_FRAME_POINTER` — keeps stack frames intact for GDB backtraces
- `CONFIG_CRYPTO_AUTHENCESN` — compiles in the vulnerable AEAD code
- `CONFIG_AF_ALG` — the userspace crypto API socket interface the exploit uses
- `CONFIG_RANDOMIZE_BASE=n` — disables KASLR so GDB symbols match runtime addresses

```bash
# IMPORTANT: run all make commands from inside the kernel source directory
cd ~/kernel-lab/linux-vulnerable   # or ~/linux — wherever your source is

# Step 2a: generate baseline config for x86_64
make SHELL=/bin/bash defconfig
# Expected output: "configuration written to .config"

# Step 2b: enable/disable specific options
./scripts/config \
  --enable  CONFIG_DEBUG_INFO \
  --enable  CONFIG_DEBUG_INFO_DWARF4 \
  --enable  CONFIG_FRAME_POINTER \
  --enable  CONFIG_CRYPTO_AUTHENC \
  --enable  CONFIG_CRYPTO_AUTHENCESN \
  --enable  CONFIG_CRYPTO_USER_API_AEAD \
  --enable  CONFIG_AF_ALG \
  --disable CONFIG_RANDOMIZE_BASE

# Step 2c: resolve any dependency conflicts silently
make SHELL=/bin/bash olddefconfig
# Expected output: "configuration written to .config"

# Step 2d: verify the important options landed correctly
grep -E "CONFIG_DEBUG_INFO=|CONFIG_CRYPTO_AUTHENCESN|CONFIG_RANDOMIZE_BASE|CONFIG_AF_ALG" .config
```

Expected grep output:
```
CONFIG_DEBUG_INFO=y
CONFIG_CRYPTO_AUTHENCESN=y
CONFIG_AF_ALG=y
# CONFIG_RANDOMIZE_BASE is not set
```

---

## Step 3 — Build the Kernel

**Theory:** The build compiles ~2,000 C files in parallel. Each `.c` file
becomes a `.o` object file, which get linked into `vmlinux`. Then `vmlinux`
gets stripped and compressed into `bzImage`. The `-j$(nproc)` flag uses all
CPU cores in parallel.

```bash
# IMPORTANT: run from inside kernel source directory
cd ~/kernel-lab/linux-vulnerable   # or ~/linux

# Build — takes 20-30 mins on 8 cores
# tee saves output to build.log so you can grep it if something fails
make SHELL=/bin/bash -j$(nproc) 2>&1 | tee build.log
```

**If the build fails:**
```bash
# Run single-threaded to see the actual error clearly
make SHELL=/bin/bash -j1 2>&1 | tee build-serial.log
```

**Common failure: missing source file** (happened to us with xt_TCPMSS.c):
```bash
# Check for files deleted during transfer
git status | grep deleted

# Restore all deleted files at once
git restore .

# Then rebuild
make SHELL=/bin/bash -j$(nproc) 2>&1 | tee build.log
```

**Verify the build succeeded:**
```bash
# Both files must exist
ls -lh arch/x86/boot/bzImage   # should be ~10-15 MB
ls -lh vmlinux                  # should be ~400-600 MB

# You should see this at the end of build.log:
tail -3 build.log
# Kernel: arch/x86/boot/bzImage is ready  (#1)  ← success
```

---

## Step 4 — Build a Minimal Root Filesystem

**Theory:** The kernel needs a root filesystem to boot into — something to run
as PID 1. We use BusyBox, which is a single static binary that contains
`sh`, `ls`, `mount`, `cat`, and 300 other tools. We pack it into a `cpio`
archive (called an initramfs) that the kernel unpacks into memory at boot.

```bash
# IMPORTANT: run from your home directory, NOT from kernel source
cd ~
mkdir rootfs
cd ~/rootfs

# Create the directory structure the kernel expects
mkdir -p bin sbin proc sys dev tmp etc

# Download static BusyBox (single binary, no dependencies)
wget https://busybox.net/downloads/binaries/1.35.0-x86_64-linux-musl/busybox
chmod +x busybox
cp busybox bin/busybox

# Create symlinks so busybox responds to different command names
for cmd in sh ls cat echo mount mkdir cp mv grep ln ps find; do
  ln -s busybox bin/$cmd
done

# Create the init script — first process the kernel runs (PID 1)
cat > init << 'EOF'
#!/bin/sh
mount -t proc  none /proc
mount -t sysfs none /sys
mount -t devtmpfs none /dev
echo "=== kernel lab ready ==="
exec /bin/sh
EOF
chmod +x init

# IMPORTANT: pack from INSIDE rootfs directory, not from ~
# The paths in the archive must be ./init not rootfs/init
cd ~/rootfs
find . | cpio -o -H newc | gzip > ~/initramfs.cpio.gz

# Verify — must show ./init not rootfs/init
zcat ~/initramfs.cpio.gz | cpio -t | grep init
# Expected: ./init  ← correct
# Bad:      rootfs/init  ← wrong, kernel won't find it
```

---

## Step 5 — Boot the Kernel in QEMU

**Theory:** QEMU emulates an entire x86_64 PC in software. We give it our
`bzImage` as the kernel and `initramfs.cpio.gz` as the filesystem.
The `-s` flag opens a GDB server on port 1234. `-nographic` sends all output
to the terminal instead of a window. `nokaslr` disables address randomization.

```bash
# Run from anywhere — uses full paths
# Terminal 1: boot QEMU (this terminal becomes the VM console)
qemu-system-x86_64 \
  -kernel ~/kernel-lab/linux-vulnerable/arch/x86/boot/bzImage \
  -initrd ~/initramfs.cpio.gz \
  -append "nokaslr console=ttyS0 rdinit=/init" \
  -m 2G \
  -nographic \
  -s
```

**Key flags explained:**
- `-kernel` — the bzImage to boot
- `-initrd` — the initramfs to use as root filesystem
- `-append` — kernel command line parameters
  - `nokaslr` — disable address randomization (critical for GDB)
  - `console=ttyS0` — send kernel output to serial (your terminal)
  - `rdinit=/init` — run our init script as PID 1 (use `rdinit` for initramfs,
    not `init` — common mistake)
- `-m 2G` — 2GB RAM for the VM
- `-nographic` — no GUI window, use terminal
- `-s` — open GDB stub on port 1234

**Expected output at the end:**
```
Run /init as init process
=== kernel lab ready ===
/ #              ← you have a shell inside your kernel
```

**To exit QEMU:** press `Ctrl+A` then `X`

---

## Step 6 — Attach GDB and Set Breakpoint

**Theory:** QEMU's `-s` flag runs a GDB server inside the VM process.
GDB on your host connects to it over TCP port 1234. GDB reads `vmlinux`
for symbol information — function names, source file locations, variable
layouts. Then when you set `break crypto_authenc_esn_encrypt`, GDB looks
up that function name in vmlinux's symbol table, finds its address
(e.g. `0xffffffff816f6a70`), and tells QEMU to pause execution when the
CPU reaches that address.

```bash
# Terminal 2: leave QEMU running in Terminal 1, open a new terminal
# IMPORTANT: run from inside kernel source directory (so gdb finds vmlinux)
cd ~/kernel-lab/linux-vulnerable   # or ~/linux

gdb vmlinux
```

Inside GDB:
```
# Connect to the running kernel in QEMU
(gdb) target remote :1234
# Expected: Remote debugging using :1234
#           0xffffffff8219b25f in pv_native_safe_halt ()...
# This means GDB is connected and the kernel is running

# Set breakpoint in the vulnerable function
(gdb) break crypto_authenc_esn_encrypt
# Expected: Breakpoint 1 at 0xffffffff816f6a70: file crypto/authencesn.c, line 160.
# The address resolving to a file + line = success

# Confirm breakpoint is set
(gdb) info breakpoints
# Should show breakpoint at crypto/authencesn.c

# Let the kernel continue running
(gdb) continue
```

**Breakpoint resolved to a file + line number = entire setup is working.**

---

## Step 7 — tmux Layout for Future Sessions

Save this script so you can launch the full lab environment with one command.

```bash
cat > ~/kernel-lab/lab.sh << 'EOF'
#!/bin/bash
# Launches the full kernel debugging environment in tmux
# Usage: bash ~/kernel-lab/lab.sh

KERNEL=~/kernel-lab/linux-vulnerable/arch/x86/boot/bzImage
# Change to ~/linux if that's where your source is
KERNEL_SRC=~/kernel-lab/linux-vulnerable
ROOTFS=~/initramfs.cpio.gz

tmux new-session -d -s kernellab

# Pane 0 (left) — QEMU VM
tmux rename-window 'kernel-lab'
tmux send-keys "qemu-system-x86_64 \
  -kernel $KERNEL \
  -initrd $ROOTFS \
  -append 'nokaslr console=ttyS0 rdinit=/init' \
  -m 2G -nographic -s" Enter

# Pane 1 (right top) — GDB
tmux split-window -h
tmux send-keys "cd $KERNEL_SRC && gdb vmlinux" Enter
tmux send-keys "target remote :1234" Enter

# Pane 2 (right bottom) — host shell for bpftrace etc
tmux split-window -v
tmux send-keys "cd $KERNEL_SRC" Enter

tmux attach -t kernellab
EOF
chmod +x ~/kernel-lab/lab.sh
```

---

## Quick Reference: Common GDB Commands for Kernel Debugging

```bash
# Connect
target remote :1234

# Breakpoints
break crypto_authenc_esn_encrypt      # break on function entry
break authencesn.c:147                # break on specific line
info breakpoints                       # list all breakpoints
delete 1                              # delete breakpoint 1

# Execution control
continue                              # resume until next breakpoint
step                                  # step one source line (into functions)
next                                  # step one source line (over functions)
finish                                # run until current function returns

# Inspect memory and variables
p *req                                # print aead_request struct
p req->src                            # print source scatterlist
p req->dst                            # print destination scatterlist
x/32xb 0xffffffff816f6a70            # examine 32 bytes at address
x/32xb $rsp                          # examine 32 bytes at stack pointer

# Watchpoints (fires when memory is written)
watch *((char*)sg_virt(req->dst) + req->dst->length)

# Backtrace
bt                                    # show call stack
bt full                               # show call stack with local variables

# Source
list                                  # show source around current line
list crypto_authenc_esn_encrypt       # show source of function
```

---

## Directory Structure After Full Setup

```
~
├── kernel-lab/
│   ├── linux-vulnerable/        ← kernel source + build output
│   │   ├── vmlinux              ← debug symbol file (give to GDB)
│   │   ├── arch/x86/boot/
│   │   │   └── bzImage          ← bootable kernel (give to QEMU)
│   │   ├── crypto/
│   │   │   ├── authencesn.c     ← vulnerable file
│   │   │   └── algif_aead.c     ← AF_ALG AEAD interface
│   │   └── .config              ← kernel config
│   └── lab.sh                   ← tmux launcher
├── rootfs/                      ← initramfs contents (source)
│   ├── init                     ← PID 1 init script
│   └── bin/                     ← busybox + symlinks
└── initramfs.cpio.gz            ← packed rootfs (give to QEMU -initrd)
```

---

## Common Mistakes to Avoid

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Running `make` from wrong directory | `Makefile not found` | Always `cd` into kernel source first |
| Packing initramfs from `~` instead of `~/rootfs` | `rdinit=/init failed: -2` | `cd ~/rootfs` then `find . \| cpio ...` |
| Using `init=` instead of `rdinit=` for initramfs | Same panic as above | Use `rdinit=/init` in `-append` |
| Forgetting `nokaslr` | GDB breakpoints land at wrong addresses | Always include `nokaslr` in `-append` |
| vmlinux and bzImage from different builds | GDB shows wrong source lines | Always copy both files together |
| Running GDB without `vmlinux` argument | No symbols, can't set named breakpoints | `gdb vmlinux` not just `gdb` |
| ARM64 binaries copied from Mac | `Exec format error` during build | Run `make mrproper` then `make distclean` and rebuild natively |