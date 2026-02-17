---
title:  "Move Picker"
date:   2026-02-15
draft: false
categories: ["chess engines"]
tags: ["move picker"]
author: Sanketh
---

# Move Picker

## Stats

```cpp
/// The Stats struct stores moves statistics. According to the template parameter
/// the class can store History and Countermoves. History records how often
/// different moves have been successful or unsuccessful during the current search
/// and is used for reduction and move ordering decisions.
/// Countermoves store the move that refute a previous one. Entries are stored
/// using only the moving piece and destination square, hence two moves with
/// different origin but same destination and piece will be considered identical.
template<typename T, bool CM = false>
struct Stats {

  static const Value Max = Value(1 << 28);

  const T* operator[](Piece pc) const { return table[pc]; }
  T* operator[](Piece pc) { return table[pc]; }
  void clear() { std::memset(table, 0, sizeof(table)); }
  void update(Piece pc, Square to, Move m) { table[pc][to] = m; }
  void update(Piece pc, Square to, Value v) {

    if (abs(int(v)) >= 324)
        return;

    table[pc][to] -= table[pc][to] * abs(int(v)) / (CM ? 936 : 324);
    table[pc][to] += int(v) * 32;
  }

private:
  T table[PIECE_NB][SQUARE_NB];
};

typedef Stats<Move> MoveStats;
typedef Stats<Value, false> HistoryStats;
typedef Stats<Value,  true> CounterMoveStats;
typedef Stats<CounterMoveStats> CounterMoveHistoryStats;
```

It is a generic 2-D table indexed by (piece, destination square)

```cpp
table[piece][to_square] → learned information about that move
```

So it doesn’t care about from square.

This is intentional:
Stockfish learns ideas, not exact moves.

> “Knight to e4 is often good in this position family”

### What does it Store?

Depends on template type T.

#### 1. MoveStats (Countermoves)

```cpp
typedef Stats<Move> MoveStats;
```

**Stores:** A move for each [piece][square]
**Usage:** "What move refutes opponent's last move?"

```cpp
MoveStats countermoves;

// Opponent played Nf6
// We responded with d4 (good response)
countermoves.update(BLACK_KNIGHT, SQ_F6, MOVE_D2D4);

// Later, opponent plays Nf6 again:
Move response = countermoves[BLACK_KNIGHT][SQ_F6];
// response = d4
// Try this first! (likely good again)
```

Again these are not actual moves played, because if we had already played them, we won't be playing them in future. These are the among the millions of possibilities examined during minmax. 

#### 2. HistoryStats (History Heuristic)

```cpp
typedef Stats<Value, false> HistoryStats;
```

- **Stores:** Score (Value) for each [piece][square]
- **Usage:** "How often has this move been good?"

Stores: [piece][square] → scoreDoes NOT care about:
- ❌ What the opponent's last move was.
- ❌ What position we're in
- ❌ What came before this move

Only tracks:
- ✅ "Has [piece to square] been good lately?"

```cpp
HistoryStats history;

// Position A: Opponent played d5
// We try Ne4 → beta cutoff
history.update(WHITE_KNIGHT, SQ_E4, +64);

// Position B: Opponent played c5  
// We try Ne4 → beta cutoff again
history.update(WHITE_KNIGHT, SQ_E4, +36);

// Position C: Opponent played Nf6
// We try Ne4 → beta cutoff again
history.update(WHITE_KNIGHT, SQ_E4, +49);

// Result:
history[WHITE_KNIGHT][SQ_E4] = 5000+ (high score)

// Interpretation:
"Ne4 has been good in general, regardless of what opponent did. This will be the first move we try for next couple of searches even if we don't play it now."
```

#### 3. CounterMoveStats

```cpp
typedef Stats<Value, true> CounterMoveStats;
```

Same as HistoryStats but:

- `CM = true` → different decay formula
- Used for countermove history (two-move patterns)
- CounterMoveStats is not independently, its used by `CounterMoveHistoryStats`

#### 4. CounterMoveHistoryStats (Follow-up History)

```cpp
typedef Stats<CounterMoveStats> CounterMoveHistoryStats;
```

**This is a 4D array!**

```cpp
// Underlying structure:
CounterMoveStats table[PIECE_NB][SQUARE_NB];
//                     ↓
//        Value table2[PIECE_NB][SQUARE_NB];

// Final structure:
Value table[piece1][square1][piece2][square2];
```

Usage: "If opponent played [piece1 to square1], and we play [piece2 to square2], was that good?"

```cpp
CounterMoveHistoryStats cmHistory;

// Opponent: Nf6 (BLACK_KNIGHT to f6)
// We: d4 (WHITE_PAWN to d4)
// Result: Good! (caused cutoff)

cmHistory[BLACK_KNIGHT][SQ_F6].update(WHITE_PAWN, SQ_D4, +64);

// Later:
// We want to evaluate what if Opponent plays Nf6 again
Value score = cmHistory[BLACK_KNIGHT][SQ_F6][WHITE_PAWN][SQ_D4];
// score = 2048 (d4 was good response to Nf6 before, let's try it first)
```

### How History and CounterMoves are Used?

```cpp
// HISTORY (context-free):
history[WHITE_KNIGHT][SQ_E4] = 5000
"Ne4 is often good"

// COUNTERMOVE HISTORY (context-aware):
cmh[BLACK_PAWN][SQ_D5][WHITE_KNIGHT][SQ_E4] = 3000
"Ne4 is often good WHEN opponent played d5"

cmh[BLACK_KNIGHT][SQ_F6][WHITE_KNIGHT][SQ_E4] = -500
"Ne4 is often BAD WHEN opponent played Nf6"
```

```cpp
// Opponent just played Nf6

// Calculate move score for Ne4:
int score_Ne4 = 0;

// Add general history
score_Ne4 += history[WHITE_KNIGHT][SQ_E4];          // +5000

// Add context-specific history
score_Ne4 += cmh[BLACK_KNIGHT][SQ_F6]               // -500
                [WHITE_KNIGHT][SQ_E4];

// Total: 5000 - 500 = 4500

// Calculate for Nd4:
int score_Nd4 = 0;
score_Nd4 += history[WHITE_KNIGHT][SQ_D4];          // +1000
score_Nd4 += cmh[BLACK_KNIGHT][SQ_F6]               // +2000
                [WHITE_KNIGHT][SQ_D4];
// Total: 1000 + 2000 = 3000

// Result: Try Ne4 first (4500 > 3000)
```

### Update - Decay Score Calculatio 

```cpp
void update(Piece pc, Square to, Value v) {
    if (abs(int(v)) >= 324)
        return;

    table[pc][to] -= table[pc][to] * abs(int(v)) / (CM ? 936 : 324);
    table[pc][to] += int(v) * 32;
}
```

#### History Update Formula

**The Goal**

Good moves should increase their history score. Bad moves should decrease their history score.

But we need:

- Decay old information (recent searches more important)
- Don't overflow (scores bounded)
- Fast convergence (respond quickly to patterns)

**Decay Intuition:**

Remember in both history and countermoves we don't store at what exact position this move was good/bad. 

As game progresses
- The move may become not so good/bad.
- Not even a legal move.

```
Like gravity pulling score toward zero
- Old information gradually forgotten
- Recent patterns have more weight
- Allows adaptation to changing positions
- Stable patterns reach equilibrium
```

**Decay rates:**
```
History: 324 (faster) → Quick adaptation
CounterMoves: 936 (slower) → Preserve stable patterns
```


**Think of it like gravity pulling the score toward zero:**
```
Current score: +10,000 (Ne4 was good in old searches)

New search: Ne4 is good again
Bonus: +64

Update:
├─ Decay:  10,000 - (10,000 * 64 / 324) = 10,000 - 1,975 = 8,025
└─ Bonus:  8,025 + (64 * 32) = 8,025 + 2,048 = 10,073

Result: Score stays high (move is still good)
```
```
Current score: +10,000 (Ne4 was good in old searches)

New search: Ne4 is BAD now
Penalty: -64

Update:
├─ Decay:  10,000 - (10,000 * 64 / 324) = 10,000 - 1,975 = 8,025
└─ Penalty: 8,025 + (-64 * 32) = 8,025 - 2,048 = 5,977

Result: Score drops (adapting to new information)
```

### Comparision with TT


**Value in Stats:**
```
❌ NOT: position evaluation
❌ NOT: alpha/beta bounds
❌ NOT: SEE score

✅ IS: "How often was this move good?" (statistical score)
```

**MoveStats vs TT:**
```
TT:        Stores info for EXACT position (very specific)
MoveStats: Stores pattern for ANY position with this move (general)
```

Both used together:
```cpp
1. Try TT move (best for this exact position)
2. Try countermove (good pattern across positions)
3. Try other moves ordered by history

// Move ordering priority:
1. TT move         ← Specific to this exact position (best!)
2. Countermove     ← General pattern (good guess)
3. History         ← Statistical frequency
4. Other moves
```

## FromToStats

This is like `HistoryStats`, but more specific - it tracks moves by their from-square and to-square.

**The Structure**

```cpp
Value table[COLOR_NB][SQUARE_NB][SQUARE_NB];
//          ↑         ↑           ↑
//        Color     From        To
//        (2)       (64)        (64)
```

3D array: `[color][from_square][to_square]` → score
Size: 2 × 64 × 64 = 8,192 entries

### Key Difference from HistoryStats

#### HistoryStats (2D)

```cpp
table[piece][to_square]

// Example:
history[WHITE_KNIGHT][e4]
// "Knight moves to e4" (from anywhere)
```

#### FromToStats (3D)

```cpp
table[color][from_square][to_square]

// Example:
fromTo[WHITE][f3][e4]
// "Move from f3 to e4" (any piece!)
```

### What It Tracks

**Less specific than HistoryStats:**

```cpp
FromToStats fromToHistory;

// Move: Nf3-e5 (knight from f3 to e5)
fromToHistory.update(WHITE, make_move(f3, e5), +64);

// Stored at:
table[WHITE][f3][e5] = 2048

// Later, any move f3→e5 gets this score:
// - Nf3-e5 (knight) ✓
// - Bf3-e5 (bishop, if possible) ✓  
// - Even pawn f3-e5 (if legal) ✓

// But NOT:
// - Nd2-e5 (different from-square) ✗
```

#### When FromToStats Helps

Captures PATH information that HistoryStats misses:
```cpp
Position: Knight can go to e5 from two squares

// From f3:
history[WHITE_KNIGHT][e5] = 5000    // "Ne5 is good"
fromTo[WHITE][f3][e5] = 8000        // "f3→e5 path is especially good!"

// From d2:
history[WHITE_KNIGHT][e5] = 5000    // "Ne5 is good" (same!)
fromTo[WHITE][d2][e5] = 1000        // "d2→e5 path is less good"

// Result: Prefer Nf3-e5 over Nd2-e5
```

**So Which Is More Specific?**

**Neither! They're DIFFERENT dimensions:**
```
HistoryStats:     PIECE-specific, PATH-agnostic
FromToStats:      PATH-specific, PIECE-agnostic

Both used together for best ordering:
score = history[piece][to] + fromTo[color][from][to]
```

**HistoryStats vs FromToStats:**
```
HistoryStats:     [piece][to]
- Knows WHAT piece
- Doesn't know WHERE from
- "Is Ne5 good?"

FromToStats:      [color][from][to]
- Knows WHERE from  
- Doesn't know WHAT piece
- "Is f3→e5 good?"
```
Complementary information!

## MovePicker - The Move Ordering Engine

This is the heart of move ordering in Stockfish. 

### The Big Picture

**Purpose:** Generate moves one at a time in best-first order to maximize alpha-beta cutoffs.

```cpp
MovePicker mp(pos, ttMove, depth, ss);

Move m;
while ((m = mp.next_move()) != MOVE_NONE) {
    // Try move in best-first order
    score = -search(pos.do_move(m), ...);
    if (score >= beta)
        break;  // Cutoff! (hopefully on first move)
}
```

**Key insight:** Don't generate all moves at once, generate them lazily in priority order.

### The Three Constructors

```cpp
MovePicker(const Position&, Move, Value);
MovePicker(const Position&, Move, Depth, Square);
MovePicker(const Position&, Move, Depth, Search::Stack*);
```

Three different use cases:

#### Constructor 1: Quiescence Search

```cpp
MovePicker(const Position& p, Move ttm, Value threshold);
```

**Parameters:**

- `ttm`: TT move (try first)
- `threshold`: Only generate captures with SEE ≥ threshold

**Used in:** Quiescence search (only captures)

```cpp
MovePicker mp(pos, ttMove, -100);
// Only generate captures that don't lose >1 pawn
```

```cpp
MovePicker::MovePicker(const Position& p, Move ttm, Value th)
           : pos(p), threshold(th) {

  assert(!pos.checkers());

  stage = PROBCUT;

  // In ProbCut we generate captures with SEE higher than the given threshold
  ttMove =   ttm
          && pos.pseudo_legal(ttm)
          && pos.capture(ttm)
          && pos.see_ge(ttm, threshold + 1)? ttm : MOVE_NONE;

  stage += (ttMove == MOVE_NONE);
}
```

```cpp
assert(!pos.checkers());
```

**What:** Checks that we're NOT in check
**Why:** This constructor is for quiescence/ProbCut, which doesn't handle check evasions


```cpp
stage = PROBCUT;
```

**What:** Set initial stage to PROBCUT
Stage enum (approximately):

```cpp
enum Stage {
    MAIN_TT = 0,
    // ...
    PROBCUT,           // Only high-SEE captures
    PROBCUT_CAPTURES,  // Generate and return them
    // ...
};
```

Why PROBCUT? This constructor is used for:

1. **ProbCut search** (try only captures that gain material)
2. **Quiescence search** (try only non-losing captures)

**TT Move Validation (The Tricky Part)**

```cpp
ttMove =   ttm
        && pos.pseudo_legal(ttm)
        && pos.capture(ttm)
        && pos.see_ge(ttm, threshold + 1) ? ttm : MOVE_NONE;
```

This is a chain of boolean conditions that must ALL be true to accept the TT move.

**Condition 1: ttm**

Check: TT move exists (not MOVE_NONE)

**Condition 2: pos.pseudo_legal(ttm)**

**Check:** TT move is pseudo-legal in current position
**Pseudo-legal** means:
- Move syntax is valid (from/to squares exist)
- Piece can make that move (e.g., knight moves like a knight)
- But might leave king in check (not validated yet)

**Condition 3: pos.capture(ttm)**

**Check:** TT move is a capture
**Why this check?** In ProbCut/quiescence, we only want captures!

**Condition 4: pos.see_ge(ttm, threshold + 1)**



#### Constructor 2: Evasion Search

```cpp
MovePicker(const Position& p, Move ttm, Depth d, Square sq);
```

**Parameters:**

- `p`: Current position
- `ttm`: TT move
- `d`: Negative depth (quiescence depth)
- `s`: Recapture square (only used in one case)- Used when in check or after a capture

**Used in:** Recapture extensions, check evasions

```cpp
// Opponent just captured on e4
MovePicker mp(pos, ttMove, depth, SQ_E4);
// Prioritize recaptures on e4
```

```cpp
MovePicker::MovePicker(const Position& p, Move ttm, Depth d, Square s)
           : pos(p) {

  assert(d <= DEPTH_ZERO);

  if (pos.checkers())
      stage = EVASION;

  else if (d > DEPTH_QS_NO_CHECKS)
      stage = QSEARCH_WITH_CHECKS;

  else if (d > DEPTH_QS_RECAPTURES)
      stage = QSEARCH_NO_CHECKS;

  else
  {
      stage = QSEARCH_RECAPTURES;
      recaptureSquare = s;
      return;
  }

  ttMove = ttm && pos.pseudo_legal(ttm) ? ttm : MOVE_NONE;
  stage += (ttMove == MOVE_NONE);
}
```

```cpp
// Depth constants (negative values):
DEPTH_ZERO = 0
DEPTH_QS_CHECKS = 0        // Try checks in quiescence
DEPTH_QS_NO_CHECKS = -1    // No checks, just captures
DEPTH_QS_RECAPTURES = -5   // Only recaptures on specific square

// Typical quiescence depths:
d = 0    → Can try checks
d = -1   → Only captures, no checks
d = -2   → Only captures, no checks
d = -5   → Only recaptures on one square
d = -7   → Only recaptures on one square
```

```cpp
assert(d <= DEPTH_ZERO);
```

**Check:** Depth must be ≤ 0 (quiescence depths are negative/zero)

**Why?** This constructor is ONLY for quiescence search, which uses negative depths.

##### Why is Depth an enum?

Stockfish needs multiple kinds of quiescence search, not just one.

Stockfish encodes the mode inside the depth number itself.

> Negative depth = different quiescence modes

So depth becomes a state machine.

**The Meaning of Each Constant**

Think of them as search regimes, not depths.

| Constant | Meaning |
| :--- | :--- |
| DEPTH_ZERO | transition point: start quiescence |
| DEPTH_QS_CHECKS | full qsearch (captures + checking moves) |
| DEPTH_QS_NO_CHECKS | captures only |
| DEPTH_QS_RECAPTURES | only recaptures on same square |
| DEPTH_NONE | stop search entirely |

**Key idea**

> The more negative the depth → the quieter the search becomes

So the engine gradually reduces tactical horizon:

```
Normal search
   ↓
Qsearch with checks
   ↓
Qsearch captures only
   ↓
Recaptures only
   ↓
Stop
```

This is called tapered quiescence.

Instead of writing:

```cpp
if (mode == QS_CHECKS) ...
else if (mode == QS_CAPTURES) ...
else if (mode == QS_RECAPTURES) ...
```

Stockfish can simply do:

```cpp
depth--
```

and naturally transition between modes.

Search controls itself automatically.

**Four scenarios:**

1. In check (any depth):
- Stage: EVASION
- Generates: Evasion moves only


2. Depth = 0 (shallow quiescence):
- Stage: QSEARCH_WITH_CHECKS
- Generates: Captures + Checks


3. Depth = -1 to -4 (normal quiescence):
- Stage: QSEARCH_NO_CHECKS
- Generates: Captures only


4. Depth ≤ -5 (deep quiescence):
- Stage: QSEARCH_RECAPTURES
- Generates: Recaptures on square only
- Early return (skips TT validation)

Key insight: Deeper quiescence = more selective (prune aggressively)

#### Constructor 3: Normal Search

```cpp
MovePicker::MovePicker(const Position& p, Move ttm, Depth d, Search::Stack* s)
    : pos(p), ss(s), depth(d)
```

**Initializer list stores:**

- `pos(p)`: Position reference
- `ss(s)`: Search stack pointer
- `depth(d)`: Current search depth

Note: No `threshold` or `recaptureSquare` - this is full search, not quiescence!

**Used in:** Regular alpha-beta search

Opposite of the quiescence constructor!

```cpp
assert(d > DEPTH_ZERO);
```

Get Previous Square

```cpp
Square prevSq = to_sq((ss-1)->currentMove);

// ss points to current ply
// ss-1 points to PARENT ply
```

Get Countermove

```cpp
countermove = pos.this_thread()->counterMoves[pos.piece_on(prevSq)][prevSq];
```

**Three parts:**

`pos.this_thread()`

```cpp
// Get the thread searching this position
// Each thread has its own move statistics
Thread* thread = pos.this_thread();
```

`pos.piece_on(prevSq)`

```cpp
// What piece is on the square opponent just moved to?
Piece theirPiece = pos.piece_on(prevSq);

// Example:
// Opponent played Nd4
// prevSq = d4
// piece_on(d4) = BLACK_KNIGHT
```

`counterMoves[piece][square]`

```cpp
// Look up our recorded response to this move
Move cm = counterMoves[BLACK_KNIGHT][d4];

// This is the move we previously found to be good
// when opponent played their knight to d4
```

Set Stage

```cpp
stage = pos.checkers() ? EVASION : MAIN_SEARCH;
```

Two possibilities:

In Check → EVASION

```cpp
if (pos.checkers())
    stage = EVASION;

// Must get out of check!
// Generate only evasion moves
```

Not in Check → MAIN_SEARCH

```cpp
else
    stage = MAIN_SEARCH;

// Normal position
// Generate all moves in priority order:
// TT → Captures → Killers → Countermove → Quiets → Bad Captures
```

TT Move Validation

```cpp
ttMove = ttm && pos.pseudo_legal(ttm) ? ttm : MOVE_NONE;
```

**Same as quiescence constructor:**

- TT move exists?
- Pseudo-legal in current position?

Stage Adjustment

```cpp
stage += (ttMove == MOVE_NONE);
```

Same trick as other constructors:

```cpp
// With valid TT move:
stage = MAIN_SEARCH (e.g., 0)
stage += 0
// = MAIN_SEARCH (try TT move first)

// Without TT move:
stage = MAIN_SEARCH (0)
stage += 1
// = MAIN_SEARCH + 1 (skip to captures)
```

### The Member Variables

```cpp
private:
    const Position& pos;              // Current position
    const Search::Stack* ss;          // Search stack (killers, history)
    Move countermove;                 // Countermove to try
    Depth depth;                      // Search depth
    Move ttMove;                      // TT move (highest priority)
    Square recaptureSquare;           // For recapture prioritization
    Value threshold;                  // SEE threshold for captures
    int stage;                        // Current generation stage
    
    ExtMove *cur;                     // Current move pointer
    ExtMove *endMoves;                // End of generated moves
    ExtMove *endBadCaptures;          // Separator for bad captures
    ExtMove moves[MAX_MOVES];         // Move buffer (218 max)
```

#### 1. pos

```cpp
const Position& pos;
```

**What:** Reference to the current chess positionWhy needed:

**Why needed:**

- Check if moves are legal (`pos.legal(move)`)
- Get piece types (`pos.piece_on(square)`)
- Generate moves (`generate<CAPTURES>(pos, ...)`)
- Evaluate captures with SEE (`pos.see_ge(move, threshold)`)
  

#### 2. ss

```cpp
const Search::Stack* ss;
```

We previously saw another stack anemd `StateInfo`, but it was used to store board state history which wil be used to make/undo moves. 

**Search::Stack → search reasoning memory**

This is NOT about board state.

It stores what the engine learned while thinking at each ply.

Each recursive search call gets one entry:

```cpp
search(depth=5) → ss[0]
 search(depth=4) → ss[1]
  search(depth=3) → ss[2]
   search(depth=2) → ss[3]
```

Search depth = stack depth.

So this stack represents:

> the thinking path inside the search tree

##### What is inside Search::Stack

**Typical fields:**

```
killers[2]          → moves that caused cutoffs here before
currentMove         → move being searched
staticEval          → evaluation of this position
excludedMove        → singular extension logic
ply                 → distance from root
continuationHistory → follow-up move learning
```

This is all heuristics — nothing about legality of position.

A stack is initialized during the beginning of `search` function and it will be destroyed once the function exits. 

However, some information is copied into global tables:
- history table
- countermove table

So the experience survives, but the stack does not.

##### 1. killers[2]

At a given depth, positions often share tactical structure.

Example:
```
You search 50 different branches at depth 8
In MANY of them the move:   Re1+   immediately refutes opponent
```

So next time you reach depth 8:

```
try Re1+ FIRST
```

Because chances are high it cuts off again.

That move becomes a killer move

Why called “killer”?

Because it kills the branch instantly (beta cutoff).

Why two killers?

Because positions differ slightly.

Typical:

```
killer1 → most reliable
killer2 → backup candidate
```

A killer move is NOT necessarily a good move in chess.

It is:

> a move that refuted opponent’s plan in many sibling nodes

Extremely powerful heuristic.

**Key properties:**
- Stored **per ply** (depth level)
- Only **quiet moves** (not captures)
- Usually store **2 killers** per ply
- Updated when a quiet move causes beta cutoff

**Why Only Quiet Moves?**

Captures are already ordered by material logic (SEE/MVV-LVA),
killers exist to rescue quiet moves that would otherwise be searched last.

**Think about move ordering priorities**

Stockfish tries moves roughly in this order:
	1.	TT move (previous best)
	2.	Good captures
	3.	Killer moves
	4.	Countermoves
	5.	History quiet moves
	6.	Bad captures
    
##### 2. currentMove

This stores the move played to reach this node.

Why needed?

Because many heuristics depend on previous move.

##### 3. staticEval

Static evaluation = NNUE evaluation without searching.

Instead of recomputing eval again and again, we store it once in stack.

Used for:
- pruning decisions
- futility pruning
- razoring
- null move pruning

##### 4. excludedMove — singular extension magic

This is advanced but super important.

Singular extension asks:

> “Is ONE move clearly much better than all others?”

If yes → extend search deeper for that move.

To test that, engine temporarily says:

```
Search position WITHOUT best move
```

So we must forbid it:

```
excludedMove = bestMove
```

Search runs again ignoring that move.

If position collapses → the move was singular → extend it.

##### 5. ply

Needed because mate scores depend on distance.

Example:

```
Mate in 5 is better than mate in 7
```

But raw score might be same.

So engine adjusts using ply.

Also used in:
- LMR reductions
- pruning margins
- TT storage

##### 6. continuationHistory

This is extremely powerful modern heuristic.

Not just:

> which move is good

but:

> which move is good AFTER another move

Example patterns:

```
Bxh7+  → Kg8 forced
Ng5+   → strong followup
Qh5    → mating attack
```

**Putting all together — what the stack really is**

At each depth the engine keeps:

- What just happened
- What worked before
- What patterns exist
- What position looks like

So instead of blind search:

Stockfish searches informed search tree

#### 3. Move countermove

```cpp
Move countermove;
```

**What:** The countermove to opponent's last move
**How it's set:**

```cpp
// In constructor:
if (ss && ss->ply > 0) {
    Move lastMove = (ss-1)->currentMove;  // Opponent's last move
    countermove = counterMoves[lastMove];  // Our recorded response
}
```

**Why stored separately**: 
- Need to try it during COUNTERMOVE stage
- Need to avoid trying it twice (if it's also killer or TT move)


#### 4. depth

```cpp
Depth depth;
```

**What:** Current search depth (in plies)
**Why needed:**

- Decide which stages to use
- At low depths, skip expensive move generation
- History bonuses scale with depth

**Example usage:**

```cpp
Move MovePicker::next_move() {
    // At depth < 3, skip quiet moves (ProbCut)
    if (depth < 3 * ONE_PLY && stage == QUIET_MOVES)
        stage = BAD_CAPTURES;  // Skip to bad captures
    
    // History bonus: depth²
    int bonus = depth * depth;
    history.update(move, bonus);
}
```

**Typical values:**
```
Depth 0:  Quiescence search (only captures)
Depth 1-3:  Tactical search (captures + killer moves)
Depth 4+:   Full search (all moves)
```

It tells the engine how reliable a move ordering decision is worth paying for.

**Near the leaves (small depth)**

Example: depth = 2 plies left

```
Us → Them → evaluate
```

You will evaluate very soon anyway.

Spending time generating and sorting 40 quiet moves is wasteful.

So engine mostly tries:
- captures
- tactical moves
- maybe killers

Because quiet positional moves cannot change evaluation much in 2 plies.

Deep in the tree (large depth)


Example: depth = 12 (left)

A bad move ordering here explodes the tree:

```
Wrong first move → no cutoff → millions of nodes
Right first move → cutoff → tiny tree
```

So now it’s worth:
- sorting quiet moves
- using history scores
- more heuristics

**That’s what this means**

> History bonuses scale with depth

If a move refutes at depth 12 → extremely important
If same move refutes at depth 2 → almost meaningless

So Stockfish rewards it proportionally:

```
bonus ≈ depth²
```

##### ProbCut

ProbCut = Probabilistic Cutoff

It is a forward pruning technique.

Meaning:

> Skip searching a branch because it’s almost certainly bad.

**Idea**

Sometimes a move is SO winning tactically
that you don’t need a full deep search to know it fails beta.

Instead:
	1.	Do a shallow search
	2.	If score is already huge
	3.	Assume deeper search will also fail-high
	4.	Prune immediately

**Example**

We are searching depth 10:

Instead of:

```cpp
search(move, depth=10) → expensive
```

We do:

```cpp
search(move, depth=4)
if score >= beta + margin:
    prune branch
```

Why valid?

Because tactical wins rarely disappear at deeper depth.

So we cut based on probability.


**Why depth matters for ProbCut**

ProbCut only makes sense when:
- Depth is large enough
- Tactics are stable
- Confidence high

At shallow depth → unreliable → disabled

So MovePicker uses depth to decide:

> Should we even bother generating quiet moves
> or just try tactical pruning?

**Intuition**

Alpha-beta pruning = mathematically safe pruning
ProbCut = statistically safe pruning

#### 5. ttMove

```cpp
Move ttMove;
```

**What**: Move from transposition table (best move from previous search)
Why stored separately:

- **Highest priority** - try first (90% chance of causing cutoff)
- Need to avoid trying it again in later stages
- Need to check if it's legal before returning it

Example: 

```cpp
// In search:
TTEntry* tte = TT.probe(pos.key());
Move ttMove = tte ? tte->move() : MOVE_NONE;

MovePicker mp(pos, ttMove, depth, ss);

// First call to next_move():
Move m1 = mp.next_move();
// Returns ttMove immediately if legal
```

**Avoiding duplicates:**

```cpp
// When generating captures:
for (Move m : all_captures) {
    if (m == ttMove)
        continue;  // Skip, already tried
    // ... add to list
}
```

#### 6. recaptureSquare

```cpp
Square recaptureSquare;
```

**What:** Square where a piece was just captured (for recapture search)
**When set:** In the recapture constructor

```cpp
MovePicker::MovePicker(const Position& p, Move ttm, Depth d, Square sq)
    : pos(p), ttMove(ttm), depth(d), recaptureSquare(sq)
{
    // sq = square where opponent just captured
}
```


**Why needed**: Prioritize recaptures on that square

**Example:**
```
Opponent played: Nxe4 (captured our pawn on e4)
recaptureSquare = e4

When scoring moves:
├─ Bxe4 (recaptures on e4) → score += 10000  (high priority!)
├─ Nf3 (doesn't recapture)  → score += history[Nf3]
└─ Qxe4 (recaptures on e4) → score += 10000
```

**Typical use case:**

```cpp
// In search, after opponent captures:
if (is_capture(move)) {
    Square capSq = to_sq(move);
    // Search recaptures deeply
    MovePicker mp(pos, ttMove, depth, capSq);
}
```

#### 7. threshold

```cpp
Value threshold;
```

**What:** Minimum SEE (Static Exchange Evaluation) for captures
**Why needed:** Filter out bad captures in quiescence search
**Example:**

```cpp
// Quiescence constructor:
MovePicker::MovePicker(const Position& p, Move ttm, Value th)
    : pos(p), ttMove(ttm), threshold(th)

// In next_move():
Move capture = next_capture();
if (pos.see_ge(capture, threshold))
    return capture;  // Good capture
else
    continue;  // Skip bad capture
```

#### 8. stage

```cpp
int stage;
```

**What:** Current move generation stage (state machine)
**Possible values:**

```cpp
enum Stage {
    MAIN_SEARCH,           // Entry point
    GOOD_CAPTURES,         // Return winning captures
    KILLERS,               // Try killer moves
    GOOD_QUIETS,           // Try quiet moves with good history
    BAD_CAPTURES,          // Return losing captures
    EVASION,               // In check (special)
    PROBCUT,               // High SEE captures only
    QSEARCH,               // Quiescence (captures only)
    // ... more
};
```

**Why needed:** Track where we are in the move generation pipeline

MovePicker does not generate all moves at once.
Instead it produces moves step-by-step in priority order every time next_move() is called.


So Stages =
👉 “Which category of moves should I generate/return right now?”

Think of it like a pipeline:
> Try the most promising moves first → maximize alpha-beta cutoffs → avoid searching garbage moves.
