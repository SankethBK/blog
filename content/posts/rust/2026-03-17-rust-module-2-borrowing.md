---
title:  "Rust Notes — Module 2"
date:   2026-03-17
categories: ["rust"]
tags: ["borrowing", "references", "ownership"]

---

# Rust Notes — Module 2: Borrowing & References

---

## 1. The Problem Ownership Alone Creates

If ownership always moves, passing values to functions becomes painful — you lose access to the value after the call:

```rust
fn print_string(s: String) {
    println!("{}", s);
}  // s is dropped here

fn main() {
    let s = String::from("hello");
    print_string(s);
    // println!("{}", s); // ❌ s was moved into print_string, gone!
}
```

You'd have to clone everything or return ownership back — both are tedious. **Borrowing** solves this.

---

## 2. References — Borrow Without Taking Ownership

A reference lets a function use a value without owning it. The `&` operator creates a reference.

```rust
fn print_string(s: &String) {   // & = "reference to"
    println!("{}", s);
}   // s goes out of scope, but owns nothing — nothing is dropped

fn main() {
    let s = String::from("hello");
    print_string(&s);            // pass a reference — borrow s
    println!("{}", s);           // ✅ s still valid, we only lent it
}
```

- Creating a reference is called **borrowing**.
- The function borrows the value, uses it, and gives it back implicitly when the reference goes out of scope.
- The original owner is never invalidated.

### Memory Model

```
Stack                    Heap
-----                    ----
s  ──────────────────►  [ h | e | l | l | o ]
                                  ▲
ref (&s) ────────────────────────┘   (points to s's heap data, read-only)
```

---

## 3. Mutable References

By default, borrowed references are **immutable** — you can read through them but not modify. To modify through a reference, use `&mut`:

```rust
fn append(s: &mut String) {
    s.push_str(" world");
}

fn main() {
    let mut s = String::from("hello");  // variable must be mut
    append(&mut s);                      // reference must be &mut
    println!("{}", s);  // "hello world"
}
```

Both the variable (`mut s`) **and** the reference (`&mut s`) must be marked mutable.

---

## 4. The Borrow Rules

The compiler enforces these rules statically — no runtime cost:

### Rule 1: Any number of immutable references simultaneously

```rust
let s = String::from("hello");
let r1 = &s;
let r2 = &s;
let r3 = &s;
println!("{} {} {}", r1, r2, r3);  // ✅ all fine
```

### Rule 2: Exactly one mutable reference — exclusive access

```rust
let mut s = String::from("hello");
let r1 = &mut s;
// let r2 = &mut s;  // ❌ compile error — two mutable refs!
// let r3 = &s;      // ❌ compile error — can't mix &mut and &
```

### Summary Table

| Situation | Allowed? |
|-----------|----------|
| Multiple `&` (immutable) refs | ✅ Yes |
| Single `&mut` (mutable) ref | ✅ Yes |
| Multiple `&mut` refs | ❌ No |
| `&mut` ref + any `&` ref simultaneously | ❌ No |

> Think of it like a **readers-writers lock**, but enforced at compile time with zero runtime overhead. Multiple readers are fine. One writer means exclusive access.

while a `&mut` borrow is active, the original owner is frozen — you can't read or write through it until the mutable reference's scope ends.

```rs
let mut s = String::from("hello");
let r = &mut s;

r.push_str(" world");   // ✅ modify through the mutable ref
// s.push_str("!!!");   // ❌ compile error — s is frozen while r is active

println!("{}", r);      // r's last use — scope ends here

s.push_str("!!!");      // ✅ now fine, r is no longer active
```

### Non-Lexical Lifetimes (NLL)

The compiler is smart — a reference's scope ends at its **last use**, not at the end of the enclosing block:

```rust
let mut s = String::from("hello");

let r1 = &s;
let r2 = &s;
println!("{} {}", r1, r2);  // r1 and r2 last used here — their scope ends here

let r3 = &mut s;            // ✅ fine! r1 and r2 are no longer active
println!("{}", r3);
```

---

## 5. Dangling References — Caught at Compile Time

In C, returning a pointer to a local variable compiles fine but crashes at runtime (dangling pointer). Rust makes this a **compile error**:

```rust
fn dangle() -> &String {       // ❌ compile error
    let s = String::from("hello");
    &s                         // s is dropped when function returns — reference would dangle!
}
```

Fix: return the owned value instead of a reference:

```rust
fn no_dangle() -> String {
    let s = String::from("hello");
    s   // ownership moves to caller — no dangling reference
}
```

---

## 6. The Slice Type

A slice is a **reference to a contiguous sequence** of elements in a collection. It does not own the data.

### String Slices (`&str`)

```rust
let s = String::from("hello world");

let hello = &s[0..5];   // "hello"  — start..end (end is exclusive)
let world = &s[6..11];  // "world"
let all   = &s[..];     // entire string

// Shorthand
let hello = &s[..5];    // start from 0
let world = &s[6..];    // go to end
```

### String Literals are Slices

```rust
let s = "hello world";   // type is &str — a slice into read-only binary memory
```

This is why string literals are immutable — `&str` is an immutable reference.

### Using `&str` over `&String` in Function Signatures

Prefer `&str` as parameter type — it accepts both `String` references and string literals:

```rust
fn first_word(s: &str) -> &str {     // ✅ more flexible
    let bytes = s.as_bytes();
    for (i, &byte) in bytes.iter().enumerate() {
        if byte == b' ' {
            return &s[0..i];
        }
    }
    &s[..]
}

fn main() {
    let s = String::from("hello world");
    let word = first_word(&s);          // pass &String — coerces to &str
    let word2 = first_word("hello");    // pass &str directly — also works
}
```

### Array Slices

Slices work on any collection, not just strings:

```rust
let arr = [1, 2, 3, 4, 5];
let slice: &[i32] = &arr[1..3];  // [2, 3]
println!("{:?}", slice);
```

---

## 7. Ownership vs Borrowing — Decision Guide

| You need to... | Use |
|---|---|
| Transfer data permanently | Owned value (`String`, `Vec`, etc.) |
| Read data without owning | Immutable reference (`&T`) |
| Modify data without owning | Mutable reference (`&mut T`) |
| Read part of a string/array | Slice (`&str`, `&[T]`) |

---

## 8. Rust vs C — Reference Safety Comparison

| Bug | C | Rust |
|-----|---|------|
| Dangling pointer (return ptr to local) | Compiles, UB at runtime | ❌ Compile error |
| Double free | Compiles, crash at runtime | ❌ Impossible — one owner |
| Use after free | Compiles, UB at runtime | ❌ Compile error |
| Data race (two writers) | Compiles, race condition | ❌ Compile error |
| Null dereference | Compiles, crash at runtime | ❌ No null in safe Rust |

---

## 9. Quick Reference — Borrowing Patterns

```
&T          → immutable reference — can read, cannot modify
&mut T      → mutable reference — can read and modify, exclusive access
&s[a..b]    → slice — borrowed view of a range, does not own
&str        → string slice type — preferred for string params
&[T]        → array/vec slice type
```

---

## Key Takeaways

- `&T` borrows a value without taking ownership — the original owner is unaffected.
- `&mut T` allows modification but enforces exclusive access — no other refs can exist simultaneously.
- The borrow rules (multiple readers OR one writer) prevent data races at compile time with zero runtime cost.
- Dangling references are impossible in safe Rust — the compiler tracks lifetimes statically.
- `&str` is a string slice — prefer it over `&String` in function parameters for flexibility.
- String literals (`"hello"`) are of type `&str` — slices into read-only program memory.