# Linux Kernel Lab Access Notes

These notes record how to reach the Linux kernel lab used for the articles in this directory.

## SSH to the Ubuntu host

From a machine on the same network, connect to the Ubuntu 20.04 host:

```sh
ssh sanketh@192.168.1.14
```

Use the configured SSH authentication. Do not store credentials in this file.

## QEMU lab

The lab is launched on the Ubuntu host from the home directory:

```sh
cd /home/sanketh
./kernel-lab/boot-bildroot.sh
```

The running QEMU command uses `-s`, which opens its GDB stub on TCP port `1234`. Its serial console is exposed at `localhost:4321` on the Ubuntu host:

```sh
telnet localhost 4321
```

The serial Telnet console may already have a client attached. Avoid opening another while it is in use.

## Attach GDB to the running guest

The matching kernel source tree and debug-symbol file are under `/home/sanketh/linux`. `vmlinux` must match the kernel image booted by QEMU.

On the Ubuntu host:

```sh
cd /home/sanketh/linux
gdb vmlinux
```

Then at the GDB prompt:

```gdb
target remote :1234
```

Connecting pauses the guest. Read-only checks include:

```gdb
info registers rip
p init_task.pid
```

Use `continue` to resume the guest. Use `detach` to disconnect GDB, let the guest continue, and free the stub for another debugger session.

## When Codex needs to inspect the guest

After confirming that no other GDB client is connected, Codex can start its own interactive GDB session through SSH:

```sh
ssh -tt sanketh@192.168.1.14 'cd /home/sanketh/linux && gdb vmlinux'
```

At the prompt, run `target remote :1234`. QEMU normally has one active GDB client, so do not start a second connection while another GDB is attached. GDB access pauses the guest; detach when inspection is complete unless the user asks to leave it paused.

If port `1234` is already occupied, check for an existing debugger session first. Do not restart QEMU or terminate another session without the user's instruction.
