--- 
title:  "Rust Notes — Module 5"
date:   2026-03-22
categories: ["rust"]
tags: ["generics", "closures", "iterators"]

---

# Rust Notes — Module 5: Generics, Closures & Iterators

---

## 1. Generics

Generics let you write code that works for any type, with the compiler generating specialized versions at compile time. Zero runtime overhead — same as C++ templates.

### Generic Functions

```rust
// T is a type parameter — placeholder for any concrete type
fn largest<T: PartialOrd>(list: &[T]) -> &T {
    let mut largest = &list[0];
    for item in list {
        if item > largest {
            largest = item;
        }
    }
    largest
}

// works for any type that implements PartialOrd
let nums = vec![1, 5, 3, 2];
let chars = vec!['a', 'z', 'm'];
println!("{}", largest(&nums));   // 5
println!("{}", largest(&chars));  // z
```

### Generic Structs

```rust
struct Stack<T> {
    elements: Vec<T>,
}

// impl block also needs <T>
impl<T> Stack<T> {
    fn new() -> Self {
        Stack { elements: Vec::new() }
    }

    fn push(&mut self, item: T) {
        self.elements.push(item);
    }

    fn pop(&mut self) -> Option<T> {
        self.elements.pop()
    }

    fn peek(&self) -> Option<&T> {
        self.elements.last()
    }

    fn is_empty(&self) -> bool {
        self.elements.is_empty()
    }
}

// type parameter inferred from usage
let mut int_stack = Stack::new();
int_stack.push(1);
int_stack.push(2);

// or explicit
let mut move_stack: Stack<Move> = Stack::new();
```

### Generic Enums

You've already used these — `Option<T>` and `Result<T, E>` are generic enums:

```rust
// from the standard library — this is how they're defined
enum Option<T> {
    Some(T),
    None,
}

enum Result<T, E> {
    Ok(T),
    Err(E),
}
```

### Generic Structs with Trait Bounds

Add bounds when the implementation needs specific behavior from T:

```rust
use std::fmt::Display;

struct Wrapper<T: Display> {
    value: T,
}

impl<T: Display> Wrapper<T> {
    fn print(&self) {
        println!("{}", self.value);
    }
}
```

### Multiple Type Parameters

```rust
struct Pair<T, U> {
    first: T,
    second: U,
}

let p = Pair { first: 42, second: "hello" };
```

### Monomorphization — How Generics Work

The compiler generates a **separate concrete version** for each type you use:

```rust
// you write
fn largest<T: PartialOrd>(list: &[T]) -> &T { ... }

// compiler generates (conceptually)
fn largest_i32(list: &[i32]) -> &i32 { ... }
fn largest_f64(list: &[f64]) -> &f64 { ... }
```

This is why generic Rust code has zero runtime overhead — by the time the binary is produced, all generics are replaced with concrete types.

---

## 2. Closures

Closures are anonymous functions that can capture variables from their surrounding scope.

### Basic Syntax

```rust
// full syntax
let add = |a: i32, b: i32| -> i32 { a + b };

// types inferred — most common
let add = |a, b| a + b;

// single expression — no braces needed
let double = |x| x * 2;

// multi-line — braces required
let complex = |x| {
    let y = x * 2;
    y + 1
};

println!("{}", add(3, 4));     // 7
println!("{}", double(5));     // 10
println!("{}", complex(3));    // 7
```

### Capturing the Environment

The key difference from regular functions — closures capture variables from the enclosing scope:

```rust
let bonus = 50;
let threshold = 100;

let add_bonus = |x| x + bonus;              // captures bonus
let is_above  = |x| x > threshold;          // captures threshold
let combined  = |x| x + bonus > threshold;  // captures both

println!("{}", add_bonus(60));   // 110
println!("{}", is_above(110));   // true
```

### Three Capture Modes

Closures automatically choose the least restrictive capture mode:

```rust
let s = String::from("hello");
let n = 5;

// 1. Immutable borrow — just reads the value
let borrow = || println!("{} {}", s, n);
borrow();
println!("{}", s);  // ✅ s still valid

// 2. Mutable borrow — modifies the value
let mut s2 = String::from("hello");
let mut mut_borrow = || s2.push_str(" world");
mut_borrow();
println!("{}", s2);  // "hello world"

// 3. Move — takes ownership
let owned = move || println!("{}", s);  // s moved into closure
owned();
// println!("{}", s);  // ❌ s was moved
```

> Use `move` closures when passing to threads — the thread needs to own its data since it may outlive the current scope.

### Closures as Function Parameters

Closures implement one of three traits depending on what they do:

| Trait | Meaning | Can be called |
|---|---|---|
| `FnOnce` | consumes captured values | once only |
| `FnMut` | mutates captured values | multiple times, needs `mut` |
| `Fn` | only reads captured values | multiple times |

```rust
// Fn — read only, most restrictive to the caller
fn apply<F: Fn(i32) -> i32>(f: F, x: i32) -> i32 {
    f(x)
}

// FnMut — closure may mutate captured state
fn apply_mut<F: FnMut(i32) -> i32>(mut f: F, x: i32) -> i32 {
    f(x)
}

// FnOnce — closure may consume captured values, least restrictive
fn apply_once<F: FnOnce(i32) -> i32>(f: F, x: i32) -> i32 {
    f(x)
}

let double = |x| x * 2;
println!("{}", apply(double, 5));       // 10
println!("{}", apply_mut(double, 5));   // 10
println!("{}", apply_once(double, 5));  // 10
```

> `FnOnce` is the most permissive bound (accepts all closures). `Fn` is the most restrictive (only accepts non-mutating closures). When in doubt, start with `Fn` and loosen if the compiler complains.

### Returning Closures

Closures have no concrete type — you must use `impl Fn` or `Box<dyn Fn>`:

```rust
// impl Fn — always returns same closure type (preferred)
fn make_adder(x: i32) -> impl Fn(i32) -> i32 {
    move |y| x + y
}

// Box<dyn Fn> — when you need to return different closure types
fn make_op(add: bool) -> Box<dyn Fn(i32, i32) -> i32> {
    if add {
        Box::new(|a, b| a + b)
    } else {
        Box::new(|a, b| a * b)
    }
}

let add5 = make_adder(5);
println!("{}", add5(3));   // 8
println!("{}", add5(10));  // 15
```

---

## 3. Iterators

An iterator is any type implementing the `Iterator` trait:

```rust
trait Iterator {
    type Item;                                    // the type of values yielded
    fn next(&mut self) -> Option<Self::Item>;    // the only required method
}
```

Returns `Some(value)` on each call, `None` when exhausted. Everything else is built on top of these two.

### Creating Iterators

```rust
let v = vec![1, 2, 3, 4, 5];

v.iter()        // yields &T      — immutable borrows, v still usable after
v.iter_mut()    // yields &mut T  — mutable borrows
v.into_iter()   // yields T       — consumes v, takes ownership of elements

// ranges are iterators
(0..5)          // 0, 1, 2, 3, 4
(0..=5)         // 0, 1, 2, 3, 4, 5
```

### Iterators are Lazy

Nothing executes until you consume the iterator:

```rust
let v = vec![1, 2, 3];

// this does NOTHING yet — just builds a pipeline description
let pipeline = v.iter().map(|x| x * 2).filter(|x| x > &3);

// THIS executes the pipeline
let result: Vec<i32> = pipeline.collect();
// [4, 6]
```

### Iterator Adapters (Lazy — return a new iterator)

```rust
let v = vec![1, 2, 3, 4, 5];

// map — transform each element
v.iter().map(|x| x * 2)
// yields 2, 4, 6, 8, 10

// filter — keep elements matching predicate
v.iter().filter(|x| *x % 2 == 0)
// yields &2, &4

// filter_map — map and filter in one step, keeps Some values
v.iter().filter_map(|x| if x % 2 == 0 { Some(x * 10) } else { None })
// yields 20, 40

// take — first n elements
v.iter().take(3)
// yields &1, &2, &3

// skip — skip first n elements
v.iter().skip(2)
// yields &3, &4, &5

// chain — concatenate two iterators
let a = vec![1, 2];
let b = vec![3, 4];
a.iter().chain(b.iter())
// yields &1, &2, &3, &4

// enumerate — yields (index, value) pairs
v.iter().enumerate()
// yields (0, &1), (1, &2), (2, &3) ...

// zip — pair up two iterators
let names = vec!["pawn", "knight"];
let values = vec![100, 320];
names.iter().zip(values.iter())
// yields (&"pawn", &100), (&"knight", &320)

// flat_map — map then flatten one level
let boards = vec![vec![1,2], vec![3,4]];
boards.iter().flat_map(|b| b.iter())
// yields &1, &2, &3, &4

// peekable — look at next element without consuming
let mut iter = v.iter().peekable();
println!("{:?}", iter.peek());  // Some(&1) — not consumed
println!("{:?}", iter.next());  // Some(&1) — now consumed
```

### Consuming Adapters (Execute the pipeline)

```rust
let v = vec![1, 2, 3, 4, 5];

// collect — gather into a collection
let doubled: Vec<i32> = v.iter().map(|x| x * 2).collect();

// sum / product
let sum: i32 = v.iter().sum();        // 15
let product: i32 = v.iter().product(); // 120

// count
let count = v.iter().filter(|x| **x > 2).count();  // 3

// fold — reduce to a single value with accumulator
let sum = v.iter().fold(0, |acc, x| acc + x);  // 15
let max = v.iter().fold(i32::MIN, |acc, &x| acc.max(x));  // 5

// any / all — short-circuit boolean checks
let has_even = v.iter().any(|x| x % 2 == 0);   // true
let all_pos  = v.iter().all(|x| *x > 0);         // true

// find — first element matching predicate
let first_even = v.iter().find(|x| *x % 2 == 0);  // Some(&2)

// position — index of first match
let pos = v.iter().position(|x| *x == 3);  // Some(2)

// min / max
let min = v.iter().min();  // Some(&1)
let max = v.iter().max();  // Some(&5)

// for_each — like a for loop, consumes iterator
v.iter().for_each(|x| println!("{}", x));
```

### Custom Iterator — BitboardIter

Implement `Iterator` once, get the entire adapter chain for free:

```rust
struct BitboardIter(u64);

impl Iterator for BitboardIter {
    type Item = u32;  // yields square indices (0-63)

    fn next(&mut self) -> Option<u32> {
        if self.0 == 0 {
            None
        } else {
            let sq = self.0.trailing_zeros();
            self.0 &= self.0 - 1;  // pop lsb
            Some(sq)
        }
    }
}

// basic iteration
for sq in BitboardIter(pawn_bb) {
    // generate pawn moves from sq
}

// count pieces on the board
let pawn_count = BitboardIter(pawn_bb).count();

// collect all squares
let squares: Vec<u32> = BitboardIter(pawn_bb).collect();

// filter squares on rank 7 (promotion rank)
let promoting_pawns: Vec<u32> = BitboardIter(pawn_bb)
    .filter(|&sq| sq / 8 == 6)
    .collect();

// get the least significant square without consuming
let lsb_sq = BitboardIter(pawn_bb).next();  // Option<u32>
```

### `for` Loops and Iterators

`for` loops are syntactic sugar over iterators — they call `into_iter()` automatically:

```rust
let v = vec![1, 2, 3];

// these are equivalent
for x in &v { println!("{}", x); }
for x in v.iter() { println!("{}", x); }

// mutable iteration
for x in &mut v { *x *= 2; }
for x in v.iter_mut() { *x *= 2; }

// consuming iteration
for x in v { println!("{}", x); }  // v moved
for x in v.into_iter() { println!("{}", x); }
```

---

## 4. Combining Generics, Closures & Iterators

These three features compose naturally — most real Rust code uses all three together:

```rust
// generic function taking a closure, used with iterators
fn apply_to_bb<F>(bb: u64, mut f: F)
where
    F: FnMut(u32),
{
    BitboardIter(bb).for_each(|sq| f(sq));
}

// collect squares matching a condition into a generic container
fn squares_where<C, F>(bb: u64, predicate: F) -> C
where
    C: FromIterator<u32>,
    F: Fn(u32) -> bool,
{
    BitboardIter(bb).filter(predicate).collect()
}

let squares: Vec<u32> = squares_where(pawn_bb, |sq| sq > 16);
```

---

## 5. Quick Reference

```
fn f<T: Bound>(x: T)         →  generic function
struct Foo<T> { }            →  generic struct
impl<T> Foo<T> { }           →  impl block for generic struct
|x| x * 2                   →  closure, types inferred
|x: i32| -> i32 { x * 2 }   →  closure, explicit types
move || ...                  →  closure that owns captured variables
Fn / FnMut / FnOnce          →  closure traits (restrictive → permissive)
.iter()                      →  borrows, yields &T
.iter_mut()                  →  mutably borrows, yields &mut T
.into_iter()                 →  consumes, yields T
.map(|x| ...)                →  transform (lazy)
.filter(|x| ...)             →  keep matching (lazy)
.enumerate()                 →  add index (lazy)
.chain(other)                →  concatenate (lazy)
.take(n) / .skip(n)          →  slice iterator (lazy)
.collect()                   →  execute pipeline into collection
.fold(init, |acc, x| ...)    →  reduce to single value
.any() / .all()              →  short-circuit boolean checks
.count() / .sum() / .min()   →  consuming aggregates
```

---

## Key Takeaways

- Generics are zero-cost — the compiler generates specialized code per type (monomorphization), same as C++ templates.
- Closures capture their environment — immutably, mutably, or by move.
- `Fn` / `FnMut` / `FnOnce` describe how a closure uses captured variables — `FnOnce` is most permissive, `Fn` most restrictive.
- Iterators are lazy — adapters build a pipeline description, consuming adapters execute it.
- Implementing `Iterator` (just `next()`) gives you the entire adapter library for free.
- `BitboardIter` is a natural fit for chess engines — clean square iteration with no boilerplate.
- `for x in collection` is sugar for `into_iter()` — understand which ownership mode you need.
- Generics + closures + iterators compose naturally — most idiomatic Rust uses all three together.