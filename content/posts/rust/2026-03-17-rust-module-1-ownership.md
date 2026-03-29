---
title:  "Rust Notes — Module 1"
date:   2026-03-17
draft: true
categories: ["rust"]
tags: ["variables", "functions", "ownership"]


---

# Rust Notes — Module 1: The Basics & Ownership

---

## 1. Why Rust?

| Language | Memory Management | Cost |
|----------|------------------|------|
| C | Manual (`malloc`/`free`) | Unsafe — use-after-free, double-free, null deref |
| Go | Garbage Collector | Safe, but runtime overhead (GC pauses) |
| **Rust** | **Ownership system (compiler-enforced)** | **Safe + zero runtime cost** |

Rust's core promise: **memory safety at compile time, with no garbage collector.**

---

## 2. Variables & Mutability

- Variables are **immutable by default** in Rust.
- You must explicitly opt into mutation with `mut`.

```rust
let x = 5;        // immutable — cannot be reassigned
// x = 6;         // ❌ compile error

let mut y = 5;    // mutable
y = 6;            // ✅ fine
```

### Shadowing

You can redeclare a variable with `let` in the same scope — this is called **shadowing**:

```rust
let x = 5;
let x = x + 1;    // shadows previous x
let x = x * 2;    // shadows again
println!("{}", x); // 12
```

Shadowing is different from `mut` — it lets you change the type too, and the original binding is gone.

---

## 3. Data Types

Rust is **statically typed** with **type inference**. You can annotate explicitly or let the compiler infer.

### Integer Types

| Signed | Unsigned | Size |
|--------|----------|------|
| `i8` | `u8` | 8-bit |
| `i16` | `u16` | 16-bit |
| `i32` | `u32` | 32-bit (default integer) |
| `i64` | `u64` | 64-bit |
| `i128` | `u128` | 128-bit |
| `isize` | `usize` | pointer-sized (arch dependent) |

```rust
let a: i32 = -42;
let b: u8 = 255;
let c = 42;       // inferred as i32
```

### Floating Point

```rust
let x: f32 = 3.14;
let y: f64 = 3.14159265; // default float type
```

### Boolean

```rust
let flag: bool = true;
let other = false; // inferred
```

### Character

```rust
let ch = 'z';         // Unicode scalar — 4 bytes (unlike C's 1-byte char)
let emoji = '😀';     // valid!
```

### Compound Types

**Tuple** — fixed size, can mix types:
```rust
let tup: (i32, f64, bool) = (42, 3.14, true);
let (x, y, z) = tup;    // destructuring
let first = tup.0;       // index access
```

**Array** — fixed size, same type, stack-allocated:
```rust
let arr = [1, 2, 3, 4, 5];
let arr2: [i32; 5] = [1, 2, 3, 4, 5];
let zeros = [0; 5];      // [0, 0, 0, 0, 0]
let third = arr[2];      // index access
```

> ⚠️ Out-of-bounds array access causes a **runtime panic** in Rust (not undefined behavior like C).

---

## 4. Functions

```rust
fn function_name(param1: Type1, param2: Type2) -> ReturnType {
    // body
}
```

- Parameter types and return type must always be **explicitly annotated**.
- The **last expression without a semicolon** is the implicit return value.
- `return` keyword works for early returns.

```rust
fn add(a: i32, b: i32) -> i32 {
    a + b       // no semicolon = return value
}

fn early_return(x: i32) -> i32 {
    if x < 0 {
        return 0;  // early return
    }
    x * 2
}
```

### Statements vs Expressions

- **Statement**: performs an action, does not return a value (ends with `;`)
- **Expression**: evaluates to a value (no `;`)

```rust
let y = {
    let x = 3;
    x + 1       // expression — this block evaluates to 4
};
// y == 4
```

---

## 5. Control Flow

### `if` expressions

`if` is an **expression** in Rust — it returns a value:

```rust
let number = 7;

if number < 5 {
    println!("small");
} else if number < 10 {
    println!("medium");
} else {
    println!("large");
}

// if as expression
let label = if number % 2 == 0 { "even" } else { "odd" };
```

> Both branches of an `if` expression must return the **same type**.

### Loops

**`loop`** — infinite loop, can return a value:
```rust
let mut counter = 0;
let result = loop {
    counter += 1;
    if counter == 10 {
        break counter * 2;  // loop returns this value
    }
};
// result == 20
```

**`while`** — conditional loop:
```rust
let mut n = 3;
while n != 0 {
    println!("{}", n);
    n -= 1;
}
```

**`for`** — idiomatic iteration:
```rust
let arr = [10, 20, 30];
for element in arr {
    println!("{}", element);
}

for i in 0..5 {     // 0, 1, 2, 3, 4
    println!("{}", i);
}

for i in 0..=5 {    // 0, 1, 2, 3, 4, 5 (inclusive)
    println!("{}", i);
}
```

---

## 6. Ownership — The Core of Rust

### The Three Rules

1. Every value has exactly **one owner**.
2. When the owner goes **out of scope**, the value is **dropped** (memory freed).
3. There can only be **one owner at a time**.

```rust
{
    let s = String::from("hello");  // s owns the string
    // use s
}   // s goes out of scope → string is dropped here automatically
```

### Stack vs Heap

| | Stack | Heap |
|---|---|---|
| Size | Fixed at compile time | Dynamic |
| Allocation | Fast (just move stack pointer) | Slower (allocator finds space) |
| Examples | integers, bools, chars, arrays, tuples | `String`, `Vec`, `Box` |

- **Stack types** (implement `Copy` trait): assignment copies the value.
- **Heap types**: assignment **moves** ownership.

### Move Semantics

```rust
// Stack type — Copy
let x = 5;
let y = x;          // x is COPIED, both x and y are valid
println!("{} {}", x, y);  // ✅

// Heap type — Move
let s1 = String::from("hello");
let s2 = s1;        // ownership MOVES to s2, s1 is invalidated
// println!("{}", s1);  // ❌ compile error: value moved
println!("{}", s2);      // ✅
```

The compiler invalidates `s1` at compile time to prevent **double-free** (both `s1` and `s2` trying to free the same heap memory when they go out of scope).

### Clone — Explicit Deep Copy

```rust
let s1 = String::from("hello");
let s2 = s1.clone();          // deep copy of heap data
println!("{} {}", s1, s2);    // ✅ both valid
```

Clone is expensive — it copies heap data. Use it deliberately.

### Ownership & Functions

Passing a heap-type to a function **moves** ownership into the function:

```rust
fn takes_ownership(s: String) {
    println!("{}", s);
}   // s is dropped here

fn makes_copy(x: i32) {
    println!("{}", x);
}   // x is dropped, but i32 is Copy so the caller's copy is fine

fn main() {
    let s = String::from("hello");
    takes_ownership(s);
    // println!("{}", s);  // ❌ s was moved

    let x = 5;
    makes_copy(x);
    println!("{}", x);    // ✅ i32 is Copy
}
```

Functions can return ownership back:

```rust
fn gives_ownership() -> String {
    String::from("hello")   // ownership moves to caller
}

fn takes_and_gives_back(s: String) -> String {
    s   // ownership moves back to caller
}
```

### Types that implement `Copy` (stack-only, cheap to duplicate)

- All integer types (`i32`, `u64`, etc.)
- Floating point types (`f32`, `f64`)
- `bool`
- `char`
- Tuples, if all their elements implement `Copy`

---

## 7. Quick Reference — Ownership Patterns

```
let s = String::from("x")   → s owns heap data
let t = s                   → ownership MOVES to t, s invalid
let t = s.clone()           → deep copy, both s and t valid
fn f(s: String)             → ownership moves into f
fn f(s: &String)            → borrow (see Module 2)
```

---

## Key Takeaways

- Rust enforces **one owner per value** — no shared mutable state by default
- **Stack types are copied**, heap types are **moved**
- When an owner goes out of scope, Rust automatically calls `drop()` — no manual free, no GC
- The **compiler** catches all use-after-move, double-free, and dangling pointer bugs — not at runtime
- `clone()` is the escape hatch for deep copies — use deliberately