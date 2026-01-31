---
title:  "Magic Bitboards and PEXT"
date:   2026-01-29
draft: false
categories: ["chess engines"]
tags: ["magic bitboards", "pext"]
author: Sanketh
references: 
    - title: Carry Rippler
      url: https://www.chessprogramming.org/Traversing_Subsets_of_a_Set
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

Output would be a bitboard containing all the squares reachable by the piece. 

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

At runtime, Stockfish computes rook attacks in 3 steps:

1. Extract only relevant blockers:
```cpp
    occ = occupied & mask
```
2. Compress this occupancy into an index:
```cpp
    index = (occ * magic) >> (64 - N)
```
3. Lookup the precomputed attack bitboard:
```cpp
    attacks = RookAttacks[square][index]
```
The magic number is chosen offline so that all 2^N occupancies map to unique indices (no collisions).


#### How are magic numbers calculated?

Magic numbers are found offline using brute force search with heuristics, and then hardcoded into Stockfish.
- There is no known direct mathematical formula
- They are computed once (during development or build tooling)
- The engine does not search for them at runtime

Stockfish just ships with a precomputed array like:

```cpp
Magic RookMagics[64];
Magic BishopMagics[64];
```

But the search is not purely random, there are some heuristics which help is to reduce the search space. For eg: for rook we need only higher 12 bits, so first 52 btits of mask don't contribute anything and they can all be 0. Brute forcing 12 bit number is a solvable problem.

### Code Walkthrough

#### 1. The Magic Bitboard Data Structures

```cpp
Bitboard  RookMasks  [SQUARE_NB];
Bitboard  RookMagics [SQUARE_NB];
Bitboard* RookAttacks[SQUARE_NB];
unsigned  RookShifts [SQUARE_NB];

Bitboard  BishopMasks  [SQUARE_NB];
Bitboard  BishopMagics [SQUARE_NB];
Bitboard* BishopAttacks[SQUARE_NB];
unsigned  BishopShifts [SQUARE_NB];
```

These arrays store the pre-computed magic bitboard data for all 64 squares, separately for rooks and bishops.

##### 1. RookMasks[SQUARE_NB]
   
- Type: Array of 64 bitboards
- Purpose: Stores the relevant occupancy mask for each square
- Content: For square sq, RookMasks[sq] is a bitboard with 1's at all relevant squares (excluding edges)

##### 2. RookMagics[SQUARE_NB]

- Type: Array of 64 bitboards (used as 64-bit magic numbers)
- Purpose: Stores the magic constant for each square
- Content: For square sq, RookMagics[sq] is the magic number found through search that creates a perfect hash

##### 3. RookAttacks[SQUARE_NB]

- Type: Array of 64 pointers to bitboards
- Purpose: Each pointer points to the attack lookup table for that square
- Content:
  - RookAttacks[sq] is a pointer to an array of attack bitboards
  - The array size depends on the number of relevant bits for that square

**Memory layout:**

```cpp
// Conceptually:
RookAttacks[A1]  → points to array of 4096 bitboards (2^12 for corner)
RookAttacks[E4]  → points to array of 1024 bitboards (2^10 for center)
RookAttacks[A8]  → points to array of 4096 bitboards (2^12 for corner)
// etc.

// Example of what RookAttacks[A1] points to:
Bitboard rook_a1_table[4096] = {
    0x01010101010101FE,  // [0]    All relevant squares empty
    0x000000000000017E,  // [1]    Blocked by piece at a2
    0x0101010101010102,  // [2]    Blocked by piece at a3
    0x0000000000000102,  // [3]    Blocked by pieces at a2 and a3
    // ... 4092 more entries
};

RookAttacks[A1] = rook_a1_table;  // Pointer assignment
```

**Usage:**

```cpp
int index = (relevant_occupancy * RookMagics[sq]) >> shift;
Bitboard attacks = RookAttacks[sq][index];
```

Its pointer instead of hardcoding 4096, because only corner squares need 4096, center squares need only 1024.

Same logic is applied for bishops.

##### 4. RookShifts[SQUARE_NB]

It stores the amount of shift required for each square as per this formula

```cpp
int index = (relevant_occupancy * RookMagics[sq]) >> shift;
```

for corner square its 4096, for center its 1024, ...

#### 2. magic_index

```cpp
/// attacks_bb() returns a bitboard representing all the squares attacked by a
/// piece of type Pt (bishop or rook) placed on 's'. The helper magic_index()
/// looks up the index using the 'magic bitboards' approach.
template<PieceType Pt>
inline unsigned magic_index(Square s, Bitboard occupied) {

  extern Bitboard RookMasks[SQUARE_NB];
  extern Bitboard RookMagics[SQUARE_NB];
  extern unsigned RookShifts[SQUARE_NB];
  extern Bitboard BishopMasks[SQUARE_NB];
  extern Bitboard BishopMagics[SQUARE_NB];
  extern unsigned BishopShifts[SQUARE_NB];

  Bitboard* const Masks  = Pt == ROOK ? RookMasks  : BishopMasks;
  Bitboard* const Magics = Pt == ROOK ? RookMagics : BishopMagics;
  unsigned* const Shifts = Pt == ROOK ? RookShifts : BishopShifts;

  if (HasPext)
      return unsigned(pext(occupied, Masks[s]));

  if (Is64Bit)
      return unsigned(((occupied & Masks[s]) * Magics[s]) >> Shifts[s]);

  unsigned lo = unsigned(occupied) & unsigned(Masks[s]);
  unsigned hi = unsigned(occupied >> 32) & unsigned(Masks[s] >> 32);
  return (lo * unsigned(Magics[s]) ^ hi * unsigned(Magics[s] >> 32)) >> Shifts[s];
}
```

This is a sophisticated, optimized version of the basic magic index calculation. 

```cpp
int index = (relevant_occupancy * RookMagics[sq]) >> shift;
```


Template parameter Pt: Either ROOK or BISHOP

- Allows one function to work for both piece types
- Compiler generates two versions at compile time



##### Step 1: Compile time branching selects the corresponding masks, magics and shifts. 

What's happening:
- Uses compile-time selection to pick rook or bishop arrays
- Masks, Magics, Shifts are pointers to the appropriate arrays
- Since Pt is a template parameter, this is resolved at compile time (zero runtime cost!)

##### Step 2: Three Different Implementations

The function has three code paths for different CPU capabilities:

###### Path 1: PEXT Instruction (Modern CPUs)

```cpp
if (HasPext)
    return unsigned(pext(occupied, Masks[s]));
```

**PEXT (Parallel Bits Extract):** A single CPU instruction (BMI2 instruction set) that does **exactly** what we need!

```cpp
pext(source, mask) → extracts bits where mask=1, compacts them
```

> Take some bits from a number (source), 
> but only at positions where mask has 1s, 
> and pack them tightly into the low bits.

In magic bitboards, we want this:

```cpp
occ = occupied & mask;
index = encode(occ);
```

Where encode() means:
- Take the bits on relevant squares
- Convert them into a compact number from 0 .. 2^N - 1

That encoding step is exactly what PEXT does instantly.

**Mask tells which squares matter**

Example: rook on A1 has 12 relevant blocker squares:

```
a2 a3 a4 a5 a6 a7  b1 c1 d1 e1 f1 g1
```

So the mask has 1s in those bit positions.

**What PEXT does**

```cpp
pext(occupied, mask)
```
It does:
1. Look at every bit where mask has a 1
2. Copy that bit from occupied
3. Pack them into a small integer

Example

```
bit:       7 6 5 4 3 2 1 0
occupied = 1 0 1 1 0 1 0 1
mask     = 0 1 1 0 1 0 0 0
```

Mask selects bits:
- bit 6
- bit 5
- bit 3

```
bit6 = 0
bit5 = 1
bit3 = 1
```

Now PEXT packs them into low bits:

```
result = 0b011
```

So

```cpp
pext(occupied, mask) = 3
```

We can clearly see why this generates a unique number between 0 to 2^N - 1 (4096 for rook on a1). Because each mask is unique, depending on occupancy some bits of mask might be turned to 0, but the result will always be unique.

This entirely skips the use of magics. 

This is the fastest method!

###### Path 2: 64-bit Magic Bitboards (Standard Case)

```cpp
if (Is64Bit)
    return unsigned(((occupied & Masks[s]) * Magics[s]) >> Shifts[s]);
```

This is our familiar version:

```cpp
int index = (relevant_occupancy * RookMagics[sq]) >> shift;
```

When used: On 64-bit CPUs without PEXT (most common case until ~2013)

###### Path 3: 32-bit Magic Bitboards (Legacy)

```cpp
unsigned lo = unsigned(occupied) & unsigned(Masks[s]);
unsigned hi = unsigned(occupied >> 32) & unsigned(Masks[s] >> 32);
return (lo * unsigned(Magics[s]) ^ hi * unsigned(Magics[s] >> 32)) >> Shifts[s];
```

**Why this is needed:** On 32-bit CPUs, multiplying two 64-bit numbers is expensive!

**The trick:** Split 64-bit numbers into two 32-bit halves

```
occupied (64-bit) = [hi 32 bits | lo 32 bits]
Masks[s] (64-bit) = [hi 32 bits | lo 32 bits]

Step 1: Extract relevant bits in each half
  lo = (occupied & 0xFFFFFFFF) & (Masks[s] & 0xFFFFFFFF)
  hi = (occupied >> 32) & (Masks[s] >> 32)

Step 2: Hash each half separately
  lo_hash = lo * (lower 32 bits of Magics[s])
  hi_hash = hi * (upper 32 bits of Magics[s])

Step 3: Combine with XOR and shift
  index = (lo_hash ^ hi_hash) >> Shifts[s]
```

**Why XOR?** It mixes the two 32-bit hashes into one hash value

**When used:** On 32-bit CPUs (rare nowadays, but important for embedded systems)

The underlying tables are different for PEXT and magic bitboard version, so we don't need to worry about producing same index in both versions. 

But this also means the type of implementation is decided at compile time, a binary compiled with PEXT implementation can't be used on 64 bit CPU without BMI2.

#### 3. init_magics

```cpp
 // init_magics() computes all rook and bishop attacks at startup. Magic
  // bitboards are used to look up attacks of sliding pieces. As a reference see
  // chessprogramming.wikispaces.com/Magic+Bitboards. In particular, here we
  // use the so called "fancy" approach.

  void init_magics(Bitboard table[], Bitboard* attacks[], Bitboard magics[],
                   Bitboard masks[], unsigned shifts[], Square deltas[], Fn index) {

    int seeds[][RANK_NB] = { { 8977, 44560, 54343, 38998,  5731, 95205, 104912, 17020 },
                             {  728, 10316, 55013, 32803, 12281, 15100,  16645,   255 } };

    Bitboard occupancy[4096], reference[4096], edges, b;
    int age[4096] = {0}, current = 0, i, size;

    // attacks[s] is a pointer to the beginning of the attacks table for square 's'
    attacks[SQ_A1] = table;

    for (Square s = SQ_A1; s <= SQ_H8; ++s)
    {
        // Board edges are not considered in the relevant occupancies
        edges = ((Rank1BB | Rank8BB) & ~rank_bb(s)) | ((FileABB | FileHBB) & ~file_bb(s));

        // Given a square 's', the mask is the bitboard of sliding attacks from
        // 's' computed on an empty board. The index must be big enough to contain
        // all the attacks for each possible subset of the mask and so is 2 power
        // the number of 1s of the mask. Hence we deduce the size of the shift to
        // apply to the 64 or 32 bits word to get the index.
        masks[s]  = sliding_attack(deltas, s, 0) & ~edges;
        shifts[s] = (Is64Bit ? 64 : 32) - popcount(masks[s]);

        // Use Carry-Rippler trick to enumerate all subsets of masks[s] and
        // store the corresponding sliding attack bitboard in reference[].
        b = size = 0;
        do {
            occupancy[size] = b;
            reference[size] = sliding_attack(deltas, s, b);

            if (HasPext)
                attacks[s][pext(b, masks[s])] = reference[size];

            size++;
            b = (b - masks[s]) & masks[s];
        } while (b);

        // Set the offset for the table of the next square. We have individual
        // table sizes for each square with "Fancy Magic Bitboards".
        if (s < SQ_H8)
            attacks[s + 1] = attacks[s] + size;

        if (HasPext)
            continue;

        PRNG rng(seeds[Is64Bit][rank_of(s)]);

        // Find a magic for square 's' picking up an (almost) random number
        // until we find the one that passes the verification test.
        do {
            do
                magics[s] = rng.sparse_rand<Bitboard>();
            while (popcount((magics[s] * masks[s]) >> 56) < 6);

            // A good magic must map every possible occupancy to an index that
            // looks up the correct sliding attack in the attacks[s] database.
            // Note that we build up the database for square 's' as a side
            // effect of verifying the magic.
            for (++current, i = 0; i < size; ++i)
            {
                unsigned idx = index(s, occupancy[i]);

                if (age[idx] < current)
                {
                    age[idx] = current;
                    attacks[s][idx] = reference[i];
                }
                else if (attacks[s][idx] != reference[i])
                    break;
            }
        } while (i < size);
    }
  }
```

**Parameters:**

- table[] - Large pre-allocated array to hold all attack bitboards
- attacks[] - Array of 64 pointers, will point into table[]
- magics[] - Will be filled with magic numbers for each square
- masks[] - Will be filled with relevant occupancy masks
- shifts[] - Will be filled with shift amounts
- deltas[] - Movement directions (e.g., {+8, -8, +1, -1} for rook)
- index - Function pointer to calculate index (64-bit or 32-bit version)

Called twice at startup:

```cpp
init_magics(RookTable, RookAttacks, RookMagics, RookMasks, RookShifts, 
            RookDeltas, magic_index<ROOK>);
            
init_magics(BishopTable, BishopAttacks, BishopMagics, BishopMasks, BishopShifts,
            BishopDeltas, magic_index<BISHOP>);
```

##### Part 1: Random Seeds

```cpp
int seeds[][RANK_NB] = { 
    { 8977, 44560, 54343, 38998,  5731, 95205, 104912, 17020 },  // 64-bit
    {  728, 10316, 55013, 32803, 12281, 15100,  16645,   255 }   // 32-bit
};
```

Purpose: Seeds for random number generator, one per rank
Why different seeds per rank?
- Squares on different ranks have different numbers of relevant bits
- Different seeds help find magic numbers faster
- These specific values were found empirically to work well

```cpp
attacks[SQ_A1] = table;

for (Square s = SQ_A1; s <= SQ_H8; ++s) {
    // ... (work for square s)
    
    if (s < SQ_H8)
        attacks[s + 1] = attacks[s] + size;
}
```

**What's happening:** Building **variable-sized tables** in one contiguous array
```
table[] (one big array):
┌────────────────────────────────────────────────────┐
│ A1 attacks | A2 attacks | A3 attacks | ... | H8    │
│ (4096)     | (2048)     | (2048)     |     | (4096)│
└────────────────────────────────────────────────────┘
 ↑            ↑            ↑                  ↑
 attacks[A1]  attacks[A2]  attacks[A3]       attacks[H8]
```

Each square gets a pointer to its portion of the table:

```cpp
attacks[A1] = &table[0];
attacks[A2] = &table[4096];      // A1 used 4096 entries
attacks[A3] = &table[4096+2048]; // A2 used 2048 entries
// etc.
```

This is the "Fancy Magic Bitboards" approach - variable-sized tables to save memory!

##### Part 3: Compute Mask for Each Square

```cpp
for (Square s = SQ_A1; s <= SQ_H8; ++s)
{
    // Board edges are not considered in the relevant occupancies
    edges = ((Rank1BB | Rank8BB) & ~rank_bb(s)) | ((FileABB | FileHBB) & ~file_bb(s));

    masks[s] = sliding_attack(deltas, s, 0) & ~edges;
    shifts[s] = (Is64Bit ? 64 : 32) - popcount(masks[s]);
```

`edges` contains a bitboard where 1 means we can ignore that square for occupancy calculation. Its calculated for each square

###### Step 1: Calculate edge squares to exclude

```cpp
// For rook on e4:
edges = ((Rank1BB | Rank8BB) & ~rank_bb(E4))  // Ranks 1 and 8, but NOT rank 4
      | ((FileABB | FileHBB) & ~file_bb(E4)); // Files a and h, but NOT file e

// Result: edges excludes e1, e8, a4, h4
```

###### Step 2: Compute sliding attacks on empty board, then remove edges

```cpp
masks[s] = sliding_attack(deltas, s, 0)  // Attacks on empty board
         & ~edges;                        // Remove edge squares

// For rook on a1:
// sliding_attack gives: a1-a8, a1-h1 (full rank and file)
// Remove edges: a8, h1
// Result: {a2, a3, a4, a5, a6, a7, b1, c1, d1, e1, f1, g1}
```

###### Step 3: Calculate shift amount

```cpp
shifts[s] = (Is64Bit ? 64 : 32) - popcount(masks[s]);

// For rook on a1: 12 relevant bits
// shifts[A1] = 64 - 12 = 52 (for 64-bit)
```

##### Part 4: Enumerate All Occupancy Patterns (Carry-Rippler)

```cpp
b = size = 0;
do {
    occupancy[size] = b;
    reference[size] = sliding_attack(deltas, s, b);
    
    if (HasPext)
        attacks[s][pext(b, masks[s])] = reference[size];
    
    size++;
    b = (b - masks[s]) & masks[s];  // Carry-Rippler trick!
} while (b);
```

For this square s, generate every possible blocker configuration on the relevant squares.

For a rook square, you may have:
- 12 relevant squares
- so 2¹² = 4096 possible occupancies

Stockfish must generate all of them at startup:
- blocker pattern → correct attack bitboard

So we need:

```cpp
for every subset b of mask:
    attacks[b] = sliding_attack(...)
```

**Carry-Rippler Trick: Enumerating all subsets**

The trick is:

```cpp
b = (b - mask) & mask;
```

This generates all subsets of mask in a cycle.

What does “subset” mean?

If:

```cpp
mask = 0b10110
```

The subset bitboards are:

```cpp
00000
00010
00100
00110
10000
10010
10100
10110
```

Note: how 1st and 4th bit remain 0 in all subsets. Every subset contains only bits that exist in mask.


**Why is this called Carry-Rippler?**

Because subtraction causes a binary carry ripple through bits.

When you subtract mask, the borrow propagates through the bit pattern, flipping bits in exactly the right way to produce the next subset.


The Carry-Rippler Trick: Enumerates all subsets of masks[s]

How it works:

```cpp
// Example: mask = 0b00010110 (bits at positions 1, 2, 4)
// We want to generate: 0b00000000, 0b00000010, 0b00000100, 0b00000110, 
//                      0b00010000, 0b00010010, 0b00010100, 0b00010110

b = 0;
Iteration 0: b = 0b00000000  // Subset: {}
Iteration 1: b = 0b00000010  // Subset: {1}
Iteration 2: b = 0b00000100  // Subset: {2}
Iteration 3: b = 0b00000110  // Subset: {1, 2}
Iteration 4: b = 0b00010000  // Subset: {4}
Iteration 5: b = 0b00010010  // Subset: {1, 4}
Iteration 6: b = 0b00010100  // Subset: {2, 4}
Iteration 7: b = 0b00010110  // Subset: {1, 2, 4}
Iteration 8: b = 0b00000000  // Wraps around, exit
```

Why `b = (b - masks[s]) & masks[s]` works:

- Subtracting flips bits in a clever way
- AND with mask keeps only relevant bits
- Magically iterates through all 2^N subsets!

If PEXT available: Fill table immediately

```cpp
if (HasPext)
    attacks[s][pext(b, masks[s])] = reference[size];
// PEXT gives us the index directly, so populate table now
```

##### Part 5: Find Magic Numbers (The Hard Part!)

```cpp
if (HasPext)
    continue;  // Skip magic finding if we have PEXT

PRNG rng(seeds[Is64Bit][rank_of(s)]);

do {
    // Generate random magic candidate
    do
        magics[s] = rng.sparse_rand<Bitboard>();
    while (popcount((magics[s] * masks[s]) >> 56) < 6);
    
    // Test if this magic works
    for (++current, i = 0; i < size; ++i) {
        unsigned idx = index(s, occupancy[i]);
        
        if (age[idx] < current) {
            age[idx] = current;
            attacks[s][idx] = reference[i];
        }
        else if (attacks[s][idx] != reference[i])
            break;  // Collision! Try next magic
    }
} while (i < size);
```

**Step 5a: Generate Magic Candidate**


```cpp
do
    magics[s] = rng.sparse_rand<Bitboard>();
while (popcount((magics[s] * masks[s]) >> 56) < 6);
```

`sparse_rand()`: Generates numbers with few bits set (sparse bitboards)

- Magic numbers work better when sparse
- Fewer bits = less chance of unwanted carries

Filter: `popcount((magics[s] * masks[s]) >> 56) < 6`

- Quick rejection test
- Multiplying magic by mask should produce at least 6 bits in top byte
- If not enough bits at top, magic won't spread occupancy well

**Step 5b: Test the Magic**

```cpp
for (++current, i = 0; i < size; ++i) {
    unsigned idx = index(s, occupancy[i]);
    
    if (age[idx] < current) {
        age[idx] = current;
        attacks[s][idx] = reference[i];
    }
    else if (attacks[s][idx] != reference[i])
        break;  // Collision!
}
```

**The age[]** array trick: Detects collisions efficiently

```cpp
int age[4096] = {0};  // Tracks which "attempt" last wrote to each index
int current = 0;       // Current attempt number

// For each new magic candidate:
++current;  // New attempt number

for each occupancy pattern i:
    idx = hash(occupancy[i]) using candidate magic
    
    if (age[idx] < current):
        // This index hasn't been used in this attempt yet
        age[idx] = current;
        attacks[s][idx] = reference[i];  // Store the correct attacks
    else:
        // This index was already used in this attempt!
        if (attacks[s][idx] != reference[i]):
            // COLLISION! Different occupancies map to same index
            // but have different attacks
            break;  // Reject this magic
```

Why this works:

- If two occupancies hash to the same index but have the same attacks, it's OK (constructive collision)
- If they have different attacks, the magic is invalid (destructive collision)
- age[] lets us detect this without clearing the array each attempt

A simple way to make sense of carry rippler is to think of subtraction as 2's complement addition. 

If we take `0b111` as mask. Cycle goes like this

```
b = 0, (0 - 0b111) = (0 + 0b001) = 0b0001 = 1
b = 1, (1 - 0b111) = (1 + 0b001) = 0b0010 =  2
b = 2, (0b010 - 0b111) = (0b010 + 0b001) = 0b0011 = 3
b = 2, (0b011 - 0b111) = (0b011 + 0b001) = 0b0100 = 4
...
```

We can see how it goes on generating all possible bit combinations. 

Similarly for a partial mask like `0b101`

```
b = 0, (0 - 0b101) = (0 + 0b011) = (0b011 & 0b101) = 0b001
b = 1, (1 - 0b001) = (0b001 + 0b011) = (0b100 & 0b101) = 0b100
b = 4, (4 - 0b001) = (0b100 + 0b011) = (0b111 & 0b101) = 0b101
b = 5, (5 - 0b001) = (0b101 + 0b011) = (0b000 & 0b101) = 0b000 <- wrap back, cycle ends
```


