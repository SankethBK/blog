---
title:  "Quiescent Search"
date:   2026-02-15
draft: false
categories: ["chess engines"]
tags: ["quiescent search"]
author: Sanketh
---

# Quiescent Search

## The Horizon Effect

The horizon effect is when a chess engine makes a terrible move because it can't see past its search depth limit.

It's like looking at a situation and thinking "This is fine!" when disaster is just one move beyond what you can see.

### Why Fixed-Depth Search Fails

Fixed-depth search stops at a specific depth, regardless of what's happening in the position.

```
Depth 10 search:
├─ Move 1, 2, 3, ... 10 ✓ Search these
└─ Move 11 ✗ STOP (even if critical!)
```

**Example 1: The Hanging Queen**

```
Position: White to move

♜ ♞ ♝ ♛ ♚ ♝ ♞ ♜
♟ ♟ ♟ ♟   ♟ ♟ ♟
        ♟      
    ♟          
        ♙      
            ♙  
♙ ♙ ♙ ♙   ♙   ♙
♖ ♘ ♗ ♕ ♔ ♗ ♘ ♖

Search to depth 8:

Depth 7: White plays Bxe5 (bishop takes pawn)
         "I won a pawn! +1.0"
         
Depth 8: Black's turn, but search STOPS
         Return evaluation: +1.0
         
Engine thinks: "Great move! I'm up a pawn."

Reality (depth 9):
Black plays Qxe5 (queen takes bishop)
Actual eval: -2.0 (lost a bishop for a pawn!)
```

The engine was "blind" to the recapture because it hit the horizon.

**Example 2: Delaying the Inevitable**

This is the classic horizon effect - pushing losses beyond the search depth.

```
Position: Black is getting mated in 5 moves

Instead of accepting mate, Black desperately gives checks:
├─ Qh4+ (check, forces King to move)
├─ Qh5+ (another check)  
├─ Qh6+ (another check)
└─ Gives up queen for rook
   → Now mated in 8 moves instead of 5

From depth 10 search perspective:
"If I don't give checks: mate in 5" (sees this)
"If I give checks: not mated yet at depth 10!" (doesn't see mate in 8)

Engine chooses to give useless checks!
```

The engine "pushes" the mate beyond the horizon, thinking it avoided it.

**Example 3: The Sacrificial Trap**

Engines might avoid sacrifices thinking they're losing material when necessary results (either capture or winning back more material) is not achieved in fixed depth.

**Key insight:** Some positions are quiet (safe to evaluate), others are not quiet (must keep searching).

### What Makes a Position "Quiet"?

#### Quiet Positions (Safe to Stop)

✓ No pieces hanging
✓ No checks
✓ No captures available
✓ No immediate threats
✓ Pieces safely defended

#### Unstable Positions (DON'T Stop!)

✗ Pieces hanging (undefended)
✗ In check
✗ Captures available
✗ Pieces attacked
✗ Tactical threats


## General Idea of Quiescent Search

```cpp
// Quiescence search function, which is called by the main search function with
// depth zero, or recursively with further decreasing depth. With depth <= 0, we
// "should" be using static eval only, but tactical moves may confuse the static eval.
// To fight this horizon effect, we implement this qsearch of tactical moves.
// See https://www.chessprogramming.org/Horizon_Effect
// and https://www.chessprogramming.org/Quiescence_Search
```

Static Eval means

- Calls `evaluate()` function
- Looks at current position only
- No lookahead, no move generation
- "Static" = not dynamic, doesn't change with search

> "At depth 0, we COULD just call evaluate() and return.
> But that would cause horizon effect!
> So instead, we use qsearch to try captures first."

**Qsearch makes recursive calls as well, just as minmax**

```cpp
value = -qsearch<nodeType>(pos, ss + 1, -beta, -alpha);
//       ↑ qsearch calls itself!
```

**Recursive flow:**
```cpp
search(depth=1)
└─ search(depth=0)
   └─ qsearch(depth=0) ← Entry point
      └─ Try Qxh7
         └─ qsearch(depth=-1) ← RECURSIVE CALL!
            └─ Try Kh8
               └─ qsearch(depth=-2) ← RECURSIVE CALL!
                  └─ No captures, return evaluate()
```

## Outline of Qsearch Algorithm

```cpp
qsearch(pos, ss, alpha, beta, depth):

├─ Step 1: Early Exits
│  ├─ Repetition draw check:
│  │  └─ if (upcoming_repetition && alpha < VALUE_DRAW)
│  │     └─ alpha = value_draw
│  │        └─ if (alpha >= beta) → return alpha
│  │
│  ├─ Draw/Max ply check:
│  │  └─ if (is_draw || ply >= MAX_PLY)
│  │     └─ return VALUE_DRAW or evaluate()
│  │
│  └─ Continue to Step 2
│
├─ Step 2: Transposition Table Probe
│  ├─ ttHit, ttData = TT.probe(posKey)
│  ├─ Extract TT move, value, bound
│  │
│  ├─ TT cutoff check (non-PV nodes):
│  │  └─ if (!PvNode && ttDepth >= DEPTH_QS && valid_bound)
│  │     └─ return ttData.value ← Early exit!
│  │
│  └─ Continue to Step 3
│
├─ Step 3: Stand Pat Evaluation
│  │
│  ├─ Case A: In Check
│  │  └─ bestValue = -VALUE_INFINITE (can't stand pat)
│  │     └─ Must try evasion moves
│  │
│  ├─ Case B: Not in Check
│  │  ├─ staticEval = evaluate(pos) or ttData.eval
│  │  ├─ bestValue = staticEval (+ corrections)
│  │  │
│  │  ├─ Stand pat cutoff:
│  │  │  └─ if (bestValue >= beta)
│  │  │     ├─ Save to TT (BOUND_LOWER)
│  │  │     └─ return bestValue ← Exit! (position already good)
│  │  │
│  │  ├─ Raise alpha:
│  │  │  └─ if (bestValue > alpha)
│  │  │     └─ alpha = bestValue (new minimum)
│  │  │
│  │  └─ futilityBase = staticEval + 359
│  │
│  └─ Continue to Step 4
│
├─ Step 4: Move Generation
│  ├─ MovePicker mp(pos, ttMove, DEPTH_QS, ...)
│  │  ├─ Generates: Captures (and checks if depth=0)
│  │  └─ Orders by: MVV-LVA
│  │
│  └─ Continue to Step 5
│
├─ Step 5-8: Move Loop
│  │
│  └─ while (move = mp.next_move()):
│     │
│     ├─ Legality check:
│     │  └─ if (!legal(move)) → continue
│     │
│     ├─ Step 6: Pruning Checks
│     │  │
│     │  ├─ Move count pruning:
│     │  │  └─ if (moveCount > 2 && !givesCheck && ...)
│     │  │     └─ continue ← Skip
│     │  │
│     │  ├─ Futility pruning:
│     │  │  ├─ futilityValue = futilityBase + PieceValue[captured]
│     │  │  └─ if (futilityValue <= alpha)
│     │  │     ├─ bestValue = max(bestValue, futilityValue)
│     │  │     └─ continue ← Skip (won't raise alpha)
│     │  │
│     │  ├─ SEE pruning (captures):
│     │  │  └─ if (!see_ge(move, alpha - futilityBase))
│     │  │     └─ continue ← Skip (loses material)
│     │  │
│     │  ├─ History pruning (quiet checks):
│     │  │  └─ if (bad_history && !capture)
│     │  │     └─ continue ← Skip
│     │  │
│     │  └─ Final SEE check:
│     │     └─ if (!see_ge(move, -75))
│     │        └─ continue ← Skip (too bad)
│     │
│     ├─ Step 7: Make Move and Recurse
│     │  ├─ do_move(move)
│     │  ├─ nodes++
│     │  ├─ ss->currentMove = move
│     │  │
│     │  ├─ RECURSIVE CALL:
│     │  │  └─ value = -qsearch(pos, ss+1, -beta, -alpha)
│     │  │     │
│     │  │     └─ [Entire qsearch runs recursively!]
│     │  │        ├─ depth = -1, -2, -3, ...
│     │  │        └─ Eventually returns when quiet
│     │  │
│     │  └─ undo_move(move)
│     │
│     └─ Step 8: Update Best Value
│        │
│        ├─ if (value > bestValue):
│        │  ├─ bestValue = value
│        │  │
│        │  └─ if (value > alpha):
│        │     ├─ bestMove = move
│        │     ├─ Update PV
│        │     │
│        │     ├─ if (value < beta):
│        │     │  └─ alpha = value ← Raise alpha
│        │     │
│        │     └─ else:
│        │        └─ break ← Beta cutoff! Exit loop
│        │
│        └─ Continue to next move
│
├─ Step 9: After Move Loop
│  │
│  ├─ Checkmate detection:
│  │  └─ if (inCheck && bestValue == -VALUE_INFINITE)
│  │     └─ return mated_in(ply) ← No legal moves when in check
│  │
│  └─ Continue to Step 10
│
└─ Step 10: Save to TT and Return
   ├─ Determine bound:
   │  └─ bound = (bestValue >= beta) ? BOUND_LOWER : BOUND_UPPER
   │
   ├─ TT.write(posKey, bestValue, bound, DEPTH_QS, bestMove, ...)
   │
   └─ return bestValue
```

### Key Patterns to Remember

```
Pattern 1: Stand Pat Cutoff
├─ evaluate() >= beta
└─ return immediately (no captures tried)

Pattern 2: Stand Pat Raises Alpha
├─ evaluate() > alpha
├─ alpha = evaluate()
└─ Captures must beat this to be interesting

Pattern 3: Good Capture Found
├─ Capture improves position
├─ value > alpha
├─ Update alpha, bestMove
└─ Continue or cutoff

Pattern 4: All Captures Pruned
├─ Futility, SEE, History checks fail
├─ No captures tried
└─ return stand pat value (bestValue)

Pattern 5: Recursion Depth
├─ depth: 0, -1, -2, -3, -4, ...
├─ Continues until position quiet
└─ Eventually stand pat or no captures
```

## The Code

```cpp
template<NodeType nodeType>
Value Search::Worker::qsearch(Position& pos, Stack* ss, Value alpha, Value beta) {

    static_assert(nodeType != Root);
    constexpr bool PvNode = nodeType == PV;

    assert(alpha >= -VALUE_INFINITE && alpha < beta && beta <= VALUE_INFINITE);
    assert(PvNode || (alpha == beta - 1));
```

nodeType is a **template** parameter, not a runtime variable.

That means:
Compiler generates separate versions of this function for:
- PV
- NonPV

So this function exists twice in the binary.

**What is static_assert?**

```cpp
static_assert(nodeType != Root);
```

This is a compile-time assertion.

It checks a condition during compilation, not at runtime.

If the condition is false → compilation fails.

In this case:

It ensures:

> qsearch is never instantiated with nodeType == Root.

Because:
- Root nodes are only used in normal search.
- Qsearch never runs at root.

**What is this line?**

```cpp
constexpr bool PvNode = nodeType == PV;
```

Why constexpr?

Because nodeType is a template parameter.

So nodeType == PV can be evaluated at compile time.

Therefore `PvNode` is a compile-time constant.

- Not runtime.
- Not stored.
- No branching cost.

This allows later code like:

```cpp
if constexpr (PvNode)
```

or even:

```cpp
assert(PvNode || (alpha == beta - 1));
```

to behave differently depending on node type.

**The assertions**

```cpp
assert(alpha >= -VALUE_INFINITE && alpha < beta && beta <= VALUE_INFINITE);
```

This is a runtime assertion.

It ensures:
- Alpha and beta are valid
- Alpha < beta
- Bounds are within legal score range

This protects search correctness.

```cpp
assert(PvNode || (alpha == beta - 1));
```

This is very important.

It says:

> If this is NOT a PV node,
> then the search window must be null-window.


### Section 1: Setup and Early Exits

```cpp
// Check if we have an upcoming move that draws by repetition
if (alpha < VALUE_DRAW && pos.upcoming_repetition(ss->ply))
{
    alpha = value_draw(this->nodes);
    if (alpha >= beta)
        return alpha;
}
```

**Repetition detection:** If we can force a draw by repetition, use it to raise alpha.

```cpp
// Step 2. Check for an immediate draw or maximum ply reached
if (pos.is_draw(ss->ply) || ss->ply >= MAX_PLY)
    return (ss->ply >= MAX_PLY && !ss->inCheck) ? evaluate(pos) : VALUE_DRAW;
```

Safety checks:

- 50-move rule, insufficient material, etc.
- Maximum search depth (prevent stack overflow)

### Section 2: Transposition Table Probe

```cpp
// Step 3. Transposition table lookup
posKey = pos.key();
auto [ttHit, ttData, ttWriter] = tt.probe(posKey);
ttData.move  = ttHit ? ttData.move : Move::none();
ttData.value = ttHit ? value_from_tt(ttData.value, ss->ply, pos.rule50_count()) : VALUE_NONE;
```


**Same as normal search:**

- Check if we've seen this position before
- Extract TT move (try it first)
- Adjust mate scores for current ply

```cpp
// At non-PV nodes we check for an early TT cutoff
if (!PvNode && ttData.depth >= DEPTH_QS
    && is_valid(ttData.value)
    && (ttData.bound & (ttData.value >= beta ? BOUND_LOWER : BOUND_UPPER)))
    return ttData.value;
```

TT cutoff:

- Non-PV nodes can use TT value directly
- Must be searched to at least quiescence depth
- Bound must allow the cutoff

### Section 3: Stand Pat (THE KEY CONCEPT!)

```cpp
// Step 4. Static evaluation of the position
if (ss->inCheck)
    bestValue = futilityBase = -VALUE_INFINITE;
else
{
    // Get static evaluation (from TT or compute)
    if (ss->ttHit)
        unadjustedStaticEval = ttData.eval;
    else
        unadjustedStaticEval = evaluate(pos);
    
    ss->staticEval = bestValue = 
        to_corrected_static_eval(unadjustedStaticEval, correctionValue);
    
    // Stand pat. Return immediately if static value is at least beta
    if (bestValue >= beta)
    {
        // Save to TT and return
        return bestValue;
    }
    
    if (bestValue > alpha)
        alpha = bestValue;
}
```

**Stand Pat Explained
This is what makes qsearch different from normal search!**

```cpp
// Normal search:
// MUST try at least one move
for (move in moves) { ... }

// Quiescence:
// Can choose to NOT capture anything!
bestValue = evaluate(pos);  // "I stand pat"

if (bestValue >= beta)
    return beta;  // Position is already good enough!

if (bestValue > alpha)
    alpha = bestValue;  // Raise the bar for captures
```

**Why stand pat?**
```
Position: We're up a queen
Static eval: +900 (huge advantage)
Alpha: -50
Beta: +50

Stand pat check:
if (+900 >= +50)  // YES!
    return +900

No need to try captures!
We're already winning by so much that
even if opponent has good captures,
they can't bring score below beta.
```

**When in check:** Can't stand pat (must move!)
```cpp
if (ss->inCheck)
    bestValue = -VALUE_INFINITE;  // Must try evasions
```

### Section 4: Futility Base

```cpp
futilityBase = ss->staticEval + 359;
```

**This sets up futility pruning** (explained in move loop).

**Idea:** 

If static eval + captured piece value < alpha
→ This capture probably won't raise alpha
→ Skip it (prune)

The +359 is a margin (roughly 3.5 pawns)

### Section 5: Move Loop Setup

```cpp
// Initialize MovePicker for quiescence
MovePicker mp(pos, ttData.move, DEPTH_QS, ...);

// Step 5. Loop through all pseudo-legal moves
while ((move = mp.next_move()) != Move::none())
{
    if (!pos.legal(move))
        continue;
    
    givesCheck = pos.gives_check(move);
    capture = pos.capture_stage(move);
    moveCount++;
```

**MovePicker in qsearch:**

- Constructor uses `DEPTH_QS` (quiescence mode)
- Only generates captures (and checks at depth 0)
- Orders by MVV-LVA

### Section 6: Pruning (THE OPTIMIZATIONS!)

This block decides:

> “Is this move worth searching fully?”

It applies multiple cheap filters before doing expensive recursive search.

The pruning layers here are:
	1.	Futility pruning
	2.	Move-count pruning
	3.	SEE-based pruning
	4.	Continuation history pruning
	5.	Hard SEE threshold pruning

All inside:

```cpp
if (!is_loss(bestValue))
```

Meaning:

> Only prune if we haven’t already found a forced loss.

If the position is already terrible, pruning becomes unsafe.

#### Part 1 — Entry Conditions

```cpp
if (!givesCheck && move.to_sq() != prevSq && !is_loss(futilityBase)
    && move.type_of() != PROMOTION)
```

We only prune if:
- Move does NOT give check (checks are tactical)
- Not a recapture square (recaptures are important)
- Futility base itself isn’t already losing
- Not a promotion (promotions are tactical)

So this pruning only applies to quiet / non-critical moves.

#### Part 2 — Move Count Pruning

```cpp
if (moveCount > 2)
    continue;
```

After 2 moves already tried:

Later moves are assumed weak.

This is late move pruning (LMP).

If you’re the 3rd+ quiet move,
and no tactical signs,
skip.


#### Futility Pruning

Futility pruning is based on this idea:

> If even after adding some optimistic margin, this move cannot possibly raise alpha — don’t search it.

```cpp
// Futility pruning
if (!givesCheck && move.to_sq() != prevSq 
    && !is_loss(futilityBase) && move.type_of() != PROMOTION)
{
    // Move count pruning: only try first 2 moves
    if (moveCount > 2)
        continue;
    
    Value futilityValue = futilityBase + PieceValue[pos.piece_on(move.to_sq())];
    
    // If static eval + captured piece << alpha, skip
    if (futilityValue <= alpha)
    {
        bestValue = std::max(bestValue, futilityValue);
        continue;  // Prune!
    }
}
```

At shallow depths, especially near leaf nodes, we can say:

```cpp
staticEval + margin < alpha
```

If that’s true, the move is probably hopeless.

So we skip it.

**Why It’s Safe (Mostly)**

At low depth (e.g., depth 1 or 2):

If static position is bad,
and move is quiet,
and margin is small,

chances are very high it won’t suddenly jump above alpha.

So pruning saves a ton of nodes.

**Why It’s Dangerous**

If margin too small:
- You prune winning moves

If margin too large:
- You prune nothing

So tuning futility margins is critical.


**Example:**
```
Static eval: +100
Alpha: +300
Capturing pawn (value 100)

futilityValue = 100 + 100 = +200

if (+200 <= +300)  // YES
    continue;  // Skip this capture

Why? Even if we capture the pawn,
we're at +200, still below alpha (+300).
Unlikely to improve our position enough.
```

#### Part 3 — Futility Value Test

```cpp
Value futilityValue = futilityBase + PieceValue[pos.piece_on(move.to_sq())];
```

This estimates:

> Best case outcome if we capture the piece on target square.

Then:

> if (futilityValue <= alpha)

Meaning:

Even optimistically, this move cannot beat alpha.

So prune.

But:

```cpp
bestValue = std::max(bestValue, futilityValue);
```

This is subtle.

Even though we prune,
we update bestValue so the node returns something reasonable.

This is fail-soft behavior.

#### SEE Pruning

```cpp
// If static exchange evaluation is too low, prune
if (!pos.see_ge(move, alpha - futilityBase))
{
    bestValue = std::min(alpha, futilityBase);
    continue;
}
```

**Example:**
```
Alpha: +300
FutilityBase: +150
Threshold: 300 - 150 = +150

Capture Bxe5 has SEE = -200 (lose bishop for pawn)

if (!see_ge(Bxe5, +150))  // SEE = -200, fails
    continue;  // Prune bad capture
```

#### Part 4 — SEE-based Futility

```cpp
if (!pos.see_ge(move, alpha - futilityBase))
```

This asks:

> Does static exchange evaluation suggest this move is too bad?

alpha - futilityBase represents how much gain we need.

If SEE says we cannot even gain that much,
skip.

This is a more precise tactical filter than static futility.


#### Part 5 — Continuation History Pruning

```cpp
if (!capture
    && history score <= 6290)
    continue;
```

This means:

If move historically performs badly,
skip it.

Continuation history tracks:

> “When previous move was X, this move Y was bad.”

If cumulative history score is low,
we assume move is unlikely good.

So prune.

This is learned pruning.


**Why All These Layers?**

Because search is exponential.

Each layer removes:
- Hopeless quiet moves
- Losing tactical moves
- Historically bad continuations
- Late weak moves

Without these,
Stockfish would search billions more nodes.

**Why Wrapped Inside !is_loss(bestValue)?**

If bestValue already indicates:

> “We are getting mated”

Then pruning becomes dangerous.

We must search more thoroughly to find escapes.

So pruning is disabled in losing situations.


### Section 7: Make Move and Recurse

```cpp
// Step 7. Make and search the move
Piece movedPiece = pos.moved_piece(move);

do_move(pos, move, st, givesCheck);
thisThread->nodes.fetch_add(1, std::memory_order_relaxed);

ss->currentMove = move;
// ... update continuation history pointers ...

value = -qsearch<nodeType>(pos, ss + 1, -beta, -alpha);

undo_move(pos, move);
```

**Standard negamax recursion:**
- Make the move
- Recursively call qsearch (NOTE: qsearch calls itself!)
- Negate the result
- Undo the move

**Identify the moved piece**

```cpp
Piece movedPiece = pos.moved_piece(move);
```

Why before do_move?

Because after do_move, the board changes.
We need the original piece type for history updates.

**Make the move**

```cpp
do_move(pos, move, st, givesCheck);
```

This:
- Updates board
- Updates hash
- Updates material
- Updates rule50
- Updates checkers
- Updates pinned pieces
- Pushes new StateInfo (st)

Important:
Search always works by:
- Make move
- Recurse
- Undo move

No board copies.

**Increment node counter**

```cpp
thisThread->nodes.fetch_add(1, std::memory_order_relaxed);
```

Counts visited nodes.

memory_order_relaxed is used because:
- We don’t need strict memory ordering
- Just approximate counting
- Faster atomic increment

**Update search stack fields**

```cpp
ss->currentMove = move;
```

The stack (ss) stores per-ply search data.

Now we record:

> “At this ply, we are searching this move.”

This is used for:
- Killer updates
- Countermove learning
- Singular extensions
- LMR decisions

**Continuation History**

```cpp
ss->continuationHistory =
  &thisThread->continuationHistory[ss->inCheck][capture][movedPiece][move.to_sq()];
```

This is advanced move ordering learning.

It means:

> Given previous move context, how good is this follow-up move historically?

Dimensions include:
- Was previous node in check?
- Was previous move a capture?
- What piece moved?
- To which square?

It allows the engine to learn patterns like:

> “After opponent plays e4, d5 is often strong.”

**Continuation Correction History**

```cpp
ss->continuationCorrectionHistory =
  &thisThread->continuationCorrectionHistory[movedPiece][move.to_sq()];
```

This adjusts static evaluation biases based on move patterns.

It slightly corrects eval errors discovered during search.

This is part of modern Stockfish tuning.

**Recursive Call**

```cpp
value = -qsearch<nodeType>(pos, ss + 1, -beta, -alpha);
```

This is classic negamax form.

Important things happening:
- We negate score (because opponent’s perspective)
- We pass `ss + 1` → next ply stack frame
- Window becomes `(-beta, -alpha)`

This is alpha-beta inversion.

**Undo move**

```cpp
undo_move(pos, move);
```

Restores:
- Board
- Hash
- Material
- StateInfo
- Checkers
- etc.

Everything returns exactly as before.

### Section 8: Update Best Move

```cpp
// Step 8. Check for a new best move
if (value > bestValue)
{
    bestValue = value;
    
    if (value > alpha)
    {
        bestMove = move;
        
        if (PvNode)
            update_pv(ss->pv, move, (ss + 1)->pv);
        
        if (value < beta)
            alpha = value;  // Raise alpha
        else
            break;  // Beta cutoff!
    }
}
```

Standard alpha-beta update:

- New best? Update bestValue
- Exceeds alpha? Update alpha and bestMove
- Exceeds beta? Cutoff, stop searching

We just finished:

```cpp
value = -qsearch(...)
```

Now we compare it.

**Did this move beat the previous best?**

```cpp
if (value > bestValue)
```

This is purely local bookkeeping.

bestValue tracks the best score among moves tried so far at this node.

If true:
- This move becomes the best move so far.

**Did it beat alpha?**

```cpp
if (value > alpha)
```

This is the important alpha-beta condition.

If value ≤ alpha:
- Move is worse than what we already had.
- Ignore it (but still may be bestValue locally).

If value > alpha:
- This move improves the lower bound.
- It might become part of the PV.

**B. Update PV (only for PV nodes)**

```cpp
if (PvNode)
    update_pv(ss->pv, move, (ss + 1)->pv);
```

This builds the principal variation.

Conceptually:

```cpp
current PV = move + child PV
```

So:

If child PV is:

```cpp
[d5, g3, Bg7]
```

And move is:
```cpp
Nf3
```

Then PV becomes:

```cpp
[Nf3, d5, g3, Bg7]
```

Only done in PV nodes because only PV nodes track exact line.

**Check for Beta Cutoff**

```cpp
if (value < beta)
    alpha = value;
else
    break;  // Beta cutoff!
```

**Case A: value < beta**

This means:

```
alpha < value < beta
```

So:
- This move improves alpha
- But does not exceed beta
- Continue searching other moves

Alpha is raised:
```
alpha = value;
```
Window narrows.

**Case B: value ≥ beta**

This is fail-high.

Meaning:

> This move is so good that opponent will never allow this branch.

So stop searching remaining moves.

This is beta cutoff.

### Section 9: Checkmate Detection

```cpp
// Step 9. Check for mate
if (ss->inCheck && bestValue == -VALUE_INFINITE)
{
    assert(!MoveList<LEGAL>(pos).size());
    return mated_in(ss->ply);
}
```

**Edge case:**

In check, no legal moves (including evasions)
→ Checkmate!
→ Return mate score

This section:
	1.	Detects mate
	2.	Applies a small fail-soft correction
	3.	Writes to the transposition table
	4.	Returns the final score


**Mate Detection**

```cpp
if (ss->inCheck && bestValue == -VALUE_INFINITE)
```

This means:
- We were in check at this node
- No move ever improved bestValue
- So no legal moves were found

Because if any legal move existed,
bestValue would have been updated.

So:
> In check + no legal moves = checkmate


Safety check
```cpp
assert(!MoveList<LEGAL>(pos).size());
```

Just double-verifying that there are no legal moves.


Return mate score

```cpp
return mated_in(ss->ply);
```

This returns something like:

```cpp
-32000 + ply
```

Meaning:
- We are getting mated
- Distance matters
- Closer mate is worse

Mate scores are always distance-adjusted.

**Fail-Soft Adjustment**

```cpp
if (!is_decisive(bestValue) && bestValue > beta)
    bestValue = (bestValue + beta) / 2;
```

This is subtle.

This only happens if:
- Not a mate score
- bestValue exceeded beta

So this is a fail-high case.

In fail-soft search,
value can exceed beta.

But extremely large values can:
- Destabilize aspiration windows
- Cause oscillations

So Stockfish compresses it slightly:

Instead of returning raw value,
it returns something closer to beta.

This stabilizes search.

**Transposition Table Write**

```cpp
ttWriter.write(
    posKey,
    value_to_tt(bestValue, ss->ply),
    pvHit,
    bestValue >= beta ? BOUND_LOWER : BOUND_UPPER,
    DEPTH_QS,
    bestMove,
    unadjustedStaticEval,
    tt.generation());
```

This stores:

**Key**

```cpp
posKey
```

Zobrist hash of position.

**Value (adjusted)**

```cpp
value_to_tt(bestValue, ss->ply)
```

This adjusts mate scores by ply.

Important:
Mate scores must be stored relative to node.

Otherwise distance breaks when reused.

**PV flag**

```cpp
pvHit
```

Indicates if this node was PV.

Used for replacement decisions.

**Bound type**

```cpp
bestValue >= beta ? BOUND_LOWER : BOUND_UPPER
```

If we failed high:
→ Lower bound

Else:
→ Upper bound

Notice:
Qsearch rarely stores EXACT bounds.

Because usually it operates in null-window.

**Depth**

```
DEPTH_QS
```

This tells TT:

> This entry is quiescence depth only.

Not full depth.

So full search can overwrite it.

**Best move**

```
bestMove
```

For move ordering next time.

**Static eval**

```
unadjustedStaticEval
```

Stored separately for:
- Reverse futility
- Null move pruning
- Other heuristics

**Generation**

Used for aging entries.

**Final Return**

```cpp
return bestValue;
```

Now the node returns to parent.
