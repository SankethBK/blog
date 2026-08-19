---
title:  "Setuid Binaries"
date:   2026-08-02
categories: ["setuid"]
tags: ["setuid"]
references:
  
---

# Setuid Binaries

```sh
# ls -la /bin/su
-rwsr-xr-x    1 root     root         67816 Aug  1 20:00 /bin/su
```

### Types of permissions and actions

## 1. The Three Types of Users (Who)

Linux divides the entire universe of users into three distinct categories. Permissions are always listed in this exact order: 

- Owner (User): The specific person who owns the file (usually the creator).
- Group: A defined collection of users who share access (e.g., a "developers" or "finance" group).
- Others: Everyone else on the system who is not the owner and not in the group.

The owner and group are stored in inode. 

## 2. The Three Basic Actions (What)

For each of those three user categories, you can grant or deny three basic actions:

- r (Read): The right to look inside. For a file, this means opening it to read the data. For a directory, it means listing the files inside it.
- w (Write): The right to make changes. For a file, this means editing or deleting it. For a directory, it means adding or removing files.
- x (Execute): The right to run. For a file, this means running it as a program or script. For a directory, it means entering it (using cd). 

## How to read the output of ls -la 

### File Types (First Character)

- **`-`** : Regular file (text file, binary, image, script)
- **`d`** : Directory (folder)
- **`l`** : Symbolic link (a shortcut pointing to another file)

### What `r`, `w`, and `x` Mean

The permissions `r`, `w`, and `x` behave differently depending on whether they apply to a **file** or a **directory**:

| Symbol | Name | Effect on Files | Effect on Directories |
| --- | --- | --- | --- |
| **`r`** | **Read** | View or copy file contents (`cat`, `less`) | List files contained inside (`ls`) |
| **`w`** | **Write** | Modify or overwrite file contents (`nano`, `echo`) | Create, delete, or rename files inside |
| **`x`** | **Execute** | Run the file as a program or shell script | Enter/traverse into the directory (`cd`) |
| **`-`** | **Denied** | Permission is not granted | Permission is not granted |

> **Directory Gotcha:** You need **`x`** permission on a directory to navigate into it or access its contents. Read (`r`) permission alone only lets you view the filenames in the directory, not read the files themselves.

### The Numeric (Octal) System

Permissions are commonly represented by 3-digit numbers (like `755` or `644`). Each letter is assigned a point value:

- **`r` (Read)** = **4**
- **`w` (Write)** = **2**
- **`x` (Execute)** = **1**
- **`-` (None)** = **0**
  
To calculate a section's value, add the numbers together:

- `rwx` = 4 + 2 + 1 = **7** (Full permissions)
- `rw-` = 4 + 2 + 0 = **6** (Read and write)
- `r-x` = 4 + 0 + 1 = **5** (Read and execute)
- `r--` = 4 + 0 + 0 = **4** (Read only)
- `---` = 0 + 0 + 0 = **0** (No permissions)

## The Setuid bit

The SetUID (Set User ID) bit is a special Linux permission that temporarily elevates a user's privileges while running a specific program.

### The Core Concept

- **Default Behavior**: When you run an executable, it runs with your user permissions.
- **SetUID Behavior**: When you run an executable with SetUID enabled, it runs with the permissions of the file's owner (frequently root), regardless of who executed it.

### Why Does SetUID Exist?

Consider the `passwd` command, which allows users to change their account password:

- Changing your password requires updating the `/etc/shadow` file.
- The `/etc/shadow` file is owned by root and unreadable/unwritable by regular users for security reasons (-rw-------).
- To bypass this chicken-and-egg problem, `/usr/bin/passwd` has the SetUID bit set and is owned by root:

When a regular user runs `passwd`, the Linux kernel executes the binary under the privileges of root, allowing the program to write to `/etc/shadow` safely.

### How to Spot SetUID in ls -l

Look at the execute (`x`) slot in the Owner section:

- `s` (lowercase): SetUID is set, and the owner has execute permission (`-rwsr-xr-x`).
- `S` (uppercase): SetUID is set, but the owner lacks execute permission (`-rwSr-xr-x`), which indicates a misconfiguration.

### How to Manage SetUID

#### 1. Symbolic Notation

```sh
chmod u+s myfile   # Enables SetUID
chmod u-s myfile   # Disables SetUID
```

#### 2. Numeric (Octal) Notation

SetUID adds a 4th digit to the standard 3-digit permission code, taking the value 4:

```sh
chmod 4755 mybinary   # 4 (SetUID) + 755 (rwxr-xr-x) -> -rwsr-xr-x
```

### Key Security Rules

- **Privilege Escalation Risk**: Any binary with SetUID owned by root is a target for attackers. If the code has a buffer overflow or logic vulnerability, users can exploit it to gain root access.
- **Ignored on Scripts**: Modern Linux kernels ignore SetUID on interpreted scripts (like #!/bin/bash or Python scripts). It only applies to compiled, native ELF binaries.

## Manual setuid Experiment

Let's create our own test programs to understand this:

```c
sanketh@ubuntu20:~$ cat show_ids.c
#include <stdio.h>
#include <unistd.h>
#include <sys/types.h>

int main() {
    uid_t ruid, euid, suid;
    getresuid(&ruid, &euid, &suid);
    printf("Real UID: %d\n", ruid);
    printf("Effective UID: %d\n", euid);
    printf("Saved UID: %d\n", suid);

    printf("\nUsing system commands:\n");
    system("id");
    return 0;
}
```

Compile it

```sh
sanketh@ubuntu20:~$ gcc -o show_ids show_ids.c
show_ids.c: In function ‘main’:
show_ids.c:7:5: warning: implicit declaration of function ‘getresuid’; did you mean ‘setreuid’? [-Wimplicit-function-declaration]
    7 |     getresuid(&ruid, &euid, &suid);
      |     ^~~~~~~~~
      |     setreuid
show_ids.c:13:5: warning: implicit declaration of function ‘system’ [-Wimplicit-function-declaration]
   13 |     system("id");
      |     ^~~~~~
```

Create copies with different permissions

```sh
sanketh@ubuntu20:~$ cp show_ids normal_binary
sanketh@ubuntu20:~$ cp show_ids setuid_binary
```

```sh
sanketh@ubuntu20:~$ ls -la normal_binary setuid_binary
-rwxrwxr-x 1 sanketh sanketh 16888 Aug  2 11:19 normal_binary
-rwxrwxr-x 1 sanketh sanketh 16888 Aug  2 11:19 setuid_binary
sanketh@ubuntu20:~$ chown root:root setuid_binary
chown: changing ownership of 'setuid_binary': Operation not permitted
sanketh@ubuntu20:~$ sudo chown root:root setuid_binary
[sudo] password for sanketh:
sanketh@ubuntu20:~$ ls -la normal_binary setuid_binary
-rwxrwxr-x 1 sanketh sanketh 16888 Aug  2 11:19 normal_binary
-rwxrwxr-x 1 root    root    16888 Aug  2 11:19 setuid_binary
```

```sh
sanketh@ubuntu20:~$ ./normal_binary
Real UID: 1000
Effective UID: 1000
Saved UID: 1000

Using system commands:
uid=1000(sanketh) gid=1000(sanketh) groups=1000(sanketh),4(adm),24(cdrom),27(sudo),30(dip),46(plugdev),120(lpadmin),133(lxd),134(sambashare)
sanketh@ubuntu20:~$ ./setuid_binary
Real UID: 1000
Effective UID: 1000
Saved UID: 1000

Using system commands:
uid=1000(sanketh) gid=1000(sanketh) groups=1000(sanketh),4(adm),24(cdrom),27(sudo),30(dip),46(plugdev),120(lpadmin),133(lxd),134(sambashare)
sanketh@ubuntu20:~$
```

It didn't work because we haven't set the setuid bit yet

```sh
sanketh@ubuntu20:~$ sudo chmod u+s setuid_binary
sanketh@ubuntu20:~$ ls -l setuid_binary
-rwsrwxr-x 1 root root 16888 Aug  2 11:19 setuid_binary
```

```sh
sanketh@ubuntu20:~$ ./setuid_binary
Real UID: 1000
Effective UID: 0
Saved UID: 0

Using system commands:
uid=1000(sanketh) gid=1000(sanketh) groups=1000(sanketh),4(adm),24(cdrom),27(sudo),30(dip),46(plugdev),120(lpadmin),133(lxd),134(sambashare)
sanketh@ubuntu20:~$
```

The real UID answers roughly:
Who launched me?

The effective UID answers:
Whose privileges should the kernel use when checking most permissions for me?


