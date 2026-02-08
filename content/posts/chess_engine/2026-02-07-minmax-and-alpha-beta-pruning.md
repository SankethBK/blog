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

**Beta (β): **The best score MIN can guarantee so far

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