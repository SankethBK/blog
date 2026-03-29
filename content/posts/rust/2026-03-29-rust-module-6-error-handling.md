--- 
title:  "Rust Notes — Module 6"
date:   2026-03-29
draft: true
categories: ["rust"]
tags: ["error handling", "result",]

---

# Rust Notes — Module 6: Error Handling

---

## 1. The Philosophy

| Language | Error Mechanism | Problem |
|---|---|---|
| C | Return codes (`-1`, `NULL`, `errno`) | Easy to ignore, no enforcement |
| Go | `(value, error)` tuples | Better, but still ignorable |
| **Rust** | `Result<T, E>` in the type system | **Impossible to ignore — compiler enforced** |

If a function can fail, its return type says so. You cannot use the success value without handling the error case first. No hidden exceptions, no surprise crashes from ignored error codes.

---

## 2. `Result<T, E>`

```rust
enum Result<T, E> {
    Ok(T),    // success — contains the value of type T
    Err(E),   // failure — contains the error of type E
}
```

### Basic Usage

```rust
// cannot call methods on Result directly
let board = Board::from_fen("...");  // type: Result<Board, FenError>
// board.pretty_print();             // ❌ compile error

// must handle both cases
match Board::from_fen("...") {
    Ok(board) => board.pretty_print(),
    Err(e)    => println!("Invalid FEN: {:?}", e),
}
```

### Functions that Return `Result`

```rust
fn parse_number(s: &str) -> Result<i32, String> {
    s.parse::<i32>().map_err(|e| e.to_string())
}

// caller must handle the Result
match parse_number("42") {
    Ok(n)  => println!("Got: {}", n),
    Err(e) => println!("Error: {}", e),
}
```

---

## 3. `Option<T>`

```rust
enum Option<T> {
    Some(T),   // value exists
    None,      // no value — no reason given
}
```

Use `Option` when absence is normal and expected (not an error). Use `Result` when failure needs an explanation.

```rust
// piece_on returns None for empty squares — not an error, just absence
fn piece_on(&self, sq: Square) -> Option<(Color, Piece)> { ... }

// from_fen returns Err with a reason — failure needs explanation
fn from_fen(fen: &str) -> Result<Board, FenError> { ... }
```

### `Option` vs `Result`

| | `Option<T>` | `Result<T, E>` |
|---|---|---|
| Use when | value may or may not exist | operation may succeed or fail |
| Failure carries info | ❌ No | ✅ Yes |
| Engine examples | `piece_on`, `en_passant` | `from_fen`, file I/O |

---

## 4. The `?` Operator

`?` is shorthand for: unwrap `Ok`/`Some` and continue, or **return the error/None immediately** to the caller.

```rust
// without ?
fn parse_castling(field: &str) -> Result<u8, FenError> {
    match inner_parse(field) {
        Ok(val) => val,
        Err(e)  => return Err(e),
    }
}

// with ? — identical behavior
fn parse_castling(field: &str) -> Result<u8, FenError> {
    let val = inner_parse(field)?;  // returns Err early if inner_parse fails
    Ok(val)
}
```

### Chaining `?`

```rust
pub fn from_fen(fen: &str) -> Result<Board, FenError> {
    // each ? either unwraps and continues, or returns Err early
    board.castling_rights = parse_castling_rights(castling)?;
    board.en_passant      = parse_en_passant(en_passant)?;
    board.halfmove_clock  = halfmove.parse::<u32>().map_err(|_| FenError::InvalidHalfmoveClock)?;
    Ok(board)
}
```

### `?` on `Option`

`?` works on `Option` too — returns `None` early if the value is absent:

```rust
fn first_piece_value(board: &Board, sq: Square) -> Option<i32> {
    let (_, piece) = board.piece_on(sq)?;  // returns None if square empty
    Some(piece.value())
}
```

> ⚠️ `?` only works inside functions that return `Result` or `Option`. Using it in `main` requires `main` to return `Result`.

```rust
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let board = Board::from_fen("...")?;
    Ok(())
}
```

---

## 5. `unwrap` and `expect`

For cases where you're certain the operation won't fail:

```rust
// unwrap — panics with generic message if Err/None
let board = Board::from_fen("...").unwrap();

// expect — panics with YOUR message if Err/None (always prefer this)
let board = Board::from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    .expect("starting position FEN must be valid");
```

> Always prefer `expect` over `unwrap` — the message explains *why* you expected success, which is invaluable when debugging a panic.

> ⚠️ Never use `unwrap`/`expect` in production paths. Use them for: known-valid constants (starting position FEN), tests, and prototyping. Replace with proper error handling in real code paths.

---

## 6. Defining Custom Error Types

```rust
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FenError {
    InvalidFieldCount,
    InvalidPiecePlacement,
    InvalidSideToMove,
    InvalidCastlingRights,
    InvalidEnPassant,
    InvalidHalfmoveClock,
    InvalidFullmoveNumber,
}
```

`#[derive(Debug)]` is required — lets you print with `{:?}`. For user-facing errors, implement `Display`:

```rust
use std::fmt;

impl fmt::Display for FenError {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            FenError::InvalidFieldCount     => write!(f, "FEN must have exactly 6 fields"),
            FenError::InvalidPiecePlacement => write!(f, "invalid piece placement string"),
            FenError::InvalidSideToMove     => write!(f, "side to move must be 'w' or 'b'"),
            FenError::InvalidCastlingRights => write!(f, "invalid castling rights"),
            FenError::InvalidEnPassant      => write!(f, "invalid en passant square"),
            FenError::InvalidHalfmoveClock  => write!(f, "invalid halfmove clock"),
            FenError::InvalidFullmoveNumber => write!(f, "invalid fullmove number"),
        }
    }
}

// now {} works in addition to {:?}
println!("{}", FenError::InvalidFieldCount);  // "FEN must have exactly 6 fields"
println!("{:?}", FenError::InvalidFieldCount); // "InvalidFieldCount"
```

---

## 7. Result and Option Methods

### Transforming Values

```rust
let r: Result<i32, &str> = Ok(42);
let o: Option<i32>       = Some(42);

// map — transform the inner value, leave Err/None untouched
r.map(|x| x * 2)            // Ok(84)
o.map(|x| x * 2)            // Some(84)

// map_err — transform only the error type
r.map_err(|e| format!("error: {}", e))  // Ok(42) — maps only if Err

// and_then — chain operations that also return Result/Option (flatmap)
r.and_then(|x| if x > 0 { Ok(x * 2) } else { Err("negative") })
o.and_then(|x| if x > 0 { Some(x * 2) } else { None })
```

### Providing Defaults

```rust
r.unwrap_or(0)               // 42 — or 0 if Err
o.unwrap_or(0)               // 42 — or 0 if None

// unwrap_or_else — default computed lazily from a closure
r.unwrap_or_else(|_| expensive_default())
o.unwrap_or_else(|| expensive_default())
```

### Checking Without Consuming

```rust
r.is_ok()                    // true
r.is_err()                   // false
o.is_some()                  // true
o.is_none()                  // false
```

### Converting Between Result and Option

```rust
// Result → Option (discards the error)
r.ok()                       // Some(42)

// Option → Result (gives it an error value)
o.ok_or(FenError::InvalidFieldCount)
// Ok(42) if Some, Err(InvalidFieldCount) if None

// ok_or_else — error computed lazily from a closure
// use this when constructing the error is expensive or needs context
o.ok_or_else(|| {
    eprintln!("piece lookup failed");
    FenError::InvalidPiecePlacement
})
// Same as ok_or but the Err value is only constructed if actually None
// Prefer ok_or_else over ok_or when the error value is non-trivial
```

### Filtering Options

```rust
// filter — turns Some into None if predicate fails
o.filter(|x| *x > 10)       // None — 42 > 10 so stays Some(42)... wait
Some(5).filter(|x| *x > 10) // None — 5 fails the predicate
Some(42).filter(|x| *x > 10) // Some(42) — 42 passes

// flatten — Option<Option<T>> → Option<T>
Some(Some(42)).flatten()     // Some(42)
Some(None::<i32>).flatten()  // None
```

---

## 8. Error Propagation Patterns

### Early Return with `?`

```rust
// clean flat code — no nesting
fn process_fen(input: &str) -> Result<String, FenError> {
    let board = Board::from_fen(input)?;
    let mv    = parse_move(get_best_move(&board)?)?;
    Ok(format!("{:?}", mv))
}
```

### Converting Error Types with `map_err`

When your function returns one error type but calls functions returning another:

```rust
fn load_position(path: &str) -> Result<Board, FenError> {
    let contents = std::fs::read_to_string(path)
        .map_err(|_| FenError::InvalidFieldCount)?;  // io::Error → FenError
    Board::from_fen(&contents)
}
```

### The `if let` Pattern for Optional Handling

```rust
// when you only care about the Some/Ok case
if let Some((color, piece)) = board.piece_on(sq) {
    println!("{:?} {:?}", color, piece);
}

if let Ok(board) = Board::from_fen(fen) {
    board.pretty_print();
}
```

---

## 9. Quick Reference

```
Result<T, E>             →  Ok(T) or Err(E) — fallible operations
Option<T>                →  Some(T) or None — optional values
?                        →  unwrap or return Err/None early to caller
expect("msg")            →  unwrap or panic with message
unwrap()                 →  unwrap or panic (avoid — use expect instead)
.map(|x| ...)            →  transform inner value
.map_err(|e| ...)        →  transform error type
.and_then(|x| ...)       →  chain fallible operations (flatmap)
.unwrap_or(default)      →  value or default if Err/None
.unwrap_or_else(|| ...)  →  value or lazily computed default
.ok()                    →  Result → Option (discards error)
.ok_or(err)              →  Option → Result (adds error value)
.ok_or_else(|| err)      →  Option → Result (error computed lazily)
.is_ok() / .is_some()    →  check without consuming
.filter(|x| ...)         →  Option: None if predicate fails
```

---

## Key Takeaways

- `Result<T, E>` is for fallible operations — always carries a reason for failure.
- `Option<T>` is for optional values — absence is normal, not an error.
- The compiler forces you to handle both cases — no silent error ignoring.
- `?` is the primary tool for propagating errors — keeps code flat and readable.
- Always use `expect` over `unwrap` — the message is invaluable when debugging panics.
- `map`, `and_then`, `map_err` let you transform values without unwrapping.
- `ok_or_else` is preferred over `ok_or` when the error value is non-trivial or expensive to construct.
- Custom error enums with `Debug` and `Display` are the idiomatic way to define domain errors.
- Error types in function signatures are documentation — you can read what can go wrong without reading the implementation.