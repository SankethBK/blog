--- 
title:  "Rust Notes — Module 4"
date:   2026-03-21
categories: ["rust"]
tags: ["traits"]

---

# Rust Notes — Module 4: Traits

---

## 1. What is a Trait?

A trait defines a set of behaviors (methods) that a type must implement. It is a **contract** — any type that implements the trait promises to provide those behaviors.

```rust
trait Greet {
    fn hello(&self) -> String;
}
```

| Concept | Rust | C++ | Go |
|---|---|---|---|
| Trait | `trait` | abstract class / concept | interface |
| Implementation | `impl Trait for Type` | override virtual method | implicit (duck typing) |
| Dispatch | static (default) or dynamic | virtual table | interface table |

---

## 2. Implementing a Trait

```rust
struct Human { name: String }
struct Robot { id: u32 }

impl Greet for Human {
    fn hello(&self) -> String {
        format!("Hi, I'm {}!", self.name)
    }
}

impl Greet for Robot {
    fn hello(&self) -> String {
        format!("BEEP. I AM UNIT {}.", self.id)
    }
}
```

- Each type provides its own implementation of the trait methods.
- A type can implement any number of traits.
- You can implement traits for types you didn't define (with some restrictions — see orphan rule below).

---

## 3. Default Implementations

Traits can provide default method implementations. Types can override them or inherit them for free:

```rust
trait Greet {
    fn hello(&self) -> String;  // no default — must implement

    fn greet_loudly(&self) -> String {  // default implementation
        self.hello().to_uppercase()
    }
}

impl Greet for Human {
    fn hello(&self) -> String {
        format!("Hi, I'm {}!", self.name)
    }
    // greet_loudly() inherited for free — no need to implement
}

impl Greet for Robot {
    fn hello(&self) -> String {
        format!("BEEP. I AM UNIT {}.", self.id)
    }

    fn greet_loudly(&self) -> String {  // override the default
        format!("!!! BEEP BEEP UNIT {} !!!", self.id)
    }
}
```

Default implementations can call other methods in the same trait, even ones without defaults.

---

## 4. Traits as Parameters — Static Dispatch

Write a function that accepts any type implementing a trait:

```rust
// impl Trait syntax — clean and readable
fn print_greeting(item: &impl Greet) {
    println!("{}", item.hello());
}

// trait bound syntax — equivalent, more explicit
fn print_greeting<T: Greet>(item: &T) {
    println!("{}", item.hello());
}

fn main() {
    let h = Human { name: String::from("Sanketh") };
    let r = Robot { id: 42 };

    print_greeting(&h);  // "Hi, I'm Sanketh!"
    print_greeting(&r);  // "BEEP. I AM UNIT 42."
}
```

This is **static dispatch** — the compiler generates a separate optimized version of the function for each concrete type at compile time. Zero runtime overhead, like C++ templates.

### Multiple Trait Bounds

```rust
fn print_greeting<T: Greet + std::fmt::Debug>(item: &T) {
    println!("{:?}", item);      // requires Debug
    println!("{}", item.hello()); // requires Greet
}
```

### `where` Clause — Cleaner Syntax for Complex Bounds

```rust
// hard to read with many bounds
fn foo<T: Greet + Debug + Clone, U: Display + PartialEq>(t: &T, u: &U) { ... }

// cleaner with where
fn foo<T, U>(t: &T, u: &U)
where
    T: Greet + Debug + Clone,
    U: Display + PartialEq,
{ ... }
```

---

## 5. Returning Types that Implement Traits

```rust
fn make_greeter() -> impl Greet {
    Human { name: String::from("Sanketh") }
}
```

> ⚠️ `impl Trait` in return position means the function returns *one specific concrete type* — the caller just doesn't know which. You cannot return different types conditionally with `impl Trait`. For that, use trait objects (`Box<dyn Trait>` — covered later).

---

## 6. Trait Objects — Dynamic Dispatch

When you need to store different types implementing the same trait in a collection, or return different types at runtime, use `dyn Trait`:

```rust
fn make_greeter(is_human: bool) -> Box<dyn Greet> {
    if is_human {
        Box::new(Human { name: String::from("Sanketh") })
    } else {
        Box::new(Robot { id: 42 })
    }
}

// store different types in one Vec
let greeters: Vec<Box<dyn Greet>> = vec![
    Box::new(Human { name: String::from("Sanketh") }),
    Box::new(Robot { id: 42 }),
];

for g in &greeters {
    println!("{}", g.hello());
}
```

This is **dynamic dispatch** — uses a vtable at runtime, like C++ virtual functions. Small runtime cost, but enables heterogeneous collections.

| | `impl Trait` | `dyn Trait` |
|---|---|---|
| Dispatch | Static (compile time) | Dynamic (runtime vtable) |
| Performance | Zero overhead | Small vtable lookup cost |
| Return different types | ❌ No | ✅ Yes |
| Store mixed types in Vec | ❌ No | ✅ Yes |

---

## 7. Common Standard Library Traits

### `Debug` and `Display`

```rust
use std::fmt;

// Debug — for {:?} printing, usually derived
#[derive(Debug)]
struct Board { ... }

// Display — for {} printing, must implement manually
impl fmt::Display for Board {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "Board at move {}", self.fullmove)
    }
}
```

### `Clone` and `Copy`

```rust
// Clone — explicit deep copy via .clone()
// Copy  — implicit copy on assignment (stack types only)
// Copy requires Clone

#[derive(Clone, Copy)]
enum Color { White, Black }

let a = Color::White;
let b = a;         // Copy — a is still valid
let c = a.clone(); // Clone — explicit
```

> A type can only be `Copy` if all its fields are `Copy`. Heap types (`String`, `Vec`) are never `Copy`.

### `PartialEq` and `Eq`

```rust
#[derive(PartialEq, Eq)]
enum Piece { Pawn, Knight, Bishop, Rook, Queen, King }

let p = Piece::Queen;
println!("{}", p == Piece::Queen);  // true
println!("{}", p != Piece::Pawn);   // true
```

- `PartialEq` — equality might not be defined for all values (e.g. `f64` where `NaN != NaN`)
- `Eq` — equality is total, always well defined. Requires `PartialEq`. Use for integers, enums, structs with no floats.

### `PartialOrd` and `Ord`

```rust
#[derive(PartialEq, Eq, PartialOrd, Ord)]
enum Rank { One, Two, Three }  // variants ordered by declaration order

let a = Rank::One;
let b = Rank::Three;
println!("{}", a < b);   // true
```

### `From` and `Into`

Convert between types cleanly:

```rust
// implement From — Into is auto-implemented
impl From<Piece> for i32 {
    fn from(p: Piece) -> i32 {
        p.value()
    }
}

let val: i32 = i32::from(Piece::Queen);  // 900
let val: i32 = Piece::Queen.into();      // same, via auto Into
```

### `Iterator`

Implementing `Iterator` gives you access to the entire iterator adapter chain — `.map()`, `.filter()`, `.fold()`, `.collect()` etc. — for free:

```rust
struct BitboardIter {
    bb: u64,
}

impl Iterator for BitboardIter {
    type Item = u32;  // yields square indices

    fn next(&mut self) -> Option<u32> {
        if self.bb == 0 {
            None
        } else {
            let sq = self.bb.trailing_zeros();
            self.bb &= self.bb - 1;  // pop lsb
            Some(sq)
        }
    }
}

// now you can do:
for square in BitboardIter { bb: my_bitboard } {
    println!("piece on square {}", square);
}
```

This is particularly useful for a chess engine — iterate over set bits in a bitboard with a clean for loop.

---

## 8. Derive Macros — Auto-implementing Traits

`#[derive(...)]` generates trait implementations automatically for simple types:

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Color { White, Black }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Piece { Pawn, Knight, Bishop, Rook, Queen, King }
```

### Rules for `derive`

- `Copy` requires `Clone`
- `Eq` requires `PartialEq`
- `Ord` requires `PartialOrd` + `Eq`
- `Hash` requires `Eq`
- `Copy` only works if **all fields** are `Copy` — cannot derive `Copy` on a struct containing `String` or `Vec`

---

## 9. `pub` and `const fn`

### `pub` — Visibility

Everything in Rust is **private by default**. `pub` opts into visibility outside the current module:

```rust
pub struct Board { ... }          // type is public
pub fn make_move(&mut self) { }   // method is public
    pieces: [[u64; 6]; 2],        // field is private (no pub)
```

| Visibility | Meaning |
|---|---|
| *(nothing)* | Private — only accessible in the same module |
| `pub` | Public — accessible anywhere |
| `pub(crate)` | Visible within the crate only |
| `pub(super)` | Visible to the parent module only |

### `const fn` — Compile-time Evaluation

`const fn` marks a function as evaluable at compile time — Rust's equivalent of C++ `constexpr`:

```rust
impl Piece {
    #[inline]
    pub const fn value(self) -> i32 {
        match self {
            Piece::Pawn   => 100,
            Piece::Knight => 320,
            Piece::Bishop => 330,
            Piece::Rook   => 500,
            Piece::Queen  => 900,
            Piece::King   => 20000,
        }
    }
}

// evaluated entirely at compile time — baked into binary as literal 900
const QUEEN_VALUE: i32 = Piece::Queen.value();
```

- Can be used to initialize `const` and `static` values
- Can be used in array sizes and match arms
- Only a subset of Rust is allowed inside `const fn` (no heap allocation, no runtime I/O)

### `#[inline]`

Hints to the compiler to inline the function at call sites — equivalent to C++'s `inline`. For tiny frequently-called functions like `value()`, this avoids function call overhead:

```rust
#[inline]
pub fn popcount(bb: u64) -> u32 {
    bb.count_ones()
}
```

Use `#[inline(always)]` to force inlining, `#[inline(never)]` to prevent it.

---

## 10. The Orphan Rule

You can implement a trait for a type **only if** at least one of — the trait or the type — is defined in your crate:

```rust
// ✅ your trait, external type
impl Greet for String { ... }

// ✅ external trait, your type
impl std::fmt::Display for Board { ... }

// ❌ both external — compile error
impl std::fmt::Display for String { ... }
```

This prevents two libraries from conflicting by implementing the same trait for the same type.

---

## 11. Quick Reference

```
trait Foo { fn bar(&self); }            →  define a trait (contract)
impl Foo for MyType { fn bar() { } }    →  implement a trait for a type
fn f(x: &impl Foo)                      →  accept any type implementing Foo (static dispatch)
fn f<T: Foo>(x: &T)                     →  equivalent trait bound syntax
T: Foo + Bar                            →  multiple trait bounds
Box<dyn Foo>                            →  trait object, dynamic dispatch
#[derive(Debug, Clone, Copy, ...)]      →  auto-implement common traits
pub                                     →  make item visible outside module
pub const fn                            →  compile-time evaluable public function
#[inline]                               →  hint to inline at call sites
```

---

## Key Takeaways

- Traits are Rust's interfaces — they define contracts that types must fulfill.
- `impl Trait for Type` is explicit — unlike Go's duck typing, you must opt in.
- Default implementations let traits provide free behavior that types can override.
- `impl Trait` parameters use static dispatch (compile-time, zero overhead) — like C++ templates.
- `dyn Trait` (trait objects) use dynamic dispatch (runtime vtable) — like C++ virtual functions.
- The standard library traits (`Debug`, `Clone`, `Copy`, `PartialEq`, `Iterator`, `From`) are the backbone of the ecosystem — derive them liberally on simple types.
- `const fn` = `constexpr` — evaluated at compile time, baked into the binary.
- `pub` = explicit visibility opt-in — everything is private by default.
- The orphan rule prevents conflicting trait implementations across crates.