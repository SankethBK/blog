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

Complementary information!