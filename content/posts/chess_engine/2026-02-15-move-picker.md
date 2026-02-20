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

### Utilities

#### 1. insertion_sort

```cpp
  // Our insertion sort, which is guaranteed to be stable, as it should be
  void insertion_sort(ExtMove* begin, ExtMove* end)
  {
    ExtMove tmp, *p, *q;

    for (p = begin + 1; p < end; ++p)
    {
        tmp = *p;
        for (q = p; q != begin && *(q-1) < tmp; --q)
            *q = *(q-1);
        *q = tmp;
    }
  }
```

This is the classic implementation of insertion sort.

##### What “stable” means here

A stable sort keeps the original order of elements that compare equal.

So if two moves have the same value:

```cpp
Before sort:  [MoveA, MoveB]
After sort :  [MoveA, MoveB]   (not swapped)
```

An unstable sort might output:

```cpp
[MoveB, MoveA]
```

##### Why Stockfish cares a LOT about this

Move ordering in Stockfish is not decided by one heuristic.

It is multi-stage ordering:
 1. TT move
 2. Winning captures (SEE)
 3. Killer moves
 4. Countermoves
 5. History heuristic
 6. Remaining quiet moves

When we reach this insertion sort, the moves already have a meaningful order from earlier stages.

The value field is only the last refinement (history score etc).

So equal scores must NOT destroy earlier priority.

**Used at Quiet Moves**

```cpp
  case QUIET_INIT:
      cur = endBadCaptures;
      endMoves = generate<QUIETS>(pos, cur);
      score<QUIETS>();
      if (depth < 3 * ONE_PLY)
      {
          ExtMove* goodQuiet = std::partition(cur, endMoves, [](const ExtMove& m)
                                             { return m.value > VALUE_ZERO; });
          insertion_sort(cur, goodQuiet);
      } else
          insertion_sort(cur, endMoves);
      ++stage;
```

This is the moment where Stockfish orders quiet moves (non-captures).

Quiet moves are the largest category of moves and also the most dangerous for alpha-beta:

> If we search them in bad order → branching explodes.

So here Stockfish performs the final ordering refinement using the history heuristic.

**What happens in this block**

```cpp
cur = endBadCaptures;
endMoves = generate<QUIETS>(pos, cur);
score<QUIETS>();
```

We now have a list like:

```cpp
[Killer1, Killer2, Countermove, history moves, trash moves...]
```

**Important:**

They are already in a meaningful heuristic order based on generation.

Now we refine them using history scores.

**Special handling at low depth**

```cpp
if (depth < 3 * ONE_PLY)
{
    ExtMove* goodQuiet = std::partition(cur, endMoves,
        [](const ExtMove& m){ return m.value > VALUE_ZERO; });

    insertion_sort(cur, goodQuiet);
}
```

**Why only QUIETS need this**

Captures already have natural ordering:
- MVV-LVA
- SEE
- winning vs losing captures


#### 2. pick_best

```cpp

  // pick_best() finds the best move in the range (begin, end) and moves it to
  // the front. It's faster than sorting all the moves in advance when there
  // are few moves, e.g., the possible captures.
  Move pick_best(ExtMove* begin, ExtMove* end)
  {
      std::swap(*begin, *std::max_element(begin, end));
      return *begin;
  }
```

**What It Does**

Finds the highest scored move and swaps it to the front.

**Why Not Full Sort?**

`pick_best():`
- O(n), finds current best → swaps to front
- Used for captures (few moves, early cutoffs)
- Like selection sort but one element at a time

`insertion_sort():`
- O(n²), stable, sorts highest first
- Used for quiet moves (full order needed)
- Stable preserves secondary ordering (killers, etc.)


**Called repeatedly:**

```cpp
// In next_move():
while (cur < endMoves) {
    pick_best(cur, endMoves);  // Find best of remaining
    return (cur++)->move;      // Return it, advance pointer
}

// Each call: O(n), O(n-1), O(n-2)...
// Total: O(n²) worst case
// But usually cutoff happens early → much faster!
```

### Methods

#### Score

Three specializations, each for different move types.

##### 1. `score<CAPTURES>()`

```cpp
/// score() assigns a numerical value to each move in a move list. The moves with
/// highest values will be picked first.
template<>
void MovePicker::score<CAPTURES>() {
  // Winning and equal captures in the main search are ordered by MVV, preferring
  // captures near our home rank. Surprisingly, this appears to perform slightly
  // better than SEE-based move ordering: exchanging big pieces before capturing
  // a hanging piece probably helps to reduce the subtree size.
  // In the main search we want to push captures with negative SEE values to the
  // badCaptures[] array, but instead of doing it now we delay until the move
  // has been picked up, saving some SEE calls in case we get a cutoff.
  for (auto& m : *this)
      m.value =  PieceValue[MG][pos.piece_on(to_sq(m))]
               - Value(200 * relative_rank(pos.side_to_move(), to_sq(m)));
}
```

**What It Does**

Scores captures by: victim value - rank penalty

**Part 1: Victim Value**

```cpp
PieceValue[MG][pos.piece_on(to_sq(m))]
```

**MVV:** Most Valuable Victim - capture the most valuable piece first

**Part 2: Rank Penalty**

```cpp
- Value(200 * relative_rank(pos.side_to_move(), to_sq(m)))
```

Penalizes captures far from our home rank!

What is `relative_rank`?

```cpp
// relative_rank returns rank from OUR perspective:
// Rank 1 = our home rank (lowest, best)
// Rank 8 = opponent's home rank (highest, penalized)

// For White:
relative_rank(WHITE, a1) = 1  (home rank)
relative_rank(WHITE, a4) = 4  (middle)
relative_rank(WHITE, a8) = 8  (opponent's rank)

// For Black (reversed!):
relative_rank(BLACK, a8) = 1  (home rank)
relative_rank(BLACK, a4) = 5  (middle)
relative_rank(BLACK, a1) = 8  (opponent's rank)
```

**Why Penalize Far Captures?**

**The comment explains it:**
> "exchanging big pieces before capturing a hanging piece probably helps to reduce the subtree size"

Example:
- Hanging pawn on h7 (rank 7 for white)
- Enemy queen on e5 (rank 5 for white)
- We have a rook that can take either

**Delayed SEE**

Important comment:

> "instead of doing it now we delay until the move has been picked up, saving some SEE calls in case we get a cutoff"

```cpp

// Done LATER in next_move():
case GOOD_CAPTURES:
    while (cur < endMoves) {
        pick_best(cur, endMoves);
        
        // SEE check happens HERE (when move is actually picked)
        if (!pos.see_ge(*cur, Value(-55 * cur->value / 1024)))
            *endBadCaptures++ = *cur++;  // Move to bad captures
        else
            return (cur++)->move;  // Return good capture
    }
```

##### 2. `score<QUIETS>()`

```cpp
template<>
void MovePicker::score<QUIETS>() {

  const HistoryStats& history = pos.this_thread()->history;
  const FromToStats& fromTo = pos.this_thread()->fromTo;

  const CounterMoveStats* cm = (ss-1)->counterMoves;
  const CounterMoveStats* fm = (ss-2)->counterMoves;
  const CounterMoveStats* f2 = (ss-4)->counterMoves;

  Color c = pos.side_to_move();

  for (auto& m : *this)
      m.value =      history[pos.moved_piece(m)][to_sq(m)]
               + (cm ? (*cm)[pos.moved_piece(m)][to_sq(m)] : VALUE_ZERO)
               + (fm ? (*fm)[pos.moved_piece(m)][to_sq(m)] : VALUE_ZERO)
               + (f2 ? (*f2)[pos.moved_piece(m)][to_sq(m)] : VALUE_ZERO)
               + fromTo.get(c, m);
}
```

**What is *this here?**

So the function is a member function of MovePicker.

Therefore:

```cpp
this  → pointer to current MovePicker object
*this → the MovePicker object itself
```

Why can we iterate over *this?

Because MovePicker is made iterable.

Inside MovePicker (in movepick.h) there are functions like:

```cpp
ExtMove* begin() { return cur; }
ExtMove* end()   { return endMoves; }
```

So MovePicker behaves like a container of moves.

That allows this:

```cpp
for (auto& m : *this)
```

to expand to:

```cpp
for (ExtMove* it = this->begin(); it != this->end(); ++it) {
    auto& m = *it;
}
```

So it loops over currently generated moves.

**What the loop is doing**

```cpp
m.value =
    history score
  + countermove score (1 ply ago)
  + countermove score (2 ply ago)
  + countermove score (4 ply ago)
  + from-to heuristic
```

##### 3. `score<EVASIONS>()`

```cpp
template<>
void MovePicker::score<EVASIONS>() {
    const HistoryStats& history = pos.this_thread()->history;
    const FromToStats& fromTo = pos.this_thread()->fromTo;
    Color c = pos.side_to_move();
    
    for (auto& m : *this)
        if (pos.capture(m))
            m.value = PieceValue[MG][pos.piece_on(to_sq(m))]
                    - Value(type_of(pos.moved_piece(m))) + HistoryStats::Max;
        else
            m.value = history[pos.moved_piece(m)][to_sq(m)]
                    + fromTo.get(c, m);
}
```

**Two Cases: Captures vs Non-Captures**

**Case 1: Captures When in Check**

```cpp
if (pos.capture(m))
    m.value = PieceValue[MG][pos.piece_on(to_sq(m))]  // Victim value
            - Value(type_of(pos.moved_piece(m)))        // Attacker type penalty
            + HistoryStats::Max;                        // Large bonus!
```

**Three parts:**

Victim Value (MVV)

```cpp
PieceValue[MG][pos.piece_on(to_sq(m))]
// Capture queen (+900) > capture rook (+500) > capture pawn (+100)
```

Attacker Type Penalty (LVA)

```cpp
- Value(type_of(pos.moved_piece(m)))

// type_of returns piece type as integer:
PAWN   = 1
KNIGHT = 2
BISHOP = 3
ROOK   = 4
QUEEN  = 5
KING   = 6

// Small penalty for using expensive piece to capture
// Pawn captures preferred over queen captures
// (but victim value dominates)
```

**MVV-LVA combined:**
```
Capture queen with pawn:   900 - 1 = 899  ← Best!
Capture queen with knight: 900 - 2 = 898
Capture rook with pawn:    500 - 1 = 499
Capture pawn with queen:   100 - 5 = 95   ← Worst
```

HistoryStats::Max Bonus

```cpp
+ HistoryStats::Max  // = 1 << 28 (very large number!)
```

Why add this large bonus?

```cpp
// Captures score: 0 to ~900 + HistoryStats::Max
// Non-captures score: history + fromTo (can be negative!)

// Adding HistoryStats::Max ensures:
// ALL captures score higher than ALL non-captures!

// Without bonus:
Capture pawn:   100 (small)
Good quiet:     5000 (from history)
→ Quiet tried before capture! WRONG!

// With bonus:
Capture pawn:   100 + 268M = 268M+ (huge!)
Good quiet:     5000 (small)
→ All captures tried before quiets ✓
```

**Case 2: Non-Captures When in Check**


```cpp
else
    m.value = history[pos.moved_piece(m)][to_sq(m)]
            + fromTo.get(c, m);
```

**Same as quiet scoring** (but without continuation history):
- No `cm`, `fm`, `f2` (too expensive when in check)
- Just history + fromTo

**Why simpler?**
```
When in check:
- Need to respond quickly
- Usually few evasion moves available
- Don't need elaborate scoring
- Simple history + fromTo is sufficient
```

##### Comparison Table

| Feature | CAPTURES | QUIETS | EVASIONS |
|---------|----------|--------|----------|
| **Base score** | Victim value | History | MVV-LVA or History |
| **Rank penalty** | Yes (-200/rank) | No | No |
| **History** | No | Yes | Yes (non-captures) |
| **Continuation** | No | 3 levels | No |
| **FromTo** | No | Yes | Yes |
| **HistoryStats::Max** | No | No | Yes (captures) |
| **SEE** | Delayed | No | No |

---

##### Summary

**score\<CAPTURES\>()**
```
score = victim_value - (200 × relative_rank)

MVV ordering (most valuable victim first)
Rank penalty (prefer nearby captures)
SEE check delayed until move is picked
```

**score\<QUIETS\>()**
```
score = history[piece][to]
      + cm[piece][to]    (1 ply ago context)
      + fm[piece][to]    (2 plies ago context)
      + f2[piece][to]    (4 plies ago context)
      + fromTo[color][from][to]

Five statistical components for accurate ordering
```

**score\<EVASIONS\>()**
```
Captures: MVV-LVA + HistoryStats::Max
          (ensures all captures before non-captures)

Non-captures: history + fromTo
              (simple, fast ordering)

Key: HistoryStats::Max separates captures from quiets!
```

#### next_move

This is the heart of move ordering! It contains all 17 stages.

##### Stage Flow Overview

```
MAIN_SEARCH path:
1. MAIN_SEARCH → return TT move
2. CAPTURES_INIT → generate captures
3. GOOD_CAPTURES → return winning captures
4. KILLERS → return killer moves
5. COUNTERMOVE → return countermove
6. QUIET_INIT → generate quiet moves
7. QUIET → return quiet moves
8. BAD_CAPTURES → return losing captures

EVASION path (in check):
9. EVASION → return TT move
10. EVASIONS_INIT → generate evasions
11. ALL_EVASIONS → return all evasions

PROBCUT path:
12. PROBCUT → return TT move
13. PROBCUT_INIT → generate captures
14. PROBCUT_CAPTURES → return high-SEE captures

QSEARCH path:
15. QSEARCH_WITH_CHECKS/NO_CHECKS → return TT move
16. QCAPTURES → return captures
17. QCHECKS → return quiet checks (depth 0 only)
18. QRECAPTURES → return recaptures only
```

##### Stages 1-8: MAIN_SEARCH (Normal Search)

**Stage 1: Return TT Move**

```cpp
case MAIN_SEARCH:
    ++stage;
    return ttMove;
```


**Simple:** Try hash move first (90% cutoff rate!)
If ttMove == MOVE_NONE: Constructor already incremented stage, skips this.

**Stage 2: CAPTURES_INIT**

```cpp
case CAPTURES_INIT:
    endBadCaptures = cur = moves;
    endMoves = generate<CAPTURES>(pos, cur);
    score<CAPTURES>();
    ++stage;
    // Fall through to GOOD_CAPTURES
```

Generate all captures:

```cpp
endBadCaptures = moves  // Start of bad captures section
cur = moves             // Current pointer
endMoves = ...          // End of captures

// Memory layout:
[moves ... endBadCaptures ... endMoves)
```


**Score them:** MVV - rank_penalty
**No return** - falls through to next stage immediately.

**Stage 3: GOOD_CAPTURES (IMPORTANT!)**

```cpp
case GOOD_CAPTURES:
    while (cur < endMoves) {
        move = pick_best(cur++, endMoves);
        if (move != ttMove) {
            if (pos.see_ge(move, VALUE_ZERO))
                return move;  // Good capture!
            
            // Losing capture, save for later
            *endBadCaptures++ = move;
        }
    }
    // Falls through to killers
```

**Key behavior:**
1. Pick best capture by MVV-LVA
2. Skip if it's TT move (already tried)
3. **SEE check** (delayed from scoring)
   - SEE ≥ 0: Return (good capture)
   - SEE < 0: Save to bad captures array
4. Repeat until no more captures

**Memory after this stage:**
```
[Good (returned) | Bad Captures | (gap) | Remaining]
 ↑                ↑                      ↑
moves         endBadCaptures          endMoves
```
After all captures checked: Falls through to killers.

**Stage 4: KILLERS (First Killer)**

```cpp
case KILLERS:  // This actually handles first killer
    ++stage;
    move = ss->killers[0];
    if (   move != MOVE_NONE
        && move != ttMove
        && pos.pseudo_legal(move)
        && !pos.capture(move))
        return move;
    // Falls through to second killer
```

Validation checks:

- Exists (not MOVE_NONE)
- Not already tried (not ttMove)
- Legal in this position
- Not a capture (captures already tried)

Falls through if killer invalid.

**Stage 5: KILLERS (Second Killer)**

```cpp
// Second killer (no case label, falls through from above)
++stage;
move = ss->killers[1];
if (   move != MOVE_NONE
    && move != ttMove
    && pos.pseudo_legal(move)
    && !pos.capture(move))
    return move;
// Falls through to countermove
```

Same checks as first killer.

**Stage 6: COUNTERMOVE**

```cpp
case COUNTERMOVE:
    ++stage;
    move = countermove;
    if (   move != MOVE_NONE
        && move != ttMove
        && move != ss->killers[0]
        && move != ss->killers[1]
        && pos.pseudo_legal(move)
        && !pos.capture(move))
        return move;
    // Falls through to quiet init
```

Extra checks:

- Not killer[0] (avoid duplicate)
- Not killer[1] (avoid duplicate)

**Stage 7: QUIET_INIT (IMPORTANT!)**

```cpp
case QUIET_INIT:
    cur = endBadCaptures;  // Start after bad captures
    endMoves = generate<QUIETS>(pos, cur);
    score<QUIETS>();  // 5-component scoring
    
    if (depth < 3 * ONE_PLY) {
        // Shallow: only sort good quiets
        ExtMove* goodQuiet = std::partition(cur, endMoves, 
            [](const ExtMove& m) { return m.value > VALUE_ZERO; });
        insertion_sort(cur, goodQuiet);
    } else {
        // Deep: sort all quiets
        insertion_sort(cur, endMoves);
    }
    ++stage;
    // Falls through to QUIET
```

Key optimizations:

1. Generate after bad captures (reuse memory)
2. Shallow depth optimization:

**Stage 8: QUIET**

```cpp
case QUIET:
    while (cur < endMoves) {
        move = *cur++;
        if (  move != ttMove
           && move != ss->killers[0]
           && move != ss->killers[1]
           && move != countermove)
            return move;
    }
    ++stage;
    cur = moves;  // Reset to start
    // Falls through to BAD_CAPTURES
```

Return quiets in history order.
Skip duplicates: ttMove, killers, countermove already tried.
After exhausted: Prepare for bad captures.

**Stage 9: BAD_CAPTURES**

```cpp
case BAD_CAPTURES:
    if (cur < endBadCaptures)
        return *cur++;
    break;  // END of main search path
```

Finally try losing captures (SEE < 0).
Break - no more moves, return MOVE_NONE.

##### Stages 10-11: EVASION (In Check)

**Stage 10: EVASION (TT Move)**

```cpp
case EVASION:
    ++stage;
    return ttMove;
```

Same as MAIN_SEARCH stage 1.

**Stage 11: EVASIONS_INIT**

```cpp
case EVASIONS_INIT:
    cur = moves;
    endMoves = generate<EVASIONS>(pos, cur);
    score<EVASIONS>();  // MVV-LVA + Max or history
    ++stage;
    // Falls through to ALL_EVASIONS
```

Generate only evasion moves:

- King moves
- Block check
- Capture checking piece

**Stage 12: ALL_EVASIONS**

```cpp
case ALL_EVASIONS:
    while (cur < endMoves) {
        move = pick_best(cur++, endMoves);
        if (move != ttMove)
            return move;
    }
    break;  // END of evasion path
```

Return all evasions in score order.
Simpler than main search (no killers, no quiets/captures split).

##### Stages 13-14: PROBCUT

**Stage 13: PROBCUT (TT Move)**

```cpp
case PROBCUT:
    ++stage;
    return ttMove;
```

**Stage 14: PROBCUT_INIT**

```cpp
case PROBCUT_INIT:
    cur = moves;
    endMoves = generate<CAPTURES>(pos, cur);
    score<CAPTURES>();
    ++stage;
    // Falls through to PROBCUT_CAPTURES
```

**Stage 15: PROBCUT_CAPTURES**

```cpp
case PROBCUT_CAPTURES:
    while (cur < endMoves) {
        move = pick_best(cur++, endMoves);
        if (  move != ttMove
           && pos.see_ge(move, threshold + 1))
            return move;
    }
    break;  // END of probcut path
```

Only return captures with SEE > threshold.
Used for ProbCut pruning (test if beta cutoff likely).

##### Stages 16-19: QSEARCH (Quiescence)

**Stage 16: QSEARCH_WITH_CHECKS / QSEARCH_NO_CHECKS**

```cpp
case QSEARCH_WITH_CHECKS:
case QSEARCH_NO_CHECKS:
    ++stage;
    return ttMove;
```

Two entry points (different constructors).

**Stage 17: QCAPTURES_1_INIT / QCAPTURES_2_INIT**

```cpp
case QCAPTURES_1_INIT:
case QCAPTURES_2_INIT:
    cur = moves;
    endMoves = generate<CAPTURES>(pos, cur);
    score<CAPTURES>();
    ++stage;
    // Falls through
```

**Stage 18: QCAPTURES_1 / QCAPTURES_2**

```cpp
case QCAPTURES_1:
case QCAPTURES_2:
    while (cur < endMoves) {
        move = pick_best(cur++, endMoves);
        if (move != ttMove)
            return move;
    }
    
    if (stage == QCAPTURES_2)
        break;  // QSEARCH_NO_CHECKS ends here
    
    // QSEARCH_WITH_CHECKS continues:
    cur = moves;
    endMoves = generate<QUIET_CHECKS>(pos, cur);
    ++stage;
    // Falls through to QCHECKS
```

Two versions:

- QCAPTURES_1: With checks (continues to QCHECKS)
- QCAPTURES_2: No checks (breaks, ends search)

**Stage 19: QCHECKS**

```cpp
case QCHECKS:
    while (cur < endMoves) {
        move = cur++->move;  // No pick_best (already sorted)
        if (move != ttMove)
            return move;
    }
    break;  // END of qsearch with checks
```

Only in QSEARCH_WITH_CHECKS (depth 0).
Generate quiet checks: Non-capture moves that give check.

**Stage 20: QSEARCH_RECAPTURES**

```cpp
case QSEARCH_RECAPTURES:
    cur = moves;
    endMoves = generate<CAPTURES>(pos, cur);
    score<CAPTURES>();
    ++stage;
    // Falls through to QRECAPTURES
```

Deep quiescence (depth ≤ -5).

**Stage 21: QRECAPTURES**

```cpp
case QRECAPTURES:
    while (cur < endMoves) {
        move = pick_best(cur++, endMoves);
        if (to_sq(move) == recaptureSquare)
            return move;
    }
    break;  // END of recaptures only
```

**Only return captures on specific square.**


##### Summary by Path

**Main Search (Normal Position)
```
TT → Good Captures → Killer1 → Killer2 → Countermove → Quiets → Bad Captures
```

**Evasion (In Check)**
```
TT → All Evasions (sorted by MVV-LVA/history)
```

**ProbCut**
```
TT → High-SEE Captures only
```

**Quiescence (With Checks, depth=0)**
```
TT → Captures → Quiet Checks
```

**Quiescence (No Checks, depth=-1 to -4)**
```
TT → Captures only
```

**Quiescence (Recaptures, depth≤-5)******
```
Captures on specific square only
