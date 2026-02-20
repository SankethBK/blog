---
title:  "Principal Variation"
date:   2026-02-21
draft: false
categories: ["chess engines"]
tags: ["principal variation"]
author: Sanketh
references:
    - title: Principal Variation
      url: https://www.chessprogramming.org/Principal_Variation
---

# Principal Variation

The principal variation is the sequence of moves that the engine considers best for both sides from the current position. It's the "main line" — the path through the game tree that alpha-beta search identifies as optimal.

## When is Principal Variation Used?

**After search is complete:** The PV is the best line the engine found. This is what gets printed to the GUI — "at depth 12, best line is e4 e5 Nf3...". Totally useful even without ID, just for knowing the answer.

**During ID (where it becomes operationally important):** The PV from depth N gets used as move ordering for depth N+1. Since the best move at depth N is very likely still best at depth N+1, searching it first means your alpha-beta pruning is maximally effective from the start. This is the key efficiency gain — without it you'd have worse move ordering on the first few nodes of each iteration.

**During Search:** Even within a single search iteration, PV line is used to aggressively prune other moves using null window, LMR, etc.

## Node Enum

```cpp
enum NodeType {
    NonPV,  // Non-Principal Variation node
    PV,     // Principal Variation node
    Root    // Root node (special PV node)
};
```

**These describe what kind of node we're searching in the game tree.**

```
Root Position
├─ e4 (best move so far) ← PV move
   └─ e5 (opponent's best response) ← PV move
      └─ Nf3 (our best continuation) ← PV move
         └─ Nc6 ← PV move
            └─ ... continues
```

This sequence is the "PV line" or "main line"

The PV is the path through the tree that survived alpha-beta without being pruned.

### 1. Root Node

Special PV node at top of the tree.

Extra responsibilities:
- stores best move
- iterative deepening updates
- aspiration windows
- UCI output
- multiPV handling

Think:

> User-facing PV

### 2. PV Node (Principal Variation)

Nodes along the principal variation path - the best line we've found.

**How a node becomes PV:**

```cpp
// During search:
if (value > alpha) {
    alpha = value;
    // This move raises the alpha, so it is now part of PV!
    if (PvNode)
        update_pv(ss->pv, move, (ss+1)->pv);
}
```


**Properties:**
- First move searched at a PV node **often** becomes PV itself
- Full window search: `alpha` and `beta` are far apart
- No aggressive pruning (might miss best move)
- Extra work: store PV, update GUI info

At a PV node:
- We need an exact score
- We cannot aggressively prune
- We search moves carefully
- We often re-search with full window

So pruning is conservative.

Think:

> Accuracy > Speed

### 3. NonPV Node (Most Common!)

> Side branches — we only need to prove they are worse.

Here we don’t care about exact score.
We only want to know:

> “Is this move worse than alpha? If yes → discard”


So we use:
- null window search (alpha, alpha+1)
- heavy pruning
- reductions
- cutoffs

Think:
> Speed > Accuracy

Most of the tree (~95%) are NonPV nodes.

**Example:**

Let's say initially engine searched move A and got its evaluation score alpha. 

For move B we only ask:

> Can B beat A?

NOT:

> What is exact evaluation of B?

If it fails → stop immediately → NonPV node.

But for move A (current best line):
We must know exact continuation → PV node.

## What actually happens (step-by-step)

Stockfish doesn’t label a move as PV because it’s proven best.
It labels a node as PV because it is currently inside the best line found so far during the search.

So PV is dynamic, not predetermined.

We start search at root:

```
alpha = -∞
beta  = +∞
```

**Move A (first move)**

We always search the first move as a PV search (full window)

Why?
Because we have no best move yet.

```
score(A) = +0.1
alpha = +0.1
PV = A
```

Now we have a candidate principal variation.


**Move B**

Now we already have a better move A = +0.1

We don’t care about exact score of B.
We only ask:

> Can B beat +0.1 ?

So we search B as NonPV (null window):

```
search window = (alpha, alpha+1) = (0.1, 0.2)
```

**Case 1 — fails low**

**Example:**

```
score(B) = -1.3
```

B is worse → discard → no PV change

**Case 2 — fails high (interesting case)**

Example:

```
score(B) ≥ 0.2
```

Now B might be better than A.

But null-window search cannot give exact score,
so we re-search B as PV node:

```
full search window (-∞, +∞) or (alpha, beta)
```

Suppose:

```
score(B) = +2.0
alpha = +2.0
PV = B
```

Now B becomes the principal variation.


Now alpha = +2.0

Again we only ask:

> Can C beat +2.0 ?

So C is searched as NonPV.

Only if it beats alpha → re-search as PV.

> Only one move per node is searched as PV: the current best candidate.
> All other moves are tested cheaply first.

So PV is basically:

> “the move that survived all previous competition so far”

One-line intuition

> PV = current champion
> Every other move must first defeat the champion in a quick match before earning a full fight.

## Principal Variation Search

The technique of considering PV as best line until we prove other line is better than it is also called as Principal Variation Search. 

It also uses a technique **null window:** Instead of earching in the full (alpha, beta) range, we search in very narrow range **(alpha, alpha + 1**). This will be vey fast, since the range is very small, many branches will be pruned aggresively. But if the subtree were to contain a move better than current alpha it will eventually bubble up and will be re-searched with the full [alpha, beta] window.

### Traditional Minimax-Style PVS

```py
def pvs(position, depth, alpha, beta, isMaxPlayer):

    if depth == 0 or position.isGameOver():
        return evaluate(position)

    firstMove = True

    if isMaxPlayer:

        value = -INFINITY

        for move in ordered_moves(position):
            child = position.makeMove(move)

            if firstMove:
                # Full window search for first move
                score = pvs(child, depth-1, alpha, beta, False)
                firstMove = False
            else:
                # Null window search
                score = pvs(child, depth-1, alpha, alpha + 1, False)

                # If move might be better, re-search fully
                if score > alpha:
                    score = pvs(child, depth-1, alpha, beta, False)

            value = max(value, score)
            alpha = max(alpha, value)

            if alpha >= beta:
                break  # Beta cutoff

        return value

    else:  # MIN player

        value = +INFINITY

        for move in ordered_moves(position):
            child = position.makeMove(move)

            if firstMove:
                # Full window search
                score = pvs(child, depth-1, alpha, beta, True)
                firstMove = False
            else:
                # Null window search
                score = pvs(child, depth-1, beta - 1, beta, True)

                # If move might be worse (for MAX), re-search fully
                if score < beta:
                    score = pvs(child, depth-1, alpha, beta, True)

            value = min(value, score)
            beta = min(beta, value)

            if alpha >= beta:
                break  # Alpha cutoff

        return value
```

### PVS Pseudocode (Negamax style)

```py
def pvs(position, depth, alpha, beta):

    if depth == 0:
        return qsearch(...)

    firstMove = true

    for move in ordered_moves:

        if firstMove:
            score = -pvs(child, depth-1, -beta, -alpha)
            firstMove = false
        else:
            # Null window search
            score = -pvs(child, depth-1, -alpha-1, -alpha)

            # If it improved alpha, re-search
            if score > alpha:
                score = -pvs(child, depth-1, -beta, -alpha)

        alpha = max(alpha, score)

        if alpha >= beta:
            break

    return alpha
```

### Why null window works?

When we search with a reduced window of (alpha, alpha + 1), we also prune the moves between (alpha + 1, beta), which could've been our PV candidates. So the question to think about while doing null window search, can we miss a move which is potentially better than we thought, but we pruned it because we weren't expecting a move that good?

#### Why shrinking window doesn’t miss good moves

At parent node, suppose:
```
alpha = 0.5
beta  = 3.0
```

Now for a later move, we call:

```cpp
score = -pvs(child, depth-1, -alpha-1, -alpha)
```

That means child sees window:

```cpp
(-0.5 - 1, -0.5) = (-1.5, -0.5)
```

After negation, this corresponds to testing:

> Is score > 0.5 ?

It is a yes/no question.

Note that now the opponent's beta is -0.5, so anything > -0.5 will cause beta cutoff, which is exactly what we are looking for. 

Let’s say true score of this move is:
```
+2.0
```

which means that child would've returned -2.0, note that even though it causes beta cutoff in child as soon as it finds -2.0, it still returns the score -2.0 to the parent. This -2.0 only serves as a fail high signal to the parent, the true score might as well have been -2.5, but we would've pruned it. 

Now in parent, instead of immediately discarding this move as we would have done in normal alpha-beta search, we trigger a re-search with the correct value of beta now. 

```py
    # If it improved alpha, re-search
    if score > alpha:
        score = -pvs(child, depth-1, -beta, -alpha)
```

So, its not possible to miss a good move just because we search with shrunken window.

#### The Core Insight

Null-window search can under-measure good moves,
but it cannot hide them.

If a move is truly better than alpha,
the null-window search must return a fail-high signal,
which forces a re-search.

Therefore:

> Shrinking the window never causes loss of correctness.
> It only delays exact evaluation until necessary.