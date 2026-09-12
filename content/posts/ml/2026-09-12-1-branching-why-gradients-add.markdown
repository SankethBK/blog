---
title:  "Computational Graphs, Part 2: Branching — Why Gradients Add"
date:   2026-09-12
categories: ["ml"]
tags: ["ml", "computational-graphs", "chain-rule", "backpropagation"]

---

# Computational Graphs, Part 2: Branching — Why Gradients Add

The [previous note](/posts/ml/2026-09-09-1-computational-graphs-and-backpropagation) covered the forward pass, the chain rule, and the backward pass on a graph where every input had exactly one path to the output. This note adds the one remaining piece: what happens when an input feeds into **more than one** operation.

When that happens, there are multiple paths from the input to the output. The chain rule tells us to **add** the contributions from those paths.

---

## 1. What you will learn

- How to draw a graph where one input branches into two operations.
- Why the total derivative is the sum of the path derivatives.
- How to verify the result by direct expansion and by perturbation.
- The difference between a single-path chain rule and a multi-path chain rule.

---

## 2. A branching example

Consider:

$$
f(x, y) = x \cdot y + x^2
$$

Here $x$ appears twice: once in the product $x \cdot y$ and once in $x^2$.

Introduce two intermediate variables:

$$
p = x \cdot y
\qquad
q = x^2
$$

Then:

$$
f = p + q
$$

The graph is:

```text
x ──► (*) ──► p ──►
       ▲            │
       │            (+) ──► f
       │            ▲
y ─────┘            │
                    q
                    ▲
                    │
x ──► (x²) ─────────┘
```

There are two paths from $x$ to $f$:

1. $x \to p \to f$
2. $x \to q \to f$

Because $x$ affects $f$ through both paths, the total sensitivity of $f$ to $x$ is the sum of the sensitivities along each path.

---

## 3. The question

We want to compute:

$$
\frac{\partial f}{\partial x}
$$

This asks: if $x$ changes by a tiny amount while $y$ stays fixed, how much does $f$ change?

Because $x$ feeds two operations, the change in $f$ has two sources. We compute each source separately and add them.

---

## 4. Forward pass with concrete numbers

Choose $x = 2$ and $y = 3$.

**Product node:**

$$
p = x \cdot y = 2 \cdot 3 = 6
$$

**Square node:**

$$
q = x^2 = 2^2 = 4
$$

**Addition node:**

$$
f = p + q = 6 + 4 = 10
$$

So when $(x, y) = (2, 3)$, the output is $f = 10$.

---

## 5. Path 1: through the product

The first path is $x \to p \to f$.

Local sensitivities on this path:

Because $f = p + q$:

$$
\frac{\partial f}{\partial p} = 1
$$

Because $p = x \cdot y$:

$$
\frac{\partial p}{\partial x} = y = 3
$$

Apply the chain rule along this single path:

$$
\left. \frac{\partial f}{\partial x} \right|_{\text{path 1}}
= \frac{\partial f}{\partial p} \cdot \frac{\partial p}{\partial x}
= 1 \cdot 3
= 3
$$

This is the contribution to $\frac{\partial f}{\partial x}$ from the product branch.

What does this number mean? If only the product branch existed, increasing $x$ by a tiny amount $\epsilon$ would increase $f$ by about $3\epsilon$.

---

## 6. Path 2: through the square

The second path is $x \to q \to f$.

Local sensitivities on this path:

Because $f = p + q$:

$$
\frac{\partial f}{\partial q} = 1
$$

Because $q = x^2$:

$$
\frac{\partial q}{\partial x} = 2x = 4
$$

Apply the chain rule along this single path:

$$
\left. \frac{\partial f}{\partial x} \right|_{\text{path 2}}
= \frac{\partial f}{\partial q} \cdot \frac{\partial q}{\partial x}
= 1 \cdot 4
= 4
$$

This is the contribution to $\frac{\partial f}{\partial x}$ from the square branch.

What does this number mean? If only the square branch existed, increasing $x$ by a tiny amount $\epsilon$ would increase $f$ by about $4\epsilon$.

---

## 7. Adding the two paths

The total derivative is the sum of the two path contributions:

$$
\frac{\partial f}{\partial x}
= \left. \frac{\partial f}{\partial x} \right|_{\text{path 1}} +
  \left. \frac{\partial f}{\partial x} \right|_{\text{path 2}}
= 3 + 4
= 7
$$

So $\frac{\partial f}{\partial x} = 7$ when $x = 2$ and $y = 3$.

The meaning is: if $x$ increases by a tiny amount $\epsilon$, the total change in $f$ is about $7\epsilon$. Three of those units come from the product branch; four come from the square branch.

---

## 8. Check by direct expansion

We can expand $f$ directly:

$$
f(x, y) = x \cdot y + x^2
$$

Take the partial derivative with respect to $x$:

$$
\frac{\partial f}{\partial x} = y + 2x
$$

At $x = 2$ and $y = 3$:

$$
\frac{\partial f}{\partial x} = 3 + 2(2) = 3 + 4 = 7
$$

This matches the graph result.

The direct expansion also makes the two paths visible: $y$ is the derivative of the product branch, and $2x$ is the derivative of the square branch.

---

## 9. Check by perturbation

Start from $f(2, 3) = 10$. Increase $x$ by a small amount $\epsilon$:

$$
f(2 + \epsilon, 3) = (2 + \epsilon) \cdot 3 + (2 + \epsilon)^2
$$

Compute each piece.

Product piece:

$$
(2 + \epsilon) \cdot 3 = 6 + 3\epsilon
$$

Square piece:

$$
(2 + \epsilon)^2 = 4 + 4\epsilon + \epsilon^2
$$

Add them:

$$
f(2 + \epsilon, 3) = 6 + 3\epsilon + 4 + 4\epsilon + \epsilon^2
$$

Group terms:

$$
f(2 + \epsilon, 3) = 10 + 7\epsilon + \epsilon^2
$$

The change in $f$ is $7\epsilon + \epsilon^2$. For tiny $\epsilon$, the $\epsilon^2$ term is negligible, so the rate of change is $7$.

This matches the derivative we computed from the graph.

---

## 10. Why gradients add

The reason we add the path contributions is not special to graphs. It is the **multivariable chain rule**.

If $f$ depends on $p$ and $q$, and both $p$ and $q$ depend on $x$, then:

$$
\frac{\partial f}{\partial x}
= \frac{\partial f}{\partial p} \cdot \frac{\partial p}{\partial x} +
  \frac{\partial f}{\partial q} \cdot \frac{\partial q}{\partial x}
$$

Each product is the sensitivity along one path. The sum is the total sensitivity.

A useful mental image: the forward pass sends the value of $x$ forward along every outgoing edge. The backward pass sends gradients backward along every incoming edge. When multiple gradients arrive at the same node, they add, because the total effect is the sum of the individual effects.

---

## 11. What about $y$?

For completeness, $y$ only has one path to $f$: $y \to p \to f$.

Because $f = p + q$:

$$
\frac{\partial f}{\partial p} = 1
$$

Because $p = x \cdot y$:

$$
\frac{\partial p}{\partial y} = x = 2
$$

So:

$$
\frac{\partial f}{\partial y}
= \frac{\partial f}{\partial p} \cdot \frac{\partial p}{\partial y}
= 1 \cdot 2
= 2
$$

There is nothing to add because $y$ has only one path.

---

## 12. Single-path vs multi-path chain rule

It is worth distinguishing the two cases.

- **Single path:** one intermediate $u$ sits between $x$ and $f$. Then:

$$
\frac{df}{dx} = \frac{df}{du} \cdot \frac{du}{dx}
$$

- **Multiple paths:** $x$ feeds several intermediates $u_1, u_2, \dots$. Then:

$$
\frac{\partial f}{\partial x}
= \sum_i \frac{\partial f}{\partial u_i} \cdot \frac{\partial u_i}{\partial x}
$$

The single-path rule is just the multi-path rule with only one term in the sum.

---

## 13. What comes next

We now have the full machinery: forward pass, chain rule, backward pass, and branching. The next note applies this machinery to a single neuron and shows that logistic regression is exactly a one-neuron graph.

---

## 14. Exercises

1. For $f(x, y) = x \cdot y + x^2$ with $x = 1$ and $y = 4$, compute $\frac{\partial f}{\partial x}$ by identifying the two paths and adding their contributions.
2. For $g(a, b) = a^2 \cdot b + a$, draw the computational graph, identify the paths from $a$ to $g$, and compute $\frac{\partial g}{\partial a}$.
3. Explain in your own words why the two path contributions in $f(x, y) = x \cdot y + x^2$ are added rather than multiplied.
