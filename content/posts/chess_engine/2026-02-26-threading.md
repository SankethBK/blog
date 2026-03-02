---
title:  "Threading in Stockfish"
date:   2026-02-26
draft: true
categories: ["chess engines"]
tags: ["threading"]


---

# Threading in Stockfish

## YBWC (Young Brothers Wait Concept)

It is a strategy for parallelizing alpha-beta search.

The core idea:

> Do NOT immediately split all children across threads.
> First search the “youngest brother” (the first move) alone.
> Only if needed, allow other threads to help.

### Why “Young Brothers”?

Imagine a node with moves:

```
Move A
Move B
Move C
Move D
```

In alpha-beta, Move A is most important because:
- Move ordering says it’s likely best.
- If Move A causes a cutoff,
you don’t need to search B, C, D at all.


If you parallelize blindly:
- Thread 1 searches A
- Thread 2 searches B
- Thread 3 searches C

You may waste huge work,
because A might cut off everything.

So YBWC says:

> Let the first child search alone.
> Only if it does NOT cause cutoff,
> then allow other threads to search siblings.

### Why This Matters

Alpha-beta pruning depends heavily on move ordering.

The first move is often the PV candidate.

If that move produces:

```cpp
score >= beta
```

Everything else is useless.

So parallelizing siblings too early destroys pruning efficiency.

YBWC preserves pruning quality.

### Basic Flow of YBWC

At a node:

```
Search Move A (alone)
If cutoff → return immediately
Else:
    Allow other threads to search Move B, C, D
```

This keeps:
- High pruning efficiency
- Reduced wasted parallel work

YBWC enforces:

> The first move must complete before siblings are searched in parallel.

That first move is the “youngest brother.”

### Where Is YBWC Used?

It is used in:
 - Split-point based parallel alpha-beta
 - Classical parallel search engines
 - Some early versions of Stockfish

It is especially useful in engines that:
 - Use heavy split-point systems
 - Carefully manage work sharing

### YBWC vs Lazy SMP

YBWC is structured, coordinated parallelism.

Lazy SMP is looser:
- Threads independently search root
- Share TT
- Less strict synchronization

Modern Stockfish uses more Lazy SMP style,
but still incorporates YBWC-like behavior at split points.

### Tradeoff

YBWC reduces wasted work,
but introduces:
- Synchronization overhead
- Waiting time for idle threads

So engines balance:
- Parallel efficiency
- Synchronization cost
- Pruning preservation

YWBC heavily relies on first move to be good, but practically it may not be entrely true as the moves are ordered only based on heuristics. If the second move is better than the first, then the overhead occurs in terms of both wait time and wasted searches as the move which can cause cutoff is searched later. 

### Split Points

A split point is a node in the search tree where the work gets divided among multiple threads.

When a thread reaches a node and realizes it has moves left to search that could potentially be parallelized, it creates a split point — essentially a shared data structure that says:
> "I'm at this node, I've searched move A, here are the remaining moves B, C, D — someone help me search them."

Idle threads can then "join" this split point, grab an unsearched move, search it, and report the result back.

**What the split point tracks:**

- The current position
- Which moves have been searched / are being searched
- The current alpha/beta values (shared, so threads can see cutoffs)
- The best score found so far
- Which threads are working here

**Why it's complex**

Since multiple threads are reading and writing alpha/beta at the same split point simultaneously, you need locks/mutexes. When thread 2 finishes a move and updates the score, thread 3 needs to see that updated alpha before searching its move — otherwise it searches with stale bounds and wastes work.

This locking overhead is exactly what YBWC tried to minimize (by only splitting when necessary), and what Lazy SMP eliminated entirely by just... not having split points at all. In Lazy SMP, threads never share a node's alpha/beta mid-search. The TT is the only shared state, and TT reads/writes are handled with much simpler atomic operations.

So "split point management" was the main complexity cost of YBWC that Lazy SMP threw away.

## Lazy SMP (Symmetric Multi-Processing)

Lazy SMP is the parallel search strategy used in modern Stockfish.
It replaced YBWC around Stockfish 7 (2016).

The core idea is almost embarrassingly simple:

> Launch N threads. All search the same root position.
> Let them share a transposition table.
> Do nothing else to coordinate them.

### Why This Works At All

Intuition says: if all threads search the same thing, you get no speedup.
But in practice, threads naturally diverge because:
- They run at slightly different speeds
- They complete nodes at different times
- TT hits cause some to skip work others did

So thread 2 might reach a node at depth 8 just as thread 1
finishes it and writes the result to the TT.
Thread 2 gets a "free" result and moves on to something else.
The threads end up searching *different parts* of the tree
without any explicit coordination.

### The Shared Transposition Table

The TT is the only communication channel between threads.
When thread 1 finishes searching a node, it writes:
- Best move
- Score
- Depth
- Bound type (exact, lower, upper) 

When thread 2 hits that same node, it reads the TT entry
and potentially gets a cutoff or a good move to try first.
This is the entire coordination mechanism.

### How Stockfish Implements It

Each thread runs its own independent iterative deepening loop.
But threads are given slightly different starting depths
so they are naturally out of phase with each other:

- Thread 0 searches depth 1, 2, 3, 4 ...
- Thread 1 searches depth 2, 3, 4, 5 ...
- Thread 2 searches depth 1, 3, 4, 5 ...

(The exact skipping varies, but the idea is deliberate desynchronization.)

This avoids the thundering herd problem where all threads
redundantly search exactly the same nodes at the same depth.

### What Gets Shared, What Doesn't

Shared (global):
- Transposition table
- Root position
- Some search limits (time, nodes)

Per-thread (local):
- Killer moves
- History heuristic tables
- PV
- Stack/ply info


Each thread has its own search state.
The TT is the only cross-thread "memory."

### Why Lazy SMP Beat YBWC in Practice

YBWC is theoretically more principled — it carefully
preserves pruning efficiency. But it has real costs:
- Complex split-point management
- Threads sitting idle waiting for the first move to finish
- Synchronization overhead grows with thread count

## Code Walkthrough

There are three layers:

```
ThreadPool   → manages all threads
   ↓
Thread       → worker thread
   ↓
Search       → recursive alpha-beta
```

Each thread:
- Has its own search state
- Own pawn/material tables
- Own history tables
- Shares TT globally

### The Thread Class

```cpp
/// Thread struct keeps together all the thread-related stuff. We also use
/// per-thread pawn and material hash tables so that once we get a pointer to an
/// entry its life time is unlimited and we don't have to care about someone
/// changing the entry under our feet.

class Thread {

  std::thread nativeThread;
  Mutex mutex;
  ConditionVariable sleepCondition;
  bool exit, searching;

public:
  Thread();
  virtual ~Thread();
  virtual void search();
  void idle_loop();
  void start_searching(bool resume = false);
  void wait_for_search_finished();
  void wait(std::atomic_bool& b);

  Pawns::Table pawnsTable;
  Material::Table materialTable;
  Endgames endgames;
  size_t idx, PVIdx;
  int maxPly, callsCnt;
  uint64_t tbHits;

  Position rootPos;
  Search::RootMoves rootMoves;
  Depth rootDepth;
  Depth completedDepth;
  std::atomic_bool resetCalls;
  HistoryStats history;
  MoveStats counterMoves;
  FromToStats fromTo;
  CounterMoveHistoryStats counterMoveHistory;
};
```

```cpp
std::thread nativeThread;
```

The actual OS thread object. This is what the operating system schedules. Everything else in this class is just data that lives alongside it.

```cpp
Mutex mutex;
ConditionVariable sleepCondition;
```

These two work together to implement sleep/wake. When a thread has nothing to do, it calls `wait()` on `sleepCondition`, which atomically releases the mutex and puts the thread to sleep. When the main thread wants to wake it up (new search started), it signals the condition variable. This is standard producer-consumer pattern — much better than busy-waiting which would waste a CPU core spinning.

```cpp
bool exit, searching;
```

`exit` is the shutdown flag — when Stockfish quits, it sets this to true and wakes all threads so they can exit their `idle_loop`. `searching` tells the thread whether it should be searching or sleeping when it wakes up.

```cpp
Thread();
virtual ~Thread();
```

Constructor starts the OS thread and puts it into `idle_loop`. Destructor signals exit and joins the thread (waits for it to finish).

```cpp
virtual void search();
```

Virtual because `MainThread` overrides it. This is where the actual search logic lives — iterative deepening loop etc.

```cpp
void idle_loop();
```

The thread spends most of its life here — sleeping, waiting to be woken up, then calling `search()`, then going back to sleep. It's an infinite loop that only exits when exit is true.

```cpp
void start_searching(bool resume = false);
void wait_for_search_finished();
```

`start_searching` wakes the thread up to begin a search. `wait_for_search_finished` blocks the caller until this thread is done — used by the main thread to synchronize at the end of search before emitting `bestmove`.

```cpp
void wait(std::atomic_bool& b);
```

A general purpose wait — blocks until the atomic bool becomes true. Used in various synchronization points.

`std::atomic_bool` is:

> A boolean variable that can be safely read and written by multiple threads without data races.

**Per-thread cache tables**

```cpp
Pawns::Table pawnsTable;
Material::Table materialTable;
Endgames endgames;
```

`pawnsTable` caches pawn structure evaluations — pawn eval is expensive (lots of structure analysis) and pawn structures repeat constantly across the search tree, so caching saves huge time. Same idea for `materialTable` — caches material imbalance evaluations. `Endgames` stores endgame-specific evaluation functions and is also per-thread for the same reason.

**Identity and diagnostics**

```cpp
size_t idx, PVIdx;
```

`idx` is the thread's index in the ThreadPool (0 = main thread, 1, 2, 3...). Used for staggering depths in Lazy SMP — thread with `idx=1` might skip odd depths, etc. `PVIdx` is for MultiPV mode — when you ask Stockfish for the top N moves, each gets a PVIdx.

```cpp
int maxPly, callsCnt;
```

`maxPly` is the deepest ply reached in the current search — reported as `seldepth` in UCI output. `callsCnt` counts how many times a certain check function has been called — used to throttle time checks (you don't want to check the clock every single node, so you check every ~1000 calls).

```cpp
uint64_t tbHits;
```

Count of Syzygy tablebase hits — reported in UCI output as `tbhits`.

**Search state**

```cpp
Position rootPos;
Search::RootMoves rootMoves;
```

Each thread gets its own copy of the root position and list of legal moves at the root. They start identical across threads but threads maintain their own position state as they traverse the tree.

```cpp
Depth rootDepth;
Depth completedDepth;
```

`rootDepth` is the depth currently being searched in the iterative deepening loop. `completedDepth` is the last depth fully completed — this is important because if time runs out mid-search, you fall back to the result from `completedDepth`, not the incomplete `rootDepth`.