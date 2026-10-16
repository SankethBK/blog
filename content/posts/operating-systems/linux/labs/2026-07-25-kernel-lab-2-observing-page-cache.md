---
title: "Kernel Lab 2: Observing the Page Cache"
date: 2026-07-25
categories: ["operating systems", "linux"]
tags: ["vfs", "mm_struct", "address_space", "vm_area_struct", "page"]
---

# Kernel Lab 2: Observing the Page Cache

## The Program

The below program opens a file via `mmap` and performs read/write operations via commands. It also shows page faults, resident pages via `mincore`, etc. 

```c
// page_cache_lab.c
#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <sys/resource.h>

static void print_help(void)
{
    printf("\nCommands:\n");
    printf("  help                     Show commands\n");
    printf("  info                     Mapping information\n");
    printf("  read <page>              Read first byte of page\n");
    printf("  write <page> <char>      Fill entire page with character\n");
    printf("  dump <page>              Dump first 64 bytes\n");
    printf("  msync                    Flush dirty pages\n");
    printf("  dontneed                 madvise(MADV_DONTNEED)\n");
    printf("  pause                    Wait for ENTER\n");
    printf("  mincore                  Show all pages compact (R=resident .=not)\n");
    printf("  mincore <page>           Check if specific page is resident\n");
    printf("  quit\n\n");
}


// compact: prints [R....R..R] style, 64 pages per line
static void print_mincore_compact(char *region, size_t filesize, long pagesize)
{
    size_t npages = (filesize + pagesize - 1) / pagesize;
    unsigned char *vec = calloc(npages, 1);
    if (!vec) { perror("calloc"); return; }

    if (mincore(region, filesize, vec) != 0) {
        perror("mincore");
        free(vec);
        return;
    }

    printf("\nPage residency (%zu pages, R=resident .=not):\n\n", npages);

    for (size_t i = 0; i < npages; i++) {
        if (i % 64 == 0)
            printf("%5zu: ", i);

        putchar((vec[i] & 1) ? 'R' : '.');

        if ((i + 1) % 64 == 0 || i == npages - 1)
            putchar('\n');
    }

    // print resident page numbers explicitly
    printf("\nResident pages: ");
    int any = 0;
    for (size_t i = 0; i < npages; i++) {
        if (vec[i] & 1) {
            printf("R(%zu) ", i);
            any = 1;
        }
    }
    if (!any) printf("none");
    printf("\n\n");

    free(vec);
}

// single page check
static void print_mincore_page(char *region, size_t filesize,
                                long pagesize, size_t page)
{
    size_t npages = (filesize + pagesize - 1) / pagesize;

    if (page >= npages) {
        printf("Page %zu out of range (max %zu)\n", page, npages - 1);
        return;
    }

    unsigned char *vec = calloc(npages, 1);
    if (!vec) { perror("calloc"); return; }

    if (mincore(region, filesize, vec) != 0) {
        perror("mincore");
        free(vec);
        return;
    }

    printf("Page %zu: %s\n", page, (vec[page] & 1) ? "resident" : "not resident");

    free(vec);
}

typedef struct {
    unsigned long minflt;
    unsigned long majflt;

    char vmrss[64];
    char rssanon[64];
    char rssfile[64];
    char rssshmem[64];
} ProcStats;

static void get_proc_stats(ProcStats *s)
{
    memset(s, 0, sizeof(*s));

    /* ---------- /proc/self/stat ---------- */

    FILE *fp = fopen("/proc/self/stat", "r");
    if (fp) {

        char buf[4096];

        if (fgets(buf, sizeof(buf), fp)) {

            /* Skip "pid (comm)" because comm may contain spaces */
            char *p = strrchr(buf, ')');

            if (p) {

                unsigned long values[64] = {0};
                int n = 0;

                char *tok = strtok(p + 2, " ");

                while (tok && n < 64) {
                    values[n++] = strtoul(tok, NULL, 10);
                    tok = strtok(NULL, " ");
                }

                /*
                 * After ')' the fields begin with:
                 *
                 * 0 state
                 * 1 ppid
                 * ...
                 * 7 flags
                 * 8 minflt
                 * 10 majflt
                 */

                if (n > 10) {
                    s->minflt = values[7];
                    s->majflt = values[9];
                }
            }
        }

        fclose(fp);
    }

    /* ---------- /proc/self/status ---------- */

    fp = fopen("/proc/self/status", "r");

    if (fp) {

        char line[256];

        while (fgets(line, sizeof(line), fp)) {

            sscanf(line, "VmRSS: %63[^\n]", s->vmrss);
            sscanf(line, "RssAnon: %63[^\n]", s->rssanon);
            sscanf(line, "RssFile: %63[^\n]", s->rssfile);
            sscanf(line, "RssShmem: %63[^\n]", s->rssshmem);
        }

        fclose(fp);
    }
}

static void print_stats(void)
{
    static unsigned long last_min = 0;
    static unsigned long last_maj = 0;

    ProcStats s;

    get_proc_stats(&s);

    printf("\n---------------------------------------\n");

    printf("Minor Faults : %-8lu (%+ld)\n",
           s.minflt,
           (long)s.minflt - (long)last_min);

    printf("Major Faults : %-8lu (%+ld)\n",
           s.majflt,
           (long)s.majflt - (long)last_maj);

    printf("---------------------------------------\n\n");

    last_min = s.minflt;
    last_maj = s.majflt;
}

struct rusage ru;

static long last_minflt = 0;
static long last_majflt = 0;

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "Usage: %s <file>\n", argv[0]);
        return 1;
    }

    const char *filename = argv[1];

    int fd = open(filename, O_RDWR);
    if (fd < 0) {
        perror("open");
        return 1;
    }

    struct stat st;
    if (fstat(fd, &st) != 0) {
        perror("fstat");
        return 1;
    }

    size_t filesize = st.st_size;

    long pagesize = sysconf(_SC_PAGESIZE);

    if (filesize == 0) {
        fprintf(stderr, "File is empty.\n");
        return 1;
    }

    char *region = mmap(NULL,
                        filesize,
                        PROT_READ | PROT_WRITE,
                        MAP_SHARED,
                        fd,
                        0);

    if (region == MAP_FAILED) {
        perror("mmap");
        return 1;
    }

    printf("\n=====================================\n");
    printf("Page Cache Lab\n");
    printf("=====================================\n");
    printf("PID          : %d\n", getpid());
    printf("File         : %s\n", filename);
    printf("Size         : %zu bytes\n", filesize);
    printf("Page Size    : %ld\n", pagesize);
    printf("Pages        : %zu\n", filesize / pagesize);
    printf("Mapping      : %p\n", region);
    

    print_help();

    char line[256];

    while (1) {

        printf("pagecache> ");
        fflush(stdout);

        if (!fgets(line, sizeof(line), stdin))
            break;

        if (strncmp(line, "help", 4) == 0) {

            print_help();
        }

        else if (strncmp(line, "info", 4) == 0) {

            printf("\n");
            printf("PID       : %d\n", getpid());
            printf("Mapping   : %p\n", region);
            printf("Size      : %zu bytes\n", filesize);
            printf("Pages     : %zu\n", filesize / pagesize);
            printf("\n");
        }

        else if (strncmp(line, "read", 4) == 0) {

            size_t page;

            if (sscanf(line, "read %zu", &page) != 1) {
                printf("Usage: read <page>\n");
                continue;
            }

            size_t offset = page * pagesize;

            if (offset >= filesize) {
                printf("Out of range\n");
                continue;
            }

            volatile char c = region[offset];

            printf("Read page %zu : '%c' (0x%02x)\n",
                   page,
                   (c >= 32 && c <= 126) ? c : '.',
                   (unsigned char)c);
        }

        else if (strncmp(line, "write", 5) == 0) {

            size_t page;
            char ch;

            if (sscanf(line, "write %zu %c", &page, &ch) != 2) {
                printf("Usage: write <page> <char>\n");
                continue;
            }

            size_t offset = page * pagesize;

            if (offset >= filesize) {
                printf("Out of range\n");
                continue;
            }

            size_t remaining = filesize - offset;

            size_t len = remaining < (size_t)pagesize ?
                         remaining :
                         (size_t)pagesize;

            memset(region + offset, ch, len);

            printf("Filled page %zu with '%c'\n",
                   page,
                   ch);
        }

        else if (strncmp(line, "dump", 4) == 0) {

            size_t page;

            if (sscanf(line, "dump %zu", &page) != 1) {
                printf("Usage: dump <page>\n");
                continue;
            }

            size_t offset = page * pagesize;

            if (offset >= filesize) {
                printf("Out of range\n");
                continue;
            }

            printf("\n");

            for (int i = 0; i < 64; i++) {

                if (offset + i >= filesize)
                    break;

                unsigned char c = region[offset + i];

                if (c >= 32 && c <= 126)
                    putchar(c);
                else
                    putchar('.');
            }

            printf("\n\n");
        }

        else if (strncmp(line, "msync", 5) == 0) {

            if (msync(region, filesize, MS_SYNC) != 0)
                perror("msync");
            else
                printf("Pages flushed.\n");
        }

        else if (strncmp(line, "dontneed", 8) == 0) {

            if (madvise(region,
                        filesize,
                        MADV_DONTNEED) != 0)
                perror("madvise");
            else
                printf("MADV_DONTNEED completed.\n");
        }

        else if (strncmp(line, "stats", 5) == 0) {
            print_stats();
            continue;
        }

        else if (strncmp(line, "mincore", 7) == 0) {
            size_t page;
            if (sscanf(line, "mincore %zu", &page) == 1) {
                // single page query
                print_mincore_page(region, filesize, pagesize, page);
            } else {
                // compact full view
                print_mincore_compact(region, filesize, pagesize);
            }
            continue;
        }

        else if (strncmp(line, "pause", 5) == 0) {

            printf("Press ENTER...");
            getchar();
        }

        else if (strncmp(line, "quit", 4) == 0) {

            break;
        }

        else {

            printf("Unknown command.\n");
        }

        print_stats();
    }

    munmap(region, filesize);
    close(fd);

    return 0;
}
```

For the setup, i had to make some changes for this to work. 

The first issue is

```sh
/mnt # ./mm_lab2 testfile.bin
mmap: Invalid argument 
```

It happened because the `/mnt` is 9p (virtfs) mount, which doesn't support page caches by default. 

Next thing i tried is copying it into `/tmp` (tmpfs)

And i tried running

```sh
/mnt # ./mm_lab2 /tmp/testfile.bin
```

Although the program started, i immediately noticed via `mincore` that all pages are already resident! turns out `/tmp` doesn't has disk backing, and the `cp` command i ran just before this to copy it already made kernel cache everything. Clearing page cache won't help as there is no disk backing. `mincore` came in super useful here (thanks for gpt for adding this out of the box command).

```sh
/mnt # cat /proc/mounts
rootfs / rootfs rw,size=1009812k,nr_inodes=252453 0 0
none /proc proc rw,relatime 0 0
none /sys sysfs rw,relatime 0 0
none /dev devtmpfs rw,relatime,size=1009812k,nr_inodes=252453,mode=755 0 0
host /mnt 9p rw,relatime,access=client,trans=virtio 0 0
```

What worked is i had to unmount and remount 9p with `cache=mmap`. That also required some workaround as `unmount` was not present directly.

```sh
/bin/sh: umount: not found
/ # mount -t 9p -o trans=virtio,access=client,cache=mmap host /mnt
[  987.207747] 9pnet_virtio: no channels available for device host
mount: mounting host on /mnt failed: Resource busy
/ # busybox umount /mnt
/ # mount -t 9p -o trans=virtio,access=client,cache=mmap host /mnt
/ # cd /mnt
```

Now we can see cache parameter

```sh
/mnt # cat /proc/mounts
rootfs / rootfs rw,size=1009812k,nr_inodes=252453 0 0
none /proc proc rw,relatime 0 0
none /sys sysfs rw,relatime 0 0
none /dev devtmpfs rw,relatime,size=1009812k,nr_inodes=252453,mode=755 0 0
host /mnt 9p rw,relatime,cache=5,access=client,trans=virtio 0 0
```

## Observing the VFS Structures

Before we dive into internals of page cache, let's briefly check the structs and fields of VFS.

```sh
/mnt # ./mm_lab2 testfile.bin

=====================================
Page Cache Lab
=====================================
PID          : 64
File         : testfile.bin
Size         : 67108864 bytes
Page Size    : 4096
Pages        : 16384
Mapping      : 0x7f44e556e000

Commands:
  help                     Show commands
  info                     Mapping information
  read <page>              Read first byte of page
  write <page> <char>      Fill entire page with character
  dump <page>              Dump first 64 bytes
  msync                    Flush dirty pages
  dontneed                 madvise(MADV_DONTNEED)
  pause                    Wait for ENTER
  mincore                  Show all pages compact (R=resident .=not)
  mincore <page>           Check if specific page is resident
  quit

pagecache>
```

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
...
0xffff888004045880  47   kworker/0:2
0xffff888004046740  48   kworker/R-mld
0xffff8880043c8000  49   kworker/R-ipv6_
0xffff8880043c9d80  58   sh
0xffff8880043c8ec0  64   mm_lab2
```

### 1. The `files` field of `task_struct`

```sh
(gdb) set $task = (struct task_struct *)0xffff8880043c8ec0
(gdb) p $task->files
$1 = (struct files_struct *) 0xffff8880039dc580
(gdb) p *$task->files
$2 = {count = {counter = 1}, resize_in_progress = false, resize_wait = {lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0,
                tail = 0}}}}}}, head = {next = 0xffff8880039dc590, prev = 0xffff8880039dc590}}, fdt = 0xffff8880039dc5a8, fdtab = {max_fds = 64, fd = 0xffff8880039dc620,
    close_on_exec = 0xffff8880039dc608, open_fds = 0xffff8880039dc610, full_fds_bits = 0xffff8880039dc618, rcu = {next = 0x0, func = 0x0}}, file_lock = {{rlock = {raw_lock = {{val = {
              counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}}, next_fd = 4, close_on_exec_init = {0}, open_fds_init = {15}, full_fds_bits_init = {
    0}, fd_array = {0xffff888003b9e000, 0xffff888003b9e000, 0xffff888003b9e000, 0xffff888003b9e300, 0x0 <repeats 60 times>}}
(gdb)
```

This is the struct of `files`

```c
files_struct {
    atomic_t count (Simple reference count)
    unsigned int next_fd (fd for next file to be opened)

    struct fdtable __rcu *fdt 
    struct fdtable fdtab 
    
    struct file __rcu * fd_array[NR_OPEN_DEFAULT];
}
```

Here is a breakdown of how these two structs work together to manage process file descriptors efficiently using embedded fast-paths and **RCU (Read-Copy-Update)** lockless reads.


#### `struct files_struct`

Top-level container owned by a process (`task_struct->files`).

* **`count` (Reference Count)**
Tracks how many tasks/threads share this `files_struct`. Multiple threads created with `clone(..., CLONE_FILES)` share a single `files_struct`. When `count` hits 0, the struct is freed.
* **`next_fd` (Allocation Hint)**
Stores the lowest candidate FD number available. When `open()` is called, the kernel starts searching for a free slot from `next_fd` instead of scanning from index 0 every time.
* **`fdt` (Active Table Pointer)**
Pointer to the **currently active** `fdtable`. Marked `__rcu` because readers can traverse it locklessly. Initially points to the inline `fdtab` field below, but switches to point to a new heap-allocated `fdtable` if the process opens more than 64 files.
* **`fdtab` (Embedded Initial Table)**
The default `struct fdtable` embedded directly inside `files_struct`. By embedding it inline, the kernel avoids doing a separate `kmalloc()` for small processes.
* **`fd_array[NR_OPEN_DEFAULT]` (Embedded File Pointer Array)**
The default array of `struct file *` pointers (usually 64 slots). `fdtab.fd` points directly to this inline array initially.


#### `struct fdtable`

Represents the actual descriptor tables and bitmaps.

* **`max_fds` (Array Capacity)**
The total number of slots allocated in the current `fd` array and bitmaps (e.g., 64 initially). If a process opens `fd 64`, the kernel must allocate a larger `fdtable` on the heap and update `fdt`.
* **`open_fds` (Open Bitmask Pointer)**
Pointer to a bitmap where bit $N = 1$ means FD $N$ is open. This allows rapid checking of whether an FD is active without dereferencing `struct file *` pointers.
* **`fd` (Array of File Pointers)**
Pointer to an array of `struct file *` pointers. This is what you index into when resolving an integer descriptor: `fdt->fd[3]` gives the `struct file *` for FD 3.
* **`rcu` (RCU Callback Head)**
Used during dynamic table expansion. When the kernel replaces an old `fdtable` with a larger one, it doesn't free the old table immediately. It uses `call_rcu()` via this `rcu_head` to safely free the old table only after all lockless reader threads have finished accessing it.


#### The Fast-Path vs. Dynamic Path Dual-Design

```text
Small process (≤ 64 files):
files_struct
 ├── fdt ───────► fdtab (embedded)
 └── fd_array ◄── fdtab.fd

Large process (> 64 files):
files_struct
 ├── fdt ───────► [Heap Allocated fdtable] ──► fd ──► [Heap Array >64]
 └── fd_array (unused)

```

### 2. The `fdt` of files

```sh
(gdb) set $files = $task->files
(gdb) p *$files->fdt
$4 = {max_fds = 64, fd = 0xffff8880039dc620, close_on_exec = 0xffff8880039dc608, open_fds = 0xffff8880039dc610, full_fds_bits = 0xffff8880039dc618, rcu = {next = 0x0, func = 0x0}}
(gdb) p $files->fdt->fd[3]
$5 = (struct file *) 0xffff888003b9e300
```

`fd[3]` represents the pointer to `file` object from VFS. 


### 3. The `file` object

```sh
(gdb) set $my_file = $files->fdt->fd[3]
(gdb) p *$my_file
$6 = {f_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}}, f_mode = 72319007,
  f_op = 0xffffffff82252180 <v9fs_file_operations_dotl>, f_mapping = 0xffff888003ce6710, private_data = 0xffff888004597060, f_inode = 0xffff888003ce65b0, f_flags = 32770, f_iocb_flags = 0,
  f_cred = 0xffff8880045b56c0, f_owner = 0x0, f_path = {mnt = 0xffff8880045b44a0, dentry = 0xffff888003c60540}, {f_pos_lock = {owner = {counter = 0}, wait_lock = {raw_lock = {{val = {
              counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, osq = {tail = {counter = 0}}, wait_list = {next = 0xffff888003b9e360,
        prev = 0xffff888003b9e360}}, f_pipe = 0}, f_pos = 0, f_security = 0xffff88800453b940, f_wb_err = 0, f_sb_err = 0, f_ep = 0x0, {f_task_work = {next = 0x0, func = 0x0}, f_llist = {
      next = 0x0}, f_ra = {start = 0, size = 0, async_size = 0, ra_pages = 32, order = 0, mmap_miss = 0, prev_pos = -1}, f_freeptr = {v = 0}}, f_ref = {refcnt = {counter = 1}}}
(gdb)
```

`f_pos` represents the read/write cursor for this process. 

```sh
(gdb) p $my_file->f_pos
$7 = 0
```

`f_flags` represents the flags with which file was opened

```sh
(gdb) p $my_file->f_flags
$8 = 32770
```

It represents two flags

- **0x0002** (`O_RDWR`): Open for reading and writing.
- **0x8000** (`O_LARGEFILE`): Allow the file to be opened even if its size exceeds 2 GB (standard on 64-bit systems).

On 64-bit Linux systems, glibc automatically appends `O_LARGEFILE` to every single open() system call behind the scenes.

`f_mode`

The primary difference is that `f_mode` stores the kernel's internal permission and capabilities mask, while `f_flags` stores the operational behavior configuration requested by the user during the open() system call.

```sh
(gdb) p $my_file->f_mode
$9 = 72319007
```

Individual Bit Breakdown (include/linux/fs.h)

Evaluating 0x44F801F bit-by-bit matches the kernel's active internal status parameters:

- `0x0000001` (FMODE_READ): File is open for reading.
- `0x0000002` (FMODE_WRITE): File is open for writing.
- `0x0000004` (FMODE_LSEEK): File is actively seekable.
- `0x0000008` (FMODE_PREAD): File supports positional reading primitives (pread).
- `0x0000010` (FMODE_PWRITE): File supports positional writing primitives (pwrite).
- `0x0008000` (FMODE_ATOMIC_POS): File requires serialization safeguards to cleanly adjust offsets natively
- `0x0010000` (FMODE_WRITER): File tracks active underlying write credits to coordinate lock status.
- `0x0020000` (FMODE_CAN_READ): File exposes operational read handlers via internal code pipelines.
- `0x0040000` (FMODE_CAN_WRITE): File exposes operational write handlers via internal code pipelines.
- `0x4000000` (FMODE_NONOTIFY): File bypasses fsnotify event layers to avoid endless auditing recursion.

**f_mode** (Internal State)
- **Purpose**: Validates runtime operations on the VFS layer.
- **Visibility**: Only visible inside the Linux kernel (include/linux/fs.h).
- **Key Bitmasks**: FMODE_READ, FMODE_WRITE, FMODE_PREAD, FMODE_PWRITE.

**f_flags** (User Configurations)
- **Purpose**: Implements specific behavioral tracking for file access.
- **Visibility**: Visible to user-space applications via standard API headers.
- **Key Bitmasks**: O_RDWR, O_APPEND, O_NONBLOCK, O_ASYNC.

Reference to `address_space`

```sh
(gdb) p $my_file->f_mapping
$18 = (struct address_space *) 0xffff888003ce6710
```

### 4. The `inode` object

```sh
(gdb) set $inode = $my_file->f_inode
(gdb) p *$inode
$6 = {i_mode = 33204, i_opflags = 13, i_uid = {val = 1000}, i_gid = {val = 1000}, i_flags = 0, i_acl = 0xffffffffffffffff, i_default_acl = 0xffffffffffffffff,
  i_op = 0xffffffff82251e40 <v9fs_file_inode_operations_dotl>, i_sb = 0xffff888004001800, i_mapping = 0xffff888003ce6710, i_security = 0xffff888004380d20, i_ino = 37635313, {i_nlink = 1,
    __i_nlink = 1}, i_rdev = 0, i_size = 67108864, i_atime_sec = 1785296514, i_mtime_sec = 1785169042, i_ctime_sec = 1785169042, i_atime_nsec = 0, i_mtime_nsec = 565404397,
  i_ctime_nsec = 565404397, i_generation = 4212446527, i_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}},
  i_bytes = 0, i_blkbits = 17 '\021', i_write_hint = WRITE_LIFE_NOT_SET, i_blocks = 131072, i_state = 0, i_rwsem = {count = {counter = 0}, owner = {counter = 0}, osq = {tail = {
        counter = 0}}, wait_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, wait_list = {next = 0xffff888003ce6660,
      prev = 0xffff888003ce6660}}, dirtied_when = 4295497166, dirtied_time_when = 0, i_hash = {next = 0x0, pprev = 0xffff88807dd2ba38}, i_io_list = {next = 0xffff888003ce6690,
    prev = 0xffff888003ce6690}, i_lru = {next = 0xffff888003ce66a0, prev = 0xffff888003ce66a0}, i_sb_list = {next = 0xffff888003ce6988, prev = 0xffff888004001d08}, i_wb_list = {
    next = 0xffff888003ce66c0, prev = 0xffff888003ce66c0}, {i_dentry = {first = 0xffff888003c605f0}, i_rcu = {next = 0xffff888003c605f0, func = 0x0}}, i_version = {counter = 0},
  i_sequence = {counter = 0}, i_count = {counter = 1}, i_dio_count = {counter = 0}, i_writecount = {counter = 1}, i_readcount = {counter = 0}, {
    i_fop = 0xffffffff82252180 <v9fs_file_operations_dotl>, free_inode = 0xffffffff82252180 <v9fs_file_operations_dotl>}, i_flctx = 0x0, i_data = {host = 0xffff888003ce65b0, i_pages = {
      xa_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}}, xa_flags = 33, xa_head = 0x0}, invalidate_lock = {
      count = {counter = 0}, owner = {counter = 0}, osq = {tail = {counter = 0}}, wait_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {
              locked_pending = 0, tail = 0}}}}, wait_list = {next = 0xffff888003ce6740, prev = 0xffff888003ce6740}}, gfp_mask = 1051850, i_mmap_writable = {counter = 1}, i_mmap = {
      rb_root = {rb_node = 0xffff888004599988}, rb_leftmost = 0xffff888004599988}, nrpages = 0, writeback_index = 0, a_ops = 0xffffffff82252040 <v9fs_addr_operations>, flags = 64,
    wb_err = 0, i_private_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}}, i_private_list = {
      next = 0xffff888003ce6790, prev = 0xffff888003ce6790}, i_mmap_rwsem = {count = {counter = 0}, owner = {counter = 0}, osq = {tail = {counter = 0}}, wait_lock = {raw_lock = {{val = {
              counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, wait_list = {next = 0xffff888003ce67b8, prev = 0xffff888003ce67b8}},
    i_private_data = 0x0}, {i_devices = {next = 0xffff888003ce67d0, prev = 0xffff888003ce67d0}, i_linklen = 63858640}, {i_pipe = 0x0, i_cdev = 0x0, i_link = 0x0, i_dir_seq = 0},
  i_fsnotify_mask = 0, i_fsnotify_marks = 0x0, i_private = 0xffff8880045970a8}
(gdb)
```

`i_ino`: The inode number on the filesystem (unique file identifier).

```sh
(gdb) p $inode->i_ino
$7 = 37635313
```

`i_mode`: Bitfield encoding the file permissions (e.g., 0644) and file type (e.g., `S_IFREG` for regular file, `S_IFDIR` for directory).

```sh
(gdb) p $inode->i_mode
$8 = 33204
```
When you convert 33204 into octal, it becomes 100664

1. **File Type (100)** The first digits 10 (or 0100000 in full bitmask) tell the system this is a regular file (like a .txt file, a script, or a binary), rather than a directory, symlink, or device.
2. **Permissions (664)** The last three digits 664 represent the standard Linux file permissions:
   - 6 (Owner): Read and write permissions (rw-).
   - 6 (Group): Read and write permissions (rw-).
   - 4 (Others): Read-only permission (r--).

`i_nlink`: Number of hard links pointing to this inode. When this drops to 0 and all file descriptors close, the kernel frees the file's disk/storage blocks.

```sh
(gdb) p $inode->i_nlink
$9 = 1
```

`i_size`: The exact size of testfile.bin in bytes. When you mmap() a file, the kernel uses i_size to determine how many virtual pages are needed to cover the file.

```sh
(gdb) p $inode->i_size
$10 = 67108864
```

Its 64 MB.

`i_uid` / `i_gid`: Owner User ID and Group ID.

```sh
(gdb) p $inode->i_uid
$11 = {val = 1000}
(gdb) p $inode->i_gid
$12 = {val = 1000}
```

In Linux, 1000 is almost always the first human user created during OS installation.

Why 1000?
Linux reserves lower numbers for system accounts and daemons:0: Reserved exclusively for root (superuser).
- 1 to 999: Reserved for system services (like systemd, nobody, or www-data).
- 1000: The default starting point for standard users.

`i_atime` / `i_mtime` / `i_ctime`: Timestamps for last access, modification, and inode status change.

```sh
(gdb) p $inode->i_atime
There is no member named i_atime.
(gdb) p $inode->i_atime_sec
$13 = 1785296514
(gdb) p $inode->i_mtime
There is no member named i_mtime.
(gdb) p $inode->i_mtime_nsec
$14 = 565404397
(gdb) p $inode->i_mtime_sec
$15 = 1785169042
(gdb) p $inode->i_ctime_sec
$16 = 1785169042
(gdb)
```

Yes, they changed. The Linux kernel developers modified the internal layout of struct `inode` in late 2023.

The old embedded structures (`struct timespec64` fields named `i_atime`, `i_mtime`, and `i_ctime`) were flattened into discrete, standalone scalar fields like `i_atime_sec` and `i_mtime_nsec`. This layout change explains why GDB reports that `i_atime` and `i_mtime` no longer exist as direct members.

Why is nsec smaller than sec?

Your observation is a common point of confusion:
- i_mtime_sec = 1785169042
- i_mtime_nsec = 565404397

The nanosecond field (nsec) is not a fraction of the total seconds. It is a sub-second remainder that tracks the hyper-precise fractional time within that exact second.

Think of it like a stopwatch reading a lap time of 3 minutes and 12 seconds. The value "12" is numerically smaller than "3", but it represents a highly precise fraction added on top of the minutes.

blkcnt_t `i_blocks` (Number of blocks of the file)

```sh
(gdb) p $inode->i_blocks
$17 = 131072
```

Reference to `address_space` (Same as file's `f_mapping`)

```sh
(gdb) p $inode->i_mapping
$19 = (struct address_space *) 0xffff888003ce6710
```

#### The Hidden Connection: Inode vs. File Page Cache

Look at the addresses from your `$my_file` dump:

```sh
(gdb) p $inode->i_mapping
$19 = (struct address_space *) 0xffff888003ce6710
(gdb) p $inode
$20 = (struct inode *) 0xffff888003ce65b0
```

Notice that `f_mapping` is offset by only `0x160` bytes from the start of `f_inode`!

This is because `struct inode` embeds a `struct address_space` field called i_data inside itself. By default, `i_mapping` points directly to `&inode->i_data`.

```
struct file ($my_file)
 └── f_mapping ───────────────┐
                              ▼
struct inode ($inode)    ┌───────────────────────────┐
 ├── i_ino               │ struct address_space      │
 ├── i_size              │ (i_data)                  │
 └── i_data ────────────►│  - host (points to inode) │
                         │  - page_tree/i_pages      │
                         └───────────────────────────┘
```

Because the page cache belongs to the file on disk rather than any single process's open file handle, multiple processes opening testfile.bin get their own distinct struct file, but their `f_mapping` pointers all point right back to this exact same `i_data` inside the shared struct inode.

The reason the addresses are so close comes down to how C handles embedded structures versus pointers.

In C, a struct can hold another struct in two ways:

- **As a pointer:** `struct address_space *i_mapping;` (stores an 8-byte memory address pointing to somewhere else on the heap).
- **As an embedded object:** `struct address_space i_data;` (allocates the entire `address_space` memory block directly inside the `inode` memory layout).

The Linux kernel embeds `i_data` directly inside `struct inode`.

**The Memory Layout**

Because `i_data` is embedded inline, its address is literally just the start address of the inode plus the byte offset of where `i_data` sits inside the struct:

```
Memory Address        Field Inside struct inode
────────────────────────────────────────────────────────────────
0xffff888003ce65b0 ──► struct inode {
                         ├── i_ino
                         ├── i_mode
                         ├── i_size
                         │   ... (other fields take up 0x160 bytes)
0xffff888003ce6710 ──►   ├── struct address_space i_data {
                         │     ├── host ──► points back to 0xffff888003ce65b0
                         │     ├── nrpages
                         │     └── i_pages (XArray containing cached pages)
                         │   }
                       }
```

So this creates more questions than it answers, does it means `i_data` and `i_mapping` are same things?

`i_data` is the actual, physical `address_space` struct embedded inside the inode, and `i_mapping` is a pointer.

Here is exactly how they differ and why the kernel maintains both.

**The Two Fields in struct inode**

If you look at the raw source code for struct inode, you will find both fields exist side-by-side:

```c
struct inode {
    // ...
    struct address_space *i_mapping;  // 8-byte pointer
    // ...
    struct address_space i_data;      // 352-byte embedded struct
};
```

**The Default State: Pointing to Itself**

When a normal file (like your `testfile.bin`) is created, the kernel initializes the inode by pointing `i_mapping` directly to its own internal `i_data`:

```c
inode->i_mapping = &inode->i_data;
```

**If it points to itself, why not just use `i_data` directly?**

The pointer indirection exists for cache sharing.

While a regular file's `i_mapping` always points to its own `i_data`, block devices (like `/dev/sda1`) behave differently.

Imagine you mount an `ext4` filesystem on `/dev/sda1`.

When you open a device file, the kernel overrides the `i_mapping` pointer of that specific inode to point to the `i_data` of the master block device inode!

(This seems to be deeper than i thought, so leaving it here for now)

### 5. The `dentry` object

```sh
(gdb) set $dentry = $my_file->f_path.dentry
(gdb) p *$dentry
$21 = {d_flags = 2097280, d_seq = {seqcount = {sequence = 2}}, d_hash = {next = 0x0, pprev = 0xffff88807da61ab0}, d_parent = 0xffff888003c603c0, d_name = {{{hash = 819312626, len = 12},
      hash_len = 52358920178}, name = 0xffff888003c60578 "testfile.bin"}, d_inode = 0xffff888003ce65b0, d_shortname = {string = "testfile.bin", '\000' <repeats 27 times>, words = {
      7308332184076772724, 1852400174, 0, 0, 0}}, d_op = 0xffffffff82252680 <v9fs_dentry_operations>, d_sb = 0xffff888004001800, d_time = 0, d_fsdata = 0xffff888004597038, d_lockref = {{
      lock_count = 4294967296, {lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}}, count = 1}}}, {d_lru = {
      next = 0xffff888003c605c8, prev = 0xffff888003c605c8}, d_wait = 0xffff888003c605c8}, d_sib = {next = 0xffff888003c608d8, pprev = 0xffff888003c60468}, d_children = {first = 0x0},
  d_u = {d_alias = {next = 0x0, pprev = 0xffff888003ce66d0}, d_in_lookup_hash = {next = 0x0, pprev = 0xffff888003ce66d0}, d_rcu = {next = 0x0, func = 0xffff888003ce66d0}}}
(gdb)
```

`d_name`: A qstr (quick string) struct containing the filename and a hash.
- `d_name.name` points to "testfile.bin".
- `d_name.hash` is a pre-computed hash used for ultra-fast lookups in the global dentry cache (dcache) hash table.

```sh
(gdb) p $dentry->d_name
$22 = {{{hash = 819312626, len = 12}, hash_len = 52358920178}, name = 0xffff888003c60578 "testfile.bin"}
```

`d_inode`: This points directly to the struct inode we examined earlier (`0xffff888003ce65b0`). If this pointer is NULL, it means it's a "negative dentry" — the VFS caches the fact that a file does not exist to speed up repeated lookups for missing files.

```sh
(gdb) p $dentry->d_inode
$23 = (struct inode *) 0xffff888003ce65b0
```

**Tree Hierarchy (The Directory Structure)**

- `d_parent`: Points to the dentry of the parent directory (which would be `/mnt` in this case).
- `d_subdirs`: If this dentry were a directory itself, this list would contain all its child dentries.
- `d_child`: The linked list node connecting this dentry to its siblings inside `/mnt`.

**Walk up the Directory Tree in GDB**

```sh
(gdb) p $dentry->d_name.name
$26 = (const unsigned char *) 0xffff888003c60578 "testfile.bin"
(gdb) p $dentry->d_parent->d_name.name
$27 = (const unsigned char *) 0xffff888003c603f8 "/"
```

I expected `/mnt` but we see `/` here. Before we jump into this mystery, let's try to see children of `/`


```sh
(gdb) p $dentry->d_parent->d_subdirs
There is no member named d_subdirs.
```

In modern Linux kernels, `d_subdirs` was renamed to `d_children` (and the child's sibling node list was renamed from `d_child` to `d_sib`).

```sh
(gdb) ptype struct dentry
type = struct dentry {
    unsigned int d_flags;
    seqcount_spinlock_t d_seq;
    struct hlist_bl_node d_hash;
    struct dentry *d_parent;
    struct qstr d_name;
    struct inode *d_inode;
    union shortname_store d_shortname;
    const struct dentry_operations *d_op;
    struct super_block *d_sb;
    unsigned long d_time;
    void *d_fsdata;
    struct lockref d_lockref;
    union {
        struct list_head d_lru;
        wait_queue_head_t *d_wait;
    };
    struct hlist_node d_sib;
    struct hlist_head d_children;
    union {
        struct hlist_node d_alias;
        struct hlist_bl_node d_in_lookup_hash;
        struct callback_head d_rcu;
    } d_u;
}
(gdb) p $dentry->d_parent->d_children
$30 = {first = 0xffff888003c605d8}
```

The reason it says "/" instead of "mnt" is because dentry trees are confined to a single filesystem.

**The VFS Illusion**

When you type `ls /mnt/testfile.bin`, the VFS stitches two completely different filesystems together to create the illusion of a single continuous path:

- `rootfs` (Initramfs): Owns the true / and the directory `/mnt`.
- `9p` (Host Share): Owns its own internal / (the root of your exported host folder) and testfile.bin.

Because you mounted 9p onto /mnt, the kernel creates a hard boundary. The dentry you are examining ($dentry) belongs exclusively to the 9p filesystem. As far as the 9p filesystem knows, its absolute top-level root directory is simply /. It has no idea that the guest OS decided to mount it under a folder called mnt.

When you walk up the d_parent pointers, you hit the root of the 9p filesystem ("/") and stop. Its parent is itself.

### 6. The `path` object

This is how the Kernel Bridges the Gap. 

If the dentry tree stops at the filesystem boundary, how does the kernel remember that this 9p filesystem is mounted at /mnt?

This is exactly why open files don't just store a dentry pointer — they store a struct path.

```c
struct path {
    struct vfsmount *mnt;    // The mount information
    struct dentry *dentry;   // The file inside that mount
};
```

Your open file (`$my_file`) uses `f_path.dentry` to track exactly where it is inside the 9p filesystem, and it uses f_path.mnt to track exactly where that 9p filesystem is attached to the rest of the OS.

```sh
(gdb) set $vfsmnt = $my_file->f_path.mnt
(gdb) p *$vfsmnt
$32 = {mnt_root = 0xffff888003c603c0, mnt_sb = 0xffff888004001800, mnt_flags = 32, mnt_idmap = 0xffffffff82b7aee0 <nop_mnt_idmap>}
(gdb)
```

(I wanted to see the boundary where the filesystem is attached in data structures, but deviating too much so leaving it here).

### 7. The `address_space` object

```sh
(gdb) set $address_space = $inode->i_mapping
(gdb) p $address_space
$35 = (struct address_space *) 0xffff888003ce6710
(gdb) p *$address_space
$36 = {host = 0xffff888003ce65b0, i_pages = {xa_lock = {{rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0,
                tail = 0}}}}}}, xa_flags = 33, xa_head = 0x0}, invalidate_lock = {count = {counter = 0}, owner = {counter = 0}, osq = {tail = {counter = 0}},
    wait_lock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, wait_list = {next = 0xffff888003ce6740,
      prev = 0xffff888003ce6740}}, gfp_mask = 1051850, i_mmap_writable = {counter = 1}, i_mmap = {rb_root = {rb_node = 0xffff888004599988},
    rb_leftmost = 0xffff888004599988}, nrpages = 0, writeback_index = 0, a_ops = 0xffffffff82252040 <v9fs_addr_operations>, flags = 64, wb_err = 0, i_private_lock = {{
      rlock = {raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}}}, i_private_list = {
    next = 0xffff888003ce6790, prev = 0xffff888003ce6790}, i_mmap_rwsem = {count = {counter = 0}, owner = {counter = 0}, osq = {tail = {counter = 0}}, wait_lock = {
      raw_lock = {{val = {counter = 0}, {locked = 0 '\000', pending = 0 '\000'}, {locked_pending = 0, tail = 0}}}}, wait_list = {next = 0xffff888003ce67b8,
      prev = 0xffff888003ce67b8}}, i_private_data = 0x0}
```

We can see `host` is back pointer to `inode`.

`nrpages`: number of pages actually cached (we will revisit this later in the program)

```sh
(gdb) p $address_space->nrpages
$37 = 0
```

`i_mmap` 

Why this matters: When a file is modified, the kernel uses `i_mmap` to do a reverse map lookup (rmap) to find every user process virtual address space mapping this file and invalidate their page table entries!

We can see the VMA allocated to our file

```sh
/ # cat /proc/64/maps
00400000-00401000 r--p 00000000 00:15 37634937                           /mnt/mm_lab2
00401000-004b5000 r-xp 00001000 00:15 37634937                           /mnt/mm_lab2
004b5000-004de000 r--p 000b5000 00:15 37634937                           /mnt/mm_lab2
004df000-004e2000 r--p 000de000 00:15 37634937                           /mnt/mm_lab2
004e2000-004e5000 rw-p 000e1000 00:15 37634937                           /mnt/mm_lab2
004e5000-004e6000 rw-p 00000000 00:00 0
2ded3000-2def6000 rw-p 00000000 00:00 0                                  [heap]
7f44e556e000-7f44e956e000 rw-s 00000000 00:15 37635313                   /mnt/testfile.bin
7f44e956e000-7f44e9572000 r--p 00000000 00:00 0                          [vvar]
7f44e9572000-7f44e9574000 r--p 00000000 00:00 0                          [vvar_vclock]
7f44e9574000-7f44e9576000 r-xp 00000000 00:00 0                          [vdso]
7ffca0c31000-7ffca0c52000 rw-p 00000000 00:00 0                          [stack]
ffffffffff600000-ffffffffff601000 --xp 00000000 00:00 0                  [vsyscall]

7f44e556e000-7f44e956e000 rw-s 00000000 00:15 37635313                   /mnt/testfile.bin
Size:              65536 kB
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
```

```sh
(gdb) p $address_space->i_mmap
$38 = {rb_root = {rb_node = 0xffff888004599988}, rb_leftmost = 0xffff888004599988}
(gdb) c
```

If we walk the rb tree we will find the corresponding `vm_area_struct` here. 

There are no pages right now, `mincore` confirms it

```sh
pagecache> mincore

Page residency (16384 pages, R=resident .=not):

    0: ................................................................
   64: ................................................................
  128: ................................................................
  192: ................................................................
  256: ................................................................
  320: ................................................................
  384: ................................................................
  448: ................................................................
  512: ................................................................
  576: ................................................................
  640: ................................................................
  704: ................................................................
  768: ................................................................
  ...
16192: ................................................................
16256: ................................................................
16320: ................................................................
```

We can see it filling up as soon as we read a page, we can see it also caused a major fault (which means read from disk)

```sh
pagecache> read 2
Read page 2 : '.' (0x00)

---------------------------------------
Minor Faults : 37       (+4)
Major Faults : 17       (+1)
---------------------------------------

pagecache> mincore

Page residency (16384 pages, R=resident .=not):

    0: RRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRR................................
   64: ................................................................
  128: ................................................................
  192: ................................................................
  256: ................................................................
  320: ................................................................
  384: ................................................................
```

`nrpages` has increased now.

```sh
(gdb) p $address_space->nrpages
$39 = 32
```

Let's walk these pages now

Because nrpages is 32 (which is less than 64), all 32 pages fit inside a single root xa_node. You don't have to navigate a deep multi-level tree.


```sh
(gdb) p $address_space->i_pages.xa_head
$5 = (void *) 0xffff888003ceaffa
```

Look at the last hex digit: a.
In binary, hex a is 1010. The lowest two bits are 10, which is 2 in decimal.

This confirms exactly what we were looking for: the `xa_head` has a tag of 2, meaning it points to an internal `xa_node`, not directly to a page. The tree has depth!


**Step 1: Clear the Tag Bits and Get the Node**

Mask off the bottom 2 bits using & ~3UL:

```sh
(gdb) set $root_node = (struct xa_node *)((unsigned long)$address_space->i_pages.xa_head & ~3UL)
(gdb) p *$root_node
$6 = {shift = 0 '\000', offset = 0 '\000', count = 32 ' ', nr_values = 0 '\000', parent = 0x0, array = 0xffff888003ce6718, {private_list = {next = 0xffff888003ceb010,
      prev = 0xffff888003ceb010}, callback_head = {next = 0xffff888003ceb010, func = 0xffff888003ceb010}}, slots = {0xffffea00000d46c0, 0xffffea00000d4700, 0xffffea00000d4740,
    0xffffea00000d4780, 0xffffea00000d47c0, 0xffffea00000d4800, 0xffffea00000d4840, 0xffffea00000d4880, 0xffffea0000086c40, 0xffffea0000086cc0, 0xffffea0000086e00, 0xffffea00000d4c00,
    0xffffea00000a7a40, 0xffffea0000086e40, 0xffffea00000a7a80, 0xffffea0000086dc0, 0xffffea00000d48c0, 0xffffea00000d4900, 0xffffea00000d4940, 0xffffea00000d4980, 0xffffea0000086d00,
    0xffffea0000086d40, 0xffffea0000086c80, 0xffffea00000d4a40, 0xffffea00000d4a80, 0xffffea00000d4ac0, 0xffffea00000d49c0, 0xffffea00000d4a00, 0xffffea00000d4b00, 0xffffea00000d4b40,
    0xffffea00000d4b80, 0xffffea00000d4640, 0x0 <repeats 32 times>}, {tags = {{0}, {0}, {0}}, marks = {{0}, {0}, {0}}}}
(gdb)
```

Look at the shift variable in the output. If shift is 0, this node's slots contain your actual struct page pointers. If shift > 0 (like 6 or 12), it means this root node points to child xa_nodes.

Depending on where the `xa_node` sits in the tree hierarchy, a slot in `slots[64]` can contain one of three things:

- A pointer to a child `xa_node` (if it's an internal / non-leaf node where shift > 0)
- A pointer to an actual data item (if it's a leaf node where shift == 0 — in the page cache, this is a `struct page *` or `struct folio *`)
- `0x0 (NULL)` (if that slot index or file offset is empty / a sparse hole)

How the Kernel Tells Them Apart: shift and Pointer Tagging?

The kernel uses two mechanism to know what is inside a slot:

1. The Node's shift Value (Tree Depth)

|shift Value | Node Type | What slots[i] Contains |
|------------|------------|-----------------------|
| shift > 0 (e.g., 6, 12) | Internal Node | Pointers to child xa_node|
| sshift == 0 | Leaf Node | Pointers to `struct page *` (or `folio *`)

**Step 2: Print All 32 Pages At Once**

```sh
(gdb) p /x *$root_node->slots@32
$7 = {0xffffea00000d46c0, 0xffffea00000d4700, 0xffffea00000d4740, 0xffffea00000d4780, 0xffffea00000d47c0, 0xffffea00000d4800, 0xffffea00000d4840, 0xffffea00000d4880, 0xffffea0000086c40,
  0xffffea0000086cc0, 0xffffea0000086e00, 0xffffea00000d4c00, 0xffffea00000a7a40, 0xffffea0000086e40, 0xffffea00000a7a80, 0xffffea0000086dc0, 0xffffea00000d48c0, 0xffffea00000d4900,
  0xffffea00000d4940, 0xffffea00000d4980, 0xffffea0000086d00, 0xffffea0000086d40, 0xffffea0000086c80, 0xffffea00000d4a40, 0xffffea00000d4a80, 0xffffea00000d4ac0, 0xffffea00000d49c0,
  0xffffea00000d4a00, 0xffffea00000d4b00, 0xffffea00000d4b40, 0xffffea00000d4b80, 0xffffea00000d4640}
(gdb)
```

**Step 3: Inspect Any Individual Page**


Assign the page address from `slots[0]` to a GDB variable (masking off any tag bits defensively):

Print the `struct page` to ensure `$page->mapping` points back to your `$address_space` (`0xffff888003ce6710`):

```sh
(gdb) set $page = (struct page *)((unsigned long)$root_node->slots[0] & ~3UL)
(gdb) p *$page
$8 = {flags = 72057594037927976, {{{lru = {next = 0xffffea00000a7788, prev = 0xffffea00000d4708}, {__filler = 0xffffea00000a7788, mlock_count = 870152}, buddy_list = {
          next = 0xffffea00000a7788, prev = 0xffffea00000d4708}, pcp_list = {next = 0xffffea00000a7788, prev = 0xffffea00000d4708}, {pcp_llist = {next = 0xffffea00000a7788},
          order = 870152}}, mapping = 0xffff888003ce6710, {__folio_index = 0, share = 0}, private = 0}, {pp_magic = 18446719884454426504, pp = 0xffffea00000d4708,
      _pp_mapping_pad = 18446612682133890832, dma_addr = 0, pp_ref_count = {counter = 0}}, {compound_head = 18446719884454426504}, {_unused_pgmap_compound_head = 0xffffea00000a7788,
      zone_device_data = 0xffffea00000d4708}, callback_head = {next = 0xffffea00000a7788, func = 0xffffea00000d4708}}, {page_type = 0, _mapcount = {counter = 0}}, _refcount = {counter = 2}}
(gdb)
```

#### PG_dirty Flag

Let's check if a page is dirty

Here we are not checking for PTE's dirty bit, but the `PG_dirty` software flag set via kernel. In this case, since file is opened via `mmap` kernel actually relies on hardware PTE's dirty flag to set the software `PG_dirty` flag.

```sh
(gdb) p (int)PG_dirty
$46 = 4
(gdb) p ($page->flags & (1UL << 4)) != 0
$47 = 0
```

or 

```sh
(gdb) p ($page->flags & (1UL << PG_dirty)) != 0
$9 = 0
```


#### The Tree-Level Mark (`xa_node->marks`) 

If the kernel writeback thread (`kworker`) had to inspect millions of `struct page` flags one-by-one to find modified pages, performance would tank.

To solve this, the XArray (`i_pages`) maintains a fast bitmask summary inside each `xa_node` called `marks`:

```c
marks = { 
  [0] = PAGECACHE_TAG_DIRTY,    // Bitmask for dirty slots
  [1] = PAGECACHE_TAG_WRITEBACK,// Bitmask for writeback in-progress
  [2] = PAGECACHE_TAG_TOWRITE   // Bitmask for staged writebacks
}
```

Look at the `marks` output from your GDB dump of $node:

```
marks = {{0}, {0}, {0}}
```

Because `marks[0]` is `{0}`, the XArray considers all 32 pages in this file completely CLEAN.


#### Catching Dirty Pages

```sh
pagecache> write 1 a
Filled page 1 with 'a'

---------------------------------------
Minor Faults : 39       (+1)
Major Faults : 17       (+0)
---------------------------------------
```

We wrote to page 1, let's check its dirty bit. 

```sh
(gdb) set $page1 = (struct page *)((unsigned long)$root_node->slots[1] & ~3UL)
(gdb) p ($page1->flags & (1UL << PG_dirty)) != 0
$14 = 1
(gdb) p *$root_node
$13 = {shift = 0 '\000', offset = 0 '\000', count = 32 ' ', nr_values = 0 '\000', parent = 0x0, array = 0xffff888003ce6718, {private_list = {next = 0xffff888003ceb010,
      prev = 0xffff888003ceb010}, callback_head = {next = 0xffff888003ceb010, func = 0xffff888003ceb010}}, slots = {0xffffea00000d46c0, 0xffffea00000d4700, 0xffffea00000d4740,
    0xffffea00000d4780, 0xffffea00000d47c0, 0xffffea00000d4800, 0xffffea00000d4840, 0xffffea00000d4880, 0xffffea0000086c40, 0xffffea0000086cc0, 0xffffea0000086e00, 0xffffea00000d4c00,
    0xffffea00000a7a40, 0xffffea0000086e40, 0xffffea00000a7a80, 0xffffea0000086dc0, 0xffffea00000d48c0, 0xffffea00000d4900, 0xffffea00000d4940, 0xffffea00000d4980, 0xffffea0000086d00,
    0xffffea0000086d40, 0xffffea0000086c80, 0xffffea00000d4a40, 0xffffea00000d4a80, 0xffffea00000d4ac0, 0xffffea00000d49c0, 0xffffea00000d4a00, 0xffffea00000d4b00, 0xffffea00000d4b40,
    0xffffea00000d4b80, 0xffffea00000d4640, 0x0 <repeats 32 times>}, {tags = {{2}, {0}, {0}}, marks = {{2}, {0}, {0}}}}
```

The value in `marks[0][0]` is 2. In binary 10 means represents page 1. 

We can check the contents of this page

```sh
(gdb) x/10c ((char *)0xffff888000000000 + ((((unsigned long)$page1 - 0xffffea0000000000UL) / 64) << 12))
0xffff88800351c000:	97 'a'	97 'a'	97 'a'	97 'a'	97 'a'	97 'a'	97 'a'	97 'a'
0xffff88800351c008:	97 'a'	97 'a'
```

Its using `vmemmap` and direct map (which we learnt already).

`vmemmap` provides a single, mathematically contiguous virtual memory range (starting at `0xffffea0000000000` on x86_64).

Even if your physical RAM is fragmented or has huge gaps, the kernel maps the struct page objects into `vmemmap` so they look like a perfectly uniform, continuous array to the CPU.

Because `vmemmap` behaves like a massive array, turning a physical Page Frame Number (PFN) into its tracking metadata is a lightning-fast, simple pointer arithmetic operation:

```
struct page pointer  = vmemmap_base + (PFN x 64)
```

In our previous GDB command, you did this exact math in reverse to find the raw memory.

the vmemmap region is completely separate from the `vmalloc` region. They serve different purposes, have different address ranges, and allocate memory differently. 

**Key Differences**

| Feature | vmemmap | vmalloc |
|---|---|---|
| Purpose | Only stores the global array of struct page metadata. | Allocates large, virtually contiguous buffers for drivers, kernel modules, or vfs. |
| x86_64 Address | 0xffffea0000000000 | 0xffffc90000000000 |
| Physical Backing | Always backed by physical memory allocated at boot time. | Backed by non-contiguous physical pages allocated on-the-fly. |
| Page Table Type | Often uses large 2MB or 1GB pages to minimize TLB misses. | Uses standard 4KB pages because the physical memory is fragmented. |

**How to Visualise It**
Think of your kernel virtual memory as a highway with dedicated lanes:

1. Direct Map Lane: Mirrors your actual RAM. Virtual address matches physical address + an offset.
2. vmemmap Lane: A massive spreadsheet tracking the status of every 4KB block in the Direct Map.
3. vmalloc Lane: A scratchpad. When a driver asks for a massive 10MB buffer, vmalloc stitches together random, scattered physical 4KB pages from the Direct Map and makes them look like one continuous 10MB block to the driver. 

The formula is quite interesting, i understood the logic behind it, its basically the idea of vmalloc but extended for entire RAM so that its easily addressable just by PFN.

But:
- `vmalloc` takes scattered physical pages and makes them look like one continuous buffer for a driver.
- `vmemmap` takes scattered struct page structures and makes them look like one giant, continuous C array across the entire RAM space. Because it is a uniform array, `vmemmap[PFN]` lands you exactly on the correct metadata struct.

In the end, GDB used the direct map to read the data.

Here is exactly how the two regions split the work in your command:

- `vmemmap` was used only for the math: You used its base address (`0xffffea0000000000`) to calculate the Page Frame Number (PFN) and physical address from `$page1`.
- **Direct Map** was used for the actual read: You added the direct map base address (`0xffff888000000000`) to that physical address. The resulting address (`0xffff88800351c000`) sits squarely inside the direct map zone, which is where GDB went to pull the 'a' characters.

This again challenges my understanding of what is PFN, so i will add a separate section at the end. 

Continuing on the experiment, after 1-2 mins the page got flushed and is no longer dirty

```sh
(gdb) p ($page1->flags & (1UL << PG_dirty)) != 0
$15 = 0
(gdb) p *$root_node
$16 = {shift = 0 '\000', offset = 0 '\000', count = 32 ' ', nr_values = 0 '\000', parent = 0x0, array = 0xffff888003ce6718, {private_list = {next = 0xffff888003ceb010,
      prev = 0xffff888003ceb010}, callback_head = {next = 0xffff888003ceb010, func = 0xffff888003ceb010}}, slots = {0xffffea00000d46c0, 0xffffea00000d4700,
    0xffffea00000d4740, 0xffffea00000d4780, 0xffffea00000d47c0, 0xffffea00000d4800, 0xffffea00000d4840, 0xffffea00000d4880, 0xffffea0000086c40, 0xffffea0000086cc0,
    0xffffea0000086e00, 0xffffea00000d4c00, 0xffffea00000a7a40, 0xffffea0000086e40, 0xffffea00000a7a80, 0xffffea0000086dc0, 0xffffea00000d48c0, 0xffffea00000d4900,
    0xffffea00000d4940, 0xffffea00000d4980, 0xffffea0000086d00, 0xffffea0000086d40, 0xffffea0000086c80, 0xffffea00000d4a40, 0xffffea00000d4a80, 0xffffea00000d4ac0,
    0xffffea00000d49c0, 0xffffea00000d4a00, 0xffffea00000d4b00, 0xffffea00000d4b40, 0xffffea00000d4b80, 0xffffea00000d4640, 0x0 <repeats 32 times>}, {tags = {{0}, {0}, {
        0}}, marks = {{0}, {0}, {0}}}}
```

I won't try to get the actual contents of disk via `O_DIRECT` to see its not flushed (because i just tried) because of caveats with `9p` and disk backing and lack of utils. 

## A Primer on Dirty Page Tracking (Very Important)

We know hardware maintains dirty flag in PTE's and kernel maintains software dirty flags in `struct page`. Since writes via `mmap` happens via userspace entirely, then there is no kernel code involved, so my understanding was kernel periodically scans the PTE's of cached pages to check if they're marked dirty, this makes sense, but turns out there is a more simple and clever approach. 

When write happens for the first time, kernel would've marked the page as read only, so it traps the write and since kernel is the one who is gonna mark it writeable, it can also set the software `PG_Dirty` flag, this is a synchronous process now!

Now let's say a second write happened, the page is writeable, so no fault this time right? 
yes, because page is already dirty now, its not gonna care. 

Let's say the background writeback thread ran and now page is marked clean. Now kernel does a nasty thing, it sets the page as read only again! 
Now the next write again causes fault and kernel will mark it dirty again. 

Won't these faults hurt performance? 
Might be, but doesn't seem so, unless writeback happens to frequently (then we have bigger delays).

Are hardware PTE's dirty bit no use then?
Turns out it is, answered below

Attaching gemini's answers

Question
```
 the file is opened via mmap, if i write to page 0 and come back immediately to gdb (kernel freezes), let's i am good and do it in < 3 secs, can i expect to catch the page dirty? in both PG_dirty and marks? or wil it take time for kernel's worker to read hardware PTE adn update these stuff? 
```

**Yes, absolutely!** You will catch **both** `PG_dirty` and `xa_node->marks` marked as dirty immediately—the very microsecond after that single write instruction executes in user space.

You don't need to wait 3 seconds, and you don't need to wait for any background kernel worker.

---

### Why It Is Instant: Dirty Tracking is Synchronous

There is a common misconception that a background `kworker` periodically scans hardware PTEs to update kernel software flags. In reality, Linux uses the CPU's Memory Management Unit (MMU) to trap writes **synchronously** via page faults.

Here is the exact chain of events when your user-space process (`mm_lab2`) executes a write instruction (e.g., `*ptr = 'A'`):

```text
User Space: *ptr = 'A'
       │
       ▼ (CPU traps to Kernel)
Page Fault Handler (do_page_fault)
       │
       ▼
filemap_page_mkwrite()
       │
       ├──► 1. Calls folio_mark_dirty()
       │      ├── Sets PG_dirty bit in page->flags
       │      └── Sets PAGECACHE_TAG_DIRTY in xa_node->marks[0]
       │
       └──► 2. Sets Hardware PTE to Writable + Dirty
       │
       ▼
Return to User Space (Write completes)

```

---

### Step-by-Step Breakdown

1. **The Initial "Trap" Setup:**
When `mmap(MAP_SHARED)` initially mapped `testfile.bin`, the kernel intentionally left the hardware PTE marked as **read-only** (or write-protected), even though you asked for `PROT_WRITE`.
2. **The First Write Triggers `page_mkwrite`:**
The instant your C program executes `*ptr = 'A'`, the CPU sees a write to a read-only page table entry and generates a **Page Fault**.
3. **Software Update Happens FIRST:**
Inside the page fault handler, the kernel calls `filemap_page_mkwrite()`, which executes `folio_mark_dirty()`. This synchronously:
* Flips bit 4 (`PG_dirty`) on `struct page->flags`.
* Flips bit 0 (`PAGECACHE_TAG_DIRTY`) in `xa_node->marks[0]`.


4. **Hardware PTE Upgraded:**
Only *after* the page cache tree and `struct page` are marked dirty in software does the kernel upgrade the hardware PTE to writable (`PTE_WRITE`) and resume your program.

When control returns to user space, the software dirty flags are **already set**. When you break in GDB right after that instruction, you will see `PG_dirty = 1` and `marks = {{1}, {0}, {0}}`.

---

### What Background Workers *Actually* Do

Kernel background workers (`kworker` / `flusher` threads) work in reverse:

* They do **not** scan hardware PTEs to mark pages dirty.
* Instead, they read `xa_node->marks[PAGECACHE_TAG_DIRTY]` to quickly find pages that are **already marked dirty in software**, flush their contents to disk (or over 9P to your host), and then clear `PG_dirty` and `marks[0]` back to `0`.

Question 
```
There is a common misconception that a background kworker periodically scans hardware PTEs to update kernel software flags. In reality, Linux uses the CPU's Memory Management Unit (MMU) to trap writes synchronously via page faults.

-> true for first time, but for second write to same page after its flushed to disk?
```

You hit on the exact core mechanism that keeps this whole system working!

**It happens again for the second write as well.** The kernel *never* has to periodically scan hardware PTEs.

The reason it works for the second write (and the 3rd, 4th, etc.) is because **flushing the page to disk write-protects the page table entry again.**

---

### The Complete Lifecycle: 1st Write $\rightarrow$ Flush $\rightarrow$ 2nd Write

```text
  1st Write (*ptr = 'A')
         │
         ▼
  Page Fault (#PF) ──► Marks PG_dirty + XArray mark ──► Sets PTE Writable
                                                               │
  Subsequent Writes (No Fault, hits PTE_WRITE directly) ◄──────┘
         │
         ▼
  Kernel Flushes Page to Disk (kworker runs writeback)
         │
         ├── Writes data to disk
         ├── Calls page_mkclean() ──► Clears PTE_WRITE (PTE is Read-Only again!)
         └── Clears PG_dirty + XArray mark (Page is clean)
         │
         ▼
  2nd Write (*ptr = 'B')
         │
         ▼
  Page Fault (#PF) ──► Marks PG_dirty + XArray mark ──► Sets PTE Writable again!

```

---

### How the Flusher Prepares the Trap (`page_mkclean`)

When the background flusher thread (`kworker`) writes a dirty page back to disk, it executes `page_mkclean()` (via `clear_page_dirty_for_io()`).

`page_mkclean()` uses the reverse-mapping (`i_mmap`) tree we inspected earlier to find every process PTE mapping this page and **strips away the `PTE_WRITE` permission bit**.

1. **Before Flush:** PTE is `READ | WRITE | DIRTY`. Writes happen in user space at CPU speed without faults.
2. **During Flush:** Kernel writes data to storage, clears `PG_dirty`, clears `PAGECACHE_TAG_DIRTY`, and sets PTE back to `READ-ONLY`.
3. **Second Write:** Because the PTE is read-only again, the CPU **traps another page fault (`#PF`)** the instant your process tries to write to it!
4. **Kernel Handler:** `filemap_page_mkwrite()` runs a second time, immediately setting `PG_dirty` and `PAGECACHE_TAG_DIRTY` back to `1` synchronously before letting user space continue.

---

### The Invariant

The kernel maintains a strict rule: **If a page is clean in the page cache, its hardware PTEs MUST be write-protected.**

By enforcing this rule, the kernel guarantees that no user process can ever transition a page from clean to dirty without trapping into the kernel first.

Question
```
Are hardware PTE's dirty bit no use then?
```

They are actually crucial! It seems redundant at first glance, but the hardware PTE dirty bit serves a vital purpose: **it tracks writes that happen *after* the initial page fault without needing any kernel intervention.**

Here is why the kernel relies heavily on the hardware PTE dirty bit (`_PAGE_DIRTY` on x86).

---

### 1. High Performance: Zero Overhead for Writes #2 through #1,000,000

If the kernel didn't have a hardware dirty bit, it would have to keep the page write-protected forever to know if you were still writing to it. That would mean trapping into a page fault (`#PF`) on *every single write instruction*—which would make system performance collapse.

Instead, the hardware dirty bit allows a smooth two-step handoff:

1. **Write #1 (Clean $\rightarrow$ Dirty):**
* Triggers a Page Fault (`#PF`).
* Kernel sets `PG_dirty = 1` in software.
* Kernel marks the PTE as **Writable (`PTE_WRITE`)** and returns to user space.


2. **Writes #2 to #1,000,000 (Already Writable):**
* **Zero page faults!** Writes execute at full CPU memory bus speed.
* As the CPU executes `MOV` or `STR` instructions into RAM, the MMU hardware automatically flips the **hardware PTE dirty bit** to `1` in the page table.



---

### 2. "Harvesting" Hardware Dirt Back to Software

Because the CPU flipped the hardware dirty bit directly in RAM while user space was running, the kernel software didn't notice it immediately.

When the kernel eventually decides to reclaim memory, unmap a page, or flush data, it reads the PTE using `pte_dirty()`:

```c
if (pte_dirty(pte)) {
    // The CPU hardware wrote to this page while it was un-faulted!
    set_page_dirty(page);  // Sync hardware dirt back to software PG_dirty
}

```

This process is called **harvesting the dirty bit**. The kernel gathers the state recorded by the CPU hardware and syncs it back to `struct page->flags`.

---

### 3. Essential for Anonymous Memory (Heap & Stack)

For file-backed memory (`testfile.bin`), we have an `address_space` and an XArray (`i_pages`) tracking pages.

But for **Anonymous memory** (your process `[heap]`, `[stack]`, or `malloc()` calls):

* There is no underlying file or `address_space`.
* There are no XArray `marks`.

When the kernel is under heavy memory pressure and needs to reclaim RAM, it scans process page tables. It checks the **hardware PTE dirty bit**:

* **If Hardware Dirty = 0:** The heap page was never modified. The kernel can instantly throw it away to free RAM.
* **If Hardware Dirty = 1:** The CPU modified this heap page. The kernel must allocate space in **Swap**, write the page out, and clear the bit.

---

### Summary: Hardware vs. Software Dirty Bits

| Layer | Controlled By | Purpose |
| --- | --- | --- |
| **Hardware PTE (`_PAGE_DIRTY`)** | CPU MMU | Set automatically by CPU hardware on non-faulting memory writes. |
| **Software Page (`PG_dirty`)** | Kernel Software | Tracks page state across the entire OS (`struct page`). |
| **Page Cache Tree (`PAGECACHE_TAG_DIRTY`)** | Kernel Software | XArray summary bitmap used by flusher threads (`kworker`) for fast disk writeback. |

## Marks field for Dirty Trackig

The `marks` field inside `struct xa_node` is one of the most brilliant performance optimizations in the Linux Virtual Memory Manager.

Without `marks`, finding dirty or writing-back pages in a multi-gigabyte file would require sweeping millions of `struct page` objects in RAM. `marks` turns that $O(N)$ tree traversal into an $O(\log N)$ or even $O(1)$ lookup.

---

### 1. How `marks` Works Under the Hood

An `xa_node` contains 64 slots (`slots[0..63]`).

Instead of storing status flags inside individual pages, `marks` stores **summary bitmasks directly inside the tree node**:

```c
#define XA_MAX_MARKS 3

struct xa_node {
    ...
    void *slots[64];
    unsigned long marks[XA_MAX_MARKS][1]; // 3 x 64-bit integers
};

```

Because an `unsigned long` on 64-bit x86 is 64 bits wide, **1 bit in `marks` maps to 1 slot in `slots[]**`:

* If bit 0 of `marks[PAGECACHE_TAG_DIRTY]` is `1`, then `slots[0]` is dirty.
* If bit 5 of `marks[PAGECACHE_TAG_WRITEBACK]` is `1`, then `slots[5]` is currently writing back to disk.

---

### 2. The "Bubble-Up" Hierarchical Propagation

The real power of `marks` comes from **tree propagation**.

If a page at slot 0 in a leaf node becomes dirty, the kernel sets the dirty bit in that leaf's `marks[0]`. It then **bubbles that bit up** to the parent node, the grandparent node, all the way to `xa_head`.

```text
Root xa_node
 └── marks[DIRTY] = 0x0000000000000002  (Bit 1 set -> Child 1 has dirty pages!)
      └── Child Node 1
           └── marks[DIRTY] = 0x0000000000000001  (Bit 0 set -> Slot 0 is dirty!)
                └── slots[0] ──► struct page (Dirty)

```

#### Why this matters for I/O performance:

When the `kworker` flusher thread runs `sys_sync()` or `msync()`, it checks `xa_head`.

* If bit 1 in the root node's `marks[DIRTY]` is `0`, **the kernel skips that entire subtree instantly**. It never wastes CPU cycles traversing millions of clean pages.

---

### 3. Deep-Dive on the 3 Tags

Linux maintains three distinct tags per node. Each serves a specific phase of the memory-to-disk pipeline:

| Tag Index | Constant | Purpose |
| --- | --- | --- |
| **0** | `PAGECACHE_TAG_DIRTY` | Page data in RAM is newer than disk. Needs flush. |
| **1** | `PAGECACHE_TAG_WRITEBACK` | Page is actively being transmitted to storage/disk I/O. |
| **2** | `PAGECACHE_TAG_TOWRITE` | Staged "snapshot" tag used to prevent sync livelocks. |

#### Why does `PAGECACHE_TAG_TOWRITE` exist? (The Livelock Problem)

Imagine a database process doing continuous heavy writes in a loop (`while(1) write(...)`).

If `sync()` only used `PAGECACHE_TAG_DIRTY`, the flusher thread would enter an **infinite loop**: as fast as it flushes dirty pages, the application dirty-marks new ones in the same file!

**The Solution (`TOWRITE`):**

1. When `writepages()` starts, the kernel calls `tag_pages_for_writeback()`.
2. It takes a **snapshot** by copying all current `PAGECACHE_TAG_DIRTY` marks into `PAGECACHE_TAG_TOWRITE`.
3. The flusher thread **only flushes pages tagged `TOWRITE**`.
4. If user space writes new data during the flush, those pages get marked `DIRTY`, but **not** `TOWRITE`. `writepages()` finishes cleanly without hanging!

---

### 4. Complete Lifecycle of a Page's Tags

Here is how the three tags flip in `xa_node->marks` as a page moves from user modification to disk:

```text
1. User writes to page (mmap or write syscall)
   ├── PAGECACHE_TAG_DIRTY     = 1  ▲ (Marked dirty)
   ├── PAGECACHE_TAG_WRITEBACK = 0
   └── PAGECACHE_TAG_TOWRITE   = 0

2. Flush Begins (writepages takes snapshot)
   ├── PAGECACHE_TAG_DIRTY     = 1
   ├── PAGECACHE_TAG_WRITEBACK = 0
   └── PAGECACHE_TAG_TOWRITE   = 1  ▲ (Tagged for this flush pass)

3. I/O Submitted to Disk / 9P (folio_start_writeback)
   ├── PAGECACHE_TAG_DIRTY     = 0  ▼ (Cleared)
   ├── PAGECACHE_TAG_WRITEBACK = 1  ▲ (I/O in progress!)
   └── PAGECACHE_TAG_TOWRITE   = 0  ▼ (Cleared)

4. Disk Interrupt Signals Completion (folio_end_writeback)
   ├── PAGECACHE_TAG_DIRTY     = 0
   ├── PAGECACHE_TAG_WRITEBACK = 0  ▼ (Cleared -> Page is now completely clean)
   └── PAGECACHE_TAG_TOWRITE   = 0

```

---

### Inspecting Marks in GDB

You can inspect the raw 64-bit integer bitmasks directly for your 32 pages:

```sh
# Print marks[0] (PAGECACHE_TAG_DIRTY)
(gdb) p /x $node->marks[0][0]

# Print marks[1] (PAGECACHE_TAG_WRITEBACK)
(gdb) p /x $node->marks[1][0]

# Print marks[2] (PAGECACHE_TAG_TOWRITE)
(gdb) p /x $node->marks[2][0]

```

* If `$node->marks[0][0]` evaluates to `0x0`, all 64 slots under this node are **clean**.
* If it evaluates to `0x1`, **slot 0** is dirty.
* If it evaluates to `0xffffffff`, the first **32 slots** are all dirty!

## What is Page Frame Number?

The final result of 4 level page table lookup is technically called PFN (PA is derived from this by simple PFN << 12). To save space, the CPU hardware architects decided: "Since physical memory is always chopped into 4KB chunks, the lower 12 bits of any page's starting address are always zero. Let's completely discard those 12 zeros to free up space for flags."

So out of 48 but VA, we only need to store 36 bit (might vary becase of archs). 

### What Exactly is `vmemmap` and How does PFN related to `vmemmap`

Let's discover `vmemmap` from first principles. We know direct map is a fast way of getting VA from PA and vice versa. But let's think about this scenario, let's say kernel us deailing with a `page *` just like we were doing above while we printed 'a'. Now kernel has `page *` but suddenly it has no idea what this page is, means kernel neither knows its VA nor PA, of course it can have multiple VA's. The `page *` obviously doesn;t contain PA or PFN because its a lean 64 bytes data structure, if 36 bits gets wasted for storing something we already know then imagine how many total space wasted overall. 

So what kernel does is: when it creates these giant list of `page *`, it doesn't create them like a linked list data structure, instead it assigns them sequentially in memory so that:

- page 0 resides as a magic constant address (vmemmap base)
- page 1 resides at vmemmap base + 64 bytes 
- page 2 resides at vmemmap base + 128 bytes 
- ...

Now notice we stored an additional information in an indrect way, since all pages are sequential, subtracing their address from vmemmap base / 64 gives us its PFN. 

Now once we find PFN, we can use direct map trick PA -> VA because PFN = PA >> 12 