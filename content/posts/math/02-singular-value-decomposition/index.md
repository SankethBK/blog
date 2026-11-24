---
title: "SVD — how much does a rectangular matrix stretch each direction?"
date: 2026-11-24
weight: 2
categories: ["math"]
tags: ["linear-algebra", "svd", "low-rank"]
---

A neural network weight matrix can map 32 input features to 96 outputs. Asking whether its output points along its input makes little sense when the two live in different spaces. We can still ask a concrete question. Among unit-length inputs, which one produces the longest output?

## Trace one rectangular matrix

Use four observations with two features and temporarily think of their data matrix as a linear map from two numbers to four.

$$
X=\begin{bmatrix}2&1\\1&2\\-2&-1\\-1&-2\end{bmatrix},
\qquad X^\top X=\begin{bmatrix}10&8\\8&10\end{bmatrix}.
$$

For a unit vector $v$, the squared output length is $v^\top X^\top Xv$. From the [eigenvector note]({{< relref "posts/math/01-eigenvectors" >}}), write $v=a q_1+b q_2$ with $a^2+b^2=1$. The squared length becomes $18a^2+2b^2$. Its maximum is 18 along $q_1$. Along the perpendicular direction $q_2$ it is 2. The actual lengths, $\sqrt{18}$ and $\sqrt 2$, are the **singular values**.

Where do these inputs land? $Xq_1=(3,3,-3,-3)^\top/\sqrt2$. Dividing by its length gives the unit output direction $u_1=(1,1,-1,-1)^\top/2$. Similarly, $Xq_2=(1,-1,-1,1)^\top/\sqrt2$, so $u_2=(1,-1,-1,1)^\top/2$. Notice that the output directions are perpendicular too.

## Read the factorization in the order it acts

Call the input directions $v_1=q_1$ and $v_2=q_2$. Stack them as columns of $V$, and stack the output directions as columns of $U$. Now $Xv_i=\sigma_i u_i$. For an arbitrary input $z$ this gives

$$
Xz=\sigma_1 u_1(v_1^\top z)+\sigma_2 u_2(v_2^\top z),
\qquad X=U\Sigma V^\top.
$$

Here the **reduced SVD** has shapes $(4,2)(2,2)(2,2)$. $V^\top$ reads two input coordinates, $\Sigma$ applies the two stretches, and $U$ combines two arrows in four-dimensional output space. NumPy returns the last factor already transposed as `Vt`. A simultaneous sign flip of $u_i$ and $v_i$ changes neither their outer product nor the reconstructed matrix.

## What do you lose by keeping one direction?

Each term $\sigma_i u_i v_i^\top$ is a rank-one matrix. **Rank** counts independent output directions. Keeping only the strongest term gives the first reconstructed row $(1.5,1.5)$ in place of $(2,1)$. Its squared error is $0.5$. The other three rows each lose the same amount, giving a total squared error of 2.

This is the best rank-one approximation under summed squared entrywise error (squared Frobenius norm). The truncated SVD gives the general result: after keeping $k$ terms the squared error is $\sum_{i>k}\sigma_i^2$. Here the full matrix has squared norm $18+2=20$. Retaining the first direction preserves $18/20=90\%$ of its squared norm.

```python
import numpy as np

X = np.array([[2, 1], [1, 2], [-2, -1], [-1, -2]], dtype=float)
U, s, Vt = np.linalg.svd(X, full_matrices=False)
rank_one = (U[:, :1] * s[:1]) @ Vt[:1]
np.testing.assert_allclose((U * s) @ Vt, X)
np.testing.assert_allclose(np.sum((X - rank_one) ** 2), 2)
```

**Connect it to LoRA.** In your full-tuning lab the matrix was $\Delta W=W_{\text{after}}-W_{\text{before}}$. Four singular directions captured about 49% of the squared change in one QKV projection. That answers how closely a rank-four matrix can reconstruct *those parameter changes*. Predicting the effect on a particular activation also requires knowing where the activation points relative to the right singular vectors. What happens to an input perpendicular to every discarded direction? [Full fine-tuning lab]({{< relref "posts/ml/labs/2026-11-24-lab-3-10-full-fine-tuning" >}}) · [Continue to PCA]({{< relref "posts/math/03-principal-component-analysis" >}})
