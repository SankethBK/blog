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

