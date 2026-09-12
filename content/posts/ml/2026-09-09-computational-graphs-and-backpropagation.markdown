---
title:  "Computational Graphs and Backpropagation"
date:   2026-09-09
categories: ["ml"]
tags: ["ml", "computational-graphs", "chain-rule", "backpropagation"]

---

# Computational Graphs and Backpropagation

This note explains how to compute gradients for any function by breaking it into a graph of simple operations. It is the bridge between the gradient-descent picture from the [linear and logistic regression note](/posts/ml/2026-09-07-ml-refresher-linear-logistic-regression) and the layered functions we will later call neural networks.

The ideas are:

1. Draw the function as a graph of operations.
2. Evaluate the graph from inputs to output: the **forward pass**.
3. Use the chain rule to carry sensitivities from the output back to the inputs: the **backward pass**.

We build this on one tiny example and walk through every step.

---

## 1. What you will learn

- How to turn a formula into a graph of operations.
- How to evaluate the graph with a forward pass.
- What a partial derivative asks on a graph.
- The chain rule as multiplying local sensitivities.
- The backward-pass recipe for computing every partial derivative.
- Why forward values are needed to compute backward gradients.

---

## 2. A function as a graph

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

The graph is:

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

## 3. Nodes, edges, leaves, and root

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

Step through the graph.

**Addition node:**

$$
q = x + y = -2 + 5 = 3
$$

**Multiplication node:**

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

Nothing more is happening here than arithmetic. The graph only organizes the arithmetic so we can see it.

---

## 5. Why intermediate variables matter

We could have written the whole thing as one line:

$$
f = (x + y) \cdot z
$$

The intermediate name $q$ is useful because it lets us talk about the output of the addition independently from the multiplication. When we later ask questions like "how sensitive is $f$ to the addition?", having a name for the addition's output makes the question concrete.

Every edge in the graph is a quantity we might want to inspect or take a derivative with respect to.

---

## 6. The question we want to answer

The question we ask now is:

> If I make a tiny change to $x$, while leaving $y$ and $z$ alone, how much does $f$ change?

That rate of change is written as the partial derivative:

$$
\frac{\partial f}{\partial x}
$$

The symbol $\partial$ just means "this is a partial derivative": we are changing $x$ but holding $y$ and $z$ fixed.

In general, we want all three partial derivatives:

$$
\frac{\partial f}{\partial x}, \quad \frac{\partial f}{\partial y}, \quad \frac{\partial f}{\partial z}
$$

---

## 7. The chain rule on a single path

Before using the graph, recall the chain rule for a simple composition. Suppose:

$$
f(x) = (x + 1)^2
$$

Break it into two operations:

$$
u = x + 1
$$

$$
f = u^2
$$

The derivative we want is $\frac{df}{dx}$. The chain rule says:

$$
\frac{df}{dx} = \frac{df}{du} \cdot \frac{du}{dx}
$$

Compute each piece separately.

Because $f = u^2$:

$$
\frac{df}{du} = 2u
$$

Because $u = x + 1$:

$$
\frac{du}{dx} = 1
$$

Multiply them:

$$
\frac{df}{dx} = 2u \cdot 1 = 2u = 2(x + 1)
$$

We can check this without the chain rule by expanding the original expression:

$$
f(x) = (x + 1)^2 = x^2 + 2x + 1
$$

Taking the derivative directly:

$$
\frac{df}{dx} = 2x + 2 = 2(x + 1)
$$

The answers match. The chain rule gave us the same result without expanding anything.

---

## 8. What each derivative means

In the expression:

$$
\frac{df}{dx} = \frac{df}{du} \cdot \frac{du}{dx}
$$

- $\frac{df}{du}$ asks: if $u$ changes, how fast does $f$ change?
- $\frac{du}{dx}$ asks: if $x$ changes, how fast does $u$ change?
- Multiplying them asks: if $x$ changes, how fast does $f$ change?

Each factor is a local sensitivity. The chain rule combines local sensitivities along a path to get a global sensitivity.

---

## 9. Applying the chain rule to the graph

Return to $f(x, y, z) = (x + y) \cdot z$. To find $\frac{\partial f}{\partial x}$, follow the path from $x$ to $f$:

```text
x ──► q ──► f
```

There are two local sensitivities:

1. How sensitive is $f$ to $q$?

Because $f = q \cdot z$:

$$
\frac{\partial f}{\partial q} = z
$$

2. How sensitive is $q$ to $x$?

Because $q = x + y$:

$$
\frac{\partial q}{\partial x} = 1
$$

Apply the chain rule:

$$
\frac{\partial f}{\partial x}
= \frac{\partial f}{\partial q} \cdot \frac{\partial q}{\partial x}
= z \cdot 1
= z
$$

Using the numbers from the forward pass, $z = -3$:

$$
\frac{\partial f}{\partial x} = -3
$$

---

## 10. Checking the answer directly

The chain rule said $\frac{\partial f}{\partial x} = -3$. Let us verify that by hand.

If we increase $x$ by a tiny amount $\epsilon$:

$$
f(-2 + \epsilon, 5, -3) = ((-2 + \epsilon) + 5) \cdot (-3)
$$

Simplify inside the parentheses:

$$
= (3 + \epsilon) \cdot (-3)
$$

Distribute:

$$
= -9 - 3\epsilon
$$

The original output was $f(-2, 5, -3) = -9$. The new output is $-9 - 3\epsilon$. The change is $-3\epsilon$, so the rate of change is $-3$.

This matches the chain rule result.

---

## 11. The other two partial derivatives

**For $y$:**

The path is $y \to q \to f$.

$$
\frac{\partial f}{\partial y}
= \frac{\partial f}{\partial q} \cdot \frac{\partial q}{\partial y}
= z \cdot 1
= z
$$

With $z = -3$:

$$
\frac{\partial f}{\partial y} = -3
$$

**For $z$:**

Here $z$ goes straight into the multiplication node, not through $q$.

Because $f = q \cdot z$:

$$
\frac{\partial f}{\partial z} = q
$$

With $q = 3$:

$$
\frac{\partial f}{\partial z} = 3
$$

Notice that $\frac{\partial f}{\partial x}$ and $\frac{\partial f}{\partial y}$ both equal $z$. That is not a coincidence. Because $x$ and $y$ enter the graph in the same way — through the addition node — their influence on the output is identical.

---

## 12. The backward-pass recipe

We can compute all three partial derivatives by walking the graph from right to left. This systematic walk is the **backward pass**.

Start at the output node. The derivative of the output with respect to itself is always 1:

$$
\frac{\partial f}{\partial f} = 1
$$

This is a bookkeeping convention. It says: "if $f$ changes by one unit, $f$ changes by one unit." We start here because every other derivative is a sensitivity *relative to the output*.

### 12.1 Step backward through the multiplication node

The last node computes $f = q \cdot z$. Its local sensitivities are:

$$
\frac{\partial f}{\partial q} = z
\qquad
\frac{\partial f}{\partial z} = q
$$

With the forward-pass values $q = 3$ and $z = -3$:

$$
\frac{\partial f}{\partial q} = -3
\qquad
\frac{\partial f}{\partial z} = 3
$$

What do these mean?

- $\frac{\partial f}{\partial q} = -3$ means: if $q$ increases a tiny amount while $z$ stays fixed, $f$ decreases by about three times that amount.
- $\frac{\partial f}{\partial z} = 3$ means: if $z$ increases a tiny amount while $q$ stays fixed, $f$ increases by about three times that amount.

Because $z$ is an input, we are already done with it:

$$
\frac{\partial f}{\partial z} = 3
$$

Because $q$ is an intermediate edge, we must keep moving left.

### 12.2 Step backward through the addition node

The previous node computes $q = x + y$. Its local sensitivities are:

$$
\frac{\partial q}{\partial x} = 1
\qquad
\frac{\partial q}{\partial y} = 1
$$

The sensitivity that arrives at $q$ from the right is $\frac{\partial f}{\partial q} = -3$. Multiply by the local sensitivity to get the sensitivity at $x$:

$$
\frac{\partial f}{\partial x}
= \frac{\partial f}{\partial q} \cdot \frac{\partial q}{\partial x}
= (-3) \cdot 1
= -3
$$

Similarly for $y$:

$$
\frac{\partial f}{\partial y}
= \frac{\partial f}{\partial q} \cdot \frac{\partial q}{\partial y}
= (-3) \cdot 1
= -3
$$

So all three partial derivatives are:

$$
\frac{\partial f}{\partial x} = -3
\qquad
\frac{\partial f}{\partial y} = -3
\qquad
\frac{\partial f}{\partial z} = 3
$$

---

## 13. Annotating the graph with both passes

We can draw the same graph twice: once with forward values, once with backward sensitivities.

Forward values:

```text
-2 ──► (+) ──┐
             ├──► 3 ──► (*) ──► -9
 5 ──► (+) ──┘            ▲
                          │
-3 ───────────────────────┘
```

Backward sensitivities flow from right to left:

```text
          ∂f/∂f = 1
              │
              ▼
∂f/∂q = -3  (*)  ∂f/∂z = 3
              │
              ▼
             (+)
            /   \
           ▼     ▼
∂f/∂x = -3     ∂f/∂y = -3
```

The leftward arrows show how gradients flow. Each node receives a gradient from the right, multiplies it by its own local derivative, and passes the result to the left.

---

## 14. Forward values vs backward sensitivities

It is easy to mix these up, so it is worth stating the difference explicitly.

- **Forward values** are the numbers the graph computes. They answer: "what is the output?"
- **Backward sensitivities** are derivatives. They answer: "if this edge changes slightly, how much does the final output change?"

The forward pass stores values on edges. The backward pass stores gradients on edges. Both passes use the same graph structure, but they move in opposite directions and carry different kinds of numbers.

A useful mental image: the forward pass sends data forward, the backward pass sends sensitivities backward.

---

## 15. Why the backward pass reuses forward values

Look at the multiplication node again. To compute:

$$
\frac{\partial f}{\partial q} = z
$$

we needed the value of $z$. To compute:

$$
\frac{\partial f}{\partial z} = q
$$

we needed the value of $q$. Both $q$ and $z$ were already computed during the forward pass.

This is a general pattern. During the backward pass, every node needs the values of its inputs to compute its local derivatives. Those values come from the forward pass. That is why backpropagation always runs forward first, then backward.

---

## 16. Why this is better than expanding

We could have expanded the original expression:

$$
f(x, y, z) = xz + yz
$$

Then:

$$
\frac{\partial f}{\partial x} = z
$$

This gives the same answer. But for a function with ten operations, expanding becomes painful. The graph lets us keep the function in its original form and compute derivatives one node at a time.

Each node only needs to know its own local rule. The chain rule handles the rest.

---

## 17. Exercises

1. For $f(x, y, z) = (x + y) \cdot z$ with $x = 1$, $y = 2$, $z = 4$, run the forward pass and then compute all three partial derivatives using the backward-pass recipe.
2. Draw the computational graph for $g(a, b) = (a \cdot b) + 2a$. Compute $\frac{\partial g}{\partial a}$ by following the path from $a$ to $g$.
3. In your own words: what is the difference between the number on an edge during the forward pass and the number on the same edge during the backward pass?

---

## 18. Further reading

- [CS231n: Backpropagation](https://cs231n.github.io/optimization-2/) — Andrej Karpathy / Stanford.
- *Deep Learning* by Goodfellow, Bengio, and Courville, Chapter 6.
