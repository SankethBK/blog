---
title:  "C++ Used in Stockfish"
date:   2026-01-05
draft: false
categories: ["chess engines", "c++"]
tags: ["c++", "stockfish"]
author: Sanketh
---

# C++ Used in Stockfish

Stockfish is written in a style of C++ that prioritizes performance, predictability, and compile-time resolution over traditional object-oriented design. Rather than heavy use of classes, inheritance, or virtual functions, the engine relies on enums, inline functions, templates, bitwise operations, and plain data structures. This makes the code extremely fast, cache-friendly, and suitable for deep search loops executed billions of times.

## Enums as Core Types

Enums form the backbone of Stockfish’s type system. Instead of using classes for concepts like pieces, squares, colors, or moves, Stockfish represents them as enums with carefully chosen integer values.

Examples include:
 - Color → WHITE, BLACK
 - PieceType → PAWN, KNIGHT, BISHOP, …
 - Piece → W_PAWN, B_QUEEN, …
 - Square → SQ_A1 … SQ_H8
 - Move → encoded 16-bit integer

These enums are not just labels — their numeric values are deliberately chosen so that:
 - Bitwise operations are meaningful
 - Conversions are cheap
 - Lookups can be done via array indexing
 - Arithmetic on enums is valid and efficient

### Inline Functions 

An inline function is a function that the compiler is allowed (not forced) to replace with the function’s body at the call site.

```c++
int f(int x) { return x + 1; }

int y = f(a);
```

The compiler may generate:

```c++
int y = a + 1;
```

Why inline functions matter in Stockfish
 - No function call overhead (no stack push/pop, no jumps)
 - Enables constant folding and dead code elimination
 - Allows bit-level operations to be optimized aggressively
 - Critical in hot loops (move generation, evaluation, search)

Most Stockfish inline functions:
 - Are tiny (1–3 operations)
 - Operate on enums or bitboards
 - Exist purely to give meaning to raw integers

### Attaching Behavior with Inline Functions

Instead of member functions on classes, Stockfish attaches behavior to enums using free inline functions.

```c++
inline File file_of(Square s) { return File(s & 7); }
inline Rank rank_of(Square s) { return Rank(s >> 3); }
inline PieceType type_of(Piece pc) { return PieceType(pc & 7); }
inline Color color_of(Piece pc) { return Color(pc >> 3); }
```

This approach replaces methods like:

```c++
square.file()
piece.color()
```

with faster, simpler operations.


### Operator Overloading on Enums

Stockfish overloads arithmetic and logical operators on enums to make them behave like small, type-safe integers.

```c++
ENABLE_FULL_OPERATORS_ON(Square)
ENABLE_FULL_OPERATORS_ON(PieceType)
ENABLE_FULL_OPERATORS_ON(Value)
```

This allows expressions such as:

```c++
Square s = SQ_E2 + NORTH;
Value v = VALUE_MATE - ply;
```

without runtime overhead or loss of clarity.

`ENABLE_FULL_OPERATORS_ON` is a macro that generates operator overloads for enum-like types.

The macro (simplified idea)

```c++
#define ENABLE_FULL_OPERATORS_ON(T) \
inline T operator+(T a, T b) { return T(int(a) + int(b)); } \
inline T operator-(T a, T b) { return T(int(a) - int(b)); } \
inline T& operator++(T& a)   { return a = T(int(a) + 1); } \
```


### Enums + Templates = Compile-Time Polymorphism

Instead of object-oriented polymorphism, Stockfish uses templates to specialize code at compile time.

```c++
template<PieceType Pt>
Bitboard attacks_from(Square s);
```

This lets the compiler generate separate, fully optimized code paths for knights, bishops, rooks, etc., without branches or virtual dispatch.

```c++
pos.attacks_from<KNIGHT>(s);
pos.attacks_from<BISHOP>(s)
```

This pattern appears everywhere in evaluation, move generation, and attack calculation.

## Generics and Metaprogramming in Stockfish

Stockfish makes heavy use of compile-time polymorphism rather than runtime polymorphism. Instead of relying on inheritance, virtual functions, or dynamic dispatch, it uses templates, constexpr logic, and specialization to generate highly optimized code paths at compile time. This approach is central to Stockfish’s performance.

### Templates as Zero-Cost Abstractions

In Stockfish, templates are used to express conceptual differences—such as piece type, color, or evaluation mode—without paying any runtime cost.

When a template function is instantiated with a specific PieceType, the compiler generates a separate function containing only the code relevant to that piece. Conditional logic depending on the template parameter is resolved at compile time, and all unused branches are completely removed.

When the compiler sees:

```c++
template<PieceType Pt>
inline Bitboard attacks_bb(Square s, Bitboard occupied) {
  return (Pt == ROOK ? RookAttacks : BishopAttacks)
         [s][magic_index<Pt>(s, occupied)];
}
```

it does not generate one generic function and branch at runtime.

Instead, it generates separate concrete functions, and each one contains only the relevant code.

For Pt = ROOK, i.e., when compiler sees a call like 

```c++
attacks_bb<  ROOK>(s, pos.pieces() ^ pos.pieces(Us, ROOK, QUEEN))
```

It generates a function `attacks_bb_rook`

```c++
inline Bitboard attacks_bb_rook(Square s, Bitboard occupied) {
    return RookAttacks[s][magic_index<ROOK>(s, occupied)];
}
```

 - The condition Pt == ROOK is true at compile time
 - The BishopAttacks branch is removed
 - No ternary operator remains
 - No runtime check exists

For Pt = BISHOP

```c++
attacks_bb<BISHOP>(s, pos.pieces() ^ pos.pieces(Us, QUEEN))
```

```c++
inline Bitboard attacks_bb_bishop(Square s, Bitboard occupied) {
    return BishopAttacks[s][magic_index<BISHOP>(s, occupied)];
}
```

Sometimes when type is not known at compile time, we can use the runtime version, which does explicit branching based on the template type, this introduces branching which is not free.

```c++
inline Bitboard attacks_bb(Piece pc, Square s, Bitboard occupied) {

  switch (type_of(pc))
  {
  case BISHOP: return attacks_bb<BISHOP>(s, occupied);
  case ROOK  : return attacks_bb<ROOK>(s, occupied);
  case QUEEN : return attacks_bb<BISHOP>(s, occupied) | attacks_bb<ROOK>(s, occupied);
  default    : return StepAttacksBB[pc][s];
  }
}
```



### Template Specialization for Termination and Control

Templates are also used to express recursive logic at compile time.

```c++
template<bool DoTrace, Color Us, PieceType Pt>
Score evaluate_pieces(...);
```

This function recursively evaluates piece types:
- KNIGHT → BISHOP → ROOK → QUEEN → KING

Termination is handled via explicit specialization:

```c++
template<>
Score evaluate_pieces<false, WHITE, KING>(...) { return SCORE_ZERO; }
```

This avoids:
  - Runtime loops
  - Dynamic type checks
  - Virtual dispatch

The recursion is unrolled at compile time.

### Boolean Template Parameters for Feature Stripping

Stockfish often uses boolean template parameters like:

```c++
template<bool DoTrace>
Value evaluate(const Position& pos);
```

This allows:
 - Tracing logic to be completely removed when DoTrace == false
 - Zero overhead in production builds
 - Debug-only code without if checks

### Two Ways Templates Create Multiple Versions of a Function

In C++, templates can produce multiple concrete versions of a function in two distinct ways. Stockfish relies on both mechanisms to precisely control performance and code generation.

#### A. Implicit Instantiation (Compiler-Generated)

Implicit instantiation occurs when a template function is used with a specific set of template parameters, but no explicit specialization is provided by the programmer.

```c++
template<PieceType Pt>
Bitboard attacks_bb(Square s, Bitboard occupied);
```

When the code calls:

```c++
attacks_bb<BISHOP>(s, occupied);
attacks_bb<ROOK>(s, occupied);
```

the compiler automatically:
 - Generates a separate concrete function for each template argument
 - Substitutes the template parameter (Pt) with a compile-time constant
 - Eliminates all code paths that depend on other values of Pt
 - Aggressively inlines the resulting function

Each instantiation is fully specialized and optimized as if it had been written by hand for that specific piece type.

This is the most common form of template usage in Stockfish and forms the backbone of its compile-time polymorphism.

#### B. Explicit Specialization (Programmer-Defined)

In some cases, Stockfish explicitly defines a custom implementation for a specific set of template parameters.

```c++
template<>
Score evaluate_pieces<false, WHITE, KING>(...) {
    return SCORE_ZERO;
}
```

This tells the compiler:
 - Do not generate a default implementation for this parameter combination
 - Use this explicitly defined version instead

Explicit specialization is used to:
 - Terminate compile-time recursion
 - Handle special cases cleanly
 - Avoid runtime conditionals
 - Keep performance-critical paths minimal

## Linkage, extern, and the One Definition Rule (ODR)

Stockfish is split across many translation units (.cpp files), but large parts of its logic depend on shared global data such as piece values, attack tables, and evaluation constants. To make this work efficiently and correctly, Stockfish relies on C++ linkage rules, especially extern.

### What Linkage Means in C++

Linkage determines whether a symbol (variable or function) refers to the same entity across different source files.
 - External linkage → the symbol is shared across translation units
 - Internal linkage → the symbol exists only within one translation unit

By default:
 - Functions have external linkage
 - Global variables have external linkage unless marked static

### Why extern Is Used in Stockfish

Consider this declaration in a header file:

```cpp
extern Value PieceValue[PHASE_NB][PIECE_NB];
```

This tells the compiler:
 - “This variable exists somewhere”
 - “Do not allocate storage here”
 - “The definition will be provided in exactly one .cpp file”

The actual definition appears in `psqt.cpp`:

```c++
Value PieceValue[PHASE_NB][PIECE_NB] = {
  { VALUE_ZERO, PawnValueMg, KnightValueMg, BishopValueMg, RookValueMg, QueenValueMg },
  { VALUE_ZERO, PawnValueEg, KnightValueEg, BishopValueEg, RookValueEg, QueenValueEg }
};
```

This separation allows:
 - The variable to be shared across the entire engine
 - Only one copy to exist in memory
 - Fast direct access without function calls
 - This is a global variable, one copy maintained across the entire program

### Internal Linkage

Consider this definition in `types.h`

```c++
const Piece Pieces[] = { W_PAWN, W_KNIGHT, W_BISHOP, W_ROOK, W_QUEEN, W_KING,
                         B_PAWN, B_KNIGHT, B_BISHOP, B_ROOK, B_QUEEN, B_KING };
```

**Technically**: This declares a global array.

**Practically**: The `const` keyword gives it **internal linkage** in C++, meaning:
- Each translation unit (.cpp file) that includes `types.h` gets its **own copy**
- No linker errors about "multiple definitions"
- Still problematic if you want a single shared instance

If we remove `const`, then it will be considered as external linkage. The linker would see: multiple definition of `Pieces` and throws error.

