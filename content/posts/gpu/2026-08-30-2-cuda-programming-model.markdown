---
title:  "CUDA Programming Model: Writing and Launching Kernels"
date:   2026-08-30
categories: ["gpu"]
tags: ["gpu", "cuda", "nvidia", "parallel-computing", "programming"]

---

# CUDA Programming Model: Writing and Launching Kernels

The [previous note](/gpu/2026-08-30-cuda-thread-hierarchy) covered the hierarchy: thread, warp, block, grid, and how those map to SMs. This note turns that hierarchy into actual code. By the end, you will have seen a complete CUDA program, understood every line, and know how a host program hands work to the GPU.

CUDA is an extension of C/C++. Most of the code you write is ordinary C++. A small number of CUDA-specific pieces — kernel functions, the launch syntax, a few memory APIs, and built-in thread indices — turn a sequential program into a massively parallel one.

---

## 1. The two processors: host and device

A CUDA program runs on two processors:

- **Host**: the CPU, with its own memory (system RAM).
- **Device**: the GPU, with its own memory (device memory, physically separate).

The host runs ordinary C++ code. It can launch kernels, allocate GPU memory, copy data between CPU and GPU, and wait for the GPU to finish. The device runs CUDA kernels — the parallel functions executed by thousands of GPU threads.

```text
+-------------+                              +-------------+
|     CPU     |                              |     GPU     |
|    Host     |  ←── cudaMalloc, cudaMemcpy  |   Device    |
|             |      kernel launch, sync     |             |
| System RAM  |      ───────────────────►    |  Device RAM |
|             |      PCIe / NVLink           |             |
+-------------+                              +-------------+
```

The two memories are separate. If you have an array in CPU memory, the GPU cannot use it directly until you copy it to GPU memory. There are newer features like Unified Memory that blur this boundary, but understanding explicit copies first is essential.

---

## 2. A kernel is just a function that runs on the GPU

A CUDA kernel is a C++ function annotated with `__global__`. It runs on the GPU and is called from the CPU.

```cpp
__global__ void add(int n, float *a, float *b, float *c)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        c[i] = a[i] + b[i];
    }
}
```

Look at it carefully:

- `__global__` tells CUDA: this function runs on the device, but is launched from the host.
- The function body is written from the point of view of **one thread**.
- `threadIdx.x` and `blockIdx.x` are built-in variables. Each thread sees its own values.
- The `if (i < n)` guard is needed when `n` is not a multiple of the block size.

When the host launches this kernel with enough threads, every element of the arrays gets its own worker.

---

## 3. Launching a kernel: the <<< >>> syntax

From the host, you call a kernel with triple angle brackets:

```cpp
add<<<numBlocks, blockSize>>>(n, d_a, d_b, d_c);
```

Inside the brackets:

- First argument: **grid dimensions** — how many blocks to launch.
- Second argument: **block dimensions** — how many threads per block.

Both can be 1D, 2D, or 3D. For now, think 1D.

Example:

```cpp
int n = 1 << 20;            // 1,048,576 elements
int blockSize = 256;        // threads per block
int numBlocks = (n + blockSize - 1) / blockSize;  // round up

add<<<numBlocks, blockSize>>>(n, d_a, d_b, d_c);
```

This launches `numBlocks` blocks, each with 256 threads, for a total of `numBlocks * 256` threads. The rounding-up division ensures we have at least `n` threads, even if `n` is not divisible by 256.

```text
n = 1,000, blockSize = 256
numBlocks = (1000 + 255) / 256 = 1256 / 256 = 4 (integer division)

Total threads launched = 4 * 256 = 1024
Threads with i >= 1000 hit the guard and do nothing
```

The guard is cheap compared to the benefit of simple block-size arithmetic.

---

## 4. The built-in index variables

Inside a kernel, every thread has access to these built-in variables:

| Variable | Meaning | Range |
|----------|---------|-------|
| `threadIdx.x` | Thread index inside its block | 0 to `blockDim.x - 1` |
| `blockIdx.x` | Block index inside the grid | 0 to `gridDim.x - 1` |
| `blockDim.x` | Number of threads per block | whatever you launched with |
| `gridDim.x` | Number of blocks in the grid | whatever you launched with |

For 2D or 3D launches, `.y` and `.z` versions also exist.

The global thread ID in 1D is:

```text
int i = blockIdx.x * blockDim.x + threadIdx.x;
```

This formula is worth memorizing. It says: each block covers a contiguous chunk of `blockDim.x` elements, and `threadIdx.x` picks the offset inside that chunk.

```text
block 0 covers elements 0..255      → blockIdx.x=0, threadIdx.x=0..255
block 1 covers elements 256..511  → blockIdx.x=1, threadIdx.x=0..255
block 2 covers elements 512..767  → blockIdx.x=2, threadIdx.x=0..255

i = blockIdx.x * 256 + threadIdx.x
```

---

## 5. A complete first CUDA program: vector addition

Here is a minimal, compilable CUDA program that adds two vectors.

```cpp
#include <stdio.h>

__global__ void add(int n, float *a, float *b, float *c)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        c[i] = a[i] + b[i];
    }
}

int main()
{
    int n = 1 << 20;                       // 1M elements
    size_t bytes = n * sizeof(float);

    // Host arrays
    float *h_a = (float *)malloc(bytes);
    float *h_b = (float *)malloc(bytes);
    float *h_c = (float *)malloc(bytes);

    for (int i = 0; i < n; i++) {
        h_a[i] = 1.0f;
        h_b[i] = 2.0f;
    }

    // Device arrays
    float *d_a, *d_b, *d_c;
    cudaMalloc(&d_a, bytes);
    cudaMalloc(&d_b, bytes);
    cudaMalloc(&d_c, bytes);

    // Copy host → device
    cudaMemcpy(d_a, h_a, bytes, cudaMemcpyHostToDevice);
    cudaMemcpy(d_b, h_b, bytes, cudaMemcpyHostToDevice);

    // Launch kernel
    int blockSize = 256;
    int numBlocks = (n + blockSize - 1) / blockSize;
    add<<<numBlocks, blockSize>>>(n, d_a, d_b, d_c);

    // Copy device → host
    cudaMemcpy(h_c, d_c, bytes, cudaMemcpyDeviceToHost);

    // Verify (check first few)
    for (int i = 0; i < 5; i++) {
        printf("h_c[%d] = %f\n", i, h_c[i]);
    }

    // Cleanup
    cudaFree(d_a); cudaFree(d_b); cudaFree(d_c);
    free(h_a); free(h_b); free(h_c);

    return 0;
}
```

### Walkthrough

1. **Allocate host memory** with `malloc`. These arrays live in CPU RAM.
2. **Allocate device memory** with `cudaMalloc`. These pointers refer to GPU RAM.
3. **Copy input data** from host to device with `cudaMemcpy(..., cudaMemcpyHostToDevice)`.
4. **Launch the kernel** with `<<< >>>`.
5. **Copy results back** with `cudaMemcpy(..., cudaMemcpyDeviceToHost)`.
6. **Free both memories** with `cudaFree` (device) and `free` (host).

This is the canonical CUDA workflow. Almost every CUDA program follows this skeleton.

---

## 6. Memory allocation and copy API

CUDA exposes device memory through a small set of C functions.

### cudaMalloc

```cpp
cudaError_t cudaMalloc(void **devPtr, size_t size);
```

Allocates `size` bytes in device memory. The pointer is valid only on the device side. You do not dereference it from host code.

```cpp
float *d_x;
cudaMalloc(&d_x, n * sizeof(float));
```

> The pointer is valid only on the device side. You do not dereference it from host code. Let's unpack this further

It means the memory address assigned to `d_x` points to a physical location inside the GPU’s VRAM, not your CPU’s system RAM.

Because the CPU and GPU have physically separate memory spaces on separate hardware buses (connected via PCIe), your CPU host code cannot directly read from or write to that memory address using standard C/C++ operators like `*d_x` or `d_x[0]`.

**What Happens If You Try to Dereference It?**

If you try to read or modify device memory directly from CPU code like this:

```cpp
float *d_x;
cudaMalloc(&d_x, 100 * sizeof(float));

// ❌ WRONG: Dereferencing a GPU pointer on the CPU
*d_x = 3.14f;       
printf("%f\n", d_x[0]);
```

Your program will instantly crash with a Segmentation Fault (or access violation error).

To the CPU's memory controller, the memory address stored in `d_x` points to invalid or unmapped system memory because the actual data lives across the PCIe bus inside the GPU hardware.

**How You Actually Work With Device Pointers**

To interact with memory allocated via `cudaMalloc`, you must pass the pointer to CUDA functions or GPU kernels:

1. Inside GPU Kernel Code (Device Side):
Once passed into a `__global__` or `__device__` function, GPU threads execute on the GPU hardware, so dereferencing d_x works fine:

```cpp
__global__ void myKernel(float *d_x) {
    d_x[threadIdx.x] = 3.14f; // ✅ VALID: Executing inside the GPU
}
```

2. Using Explicit Transfer Functions (Host Side):
To move data between CPU RAM and GPU VRAM from host code, you must pass the pointer to API functions like `cudaMemcpy`:

```cpp
float h_x = 3.14f; // Lives in CPU RAM

// ✅ VALID: Tells the CUDA driver to transfer bytes over PCIe into VRAM
cudaMemcpy(d_x, &h_x, sizeof(float), cudaMemcpyHostToDevice);
```


### cudaFree

```cpp
cudaError_t cudaFree(void *devPtr);
```

Frees device memory allocated by `cudaMalloc`.

### cudaMemcpy

```cpp
cudaError_t cudaMemcpy(void *dst, const void *src, size_t count,
                       cudaMemcpyKind kind);
```

Copies `count` bytes from `src` to `dst`. The `kind` argument specifies the direction:

- `cudaMemcpyHostToDevice` — CPU to GPU
- `cudaMemcpyDeviceToHost` — GPU to CPU
- `cudaMemcpyDeviceToDevice` — GPU to GPU
- `cudaMemcpyHostToHost` — CPU to CPU

```cpp
// Host array h_x to device array d_x
cudaMemcpy(d_x, h_x, bytes, cudaMemcpyHostToDevice);
```

`cudaMemcpy` is synchronous with respect to the host: it does not return until the copy is complete. There are asynchronous variants (`cudaMemcpyAsync`) used for overlapping copies and compute, but start with the synchronous version.

---

## 7. Kernel execution qualifiers

CUDA uses function qualifiers to say where code runs and where it is called from.

| Qualifier | Runs on | Called from | Notes |
|-----------|---------|-------------|-------|
| `__global__` | Device (GPU) | Host (CPU) | Returns `void`; can be launched with `<<< >>>` |
| `__device__` | Device (GPU) | Device (GPU) | Helper functions called from kernels |
| `__host__` | Host (CPU) | Host (CPU) | Ordinary C++ function; implicit if no qualifier |

A common pattern:

```cpp
__device__ float clamp(float x, float lo, float hi)
{
    return (x < lo) ? lo : ((x > hi) ? hi : x);
}

__global__ void process(float *out, const float *in, int n)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        out[i] = clamp(in[i], 0.0f, 1.0f);
    }
}
```

`clamp` is a device helper. `process` is the kernel launched from the host.

---

## 8. Synchronization: cudaDeviceSynchronize

Kernel launches are **asynchronous** with respect to the host. The host line:

```cpp
add<<<numBlocks, blockSize>>>(n, d_a, d_b, d_c);
```

returns immediately. The GPU starts working in the background. If the host then immediately reads `h_c`, it may read stale data because the kernel has not finished.

To wait for all previously launched GPU work to complete:

```cpp
cudaDeviceSynchronize();
```

In our vector addition example, `cudaMemcpy` after the kernel implicitly waits for the kernel to finish because the copy needs the result. But in general, if you launch a kernel and then want to use the result on the host without a copy, you must call `cudaDeviceSynchronize()`.

```text
Host timeline:

  launch kernel ──► kernel runs on GPU (async)
       │
       │  host can do other CPU work here
       │
       ▼
  cudaDeviceSynchronize()  ← host blocks until GPU is done
       │
       ▼
  use result
```

There is also `__syncthreads()`, but that is for threads *inside a block* to synchronize, not for host-device synchronization.

---

## 9. Error checking

CUDA functions return `cudaError_t`. Production code checks every call. For learning, you can use a simple wrapper macro:

```cpp
#define cudaCheck(ans) { gpuAssert((ans), __FILE__, __LINE__); }
inline void gpuAssert(cudaError_t code, const char *file, int line)
{
    if (code != cudaSuccess) {
        fprintf(stderr, "CUDA error at %s:%d: %s\n",
                file, line, cudaGetErrorString(code));
        exit(1);
    }
}
```

Then wrap calls:

```cpp
cudaCheck(cudaMalloc(&d_a, bytes));
cudaCheck(cudaMemcpy(d_a, h_a, bytes, cudaMemcpyHostToDevice));
add<<<numBlocks, blockSize>>>(n, d_a, d_b, d_c);
cudaCheck(cudaGetLastError());          // catch kernel launch errors
cudaCheck(cudaDeviceSynchronize());     // catch runtime kernel errors
```

Kernel launch errors are reported asynchronously, so `cudaGetLastError()` checks the launch itself and `cudaDeviceSynchronize()` catches errors that happen while the kernel runs (like out-of-bounds memory access).

---

## 10. 2D indexing: an image example

For 2D data, use 2D blocks and grids. Built-in variables `.x` and `.y` now matter.

```cpp
__global__ void addImages(int width, int height,
                          float *a, float *b, float *c)
{
    int col = blockIdx.x * blockDim.x + threadIdx.x;
    int row = blockIdx.y * blockDim.y + threadIdx.y;

    if (col < width && row < height) {
        int idx = row * width + col;
        c[idx] = a[idx] + b[idx];
    }
}
```

Launch:

```cpp
dim3 blockSize(16, 16);                     // 256 threads per block
dim3 numBlocks((width + 15) / 16, (height + 15) / 16);
addImages<<<numBlocks, blockSize>>>(width, height, d_a, d_b, d_c);
```

`dim3` is a CUDA type with `.x`, `.y`, `.z`. Here the grid is 2D, matching the image.

```text
Image: width × height pixels
Divided into 16×16 thread blocks

         col 0..15      col 16..31
       +-----------+-----------+
row0-15| block(0,0)| block(1,0)|
       +-----------+-----------+
row16-31| block(0,1)| block(1,1)|
       +-----------+-----------+

Total threads per block = 16 * 16 = 256
```

The row-major index `row * width + col` is the standard way to map a 2D coordinate into a 1D array in C/C++.

---

## 11. What nvcc does

CUDA source files usually have a `.cu` extension. You compile them with `nvcc`, NVIDIA's compiler driver.

```bash
nvcc -o vector_add vector_add.cu
```

`nvcc` splits the file:

- Host code is passed to the host C++ compiler (gcc/clang/MSVC).
- Device code is compiled by the NVIDIA PTX compiler and assembler.
- The final linker combines host and device code into one executable.

You generally do not need to understand the details of this split; just remember that `.cu` files can contain both host and device code, and `nvcc` knows how to separate them.

---

## 12. The full mental model, in one picture

```text
Host code (CPU)
   │
   │  cudaMalloc, cudaMemcpy(H2D)
   ▼
Device memory (GPU RAM)
   │
   │  add<<<numBlocks, blockSize>>>(...)
   │      kernel launch: creates Grid of Blocks
   ▼
Grid
 └── Block 0  ──→ SM 7
 │     └── Warp 0 (threads 0..31)
 │     └── Warp 1 (threads 32..63)
 │     └── ...
 └── Block 1  ──→ SM 12
 │     └── Warp 0
 │     └── ...
 └── ...
   │
   │  each thread: i = blockIdx.x * blockDim.x + threadIdx.x
   │               c[i] = a[i] + b[i]
   ▼
Device memory (results)
   │
   │  cudaMemcpy(D2H)
   ▼
Host memory (CPU RAM)
```

This is the full loop: host allocates, copies, launches, waits, copies back, frees.

---

## 13. Common first mistakes

### Forgetting the `if (i < n)` guard

If `n` is not a multiple of `blockSize`, you launch extra threads. Without the guard, those threads read and write out of bounds.

### Dereferencing a device pointer from host code

`d_a` is not accessible from the CPU. You must use `cudaMemcpy`, not `h_c[i] = d_c[i]`.

### Launching with zero blocks

If `numBlocks` computes to 0 because of integer division bugs, the kernel does not run and your output is unchanged.

### Confusing `__syncthreads()` with `cudaDeviceSynchronize()`

`__syncthreads()` synchronizes threads inside one block. `cudaDeviceSynchronize()` synchronizes the host with the whole GPU. They solve different problems.

### Copying too little data

The `bytes` argument to `cudaMemcpy` must match the allocation size. Off-by-one errors here lead to garbage or silent wrong results.

---

## 14. Summary

A CUDA program is ordinary C++ plus a few new concepts:

- `__global__` kernels run on the GPU but are launched from the CPU.
- `<<<grid, block>>>` decides how many threads run and how they are grouped.
- Inside the kernel, `blockIdx`, `threadIdx`, `blockDim`, and `gridDim` tell each thread which data element to work on.
- Device memory is separate: `cudaMalloc`, `cudaMemcpy`, and `cudaFree` manage it.
- Kernel launches are asynchronous; `cudaDeviceSynchronize()` waits for the GPU.

The programming model is a direct translation of the hardware hierarchy. You write scalar code for one thread, launch it as a grid of blocks, and the hardware maps those blocks to SMs, warps to schedulers, and threads to ALU lanes.

---

## 15. What comes next

With the programming model in place, the next notes should tackle the first performance topics:

- **Memory coalescing**: why threads in a warp should access contiguous memory, and what happens when they do not.
- **Occupancy**: how register and shared-memory usage determine how many warps can live on an SM.
- **Shared-memory tiling**: using `__shared__` to load data once and reuse it across a block.

These are where CUDA stops being "write a kernel" and starts being "make the GPU actually fast."
