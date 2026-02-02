---
title:  "Move Generation"
date:   2026-02-01
draft: false
categories: ["chess engines"]
tags: ["move generation"]
author: Sanketh
---

# Move Generation

Move generation is one of the core responsibilities of a chess engine: given a `Position`, the engine must efficiently produce all possible moves available to the side to move.

In Stockfish, move generation is designed to be extremely fast because it is executed millions of times during search. Instead of always generating every legal move, Stockfish generates different categories of moves depending on the search phase (captures only, quiet moves, evasions under check, etc.).

The `movegen.h` header defines the public interface for this system:
- `GenType` specifies what kind of moves to generate
- `ExtMove` stores a move along with a heuristic score for move ordering
- `generate<T>()` produces move lists using compile-time specialization
- `MoveList<T>` provides a lightweight wrapper for iteration and convenience

This module is the bridge between the board representation (`Position`) and the search algorithm, supplying the raw move candidates explored by alpha-beta.

## GenType

```cpp
enum GenType {
  CAPTURES,
  QUIETS,
  QUIET_CHECKS,
  EVASIONS,
  NON_EVASIONS,
  LEGAL
};
```

Stockfish does not always generate all legal moves at once. Instead, it generates only the type of moves needed in a given search context.

### Meaning of Each Type

- CAPTURES:
Generate only capturing moves (including en-passant).
Used heavily in quiescence search to resolve tactical positions.

- QUIETS:
Generate only non-capturing moves (normal positional moves).
Used in the main search after captures are considered.

- QUIET_CHECKS:
Generate quiet moves that give check.
Useful in quiescence extensions, since checks can drastically change evaluation.

- EVASIONS:
Generate only moves that escape check.
When the king is in check, only evasions are legal.

- NON_EVASIONS:
Generate all moves when not in check:
captures + quiets (the normal move set).

- LEGAL:
Generate the complete list of fully legal moves, filtering out illegal ones
(e.g., moves leaving the king in check).

## ExtMove

```cpp
struct ExtMove {
  Move move;
  Value value;

  operator Move() const { return move; }
  void operator=(Move m) { move = m; }
};
```

ExtMove is an “extended move” structure used during move generation. Both `Move` and `Value` are enums.

**Fields**
- Move move:
The actual encoded chess move (16-bit representation).
- Value value:
A score used for move ordering (captures, killer moves, history heuristic, etc.).

Stockfish generates moves along with a priority score so they can be sorted and searched in the best order.


## MoveList

```cpp
/// The MoveList struct is a simple wrapper around generate(). It sometimes comes
/// in handy to use this class instead of the low level generate() function.
template<GenType T>
struct MoveList {

  explicit MoveList(const Position& pos) : last(generate<T>(pos, moveList)) {}
  const ExtMove* begin() const { return moveList; }
  const ExtMove* end() const { return last; }
  size_t size() const { return last - moveList; }
  bool contains(Move move) const {
    for (const auto& m : *this) if (m == move) return true;
    return false;
  }

private:
  ExtMove moveList[MAX_MOVES], *last;
};
```

`MoveList` is a lightweight helper class that wraps Stockfish’s low-level `generate()` function.

Key Idea
- Automatically generates all moves of type T (captures, quiets, evasions, etc.)
- Stores them in a fixed-size array for fast iteration

```cpp
private:
  ExtMove moveList[MAX_MOVES], *last;
```

- `moveList` is an array that stores generated moves
- `last` is a pointer to an ExtMove


### Constructor

```cpp
explicit MoveList(const Position& pos)
  : last(generate<T>(pos, moveList)) {}
```

This is called a constructor initializer list.

It means:
> Before the constructor body runs, initialize last with the return value of generate<T>().

Equivalent longer form:

```cpp
explicit MoveList(const Position& pos) {
    last = generate<T>(pos, moveList);
}
```

- Calls `generate<T>()` immediately
- `last` points to the end of the generated move list

### Iteration Support

```cpp
  const ExtMove* begin() const { return moveList; }
  const ExtMove* end() const { return last; }
```

Makes MoveList usable in range-based loops:

```cpp
for (const auto& m : MoveList<CAPTURES>(pos))
```

### Utility Methods

```cpp
  size_t size() const { return last - moveList; }
  bool contains(Move move) const {
    for (const auto& m : *this) if (m == move) return true;
    return false;
  }
```

- `size()` → number of moves generated
- `contains(move)` → checks if a move exists in the list (used for validation)

### Storage

```cpp
ExtMove moveList[MAX_MOVES];
ExtMove* last;
```

- Uses a static array (no heap allocation)
- Efficient and search-friendly

## generate_pawn_moves

Pawn moves are special in chess because they have unique movement rules:

- Move forward 1 square (or 2 from starting rank)
- Capture diagonally
- Promote when reaching the 8th rank
- En passant capture

This function generates all pawn moves for one side, depending on the requested move category:
- quiet pushes
- captures
- promotions
- en passant
- evasions (moves to escape check)
- quiet checks

The function is templated by:

- `Color Us`: Which side is moving (WHITE or BLACK)
- `GenType Type`: What kind of moves to generate (CAPTURES, QUIETS, EVASIONS, etc.)

The `target` parameter filters which destination squares are valid (used for check evasions, captures only, etc.).

Depending on `GenType`, it restricts pawn moves to only squares we care about:
- CAPTURES → target = squares containing capturable enemy pieces
- EVASIONS → target = squares that block/capture the checking piece
- QUIETS / QUIET_CHECKS → target = squares where quiet pawn pushes are allowed


```cpp
template<Color Us, GenType Type>
ExtMove* generate_pawn_moves(const Position& pos, ExtMove* moveList, Bitboard target) {
```

**Function template:** Generate pawn moves for side `Us`. `moveList` is a pointer where we'll write the moves, and we return the updated pointer.

### Initialization

```cpp
    // Compute our parametrized parameters at compile time, named according to
    // the point of view of white side.
    const Color    Them     = (Us == WHITE ? BLACK      : WHITE);
    const Bitboard TRank8BB = (Us == WHITE ? Rank8BB    : Rank1BB); // Target promotion rank: 8th rank for WHITE, 1st rank for BLACK (where pawns promote)
    const Bitboard TRank7BB = (Us == WHITE ? Rank7BB    : Rank2BB); // Pre-promotion rank: 7th rank for WHITE, 2nd rank for BLACK (pawns here will promote next move).
    const Bitboard TRank3BB = (Us == WHITE ? Rank3BB    : Rank6BB); // Double-push landing rank: When a pawn moves 2 squares from its starting position, it lands here (3rd rank for WHITE, 6th for BLACK).
    const Square   Up       = (Us == WHITE ? NORTH      : SOUTH);
    const Square   Right    = (Us == WHITE ? NORTH_EAST : SOUTH_WEST);
    const Square   Left     = (Us == WHITE ? NORTH_WEST : SOUTH_EAST);
```

```cpp
    Bitboard emptySquares;
```

Declare variable: Will hold bitboard of empty squares (used for pawn pushes).

```cpp
    Bitboard pawnsOn7    = pos.pieces(Us, PAWN) &  TRank7BB;
```

**Pawns about to promote:** Get all our pawns that are on the 7th rank (about to promote on next move).

```cpp
    Bitboard pawnsNotOn7 = pos.pieces(Us, PAWN) & ~TRank7BB;
```

**Regular pawns:** Get all our pawns NOT on the 7th rank (won't promote this move).

```cpp
Bitboard enemies = (Type == EVASIONS ? pos.pieces(Them) & target:
                        Type == CAPTURES ? target : pos.pieces(Them));
```

Enemy pieces to capture:

### Case 1: Type == NON_EVASIONS (normal movegen)

```cpp
enemies = pos.pieces(Them);
```

Meaning:
- We are not in check
- Captures can be against any enemy piece

### Case 2: Type == CAPTURES

```cpp
enemies = target;
```

Here, target is already prepared by the caller.

For captures-only generation, Stockfish passes:

```cpp
target = pos.pieces(Them);
```

(or sometimes only “good captures”, etc.)

So it says:
- Don’t recompute enemy set
- Just trust the filtered capture target

### Case 3: Type == EVASIONS (king is in check)

```cpp
enemies = pos.pieces(Them) & target;
```

When in check, you cannot capture any random enemy piece.

You are only allowed to:
- capture the checking piece, OR
- block the check, OR
- move king away

So target here is:
- squares that resolve the check

Example:
- Black queen is giving check on e2
- Then:

```cpp
target = {e2}  (only checking piece square)
```

Now:
```cpp
pos.pieces(Them) = all black pieces
target = only squares that stop check
```
```cpp
    // Single and double pawn pushes, no promotions
    if (Type != CAPTURES)
    {
        emptySquares = (Type == QUIETS || Type == QUIET_CHECKS ? target : ~pos.pieces());

        Bitboard b1 = shift<Up>(pawnsNotOn7)   & emptySquares;
        Bitboard b2 = shift<Up>(b1 & TRank3BB) & emptySquares;
```

### Non-capture moves section

Skip this if we're only generating captures.

```cpp
    // Single and double pawn pushes, no promotions
    if (Type != CAPTURES)
    {
        emptySquares = (Type == QUIETS || Type == QUIET_CHECKS ? target : ~pos.pieces());

        Bitboard b1 = shift<Up>(pawnsNotOn7)   & emptySquares;
        Bitboard b2 = shift<Up>(b1 & TRank3BB) & emptySquares;
```

**Define empty squares:**

- If generating only quiet moves or quiet checks: Use `target` (pre-filtered valid destinations)
- Otherwise: All empty squares on the board (`~pos.pieces()` inverts the occupied bitboard)

```cpp
        Bitboard b1 = shift<Up>(pawnsNotOn7)   & emptySquares;
```

**Single pawn pushes:** Shift all non-promoting pawns forward by one square, keep only those landing on empty squares.

Example (WHITE):
- Pawns on rank 2,3,4,5,6: Shift NORTH
- Filter to only empty destination squares

```cpp
        Bitboard b2 = shift<Up>(b1 & TRank3BB) & emptySquares;
```

**Double pawn pushes:**

- Take pawns that just pushed to rank 3 (b1 & TRank3BB)
- These pawns started on rank 2 (starting position)
- Push them forward again
- Keep only those landing on empty squares

This ensures pawns can only double-push from their starting rank.

```cpp
        if (Type == EVASIONS) // Consider only blocking squares
        {
            b1 &= target;
            b2 &= target;
        }
```

**Filter for evasions:** If we're in check and generating evasion moves, only keep pawn pushes that land on `target` squares (blocking squares or capturing the checker).

### Quiet check moves

Generate pawn pushes that give check to the enemy king.

```cpp
        if (Type == QUIET_CHECKS)
        {
            Square ksq = pos.square<KING>(Them);

            b1 &= pos.attacks_from<PAWN>(ksq, Them);
            b2 &= pos.attacks_from<PAWN>(ksq, Them);
```

```cpp
            Square ksq = pos.square<KING>(Them);
```

**Get enemy king square:** We need to know where the enemy king is to determine if a pawn push gives check.

```cpp
            b1 &= pos.attacks_from<PAWN>(ksq, Them);
            b2 &= pos.attacks_from<PAWN>(ksq, Them);
```

**Direct pawn checks:** Keep only pawn pushes that land on squares where a pawn attacks the enemy king.

`attacks_from<PAWN>(ksq, Them)` returns squares where an enemy pawn would need to be to attack the king. If our pawn pushes there, it gives check.

This is the reverse lookup trick used throughout the stockfish, `attacks_from<PAWN>(sq, BLACK)` is same as `attacks_to<PAWN>(sq, WHITE)`

### Discovered check candidates

```cpp
            // Add pawn pushes which give discovered check. This is possible only
            // if the pawn is not on the same file as the enemy king, because we
            // don't generate captures. Note that a possible discovery check
            // promotion has been already generated amongst the captures.
            Bitboard dcCandidates = pos.discovered_check_candidates();
```

Get pieces that, if they move, would reveal a check from a piece behind them (e.g., pawn moves, revealing a rook/bishop attack on the king).

It uses `blockersForKing` to quickly calculate it, our pieces which are blockers for opponent's king are discovered check candidates. 

```cpp
inline Bitboard Position::discovered_check_candidates() const {
  return st->blockersForKing[~sideToMove] & pieces(sideToMove);
}
```

```cpp
            if (pawnsNotOn7 & dcCandidates)
            {
```

If we have pawns (not on 7th rank) that can give discovered checks: Process them.

```cpp
                Bitboard dc1 = shift<Up>(pawnsNotOn7 & dcCandidates) & emptySquares & ~file_bb(ksq);
```

**Single-push discovered checks:**

- Shift discovered-check pawns forward
- Must land on empty squares
- Must NOT be on the same file as the king (~file_bb(ksq)) - if on the same file, moving wouldn't discover 

```cpp
                Bitboard dc2 = shift<Up>(dc1 & TRank3BB) & emptySquares;
```

**Double-push discovered checks:** Same logic as regular double pushes, but for discovered-check candidates.

```cpp
                b1 |= dc1;
                b2 |= dc2;
            }
        }
```

**Add discovered checks to move lists:** Merge discovered check moves into our existing pawn push bitboards.

### Adding Non captures to moveList

```cpp
        while (b1)
        {
            Square to = pop_lsb(&b1);
            *moveList++ = make_move(to - Up, to);
        }
```

**Generate single-push moves:**

- `pop_lsb(&b1)`: Extract the least significant bit (lowest square) from b1 and remove it
- `to - Up`: The origin square (one square back from destination)
- `*moveList++ = ...`: Write the move and advance the pointer

```cpp
        while (b2)
        {
            Square to = pop_lsb(&b2);
            *moveList++ = make_move(to - Up - Up, to);
        }
    }
```

**Generate double-push moves**: Origin is two squares back (`to - Up - Up`).

### Promotion moves section

```cpp
    // Promotions and underpromotions
    if (pawnsOn7 && (Type != EVASIONS || (target & TRank8BB)))
    {
```

- Only if we have pawns on the 7th rank
- Skip if generating evasions AND the 8th rank isn't in target (can't promote to block/capture)

```cpp
        if (Type == CAPTURES)
            emptySquares = ~pos.pieces();
```

**Empty squares for promotion pushes**: If only generating captures, we still need to know empty squares for promotion pushes (which aren't captures but might be needed).

```cpp
        if (Type == EVASIONS)
            emptySquares &= target;
```

**Filter empty squares for evasions**: Only promotion pushes landing on `target` squares.

```cpp
        Bitboard b1 = shift<Right>(pawnsOn7) & enemies;
        Bitboard b2 = shift<Left >(pawnsOn7) & enemies;
        Bitboard b3 = shift<Up   >(pawnsOn7) & emptySquares;
```

Three types of promotions:
- `b1`: Promote by capturing right diagonal
- `b2`: Promote by capturing left diagonal
- `b3`: Promote by pushing forward (no capture)

```cpp
        Square ksq = pos.square<KING>(Them);
```

**Get enemy king square**: Needed for the promotion move generator to determine if promotions give check.

```cpp
        while (b1)
            moveList = make_promotions<Type, Right>(moveList, pop_lsb(&b1), ksq);

        while (b2)
            moveList = make_promotions<Type, Left >(moveList, pop_lsb(&b2), ksq);

        while (b3)
            moveList = make_promotions<Type, Up   >(moveList, pop_lsb(&b3), ksq);
    }
```

**Generate all promotions**: For each promotion square, `make_promotions()` generates 4 moves (Queen, Rook, Bishop, Knight) or filters based on Type. Returns the updated moveList pointer.


### Regular captures section

```cpp
    // Standard and en-passant captures
    if (Type == CAPTURES || Type == EVASIONS || Type == NON_EVASIONS)
    {
```

Generate non-promotion captures (we already handled promotion captures above).

```cpp
        Bitboard b1 = shift<Right>(pawnsNotOn7) & enemies;
        Bitboard b2 = shift<Left >(pawnsNotOn7) & enemies;
```


Diagonal captures:
- `b1`: Pawns that can capture to the right
- `b2:` Pawns that can capture to the left

```cpp
        while (b1)
        {
            Square to = pop_lsb(&b1);
            *moveList++ = make_move(to - Right, to);
        }

        while (b2)
        {
            Square to = pop_lsb(&b2);
            *moveList++ = make_move(to - Left, to);
        }
```

**Generate capture moves**: Origin is one diagonal square back.

```cpp
        if (pos.ep_square() != SQ_NONE)
        {
```

Remember `epSquare` is set in `do_move` if an en-passant oppurtunity is present. 

```cpp
            assert(rank_of(pos.ep_square()) == relative_rank(Us, RANK_6));
```

**Verify en passant rank**: En passant square should be on rank 6 (from our perspective). This is a sanity check.

```cpp
            // An en passant capture can be an evasion only if the checking piece
            // is the double pushed pawn and so is in the target. Otherwise this
            // is a discovery check and we are forced to do otherwise.
            if (Type == EVASIONS && !(target & (pos.ep_square() - Up)))
                return moveList;
```

En passant evasion check:

- If generating evasions (we're in check)
- The en passant capture can only help if the checking piece is the pawn that just double-pushed
- That pawn is at `ep_square() - Up` (one square behind the en passant square)
- If that square isn't in `target`, en passant won't help, so skip it

```cpp
            b1 = pawnsNotOn7 & pos.attacks_from<PAWN>(pos.ep_square(), Them);
```

**Find pawns that can en passant**: Get our pawns that can attack the en passant square (as if it were an enemy pawn).

This is the reverse lookup trick again, it works because `epSquare` is the square our pawn moves to after en-passant capture. If an enemy pawn from that location can attack any of our pawn, then en-passant is possible.

```cpp
            assert(b1);
```

**Sanity check**: There should always be at least one pawn that can capture en passant (otherwise the en passant square wouldn't be set).

```cpp
            while (b1)
                *moveList++ = make<ENPASSANT>(pop_lsb(&b1), pos.ep_square());
        }
    }
```


**Generate en passant moves**: Create special ENPASSANT move type for each pawn that can capture.

```cpp
    return moveList;
}
```


**Return updated pointer**: The caller uses this to know where the next moves should be written.

Summary
The function generates pawn moves in this order:

1. Single and double pushes (non-promoting pawns)
2. Promotions (pawns on 7th rank, with or without capture)
3. Regular captures (non-promoting pawns)
4. En passant (special capture)


## shift

```cpp
/// shift() moves a bitboard one step along direction D. Mainly for pawns

template<Square D>
inline Bitboard shift(Bitboard b) {
  return  D == NORTH      ?  b             << 8 : D == SOUTH      ?  b             >> 8
        : D == NORTH_EAST ? (b & ~FileHBB) << 9 : D == SOUTH_EAST ? (b & ~FileHBB) >> 7
        : D == NORTH_WEST ? (b & ~FileABB) << 7 : D == SOUTH_WEST ? (b & ~FileABB) >> 9
        : 0;
}
```

shift() = move a bitboard one square in some direction

A bitboard is a 64-bit integer where each bit is a square.

This function shifts those bits to simulate piece movement (mainly pawns).

**How it works**

```cpp
shift<NORTH>(b)  -> b << 8
```

Moving one rank up = shift left by 8 bits.

```cpp
shift<SOUTH>(b)  -> b >> 8
```

Moving one rank down = shift right by 8 bits.


**Diagonals (pawn captures)**

```cpp
shift<NORTH_EAST>(b) -> (b & ~FileHBB) << 9
```

- Move up + right = << 9
- Mask out File H first so pieces don’t wrap from h-file to a-file.

```cpp
shift<NORTH_WEST>(b) -> (b & ~FileABB) << 7
```

- Move up + left = << 7
- Mask out File A to prevent wraparound.

Same logic for south-east / south-west.

## make_promotions

```cpp
  template<GenType Type, Square D>
  ExtMove* make_promotions(ExtMove* moveList, Square to, Square ksq) {

    if (Type == CAPTURES || Type == EVASIONS || Type == NON_EVASIONS)
        *moveList++ = make<PROMOTION>(to - D, to, QUEEN);

    if (Type == QUIETS || Type == EVASIONS || Type == NON_EVASIONS)
    {
        *moveList++ = make<PROMOTION>(to - D, to, ROOK);
        *moveList++ = make<PROMOTION>(to - D, to, BISHOP);
        *moveList++ = make<PROMOTION>(to - D, to, KNIGHT);
    }

    // Knight promotion is the only promotion that can give a direct check
    // that's not already included in the queen promotion.
    if (Type == QUIET_CHECKS && (StepAttacksBB[W_KNIGHT][to] & ksq))
        *moveList++ = make<PROMOTION>(to - D, to, KNIGHT);
    else
        (void)ksq; // Silence a warning under MSVC

    return moveList;
  }
```

This function generates all promotion moves for a single pawn that's promoting. A pawn can promote to 4 different pieces (Queen, Rook, Bishop, Knight), and this function decides which promotions to generate based on the `Type` parameter.

The `D` template parameter indicates the direction the pawn moved to promote (Up, Right, or Left - i.e., push forward, capture right diagonal, or capture left diagonal).

### Function template:

```cpp
template<GenType Type, Square D>
ExtMove* make_promotions(ExtMove* moveList, Square to, Square ksq) {
```

- `Type`: What kind of moves to generate (CAPTURES, QUIETS, etc.)
- `D`: Direction of promotion (Up = push, Right/Left = capture)
- `to`: Destination square (the promotion square on rank 8/1)
- `ksq`: Enemy king square (needed to check if knight promotion gives check)
- Returns: Updated moveList pointer

```cpp
if (Type == CAPTURES || Type == EVASIONS || Type == NON_EVASIONS)
    *moveList++ = make<PROMOTION>(to - D, to, QUEEN);
```

**Queen promotion (when capturing or all moves):**

- Generate queen promotion if we're generating captures, evasions, or all moves
- `to - D`: Origin square (one square back in direction D)
  - If` D = Up`: to - Up (one square behind)
  - If `D = Right`: to - Right (one square down-left from promotion square)
  - If` D = Left`: to - Left (one square down-right from promotion square)
- Queen promotion is included for captures because:
  - If promotion was by capture (`D = Right` or `Left`), it's a capturing move
  - Queen is the most valuable piece, so always relevant for captures

### Underpromotions section

```cpp
if (Type == QUIETS || Type == EVASIONS || Type == NON_EVASIONS)
    {
```

Generate promotions to pieces other than Queen.

These are considered "quiet" in the sense that:

- They're usually not tactically forcing (Queen is almost always better)
- But they might be needed in special positions (avoiding stalemate, giving check, etc.)

```cpp
    *moveList++ = make<PROMOTION>(to - D, to, ROOK);
    *moveList++ = make<PROMOTION>(to - D, to, BISHOP);
    *moveList++ = make<PROMOTION>(to - D, to, KNIGHT);
    }
```

**Generate Rook, Bishop, Knight promotions**: Create all three underpromotions.
These are included when:
- `QUIETS`: Generating all quiet moves
- `EVASIONS`: In check, might need specific piece to block/capture
- `NON_EVASIONS`: Generating all legal moves (not in check)

```cpp
    // Knight promotion is the only promotion that can give a direct check
    // that's not already included in the queen promotion.
if (Type == QUIET_CHECKS && (StepAttacksBB[W_KNIGHT][to] & ksq))
    *moveList++ = make<PROMOTION>(to - D, to, KNIGHT);
```

**Special case: Knight promotion giving check**:

When generating only quiet checks (`QUIET_CHECKS`):
- Queen promotions are NOT generated (already handled in capture promotions)
- But knight can give check in ways a queen cannot!

**Why knight is special:**
- Queen attacks all squares a rook and bishop attack
- But Queen does NOT attack all squares a knight attacks (knight moves in L-shape)
- So knight promotion might give check when queen promotion wouldn't

```cpp
else
    (void)ksq; // Silence a warning under MSVC
```

### Compiler warning suppression:

- If we're not generating `QUIET_CHECKS`, the `ksq` parameter is unused
- Microsoft Visual C++ compiler warns about unused parameters
- `(void)ksq` tells the compiler "I know this is unused, it's intentional"