---
title:  "Magic Bitboards and PEXT"
date:   2026-01-29
draft: false
categories: ["chess engines"]
tags: ["magic bitboards", "pext"]
author: Sanketh
---

# Magic Bitboards and PEXT

## The Problem: Sliding Piece Attacks

### Why Sliding Pieces Are Hard

**Non-sliding pieces (knight, king, pawn):**

- Fixed attack pattern regardless of board state
- Can pre-compute all attacks at startup
- Simple lookup: `StepAttacksBB[piece][square]`

**Sliding pieces (rook, bishop, queen):**

- Attack pattern depends on blocking pieces
- Can't pre-compute all possibilities (too many combinations)

### The Challenge

```
Rook on e4 - different scenarios:

Scenario 1: Empty board
  8  . . . . X . . .
  7  . . . . X . . .
  6  . . . . X . . .
  5  . . . . X . . .
  4  X X X X R X X X  ← Attacks entire rank and file
  3  . . . . X . . .
  2  . . . . X . . .
  1  . . . . X . . .
     a b c d e f g h

Scenario 2: Blocked by pieces
  8  . . . . . . . .
  7  . . . . . . . .
  6  . . . . X . . .
  5  . . . . X . . .
  4  . . X X R X . .  ← Blocked at c4 and f4
  3  . . . . X . . .
  2  . . . . . . . .
  1  . . . . . . . .
     a b c d e f g h
     (Pieces at: c4, e2, e6, f4)
```

The question: How do we efficiently compute attacks for ANY occupancy pattern?

## Naive Solutions (Too Slow)

### Solution 1: Compute On-Demand

```cpp
Bitboard rook_attacks(Square sq, Bitboard occupied) {
    Bitboard attacks = 0;
    
    // North
    for (Square s = sq + 8; s <= SQ_H8; s += 8) {
        attacks |= s;
        if (occupied & s) break;  // Hit a piece, stop
    }
    
    // South
    for (Square s = sq - 8; s >= SQ_A1; s -= 8) {
        attacks |= s;
        if (occupied & s) break;
    }
    
    // East, West (similar)
    ...
    
    return attacks;
}
```

Cost: 4 loops, up to 7 iterations each = ~20-30 cycles
Called: Millions of times per second
Too slow!

### Solution 2: Pre-compute Everything

```cpp
// For EACH square (64) and EACH possible occupancy pattern
Bitboard RookAttacks[64][2^64];  // Store all possibilities
```

**Problem:** 
- 64 squares × 2^64 occupancies = impossibly large (10^19 entries!)
- Would need exabytes of RAM


## The Insight: Most Bits Don't Matter

### Relevant Occupancy

For a rook on e4, **only these squares matter**:
```
  8  . . . . . . . .
  7  . . . . X . . .  ← Only e7 matters (not e8 - edge)
  6  . . . . X . . .
  5  . . . . X . . .
  4  . X X X R X X .  ← Only b4-d4 and f4-g4 (not a4, h4 - edges)
  3  . . . . X . . .
  2  . . . . X . . .
  1  . . . . . . . .  ← Only e2 matters (not e1 - edge)
     a b c d e f g h
```

Relevant squares: {b4, c4, d4, f4, g4, e2, e3, e5, e6, e7}
= 10 squares

Similarly for a rook in a1

For a rook on e4, **only these squares matter**:
```
  8  . . . . . . . .
  7  X . . . . . . . 
  6  X . . . . . . .
  5  X . . . . . . .
  4  X . . . . . . .  
  3  X . . . . . . .
  2  X . . . . . . .
  1  R X X X X X X .  
     a b c d e f g h
```


Relevant squares: {a2, a3, a4, a5, a6, a7, b1, c1, d1, e1, f1, g1}
= 12 squares

**Why ignore edges?**
- Attacks always **stop at** or **go past** the edge
- Occupancy of edge squares doesn't change the attack pattern

This is the maximum number of squares we would ever need for a rook.

## The Next Idea: Perfect Hashing

### The Problem We Still Have

Even with only relevant squares, we still need efficient lookup:

- Rook on e4: 10 relevant squares → 2^10 = 1,024 possible occupancy patterns
- Rook on a1: 12 relevant squares → 2^12 = 4,096 possible occupancy patterns

We could create a table like:

```cpp
Bitboard RookAttacks[64][4096];  // Much better than 2^64!
```

Let's take a step back and understand what is the 4096 here, its 2^12. At worst, we might need to represent 12 squares whose occupancy affects rook reachability. Since each square can be occupied or empty, we take 2^12. 

This means the second index is an encoded way to tell which of these relevant squares are occupied by any piece (blockers),


**Concrete Example: Rook on a1 (12 relevant squares)**

```
  8  . . . . . . . .
  7  X . . . . . . . ← a7 (relevant)
  6  X . . . . . . . ← a6 (relevant)
  5  X . . . . . . . ← a5 (relevant)
  4  X . . . . . . . ← a4 (relevant)
  3  X . . . . . . . ← a3 (relevant)
  2  X . . . . . . . ← a2 (relevant)
  1  R X X X X X X . ← b1,c1,d1,e1,f1,g1 (relevant)
     a b c d e f g h
```

Relevant squares: {a2, a3, a4, a5, a6, a7, b1, c1, d1, e1, f1, g1} = 12 squares

#### All Possible Occupancy Patterns

- **Pattern 0:** All 12 squares empty
```
Occupancy: [0,0,0,0,0,0,0,0,0,0,0,0] → Attacks go to edges
```
- **Pattern 1:** Only a2 occupied
```
Occupancy: [1,0,0,0,0,0,0,0,0,0,0,0] → Attacks blocked at a2 vertically
```
- **Pattern 2:** Only a3 occupied
```
Occupancy: [0,1,0,0,0,0,0,0,0,0,0,0] → Attacks blocked at a3 vertically
```
- **Pattern 3:** Both a2 and a3 occupied
```
Occupancy: [1,1,0,0,0,0,0,0,0,0,0,0] → Attacks blocked at a2 (closer blocker)
```
... continuing through ...
- **Pattern 4095:** All 12 squares occupied
```
Occupancy: [1,1,1,1,1,1,1,1,1,1,1,1] → Attacks only to a2 and b1
```


#### Why We Need All Combinations

Each combination produces a different attack pattern:

```
// Example: Different occupancies → Different attacks

// Empty board
Occupancy: 000000000000 → Attacks: a2-a7, b1-g1

// Piece at a4 only  
Occupancy: 000100000000 → Attacks: a2-a4, b1-g1

// Piece at c1 only
Occupancy: 000000010000 → Attacks: a2-a7, b1-c1

// Pieces at both a4 AND c1
Occupancy: 000100010000 → Attacks: a2-a4, b1-c1 (different from either alone!)
```

#### The Table Structure

So we build:

```
// For rook on a1 with 12 relevant squares:
Bitboard RookAttacks_a1[4096];  // One entry for each occupancy pattern

RookAttacks_a1[0]    = attacks when all relevant squares empty
RookAttacks_a1[1]    = attacks when only a2 occupied
RookAttacks_a1[2]    = attacks when only a3 occupied
RookAttacks_a1[3]    = attacks when a2 and a3 occupied
...
RookAttacks_a1[4095] = attacks when all 12 squares occupied
```

But in order to generate the second index, we must encode the information of pieces present on same rank and file into a integer.

### Naive Approach

A naive way of building the second index would be to loop through the corresponding file and column and set the bits, but loops defeat the whole purpose here. 

For a rook on a1

```cpp
// Extract relevant bits manually
int index = 0;
if (occupied & (1ULL << 1))  index |= (1 << 0);   // Check a2
if (occupied & (1ULL << 2))  index |= (1 << 1);   // Check b1
if (occupied & (1ULL << 3))  index |= (1 << 2);   // Check c1
if (occupied & (1ULL << 4))  index |= (1 << 3);   // Check d1
if (occupied & (1ULL << 5))  index |= (1 << 4);   // Check e1
if (occupied & (1ULL << 6))  index |= (1 << 5);   // Check f1
if (occupied & (1ULL << 8))  index |= (1 << 6);   // Check a3
if (occupied & (1ULL << 16)) index |= (1 << 7);   // Check a4
// ... 12 checks total!

// Finally lookup:
Bitboard attacks = RookAttacks_a1[index];
```

**Cost:** 12 conditional checks, 12 bit operations = **~30-40 CPU cycles**

## The Magic Bitboard Solution

### The Mask

In order to quickly extract only the pieces on relevant rank and file, we can use pre-computed masks. 

For eg: for a rook on a1, the mask will be 


```
  8  . . . . . . . .
  7  1 . . . . . . . ← a7 (relevant)
  6  1 . . . . . . . ← a6 (relevant)
  5  1 . . . . . . . ← a5 (relevant)
  4  1 . . . . . . . ← a4 (relevant)
  3  1 . . . . . . . ← a3 (relevant)
  2  1 . . . . . . . ← a2 (relevant)
  1  0 1 1 1 1 1 1 . ← b1,c1,d1,e1,f1,g1 (relevant)
     a b c d e f g h
```

In hex it can be written as 

```cpp
Bitboard mask   = 0x0001010101010126;  // Relevant squares
```

Similarly there are 64 squares, each square will have a mask for each type of sliding piece. 

### The Mapping Problem

Once we have the mask, we can extract only the pieces on relevant rank/file/diagonal by using pre-computed mask.

`occupied & mask` will give us the bitboard of only relevant pieces. 

Now for rook on a1, there can be 4096 such bitboards, we need a way to map each of them uniquely to a number between 0 and 4095. 

It doesn't matter which scenario corresponds to what number. 

For eg: for rook on a1 scenario:
- index 0 could be the case where there are no blockers
- index 1 could be the case where there is a blocker on c1
- index 2 could be the case where there is a blocker on a6, a3. 
- ...
- index 4095 could be the case where are blockers on d1, g1, a4, a6

We need a function which consumes `occupied & mask` and outputs a unique index between 0 and 4095. Since the input space is finite and bounded, ensuring collision free output space is possible. 



### How multiplication helps

The key insight: **A single multiplication can rearrange bits!**

When you multiply two numbers, bits from the multiplicand appear at different positions in the result:
```
Example:
  x = 0b00001010  (bits at positions 1 and 3)
  m = 0b00000011  (magic multiplier)
  
  x * m = ?
  
In binary multiplication:
      00001010
    × 00000011
    ──────────
      00001010  (x × 1)
     00001010   (x × 2, shifted left 1)
    ──────────
     000011110
```

Notice: The bits from `x` appeared at new positions in the result!

Multiplication causes the relevant occupancy bits to interact and spread into the upper bits. With the right magic constant, every different occupancy produces a unique high-bit pattern.

### The Magic Bitboard

For each scenario, eg: rook on a1, we choose a seemingly random magic bitboard

```cpp
Bitboard magic  = 0x0080001020400080;
```

Magic bitboards work like a hash function:

```cpp
hash(occupancy_pattern) = ((occupancy & mask) * magic) >> shift
```

Requirements:

- Different patterns → Different indices (no collisions)
- Same pattern → Same index (deterministic)
- Index range: 0 to 2^N - 1 (where N = number of relevant squares)

For our case of rook on a1, N = 12

```cpp
Bitboard magic  = 0x0080001020400080;
hash(occupancy_pattern) = ((occupancy & mask) * magic) >> 52
```

Reason for right shifting by 52 is:

- Right shifting by 52 ensures the range is within 0 to 4095 because 2^64 / 2^52 = 2^12. 
- After multiplication, the useful information ends up in the top bits
- We discard the lower noisy bits

The magic mask is not randomly selected, it is carefully found via search such that it scatters the patterns so that there is no collision in the end result of 0 to 4095. 

Each square will have its own unique magic mask for each type of sliding piece. 

