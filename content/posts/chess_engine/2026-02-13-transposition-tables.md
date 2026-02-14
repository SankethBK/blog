---
title:  "Transposition Tables"
date:   2026-02-13
draft: false
categories: ["chess engines"]
tags: ["transposition tables"]
author: Sanketh
---

# Transposition Tables

The transposition table is the engine’s memory of previously analyzed positions.
Because the same chess position can be reached through different move orders (transpositions), storing results avoids re-searching identical subtrees — this is one of the biggest speedups in modern engines.

Stockfish stores a compact 10-byte entry per position.

## TTEntry — What is stored

Each entry stores just enough info to help pruning and move ordering:

```cpp
struct TTEntry {
    private:
        friend class TranspositionTable;

        uint16_t key16;
        uint16_t move16;
        int16_t  value16;
        int16_t  eval16;
        uint8_t  genBound8;
        int8_t   depth8;
};
```

### C++ Used here

#### Structs in C++ 

In C++, struct and class are almost identical, with one default difference:

```cpp
struct MyStruct {
    int x;  // PUBLIC by default
};

class MyClass {
    int x;  // PRIVATE by default
};
```

But you can override the defaults:

```cpp
struct MyStruct {
private:     // ← Explicitly make it private
    int x;
};

class MyClass {
public:      // ← Explicitly make it public
    int x;
};
```

#### Friend Class - Controlled Access

**The Problem**

```cpp
struct TTEntry {
private:
    uint16_t key16;
    // ... other fields
};

class TranspositionTable {
    TTEntry entries[MILLIONS];
    
    void store(uint64_t hash, int value) {
        // Need to access TTEntry internals!
        entries[index].key16 = ???;  // ❌ ERROR: private!
    }
};
```

**TranspositionTable** needs to manipulate TTEntry internals, but they're private!

The Solution: `friend`

```cpp
struct TTEntry {
private:
    friend class TranspositionTable;  // ← Grant access!
    
    uint16_t key16;
    uint16_t move16;
    // ...
};

class TranspositionTable {
    TTEntry entries[MILLIONS];
    
    void store(uint64_t hash, int value) {
        entries[index].key16 = hash >> 48;  // ✓ OK! (friend access)
        entries[index].value16 = compress(value);
    }
};
```

`friend class TranspositionTable` means:
> "TranspositionTable is my friend - it can access my private parts"

### Collision Probability in Transposition Tables

A TT hit is accepted only if all 3 filters pass:
	1.	Same table index (lower bits match)
	2.	Same verification key (key16)
	3.	Same Zobrist hash (no real hash collision)

So a wrong reuse requires ALL THREE to collide simultaneously.

We estimate probability layer-by-layer.

#### Layer 1 — Index Collision (Bucket Clash)

We index using lower N bits:

```cpp
index = zobrist & (tableSize - 1)
```

For a table of size:

```cpp
2^27 ≈ 134 million entries
```

Two random positions collide in index with probability:

P1 = 1 / 2^27

So:

```
≈ 1 in 134,217,728
```

But engines search billions of nodes → this happens often.
That’s why we need a verification key.

#### Layer 2 — Partial Key Verification (key16)

We store upper 16 bits:

```cpp
stored.key16 == key >> 48
```

Probability a random different position matches:

P2 = 1 / 2^16

```
≈ 1 in 65,536
```

Now combined probability:

```
P_{1+2} = 1 / 2^{27} × 1 / 2^{16} = 1 / 2^{43}

≈ 1 in 8.8 trillion
```

Already astronomically small.

#### Layer 3 — Real Zobrist Collision

Zobrist hashing is 64-bit random hashing.

Probability two different chess positions share the same hash:

P3 = 1 / 2^64

```
≈ 1 in 18,446,744,073,709,551,616
```

#### Final Probability (All Layers Fail)

```
P_{total} = 1 / 2^{27} × 1 / 2^{16} × 1 / 2^{64}
= 1 / 2^{107}

≈ 1 in 1.6 × 10^32
```

For perspective:

> You are more likely to win the lottery every week for the rest of your life than hit a harmful TT collision.

Chess engines choose a practically perfect approach.

Even if a collision happens:
- evaluation error is small
- future searches overwrite it
- alpha-beta is resilient



### TTEntry Fields

```
| Field       | Size     | Purpose                                      |
| ----------- | -------- | -------------------------------------------- |
| `key16`     | 16 bits  | Upper part of Zobrist key (verification)     |
| `move16`    | 16 bits  | Best move found from this position           |
| `value16`   | 16 bits  | Search result (score from search)            |
| `eval16`    | 16 bits  | Static evaluation (NNUE eval, before search) |
| `genBound8` | 6+2 bits | Entry age + bound type                       |
| `depth8`    | 8 bits   | Depth searched                               |
```

#### 1. `uint16_t key16` - Hash Verification

**What it stores:** upper 16 bits of the 64-bit Zobrist hash

**Why not store full 64-bit key?**

Memory.

A TT may contain hundreds of millions of entries.
Storing full keys would double the size → halve usable depth.

key16 is not the key used to index the table. It is only a collision checker.

A transposition table lookup has two stages:

```cpp
uint64_t fullHash = zobristHash(position);  // 64-bit hash

// Step 1: Find the slot
size_t index = fullHash & (tableSize - 1);  // Use lower bits
                                             // Example: bits 0-26 for 128M entries

// Step 2: Store verification key
entry->key16 = fullHash >> 48;              // Store upper 16 bits

// Later, when probing:
TTEntry* entry = table[index];
if (entry->key16 == (fullHash >> 48)) {     // Verify match
    // Same position!
} else {
    // Collision - different position in same slot
}
```


##### 1. Indexing (where in the table?)

We want to map a 64-bit hash to a valid table index:

```
fullHash = 0xABCD_1234_5678_9EF0  (any 64-bit number)
tableSize = 134,217,728           (128 million entries)

Need: index in range [0, 134,217,727]
```

**Naive Approach: Modulo**

```cpp
size_t index = fullHash % tableSize;
```

Problem: Modulo (`%`) is slow on most CPUs (10-40 cycles).

**Fast Approach: Bitwise AND (When Size is Power of 2)**

**The Trick:**
**If tableSize is a power of 2**, we can use bitwise AND instead:

```cpp
size_t index = fullHash & (tableSize - 1);
```

**Bitwise AND (`&`) is extremely fast** (1 cycle).

**Why This Works?**

Understanding Powers of 2 in Binary

```
tableSize = 128M = 2^27 = 134,217,728

In binary:
2^27 = 1000_0000_0000_0000_0000_0000_0000  (1 followed by 27 zeros)

2^27 - 1 = 0111_1111_1111_1111_1111_1111_1111  (27 ones)
```

**The Magic of AND with (2^n - 1)**

When you AND any number with `(2^n - 1)`, you **keep only the lower n bits**:
```
fullHash:        ????_????_????_????_????_????_????  (any bits)
(tableSize - 1): 0000_0000_0000_0000_0111_1111_1111  (27 ones)
                 ─────────────────────────────────
Result:          0000_0000_0000_0000_0???_????_????  (lower 27 bits)
```

**This is exactly the same as `fullHash % tableSize`!**

The important observation here is there are 27 ones in lower bits. So it has potentially select all numbers between 0 and 2^27. This wouldn't have been possible if all lower 27 bits weren't ones, Thus taking `(2^n - 1)` is important. 

##### 2. Verification (is it the same position?)

Uses UPPER 16 bits

```cpp
stored.key16 == key >> 48
```

This only checks:

> “Did we land on the correct position or just collide?”

#### 2. `move16` — Best move (move ordering weapon)

Stores: the best move previously found from this position

Remember `enum Move` is 16 bits. 

**Why this is insanely important**

Alpha-beta effectiveness depends on searching the best move first.

Because if the best move is searched first:

```
beta cutoff happens earlier
→ whole branches disappear
→ exponential speedup
```

So TT move is used as:

```
FIRST move to search at this node
```

Even if evaluation is outdated, move ordering value remains huge.

> TT move ordering is one of the strongest heuristics in chess engines.

#### 3. `value16` — Search result (alpha-beta bound)

**Stores:** the search score returned by alpha-beta

But important:
This is not always exact.

The key idea:

> A transposition table usually does not store the position value.
> It stores information about the search window result.

It doesn’t ask:

> “What is the exact value of this position?”

It asks:

> “Is the value inside the window [alpha, beta]?”

So most nodes never compute the exact score.

**Why alpha-beta rarely knows the real value**

Suppose we search with window:

```
alpha = -0.50
beta  = +0.50
```

We are basically asking:

> “Is the position worse than -0.50, better than +0.50, or inside?”

We stop searching as soon as we can prove one of those.

So the engine often returns **inequalities**, not numbers.

##### The Three Possible Results

**1. Exact value (PV node):**

We searched fully without cutoff.

```
alpha < score < beta
```

Example:

```
window = [-0.50, +0.50]
real score = +0.20
```

We had to examine all moves → we now KNOW the exact value.

Stored as:

```
BOUND_EXACT
value16 = +0.20
```

This is rare — only principal variation nodes.

**2. Fail-High (Lower Bound)**

Search proves position is at least beta.

```
score ≥ beta
```

Example:

```
window = [-0.50, +0.50]
we find a move giving +1.80
```

Opponent would never allow this → we stop immediately.

We do NOT know the real score.
It might be +1.80, +3.00, or mate.

We only know:

> position ≥ +0.50

Stored as:

```
BOUND_LOWER
value16 = beta (or score)
meaning: score ≥ value16
```

**3. Fail-Low (Upper Bound)**

Search proves position is at most alpha.

```
score ≤ alpha
```

Example:

```
window = [-0.50, +0.50]
all moves ≤ -0.80
```

We stop — too bad for us.

We only know:

> position ≤ -0.50

Stored as:

```
BOUND_UPPER
value16 = alpha
meaning: score ≤ value16
```

##### Why this is powerful (instant pruning)

Later we revisit the same position with window:

```
alpha = -0.30
beta  = +0.30
```

We probe TT.

**Case A — Stored LOWER bound ≥ beta**

Stored:

```
score ≥ +0.50
```

Current search asks:

```
Is score < +0.30 ?
```

Impossible.

So we instantly prune — no search.

**Case B — Stored UPPER bound ≤ alpha**

Stored:

```
score ≤ -0.50
```

Current search asks:

```
Is score > -0.30 ?
```

Impossible.

Instant prune again.

**Case C — Stored EXACT**

We directly return value.

No search at all.

So the general idea is when we start to search initally, we obviously want to know the exact score for that position not some alpha, beta range, but while doing so we will encounter millions of intermediate positions for whom we may not calculate exact score and prune if they are out of range, only if they lie in range we get exact value since it can contribute to final asnwer.

##### Value Range and Encoding

```
// Stockfish value range:
VALUE_ZERO      = 0
VALUE_DRAW      = 0
VALUE_MATE      = 32000
VALUE_INFINITE  = 32001

// All fit in int16_t (-32768 to +32767)
// Positive = good for White
// Negative = good for Black
```

**Mate Distance Adjustment**

Engines encode mate as very large numbers:

```
+32000  → winning mate
-32000  → getting mated
```

But they don’t store just mate yes/no — they store mate in N.

Why?

Because:

> Mate in 3 is better than mate in 10

So engines encode:

```
mate in N  =  +MATE - N
mated in N =  -MATE + N
```

Example:

```
MATE = 32000

Mate in 1 = 31999
Mate in 2 = 31998
Mate in 3 = 31997
```

Higher = faster win

**Where the bug appears (Transposition Table)**

The SAME board position can appear at different depths in the tree.

But distance to mate from root is different.

Example tree:

From root:

```
Root
 └── A
     └── B
         └── C  ← position P
             └── forced mate in 3
```

At node P, engine finds:

> mate in 3

So evaluation stored:

```
score = 31997
```

But this means:

> mate in 3 FROM P
> NOT from root

From root it’s actually:

```
Root → A → B → C → mate in 3
distance from root = 3 + 3 = 6 plies
```

So correct root interpretation = mate in 6

Now suppose same position appears elsewhere:

```
Root
 └── X
     └── Y
         └── Z
             └── W
                 └── P   ← same board again
```

Now P is deeper!

From here:

```
mate in 3 from P = mate in 7 from root
```

BUT TT stored 31997 without context
Engine would think it’s mate in 3 again ❌

So engine thinks:

> This line mates faster than it really does

→ causes wrong move ordering
→ even wrong best move selection


**The Fix: Store relative to ply**

We store mate score shifted by current depth (ply).

When storing

At node P:

```
true local score = +31997 (mate in 3 from here)
current ply = 5 from root

storedValue = score + ply
            = 31997 + 5
            = 32002
```

We convert:

> from “mate from here” → “mate from root”

**When retrieving later**

Suppose we reach P again at ply = 8:

```
retrievedScore = storedValue - ply
               = 32002 - 8
               = 31994
```

Which equals:

```
mate in 6 from here
```

#### 4. `int16_t eval16` - Static Evaluation

Stores: evaluation without search (NNUE / handcrafted eval)

**Why store this separately from value16?**

Because:

```
value = eval + tactics discovered during search
```

Later when probing:

If depth too shallow to trust value
→ engine still reuses eval

This avoids recomputing expensive evaluation (especially NNUE).

> Think of it as an evaluation memoization cache.

##### Static vs Search Evaluation

STATIC EVAL (eval16):
- Just look at current position
- Count material, position, king safety
- No search ahead
- Fast: ~1 microsecond
- Example: +0.5 pawns

SEARCH VALUE (value16):  
- Minimax result after searching ahead
- Considers tactics, forced sequences
- Slow: varies with depth
- Example: +2.0 pawns (found tactic)

#### 5. `uint8_t genBound8` - Generation & Bound Type

Two Pieces of Information Packed
This 8-bit field contains:

1. Generation (upper 6 bits): Which search iteration stored this
2. Bound type (lower 2 bits): EXACT, LOWER_BOUND, or UPPER_BOUND

**Part A: Generation (Replacement Scheme)**

**Purpose:** Decide which entries to replace when TT is full.

```cpp
// At start of each search:
TT.new_search();  // generation++ (0 → 1 → 2 → ... → 63 → 0)

// When storing entry:
entry->genBound8 = (generation << 2) | bound;

// When deciding to replace:
if (entry->generation() != currentGeneration) {
    // Old entry from previous search
    // More likely to replace
}
```


**Generation wraparound** (6 bits = 0-63):

```
Search 1: generation = 1
Search 2: generation = 2
...
Search 63: generation = 63
Search 64: generation = 0 (wraps around)
```

**Replacement logic:**

```cpp
bool shouldReplace(TTEntry* existing, int newDepth, int currentGen) {
    // Always replace if:
    // 1. Empty slot
    if (existing->depth8 == 0)
        return true;
    
    // 2. Same position (update)
    if (existing->key16 == newKey)
        return true;
    
    // 3. Old generation AND new search is deeper
    if (existing->generation() != currentGen && newDepth >= existing->depth8)
        return true;
    
    // 4. Much deeper search
    if (newDepth > existing->depth8 + 4)
        return true;
    
    return false;
}
```

**Part B: Bound Type (Node Type)**

**Purpose:** Know how to use the stored value.

```cpp
enum Bound {
    BOUND_NONE  = 0,  // 00
    BOUND_UPPER = 1,  // 01 (fail-low, all node)
    BOUND_LOWER = 2,  // 10 (fail-high, cut node)  
    BOUND_EXACT = 3   // 11 (PV node)
};
```

**How bound is determined:**

```cpp
// After search:
Bound bound;
if (value <= alphaOrig)
    bound = BOUND_UPPER;  // Fail-low
else if (value >= beta)
    bound = BOUND_LOWER;  // Fail-high
else
    bound = BOUND_EXACT;  // Within window

entry->genBound8 = (generation << 2) | bound;
```

**Usage when retrieving:**

```cpp
if (tte->depth() >= depth) {
    int score = tte->value();
    
    if (tte->bound() == BOUND_EXACT) {
        return score;  // Use as-is
    }
    else if (tte->bound() == BOUND_LOWER) {
        alpha = max(alpha, score);  // At least this good
    }
    else if (tte->bound() == BOUND_UPPER) {
        beta = min(beta, score);    // At most this good
    }
    
    if (alpha >= beta)
        return score;  // Cutoff
}
```

#### 6. `int8_t depth8` - Search Depth

**Purpose:**

**Track how deeply this position was searched** - to decide if we can use this entry.

The Rule
```
Can use TT entry ONLY if:
  storedDepth >= currentSearchDepth
```

**Why?**

Previously searched to depth 5: value = +0.3
Now searching to depth 10

→ Depth 5 result is NOT good enough for depth 10!
→ Must search deeper
→ Don't use TT entry (except for move ordering)

##### Depth Values

```
// Depth is measured in plies (half-moves):
DEPTH_ZERO = 0
ONE_PLY = 1

// Example values:
depth8 = 0:  Leaf node (just eval)
depth8 = 1:  Searched 1 ply (half-move)  
depth8 = 10: Searched 10 plies (5 full moves)
depth8 = 20: Searched 20 plies (10 full moves)

// Can be negative due to reductions!
depth8 = -1: Reduced below quiescence search
```

**Usage Example**

```cpp
// Searching position at depth 12
TTEntry* tte = TT.probe(hash, found);

if (found) {
    if (tte->depth() >= 12) {
        // Previous search was deep enough
        // → Use stored value (if bound allows)
        return tte->value();
    }
    else if (tte->depth() >= 8) {
        // Not deep enough for cutoff, but use move!
        Move bestMove = tte->move();
        // Try this move first
    }
    else {
        // Very shallow, might ignore completely
    }
}

// If not usable, search and store new result:
value = search(...);
TT.store(hash, value, depth=12, ...);
```

**Depth and Replacement**

Deeper searches are more valuable:

```cpp
// Replacement prefers keeping deeper searches:
if (newDepth <= existingDepth - 4) {
    // Don't replace much deeper entry
    return;  // Keep existing
}
```

**Example:**
```
Slot contains: depth=15, value=+0.5, generation=5

New entry: depth=8, value=+0.3, generation=6
→ Don't replace! (15 >> 8, even though newer)

New entry: depth=16, value=+0.4, generation=6  
→ Replace! (16 > 15, deeper search)
```

**Why int8_t? (Signed)**
Range: -128 to +127
Needs to be signed for:

1. **Reductions**: Search can go below depth 0
2. **Extensions**: Depth can increase beyond nominal
3. **Quiescence**: Depth 0, -1, -2 during qsearch

```cpp
// During search:
if (dangerousMove)
    depth += 1;  // Extend (depth could be 21, 22, etc.)

if (likelyBad)
    depth -= 2;  // Reduce (could go negative)
```

