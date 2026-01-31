---
title:  "Game Mechanics"
date:   2026-01-12
draft: false
categories: ["chess engines"]
tags: ["game mechanics"]
author: Sanketh
---

We will go through some of the functions which are part of core game mechanics


# Game Mechanics

## 1. Piece Movement

### 1. do_move

**Purpose**: Execute a move and update all position state incrementally.

**Critical for performance**: This function is called **millions of times per second** during search. Every optimization matters.

**Preconditions**:
- Move `m` must be **legal** (pseudo-legal moves should be filtered first)
- `newSt` must be a **different** StateInfo object than current state
- Caller provides `givesCheck` flag (optional optimization to avoid recalculating)

#### Function Structure Overview

1. Setup and assertions
2. Copy old state → new state
3. Increment counters
4. Handle castling (special case)
5. Handle captures
6. Update position hash
7. Reset en passant
8. Update castling rights
9. Move the piece
10. Handle pawn moves (en passant, promotion)
11. Update incremental scores
12. Finalize state
13. Flip side to move
14. Compute check info

```cpp
/// Position::do_move() makes a move, and saves all information necessary
/// to a StateInfo object. The move is assumed to be legal. Pseudo-legal
/// moves should be filtered out before this function is called.

void Position::do_move(Move m, StateInfo& newSt, bool givesCheck) {

  assert(is_ok(m));
  assert(&newSt != st);

  ++nodes;
  Key k = st->key ^ Zobrist::side;

  // Copy some fields of the old state to our new StateInfo object except the
  // ones which are going to be recalculated from scratch anyway and then switch
  // our state pointer to point to the new (ready to be updated) state.
  std::memcpy(&newSt, st, offsetof(StateInfo, key));
  newSt.previous = st;
  st = &newSt;

  // Increment ply counters. In particular, rule50 will be reset to zero later on
  // in case of a capture or a pawn move.
  ++gamePly;
  ++st->rule50;
  ++st->pliesFromNull;

  Color us = sideToMove;
  Color them = ~us;
  Square from = from_sq(m);
  Square to = to_sq(m);
  Piece pc = piece_on(from);
  Piece captured = type_of(m) == ENPASSANT ? make_piece(them, PAWN) : piece_on(to);

  assert(color_of(pc) == us);
  assert(captured == NO_PIECE || color_of(captured) == (type_of(m) != CASTLING ? them : us));
  assert(type_of(captured) != KING);

  if (type_of(m) == CASTLING)
  {
      assert(pc == make_piece(us, KING));
      assert(captured == make_piece(us, ROOK));

      Square rfrom, rto;
      do_castling<true>(us, from, to, rfrom, rto);

      st->psq += PSQT::psq[captured][rto] - PSQT::psq[captured][rfrom];
      k ^= Zobrist::psq[captured][rfrom] ^ Zobrist::psq[captured][rto];
      captured = NO_PIECE;
  }

  if (captured)
  {
      Square capsq = to;

      // If the captured piece is a pawn, update pawn hash key, otherwise
      // update non-pawn material.
      if (type_of(captured) == PAWN)
      {
          if (type_of(m) == ENPASSANT)
          {
              capsq -= pawn_push(us);

              assert(pc == make_piece(us, PAWN));
              assert(to == st->epSquare);
              assert(relative_rank(us, to) == RANK_6);
              assert(piece_on(to) == NO_PIECE);
              assert(piece_on(capsq) == make_piece(them, PAWN));

              board[capsq] = NO_PIECE; // Not done by remove_piece()
          }

          st->pawnKey ^= Zobrist::psq[captured][capsq];
      }
      else
          st->nonPawnMaterial[them] -= PieceValue[MG][captured];

      // Update board and piece lists
      remove_piece(captured, capsq);

      // Update material hash key and prefetch access to materialTable
      k ^= Zobrist::psq[captured][capsq];
      st->materialKey ^= Zobrist::psq[captured][pieceCount[captured]];
      prefetch(thisThread->materialTable[st->materialKey]);

      // Update incremental scores
      st->psq -= PSQT::psq[captured][capsq];

      // Reset rule 50 counter
      st->rule50 = 0;
  }

  // Update hash key
  k ^= Zobrist::psq[pc][from] ^ Zobrist::psq[pc][to];

  // Reset en passant square
  if (st->epSquare != SQ_NONE)
  {
      k ^= Zobrist::enpassant[file_of(st->epSquare)];
      st->epSquare = SQ_NONE;
  }

  // Update castling rights if needed
  if (st->castlingRights && (castlingRightsMask[from] | castlingRightsMask[to]))
  {
      int cr = castlingRightsMask[from] | castlingRightsMask[to];
      k ^= Zobrist::castling[st->castlingRights & cr];
      st->castlingRights &= ~cr;
  }

  // Move the piece. The tricky Chess960 castling is handled earlier
  if (type_of(m) != CASTLING)
      move_piece(pc, from, to);

  // If the moving piece is a pawn do some special extra work
  if (type_of(pc) == PAWN)
  {
      // Set en-passant square if the moved pawn can be captured
      if (   (int(to) ^ int(from)) == 16
          && (attacks_from<PAWN>(to - pawn_push(us), us) & pieces(them, PAWN)))
      {
          st->epSquare = (from + to) / 2;
          k ^= Zobrist::enpassant[file_of(st->epSquare)];
      }

      else if (type_of(m) == PROMOTION)
      {
          Piece promotion = make_piece(us, promotion_type(m));

          assert(relative_rank(us, to) == RANK_8);
          assert(type_of(promotion) >= KNIGHT && type_of(promotion) <= QUEEN);

          remove_piece(pc, to);
          put_piece(promotion, to);

          // Update hash keys
          k ^= Zobrist::psq[pc][to] ^ Zobrist::psq[promotion][to];
          st->pawnKey ^= Zobrist::psq[pc][to];
          st->materialKey ^=  Zobrist::psq[promotion][pieceCount[promotion]-1]
                            ^ Zobrist::psq[pc][pieceCount[pc]];

          // Update incremental score
          st->psq += PSQT::psq[promotion][to] - PSQT::psq[pc][to];

          // Update material
          st->nonPawnMaterial[us] += PieceValue[MG][promotion];
      }

      // Update pawn hash key and prefetch access to pawnsTable
      st->pawnKey ^= Zobrist::psq[pc][from] ^ Zobrist::psq[pc][to];
      prefetch(thisThread->pawnsTable[st->pawnKey]);

      // Reset rule 50 draw counter
      st->rule50 = 0;
  }

  // Update incremental scores
  st->psq += PSQT::psq[pc][to] - PSQT::psq[pc][from];

  // Set capture piece
  st->capturedPiece = captured;

  // Update the key with the final value
  st->key = k;

  // Calculate checkers bitboard (if move gives check)
  st->checkersBB = givesCheck ? attackers_to(square<KING>(them)) & pieces(us) : 0;

  sideToMove = ~sideToMove;

  // Update king attacks used for fast check detection
  set_check_info(st);

  assert(pos_is_ok());
}
```


#### Phase 1: Sanity checks and bookkeeping

```cpp
assert(is_ok(m));
assert(&newSt != st);

++nodes;
Key k = st->key ^ Zobrist::side;
```

- Ensures the move encoding is valid
- Ensures we don’t overwrite the current state
- Increments node counter (used for search statistics)
- Flips side-to-move bit in the Zobrist key, k is a working copy of the hash key, updated incrementally.

#### Phase 2: StateInfo chaining (undo mechanism)

```cpp
std::memcpy(&newSt, st, offsetof(StateInfo, key));
newSt.previous = st;
st = &newSt;
```

- Copies all fields up to key
- Fields after key will be recomputed
- Links the new state to the previous one (stack-style undo)
- Advances the st pointer

#### Phase 3: Ply counters

```cpp
++gamePly;
++st->rule50;
++st->pliesFromNull;
```

- gamePly: depth from game start
- rule50: increments unless reset later
- pliesFromNull: prevents consecutive null moves

#### Phase 4: Decode move and involved pieces

```cpp
Color us = sideToMove;
Color them = ~us;

Square from = from_sq(m);
Square to   = to_sq(m);

Piece pc = piece_on(from);
Piece captured =
    type_of(m) == ENPASSANT ? make_piece(them, PAWN) : piece_on(to);

assert(color_of(pc) == us);
assert(captured == NO_PIECE || color_of(captured) == (type_of(m) != CASTLING ? them : us));
assert(type_of(captured) != KING);
```

- Determines moving side
- Determines source and destination squares
- Determines captured piece (special handling for en passant)

Assertions ensure:
- Correct colors
- No king is ever captured

#### Phase 5: Castling (special-case logic)

```cpp
if (type_of(m) == CASTLING)
{
    assert(pc == make_piece(us, KING));
    assert(captured == make_piece(us, ROOK));

    Square rfrom, rto;
    do_castling<true>(us, from, to, rfrom, rto);

    st->psq += PSQT::psq[captured][rto] - PSQT::psq[captured][rfrom];
    k ^= Zobrist::psq[captured][rfrom] ^ Zobrist::psq[captured][rto];
    captured = NO_PIECE;
}
```

Castling is encoded as "king captures rook":

- `from` = king square (e.g., e1)
- `to` = rook square (e.g., h1 for kingside)
- `captured` = our own rook

`do_castling<true>()` does:

- Moves king to final square (g1)
- Moves rook to final square (f1)
- Returns `rfrom` and `rto` (rook's old and new squares)

```cpp
st->psq += PSQT::psq[captured][rto] - PSQT::psq[captured][rfrom];
```

- Remove rook's old position score
- Add rook's new position score
- (King's score updated later in main move code)

```cpp
k ^= Zobrist::psq[captured][rfrom] ^ Zobrist::psq[captured][rto];
```
- XOR out rook from old square
- XOR in rook on new square

```cpp
captured = NO_PIECE;
```

- Special logic for castling is complete here, `captured` is set back to `NO_PIECE` (we don't actually capture in castling)
- Prevents later code from treating this as a capture

#### Phase 6: Capture handling

If a capture occurs: (Castling doesn't enter here)


```cpp
if (captured)
{
    Square capsq = to;

    // If the captured piece is a pawn, update pawn hash key, otherwise
    // update non-pawn material.
    if (type_of(captured) == PAWN)
    {
        if (type_of(m) == ENPASSANT)
        {
            capsq -= pawn_push(us);

            assert(pc == make_piece(us, PAWN));
            assert(to == st->epSquare);
            assert(relative_rank(us, to) == RANK_6);
            assert(piece_on(to) == NO_PIECE);
            assert(piece_on(capsq) == make_piece(them, PAWN));

            board[capsq] = NO_PIECE; // Not done by remove_piece()
        }

        st->pawnKey ^= Zobrist::psq[captured][capsq];
    }
    else
        st->nonPawnMaterial[them] -= PieceValue[MG][captured];

    // Update board and piece lists
    remove_piece(captured, capsq);

    // Update material hash key and prefetch access to materialTable
    k ^= Zobrist::psq[captured][capsq];
    st->materialKey ^= Zobrist::psq[captured][pieceCount[captured]];
    prefetch(thisThread->materialTable[st->materialKey]);

    // Update incremental scores
    st->psq -= PSQT::psq[captured][capsq];

    // Reset rule 50 counter
    st->rule50 = 0;
}
```

Capture square:

- Usually `to` (normal capture)
- Exception: En passant (handled next)

```cpp
    if (type_of(m) == ENPASSANT)
    {
        capsq -= pawn_push(us);
```

- For Enpassant, captured piece is one square behind the captured square.

```
Example: White pawn on e5, black pawn on d5 (just moved d7-d5)
Move: exd6 (en passant)

to = d6 (target square, EMPTY)
capsq = d6 - pawn_push(WHITE)
      = d6 - 8
      = d5 (where black pawn actually is)
```

```cpp
        board[capsq] = NO_PIECE; // Not done by remove_piece()
```

- Special case for Enpassant, we need to clear the mailbox board manually, for other captures it will be handled by `move_piece` later.

```cpp
          st->pawnKey ^= Zobrist::psq[captured][capsq];
```

- Remove captured pawn from pawn structure hash.

```cpp
else
    st->nonPawnMaterial[them] -= PieceValue[MG][captured];
```

- `nonPawnMaterial` excludes pawns (used for endgame detection)
- Pawn captures don't change this value

**Remove Captured Piece**

```cpp
remove_piece(captured, capsq);
```

`remove_piece()` does:

- Clear from `byTypeBB[type]`
- Clear from `byColorBB[color]`
- Remove from `pieceList[captured]`
- Update `index[]` array
- Decrement `pieceCount[captured]`
- At this point, captured piece is completely out of the board. 


**Update Material Hash**

```cpp
k ^= Zobrist::psq[captured][capsq];
st->materialKey ^= Zobrist::psq[captured][pieceCount[captured]];
```

- Captured piece is removed from Zobrist hash key `k`
- Same for `materialKey`. Remember: Material hash uses count, not square

**Prefetch Material Table**

```cpp
prefetch(thisThread->materialTable[st->materialKey]);
```

Prefetch explained:

Modern CPUs have cache hierarchy (L1/L2/L3). Prefetching hints the CPU to load data into cache before it's needed.

```cpp
prefetch(address)  // → CPU instruction: load this memory into cache
```

Why prefetch?

- We'll need `materialTable[st->materialKey]` soon (for evaluation)
- Loading from RAM is slow (~100+ cycles)
- Prefetching starts the load now (overlaps with other work)
- By the time we need it, it's already in cache

**Update PSQ Score**

```cpp
st->psq -= PSQT::psq[captured][capsq];
```

- Remove captured piece's positional bonus from total score.

**Reset 50-Move Rule**

```cpp
st->rule50 = 0;
```

- Captures reset the 50-move draw counter.


**Update Hash for Moving Piece**

```cpp
k ^= Zobrist::psq[pc][from] ^ Zobrist::psq[pc][to];
```

- We already removed only the captured piece from hash, this is just a piece moving from one swuare to another.

**Reset En Passant Square**

```cpp
if (st->epSquare != SQ_NONE)
{
    k ^= Zobrist::enpassant[file_of(st->epSquare)];
    st->epSquare = SQ_NONE;
}
```

Clear old en passant:

- Old state might have had en passant opportunity
- Remove it from hash
- Reset to `SQ_NONE`
- (Will be set again later if this move creates new ep opportunity)

#### Phase 7: Update Castling Rights

```cpp
if (st->castlingRights && (castlingRightsMask[from] | castlingRightsMask[to]))
{
    int cr = castlingRightsMask[from] | castlingRightsMask[to];
    k ^= Zobrist::castling[st->castlingRights & cr];
    st->castlingRights &= ~cr;
}
```

- If `castlingRights` is present and the current move touches any of the square that disturbs any castling rights

```cpp
int cr = castlingRightsMask[from] | castlingRightsMask[to];
```
- These are the castling rights lost.


#### Phase 8: Move the Piece

```cpp
if (type_of(m) != CASTLING)
    move_piece(pc, from, to);
```

`move_piece()` does:

- Update `board[from]` and `board[to]`
- Update bitboards
- Update `pieceList[]`
- Update `index[]`

**Why skip for castling?**

- Castling already moved both king and rook in `do_castling()`
- Would be redundant and incorrect to move again

#### Phase 9: Pawn Specific handling

```cpp
  // If the moving piece is a pawn do some special extra work
  if (type_of(pc) == PAWN)
  {
      // Set en-passant square if the moved pawn can be captured
      if (   (int(to) ^ int(from)) == 16
          && (attacks_from<PAWN>(to - pawn_push(us), us) & pieces(them, PAWN)))
      {
          st->epSquare = (from + to) / 2;
          k ^= Zobrist::enpassant[file_of(st->epSquare)];
      }

      else if (type_of(m) == PROMOTION)
      {
          Piece promotion = make_piece(us, promotion_type(m));

          assert(relative_rank(us, to) == RANK_8);
          assert(type_of(promotion) >= KNIGHT && type_of(promotion) <= QUEEN);

          remove_piece(pc, to);
          put_piece(promotion, to);

          // Update hash keys
          k ^= Zobrist::psq[pc][to] ^ Zobrist::psq[promotion][to];
          st->pawnKey ^= Zobrist::psq[pc][to];
          st->materialKey ^=  Zobrist::psq[promotion][pieceCount[promotion]-1]
                            ^ Zobrist::psq[pc][pieceCount[pc]];

          // Update incremental score
          st->psq += PSQT::psq[promotion][to] - PSQT::psq[pc][to];

          // Update material
          st->nonPawnMaterial[us] += PieceValue[MG][promotion];
      }

      // Update pawn hash key and prefetch access to pawnsTable
      st->pawnKey ^= Zobrist::psq[pc][from] ^ Zobrist::psq[pc][to];
      prefetch(thisThread->pawnsTable[st->pawnKey]);

      // Reset rule 50 draw counter
      st->rule50 = 0;
  }
  ```

Pawns require extra handling because they have unique rules:
- double pushes create en-passant rights
- promotions replace the pawn with a new piece
- pawn structure is evaluated separately
- pawn moves reset the 50-move draw counter

```cpp
if (   (int(to) ^ int(from)) == 16
    && (attacks_from<PAWN>(to - pawn_push(us), us) & pieces(them, PAWN)))
```

A pawn double push always moves exactly 16 squares in index space:
- White: rank 2 → rank 4
- Black: rank 7 → rank 5

Stockfish uses XOR instead of subtraction because it’s slightly faster and works reliably with square encoding.

**Can the pawn actually be captured?**

Meaning:
- look at the square the pawn passed over
- generate pawn attacks from that square
- check if enemy pawns exist on those attack squares

So en-passant is only enabled if it is a real tactical possibility.

**Setting the en-passant square**

```cpp
st->epSquare = (from + to) / 2;
```

The en-passant target is the square “in between”.

Example:
- e2 → e4
- epSquare = e3

Let's take a scenario where blakc pawn is on d4 and white just moved pawn from e2 to e4.

```cpp
from = e2 = 12
to = e4 = 28

// Condition 1: Double push?
(int(to) ^ int(from)) == 16
(28 ^ 12) == 16
16 == 16  ✓

// Condition 2: Can be captured?
to - pawn_push(WHITE) = 28 - 8 = 20 (e3)

attacks_from<PAWN>(e3, WHITE) = StepAttacksBB[W_PAWN][e3]
                               = Bitboard{d4, f4}
                               = 0x0000000014000000

pieces(BLACK, PAWN) = Bitboard{d4}

d4_and_f4 & black_pawns = Bitboard{d4} & Bitboard{d4}
                        = Bitboard{d4}  ✓ Non-zero!

// En passant IS set:
st->epSquare = (e2 + e4) / 2 = (12 + 28) / 2 = 20 (e3)
```

**Updating the Zobrist hash**

```cpp
k ^= Zobrist::enpassant[file_of(st->epSquare)];
```

En-passant affects legality and repetition detection, so it must be included in the position hash. Stockfish hashes only the file (not full square) because en-passant is file-dependent.

**Handling Pawn Promotion**

```cpp
else if (type_of(m) == PROMOTION)
```

Promotions are special because the pawn is removed and replaced by a stronger piece.

1. Create the promoted piece

```cpp
Piece promotion = make_piece(us, promotion_type(m));
```

Example:
- White pawn promotes to queen → W_QUEEN

Sanity checks

```cpp
assert(relative_rank(us, to) == RANK_8);
assert(type_of(promotion) >= KNIGHT && type_of(promotion) <= QUEEN);
```

Promotion must occur on the last rank, and only to:
- Knight
- Bishop
- Rook
- Queen

2. Replace pawn with promoted piece

```cpp
remove_piece(pc, to);
put_piece(promotion, to);
```

So the board now contains the new piece instead of the pawn.

3. Updating Hash Keys During Promotion

```cpp
k ^= Zobrist::psq[pc][to] ^ Zobrist::psq[promotion][to];
```

Meaning:
- remove pawn from hash
- add promoted piece to hash

Pawn structure hash

```cpp
st->pawnKey ^= Zobrist::psq[pc][to];
```

Pawn hash only tracks pawns, so the pawn disappears from it.

Material hash

```cpp
st->materialKey ^=  Zobrist::psq[promotion][pieceCount[promotion]-1]
                  ^ Zobrist::psq[pc][pieceCount[pc]];
```

MaterialKey tracks piece counts, so promotion changes:
- pawn count decreases
- promoted piece count increases

This hash is used for caching evaluation terms like bishop pair bonuses.

4. Updating Incremental Evaluation (PSQT)

```cpp
st->psq += PSQT::psq[promotion][to] - PSQT::psq[pc][to];
```

This is an incremental update:
- subtract pawn-square contribution
- add promoted piece-square contribution

5. Updating Material Balance

```cpp
st->nonPawnMaterial[us] += PieceValue[MG][promotion];
```

Promotion increases non-pawn material:
- pawn is removed
- queen/rook/etc is added

6. Updating Pawn Hash After Any Pawn Move

Regardless of promotion:

```cpp
st->pawnKey ^= Zobrist::psq[pc][from] ^ Zobrist::psq[pc][to];
```

Pawn structure is extremely important, so Stockfish maintains a separate pawn hash key.

This enables a pawn evaluation cache:

```cpp
prefetch(thisThread->pawnsTable[st->pawnKey]);
```

Meaning:
- pawn evaluation will be needed soon
- prefetch it into CPU cache early

#### Phase 10: Wrap up

```cpp
  // Update incremental scores
  st->psq += PSQT::psq[pc][to] - PSQT::psq[pc][from];

  // Set capture piece
  st->capturedPiece = captured;

  // Update the key with the final value
  st->key = k;

  // Calculate checkers bitboard (if move gives check)
  st->checkersBB = givesCheck ? attackers_to(square<KING>(them)) & pieces(us) : 0;

  sideToMove = ~sideToMove;

  // Update king attacks used for fast check detection
  set_check_info(st);

  assert(pos_is_ok());
```


This section completes the move by updating:
- evaluation bookkeeping (PSQT)
- captured piece info (for undo)
- final Zobrist key
- check detection bitboards
- side-to-move switch
- king safety helper data

**1. Incremental PSQT Update**

```cpp
// Update incremental scores
st->psq += PSQT::psq[pc][to] - PSQT::psq[pc][from];
```

st->psq is the piece-square evaluation score of the current position.

Instead of recomputing evaluation from scratch every move, Stockfish maintains it incrementally:
- Remove the piece’s contribution from the old square
- Add the contribution from the new square


**2. Store Captured Piece for Undo**

```cpp
// Set capture piece
st->capturedPiece = captured;
```

Why store this?

When search backtracks, Stockfish calls:

```cpp
undo_move(m);
```

To undo correctly, it must know:
- Was something captured?
- What piece was it?
- Where should it be restored?

So `capturedPiece` is saved inside `StateInfo`.

**3. Finalize the Zobrist Key**

```cpp
// Update the key with the final value
st->key = k;
```

What is k?

Throughout do_move(), Stockfish incrementally updated:
- piece-square hash changes
- castling rights changes
- en-passant changes
- side-to-move flip

Now the hash is complete.

**4. Compute Checkers Bitboard**

```cpp
// Calculate checkers bitboard (if move gives check)
st->checkersBB =
    givesCheck ? attackers_to(square<KING>(them)) & pieces(us) : 0;
```

What is checkersBB?

A bitboard containing all pieces currently giving check to the opponent king.

Why only if givesCheck?

Stockfish already computed earlier whether this move gives check.

So instead of recomputing always, it does:
- If check → compute attackers
- Else → set to 0

How does it work?

```cpp
attackers_to(enemyKingSquare)
```

returns all pieces attacking that square.

Intersect with:

```cpp
pieces(us)
```

to keep only the current side’s attackers.

Why store it?

Later, move generation and legality checks depend heavily on:
- “Are we in check?”
- “Who is checking us?”

**5. Switch Side to Move**

```cpp
sideToMove = ~sideToMove;
```

After making a move, it becomes the opponent’s turn.

### 2. undo_move

```cpp
/// Position::undo_move() unmakes a move. When it returns, the position should
/// be restored to exactly the same state as before the move was made.

void Position::undo_move(Move m) {

  assert(is_ok(m));

  sideToMove = ~sideToMove;

  Color us = sideToMove;
  Square from = from_sq(m);
  Square to = to_sq(m);
  Piece pc = piece_on(to);

  assert(empty(from) || type_of(m) == CASTLING);
  assert(type_of(st->capturedPiece) != KING);

  if (type_of(m) == PROMOTION)
  {
      assert(relative_rank(us, to) == RANK_8);
      assert(type_of(pc) == promotion_type(m));
      assert(type_of(pc) >= KNIGHT && type_of(pc) <= QUEEN);

      remove_piece(pc, to);
      pc = make_piece(us, PAWN);
      put_piece(pc, to);
  }

  if (type_of(m) == CASTLING)
  {
      Square rfrom, rto;
      do_castling<false>(us, from, to, rfrom, rto);
  }
  else
  {
      move_piece(pc, to, from); // Put the piece back at the source square

      if (st->capturedPiece)
      {
          Square capsq = to;

          if (type_of(m) == ENPASSANT)
          {
              capsq -= pawn_push(us);

              assert(type_of(pc) == PAWN);
              assert(to == st->previous->epSquare);
              assert(relative_rank(us, to) == RANK_6);
              assert(piece_on(capsq) == NO_PIECE);
              assert(st->capturedPiece == make_piece(~us, PAWN));
          }

          put_piece(st->capturedPiece, capsq); // Restore the captured piece
      }
  }

  // Finally point our state pointer back to the previous state
  st = st->previous;
  --gamePly;

  assert(pos_is_ok());
}
```

undo_move() reverses the effects of do_move().

After this function finishes:
- board[] must match exactly
- bitboards must match exactly
- piece lists must match exactly
- hash keys, castling rights, ep square must match exactly
- evaluation state must match exactly

This is what allows Stockfish to explore:

```
Position → move → deeper search → undo → next move
```

undo_move() reverses a move by:
- flipping side-to-move back
- undoing promotions (piece → pawn)
- undoing castling (king + rook)
- moving the piece back
- restoring captured pieces (including en passant)
- restoring the previous StateInfo snapshot


#### Step-by-step Breakdown

#### 1. Flip Side to Move Back

```cpp
sideToMove = ~sideToMove;
```

#### 2. Special Move Reversal

Undo must handle tricky move types first:
- Promotion
- Castling
- En passant
- Captures

#### 3. Undo Promotion

```cpp
if (type_of(m) == PROMOTION)
{
    remove_piece(pc, to);
    pc = make_piece(us, PAWN);
    put_piece(pc, to);
}
```

Promotion replaced a pawn with a new piece:

```
Pawn disappears → Queen appears
```

Undo must reverse:

```
Queen disappears → Pawn comes back
```

**Why is pc reassigned?**

Because later we still need to move the pawn back to from.

So we convert:

```cpp
pc = Pawn
```

#### 4. Undo Castling

```cpp
if (type_of(m) == CASTLING)
{
    Square rfrom, rto;
    do_castling<false>(us, from, to, rfrom, rto);
}
```

**Castling is special**

Castling moves two pieces:
- King
- Rook

So Stockfish uses a helper:

```cpp
do_castling<false>()
```

Where `<false>` means:

> undo mode

This restores:
- king back to from
- rook back to its original square

#### 5. Undo Normal Moves

```cpp
else
{
    move_piece(pc, to, from);
}
```

For all regular moves:
- Move piece back from destination → origin

This restores the moved piece.


#### 6. Restoring Captures

```cpp
if (st->capturedPiece)
{
    Square capsq = to;
```

If something was captured, Stockfish stored it earlier in:

```cpp
st->capturedPiece
```

So undo checks:
- Was this move a capture?

If yes → restore the captured piece.


**Special Case: En Passant Capture**

```cpp
if (type_of(m) == ENPASSANT)
{
    capsq -= pawn_push(us);
}
```

Why?

In en passant:
- captured pawn is not on to
- it is behind it

#### 7. Restore the Captured Piece

```cpp
put_piece(st->capturedPiece, capsq);
```

This places the captured piece back on the board and updates:
- board[]
- bitboards
- pieceList[]
- pieceCount[]

Undo is complete now.


#### 8. Roll Back State Pointer

```cpp
st = st->previous;
--gamePly;
```

It automatically restores:
- zobrist key
- pawnKey
- materialKey
- castling rights
- ep square
- rule50
- psq score
- check info

Without recomputation.

## 2. Move Generation

### 1. legal

```cpp

/// Position::legal() tests whether a pseudo-legal move is legal

bool Position::legal(Move m) const {

  assert(is_ok(m));

  Color us = sideToMove;
  Square from = from_sq(m);

  assert(color_of(moved_piece(m)) == us);
  assert(piece_on(square<KING>(us)) == make_piece(us, KING));

  // En passant captures are a tricky special case. Because they are rather
  // uncommon, we do it simply by testing whether the king is attacked after
  // the move is made.
  if (type_of(m) == ENPASSANT)
  {
      Square ksq = square<KING>(us);
      Square to = to_sq(m);
      Square capsq = to - pawn_push(us);
      Bitboard occupied = (pieces() ^ from ^ capsq) | to;

      assert(to == ep_square());
      assert(moved_piece(m) == make_piece(us, PAWN));
      assert(piece_on(capsq) == make_piece(~us, PAWN));
      assert(piece_on(to) == NO_PIECE);

      return   !(attacks_bb<  ROOK>(ksq, occupied) & pieces(~us, QUEEN, ROOK))
            && !(attacks_bb<BISHOP>(ksq, occupied) & pieces(~us, QUEEN, BISHOP));
  }
```

Purpose

```cpp
/// Position::legal() tests whether a pseudo-legal move is legal
```

Stockfish generates pseudo-legal moves first:
- piece moves correctly
- ignores king safety

Then legal() filters out moves that are illegal because:
- king is left in check
- pinned piece moved wrongly
- en passant reveals discovered attack

#### 1. Basic Setup

```cpp
Color us = sideToMove;
Square from = from_sq(m);
```

- us = side making the move
- from = origin square of the move

```cpp
assert(color_of(moved_piece(m)) == us);
assert(piece_on(square<KING>(us)) == make_piece(us, KING));
```

These ensure:
- the moving piece belongs to the side to move
- the king exists where expected

These are debugging correctness checks.


#### 2. Special Case 1: En Passant

```cpp
if (type_of(m) == ENPASSANT)
```

En passant is special because the captured pawn is not on the destination square.

Example:

```
White pawn e5 captures d6 en passant
Captured pawn was actually on d5
```

So removing that pawn can suddenly open a file/diagonal and expose the king.

That means:

> An en passant move may be pseudo-legal but illegal because it reveals check.

##### Stockfish’s solution: simulate occupancy

```
Square ksq = square<KING>(us);
Square to = to_sq(m);
Square capsq = to - pawn_push(us);
Bitboard occupied = (pieces() ^ from ^ capsq) | to;
```

This creates a simulated occupancy bitboard showing what the board would look like after the en passant.

Breaking it down:

```cpp
pieces()        // All pieces currently on the board
^ from          // XOR with 'from' → removes our pawn from e4
^ capsq         // XOR with 'capsq' → removes their pawn from d5
| to            // OR with 'to' → adds our pawn to d6
```


So occupied is:

> what the board would look like after en passant

##### Check if king becomes attacked

```cpp
return   !(attacks_bb<ROOK>(ksq, occupied) & pieces(~us, QUEEN, ROOK))
      && !(attacks_bb<BISHOP>(ksq, occupied) & pieces(~us, QUEEN, BISHOP));
```

This checks TWO conditions (both must be true):

- King not attacked by enemy rooks/queens (along ranks/files)
- King not attacked by enemy bishops/queens (along diagonals)

**Check 1: Rook/Queen Attacks**

```cpp
!(attacks_bb<ROOK>(ksq, occupied) & pieces(~us, QUEEN, ROOK))
```

```cpp
attacks_bb<ROOK>(ksq, occupied)
```
**What it does:** Computes **rook attacks from the king's square** using the simulated occupancy.

**Interpretation:** "If there were a rook on the king's square, what squares could it attack?"

**Reverse logic:** "What squares have line-of-sight to the king along ranks/files?"

```cpp
pieces(~us, QUEEN, ROOK)
```

All enemy queens and rooks.

```cpp
attacks_bb<ROOK>(ksq, occupied) & pieces(~us, QUEEN, ROOK)
```
**Intersection:** Are any enemy rooks/queens on squares that have rook-line-of-sight to our king?

If there was any bishop or rook in place of our king, will it see any enemy rook, bishop or queen? If so it means our king will end up in check after this move. 

If intersection is non-empty → function returns false (illegal move).

#### 3. Special Case 2: King Moves

```cpp
// If the moving piece is a king, check whether the destination
// square is attacked by the opponent. Castling moves are checked
// for legality during move generation.

if (type_of(piece_on(from)) == KING)
    return type_of(m) == CASTLING || !(attackers_to(to_sq(m)) & pieces(~us));
```

If the moving piece is the king:
- king cannot move into check

Castling rules are checked during move generation itself. 

#### 4. Non-King Move Legality Check 

```cpp
  // A non-king move is legal if and only if it is not pinned or it
  // is moving along the ray towards or away from the king.
  return   !(pinned_pieces(us) & from)
        ||  aligned(from, to_sq(m), square<KING>(us));
```

This handles legality for all non-king, non-en-passant moves by checking if the move would expose the king to check.

```cpp
Case 1: !(pinned_pieces(us) & from)     // Piece is NOT pinned
   OR
Case 2: aligned(from, to_sq(m), square<KING>(us))  // Move is along pin line
```

**Case 1: Piece is NOT Pinned**

```cpp
Bitboard pinned_pieces(Color c) const;
```
Returns: Bitboard of all our pieces that are pinned to our king.

Bitwise and with `from` gives the intersection, it tells if the moving piece is pinned. 

**Case 2: Move Along Pin Line**

```cpp
aligned(from, to_sq(m), square<KING>(us))
```

Only checked if Case 1 fails (piece IS pinned).

### 2. pseudo_legal

```cpp
/// Position::pseudo_legal() takes a random move and tests whether the move is
/// pseudo legal. It is used to validate moves from TT that can be corrupted
/// due to SMP concurrent access or hash position key aliasing.

bool Position::pseudo_legal(const Move m) const {

  Color us = sideToMove;
  Square from = from_sq(m);
  Square to = to_sq(m);
  Piece pc = moved_piece(m);

  // Use a slower but simpler function for uncommon cases
  if (type_of(m) != NORMAL)
      return MoveList<LEGAL>(*this).contains(m);

  // Is not a promotion, so promotion piece must be empty
  if (promotion_type(m) - KNIGHT != NO_PIECE_TYPE)
      return false;

  // If the 'from' square is not occupied by a piece belonging to the side to
  // move, the move is obviously not legal.
  if (pc == NO_PIECE || color_of(pc) != us)
      return false;

  // The destination square cannot be occupied by a friendly piece
  if (pieces(us) & to)
      return false;

  // Handle the special case of a pawn move
  if (type_of(pc) == PAWN)
  {
      // We have already handled promotion moves, so destination
      // cannot be on the 8th/1st rank.
      if (rank_of(to) == relative_rank(us, RANK_8))
          return false;

      if (   !(attacks_from<PAWN>(from, us) & pieces(~us) & to) // Not a capture
          && !((from + pawn_push(us) == to) && empty(to))       // Not a single push
          && !(   (from + 2 * pawn_push(us) == to)              // Not a double push
               && (rank_of(from) == relative_rank(us, RANK_2))
               && empty(to)
               && empty(to - pawn_push(us))))
          return false;
  }
  else if (!(attacks_from(pc, from) & to))
      return false;

  // Evasions generator already takes care to avoid some kind of illegal moves
  // and legal() relies on this. We therefore have to take care that the same
  // kind of moves are filtered out here.
  if (checkers())
  {
      if (type_of(pc) != KING)
      {
          // Double check? In this case a king move is required
          if (more_than_one(checkers()))
              return false;

          // Our move must be a blocking evasion or a capture of the checking piece
          if (!((between_bb(lsb(checkers()), square<KING>(us)) | checkers()) & to))
              return false;
      }
      // In case of king moves under check we have to remove king so as to catch
      // invalid moves like b1a1 when opposite queen is on c1.
      else if (attackers_to(to, pieces() ^ from) & pieces(~us))
          return false;
  }

  return true;
}
```

**Purpose:** Validate that a move is **pseudo-legal** (follows piece movement rules, but may leave king in check).

**Use case:** Validate moves from **transposition table** that might be corrupted due to:
- Hash collisions (different positions with same key)
- SMP concurrent access (race conditions)
- Memory corruption

**Pseudo-legal vs Legal:**
- **Pseudo-legal:** Piece can physically make the move (ignoring king safety)
- **Legal:** Pseudo-legal AND doesn't leave own king in check


#### Function Structure

1. Extract move information
2. Handle special moves (promotion, castling, en passant) via slow path
3. Basic validation (piece exists, colors match)
4. Validate destination square
5. Validate piece-specific movement rules
6. Handle check evasions
7. Return result

#### 1. Extract Move Information

```cpp
Color us = sideToMove;
Square from = from_sq(m);
Square to = to_sq(m);
Piece pc = moved_piece(m);
```


Standard setup:

- `us`: Whose turn it is
- `from`: Source square
- `to`: Destination square
- `pc`: What piece is moving (from the move encoding or board)


#### 2. Special Move Types (Slow Path)

```cpp
// Use a slower but simpler function for uncommon cases
if (type_of(m) != NORMAL)
    return MoveList<LEGAL>(*this).contains(m);
```

Handle special cases by generating all legal moves:
- `PROMOTION`: Pawn reaching 8th rank
- `ENPASSANT`: En passant capture
- `CASTLING`: Castling

Why slow path?

```cpp
MoveList<LEGAL>(*this)  // Generates ALL legal moves for position
.contains(m)            // Checks if m is in the list
```

This generates every legal move (expensive!) just to validate one move.

**Why do this?**

- Special moves have complex validation rules
- They're rare (~5% of moves)
- Simpler to reuse existing move generation than duplicate logic


**Example:**

```cpp
Move m = make_move(e7, e8, PROMOTION, QUEEN);

type_of(m) = PROMOTION  ✓ Not NORMAL

// Generate all legal moves:
MoveList<LEGAL> moves(*this);  // {e7e8q, e7e8r, e7e8b, e7e8n, Nf6, ...}

// Check if our move is in the list:
return moves.contains(e7e8q);  ✓ true
```

**Performance:** This is acceptable because:

- TT validation is infrequent (only when probe succeeds)
- Special moves are rare
- Correctness > speed for this function

#### 3. Promotion Validation

```cpp
// Is not a promotion, so promotion piece must be empty
if (promotion_type(m) - KNIGHT != NO_PIECE_TYPE)
    return false;
```

What this checks: If move type is NORMAL, there should be no promotion piece encoded. Its subtracting KNIGHT, because promotion pieces are encoded as KNIGHT - 2. 

#### 4. Basic Piece Validation

```cpp
// If the 'from' square is not occupied by a piece belonging to the side to
// move, the move is obviously not legal.
if (pc == NO_PIECE || color_of(pc) != us)
    return false;
```

##### Check 1: Piece exists

```cpp
pc == NO_PIECE
```

**Example of failure:**

```
Board:
  4  . . . . . . . .  ← e4 is empty
  
Move: e4-e5

pc = piece_on(e4) = NO_PIECE  ✗

return false  // Can't move nothing!
```

##### Check 2: Correct color

```cpp
color_of(pc) != us
```

**Example of failure:**
```
Board:
  4  . . . . ● . . .  ← e4 has black pawn
  
Side to move: WHITE
Move: e4-e5

pc = B_PAWN
color_of(B_PAWN) = BLACK
BLACK != WHITE  ✗

return false  // Can't move opponent's piece!
```

**Why these can fail:**

- Hash collision: Different position mapped to same TT entry
- Concurrent access: Position changed while reading TT entry
- Move encoding corruption

#### 5. Destination Square Validation

```cpp
// The destination square cannot be occupied by a friendly piece
if (pieces(us) & to)
    return false;
```

Can't capture our own pieces:

#### 6. Pawn Movement Validation

```cpp
if (type_of(pc) == PAWN)
{
    // We have already handled promotion moves, so destination
    // cannot be on the 8th/1st rank.
    if (rank_of(to) == relative_rank(us, RANK_8))
        return false;
```

##### Check 1: Not on promotion rank

Since promotions were handled earlier (slow path), a NORMAL pawn move can't end on the 8th rank.

```cpp
relative_rank(WHITE, RANK_8) = RANK_8 (8th rank for white)
relative_rank(BLACK, RANK_8) = RANK_1 (1st rank for black, which is black's 8th)

// Example:
us = WHITE
to = e8
rank_of(e8) = RANK_8
RANK_8 == RANK_8  ✗

return false  // Pawn to 8th rank must be promotion!
```

##### Pawn Movement Rules

```cpp
if (   !(attacks_from<PAWN>(from, us) & pieces(~us) & to) // Not a capture
    && !((from + pawn_push(us) == to) && empty(to))       // Not a single push
    && !(   (from + 2 * pawn_push(us) == to)              // Not a double push
         && (rank_of(from) == relative_rank(us, RANK_2))
         && empty(to)
         && empty(to - pawn_push(us))))
    return false;
```

This is a complex condition: Move is valid if ANY of these is true:
- Pawn capture
- Single push
- Double push

If NONE are true → invalid.

**Part 1: Pawn Capture**

```cpp
!(attacks_from<PAWN>(from, us) & pieces(~us) & to)
```

Check: Is this a valid pawn capture?

```cpp
attacks_from<PAWN>(from, us)  // Diagonal attacks from source
& pieces(~us)                 // Enemy pieces
& to                          // Destination square
```

Example - Valid capture:
```cpp
  5  . . . ○ . . . .  ← d5: black pawn
  4  . . . . ● . . .  ← e4: white pawn
  
Move: e4xd5

attacks_from<PAWN>(e4, WHITE) = {d5, f5}
pieces(BLACK) = {d5, ...}
to = d5

{d5, f5} & {d5, ...} & d5 = {d5}  ✓ Non-empty (valid capture)
!{d5} = false

// This part fails, but that's OK - we check other parts
```

**Part 2: Single Push**

```cpp
!((from + pawn_push(us) == to) && empty(to))
```

Check: Is this a valid single square forward move?

```cpp
pawn_push(WHITE) = 8  (NORTH)
pawn_push(BLACK) = -8 (SOUTH)

from + pawn_push(us) == to  // Is destination one square forward?
&& empty(to)                // Is destination empty?
```

Example - Valid single push:
```cpp
  5  . . . . . . . .  ← e5: empty
  4  . . . . ● . . .  ← e4: white pawn
  
Move: e4-e5

from + pawn_push(WHITE) = e4 + 8 = e5
e5 == e5  ✓
empty(e5) = true  ✓

(true && true) = true
!(true) = false

// This part fails, but that's OK (valid move)
```

**Part 3: Double Push**

```cpp
!(   (from + 2 * pawn_push(us) == to)              // Two squares forward
  && (rank_of(from) == relative_rank(us, RANK_2))  // From starting rank
  && empty(to)                                      // Destination empty
  && empty(to - pawn_push(us)))                    // Square in between empty
```

#### 7. Non-Pawn Movement Validation

```cpp
else if (!(attacks_from(pc, from) & to))
    return false;
```

For knights, bishops, rooks, queens, kings:

example - Valid knight move:

Move: Nd3-e4

```cpp

attacks_from(pc, from)  // Bitboard of squares piece can attack
& to                    // Is destination in attack set?

attacks_from(W_KNIGHT, d3) & e4 = {e4}  ✓ Non-empty
!{e5} = false

// Don't return false, continue checking...
```

#### 8. Check Evasion Validation

```cpp
if (checkers())
{
```

If we're in check, additional restrictions apply:

```cpp
if (type_of(pc) != KING)
{
```

It means the piece we moved is not king, even though we were in check.

##### 1. Double Check → Must Move King

```cpp
    // Double check? In this case a king move is required
    if (more_than_one(checkers()))
        return false;
```

```cpp
checkers()  // Bitboard of pieces giving check
more_than_one(checkers())  // Are there 2+ checkers?
```

If its double check and king hasn't moved, we can return false.

##### 2. Single Check → Block or Capture

```cpp
    // Our move must be a blocking evasion or a capture of the checking piece
    if (!((between_bb(lsb(checkers()), square<KING>(us)) | checkers()) & to))
        return false;
}
```

In single check, move must EITHER:
- Block the check (move to a square between attacker and king)
- Capture the checking piece

```cpp
(between_bb(lsb(checkers()), square<KING>(us))  // Squares between checker and king
| checkers())                                   // OR the checker's square itself
& to                                           // Is destination one of these?
```
It means we should move to a square in-between king and checker or capture the checker. 

Since we know it can't be double check, we can safely extract checker by `lsb(checkers())`

##### 3. King Moves Under Check

```cpp
// In case of king moves under check we have to remove king so as to catch
// invalid moves like b1a1 when opposite queen is on c1.
else if (attackers_to(to, pieces() ^ from) & pieces(~us))
    return false;
```

**Special handling for king moves when in check:**

```cpp
pieces() ^ from  // Occupancy with king removed from current square
```

**Why remove king?** To detect attacks "through" the king's current square.

**Example - Invalid king move:**

```
  2  . . . . . . . .
  1  . K . q . . . .  ← b1: king, d1: black queen
     a b c d e f g h
     ╰───╯
     King trying to move along queen's attack ray

Move: Kb1-a1


Without removing king:
attackers_to(a1, pieces()) queen on d1 doesn't attack b1 and a1, since its blocked by our king.
```

#### 9. All Tests passed

```cpp
  return true;
```

### 3. attackers_to

`attackers_to(sq)` answers the question:

> “Which pieces (of either side) are currently attacking square sq?”

It returns a bitboard containing all attackers.

**Function Signatures**

```cpp
Bitboard attackers_to(Square s) const;
Bitboard attackers_to(Square s, Bitboard occupied) const;
```

- `attackers_to(s)`: attackers using current board occupancy
- `attackers_to(s, occupied)`: attackers assuming a custom occupancy mask

The second one is used in tricky cases like:
- en passant legality
- discovered attacks
- move simulation without actually making the move

```cpp
inline Bitboard Position::attackers_to(Square s) const {
  return attackers_to(s, byTypeBB[ALL_PIECES]);
}
```

```cpp
/// Position::attackers_to() computes a bitboard of all pieces which attack a
/// given square. Slider attacks use the occupied bitboard to indicate occupancy.

Bitboard Position::attackers_to(Square s, Bitboard occupied) const {

  return  (attacks_from<PAWN>(s, BLACK)    & pieces(WHITE, PAWN))
        | (attacks_from<PAWN>(s, WHITE)    & pieces(BLACK, PAWN))
        | (attacks_from<KNIGHT>(s)         & pieces(KNIGHT))
        | (attacks_bb<ROOK  >(s, occupied) & pieces(ROOK,   QUEEN))
        | (attacks_bb<BISHOP>(s, occupied) & pieces(BISHOP, QUEEN))
        | (attacks_from<KING>(s)           & pieces(KING));
}
```

Attackers come from 6 piece types:
- pawns
- knights
- bishops
- rooks
- queens
- king

So conceptually:

```cpp
attackers =
    pawn_attackers +
    knight_attackers +
    bishop_attackers +
    rook_attackers +
    queen_attackers +
    king_attackers;
```

#### 1. Pawn Attackers

Pawns are asymmetric:
white pawns attack upward, black pawns downward.

So Stockfish reverses the logic:

```cpp
(attacks_from<PAWN>(s, BLACK) & pieces(WHITE, PAWN))
```

To answer which white pawns attack the square s, stockfish asks the reverse questions: 

```cpp
attacks_from<PAWN>(s, BLACK)
```
If a black pawn was present in square s, which squares would it attack? 

```cpp
pieces(WHITE, PAWN)
```

This returns a bitboard with only squares containing white pawns, so the final result contains only those squares which are under attack by a hypothetical black pawn in square s, bitwise and white pawns. So final bitboard will give us all white pawns which can attack this square s. 

`attacks_from<PAWN>` uses `StepAttacksBB` which is a map of precomputed attack squares. 

```cpp
template<>
inline Bitboard Position::attacks_from<PAWN>(Square s, Color c) const {
  return StepAttacksBB[make_piece(c, PAWN)][s];
}
```


**Examples:**

```cpp
StepAttacksBB[W_PAWN][e4]  → Bitboard with d5, f5 set (white pawn attacks)
StepAttacksBB[B_PAWN][e5]  → Bitboard with d4, f4 set (black pawn attacks)
StepAttacksBB[W_KNIGHT][e4] → Bitboard with d2, f2, c3, g3, c5, g5, d6, f6
StepAttacksBB[W_KING][e1]  → Bitboard with d1, f1, d2, e2, f2
```

Similar logic is used to find all black pawns attacking the square s

```cpp
(attacks_from<PAWN>(s, WHITE) & pieces(BLACK, PAWN))
```

#### 2. Knight Attacks 

```cpp
(attacks_from<KNIGHT>(s)         & pieces(KNIGHT))
```

Knights are color-independent (same attack pattern for white/black).

```cpp
attacks_from<KNIGHT>(s)  // All squares a knight on `s` could attack
pieces(KNIGHT)           // All knights (both colors)
```

This is again a reverse lookup with same logic. 

In this case, the implementation of `attacks_from` is 

```cpp
template<PieceType Pt>
inline Bitboard Position::attacks_from(Square s) const {
  return  Pt == BISHOP || Pt == ROOK ? attacks_bb<Pt>(s, byTypeBB[ALL_PIECES])
        : Pt == QUEEN  ? attacks_from<ROOK>(s) | attacks_from<BISHOP>(s)
        : StepAttacksBB[Pt][s];
}
```

For knight also its just `StepAttacksBB[Pt][s]` after stripping all the polymorphic code

#### 3. Sliding Attacks (Rook/Bishop/Queen, Occupancy-Dependent)

```cpp
template<PieceType Pt>
inline Bitboard attacks_bb(Square s, Bitboard occupied) {

  extern Bitboard* RookAttacks[SQUARE_NB];
  extern Bitboard* BishopAttacks[SQUARE_NB];

  return (Pt == ROOK ? RookAttacks : BishopAttacks)[s][magic_index<Pt>(s, occupied)];
}
```

It uses the precomputed magic bitboards to get the attack bitboard, logic is similar for rook and bishop, but they have different precomputed tables. 

For queen, the attack bitboard is just bitwise OR of rook and bishop

```cpp
Pt == QUEEN  ? attacks_from<ROOK>(s) | attacks_from<BISHOP>(s)
```





