---
title:  "Computational Graphs, Part 1: What a Graph Represents"
date:   2026-09-09
categories: ["ml"]
tags: ["ml", "computational-graphs", "backpropagation"]

---

# Computational Graphs, Part 1: What a Graph Represents

This is the first of several short notes on backpropagation. The goal here is not to derive gradients yet. It is only to get comfortable with the picture we will use to derive them.

A **computational graph** is a way of drawing a function so that every operation is a separate step. The picture makes the chain rule almost automatic once we are ready to use it.

---

## 1. What you will learn

- How to turn a formula into a graph of operations.
- What the nodes and edges represent.
- How to evaluate the graph from left to right: the **forward pass**.
- Why we give names to intermediate results.

---

## 2. A function as a sequence of operations

Take the expression:

$$
f(x, y, z) = (x + y) \cdot z
$$

There are two operations inside it: an addition and a multiplication. To draw the graph, introduce an intermediate variable for the result of the addition:

$$
q = x + y
$$

Then the output is:

$$
f = q \cdot z
$$

The graph looks like this:

```text
x ──► (+) ──┐
            ├──► q ──► (*) ──► f
y ──► (+) ──┘            ▲
                         │
z ───────────────────────┘
```

Each box is an operation. Each arrow is a value. The value $q$ is an edge between the addition node and the multiplication node.

The point of the graph is that **each node is simple**. A node does one thing. The complexity of the whole function comes from how the nodes are connected.

---

## 3. Nodes and edges

- **Nodes** are operations: addition, multiplication, exponentiation, a sigmoid, and so on.
- **Edges** are numbers: the inputs and outputs of each operation.
- **Leaves** on the left are the inputs we control: $x$, $y$, $z$.
- **Root** on the right is the final output: $f$.

Every edge has a concrete value once the inputs are chosen. If the inputs change, we recompute the edges from left to right.

---

## 4. The forward pass

The forward pass is just evaluating the graph in order. Choose concrete numbers:

$$
x = -2, \quad y = 5, \quad z = -3
$$

Step through the graph:

1. **Addition node:**

$$
q = x + y = -2 + 5 = 3
$$

2. **Multiplication node:**

$$
f = q \cdot z = 3 \cdot (-3) = -9
$$

So when $(x, y, z) = (-2, 5, -3)$, the graph computes $f = -9$.

We can annotate the graph with the values on the edges:

```text
-2 ──► (+) ──┐
             ├──► 3 ──► (*) ──► -9
 5 ──► (+) ──┘            ▲
                          │
-3 ───────────────────────┘
```

Nothing more is happening here than arithmetic. The graph just organizes the arithmetic so we can see it.

---

## 5. Why introduce intermediate variables?

We could have written the whole thing as one line:

$$
f = (x + y) \cdot z
$$

The intermediate name $q$ is useful because it lets us talk about the output of the addition independently from the multiplication. When we later ask questions like "how sensitive is $f$ to the addition?", having a name for the addition's output makes the question concrete.

Every edge in the graph is a quantity we might want to inspect or take a derivative with respect to.

---

## 6. A second example

Consider:

$$
g(a, b) = a^2 + b
$$

Introduce an intermediate variable:

$$
h = a^2
$$

Then:

$$
g = h + b
$$

Graph:

```text
a ──► (a²) ──► h ──► (+) ──► g
                          ▲
                          │
b ────────────────────────┘
```

If $a = 3$ and $b = 4$, the forward pass gives:

$$
h = 3^2 = 9
$$

$$
g = 9 + 4 = 13
$$

Again, the graph does not change the math. It only makes the pieces visible.

---

## 7. What comes next

Once the graph is drawn, we can ask how the output changes when an input changes. The answer is a derivative, and derivatives on a graph move from right to left. But before we move there, the next note will look at the chain rule itself — the tool that lets us combine derivatives along a path.

