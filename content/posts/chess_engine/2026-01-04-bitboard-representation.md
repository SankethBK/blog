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