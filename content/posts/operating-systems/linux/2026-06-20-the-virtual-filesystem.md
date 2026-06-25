---
title: "The Virtual Filesystem"
date: 2026-06-20
categories: ["operating systems", "linux"]
tags: ["file system", "vfs"]
---

# The Virtual Filesystem

### What is a Filesystem?

Imagine a bare hard drive as a massive, empty warehouse. You can throw billions of bytes of data in there, but without a system, you will never find anything again.

A **filesystem** is the specific set of rules, data structures, and "ledgers" (like the Inodes and Superblocks we discussed) used to organize, index, and retrieve that data. It dictates how large a file can be, how folders are nested, and how permissions are handled.


### Why Were So Many Created?

There isn’t a single "perfect" filesystem. They multiplied over the decades due to three main pressures:

1. **Hardware Evolution:** A filesystem designed in 1985 to manage a 1.4MB floppy disk is fundamentally unequipped to manage a 4TB NVMe solid-state drive in 2026. New hardware required new indexing mathematics.
2. **The OS Wars:** Microsoft, Apple, and the Unix/Linux communities historically built their own isolated ecosystems. They designed filesystems heavily tailored to their specific operating system features (like Windows Registry vs. Unix permissions).
3. **The "Speed vs. Safety" Trade-off:** Some filesystems are designed to be incredibly fast and lightweight (perfect for a camera SD card). Others are designed to be bulletproof, using complex "journaling" to ensure data isn't corrupted if the power goes out (perfect for banking servers).


### The Major Eras & Players

#### 1. The Legacy / Universal Era (FAT)

* **FAT32 (File Allocation Table):** Created by Microsoft in the 1990s.
* *The Good:* It is the lowest common denominator. Every device on earth—Windows, Mac, Linux, your TV, your car stereo—can read FAT32.
* *The Bad:* It has severe historical limits. It cannot store a file larger than 4GB. It has no security permissions and no crash protection.


* **exFAT:** Microsoft’s modern update to FAT. It removes the 4GB file limit and is optimized specifically for flash memory (USB drives and SD cards). It is the standard format for modern portable storage.

#### 2. The Windows Heavyweight (NTFS)

* **NTFS (New Technology File System):** Introduced in the 90s for Windows NT and is the standard for every modern Windows machine.
* *Why it was built:* Microsoft needed a filesystem for enterprise servers. NTFS introduced **Journaling** (keeping a log of pending changes so a power failure doesn't corrupt the disk), file-level encryption, and complex user-access controls.
* *The Catch:* It is heavily proprietary. Macs can read NTFS but cannot natively write to it without third-party software.


#### 3. The Linux Workhorses (ext family)

* **ext2 / ext3 / ext4 (Extended Filesystem):** The native Unix/Linux lineage.
* *ext2:* The early Linux standard. Fast, but lacked crash protection.
* *ext3:* Added journaling (crash protection).
* *ext4:* The current standard for almost all Linux distributions (and Android phones). It supports massive volume sizes, reduces fragmentation, and is incredibly stable. It perfectly maps to the Unix concepts of Inodes and Superblocks.



#### 4. The Apple Ecosystem

* **HFS+ (Mac OS Extended):** Apple’s classic filesystem used for decades.
* **APFS (Apple File System):** Released in 2017.
* *Why it was built:* HFS+ was built for spinning hard drives. APFS was built from scratch specifically for Solid State Drives (SSDs) and flash memory. It introduced instant file cloning and native encryption.



#### 5. The "Next-Gen" Datacenter Filesystems (ZFS, Btrfs)

* These are hyper-advanced filesystems designed for massive server arrays.
* *Why they were built:* They combine the volume manager (RAID) with the filesystem. They use **Copy-on-Write** (never overwriting old data until the new data is safely written) and cryptographic checksums to detect "bit rot" (data silently corrupting over time).


#### Summary Cheat Sheet

| Filesystem | Primary OS | Best Used For | Key Characteristic |
| --- | --- | --- | --- |
| **FAT32** | Universal | Old USBs, small SD cards | Max file size is 4GB; works on everything. |
| **exFAT** | Universal | Modern USBs, Camera SDs | Removes the 4GB limit; great for flash media. |
| **NTFS** | Windows | Windows internal drives | Journaling, proprietary Microsoft features. |
| **ext4** | Linux / Android | Linux root partitions | Highly stable, perfect Unix abstraction. |
| **APFS** | macOS / iOS | Apple internal drives | Optimized strictly for flash/SSDs. |

## 1. What is the Virtual Filesystem (VFS)?

The VFS is the kernel subsystem that acts as an **abstraction layer** (or a "switch") between userspace programs and physical storage filesystems.

It is the universal glue of the Linux storage stack. Because of the VFS, filesystems like `ext4`, `XFS`, `NTFS`, and `FAT32` do not just coexist—they **interoperate**.

### The Classic Example: `cp` (Copy)

If you run `cp /media/harddisk/photo.jpg /media/usb_stick/photo.jpg`, you might be moving data from a hard drive running `ext4` to a thumb drive running `FAT32`.

* In old operating systems (like DOS), this required specialized tools because the OS couldn't natively bridge two different filesystem designs.
* In Linux, the `cp` utility has absolutely no idea what an `ext4` or `FAT32` layout looks like. It just issues standard Unix system calls (`read()` and `write()`), and the VFS seamlessly handles the translation on the fly.

### The Power of the Abstraction Layer

The VFS dictates a **Common File Model**. This is an idealized, Unix-centric blueprint of what a filesystem *should* look like.

To play nice with Linux, every filesystem driver must "mold" its internal logic to fit this blueprint.

* **The Frontend:** Userspace programs see a perfectly uniform naming policy and a single set of generic system calls (`open()`, `read()`, `write()`, `close()`).
* **The Backend:** The actual hardware complexities and disk-layout structures are hidden deep inside specific filesystem drivers.
* **The Massive Benefit:** You can plug a brand-new storage medium or invent a brand-new filesystem tomorrow, and you will **never** need to rewrite or recompile your userspace applications to use it.


### Data Flow Walkthrough: Tracing a `write()` Call

The text provides a great step-by-step example of what happens when a program calls:
`ret = write(fd, buf, len);`

Instead of hitting the physical disk directly, the call takes a precise journey down the kernel stack:

```
  [ Userspace Application ]
             │  issues write()
             ▼
   [ VFS Layer: sys_write() ]  <─── Generic frontend determines which 
             │                      filesystem owns the File Descriptor (fd)
             ▼
 [ Filesystem-Specific Method ] <─── Backend driver handles layout rules
             │                      (e.g., ext4_file_write_iter)
             ▼
     [ Physical Media ]         <─── Data lands on SSD, HDD, or Flash

```

## Unix Filesystems

### 1. The Unified Namespace (Unix vs. Windows)

* **The Unix Way:** All mounted filesystems are seamlessly blended into a single, global directory tree (a namespace). The hardware boundary is completely hidden.
* **The DOS/Windows Way:** The namespace is fractured by device/partition boundaries (e.g., `C:\`, `D:\`).
* **The Takeaway:** Windows leaks hardware details into the software abstraction. Linux hides the hardware entirely, making the namespace much cleaner for userspace. *(Note: Linux now technically uses per-process namespaces, but they default to inheriting a seemingly global one).*

### 2. Files: Keep It Simple

* **Definition:** A file is simply an ordered string of bytes.
* **Unix vs. Legacy:** Older systems (like OpenVMS) used "record-oriented" filesystems with complex internal structures. Unix threw that away in favor of a raw byte-stream. It sacrifices built-in structure for massive flexibility.

### 3. Directories & Dentries (The Path)

* **The Secret of Directories:** To the VFS, **a directory is just a normal file.** The only difference is that its "data" is simply a list of the files contained inside it.
* **Dentries (Directory Entries):** Every single component of a path is a dentry.
* *Example:* In `/home/wolfman/butter`, the root `/`, the folder `home`, the folder `wolfman`, and the file `butter` are **all** dentries.

### 4. Metadata Segregation (Inodes & Superblocks)

Unix strictly separates the *contents* of a file from the *information about* the file/filesystem.

| Structure | What it holds | Example Data |
| --- | --- | --- |
| **File Object** | The actual data | "Hello World" (The string of bytes) |
| **Inode** (Index Node) | File Metadata | Size, owner, permissions, creation time |
| **Superblock** | Filesystem Metadata | Total blocks, block size, filesystem state |

### 5. The "Faking It" Requirement for Non-Unix Filesystems

* **Native Unix FS (ext4, etc.):** These concepts physically exist on the hard drive. There is literally a block on the disk designated as the Superblock, and specific blocks designated as Inodes.
* **Non-Unix FS (FAT32, NTFS):** These filesystems do not have physical Inodes or Unix-style Superblocks on the disk.
* **The VFS Mandate:** To mount a FAT32 drive in Linux, the FAT32 driver must **fake it**. It must read its own proprietary disk layout and instantly construct fake Inode and Superblock structures in RAM so the VFS has the standardized objects it expects to work with.

#### 1. Where is the "faking" code written?

The code is written **directly inside the filesystem driver itself**.

In the Linux kernel source code, there is a directory called `fs/`. Inside that directory, there is a subfolder for every supported filesystem (`fs/ext4/`, `fs/fat/`, `fs/ntfs3/`).

The filesystem driver *is* the bridge. Here is how the contract works:

1. The VFS defines an "interface" using C structures filled with function pointers (very similar to Interfaces in Object-Oriented Programming). It says, *"I don't care who you are, if you want to mount, you must provide a function called `read_inode()`."*
2. The FAT32 driver code includes a specific function (e.g., `fat_read_inode`).
3. When you access a file, the VFS calls `fat_read_inode`.
4. The FAT32 driver reads its own proprietary File Allocation Table off the disk, allocates a standard VFS `struct inode` in RAM, fills the Unix variables with translated FAT data, and hands it back to the VFS.

To the VFS, it looks like a perfect Unix object. The VFS never knows it was artificially constructed in RAM just a microsecond prior.

#### 2. How hard is it to "fake" things?

It ranges from trivial to incredibly difficult, depending on the **impedance mismatch** between the filesystem's design and Unix's expectations.

Here is how a driver like FAT32 handles the faking process:

##### The Easy Part: File Size and Timestamps

Unix needs to know how big a file is and when it was modified. FAT32 actually stores this data on the disk. The FAT32 driver simply reads the proprietary FAT byte layout, grabs the size/time, and copies it into the VFS Inode structure. Easy.

##### The Moderate Part: Fake Inode Numbers (`i_ino`)

Unix programs constantly track files by their Inode Number (a unique integer ID). FAT32 has no concept of Inode numbers; it only tracks the physical disk block where a file starts.

* **The Hack:** The FAT32 driver usually takes the physical disk sector/offset where the file is located and hashes it into an integer. It tells the VFS, *"Here is your Inode number!"* * **The Flaw:** If you defragment a FAT32 drive, the physical location of the file changes. This means the driver will generate a *different* fake Inode number the next time it reads it. This can occasionally confuse strict Unix programs that expect Inode numbers to be perfectly permanent.

##### The Hard Part: Ownership and Permissions

Unix absolutely requires every file to have an Owner (UID), a Group (GID), and read/write/execute permissions (e.g., `rwxr-xr-x`). **FAT32 physically cannot store this information on the disk.** It only has a simple "Read Only" or "Hidden" toggle.

* **The Hack:** Because the driver cannot read this from the disk, it forces you to fake it at the moment you mount the drive.
* **How it works:** When you mount a USB stick, the OS passes "mount options" to the driver (e.g., `uid=1000, gid=1000, umask=022`). The FAT32 driver takes those rules and blindly paints them over *every single file* it puts into RAM. If you ask the VFS who owns a file on a USB stick, the VFS will confidently say "User 1000." But if you unplug that USB stick and hand it to a friend, there is zero record of User 1000 on the actual metal.

##### Summary

Writing a native Unix driver (like `ext4`) is mostly about disk speed and safety. Writing a non-Unix driver (like `FAT32` or `NTFS`) is an exercise in creative translation—figuring out how to bend foreign disk layouts to satisfy the strict, unyielding demands of the Linux VFS.


### 6. Mounting and Unmounting File Systems

In Windows, when you plug in a USB drive, it automatically gets a new, separate letter (like `E:\`). As we discussed in the last section, Unix/Linux doesn't do this; it uses one single, massive directory tree (the namespace) starting at the root (`/`).

Because there is only one tree, new hardware has to be mathematically "grafted" onto a branch of that tree before you can use it.

#### 1. Mounting (Attaching the Drive)

**Definition:** Mounting is the process of attaching a filesystem found on a physical device (like a USB drive, SSD, or network share) to a specific directory in the existing Linux filesystem tree.

* **The Mount Point:** This is the existing, usually empty, directory that acts as the "doorway" to the new drive.
* **How it works:** Let's say you have an empty folder at `/media/usb`. When you mount a flash drive to that folder, the VFS temporarily hides whatever was inside `/media/usb` and redirects all traffic. Going into that folder now physically reads from the flash drive.
* **The Command:** `mount /dev/sdb1 /media/usb`
*(Translation: "Hey VFS, take the filesystem on physical device `sdb1` and attach it to the folder `/media/usb`.")*

#### 2. Unmounting (Safely Detaching)

**Definition:** Unmounting severs the connection between the mount point directory and the physical device.

* **Why is it critical?** Linux is aggressively lazy about writing to disks (it keeps data in RAM caches as long as possible to improve speed). If you just yank a USB drive out of the computer, any data still sitting in the RAM cache is permanently lost, corrupting the drive.
* **How it works:** When you issue an unmount command, the VFS forces the kernel to flush all pending data writes directly to the physical hardware. Once it confirms the disk is perfectly synced and no programs are actively using it, it detaches the filesystem.
* **The Result:** The `/media/usb` folder goes back to being a normal, empty folder on your main hard drive, and you can safely unplug the USB.
* **The Command:** `umount /media/usb`

> **Quick Analogy:** The Linux directory tree is a physical building. Mounting is building a new hallway that connects a temporary shipping container (the USB drive) to one of the building's doors (the mount point). Unmounting is making sure everyone has left the container and all boxes are secured before knocking the hallway down and driving the container away.

## VFS Objects and Their Data Structures

### The VFS Architecture: Object-Oriented C

Even though the Linux kernel is written in C (which lacks native classes or objects), the VFS is fundamentally an **Object-Oriented** system.

It achieves this by using standard C `structs`.

* **The "Object" (Data):** The variables inside the `struct`.
* **The "Methods" (Operations):** Pointers to functions stored inside the `struct` that operate on the object's data.

To the VFS, it doesn't matter if the underlying filesystem is `ext4` or `FAT32`; it interacts with them entirely through these standardized C structures.

### 1. The 4 Primary VFS Objects

These are the core data structures that represent the Common File Model.

1. **The Superblock Object:** Represents a specific, globally mounted filesystem (the entire drive/partition).
2. **The Inode Object:** Represents a specific, individual file on the disk.
3. **The Dentry Object:** Represents a directory entry (a single component of a path, like `home` or `file.txt`).
4. **The File Object:** Represents an open file as it is currently associated with a running process.

> **Crucial Quirk:** There is **no** "Directory Object." Because Unix treats directories purely as files that contain lists of other files, a directory is just represented by an Inode and a Dentry, exactly like a normal file.


### 2. The Operations Objects (The "Methods")

Every primary object has a corresponding `_operations` object inside it. This is literally a struct filled with function pointers.

If a filesystem driver (like `ext4`) wants to do something special, it plugs its own custom functions into these pointers. If it doesn't need to do anything special, it simply inherits the kernel's default, generic VFS functions.

| Primary Object | Operations Object | Example Methods | What it dictates |
| --- | --- | --- | --- |
| **Superblock** | `super_operations` | `write_inode()`, `sync_fs()` | How the kernel interacts with the whole filesystem. |
| **Inode** | `inode_operations` | `create()`, `link()` | How the kernel interacts with a specific file on disk. |
| **Dentry** | `dentry_operations` | `d_compare()`, `d_delete()` | How the kernel navigates and manages paths/names. |
| **File** | `file_operations` | `read()`, `write()` | How a running user process interacts with an open file. |


### 3. The Supporting Cast

Beyond the four primary objects, the VFS relies on a few other key structures to manage the system state:

* **`file_system_type`:** Describes a registered filesystem driver (e.g., "I am the `ext4` driver, and here are my capabilities").
* **`vfsmount`:** Represents a specific mount point (e.g., "I am the connection at `/media/usb`, and here are my mount flags").

**Per-Process Structures:**

* **`fs_struct`** & **`file` structure:** These track the specific files and filesystem states associated with an individual running process.

Here are your notes for the Superblock object — high-value fields only, methods explained by what they do for you conceptually, not exhaustively.


## The Superblock Object

### What It Represents

One mounted filesystem instance — the entire drive/partition. For disk-based filesystems (ext4), it's a real on-disk structure, read into memory at mount time. For memory-based filesystems (sysfs), there's no disk to read from — the superblock is fabricated on the fly. Either way, the VFS sees the same `struct super_block`.

### `struct super_block` — fields worth keeping

| Field | Why it matters |
|---|---|
| `s_dev` | Which device this filesystem lives on |
| `s_blocksize` / `s_blocksize_bits` | The filesystem's block size — everything I/O-related is rounded to this |
| `s_maxbytes` | Max file size this filesystem supports — this is *why* FAT32's 4GB limit exists at the VFS level |
| `s_type` | Pointer back to the `file_system_type` — "which driver am I" |
| `s_op` | **The important one** — pointer to the superblock operations table, covered below |
| `s_root` | The dentry for this filesystem's root directory — the entry point into its namespace |
| `s_dirty` / `s_io` | Lists tracking inodes that need writeback — connects directly to the dirty-page concepts from your memory management notes |
| `s_fs_info` | Opaque pointer for filesystem-private data — ext4 hangs its own internal structures off this without the VFS needing to know what they are |

Everything else (locks, refcounts, security module hooks, quota structs) is plumbing you won't need until you're deep in a specific subsystem.

### Superblock Operations — the contract

`s_op` is a pointer to `struct super_operations` — a table of function pointers. This is the C version of a vtable: the filesystem driver fills in the functions it cares about, leaves the rest NULL (VFS falls back to generic behavior or does nothing).

Calling convention always looks like this, because C has no implicit `this`:

```c
sb->s_op->write_super(sb);   // sb passed explicitly — there's no other way to get it
```

### Operations worth remembering (grouped by what they actually do)

**Inode lifecycle** — creation/destruction of the in-memory inode object itself:
- `alloc_inode()` — allocate + init a fresh inode under this superblock
- `destroy_inode()` — free it

**Inode persistence** — getting inode changes onto disk:
- `dirty_inode()` — called when an inode is modified in memory. This is the hook journaling filesystems (ext3/ext4) use to log the change *before* it hits disk — ties directly into the journaling vs non-journaling distinction from your filesystem-types notes earlier.
- `write_inode()` — actually writes inode to disk, `wait` controls sync vs async
- `delete_inode()` — removes inode from disk entirely (file was deleted)
- `drop_inode()` — last reference gone; normal Unix filesystems just let the VFS handle deletion by leaving this NULL

**Filesystem-wide sync** — same idea as inode writeback, but for the superblock itself:
- `write_super()` — flush the in-memory superblock state back to disk
- `sync_fs()` — sync filesystem metadata generally

**Mount lifecycle**:
- `put_super()` — called on unmount, releases the superblock
- `remount_fs()` — handle being remounted with new options (e.g. `mount -o remount,ro`)
- `umount_begin()` — interrupt an in-progress mount; mainly used by network filesystems (NFS) where unmounting needs to abort outstanding network ops

**Stats**:
- `statfs()` — backs the `statfs()`/`df` family of calls

### The pattern to internalize

This is the same shape you'll see repeated for Inode, Dentry, and File objects next: **a struct holding state + a pointer to an operations table**, and the operations table is how a filesystem driver customizes behavior without the VFS needing any `if (fstype == ext4)` branching anywhere. ext4 fills in real disk-writing logic; sysfs leaves most of these NULL because there's no disk to write to.

Here are your notes for the Inode object — same filtering principle.

---

## The Inode Object

### What It Represents

A single file (or directory — remember, directories are just files with a listing as their data). For Unix-style filesystems, this is read directly from an on-disk inode. For filesystems without inodes (FAT32), the driver fabricates it — this is the same "faking it" mechanism you already wrote up earlier, just now you're seeing the actual struct being faked.

One inode object exists in memory only while the file is actively being accessed — not for every file on disk at all times.

### `struct inode` — fields worth keeping

| Field | Why it matters |
|---|---|
| `i_ino` | The inode number — the thing FAT32 has to fake by hashing disk location, from your earlier notes |
| `i_count` | Reference count — same `_refcount` discipline you already know from `struct page`. Inode isn't freed while this is nonzero |
| `i_uid` / `i_gid` / `i_mode` | Owner, group, permission bits — the exact fields FAT32 *cannot* derive from disk and has to paint on at mount time via `uid=`/`gid=`/`umask=` mount options |
| `i_size` | File size in bytes |
| `i_atime` / `i_mtime` / `i_ctime` | Access / modify / change timestamps — note the text's point that a filesystem without real timestamp support is free to fake these too (zero them, alias them, whatever) |
| `i_op` | **Inode operations table** — covered below |
| `i_fop` | File operations table — this is the *default* operations a freshly opened file on this inode will get (distinct from the Inode object's own ops — don't conflate the two) |
| `i_sb` | Back-pointer to this inode's superblock |
| `i_mapping` | Pointer to the `address_space` — this is the page cache connection. Worth flagging since you've already been deep in page cache mechanics for your CVE work; this is the field that ties an inode to its cached pages |
| `i_bdev` / `i_cdev` / `i_pipe` (union) | Special-file backing — a block device, char device, or pipe. Union because an inode is only ever *one* of these (or none) — same union-for-mutual-exclusivity pattern as `struct page`'s fields |

Everything else (locks, dnotify/inotify bookkeeping, quota pointers, security module hook) is plumbing — skip until a specific task needs it.

### Inode Operations — the contract

Same shape as superblock: `i_op` is a pointer to `struct inode_operations`, a table of function pointers the filesystem driver fills in. Called the same explicit way:

```c
i->i_op->truncate(i);
```

### Operations worth remembering (grouped by what they do)

**Namespace mutation** — these are what backs the actual filesystem syscalls you already use daily:
- `create()` — backs `creat()`/`open()` with `O_CREAT`
- `lookup()` — given a directory inode + a name, find the corresponding inode. **This is the single most-called inode operation** — every path component resolution during a path lookup goes through this
- `link()` / `unlink()` — hard link create/remove
- `symlink()` / `readlink()` / `follow_link()` / `put_link()` — symlink creation and resolution. `follow_link()` is the one that actually translates the symlink target into a real inode
- `mkdir()` / `rmdir()` — directory create/remove
- `mknod()` — create a special file (device node, named pipe, socket)
- `rename()` — move/rename within or across directories

**Size and permission**:
- `truncate()` — resize a file. Caller sets `i_size` *before* calling this — the inode field is updated first, then the operation makes disk reality match it
- `permission()` — access check. Most filesystems leave this NULL and let the VFS do the generic mode-bit comparison; only ACL-supporting filesystems implement their own
- `setattr()` / `getattr()` — change notification and on-demand refresh-from-disk

**Extended attributes** (`setxattr`/`getxattr`/`listxattr`/`removexattr`) — arbitrary key/value pairs attached to a file. Not core to VFS navigation; useful to know exists, not worth memorizing signatures.

### The Pattern Holds

Same shape as the superblock: state struct + operations table. The thing worth carrying forward specifically from *this* object is `lookup()` — that's the function that gets called over and over as the kernel walks a path like `/home/wolfman/butter`, one dentry at a time. That's your bridge into the Dentry object, which is what's coming next.

## The Dentry (Directory Entry) Object

**The Core Concept:** A dentry answers the question, *"What name/path led me to this file?"* It is essentially a **cached pathname component lookup**.

### 1. The Problem: Path Resolution is Expensive

Without dentries, opening a file like `/home/sanketh/notes.txt` forces the kernel to read directory metadata and search entries at every single step:

1. Search `/`
2. Search `home`
3. Search `sanketh`
4. Search `notes.txt`

If you run commands repeatedly (like `git status` or `ls`), the kernel would have to traverse that physical disk path over and over.

### 2. The Solution: The Dentry Cache

To solve this, the VFS creates a separate `dentry` object for **each component** of the path and stores them in RAM (the dentry cache).

* `/`
* `home`
* `sanketh`
* `notes.txt`

Next time you open the same path, it is a rapid **dentry cache hit**—no disk lookup or directory scan required.

### 3. Dentry vs. Inode (The Mental Model)

People frequently confuse these two objects.

* **Inode = File Identity.** It represents the file itself (permissions, size, timestamps, block pointers).
* **Dentry = Directory Name.** It represents the name of the file and where it sits in the directory tree. It acts as the *name-to-inode mapping*.

**The Hard Link Example:**
If you create a hard link (`ln notes.txt notes2.txt`), you now have:

* **One Inode** (the actual data and permissions remain the same).
* **Two Dentries** (because there are two distinct names/paths pointing to that single file identity).

### 4. Negative Dentries (Performance Hack)

If a process tries to open a file that doesn't exist (e.g., `/tmp/does_not_exist`), the kernel does the expensive lookup, fails, and then creates a **negative dentry**.

* **Meaning:** "I already checked the disk, and this name definitively does not exist."
* **Benefit:** Future lookups for that missing file fail instantly in the cache, saving massive I/O overhead.

Here is the step-by-step breakdown of how the kernel translates a human-readable path into a specific file on the disk, and exactly how dentries fit into that puzzle.

### The File Lookup Path

#### 1. The Raw Path Walk (Assuming No Cache)

When a process calls `open("/home/sanketh/notes.txt")`, the kernel receives a raw string. It must split that string into components (`home`, `sanketh`, `notes.txt`) and walk down the directory tree step-by-step.

* **Step 0: Start at the Root (`/`)**
The kernel looks at the root directory's inode. An inode does not contain filenames; it contains metadata and pointers to data blocks. For a directory, those data blocks contain a table mapping filenames to inode numbers.
* **Step 1: Lookup "home"**
The kernel reads the root directory's table and finds the mapping: `home -> inode 42`. It steps into inode 42.
* **Step 2: Lookup "sanketh"**
The kernel reads the `/home` directory's table and finds: `sanketh -> inode 102`. It steps into inode 102.
* **Step 3: Lookup "notes.txt"**
The kernel reads the `/home/sanketh` directory's table and finds: `notes.txt -> inode 555`.

**Result:** The kernel has successfully resolved the path to **inode 555**.


#### 2. The Core Revelation: Where do Filenames Live?

The biggest misconception in Linux filesystems is thinking a file knows its own name. **It does not.**

The mapping of `filename -> inode_number` is stored exclusively inside the **parent directory's data blocks**.

```text
Directory Data Block for /home/sanketh/
+-----------------------------+
| notes.txt   ->  inode 555   |
| photo.jpg   ->  inode 556   |
+-----------------------------+

```

##### Why don't Inodes own their names?

Because of **Hard Links**. If you run `ln notes.txt notes_backup.txt`, you now have two completely different filenames pointing to the exact same file.

If the inode stored the filename, it could only ever have one name. Because the *directory* owns the name, you can have a hundred different directory entries (names) all pointing to single file identity (inode 555).


#### 3. Where Dentries Come In (The Fast Path)

Walking the path as described in Section 1 requires reading from the physical disk at every single step. If you run a command inside that folder, doing that disk-walk every time would bring the system to a crawl.

This is why the VFS creates **Dentries** as it does the walk.

* **The Cache:** Once the kernel finds `home -> inode 42`, it creates a `dentry("home")` in RAM. It does the same for `sanketh` and `notes.txt`.
* **The Shortcut:** The next time you open that file, the kernel checks the Dentry Cache in RAM. It sees the cached mapping and instantly knows `notes.txt` equals `inode 555` without having to touch the hard drive or scan directory tables.


#### 4. The Final Handoff (Path → Inode → Data)

It is crucial to understand where the path resolution process ends.

When the kernel finally gets the target inode (555), it has only answered the question: *"What file is this?"* It has **not** accessed the file content yet.

The flow of opening a file is a three-stage handoff:

1. **Directory Entry Lookup:** Maps the string name to an Inode.
2. **The Inode:** Provides the permissions, size, and physical block pointers.
3. **The File Data:** The physical disk blocks where the actual text/bytes are stored.

> **The One-Sentence Summary:** > The kernel resolves a path by repeatedly asking each directory, *"Do you have an entry named X?"* until it reaches the final inode; Dentries are simply the cached results of those questions so the kernel never has to ask twice.