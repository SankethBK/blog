---
title:  "Zobrist Hashing"
date:   2026-01-10
draft: false
categories: ["chess engines"]
tags: ["zobrist hashing"]
author: Sanketh
---

# Zobrist Hashing

## What problem Zobrist hashing solves

In a chess engine, we constantly need to:
- Identify identical positions reached via different move orders
- Detect threefold repetition
- Cache evaluations in a transposition table (TT)

But:
- Comparing full board state is too slow
- Copying board state is too expensive

## The Core Idea

**Goal:** Convert a chess position into a single 64-bit number (the "hash" or "key") that:

1. Uniquely identifies the position (with very high probability)
2. Can be incrementally updated when making moves
3. Enables O(1) position comparison

## What a Zobrist key represents

A Zobrist key is a 64-bit integer (Key in Stockfish) representing:
- Which pieces are on which squares
- Side to move
- Castling rights
- En-passant file (if any)

```cpp
namespace Zobrist {

  Key psq[PIECE_NB][SQUARE_NB];
  Key enpassant[FILE_NB];
  Key castling[CASTLING_RIGHT_NB];
  Key side;
}
```

Key is 64 bit unsigned integer 

```cpp
typedef uint64_t Key;
```

Formally:

```
key =
  XOR(piece-square keys)
^ XOR(side-to-move key)
^ XOR(castling-rights key)
^ XOR(en-passant-file key)
```

Two positions that are identical under chess rules will have the same Zobrist key.


## Core idea: XOR as reversible edit

Zobrist hashing relies on one crucial property:

```cpp
X ^ A ^ A == X
```

This makes it perfect for move/unmove.

Example

If a white knight moves from g1 → f3:

```cpp
key ^= Zobrist::psq[W_KNIGHT][G1];
key ^= Zobrist::psq[W_KNIGHT][F3];
```

Undoing the move applies the same XORs, restoring the old key.

Key Insight: Zobrist keys are not recomputed — they are edited.

## Zobrist tables in Stockfish

### Initialization (At Program Startup)

```cpp
void Position::init() {

  PRNG rng(1070372);

  for (Piece pc : Pieces)
      for (Square s = SQ_A1; s <= SQ_H8; ++s)
          Zobrist::psq[pc][s] = rng.rand<Key>();

  for (File f = FILE_A; f <= FILE_H; ++f)
      Zobrist::enpassant[f] = rng.rand<Key>();

  for (int cr = NO_CASTLING; cr <= ANY_CASTLING; ++cr)
  {
      Zobrist::castling[cr] = 0;
      Bitboard b = cr;
      while (b)
      {
          Key k = Zobrist::castling[1ULL << pop_lsb(&b)];
          Zobrist::castling[cr] ^= k ? k : rng.rand<Key>();
      }
  }

  Zobrist::side = rng.rand<Key>();
}
```

**Why a fixed seed?**

- Same random numbers every time the program runs
- Makes debugging easier (hashes are reproducible)
- Different engines use different seeds (so they don't share bugs)
- Avoid collision of random values

Stockfish precomputes random 64-bit values for:

### 1. Piece–square keys

```cpp
Zobrist::psq[piece][square]
```

- One random number for every (piece, square) pair
- 12 pieces x 64 squares = 768 random values
- Covers all colors and piece types

Used for:
- Full position key
- Pawn key
- Material key

### 2. Side to move

```cpp
Zobrist::side
```

- XORed once per move
- Ensures same board with different side ≠ same key

### 3. Castling rights

```cpp
Zobrist::castling[rights_mask]
```

- Indexed by castling-rights bitmask
- Rights are removed incrementally

### 4. En-passant file

```cpp
Zobrist::enpassant[file]
```

- Only the file matters (rank is implicit)
- Only added if EP capture is legal
- Prevents false repetition detection

## Incremental Updates (The Magic!)

### Moving a Piece (e.g., Nf3-e5)

```cpp
// Starting hash
Key hash = current_position_hash;

// Remove knight from f3
hash ^= Zobrist::psq[W_KNIGHT][f3];

// Add knight to e5
hash ^= Zobrist::psq[W_KNIGHT][e5];

// Flip side to move
hash ^= Zobrist::side;

// Done! New hash computed in O(1)
```

### Capturing (e.g., Nxe5, capturing black pawn)

```cpp
Key hash = current_position_hash;

// Remove white knight from f3
hash ^= Zobrist::psq[W_KNIGHT][f3];

// Remove black pawn from e5 (captured)
hash ^= Zobrist::psq[B_PAWN][e5];

// Add white knight to e5
hash ^= Zobrist::psq[W_KNIGHT][e5];

// Flip side to move
hash ^= Zobrist::side;
```

### Castling (e.g., White kingside O-O)

```cpp
Key hash = current_position_hash;

// Remove king from e1
hash ^= Zobrist::psq[W_KING][e1];

// Add king to g1
hash ^= Zobrist::psq[W_KING][g1];

// Remove rook from h1
hash ^= Zobrist::psq[W_ROOK][h1];

// Add rook to f1
hash ^= Zobrist::psq[W_ROOK][f1];

// Update castling rights (white loses both)
hash ^= Zobrist::castling[old_rights];  // Remove old
hash ^= Zobrist::castling[new_rights];  // Add new

// Flip side to move
hash ^= Zobrist::side;
```

### Creating en passant opportunity (e.g., e2-e4):

```cpp
// Clear old en passant (if any)
if (old_ep_square != SQ_NONE)
    hash ^= Zobrist::enpassant[file_of(old_ep_square)];

// Set new en passant
hash ^= Zobrist::enpassant[FILE_E];
```

## Keys used in StateInfo

`StateInfo` class stores 3 zobrist hashing keys

```cpp
struct StateInfo {

  // Copied when making a move
  Key    pawnKey;
  Key    materialKey;
  ...

  // Not copied when making a move (will be recomputed anyhow)
  Key        key;
};
```

### Initialization Logic

```cpp
void Position::set_state(StateInfo* si) const {

  si->key = si->pawnKey = si->materialKey = 0;
  si->nonPawnMaterial[WHITE] = si->nonPawnMaterial[BLACK] = VALUE_ZERO;
  si->psq = SCORE_ZERO;
  si->checkersBB = attackers_to(square<KING>(sideToMove)) & pieces(~sideToMove);

  set_check_info(si);

  for (Bitboard b = pieces(); b; )
  {
      Square s = pop_lsb(&b);
      Piece pc = piece_on(s);
      si->key ^= Zobrist::psq[pc][s];
      si->psq += PSQT::psq[pc][s];
  }

  if (si->epSquare != SQ_NONE)
      si->key ^= Zobrist::enpassant[file_of(si->epSquare)];

  if (sideToMove == BLACK)
      si->key ^= Zobrist::side;

  si->key ^= Zobrist::castling[si->castlingRights];

  for (Bitboard b = pieces(PAWN); b; )
  {
      Square s = pop_lsb(&b);
      si->pawnKey ^= Zobrist::psq[piece_on(s)][s];
  }

  for (Piece pc : Pieces)
  {
      if (type_of(pc) != PAWN && type_of(pc) != KING)
          si->nonPawnMaterial[color_of(pc)] += pieceCount[pc] * PieceValue[MG][pc];

      for (int cnt = 0; cnt < pieceCount[pc]; ++cnt)
          si->materialKey ^= Zobrist::psq[pc][cnt];
  }
}
```

### 1. Full position key

```cpp
st->key
```

Used for:
- Transposition table
- Repetition detection

### 2. Pawn hash

```cpp
st->pawnKey
```

Only includes:
- Pawn piece-square keys

Used for:
- Pawn structure evaluation cache

-> Pawn structure changes rarely → huge speed win

### 3 Material hash

```cpp
st->materialKey
```

Includes:
 - Piece counts only (not squares)

Used for:
 - Material evaluation
 - Endgame detection

## Clever bit operation to unset LSB

In this code

```cpp
for (Bitboard b = pieces(PAWN); b; )
  {
      Square s = pop_lsb(&b);
      si->pawnKey ^= Zobrist::psq[piece_on(s)][s];
  }
```

`pieces(PAWN)` is just one bitboard, we are repeadly iterating through it until it becomes 0. `b;` breaks the loop when b is 0. 

`pop_lsb` is responsible for unsetting LSB of `b`.

```cpp
inline Square pop_lsb(Bitboard* b) {
  const Square s = lsb(*b);
  *b &= *b - 1;
  return s;
}

inline Square lsb(Bitboard b) {
  assert(b);
  return Square(__builtin_ctzll(b));
}
```

`x = x & (x - 1)` is a clever way of unsetting the LSB.

It works because, any positive numbers can be assumed as of he form

```
xxxxx1000...000
     ^
     lowest set bit (LSB)
```

That is:
- Some prefix of bits (x)
- Then one 1
- Then only zeros to the right

Example

```
x = 40 = 0b00101000
              ^
              LSB
```

**What does x - 1 do in binary?**


Subtracting 1:
- Turns the rightmost 1 into 0
- Turns all trailing zeros into 1s

Example

```
x     = 00101000
x - 1 = 00100111
```

So:
- The lowest 1 flips to 0
- Everything to the right becomes 1

Now apply x & (x - 1)

Let’s AND them:

```
x     = 00101000
x - 1 = 00100111
---------------- &
result= 00100000
```

What happened?
- All higher bits stay the same
- The lowest set bit is cleared
- Nothing else changes


### __builtin_ctzll

`__builtin_ctzll` is a compiler intrinsic that usually compiles down to a single CPU instruction.

- ctz = count trailing zeros
- ll = long long (64-bit)
- Returns: number of consecutive 0 bits starting from the least significant bit

On x86-64, this usually becomes:
- `TZCNT` (newer CPUs)
- or `BSF` (older CPUs)

Both are single instructions.

On ARM64 (Apple Silicon), it becomes:
- `RBIT` + `CLZ`
or
- native `CTZ` instruction

Still 1–2 instructions max.