---
title:  "Bitboard representation of Chess Board"
date:   2026-01-04
draft: false
categories: ["chess engines"]
tags: ["bitboard"]
author: Sanketh
---

## Bitboard-Based Game Representation in Stockfish

Stockfish represents the chessboard using **bitboards**: 64-bit unsigned integers where each bit corresponds to a square on the board.

```cpp
typedef uint64_t Bitboard;
```

* Bit 0 (LSB) → **A1**
* Bit 63 (MSB) → **H8**

This representation allows the engine to manipulate entire sets of squares using fast bitwise operations, which is critical for performance.

---

## Piece Encoding

```cpp
enum Piece {
  NO_PIECE,
  W_PAWN = 1, W_KNIGHT, W_BISHOP, W_ROOK, W_QUEEN, W_KING,
  B_PAWN = 9, B_KNIGHT, B_BISHOP, B_ROOK, B_QUEEN, B_KING,
  PIECE_NB = 16
};
```

### Numeric Structure

| Piece  | Value | Binary |
| ------ | ----- | ------ |
| W_PAWN | 1     | 0001   |
| W_KING | 6     | 0110   |
| B_PAWN | 9     | 1001   |
| B_KING | 14    | 1110   |

Key observations:

* White pieces occupy values **1–6**
* Black pieces occupy values **9–14**
* The **4th bit** distinguishes color

This enables a compact and efficient encoding:

```cpp
Piece = (Color << 3) | PieceType
```

### Extracting Type and Color

```cpp
inline PieceType type_of(Piece pc) { return PieceType(pc & 7); }
inline Color color_of(Piece pc)    { return Color(pc >> 3); }
```

* `pc & 7` strips color → piece type
* `pc >> 3` extracts color

### Flipping Color

```cpp
~pc == pc ^ 8
```

Toggles the color bit while keeping the piece type unchanged.

### `PIECE_NB`

```cpp
PIECE_NB = 16
```

Used for array sizing and indexing. It is **not** the number of actual chess pieces, but the size of the encoding space.

---

## PieceType: Color-Independent Identity

```cpp
enum PieceType {
  NO_PIECE_TYPE, PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING,
  ALL_PIECES = 0,
  PIECE_TYPE_NB = 8
};
```

### Purpose

* Represents **kind of piece**, independent of color
* Used for:

  * Move generation
  * Attack generation
  * Evaluation
  * Bitboard indexing

This enum deliberately excludes color, which is handled separately.

The encoding aligns perfectly with `Piece`:

```cpp
Piece = (Color << 3) | PieceType
```

### Special Values

* `ALL_PIECES = 0`
  Used as a generic index when aggregating attacks.
* `PIECE_TYPE_NB = 8`
  Total number of piece types including sentinel values.

---

## Square Representation

```cpp
enum Square {
  SQ_A1, SQ_B1, ..., SQ_H8,
  SQ_NONE,

  SQUARE_NB = 64,

  NORTH =  8,
  EAST  =  1,
  SOUTH = -8,
  WEST  = -1,

  NORTH_EAST = NORTH + EAST,
  SOUTH_EAST = SOUTH + EAST,
  SOUTH_WEST = SOUTH + WEST,
  NORTH_WEST = NORTH + WEST
};
```

### Numeric Layout

Squares are encoded in **rank-major order**:

```
A1 = 0   B1 = 1   ... H1 = 7
A2 = 8   B2 = 9   ... H2 = 15
...
A8 = 56  B8 = 57  ... H8 = 63
```

Example:

```cpp
int(SQ_E4) == 4 + 3 * 8 == 28
```

### Why This Layout?

* Files increment by `+1`
* Ranks increment by `+8`
* Board geometry becomes simple integer arithmetic

---

## Directions as Integer Offsets

```cpp
NORTH =  8
EAST  =  1
SOUTH = -8
WEST  = -1
```

This allows simple move computation:

```cpp
SQ_E2 + NORTH        == SQ_E3
SQ_E2 + NORTH_EAST   == SQ_F3
```

Diagonal directions are composed, not duplicated:

```cpp
NORTH_EAST = NORTH + EAST
```

---

## File and Rank Enums

```cpp
enum File : int { FILE_A, FILE_B, ..., FILE_H, FILE_NB };
enum Rank : int { RANK_1, RANK_2, ..., RANK_8, RANK_NB };
```

These are **semantic types**, not just integers.

They improve:

* Readability
* Type safety
* Template specialization

Extraction helpers:

```cpp
inline File file_of(Square s) { return File(s & 7); }
inline Rank rank_of(Square s) { return Rank(s >> 3); }
```

Construction:

```cpp
inline Square make_square(File f, Rank r) {
  return Square((r << 3) + f);
}
```

Everything reduces to:

```
square = rank * 8 + file
```

---

## Color-Relative Squares

```cpp
inline Square relative_square(Color c, Square s) {
  return Square(s ^ (c * 56));
}
```

* For **WHITE (c = 0)**: square unchanged
* For **BLACK (c = 1)**: square vertically flipped

Why `56`?

```
56 = 7 * 8 = A8
```

Examples:

```
A1 ^ 56 = A8
C1 ^ 56 = C8
```

This allows writing **color-independent evaluation logic**.

---

## Castling Representation

### CastlingSide

```cpp
enum CastlingSide {
  KING_SIDE,
  QUEEN_SIDE,
  CASTLING_SIDE_NB = 2
};
```

* Simple selector enum
* Not a bitmask
* Used in templates and branching logic

---

### CastlingRight: Bitmask Encoding

```cpp
enum CastlingRight {
  NO_CASTLING,
  WHITE_OO,
  WHITE_OOO = WHITE_OO << 1,
  BLACK_OO  = WHITE_OO << 2,
  BLACK_OOO = WHITE_OO << 3,
  ANY_CASTLING = WHITE_OO | WHITE_OOO | BLACK_OO | BLACK_OOO,
  CASTLING_RIGHT_NB = 16
};
```

### Numeric Values

```
WHITE_OO    = 1  // 0001
WHITE_OOO   = 2  // 0010
BLACK_OO    = 4  // 0100
BLACK_OOO   = 8  // 1000
```

### Why Bitmasks?

Castling rights are **independent flags**:

* A position may have:

  * Only king-side rights
  * Only queen-side rights
  * Both
  * None

Bitmasks allow all combinations efficiently:

```cpp
WHITE_OO | WHITE_OOO   // White can castle both sides
BLACK_OO | BLACK_OOO   // Black can castle both sides
WHITE_OO | BLACK_OO    // Both can castle king-side
ANY_CASTLING           // All rights available
```

## Score: Middlegame and Endgame Packed Together

Stockfish does not evaluate a position with a single number. Instead, it evaluates **two positions in parallel**:

* **Middlegame (MG) score**
* **Endgame (EG) score**

These two values are packed into a single 32-bit integer called `Score`.

```cpp
/// Score enum stores a middlegame and an endgame value in a single integer
/// The upper 16 bits store the middlegame value
/// The lower 16 bits store the endgame value
enum Score : int { SCORE_ZERO };
```

### Bit Layout

```
32-bit Score integer

|  MG (signed 16 bits) |  EG (signed 16 bits) |
|----------------------|----------------------|
| bits 31 ........ 16 | bits 15 ........ 0  |
```

This allows Stockfish to accumulate middlegame and endgame evaluations **simultaneously**, without branching on game phase.

---

### Creating a Score

```cpp
inline Score make_score(int mg, int eg) {
  return Score((int)((unsigned int)eg << 16) + mg);
}
```

Conceptually:

```
Score = (EG << 16) | MG
```

The implementation uses unsigned arithmetic to avoid undefined behavior when shifting signed integers.

---

### Extracting Values

**Endgame value:**

```cpp
inline Value eg_value(Score s) {

  union { uint16_t u; int16_t s; } eg = {
    uint16_t(unsigned(s + 0x8000) >> 16)
  };

  return Value(eg.s);
}
```

**Middlegame value:**

```cpp
inline Value mg_value(Score s) {

  union { uint16_t u; int16_t s; } mg = {
    uint16_t(unsigned(s))
  };

  return Value(mg.s);
}
```

These functions carefully preserve sign and avoid implementation-defined behavior in C++.

---

### Why Stockfish Uses `Score`

This design enables:

* Continuous transition between middlegame and endgame
* No runtime branching on game phase
* Extremely cache-friendly evaluation
* Simple accumulation of evaluation terms

Throughout evaluation, Stockfish accumulates `Score` values:

```cpp
Score score = SCORE_ZERO;
score += MobilityBonus;
score += PawnStructure;
score += KingSafety;
```

Only at the very end is the final value computed by interpolating between MG and EG using the game phase.

---

### Mental Model

Think of `Score` as a **2-component vector**:

```
Score = ⟨middlegame, endgame⟩
```

Evaluation is vector addition, and the final numeric score is a weighted projection based on how far the game has progressed.

## Move Representation

```cpp
/// A move needs 16 bits to be stored
///
/// bit  0- 5: destination square (from 0 to 63)
/// bit  6-11: origin square (from 0 to 63)
/// bit 12-13: promotion piece type - 2 (from KNIGHT-2 to QUEEN-2)
/// bit 14-15: special move flag: promotion (1), en passant (2), castling (3)
/// NOTE: EN-PASSANT bit is set only when a pawn can be captured
///
/// Special cases are MOVE_NONE and MOVE_NULL. We can sneak these in because in
/// any normal move destination square is always different from origin square
/// while MOVE_NONE and MOVE_NULL have the same origin and destination square.

enum Move : int {
  MOVE_NONE,
  MOVE_NULL = 65
};
```

Stockfish represents every chess move in just 16 bits for speed and cache efficiency.

### Bit Layout (16 bits)

```
15 14 | 13 12 | 11 ...... 6 | 5 ...... 0
----------------------------------------
flags | promo |   from      |   to
```

```
| Bits    | Meaning                       |
| ------- | ----------------------------- |
| 0–5     | Destination square (0–63)     |
| 6–11    | Origin square (0–63)          |
| 12–13   | Promotion piece − 2           |
| 14–15   | Special move flag             |
```

### Squares (6 bits each)

Squares are encoded as integers:

```
A1 = 0, B1 = 1, ..., H8 = 63
```

So:
- `from_sq(m)` → bits 6–11
- `to_sq(m)` → bits 0–5

### Special Move Flags (bits 14–15)

```
| Value | Meaning     |
| ----: | ----------- |
|  `00` | Normal move |
|  `01` | Promotion   |
|  `10` | En passant  |
|  `11` | Castling    |
```

### Promotion Encoding (bits 12–13)

Promotion piece type is encoded as:

```
promotion_piece = (promotion_type + 2)
```

```
| Promotion | Encoded |
| --------- | ------- |
| Knight    | 0       |
| Bishop    | 1       |
| Rook      | 2       |
| Queen     | 3       |
```

Because as per Stockfish representation, `NO_PIECE_TYPE` and `PAWN` are not useful for promotion, so we can save bits.

```cpp
enum PieceType {
  NO_PIECE_TYPE = 0,
  PAWN          = 1,
  KNIGHT        = 2,
  BISHOP        = 3,
  ROOK          = 4,
  QUEEN         = 5,
  KING          = 6
};
```

### MOVE_NONE and MOVE_NULL

```cpp
enum Move : int {
  MOVE_NONE,
  MOVE_NULL = 65
};
```

Why this works
- A legal move always has from != to
- These special moves violate that rule

#### MOVE_NONE

```
from = 0
to   = 0
```

Used to mean:
- “no move”
- invalid move
- search sentinel

#### MOVE_NULL

```
from = 1
to   = 1   // 1 | (1 << 6) = 65
```

Used for:
- null move pruning
- represents “pass move” (side switches, no piece moved)

### Accessor Macros 

Internally Stockfish uses helpers like:

```cpp
to_sq(m)      = m & 0x3F
from_sq(m)    = (m >> 6) & 0x3F
type_of(m)    = m & 0xC000
promo_type(m) = ((m >> 12) & 3) + KNIGHT
```

## StepAttacksBB - Pre-computed Attack Tables

`StepAttacksBB` is a lookup table that stores pre-computed attack patterns for pieces that move in fixed steps (not sliding pieces).

```cpp
Bitboard StepAttacksBB[PIECE_NB][SQUARE_NB];
// [16 piece types][64 squares] = 1024 bitboards
```

"Step attacks" = pieces that attack a fixed pattern of squares:

- Pawns (different for white/black)
- Knights
- Kings
- NOT bishops, rooks, queens (these are "sliding" pieces)

### What's Stored

```cpp
// For each piece type and square, store which squares it attacks
StepAttacksBB[piece][from_square] → Bitboard of attacked squares
```

**Examples:**

```cpp
StepAttacksBB[W_PAWN][e4]  → Bitboard with d5, f5 set (white pawn attacks)
StepAttacksBB[B_PAWN][e5]  → Bitboard with d4, f4 set (black pawn attacks)
StepAttacksBB[W_KNIGHT][e4] → Bitboard with d2, f2, c3, g3, c5, g5, d6, f6
StepAttacksBB[W_KING][e1]  → Bitboard with d1, f1, d2, e2, f2
```

## LineBB

```cpp
Bitboard LineBB[SQUARE_NB][SQUARE_NB];
```

LineBB is a precomputed bitboard table that represents:

> The entire straight line passing through two squares
> if they are aligned (same rank/file/diagonal)

Otherwise:

```cpp
LineBB[a][b] = 0
```

Intuition

If you pick two squares:
- e1 and e8 → same file
- c1 and h6 → same diagonal
- a1 and h1 → same rank

Then the squares between them lie on a straight line.


So `LineBB[s1][s2] `is a bitboard answers:

> Which squares belong to the line containing both s1 and s2?

Example:

Squares: e1 and e8

They are aligned vertically.

So `LineBB[e1][e8]` returns bitboard containing `e1 e2 e3 e4 e5 e6 e7 e8`.

Squares: c1 and h6

Diagonal alignment: So `LineBB[c1][h6]` returns `c1 d2 e3 f4 g5 h6`.

Squares: a1 and c2

Not aligned (not same file/rank/diagonal). So `LineBB[a1][c2] == 0`.

### Used in aligned()


```cpp
aligned(from, to, kingSquare)
```

This is implemented as:

```cpp
inline bool aligned(Square a, Square b, Square c) {
    return LineBB[a][b] & c;
}
```

Meaning:

> Is square c on the line through a and b?

## BetweenBB

```cpp
Bitboard BetweenBB[SQUARE_NB][SQUARE_NB];
```

This is a precomputed lookup table:

BetweenBB[a][b] gives the bitboard of all squares strictly between square a and square b, if they are aligned.

What does “between” mean?

If two squares lie on the same:
- rank (horizontal)
- file (vertical)
- diagonal

**Why is this useful?**

Because chess is full of “line relationships”:
- pinned pieces
- blocking checks
- sliding attacks (rook/bishop/queen)
- discovering check
- legality testing

Example BetweenBB[a1][a8] returns a bitboard of these squares {a2, a3, a4, a5, a6, a7}

If squares are not aligned → empty bitboard


### Key usage: Blocking a check


Suppose black queen gives check:

```
Black queen: e7
White king:  e1
```

BetweenBB[E7][E1] = {E6,E5,E4,E3,E2}

Now, if white is in check, legal responses include:
- capture attacker
- move king
- block the line

Stockfish uses this here:

```cpp
if (!((between_bb(checkerSq, kingSq) | checkers()) & to))
    return false;
```

Means you must do either
- capture the checker, or
- land on a square between checker and king

BetweenBB is precomputed for speed


## SquareBB

```cpp
Bitboard SquareBB[SQUARE_NB];
```

This is an array of 64 bitboards:
- SquareBB[SQ_A1] → bitboard with only A1 set
- SquareBB[SQ_E4] → bitboard with only E4 set

Example

```cpp
SquareBB[E4] = 1ULL << E4
```

```cpp
SquareBB[E4] = 00000000
               00000000
               00000000
               00010000   ← only e4 bit is 1
               00000000
               00000000
               00000000
               00000000
```

Used for:
- Adding/removing pieces quickly
- XOR toggling squares
- Building masks

```cpp
byTypeBB[PAWN] |= SquareBB[s];
```

So instead of computing (1ULL << s) every time, Stockfish just does:

```cpp
SquareBB[s]
```

## FileBB

Meaning: Bitboard for an entire file

```cpp
Bitboard FileBB[FILE_NB];
```

There are 8 files:
- File A
- File B
- …
- File H

So:
- FileBB[FILE_A] = all squares on file A set
- FileBB[FILE_E] = all squares on file E set

Example: File A

```cpp
FileBB[A] =
  8  1 . . . . . . .
  7  1 . . . . . . .
  6  1 . . . . . . .
  5  1 . . . . . . .
  4  1 . . . . . . .
  3  1 . . . . . . .
  2  1 . . . . . . .
  1  1 . . . . . . .
     a b c d e f g h
```

Hex:

```cpp
FileBB[A] = 0x0101010101010101
```

Used for:
- Pawn structure evaluation
- Open/semi-open files
- Rook file attacks

```cpp
if (!(pieces(PAWN) & FileBB[file]))
    // file is open
```

## RankBB

Meaning: Bitboard for an entire rank

```cpp
Bitboard RankBB[RANK_NB];
```

There are 8 ranks:
- Rank 1
- Rank 2
- …
- Rank 8

So:
- RankBB[RANK_1] = all squares on rank 1 set
- RankBB[RANK_4] = all squares on rank 4 set

Example: Rank 4

```cpp
RankBB[4] =
  8  . . . . . . . .
  7  . . . . . . . .
  6  . . . . . . . .
  5  . . . . . . . .
  4  1 1 1 1 1 1 1 1
  3  . . . . . . . .
  2  . . . . . . . .
  1  . . . . . . . .
     a b c d e f g h
```

Hex:

```cpp
RankBB[4] = 0x00000000FF000000
```

Used for:
- Passed pawn detection
- Back rank weakness
- Rank-based attack masks

```cpp
Bitboard rank4Pieces = pieces() & RankBB[RANK_4];
```

## PseudoAttacks

```cpp
Bitboard PseudoAttacks[PIECE_TYPE_NB][SQUARE_NB];
```

PseudoAttacks is a precomputed attack lookup table:

> For every piece type and every square, it stores the squares that piece could attack on an empty board (or ignoring blockers).

```cpp
PseudoAttacks[pt][sq]
```

answers:

> “If a piece of type pt sits on square sq, what squares are in its attack pattern?”


Why “Pseudo”?

Because these are not always real attacks in an actual position.

For sliding pieces (rook/bishop/queen):
- The direction is correct
- But blockers are ignored

So it’s a pseudo-attack, not the final legal attack set.
