---
title:  "History of Chess Engines"
date:   2026-01-02
draft: false
categories: ["chess engines"]
tags: ["claude shannon's research"]
author: Sanketh
---

# History of Chess Engines

[Programming a Computer for Playing Chess (1950) by Claude Shannon](https://vision.unipv.it/IA1/ProgrammingaComputerforPlayingChess.pdf) is the foundational paper of computer chess and one of the earliest works in artificial intelligence. Written at a time when programmable computers were still experimental, the paper does not attempt to build a chess program, but instead asks a deeper question: what would it even mean for a machine to play chess intelligently under severe computational limits? Shannon shows that perfect play is theoretically possible but practically impossible, and develops a principled framework based on approximate evaluation, game-tree search, selectivity, and bounded rationality. Nearly every major idea used in modern chess engines—minimax, heuristic evaluation, quiescence, selective search, opening books, randomness, and even learning—appears here in conceptual form. The paper remains important not as a historical curiosity, but because it correctly identifies the permanent constraints and core ideas that still govern strong chess-playing programs today.

## Why Chess is a Hard Problem?

Chess is a finite, deterministic, perfect-information game. There is no randomness during play (apart from the initial choice of colour), and both players have complete knowledge of the position and all previous moves. As shown in classical game theory, this implies that every chess position must belong to exactly one of three categories:

1. A forced win for White,
2. A forced draw, or
3. A forced win for Black.

When considering whether a game can be solved by a computer, two-player board games can be broadly divided into two types.

Type 1 games are those in which we can determine whether a position is winning or losing simply by inspecting the current position, without any lookahead into future moves. These games are easily solvable by computers because the required computation is extremely cheap. A classic example is Nim, where players take turns removing objects from piles and the player who removes the last object wins. In Nim, the outcome of a position can be decided by computing the XOR (nim-sum) of the pile sizes. If the nim-sum is zero, the position is a losing one (a P-position) for the player to move; otherwise, it is winning. No simulation of future play is required—the solution is entirely local.

Type 2 games also have clearly defined rules, but determining whether a position is better for one side or the other requires looking ahead into future possibilities and analysing how those possibilities terminate. Some games, such as tic-tac-toe, fall into this category but are still computationally cheap: although lookahead is required, the game tree is small enough to be explored exhaustively, making perfect play trivial for a computer.

Chess, however, belongs to a much harder subclass of Type 2 games. In chess, there is no reliable static evaluation that can determine which side is better merely by inspection—simple heuristics such as “the side with more pieces is better” often fail. Determining the true value of a position requires analysing future play, but the number of possible continuations grows so rapidly that exhaustive search becomes infeasible. Moreover, the outcomes of chess positions are not merely right or wrong; they span a continuous range of quality, from clearly winning to slightly advantageous to barely defensible.

It is precisely this combination—deep lookahead requirements, explosive growth of possibilities, and graded rather than binary outcomes—that makes chess difficult for computers, and also makes it an ideal test case for studying approximation, judgement, and decision-making under limited computational resources. Insights gained from attempting to solve such problems were expected, even at the time, to extend naturally into other complex domains.

Although chess is widely believed to be a “fair” game in the sense that the first player does not have a guaranteed forced win, this has never been formally proven for the standard rules of chess. What can be shown is that chess is a finite, perfect-information game with no chance elements, which implies that the initial position must be either a win for White, a draw, or a win for Black. Empirical evidence from centuries of high-level play strongly suggests that correct play by both sides leads to a draw, but no practical method exists to determine this conclusively. Interestingly, Shannon points out that if the rules are modified slightly to allow a player to “pass,” then one can rigorously prove that White can always force at least a draw by a symmetry argument. This highlights that chess appears fair not because its outcome is known, but because determining the true value of the initial position is computationally infeasible.

## Approximate Evaluation Function For Chess

Since an exact evaluation function for chess positions is computationally unattainable, any practical chess-playing program must rely on an approximate evaluation function. Rather than classifying positions strictly as won, drawn, or lost, such a function assigns a numerical score that reflects how favourable a position appears for one side, given limited computational resources.

Human chess players operate in exactly this manner. Strong players do not calculate every possible continuation to the end of the game; instead, they form judgements based on features such as material balance, piece activity, king safety, pawn structure, and overall mobility. These judgements are inherently heuristic and statistical in nature. They are not infallible, but stronger players tend to make better approximations more consistently.

Shannon emphasizes that most classical “principles of chess” are not absolute rules, but empirical generalizations derived from experience. Statements such as “a queen is worth more than a rook,” “rooks belong on open files,” or “doubled pawns are weak” admit numerous counterexamples. Their usefulness lies not in their universal correctness, but in their average predictive value across many positions. This makes them well suited for incorporation into an approximate evaluation function.

A key property of such an evaluation is that its output lies on a continuous scale, rather than in discrete categories. A position may be winning in a trivial sense (e.g., a queen ahead), only slightly better, or technically winning but extremely difficult to convert. This contrasts sharply with the assumptions of classical game theory, where a position is either winning, drawn, or lost, and even the smallest winning advantage is treated as equivalent to immediate checkmate.

### Claude Shannon's Approximation Function

To make the idea of approximate evaluation concrete, Claude Shannon proposed a simple but sensible numerical evaluation function for chess positions. He did not claim this function to be accurate or complete; rather, it was intended as an illustration of how general chess principles could be translated into a form suitable for computation.

Shannon’s evaluation function assigns a numerical score to a position by combining several familiar features of chess. At its core is material balance, with pieces weighted according to their approximate relative values (for example, queen ≈ 9, rook ≈ 5, bishop and knight ≈ 3, pawn ≈ 1). This reflects the long-established observation that, all else being equal, the side with more material tends to have the advantage.

Beyond material, Shannon includes additional positional terms. Penalties are applied for structural weaknesses such as doubled, isolated, or backward pawns, while positive weight is given to mobility, measured as the number of legal moves available to a side. The idea is that greater freedom of movement generally corresponds to a healthier position. Checkmate is handled artificially by assigning the king an overwhelmingly large value, ensuring that mating positions dominate all other considerations.

```
f(P) = 200(K-K') + 9(Q-Q') + 5(R-R') + 3(B-B'+N-N') + (P-P') - 0.5(D-D'+S-S'+I-I') +
0.1(M-M') + ...
```

What is important is not the quality of this particular evaluation, but the conceptual shift it represents. Instead of asking whether a position is objectively won or lost, the machine assigns a graded score expressing relative advantage. Positions that are “easy wins,” “difficult wins,” or “slightly better” are distinguished numerically, reflecting how chess is actually played under practical constraints.

## From Evaluation to Strategy: Minimax and Game-Tree Search

An approximate evaluation function by itself does not define how a machine should play chess. To make decisions, the machine must determine which move to choose, taking into account that the opponent will respond optimally. This leads naturally to the idea of game-tree search, in which chess is represented as a tree of positions connected by legal moves.

Starting from a given position, each legal move generates a new position. From each of those positions, the opponent has their own set of legal replies, and so on. This branching structure forms a game tree, whose leaves correspond to positions reached after some finite number of moves. Because it is impossible to explore the entire tree, the machine searches only to a limited depth and applies the evaluation function to the resulting positions.

The fundamental assumption underlying this process is that both players act rationally: each side attempts to maximize its own advantage while minimizing the opponent’s. Under this assumption, move selection can be formalized using the minimax principle. At positions where it is the machine’s turn to move, it chooses the move that leads to the position with the highest evaluation. At positions where it is the opponent’s turn, it assumes the opponent will choose the move that minimizes this evaluation.

Formally, this leads to an alternating process of maximization and minimization as one moves down the game tree. For a search of one move ahead, the machine evaluates all positions resulting from its possible moves and chooses the one with the highest score. For a deeper search, it considers the opponent’s best reply to each candidate move, then its own best response to that reply, and so on, propagating evaluation values backward through the tree.

However, this strategy comes at a cost. Even with a modest branching factor, the number of positions grows exponentially with search depth. Searching uniformly to a fixed depth quickly becomes impractical, and shallow searches often miss tactically critical sequences. These limitations motivate the need for further refinements, such as selective search and more careful control over when evaluation is applied.

### Type A Strategy: Exhaustive Fixed-Depth Search

The most direct way to combine evaluation with game-tree search is what Shannon calls a Type A strategy. In this approach, the machine explores all legal moves uniformly to a fixed depth and applies the evaluation function only at the leaf positions. No distinction is made between forcing and non-forcing moves, and no variation is explored deeper than any other.

Concretely, starting from the current position, the machine generates every legal move for itself, then every legal reply for the opponent, and continues this process until a predetermined depth is reached. At that point, the approximate evaluation function is applied to each resulting position. These values are then propagated backward through the game tree using the minimax principle: positions where the machine is to move select the maximum value among their children, while positions where the opponent is to move select the minimum.

The appeal of the Type A strategy lies in its conceptual simplicity and correctness in principle. Given sufficient depth, it will never overlook a continuation simply because it appears unpromising. All variations are treated equally, and no chess-specific judgement is required beyond move generation and evaluation. In this sense, Type A represents the purest form of brute-force reasoning applied to chess.

However, this uniformity is also its fundamental weakness. The branching factor in chess is large—typically on the order of thirty legal moves per position—and remains high throughout much of the game. As a result, the number of positions explored grows exponentially with depth. Even a search only a few moves deep requires evaluating an enormous number of positions, making the approach computationally impractical.

### Quiescent Positions and Improving Type A Search

One of the central weaknesses of the Type A strategy is that it applies the evaluation function at a fixed depth, regardless of whether the position at that depth is tactically stable. In real chess play, however, many positions encountered during search are highly volatile: pieces may be hanging, exchanges may be incomplete, or checks may force immediate replies. Evaluating such positions can produce values that have little relation to the true outcome of the position.

To address this problem, Shannon introduces the notion of a quiescent position. A position is said to be quiescent if there are no immediate tactical events pending—no forced captures, no checks, and no obvious imbalances such as pieces attacked by lower-valued pieces or by more attackers than defenders. Only in such positions does it make sense to apply an approximate evaluation function, since the position has reached a temporary equilibrium.

This idea can be incorporated into a Type A strategy by relaxing the rigid stopping condition of fixed-depth search. Instead of always terminating the search after a predetermined number of moves, the machine continues to explore the game tree whenever the current position is tactically unstable. Forced moves—such as captures and checks—are followed until the position settles into a quiescent state, subject to reasonable limits to prevent infinite extension.

In effect, this enhancement allows the search depth to vary dynamically. Quiet positions may be evaluated after only a small number of moves, while sharp tactical lines are explored more deeply. This significantly reduces errors caused by evaluating positions in the middle of combinations and helps mitigate the horizon effect, where the consequences of a tactical sequence lie just beyond the search boundary.

Importantly, this refinement does not abandon the exhaustive nature of Type A search; it merely postpones evaluation to more appropriate positions. The underlying minimax structure remains unchanged, but the quality of the information propagated back up the tree is greatly improved. As a result, even shallow searches become more reliable, since evaluations are applied only when the position has stabilized.

### Type B Strategy: Selective and Force-Aware Search

While the introduction of quiescent positions improves the reliability of a Type A strategy, it does not address its most serious inefficiency: the uniform exploration of all variations. In real chess play, not all moves are equally important. Some moves force immediate responses and drastically constrain the opponent’s choices, while others are quiet and allow many possible replies. Treating these moves identically wastes computational effort and limits the effective depth of search.

To overcome this, Shannon proposes what he calls a Type B strategy, in which the machine selectively explores variations based on their tactical significance. Instead of expanding every legal move at every node, the machine prioritizes forceful moves—such as checks, captures, and direct threats—that are more likely to influence the outcome of the position.

The key idea is to guide the search using a heuristic function h(P, M), which estimates how worthy a particular move M is of further investigation in position P. Moves that give check, attack major pieces, threaten mate, or initiate exchanges are assigned higher priority, while quiet or passive moves receive lower priority. Crucially, this screening must be conservative: moves that initially appear bad, such as sacrifices, must not be discarded simply because they lose material in the short term.

A defining feature of Type B search is that selectivity increases with depth. Near the root of the search tree, many candidate moves may be examined. As the search progresses deeper, only increasingly forceful moves are considered, causing the tree to narrow naturally. This mirrors human calculation, where players quickly discard irrelevant ideas and focus their attention on a small number of critical lines.

Type B strategy thus replaces blind trial-and-error with directed exploration. By spending computational resources on variations where tactical resolution is required and avoiding vast numbers of uninteresting continuations, the machine achieves much greater effective depth without increasing raw computing power. Importantly, this selectivity is layered on top of minimax search rather than replacing it; the assumption of optimal play by both sides remains intact.

Shannon argues that this combination—approximate evaluation, quiescence awareness, and selective expansion of forcing lines—captures the essential structure of skilful chess play. It balances the strengths of the computer, namely speed and accuracy, with its weaknesses in pattern recognition and judgement, and marks the transition from brute-force calculation to genuinely intelligent search.