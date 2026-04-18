---
title:  "Rust Notes — Module 3"
date:   2026-03-21
categories: ["rust"]
tags: ["structs", "enums"]

---

# Rust Notes — Module 3: Structs & Enums

---

## 1. Structs

Structs group related data together into a named type — same concept as C structs, cleaner syntax.

```rust
struct User {
    username: String,
    email: String,
    age: u32,
    active: bool,
}
```

### Creating and Accessing

```rust
let user = User {
    username: String::from("sanketh"),
    email: String::from("sanketh@example.com"),
    age: 20,
    active: true,
};

println!("{}", user.username);  // field access with .
```

### Mutability

The **entire instance** must be `mut` — you cannot mark individual fields as mutable:

```rust
let mut user = User { ... };
user.age = 21;      // ✅
user.active = false; // ✅
```

### Struct Update Syntax

Create a new instance reusing fields from another:

```rust
let user2 = User {
    email: String::from("new@example.com"),
    ..user1    // fill remaining fields from user1
};
```

> ⚠️ If any moved fields are heap types (like `String`), `user1` is partially moved and can no longer be used as a whole.

### Tuple Structs

Structs without named fields — useful for newtype wrappers:

```rust
struct Color(u8, u8, u8);
struct Point(f64, f64, f64);

let black = Color(0, 0, 0);
let origin = Point(0.0, 0.0, 0.0);

let r = black.0;   // access by index
```

### Unit Structs

Structs with no fields — useful for implementing traits on a type with no data:

```rust
struct Marker;
let m = Marker;
```

### Printing Structs

Add `#[derive(Debug)]` to enable `{:?}` and `{:#?}` (pretty-print) formatting:

```rust
#[derive(Debug)]
struct Rectangle {
    width: f64,
    height: f64,
}

let r = Rectangle { width: 10.0, height: 5.0 };
println!("{:?}", r);   // Rectangle { width: 10.0, height: 5.0 }
println!("{:#?}", r);  // pretty-printed, each field on its own line
```

---

## 2. Methods with `impl`

Attach functions to a struct using an `impl` block. This is Rust's equivalent of C++ member functions.

```rust
struct Rectangle {
    width: f64,
    height: f64,
}

impl Rectangle {
    // &self — immutable borrow of the instance (read-only method)
    fn area(&self) -> f64 {
        self.width * self.height
    }

    // &mut self — mutable borrow (modifying method)
    fn scale(&mut self, factor: f64) {
        self.width *= factor;
        self.height *= factor;
    }

    // no self — associated function (like a static method / constructor)
    fn new(width: f64, height: f64) -> Rectangle {
        Rectangle { width, height }   // field init shorthand when param name matches
    }

    // can have multiple impl blocks — all equivalent
}

fn main() {
    let mut r = Rectangle::new(10.0, 5.0);  // :: for associated functions
    println!("{}", r.area());                // . for methods
    r.scale(2.0);
    println!("{}", r.area());               // 200.0
}
```

### `self` variants

| Parameter | Meaning | Use case |
|---|---|---|
| `&self` | immutable borrow of instance | read-only methods |
| `&mut self` | mutable borrow of instance | methods that modify the struct |
| `self` | takes ownership of instance | consuming methods (rare) |
| *(no self)* | associated function | constructors, static utilities |

### Multiple `impl` blocks

A struct can have multiple `impl` blocks — all are equivalent, just split for organization:

```rust
impl Rectangle {
    fn area(&self) -> f64 { ... }
}

impl Rectangle {
    fn perimeter(&self) -> f64 { ... }
}
```

---

## 3. Enums — Algebraic Data Types

Rust enums are far more powerful than C/C++ enums. Each variant can carry its own data.

```rust
enum Shape {
    Circle(f64),                          // tuple variant — carries a radius
    Rectangle(f64, f64),                  // carries width and height
    Triangle { base: f64, height: f64},  // struct variant — named fields
    Point,                                // unit variant — no data (like C enum)
}
```

This is called an **algebraic data type** — a type that is *one of* several variants, each with its own payload.

### Plain Enums — Zero Cost (like C++)

Enums with no data compile down to plain integers, identical to C/C++:

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Color { White, Black }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Piece { Pawn, Knight, Bishop, Rook, Queen, King }

let c = Color::White;
let p = Piece::Knight;
println!("{} {}", c as u32, p as u32);  // cast to integer like C
```

### Enums with Methods

Just like structs, enums can have `impl` blocks:

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

let val = Piece::Queen.value();  // 900
```

`const fn` = Rust's `constexpr` — evaluated at compile time.

---

## 4. Pattern Matching with `match`

`match` is how you interact with enums — like `switch` but exhaustive and with destructuring.

```rust
fn area(shape: &Shape) -> f64 {
    match shape {
        Shape::Circle(r)                    => std::f64::consts::PI * r * r,
        Shape::Rectangle(w, h)              => w * h,
        Shape::Triangle { base, height }    => 0.5 * base * height,
        Shape::Point                        => 0.0,
    }
}
```

### Exhaustiveness

`match` must cover **every variant** — the compiler enforces this. Forget one and it won't compile:

```rust
match shape {
    Shape::Circle(r) => ...,
    // ❌ compile error — Rectangle, Triangle, Point not covered
}
```

Use `_` as a catch-all:

```rust
match shape {
    Shape::Circle(r) => ...,
    _ => 0.0,   // handle all other variants
}
```

### Matching with Guards

Add conditions to match arms:

```rust
match piece {
    Piece::Pawn if is_passed => 150,   // only matches passed pawns
    Piece::Pawn               => 100,
    _                         => piece.value(),
}
```

### Matching Multiple Patterns

```rust
match piece {
    Piece::Bishop | Piece::Knight => println!("minor piece"),
    Piece::Rook   | Piece::Queen  => println!("major piece"),
    _                              => {},
}
```

### `if let` — Match One Variant

When you only care about one variant, `if let` is cleaner than a full `match`:

```rust
if let Piece::Pawn = piece {
    println!("it's a pawn");
}

// with data
if let Shape::Circle(r) = shape {
    println!("radius: {}", r);
}
```

`if let` with `else`:
```rust
if let Shape::Circle(r) = shape {
    println!("circle, radius {}", r);
} else {
    println!("not a circle");
}
```

### `while let` — Loop Until Pattern Fails

```rust
while let Some(value) = stack.pop() {
    println!("{}", value);
}
```

---

## 5. `Option<T>` — Rust's Null Safety

Rust has no `null`. Instead, the standard library provides `Option<T>`:

```rust
enum Option<T> {
    Some(T),   // contains a value of type T
    None,      // no value
}
```

Any value that might not exist is wrapped in `Option`. The compiler forces you to handle `None` before you can use the inner value — null pointer crashes are impossible.

```rust
fn find_piece(square: u8) -> Option<Piece> {
    if square < 64 {
        Some(Piece::Pawn)
    } else {
        None
    }
}

match find_piece(10) {
    Some(piece) => println!("{:?}", piece),
    None        => println!("empty square"),
}
```

### Useful `Option` Methods

```rust
let opt: Option<i32> = Some(42);

opt.is_some()              // true
opt.is_none()              // false
opt.unwrap()               // 42 — panics if None
opt.unwrap_or(0)           // 42 — returns 0 if None
opt.unwrap_or_else(|| 0)   // 42 — calls closure if None
opt.map(|x| x * 2)        // Some(84) — transform inner value
opt.and_then(|x| Some(x * 2))  // Some(84) — flatmap
```

---

## 6. Derive Macros

`#[derive(...)]` auto-implements traits — saves writing boilerplate:

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Color { White, Black }
```

| Derive | What it gives you |
|---|---|
| `Debug` | `{:?}` and `{:#?}` printing |
| `Clone` | `.clone()` — explicit deep copy |
| `Copy` | implicit copy on assignment (for stack types) |
| `PartialEq` | `==` and `!=` operators |
| `Eq` | total equality (required for `HashMap` keys alongside `Hash`) |
| `Hash` | usable as `HashMap` / `HashSet` key |

> For plain enums and simple structs: always derive `Debug, Clone, Copy, PartialEq, Eq`. You'll almost never regret it.

> `Copy` requires `Clone`. `Eq` requires `PartialEq`. Always derive them together.

---

## 7. Quick Reference

```
struct Foo { }          →  named fields, like C struct
struct Foo(T, T)        →  tuple struct, access by index
impl Foo { }            →  attach methods to a struct or enum
&self                   →  read-only method
&mut self               →  mutating method
Foo::new()              →  associated function (no self), called with ::
enum Foo { A, B(T) }    →  variants can carry data
match                   →  exhaustive pattern matching, must cover all variants
if let Variant(x) = v   →  match single variant, bind inner value
Option<T>               →  Some(T) or None — Rust's null safety
#[derive(...)]          →  auto-implement common traits
```

---

## Key Takeaways

- Structs group data, `impl` blocks attach behavior — together they replace C++ classes.
- Methods take `&self` (read), `&mut self` (write), or no self (associated/static).
- Rust enums are algebraic data types — each variant can carry different data.
- Plain enums (no data) compile to integers, identical to C/C++ enums — zero overhead.
- `match` is exhaustive — the compiler forces you to handle every variant, no silent bugs.
- `Option<T>` replaces null — you cannot use a value without handling the `None` case.
- `#[derive(...)]` auto-generates common trait implementations — use it liberally on simple types.