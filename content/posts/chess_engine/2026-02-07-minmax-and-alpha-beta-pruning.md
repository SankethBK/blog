---
title:  "Minmax with Alpha Beta Pruning"
date:   2026-02-07
draft: false
categories: ["chess engines"]
tags: ["minmax", "alpha-beta pruning", "negamax"]
author: Sanketh
---

# Minmax with Alpha Beta Pruning

## Game Tree Search

### The Goal of a Chess Engine

A chess engine is solving:

> “Given a position, what move leads to the best possible future?”

But the engine cannot know the future, so it simulates it.

This simulation is called search.



### The Game Tree 

Every legal move creates a new position.
From that position, the opponent also has moves.

This forms a tree:

```
Position
 ├── Move A
 │    ├── Opp Move A1
 │    │     ├── Move A1a
 │    │     └── Move A1b
 │    └── Opp Move A2
 │          └── ...
 └── Move B
      └── ...
```

This is called the game tree.

### Evaluation Function

We cannot search until checkmate (too big).
So at some depth we stop and estimate who is better

```cpp
evaluate(position) → score
+ positive = good for white
+ negative = good for black
```

We can also think of it as static evaluation function, because it generates a score just by looking at the current board with no look ahead.

Example:

```
+1.20  → White is winning
-0.50  → Black slightly better
0.00   → Equal
```

## The Minimax Principle

- Max player (White): tries to maximize the score
- Min player (Black): tries to minimize the score
- Each player assumes the opponent plays optimally
- At each ply, we alternate between max and min

```js
function minimax(position, depth, isMaximizingPlayer):
    if depth == 0 or position.isGameOver():
        return evaluate(position)
    
    if isMaximizingPlayer:
        maxEval = -INFINITY
        for each move in position.getLegalMoves():
            newPosition = position.makeMove(move)
            eval = minimax(newPosition, depth - 1, false)
            maxEval = max(maxEval, eval)
        return maxEval
    else:
        minEval = +INFINITY
        for each move in position.getLegalMoves():
            newPosition = position.makeMove(move)
            eval = minimax(newPosition, depth - 1, true)
            minEval = min(minEval, eval)
        return minEval
```

Example

```
Root Position (White to move, MAX, depth=2)
Score: ?
│
├── Move A: Nf3
│   │
│   ├── Black Move A1: d5 (MIN, depth=1)
│   │   Score: ?
│   │   │
│   │   ├── White Move A1a: d4 (MAX, depth=0) 
│   │   │   └── [EVAL: +0.3] ← Static evaluation here!
│   │   │
│   │   └── White Move A1b: e3 (MAX, depth=0)
│   │       └── [EVAL: +0.1] ← Static evaluation here!
│   │   
│   │   → MIN picks lowest: min(+0.3, +0.1) = +0.1
│   │
│   └── Black Move A2: e5 (MIN, depth=1)
│       Score: ?
│       │
│       ├── White Move A2a: d4 (MAX, depth=0)
│       │   └── [EVAL: +0.5] ← Static evaluation here!
│       │
│       └── White Move A2b: Nc3 (MAX, depth=0)
│           └── [EVAL: +0.2] ← Static evaluation here!
│       
│       → MIN picks lowest: min(+0.5, +0.2) = +0.2
│   
│   → MAX at Move A picks highest: max(+0.1, +0.2) = +0.2
│
├── Move B: e4
│   │
│   ├── Black Move B1: c5 (MIN, depth=1)
│   │   Score: ?
│   │   │
│   │   ├── White Move B1a: Nf3 (MAX, depth=0)
│   │   │   └── [EVAL: +0.4] ← Static evaluation here!
│   │   │
│   │   └── White Move B1b: d4 (MAX, depth=0)
│   │       └── [EVAL: +0.6] ← Static evaluation here!
│   │   
│   │   → MIN picks lowest: min(+0.4, +0.6) = +0.4
│   │
│   └── Black Move B2: e5 (MIN, depth=1)
│       Score: ?
│       │
│       ├── White Move B2a: Nf3 (MAX, depth=0)
│       │   └── [EVAL: +0.3] ← Static evaluation here!
│       │
│       └── White Move B2b: Bc4 (MAX, depth=0)
│           └── [EVAL: +0.5] ← Static evaluation here!
│       
│       → MIN picks lowest: min(+0.3, +0.5) = +0.3
│   
│   → MAX at Move B picks highest: max(+0.4, +0.3) = +0.4
│
└── Move C: d4
    │
    ├── Black Move C1: d5 (MIN, depth=1)
    │   Score: ?
    │   │
    │   ├── White Move C1a: c4 (MAX, depth=0)
    │   │   └── [EVAL: +0.2] ← Static evaluation here!
    │   │
    │   └── White Move C1b: Nf3 (MAX, depth=0)
    │       └── [EVAL: +0.1] ← Static evaluation here!
    │   
    │   → MIN picks lowest: min(+0.2, +0.1) = +0.1
    │
    └── Black Move C2: Nf6 (MIN, depth=1)
        Score: ?
        │
        ├── White Move C2a: c4 (MAX, depth=0)
        │   └── [EVAL: +0.3] ← Static evaluation here!
        │
        └── White Move C2b: Nc3 (MAX, depth=0)
            └── [EVAL: +0.4] ← Static evaluation here!
        
        → MIN picks lowest: min(+0.3, +0.4) = +0.3
    
    → MAX at Move C picks highest: max(+0.1, +0.3) = +0.3

FINAL DECISION at Root:
White chooses: max(+0.2, +0.4, +0.3) = +0.4
→ Best move: e4 (Move B)
```

## Alpha-Beta Pruning

### The Problem with Plain Minimax

Plain minimax explores every node in the tree, even when we already know some branches won't affect the final decision.

**Example:** You're looking at move options. You found one that guarantees you a score of +5. Then you start looking at another move, and the opponent's first response gives you -3. Do you need to check the opponent's other responses? NO! You already have +5, so you won't opponent to play this move in the first place.

This optimization is called Alpha-Beta Pruning.

### The Two Parameters

**Alpha (α):** The best score MAX can guarantee so far

- Best score the maximizing side (us) is GUARANTEED so far
- Starts at -∞
- Only MAX updates it (increases it)
- Represents MAX's "floor" - the worst MAX will accept

**Beta (β):** The best score MIN can guarantee so far

- Best score the minimizing side (opponent) is GUARANTEED so far
- Starts at +∞
- Only MIN updates it (decreases it)
- Represents MIN's "ceiling" - the worst MIN will accept

So at any node:

> The true value of the position must lie inside [α, β]

If we ever prove it lies outside this window → stop searching
because parent will never choose it.

### The Two Types of Pruning

There are two different situations where we prune, depending on which player discovers the cutoff:

#### 1. Beta Cutoff 

Occurs at a node where opponent is choosing (minimizing node).

**Meaning**

We found a move so good for us
that opponent will NEVER allow reaching this position.

**Example**

We are evaluating Move A at root.

We already have:

```cpp
alpha = +2   (we can get +2 elsewhere)
```

Now inside this branch opponent analyzes a reply:

```cpp
position score = +5 for us
```

Opponent says:

> “Nope. I will never play a move that gives you +5 when I can choose another line giving you +2.”

So this branch is irrelevant.

Therefore:

```cpp
score >= beta  →  BETA CUTOFF
```

#### 2. Alpha Cutoff 

Occurs at a node where we are choosing (maximizing node).

**Meaning**

We found a move so bad
that we will never play this line.

**Example**

Opponent already has a line giving us:

```cpp
beta = -4
```

Now we analyze another continuation and find:

```cpp
score = -7
```

#### Pseudocode

```js
function alphaBeta(position, depth, alpha, beta, isMaximizingPlayer):
    if depth == 0 or position.isGameOver():
        return evaluate(position)
    
    if isMaximizingPlayer:
        maxEval = -INFINITY
        for each move in position.getLegalMoves():
            newPosition = position.makeMove(move)
            eval = alphaBeta(newPosition, depth - 1, alpha, beta, false)
            maxEval = max(maxEval, eval)
            
            alpha = max(alpha, eval)          // ← MAX updates alpha
            if beta <= alpha:                 // ← Pruning condition
                break  // Beta cutoff: MIN won't allow this path
                
        return maxEval
        
    else:  // Minimizing player
        minEval = +INFINITY
        for each move in position.getLegalMoves():
            newPosition = position.makeMove(move)
            eval = alphaBeta(newPosition, depth - 1, alpha, beta, true)
            minEval = min(minEval, eval)
            
            beta = min(beta, eval)            // ← MIN updates beta
            if beta <= alpha:                 // ← Pruning condition
                break  // Alpha cutoff: MAX won't allow this path
                
        return minEval

// Initial call from root
bestMove = alphaBeta(position, MAX_DEPTH, -INFINITY, +INFINITY, true)
```

## Negamax - A Simpler Way to Write Minimax

Negamax is not a different algorithm - it's just a cleaner way to write minimax.

Instead of having separate logic for MAX and MIN players, negamax exploits a mathematical symmetry:

> "Your best move is my worst move (negated)"


### The Key Insight

In chess (and most zero-sum games):
- What's good for White (+5) is equally bad for Black (-5)
- White maximizes the score
- Black minimizes the score

But we can flip the perspective:
- **From White's view:** position scores +5
- **From Black's view:** same position scores -5

So instead of:

```
White (MAX): pick maximum
Black (MIN): pick minimum
```

We can do:

```
Current player: pick maximum FROM THEIR PERSPECTIVE
Opponent: negate the score to flip perspective
```

### Minimax vs Negamax - Side by Side

**Regular Minimax**

```js
function minimax(position, depth, isMaximizingPlayer):
    if depth == 0:
        return evaluate(position)
    
    if isMaximizingPlayer:  // White's turn
        maxEval = -INFINITY
        for each move in position.getLegalMoves():
            eval = minimax(makeMove(move), depth - 1, false)
            maxEval = max(maxEval, eval)
        return maxEval
        
    else:  // Black's turn
        minEval = +INFINITY
        for each move in position.getLegalMoves():
            eval = minimax(makeMove(move), depth - 1, true)
            minEval = min(minEval, eval)
        return minEval
```

**Negamax - Simplified!**

```js
function negamax(position, depth, color):
    if depth == 0:
        return color * evaluate(position)  # ← Flip perspective!
    
    maxEval = -INFINITY
    for each move in position.getLegalMoves():
        eval = -negamax(makeMove(move), depth - 1, -color)  // ← Negate!
        maxEval = max(maxEval, eval)
    
    return maxEval


// Initial call
// color = +1 for White (maximizing)
// color = -1 for Black (minimizing)
bestScore = negamax(position, depth, +1)
```

**Why Negate the Recursive Call?**

```cpp
eval = -negamax(...)
```

Think of it as **switching perspective**:
- Child node returns score from their perspective
- We want score from our perspective
- Our best = opponent's worst
- So we negate!

**Example:**

Black finds a position worth -5 from White's view
→ From Black's view, that's +5 (good for Black!)
→ Negamax returns +5 to Black
→ White receives -5 (bad for White, correctly)

Let's trace a simple tree:
```
Position (White to move, color=+1, depth=2)
│
├── Move A
│   │
│   └── Position after A (Black to move, color=-1, depth=1)
│       │
│       ├── Move A1
│       │   └── [EVAL from White's view: +3]
│       │       color=-1, so return: -1 * (+3) = -3
│       │       To White (parent): -(-3) = +3
│       │
│       └── Move A2
│           └── [EVAL from White's view: +1]
│               color=-1, so return: -1 * (+1) = -1
│               To White (parent): -(-1) = +1
│       
│       Black picks max(-3, -1) = -1 (best for Black)
│       Return to White: -(-1) = +1
│
└── Move B
    │
    └── Position after B (Black to move, color=-1, depth=1)
        │
        ├── Move B1
        │   └── [EVAL: +5]
        │       Returns to Black: -1 * (+5) = -5
        │       To White: -(-5) = +5
        │
        └── Move B2
            └── [EVAL: +2]
                Returns to Black: -1 * (+2) = -2
                To White: -(-2) = +2
        
        Black picks max(-5, -2) = -2
        Return to White: -(-2) = +2

White picks max(+1, +2) = +2
Best move: B
```

### Negamax with Alpha-Beta Pruning

```py
function negamax(position, depth, alpha, beta, color):
    if depth == 0:
        return color * evaluate(position)
    
    maxEval = -INFINITY
    for each move in position.getLegalMoves():
        eval = -negamax(makeMove(move), depth - 1, -beta, -alpha, -color)
        maxEval = max(maxEval, eval)
        alpha = max(alpha, eval)
        
        if alpha >= beta:
            break  # Prune
    
    return maxEval

# Initial call
bestScore = negamax(position, MAX_DEPTH, -INFINITY, +INFINITY, +1)
```

**Why swap alpha and beta?**
- Alpha/beta represent a window from current player's perspective
- When we flip perspective (negate), we must also flip the window
- Your alpha becomes opponent's negative beta, and vice versa

#### Alpha and Beta in Negamax

In negamax, alpha and beta always represent the window from the CURRENT player's perspective.

```
Alpha: "I'm guaranteed at least this score"
Beta:  "My opponent won't let me get more than this"
```

Both players use the same logic, but when we recurse, we negate and swap the window.

**Why We Swap Alpha and Beta**

1. **Your alpha** = "best I can guarantee"
   - For opponent, this becomes **their beta** = "worst they'll allow you"
   - But negated: `-alpha`

2. **Your beta** = "best opponent will allow"
   - For opponent, this becomes **their alpha** = "best they can guarantee"
   - But negated: `-beta`

**Step-by-Step Example**

```
Root: White's turn (color = +1)
      alpha = -∞, beta = +∞
      "I want at least -∞, opponent won't give me more than +∞"
      
├── Exploring Move A
│   
│   Call: negamax(positionA, depth-1, -∞, +∞, -1)
│                                      ↓
│         After negation: negamax(..., -beta, -alpha, -color)
│                                      -(+∞)  -(-∞)
│                                       -∞     +∞
│   
│   Black's turn (color = -1)
│   alpha = -∞, beta = +∞  (from Black's perspective)
│   "I (Black) want at least -∞, White won't give me more than +∞"
│   
│   ├── Move A1: returns +3 (from Black's view)
│   │   alpha = max(-∞, +3) = +3
│   │   "I now have at least +3 (from my Black perspective)"
│   │
│   ├── Move A2: returns +1
│   │   alpha = max(+3, +1) = +3 (no change)
│   
│   Black returns: +3
│   
│   Back to White: -(+3) = -3
│   White's alpha = max(-∞, -3) = -3
│   "I (White) now have at least -3"
│
├── Exploring Move B
│   
│   White now has alpha = -3, beta = +∞
│   
│   Call: negamax(positionB, depth-1, -beta, -alpha, -color)
│                                      -(+∞)  -(-3)
│                                       -∞     +3    ← Swapped!
│   
│   Black's turn
│   alpha = -∞, beta = +3  (from Black's perspective)
│   "I want at least -∞, but White won't let me get more than +3"
│                                                              ↑
│                               This came from White's alpha = -3
│   
│   ├── Move B1: returns +5 (from Black's view)
│   │   alpha = max(-∞, +5) = +5
│   │   Check: alpha >= beta? → +5 >= +3? YES! ✂️
│   │   PRUNE! (Beta cutoff)
│   │
│   │   Why prune?
│   │   Black found +5 for themselves
│   │   But White (parent) already has -3 guaranteed
│   │   From White's view, +5 for Black = -5 for White
│   │   White won't choose this branch (-5 < -3)
│   
│   └── Move B2: ✂️ Not explored
```

## Iterative Deepening

Imagine you're writing a chess engine and give it 10 seconds to find a move.

**Naive approach:**

```
"Let me search to depth 6... oh wait, this is taking 15 seconds!"
→ Time's up, no move found yet!
```

**Better approach (Iterative Deepening):**

```
Depth 1: 0.001s → Found move: e4 (score: +0.2)
Depth 2: 0.01s  → Found move: e4 (score: +0.3)
Depth 3: 0.1s   → Found move: Nf3 (score: +0.4)
Depth 4: 1s     → Found move: Nf3 (score: +0.5)
Depth 5: 8s     → Found move: d4 (score: +0.6)
[Time's up!]
→ Return d4 (best move found at depth 5)
```

**Iterative Deepening:** Search depth 1, then depth 2, then depth 3... until time runs out. Always have a move ready!

### Pseudocode

#### Basic Iterative Deepening

```py
function iterativeDeepeningSearch(position, maxTime):
    startTime = currentTime()
    bestMove = null
    bestScore = -INFINITY
    
    for depth = 1 to INFINITY:
        # Check if we have time for this depth
        if currentTime() - startTime >= maxTime:
            break
        
        # Search at current depth
        score, move = negamax(position, depth, -INF, +INF, +1)
        
        # Update best move found so far
        bestMove = move
        bestScore = score
        
        # Optional: print info
        print("Depth:", depth, "Move:", move, "Score:", score)
    
    return bestMove
```

#### With Time Management

```py
function iterativeDeepeningSearch(position, maxTime):
    startTime = currentTime()
    bestMove = null
    timeForDepth = []  # Track time per depth
    
    for depth = 1 to MAX_DEPTH:
        depthStartTime = currentTime()
        
        # Estimate if we have time for this depth
        if depth > 2:
            estimatedTime = predictTimeForDepth(depth, timeForDepth)
            if currentTime() - startTime + estimatedTime > maxTime:
                break  # Not enough time, use previous result
        
        # Search at current depth
        score, move = alphaBeta(position, depth, -INF, +INF, +1)
        
        # Record how long this depth took
        timeForDepth.append(currentTime() - depthStartTime)
        
        # Update best move
        bestMove = move
        bestScore = score
        
        # Check if time is up
        if currentTime() - startTime >= maxTime:
            break
    
    return bestMove
```

### Why Does This Work?

Isn't searching depth 1, 2, 3... wasteful?"

**Intuition says:** Yes! You're re-searching the same positions multiple times.

**Reality says:** No! The time is dominated by the deepest search.

#### The Math Behind It

Chess has a **branching factor** of ~35 (average legal moves per position).

#### Time for each depth:
```
Depth 1:  35^1  =           35 nodes
Depth 2:  35^2  =        1,225 nodes
Depth 3:  35^3  =       42,875 nodes
Depth 4:  35^4  =    1,500,625 nodes
Depth 5:  35^5  =   52,521,875 nodes
Depth 6:  35^6  = 1,838,265,625 nodes
```


#### Total work with Iterative Deepening to depth 6:

```
Total = 35 + 1,225 + 42,875 + ... + 1,838,265,625
      ≈ 1,838,310,235 nodes

Just depth 6 alone: 1,838,265,625 nodes
Overhead from earlier depths: 44,610 nodes (0.002%!)
```

**The overhead is negligible!** The deepest search dominates everything.

### General Formula

For branching factor `b` and depth `d`:

**Time for depth d:** `b^d`

**Total time with ID:**
```
b^1 + b^2 + b^3 + ... + b^d = (b^(d+1) - b) / (b - 1)
                              ≈ b^d * (b / (b-1))

For b=35:

Overhead factor = 35 / 34 = 1.029
```

### Benefits of Iterative Deepening

#### 1. Time Management

```py
# Always have a move ready
for depth in 1..∞:
    if timeUp():
        return bestMoveFoundSoFar  # ← Always valid!
    search(depth)
```

#### 2. Better Move Ordering

Results from shallower searches help order moves in deeper searches:

```py
# Depth 3 found: d4 is best, Nf3 second, e4 third
# At depth 4, search in this order first:
moves = [d4, Nf3, e4, ...]  # ← Previous best first!
                            # → More alpha-beta pruning!
```

This is called **Principal Variation (PV) move ordering**.

Principal Variation = the line of moves the engine currently believes is best.


Example after depth 4:

```
PV: 1. Nf3 d5 2. d4 Nf6
```

This dramatically speeds up alpha-beta pruning because

> Alpha-beta is only fast if you search the BEST move first.

If the best move is searched late → pruning almost disappears.

#### 3. Progressive Information

```
Depth 1: e4 (+0.2)   [0.001s]
Depth 2: e4 (+0.3)   [0.01s]
Depth 3: Nf3 (+0.4)  [0.1s]
Depth 4: Nf3 (+0.5)  [1s]
```
You see the engine "thinking deeper" in real-time!

#### 4. Handles Unknown Time Limits

Don't know how long to search? Just keep going deeper until interrupted!

**Psuedocode (Time Limit and PV move Ordering)**

```py
function findBestMove(position, maxTime):
    startTime = now()
    bestMove = null
    pvMoves = []  # Principal variation from previous depth
    
    for depth = 1 to 100:  # Practically infinite
        # Check time before starting new depth
        elapsed = now() - startTime
        if elapsed > maxTime * 0.9:  # Leave 10% buffer
            break
        
        # Search at current depth with move ordering
        result = search(position, depth, pvMoves)
        
        # Update best move and PV
        bestMove = result.move
        bestScore = result.score
        pvMoves = result.principalVariation
        
        # Log progress
        print(f"Depth {depth}: {bestMove} (score: {bestScore}, time: {elapsed}s)")
        
        # Check for forced mate
        if abs(bestScore) > MATE_THRESHOLD:
            print(f"Mate found in {depth} plies!")
            break
    
    return bestMove


function search(position, depth, pvMoves):
    # Order moves: PV move first, then others
    moves = orderMoves(position.getLegalMoves(), pvMoves)
    
    bestMove = null
    bestScore = -INFINITY
    alpha = -INFINITY
    beta = +INFINITY
    pv = []
    
    for move in moves:
        newPos = position.makeMove(move)
        score = -negamax(newPos, depth - 1, -beta, -alpha, -1)
        
        if score > bestScore:
            bestScore = score
            bestMove = move
            pv = [move] + childPV
        
        alpha = max(alpha, score)
    
    return {move: bestMove, score: bestScore, principalVariation: pv}
```

#### 5. Iterative Deepening with Aspiration Windows

Advanced engines narrow the alpha-beta window using previous depth's score:

Normally search starts with:
```
alpha = -∞
beta  = +∞
```

Meaning:
> “I have no idea what the position score is — search everything.”

This is slow because pruning is weak.

**Key Observation**

From iterative deepening, you already know the score from previous depth.

Example:
```
Depth 6 → score = +0.32
Depth 7 → score ≈ probably near +0.32
```
Chess positions are stable.
Score rarely jumps from +0.3 → -5.0 in one extra ply.

So instead of searching full range…

we search only near the expected value.

**Aspiration Window Idea**

Instead of:

```
alpha = -∞
beta  = +∞
```

we search:

```cpp
alpha = previousScore - margin
beta  = previousScore + margin
```

**Why this is FAST**

Alpha-beta pruning strength depends on window size.

Smaller window ⇒ way more cutoffs ⇒ exponential speedup

```py
function iterativeDeepening(position, maxTime):
    previousScore = 0
    
    for depth = 1 to ∞:
        # Use narrow window around previous score
        windowSize = 0.5
        alpha = previousScore - windowSize
        beta = previousScore + windowSize
        
        score = negamax(position, depth, alpha, beta, +1)
        
        # Re-search if score falls outside window
        if score <= alpha or score >= beta:
            # Widen window and re-search
            score = negamax(position, depth, -INF, +INF, +1)
        
        previousScore = score
        
        if timeUp():
            break
    
    return bestMove
```

