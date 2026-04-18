--- 
title:  "Rust Notes — Module 7"
date:   2026-03-29
categories: ["rust"]
tags: ["crates", "packages", "modules"]

---

# Rust Notes — Module 7: Packages, Crates & Modules

---

## 1. How Rust Compilation Works

In C, you hand the compiler a list of files. Each file compiles independently, and a linker stitches the object files together. The problem — the compiler has no idea which files depend on which, so you need a Makefile to track what needs recompiling when something changes.

Rust takes a different approach. You hand the compiler **one root file** (`main.rs` or `lib.rs`). The compiler follows `mod` declarations to find every other file that's part of the crate. Because Rust knows the full dependency graph from the start, it handles incremental recompilation internally — no Makefile needed.

```
C compiler:   rustc a.c b.c c.c    ← you list every file
Rust compiler: rustc main.rs       ← follows mod declarations to find the rest
```

---

## 2. The Three Levels

```
Package   →  what Cargo manages — has a Cargo.toml
Crate     →  a single compilation unit — binary or library
Module    →  code organization within a crate
```

### Mental Model

```
Package (Cargo.toml)
├── Library crate (src/lib.rs)      ← at most one
├── Binary crate (src/main.rs)      ← default binary
└── Binary crates (src/bin/*.rs)    ← additional binaries
```

---

## 3. Crates

A crate is the smallest unit the Rust compiler works with. Two kinds:

### Binary Crate
- Has a `main` function
- Compiles to an executable
- Entry point: `src/main.rs` (default) or any file in `src/bin/`

### Library Crate
- No `main` function
- Compiles to a library — not directly executable
- Entry point: `src/lib.rs`
- When Rustaceans say "crate" they usually mean library crate

```bash
cargo new chess-engine        # creates package with binary crate (src/main.rs)
cargo new chess-core --lib    # creates package with library crate (src/lib.rs)
```

---

## 4. Packages

A package is a bundle of one or more crates with a `Cargo.toml` describing how to build them.

### Rules
- A package must have **at least one** crate
- A package can have **at most one** library crate
- A package can have **multiple** binary crates

### Why at most one library?

When you add a dependency in `Cargo.toml`:
```toml
[dependencies]
chess-engine = "1.0"
```

Cargo needs to know unambiguously which crate you mean. Since there's at most one library per package, no ambiguity — it's always the library crate. If multiple libraries were allowed, you'd need a way to specify *which* library you depend on, creating two separate dependency systems. The limitation keeps things simple.

On the other hand, binaries are never depended upon by other packages — Cargo only cares about library targets when resolving dependencies. So there's no reason to limit binaries.

### Real world example — Cargo itself

```
cargo (package)
├── cargo (library crate)   ← logic that cargo-edit, cargo-watch etc. depend on
└── cargo (binary crate)    ← the CLI tool you use every day
```

---

## 5. Multiple Binary Crates

Additional binaries go in `src/bin/` — each file becomes its own binary crate:

```
src/
  main.rs          ←  chess-engine  (default binary)
  lib.rs           ←  chess-engine  (library — shared logic)
  bin/
    perft.rs       ←  perft         (perft testing tool)
    bench.rs       ←  bench         (benchmarking tool)
    tune.rs        ←  tune          (parameter tuning)
```

Each file in `src/bin/` must have its own `main` function. They share code via the library crate:

```rust
// src/bin/perft.rs
use chess_engine::Board;        // uses the library crate
use chess_engine::AttackTable;

fn main() {
    let attacks = AttackTable::init();
    let board = Board::starting_position();
    // run perft...
}
```

```bash
cargo run                     # runs src/main.rs
cargo run --bin perft         # runs src/bin/perft.rs
cargo run --bin bench         # runs src/bin/bench.rs
cargo build                   # builds all crates
```

---

## 6. Modules

Modules organize code into namespaces within a crate. Two ways to define them:

### Inline Module
```rust
mod movegen {
    pub fn generate_moves() { ... }

    fn internal_helper() { ... }  // private — not visible outside mod
}

movegen::generate_moves();  // :: to access
```

### File Module
```rust
// main.rs
mod types;      // Rust looks for src/types.rs — treats its contents as the module body
mod board;      // Rust looks for src/board.rs
mod bitboard;
```

These are **identical** to the compiler. The file version is just the inline version with the body moved to a separate file. Without `mod types;`, `types.rs` is completely ignored even if it exists.

### Nested Modules — Subdirectories

For deeply nested modules:
```
src/
  main.rs
  movegen/
    mod.rs        ←  root of the movegen module
    pawns.rs      ←  movegen::pawns submodule
    knights.rs    ←  movegen::knights submodule
```

```rust
// main.rs
mod movegen;    // Rust finds src/movegen/mod.rs

// src/movegen/mod.rs
pub mod pawns;
pub mod knights;
```

---

## 7. Visibility

Everything in Rust is **private by default**. Visibility is opt-in:

```rust
pub fn f()           // visible everywhere
pub(crate) fn f()    // visible within this crate only
pub(super) fn f()    // visible to parent module only
fn f()               // private — only within this module
```

### Struct Field Visibility

`pub` on a struct doesn't make its fields public:

```rust
pub struct Board {
    pub side_to_move: Color,    // pub field — accessible outside
    pieces: [[u64; 6]; 2],      // private field — only Board's methods can touch it
}
```

### Enum Visibility

`pub` on an enum makes **all variants** public — you can't have private variants:

```rust
pub enum Color {
    White,   // automatically pub
    Black,   // automatically pub
}
```

---

## 8. `use` — Bringing Names Into Scope

```rust
use crate::types::Color;                    // absolute path from crate root
use crate::types::{Color, Piece, Square};   // multiple at once
use crate::types::*;                        // everything (use sparingly)

use super::types::Color;                    // relative — super = parent module
use self::helpers::parse;                   // relative — self = current module
```

### Aliasing with `as`

```rust
use crate::bitboard::pretty_print as print_bb;
use std::collections::HashMap as Map;
```

### Re-exporting with `pub use`

Expose internal types at the crate's top level — lets you restructure internals without breaking the public API:

```rust
// src/lib.rs
pub use types::Color;
pub use types::Piece;
pub use board::Board;

// external users can now write:
use chess_engine::Board;        // instead of chess_engine::board::Board
use chess_engine::Color;        // instead of chess_engine::types::Color
```

---

## 9. External Dependencies

Add to `Cargo.toml`:

```toml
[dependencies]
rand = "0.8"          # >=0.8.0, <0.9.0  (most common)
rand = "=0.8.5"       # exactly 0.8.5
rand = "*"            # any version (avoid)
```

```bash
cargo build           # downloads, compiles, links automatically
cargo update          # update dependencies within version constraints
```

```rust
use rand::Rng;
let zobrist_key: u64 = rand::thread_rng().gen();
```

No CMake, no vcpkg, no manual linking. For your engine — `rand` for Zobrist key generation when you get there.

### Dev Dependencies

Dependencies only needed for tests/benchmarks:

```toml
[dev-dependencies]
criterion = "0.5"     # benchmarking framework — only compiled during tests/benches
```

---

## 10. Workspaces — Multiple Packages Together

When a project grows into multiple packages, a workspace keeps them together with a shared build cache and `Cargo.lock`:

```toml
# Cargo.toml at repo root
[workspace]
members = [
    "chess-engine",
    "chess-uci",
    "chess-tuner",
]
```

```bash
cargo build           # builds all members
cargo test            # tests all members
cargo run -p chess-engine  # run specific member
```

Not needed now — but the natural next step when you want to split the UCI protocol layer from the engine core.

---

## 11. `const` and `static`

```rust
// const — inlined at every use site, no memory address
const MAX_DEPTH: u32 = 64;
const INFINITY: i32  = 30_000;
const NEG_INFINITY: i32 = -30_000;

// static — single location in memory, lives for entire program lifetime
static STARTING_FEN: &str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
```

For your engine:
- `const` — piece values, search constants, file/rank masks
- `static` — attack tables (initialized once, accessed everywhere)

---

## 12. `#[cfg]` — Conditional Compilation

Rust's equivalent of `#ifdef`:

```rust
#[cfg(test)]
mod tests { ... }               // only compiled during cargo test

#[cfg(debug_assertions)]
println!("debug info");         // only in debug builds, not release

#[cfg(target_arch = "x86_64")]
fn use_popcnt(bb: u64) -> u32 {
    bb.count_ones()             // compiles to POPCNT instruction on x86_64
}
```

Useful for your engine — on x86_64 `trailing_zeros()` and `count_ones()` compile to single CPU instructions (`TZCNT`, `POPCNT`). `#[cfg]` lets you write architecture-specific fast paths with fallbacks.

---

## 13. Your Engine's Module Layout

```
src/
  main.rs       ←  mod declarations, entry point, AttackTable::init()
  lib.rs        ←  pub use re-exports (if you split into lib + binary)
  types.rs      ←  Color, Piece, Square, Move, CastlingRights
  bitboard.rs   ←  Bitboard alias, lsb, pop_lsb, masks, shift helpers
  board.rs      ←  Board struct, FEN parsing, make/unmake, pretty_print
  attacks.rs    ←  AttackTable, precomputed lookup tables
  movegen.rs    ←  generate_moves, MoveList
  evaluate.rs   ←  evaluate()
  search.rs     ←  negamax, alpha_beta, SearchInfo
  bin/
    perft.rs    ←  standalone perft tool
    bench.rs    ←  benchmarking tool (later)
```

```rust
// main.rs
mod types;
mod bitboard;
mod board;
mod attacks;
mod movegen;
mod evaluate;
mod search;

use board::Board;
use attacks::AttackTable;

fn main() {
    let attacks = AttackTable::init();
    let board   = Board::starting_position();
    board.pretty_print();
}
```

---

## 14. Quick Reference

```
cargo new foo          →  package with binary crate (src/main.rs)
cargo new foo --lib    →  package with library crate (src/lib.rs)
cargo run --bin name   →  run a specific binary crate
mod foo;               →  declare module, Rust finds src/foo.rs
mod foo { }            →  inline module definition
pub                    →  visible everywhere
pub(crate)             →  visible within crate only
pub(super)             →  visible to parent module only
use crate::foo::Bar    →  absolute import from crate root
use super::foo::Bar    →  relative import from parent module
pub use foo::Bar       →  re-export — expose at current module level
[dependencies]         →  external crates in Cargo.toml
[dev-dependencies]     →  test/bench only dependencies
#[cfg(test)]           →  conditional compilation
const                  →  compile-time constant, inlined at use sites
static                 →  single memory location, program lifetime
```

---

## Key Takeaways

- Rust finds all files in a crate by following `mod` declarations from one root file — no Makefile needed.
- A package can have at most one library crate — keeps the dependency system unambiguous.
- Multiple binary crates in `src/bin/` share the library crate — perfect for perft tool, bench tool, main engine.
- Everything is private by default — `pub` is an explicit opt-in, not the default.
- `use crate::` is an absolute path, `use super::` is relative to the parent module.
- `pub use` lets you re-export types at a higher level — decouple public API from internal structure.
- `const` is inlined at every use site. `static` has a single memory address for the program's lifetime.
- `#[cfg(target_arch = "x86_64")]` lets you use CPU-specific instructions with fallbacks — relevant for `POPCNT` and `TZCNT` in your engine.