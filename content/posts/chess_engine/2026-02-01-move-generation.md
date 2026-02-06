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

## generate_moves

This function generates moves for a specific piece type (Knight, Bishop, Rook, or Queen - NOT King or Pawn, which have their own special generators).

The function is templated by:
- `Pt`: The piece type (KNIGHT, BISHOP, ROOK, or QUEEN)
- `Checks`: Whether we're only generating moves that give check

The `target` parameter filters which destination squares are valid (for captures only, evasions, etc.).

```cpp
  template<PieceType Pt, bool Checks>
  ExtMove* generate_moves(const Position& pos, ExtMove* moveList, Color us,
                          Bitboard target) {

    assert(Pt != KING && Pt != PAWN);

    const Square* pl = pos.squares<Pt>(us);

    for (Square from = *pl; from != SQ_NONE; from = *++pl)
    {
        if (Checks)
        {
            if (    (Pt == BISHOP || Pt == ROOK || Pt == QUEEN)
                && !(PseudoAttacks[Pt][from] & target & pos.check_squares(Pt)))
                continue;

            if (pos.discovered_check_candidates() & from)
                continue;
        }

        Bitboard b = pos.attacks_from<Pt>(from) & target;

        if (Checks)
            b &= pos.check_squares(Pt);

        while (b)
            *moveList++ = make_move(from, pop_lsb(&b));
    }

    return moveList;
  }
```

### Function template:

- `Pt`: Piece type to generate moves for
- `Checks`: If `true`, only generate moves that give check
- `us`: Which color is moving
- `target`: Bitboard of valid destination squares
- Returns: Updated moveList pointer

```cpp
assert(Pt != KING && Pt != PAWN);
```

**Sanity check**: This function should not be called for Kings or Pawns (they have dedicated generators due to their special movement rules).

```cpp
const Square* pl = pos.squares<Pt>(us);
```

**Get piece list:** Returns a pointer to an array of squares where our pieces of type `Pt` are located.

For example, if `Pt = KNIGHT` and `us = WHITE`, this returns a list like `{b1, g1, SQ_NONE}` (terminated by `SQ_NONE`).

This is more efficient than iterating through all 64 squares checking if there's a knight.

### Loop through all pieces of this type:

```cpp
for (Square from = *pl; from != SQ_NONE; from = *++pl)
    {
```

- `from = *pl`: Start with the first piece's square
- `from != SQ_NONE`: Continue until we hit the terminator
- `from = *++pl`: Pre-increment to next piece square

Example iteration for WHITE knights at b1, g1:

1. `from = b1`
2. `from = g1`
3. `from = SQ_NONE` → exit loop

### Check-giving moves 

If we're only generating moves that give check, apply special filtering.

```cpp
if (    (Pt == BISHOP || Pt == ROOK || Pt == QUEEN)
    && !(PseudoAttacks[Pt][from] & target & pos.check_squares(Pt)))
    continue;
```

**Skip sliding pieces that can't give direct check**:

Breaking this down:
- `(Pt == BISHOP || Pt == ROOK || Pt == QUEEN)`: This is a sliding piece
- `PseudoAttacks[Pt][from]`: All squares this piece could attack (ignoring blockers)
- `& target`: Intersect with valid destination squares
- `& pos.check_squares(Pt)`: Intersect with squares where this piece type would give check

If this intersection is empty, the piece can't give a direct check from this square, so skip it (`continue`).

**Why only for sliding pieces?**
- Knights have to be checked differently (they always move a fixed distance)
- Knights are handled by the later `b &= pos.check_squares(Pt)` line

```cpp
if (pos.discovered_check_candidates() & from)
    continue;
```

**Skip discovered check candidates**:

If this piece is a discovered check candidate (moving it would reveal a check from a piece behind it), skip it.

**Why?**
- Discovered checks are more complex to calculate
- They're handled separately or in a different part of move generation
- When generating only quiet checks, we want DIRECT checks, not discovered checks

```cpp
Bitboard b = pos.attacks_from<Pt>(from) & target;
```

Get all valid destination squares:

- `pos.attacks_from<Pt>(from)`: All squares this piece can attack from `from` (considers blockers for sliding pieces)
- `& target`: Filter to only valid destinations (based on what we're generating - captures, quiets, evasions, etc.)

Example (Rook on d4):

- `attacks_from<ROOK>(d4)` = all squares on rank 4 and file d (until blocked)
- If `target` = enemy pieces (captures only), b = capturable pieces on rank 4 and file d

```cpp
if (Checks)
    b &= pos.check_squares(Pt);
```

**Filter to only checking moves**:

If we're generating only moves that give check:
- `pos.check_squares(Pt)`: Bitboard of squares where this piece type would give check to the enemy king
- `& b`: Keep only destinations that both (a) are reachable and (b) give check

Example

- `attacks_from<KNIGHT>(d5)` = {c3, e3, f4, f6, e7, c7, b6, b4}
- `check_squares(KNIGHT)` = squares where knight would attack e8 = {c6, d6, f6, g7, f7, c7}
- `b = {c7, f6}` (only moves that give check)

```cpp
while (b)
    *moveList++ = make_move(from, pop_lsb(&b));
```

**Generate all moves**:

- `pop_lsb(&b)`: Extract the least significant bit (a destination square) and remove it from b
- `make_move(from, to)`: Create a move from from to this destination
- `*moveList++ = ...`: Write the move and advance pointer
Loop continues until all bits in b are processed

## generate

```cpp
template<GenType>
ExtMove* generate(const Position& pos, ExtMove* moveList);
```

### Explicit Template Instantiations

```cpp
// Explicit template instantiations
template ExtMove* generate<CAPTURES>(const Position&, ExtMove*);
template ExtMove* generate<QUIETS>(const Position&, ExtMove*);
template ExtMove* generate<NON_EVASIONS>(const Position&, ExtMove*);
```

This is not a declaration - it's actually forcing the compiler to generate code for specific template parameter values.

**Why It's Needed**

Templates in C++ are "lazy" - the compiler only generates code for template instantiations that are actually used. But Stockfish has a specific reason to force these instantiations:

Without explicit instantiation, every .cpp file that uses eg: `generate<CAPTURES>()` would compile its own copy of the template code. This leads to:

- Longer compile times
- Larger binary size (duplicate code)
- Worse instruction cache performance

Explicit template instantiations tells the compiler: "Generate these three versions of the function right here in `movegen.cpp`"

Now other files can just call them without the compiler needing to see the template implementation.

Notice they only instantiate `CAPTURES`, `QUIETS`, and `NON_EVASIONS`.

Looking at the code, these are probably the most commonly used. Other types like `EVASIONS` or `QUIET_CHECKS` might be:

- Used less frequently
- Generated on-demand when needed

```cpp

/// generate<CAPTURES> generates all pseudo-legal captures and queen
/// promotions. Returns a pointer to the end of the move list.
///
/// generate<QUIETS> generates all pseudo-legal non-captures and
/// underpromotions. Returns a pointer to the end of the move list.
///
/// generate<NON_EVASIONS> generates all pseudo-legal captures and
/// non-captures. Returns a pointer to the end of the move list.

template<GenType Type>
ExtMove* generate(const Position& pos, ExtMove* moveList) {

  assert(Type == CAPTURES || Type == QUIETS || Type == NON_EVASIONS);
  assert(!pos.checkers());

  Color us = pos.side_to_move();

  Bitboard target =  Type == CAPTURES     ?  pos.pieces(~us)
                   : Type == QUIETS       ? ~pos.pieces()
                   : Type == NON_EVASIONS ? ~pos.pieces(us) : 0;

  return us == WHITE ? generate_all<WHITE, Type>(pos, moveList, target)
                     : generate_all<BLACK, Type>(pos, moveList, target);
}
```

Generic entry point for normal move generation (not evasions, not legal filtering yet).

This generic definition is used only for 3 types of scenarios as others have specific definition.

#### Target mask 

```cpp
Bitboard target =  Type == CAPTURES     ?  pos.pieces(~us)
                 : Type == QUIETS       ? ~pos.pieces()
                 : Type == NON_EVASIONS ? ~pos.pieces(us) : 0;
```

`target` tells lower-level generators which destination squares are allowed.

| Mode         | target means               | Result            |
| ------------ | -------------------------- | ----------------- |
| CAPTURES     | squares occupied by enemy  | only captures     |
| QUIETS       | empty squares              | only non-captures |
| NON_EVASIONS | squares NOT occupied by us | captures + quiets |



### generate<QUIET_CHECKS>

```cpp
/// generate<QUIET_CHECKS> generates all pseudo-legal non-captures and knight
/// underpromotions that give check. Returns a pointer to the end of the move list.
template<>
ExtMove* generate<QUIET_CHECKS>(const Position& pos, ExtMove* moveList) {

  assert(!pos.checkers());

  Color us = pos.side_to_move();
  Bitboard dc = pos.discovered_check_candidates();

  while (dc)
  {
     Square from = pop_lsb(&dc);
     PieceType pt = type_of(pos.piece_on(from));

     if (pt == PAWN)
         continue; // Will be generated together with direct checks

     Bitboard b = pos.attacks_from(Piece(pt), from) & ~pos.pieces();

     if (pt == KING)
         b &= ~PseudoAttacks[QUEEN][pos.square<KING>(~us)];

     while (b)
         *moveList++ = make_move(from, pop_lsb(&b));
  }

  return us == WHITE ? generate_all<WHITE, QUIET_CHECKS>(pos, moveList, ~pos.pieces())
                     : generate_all<BLACK, QUIET_CHECKS>(pos, moveList, ~pos.pieces());
}
```

```cpp
/// generate<QUIET_CHECKS> generates all pseudo-legal non-captures and knight
/// underpromotions that give check. Returns a pointer to the end of the move list.
template<>
ExtMove* generate<QUIET_CHECKS>(const Position& pos, ExtMove* moveList) {
```

#### Template specialization

This is a complete specialization for `GenType = QUIET_CHECKS`. It completely replaces any generic template implementation.

The `<>` after `template` means "this is a full specialization with no template parameters left".

```cpp
assert(!pos.checkers());
```

**Sanity check:** We should not be in check when generating quiet checks. If we're in check, we should be generating evasions instead.
Although its possible to give check while evading enemy check, it's considered elsewhere.

```cpp
Color us = pos.side_to_move();
```
```cpp
`pos.checkers()` returns a bitboard of pieces giving check. It should be empty (0).

Bitboard dc = pos.discovered_check_candidates();
```

**Get discovered check candidates**: Returns a bitboard of pieces that, if moved, would reveal a check from a piece behind them.

```cpp
  while (dc)
  {
     Square from = pop_lsb(&dc);
     PieceType pt = type_of(pos.piece_on(from));
```

#### Loop through discovered check candidates: 

- Process each piece that can give a discovered check.
- Get the square of the next discovered check candidate and remove it from the bitboard.

```cpp
if (pt == PAWN)
    continue; // Will be generated together with direct checks
```

**Skip pawns:** Pawn discovered checks are handled later by `generate_all()` because:

- Pawn moves are complex (pushes, captures, promotions, en passant)
- They're better handled by the specialized `generate_pawn_moves()` function
- That function already knows how to filter for checks

```cpp
Bitboard b = pos.attacks_from(Piece(pt), from) & ~pos.pieces();
```

**Get quiet discovered check moves**:
- `pos.attacks_from(Piece(pt), from)`: All squares this piece can attack from `from`
- `& ~pos.pieces()`: Filter to only **empty squares** (quiet moves, not captures)

```cpp
if (pt == KING)
    b &= ~PseudoAttacks[QUEEN][pos.square<KING>(~us)];
```
**Special case for king discovered checks**:

If the king itself is a discovered check candidate (rare but possible), we need extra filtering:
- `PseudoAttacks[QUEEN][pos.square<KING>(~us)]`: All squares the enemy king can "see" (as if it were a queen - all 8 directions)
- `~...`: Invert the bitboard
- `b &= ...`: Remove these squares from valid king moves

**Why?** Moving our king next to the enemy king would be illegal (kings can't be adjacent). This filters out those illegal moves.

**Note:** Here we are not limiting the direction of king to be 1 square, it still works because if our king is already a discovered check candidate, it cannot possibly block the ray of another sliding piece to king. 

#### Generate all discovered check moves

For each valid destination square, create a move and add it to the list.

```cpp
return us == WHITE ? generate_all<WHITE, QUIET_CHECKS>(pos, moveList, ~pos.pieces())
                   : generate_all<BLACK, QUIET_CHECKS>(pos, moveList, ~pos.pieces());
}
```
**Generate direct checks**: After handling discovered checks, call `generate_all()` to generate moves that give **direct checks** (the moving piece itself attacks the king).

**Parameters:**
- Template: `WHITE` or `BLACK` (which side is moving)
- Template: `QUIET_CHECKS` (tells `generate_all()` to only generate checking moves)
- `pos`: Position
- `moveList`: Current end of move list (with discovered checks already added)
- `~pos.pieces()`: Target bitboard = all empty squares (quiet moves only)


### generate<EVASIONS>

This function generates all evasion moves when the king is in check. There are only 3 ways to get out of check:

1. Move the king to a safe square
2. Block the check (only works for sliding piece checks: bishop, rook, queen)
3. Capture the checking piece

The function handles these carefully, with special logic for double checks (where only king moves work).

#### Initialize slider attack bitboard

Will hold all squares attacked by sliding pieces (bishops, rooks, queens) that are giving check.

```cpp
Bitboard sliderAttacks = 0;
Bitboard sliders = pos.checkers() & ~pos.pieces(KNIGHT, PAWN);
```

**Get sliding checkers:**

- `pos.checkers()`: All pieces giving check
- `& ~pos.pieces(KNIGHT, PAWN)`: Remove knights and pawns (they're not sliders)
- Result: Only bishops, rooks, and queens that are giving check

**Why separate sliders?** Because slider checks create a "ray of attack" that the king cannot move along, while knight/pawn checks don't have this property.

#### Loop through sliding checkers:

```cpp
  // Find all the squares attacked by slider checkers. We will remove them from
  // the king evasions in order to skip known illegal moves, which avoids any
  // useless legality checks later on.
  while (sliders)
  {
      Square checksq = pop_lsb(&sliders);
      sliderAttacks |= LineBB[checksq][ksq] ^ checksq;
  }
```

- Process each sliding piece giving check.
- Extract the position of the sliding checker.
- Add the attack ray to `sliderAttacks`

Let me break this down:
- `LineBB[checksq][ksq]`: The **entire line** (rank, file, or diagonal) connecting the checker to our king
- `^ checksq`: **XOR** (remove) the checker's square itself from the line

**Why remove the checker's square?**

Because the king **CAN** capture the checking piece! We only want to exclude squares along the ray **beyond** the checker.

#### Generate king evasion moves

```cpp
  // Generate evasions for king, capture and non capture moves
  Bitboard b = pos.attacks_from<KING>(ksq) & ~pos.pieces(us) & ~sliderAttacks;
  while (b)
      *moveList++ = make_move(ksq, pop_lsb(&b))
```

**Get legal king moves**:

- `pos.attacks_from<KING>(ksq)`: All 8 squares around the king
- `& ~pos.pieces(us)`: Can't capture our own pieces
- `& ~sliderAttacks`: Can't move along the slider's attack ray
- For each safe square, create a king move.

```cpp
if (more_than_one(pos.checkers()))
    return moveList; // Double check, only a king move can save the day
```

**Double check special case**: 

If there are 2+ pieces giving check, the ONLY way to escape is to move the king (you can't block two checks at once, and you can't capture two pieces in one move).

`more_than_one(bitboard)` checks if the bitboard has more than one bit set.

```cpp
// Generate blocking evasions or captures of the checking piece
Square checksq = lsb(pos.checkers());
```

#### Get the (single) checking piece's square:

Since we passed the double-check test, there's exactly one checker. `lsb()` gets the least significant bit (the checker's position).

```cpp
Bitboard target = between_bb(checksq, ksq) | checksq;
```

**Calculate valid evasion squares**: Pieces (other than the king) can either:
1. **Block** the check by moving between the checker and king
2. **Capture** the checking piece

- `between_bb(checksq, ksq)`: All squares **between** the checker and king (only non-empty for sliders)
- `| checksq`: OR with the checker's square itself (capturing it)

```cpp
return us == WHITE ? generate_all<WHITE, EVASIONS>(pos, moveList, target)
                   : generate_all<BLACK, EVASIONS>(pos, moveList, target);
}
```
**Generate blocking/capturing moves**: 

Call `generate_all()` with the `target` bitboard set to valid evasion squares.

This will generate:
- Pawn moves to blocking/capturing squares
- Knight moves to blocking/capturing squares
- Bishop moves to blocking/capturing squares
- Rook moves to blocking/capturing squares
- Queen moves to blocking/capturing squares
- (King moves already generated above)
- (No castling - can't castle out of check)

The `target` parameter ensures pieces only move to squares that help escape check.

## generate_all

`generate_all` is the central dispatcher that produces all pseudo-legal moves for one side by delegating work to specialized generators.

It generates moves in a fixed order: pawns → minor/major pieces → king → castling, while filtering squares using the target bitboard (captures, quiets, evasions, etc.).

The behavior is controlled at compile-time using templates (Color and GenType) so there are no runtime condition branches inside tight loops.

It focuses purely on speed and completeness — legality (king safety) is verified later, not here.

```cpp
  template<Color Us, GenType Type>
  ExtMove* generate_all(const Position& pos, ExtMove* moveList, Bitboard target) {

    const bool Checks = Type == QUIET_CHECKS;

    moveList = generate_pawn_moves<Us, Type>(pos, moveList, target);
    moveList = generate_moves<KNIGHT, Checks>(pos, moveList, Us, target);
    moveList = generate_moves<BISHOP, Checks>(pos, moveList, Us, target);
    moveList = generate_moves<  ROOK, Checks>(pos, moveList, Us, target);
    moveList = generate_moves< QUEEN, Checks>(pos, moveList, Us, target);

    if (Type != QUIET_CHECKS && Type != EVASIONS)
    {
        Square ksq = pos.square<KING>(Us);
        Bitboard b = pos.attacks_from<KING>(ksq) & target;
        while (b)
            *moveList++ = make_move(ksq, pop_lsb(&b));
    }

    if (Type != CAPTURES && Type != EVASIONS && pos.can_castle(Us))
    {
        if (pos.is_chess960())
        {
            moveList = generate_castling<MakeCastling<Us,  KING_SIDE>::right, Checks, true>(pos, moveList, Us);
            moveList = generate_castling<MakeCastling<Us, QUEEN_SIDE>::right, Checks, true>(pos, moveList, Us);
        }
        else
        {
            moveList = generate_castling<MakeCastling<Us,  KING_SIDE>::right, Checks, false>(pos, moveList, Us);
            moveList = generate_castling<MakeCastling<Us, QUEEN_SIDE>::right, Checks, false>(pos, moveList, Us);
        }
    }

    return moveList;
  }
```

```cpp
const bool Checks = Type == QUIET_CHECKS;
```

Some generators need to know whether we only want checking moves.
Compile-time constant → no runtime branching inside hot loops.

### Pawn moves (special case first)

```cpp
moveList = generate_pawn_moves<Us, Type>(pos, moveList, target);
```

Pawns handled separately because they are the most complex:
- promotions
- double pushes
- en-passant
- discovered checks
- asymmetric movement

### Normal piece moves

```cpp
moveList = generate_moves<KNIGHT, Checks>(pos, moveList, Us, target);
moveList = generate_moves<BISHOP, Checks>(pos, moveList, Us, target);
moveList = generate_moves<  ROOK, Checks>(pos, moveList, Us, target);
moveList = generate_moves< QUEEN, Checks>(pos, moveList, Us, target);
```

Generic generator reused for all non-pawn, non-king pieces.
- Checks → generate only checking moves when needed
- target → filters capture/quiet squares

### King normal moves

```cpp
if (Type != QUIET_CHECKS && Type != EVASIONS)
{
    Square ksq = pos.square<KING>(Us);
    Bitboard b = pos.attacks_from<KING>(ksq) & target;
    while (b)
        *moveList++ = make_move(ksq, pop_lsb(&b));
}
```

King moves excluded when:

- QUIET_CHECKS: king quiet checks handled elsewhere
- EVASIONS: special generator required

Otherwise:
- king attacks = adjacent squares
- & target filters captures/quiet

### Castling

```cpp
if (Type != CAPTURES && Type != EVASIONS && pos.can_castle(Us))
```

Castling only generated when:
- not capture generation
- not in check evasions
- castling rights exist

**Chess960 vs Standard chess**

```cpp
if (pos.is_chess960())
    generate_castling<..., true>
else
    generate_castling<..., false>
```

Stockfish compiles two versions:
- normal chess
- Chess960 rules

No runtime branching inside generator.

**Overall structure**

```cpp
generate_all
 ├─ pawns
 ├─ knights
 ├─ bishops
 ├─ rooks
 ├─ queens
 ├─ king moves
 └─ castling
```

Each piece uses:
- bitboards
- target filtering
- compile-time specialization

**Key Idea**

This function is the central move generation pipeline.

It does NOT check legality — only produces pseudo-legal moves efficiently.

Legal filtering happens later.