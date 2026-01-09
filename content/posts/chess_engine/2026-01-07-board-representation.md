---
title:  "Representation of The Game State"
date:   2026-01-07
draft: false
categories: ["chess engines"]
tags: ["board representation", "stockfish"]
author: Sanketh
---

# Representation of The Game State

## The Position Class

The `Position` class is the core data structure in Stockfish that represents the complete state of a chess game at any given moment. It stores the board, pieces, game state, and provides methods to query and manipulate the position.

```cpp
class Position {
public:
  static void init();

  Position() = default;
  Position(const Position&) = delete;
  Position& operator=(const Position&) = delete;

  // FEN string input/output
  Position& set(const std::string& fenStr, bool isChess960, StateInfo* si, Thread* th);
  const std::string fen() const;

  // Position representation
  Bitboard pieces() const;
  Bitboard pieces(PieceType pt) const;
  Bitboard pieces(PieceType pt1, PieceType pt2) const;
  Bitboard pieces(Color c) const;
  Bitboard pieces(Color c, PieceType pt) const;
  Bitboard pieces(Color c, PieceType pt1, PieceType pt2) const;
  Piece piece_on(Square s) const;
  Square ep_square() const;
  bool empty(Square s) const;
  template<PieceType Pt> int count(Color c) const;
  template<PieceType Pt> const Square* squares(Color c) const;
  template<PieceType Pt> Square square(Color c) const;

  // Castling
  int can_castle(Color c) const;
  int can_castle(CastlingRight cr) const;
  bool castling_impeded(CastlingRight cr) const;
  Square castling_rook_square(CastlingRight cr) const;

  // Checking
  Bitboard checkers() const;
  Bitboard discovered_check_candidates() const;
  Bitboard pinned_pieces(Color c) const;
  Bitboard check_squares(PieceType pt) const;

  // Attacks to/from a given square
  Bitboard attackers_to(Square s) const;
  Bitboard attackers_to(Square s, Bitboard occupied) const;
  Bitboard attacks_from(Piece pc, Square s) const;
  template<PieceType> Bitboard attacks_from(Square s) const;
  template<PieceType> Bitboard attacks_from(Square s, Color c) const;
  Bitboard slider_blockers(Bitboard sliders, Square s, Bitboard& pinners) const;

  // Properties of moves
  bool legal(Move m) const;
  bool pseudo_legal(const Move m) const;
  bool capture(Move m) const;
  bool capture_or_promotion(Move m) const;
  bool gives_check(Move m) const;
  bool advanced_pawn_push(Move m) const;
  Piece moved_piece(Move m) const;
  Piece captured_piece() const;

  // Piece specific
  bool pawn_passed(Color c, Square s) const;
  bool opposite_bishops() const;

  // Doing and undoing moves
  void do_move(Move m, StateInfo& st, bool givesCheck);
  void undo_move(Move m);
  void do_null_move(StateInfo& st);
  void undo_null_move();

  // Static Exchange Evaluation
  bool see_ge(Move m, Value value) const;

  // Accessing hash keys
  Key key() const;
  Key key_after(Move m) const;
  Key material_key() const;
  Key pawn_key() const;

  // Other properties of the position
  Color side_to_move() const;
  Phase game_phase() const;
  int game_ply() const;
  bool is_chess960() const;
  Thread* this_thread() const;
  uint64_t nodes_searched() const;
  bool is_draw() const;
  int rule50_count() const;
  Score psq_score() const;
  Value non_pawn_material(Color c) const;

  // Position consistency check, for debugging
  bool pos_is_ok(int* failedStep = nullptr) const;
  void flip();

private:
  // Initialization helpers (used while setting up a position)
  void set_castling_right(Color c, Square rfrom);
  void set_state(StateInfo* si) const;
  void set_check_info(StateInfo* si) const;

  // Other helpers
  void put_piece(Piece pc, Square s);
  void remove_piece(Piece pc, Square s);
  void move_piece(Piece pc, Square from, Square to);
  template<bool Do>
  void do_castling(Color us, Square from, Square& to, Square& rfrom, Square& rto);

  // Data members
  Piece board[SQUARE_NB];
  Bitboard byTypeBB[PIECE_TYPE_NB];
  Bitboard byColorBB[COLOR_NB];
  int pieceCount[PIECE_NB];
  Square pieceList[PIECE_NB][16];
  int index[SQUARE_NB];
  int castlingRightsMask[SQUARE_NB];
  Square castlingRookSquare[CASTLING_RIGHT_NB];
  Bitboard castlingPath[CASTLING_RIGHT_NB];
  uint64_t nodes;
  int gamePly;
  Color sideToMove;
  Thread* thisThread;
  StateInfo* st;
  bool chess960;
};
```

### Class Design Decisions

#### 1. Non-Copyable

```cpp
Position(const Position&) = delete;
Position& operator=(const Position&) = delete;
```

- Cannot be copied (copy constructor and assignment deleted)
- Why? Positions are heavy objects with complex state
- Must be moved or passed by reference/pointer
- Prevents accidental expensive copies

#### 2. Default Constructor

```cpp
Position() = default;
```

- Creates uninitialized position
- Must call `set()` to initialize with FEN string

### Core Data Members

#### 1. Board Representation - MailBox 

```cpp
Piece board[SQUARE_NB];  // SQUARE_NB = 64
```

- Mailbox representation: Direct lookup "what piece is on square X?"
- `board[e4]` → returns `W_KNIGHT` or `NO_PIECE`
- Fast for: "piece_on(Square s)"

#### 2. Bitboard Representation

Technically we need 12 bitboards to represent the all the pieces on chessboard.

```
white pawns
white knights
white bishops
white rooks
white queens
white king

black pawns
black knights
black bishops
black rooks
black queens
black king
```

**Stockfish’s representation (factorized)**

##### 1. byTypeBB

```cpp
Bitboard byTypeBB[PIECE_TYPE_NB];  // PIECE_TYPE_NB = 8
```

`byTypeBB` is an array of 8 bitboards. This stores piece-type bitboards regardless of color:

```cpp
enum PieceType {
  NO_PIECE_TYPE,  // = 0
  PAWN,           // = 1
  KNIGHT,         // = 2
  BISHOP,         // = 3
  ROOK,           // = 4
  QUEEN,          // = 5
  KING,           // = 6
  ALL_PIECES = 0, // = 0 (EXPLICIT assignment, alias for NO_PIECE_TYPE)
  PIECE_TYPE_NB = 8  // = 8 (total count for array sizing)
};
```

**Index mapping**

```cpp
byTypeBB[0] = byTypeBB[NO_PIECE_TYPE] = byTypeBB[ALL_PIECES] = all pieces (both colors)
byTypeBB[1] = byTypeBB[PAWN]          = all pawns
byTypeBB[2] = byTypeBB[KNIGHT]        = all knights
byTypeBB[3] = byTypeBB[BISHOP]        = all bishops
byTypeBB[4] = byTypeBB[ROOK]          = all rooks
byTypeBB[5] = byTypeBB[QUEEN]         = all queens
byTypeBB[6] = byTypeBB[KING]          = all kings
byTypeBB[7] = ??? // (UNUSED, for padding)
```

##### 2. byColorBB

```cpp
Bitboard byColorBB[COLOR_NB];  // COLOR_NB = 2
```

- Bitboards by color: All pieces of a color
- byColorBB[WHITE] → all white pieces
- byColorBB[BLACK] → all black pieces
- Fast for: "where are all black pieces?"

##### 3. castlingPath

```cpp
Bitboard castlingPath[CASTLING_RIGHT_NB]; // CASTLING_RIGHT_NB = 16
```

THis seems like the biggest bitboard array with eleemnts `16 × 8 bytes = 128 bytes`.

Let's understand why its like this

```cpp
enum CastlingRight {
  NO_CASTLING,
  WHITE_OO,
  WHITE_OOO = WHITE_OO << 1,
  BLACK_OO  = WHITE_OO << 2,
  BLACK_OOO = WHITE_OO << 3,
  ANY_CASTLING = WHITE_OO | WHITE_OOO | BLACK_OO | BLACK_OOO,
  CASTLING_RIGHT_NB = 16
};
```

So the values range from:

```
0000 (0)  → no castling
0001 (1)  → white O-O
0010 (2)  → white O-O-O
...
1111 (15) → all castling rights
```

16 possible states, hence `CASTLING_RIGHT_NB` = 16

**What castlingPath Actually Stores?**

`castlingPath` stores the squares that must be empty for each individual castling move, not for each combination of rights. It has 16 bitboards but only 4 of them are used.

```
castlingPath[NO_CASTLING]  // Index 0 - unused
castlingPath[WHITE_OO]     // Index 1 - squares between white king and h1 rook
castlingPath[WHITE_OOO]    // Index 2 - squares between white king and a1 rook  
castlingPath[BLACK_OO]     // Index 4 - squares between black king and h8 rook
castlingPath[BLACK_OOO]    // Index 8 - squares between black king and a8 rook
```

Why? Because they're bit flags designed to be combined with bitwise OR:

```cpp
int rights = WHITE_OO | BLACK_OOO;  // = 1 | 8 = 9 (0b1001)
```

We can see most of the squares of bitboards will be empty. This is a deliberate design choice, so that we can quickly compute operations like this:

```cpp
bool Position::castling_impeded(CastlingRight cr) const {
  return byTypeBB[ALL_PIECES] & castlingPath[cr];
}
```

If any overlap exists, the AND is non-zero → castling blocked.

This is:
- 1 CPU instruction (AND)
- 1 branchless boolean check


#### 3. PieceCount

```cpp
int pieceCount[PIECE_NB];  // PIECE_NB = 16
```

- Count of each piece type per color
- `pieceCount[W_KNIGHT]` → number of white knights (0-10)
- Fast for: "how many white rooks exist?"

```cpp
Square pieceList[PIECE_NB][16];
```

- List of squares for each piece type
- `pieceList[W_KNIGHT] = {SQ_B1, SQ_G1, SQ_NONE, ...}`
- Max 16 of any piece (all pawns could promote)
- Fast for: iterating over pieces (no need to scan entire board)
- Terminated by `SQ_NONE`


#### 4. Index 

```cpp
int index[SQUARE_NB];
```

- Reverse lookup: Which index in pieceList?
- `index[b1]` → 0 (first white knight in pieceList)
- Used when moving/removing pieces to update pieceList efficiently

#### Why Multiple Representations?

Redundancy for speed! Different operations need different views:

| Operation | Best Representation |
|-----------|---------------------|
| "What piece is on e4?" | `board[e4]` (O(1)) |
| "Where are all white pieces?" | `byColorBB[WHITE]` (O(1)) |
| "Are there any black rooks on the 7th rank?" | `byTypeBB[ROOK] & byColorBB[BLACK] & Rank7BB` |
| "Loop through all white knights" | `pieceList[W_KNIGHT]` (no empty squares) |


