---
title: "Eigenvectors — which directions does a matrix preserve?"
date: 2026-11-24
weight: 1
categories: ["math"]
tags: ["linear-algebra", "eigenvectors"]
---

Suppose a two-neuron linear layer takes an input $v$ and returns $Av$. You already know how to compute the output for one input. Can you find two inputs whose behavior tells you what happens to *every* input?

## Try the axes, then the diagonals

Take this matrix and treat inputs as column vectors.

$$
A=\begin{bmatrix}10&8\\8&10\end{bmatrix}.
$$

An input pointing right, $(1,0)$, becomes $(10,8)$. The input axis has tilted. Try stepping along both input coordinates equally. Multiplying $(1,1)$ gives $(18,18)$. Try increasing the first coordinate while decreasing the second. Multiplying $(1,-1)$ gives $(2,-2)$. Each diagonal maps back onto its own line.

An **eigenvector** is any nonzero vector $v$ satisfying $Av=\lambda v$. Its **eigenvalue** $\lambda$ is the multiplier. A negative multiplier reverses the arrow. A zero multiplier sends it to the origin. Scaling the starting vector leaves its eigenvalue unchanged, which is why we can choose convenient unit-length representatives.

## Find those directions without guessing

Rearrange to $(A-\lambda I)v=0$. An invertible matrix would force $v=0$, so we look for values that make $A-\lambda I$ singular. For this two-by-two matrix its determinant is

$$
(10-\lambda)^2-8^2=0.
$$

This gives $\lambda=18$ or $2$. Substitute 18 into the first row of the equation and you get $-8v_1+8v_2=0$, hence $v_1=v_2$. Substituting 2 gives $8v_1+8v_2=0$, hence $v_1=-v_2$. Dividing each direction by its length gives

$$
q_1=\tfrac{1}{\sqrt 2}(1,1)^\top,\qquad q_2=\tfrac{1}{\sqrt 2}(1,-1)^\top.
$$

Their dot product is zero and each has length one. Such a basis is **orthonormal**. For any input $x$, the dot product $q_i^\top x$ measures its signed coordinate along $q_i$.

## Rebuild the action on an ordinary input

For $x=(2,0)^\top$, both coordinates in the new basis are $\sqrt 2$. Stretch one by 18 and the other by 2. Converting back gives $18(1,1)^\top+2(1,-1)^\top=(20,16)^\top$. Check that against direct multiplication.

Put the unit vectors in the columns of $Q$ and the multipliers on the diagonal of $\Lambda$. The calculation you just did is the **eigendecomposition**

$$
Ax=Q\Lambda Q^\top x.
$$

Reading right to left, $Q^\top$ finds coordinates, $\Lambda$ scales them, and $Q$ rebuilds the output. Real **symmetric** matrices such as this one always have an orthonormal eigenbasis. A general square matrix may lack one. For example, a 90-degree rotation has no real eigenvector because it turns every nonzero arrow off its original line.

## Why this comes up in ML

Suppose $X$ holds observations in its rows. Then $A=X^\top X$ is square and symmetric even when $X$ is rectangular. Also $v^\top A v=\|Xv\|^2\geq0$. For a unit eigenvector this quantity is exactly its eigenvalue. This explains why the eigenvalues of this particular kind of matrix are nonnegative and why a large one identifies a direction along which $X$ has a large effect.

**Try before continuing.** For input $(1,0)^\top$, predict which diagonal contributes more to the output. If both eigenvalues were 2, what would happen to every input direction? [Continue to SVD]({{< relref "posts/math/02-singular-value-decomposition" >}})
