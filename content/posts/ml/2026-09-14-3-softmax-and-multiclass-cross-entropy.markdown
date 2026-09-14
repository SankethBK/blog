---
title:  "Softmax and Multiclass Cross-Entropy: Turning Raw Scores Into Probabilities"
date:   2026-09-14
categories: ["ml"]
tags: ["ml", "softmax", "cross-entropy", "classification", "neural-networks", "logits"]

---

# Softmax and Multiclass Cross-Entropy: Turning Raw Scores Into Probabilities

So far, every classification in these notes has been binary — spam or not, XOR's 0 or 1 — and the output has been single sigmoid feeding binary cross-entropy, whose gradient collapsed to the beautiful $\delta = a - y$.

Real classifiers rarely answer two-way questions. "Which of 10 digits is this image?" "Which of 50,000 tokens comes next?" "Is this a cat, a dog, or a bird?" This note generalizes the output of a neural network to $k$ classes, and it turns out almost everything we know carries over — with soft-max doing the job sigmoid did.

Assumptions: you know the backprop pass on dense layers, sigmoid+BCE, and the $\delta = a - y$ result ([activation functions note](/posts/ml/2026-09-14-2-activation-functions-sigmoid-relu)). We will not redo those derivations; we'll do the new parts numerically, on ONE small example the whole way through.

---

## 1. From one output to k outputs: logits

A binary classifier ends in one neuron producing one number. A 3-class classifier ends in three neurons producing three numbers. In our running example (same network, but three output neurons), suppose the last linear step produces:

$$
z_1 = 2, \qquad z_2 = 1, \qquad z_3 = 0
$$

These numbers are called **logits** — the raw network output right before any activation is applied. Three observations matter before we do anything to them:

1. **Logits feel like scores**: bigger means "network is more partial to this class." The network currently prefers class 1 the most, class 3 the least.
2. **They are unbounded.** They can be $-50$, $3$, or $10{,}000$. That alone means they cannot be probabilities, which must live in $[0, 1]$.
3. **They do not sum to anything in particular.** $2 + 1 + 0 = 3$. Probabilities across mutually exclusive classes must sum to $1$.

Note also what logits are *not*: they are not "log-odds" and not anything inherently probabilistic yet. "Logit" is just the field's conventional name for "the value right before the output squashing activation," pure bookkeeping.

Our job: transform $(2, 1, 0)$ into a probability distribution over classes $(p_1, p_2, p_3)$ with $p_i \geq 0$ and $\sum p_i = 1$, such that bigger logit → bigger probability and the ordering of preference is preserved.

Many functions could do that. The field picked softmax, and the rest of the note is why — and what the consequences are.

---

## 2. Softmax, computed on our example

The softmax of a logit vector $z = (z_1, \dots, z_k)$ is:

$$
p_i = \operatorname{softmax}(z)_i = \frac{e^{z_i}}{\sum_{j=1}^{k} e^{z_j}}
$$

Every probability is $e^{z_i}$ normalized by the sum of all the exponentials. Compute it step by step for $z = (2, 1, 0)$:

$$
e^{z_1} = e^{2} \approx 7.389 \qquad e^{z_2} = e^{1} \approx 2.718 \qquad e^{z_3} = e^{0} = 1.000
$$

The "sum of exponentials," sometimes called the partition function:

$$
S = 7.389 + 2.718 + 1.000 = 11.107
$$

Normalize:

$$
p_1 = \frac{7.389}{11.107} = 0.665 \qquad p_2 = \frac{2.718}{11.107} = 0.245 \qquad p_3 = \frac{1.000}{11.107} = 0.090
$$

So:

$$
\operatorname{softmax}(2, 1, 0) = (0.665, 0.245, 0.090)
$$

Sanity checks, all passed:

- Every $p_i$ is between 0 and 1.
- $0.665 + 0.245 + 0.090 = 1.000$.
- Ordering preserved: class 1, with the biggest logit, got the biggest probability.

### The role of the exponential

Why $e^{z}$ and not something else? Two reasons, one mathematical, one behavioral:

- **Positivity, guaranteed.** $e^{z} > 0$ for every finite $z$, so no probability can ever go negative no matter what scores the network outputs.
- **Amplification of differences.** A gap of 1 unit between logits becomes a *factor of $e$* between probabilities. Logits $2$ and $1$ differ by one unit; their exponentials $7.389$ and $2.718$ have ratio $\approx 2.7$. Bigger logit gaps produce geometrically bigger probability gaps. Softmax is "soft arg+max": argmax would zero out the losers entirely; softmax lets them keep a share, with an exponential bias toward the winner.

### One logit moves every probability

This is the property that distinguishes softmax from doing $k$ independent sigmoids, and it comes straight from the denominator. Suppose we nudge $z_3$ up from $0 \to 2$ and leave the others alone:

$$
e^{z} = (7.389,\, 2.718,\, 7.389), \qquad S = 17.496
$$
$$
p = \left(\frac{7.389}{17.496},\, \frac{2.718}{17.496},\, \frac{7.389}{17.496}\right) = (0.422,\, 0.155,\, 0.422)
$$

$p_3$ more than quadrupled ($0.090 \to 0.422$) — but $p_1$ and $p_2$ were *also* forced to change ($0.665 \to 0.422$ and $0.245 \to 0.155$), even though their logits never moved. The probabilities are coupled through the denominator, like slices of a fixed-size pie: one slice getting bigger forces all the others to shrink.

This is exactly what "the classes are mutually exclusive" means when formalized. Compare with sigmoid-per-class: each sigmoid answers "is it this class, yes/no, independently of the others," and you can get $(0.9, 0.8, 0.7)$ — "confidently all three" — which is a contradiction for a mutually exclusive problem but a perfectly sensible answer for multi-label problems (an image can contain a cat and a dog). Choose sigmoid-per-class for multi-label; softmax for single-label.

---

## 3. Temperature: sharpening or flattening

One logit-scaling trick you meet everywhere (especially in Transformer decoding) is to divide the logits by a number $T > 0$ before softmax:

$$
p_i = \frac{e^{z_i / T}}{\sum_{j} e^{z_j / T}}
$$

This parameter is called **temperature**. Two regimes worth seeing concretely with our example:

**Low temperature ($T = 0.5$)** divides logits by a small number, equivalently scales them up: $(4, 2, 0)$. Exponentials $(54.60, 7.39, 1.00)$, sum $62.99$:

$$
p = (0.866, 0.117, 0.016)
$$

Sharper distribution, closer to argmax. Logit gaps of 1 unit behaved like gaps of 2.

**High temperature ($T = 2$)** flattens: logits $(1, 0.5, 0)$. Exponentials $(2.72, 1.65, 1.00)$, sum $5.37$:

$$
p = (0.506, 0.307, 0.186)
$$

Flatter, closer to uniform $(0.333, 0.333, 0.333)$.

$T = 1$ is vanilla softmax. The limits are: $T \to 0$ collapses onto argmax; $T \to \infty$ collapses onto uniform. Training temperatures are almost invariably 1; temperature mostly appears at *generation/inference* time, where cranking it up injects variety into sampled outputs and dropping it makes outputs more boring-but-conservative.

---

## 4. Multiclass cross-entropy

Now the loss. With binary classification we had $L = -(y \log a + (1 - y) \log (1-a))$. For $k$ classes, the label becomes a **one-hot vector** $y$ — a vector of $k-1$ zeros and one $1$ at the true class. The natural generalization:

$$
L = - \sum_{j=1}^{k} y_j \log p_j
$$

Because $y$ is one-hot, this whole sum collapses: if the true class is $c$, then $y_c = 1$ and every other $y_j = 0$, so all terms vanish except one:

$$
L = - y_c \log p_c = - \log p_c
$$

Just "the negative log of the probability the network assigned to the correct class." Compute it for our example, supposing the true class is $c = 2$:

$$
L = - \log(0.245) = 1.409
$$

This function punishes *underestimating the true class*, brutally at the extremes: if the network gives the correct class probability $0.99$, the loss is $-\log(0.99) \approx 0.01$; if it gives $0.01$, the loss is $-\log(0.01) = 4.6$. As the network's correct-class probability tends to $0$, the loss explodes to infinity. Cross-entropy is a harsh teacher: nothing matters to it except the probability on the right answer.

---

## 5. Why this pairing is chosen: the gradient is $p - y$

Combine the loss and the softmax, and take the derivative with respect to a logit $z_i$. The softmax has derivatives that couple every pair of classes — this is the Jacobian of softmax, and its $(i, j)$ entry is:

$$
\frac{\partial p_j}{\partial z_i} = p_j (\delta_{ij} - p_i)
$$

where $\delta_{ij}$ is $1$ if $i = j$ and $0$ otherwise. Now chain it into the loss:

$$
\frac{\partial L}{\partial z_i} = \sum_{j} \frac{\partial L}{\partial p_j} \cdot \frac{\partial p_j}{\partial z_i} = \sum_{j} \left( -\frac{y_j}{p_j} \right) \cdot p_j (\delta_{ij} - p_i)
$$

The $p_j$ in the denominator cancels the $p_j$ factor — exactly the same magical cancellation we saw with sigmoid+BCE, only now it happens across the whole Jacobian:

$$
\frac{\partial L}{\partial z_i} = - \sum_{j} y_j (\delta_{ij} - p_i) = -y_i + p_i \sum_{j} y_j = -y_i + p_i \cdot 1
$$

and therefore:

$$
\frac{\partial L}{\partial z_i} = p_i - y_i
$$

The gradient of softmax-cross-entropy with respect to the logits is just **prediction minus target**. For our example with $y = (0, 1, 0)$:

$$
\delta^{(out)} = p - y = (0.665 - 0,\; 0.245 - 1,\; 0.090 - 0) = (0.665,\; -0.755,\; 0.090)
$$

Read this vector: the gradient is positive on the classes the network over-rated and negative on the true class it under-rated. Gradient descent adds $-\eta \, \delta^{(out)}$ to the upstream weight gradient computation, which pushes $z_2$ up and pushes $z_1, z_3$ down, in precisely the amounts proportional to the current probability errors. The bigger the probability over-assigned to class 1, the harder its logit gets pushed down. Elegant, and exactly parallel to $\delta = a - y$ in the binary case — which is in fact the special case $k=2$.

One nuance worth noticing: unlike what you might guess ("only the true class should get a gradient"), **every logit receives a signal**. That is the price of the coupled denominator — raising one probability necessarily steals mass from the others, so the optimizer must be told about all of them.

---

## 6. One production detail: numerical stability

You will see this in every implementation, so it deserves 30 seconds. Logits can be as large as, say, $1000$. Then $e^{1000}$ is overflow → `inf` → NaN, and your entire training run is dead. The standard fix is to subtract the largest logit first:

$$
\operatorname{softmax}(z)_i = \frac{e^{z_i - m}}{\sum_j e^{z_j - m}}, \qquad m = \max_j z_j
$$

This is mathematically identical — numerator and denominator are both multiplied by $e^{-m}$, which cancels — but now the biggest exponent is $e^{0} = 1$, so nothing can overflow. In PyTorch, `nn.CrossEntropyLoss` takes **logits directly** (never softmaxed probabilities) precisely so it can do this internally via log-sum-exp. If you ever write `softmax()` yourself just to feed `log()`, you are setting a NaN trap for future-you.

---

## 7. Plugging it into the general backward loop

In the layer-loop pseudocode from the NumPy note, exactly one symbolic line changes:

```text
dZ[L] = output_error(A[L], Y)
```

With softmax outputs and cross-entropy, `output_error` is `A[L] - Y` — where now `Y` is a batch of one-hot rows instead of binary labels. That's it. The loop, the matrix shapes (now $(m, k)$ at the output instead of $(m, 1)$), the updates, everything else is untouched. The general machinery did not notice.

Binary sigmoid+BCE and multiclass softmax+CE are the same algorithm viewed at two different output widths — and that's not a coincidence, because sigmoid is just the 2-class special case of softmax with one degree of freedom removed.

---

## 8. Summary

- The network's raw outputs are **logits**: unbounded scores that encode preference order but are not probabilities.
- **Softmax** turns logits into a probability distribution: exponentiate (guaranteed positive, exaggerates gaps), normalize by the sum. Bigger logit → exponentially bigger share.
- The shared denominator **couples all classes**: moving any one logit changes every probability. That's the right semantics for single-label classification; use per-class sigmoid for multi-label.
- **Temperature** $T$ scales the logits pre-softmax: $T < 1$ sharpens, $T > 1$ flattens; used mostly at sampling/decode time.
- Multiclass **cross-entropy** is $-\log p_{\text{true}}$: only the network's probability on the correct class matters, and the cost of being confidently wrong is unbounded.
- The pair's gradient with respect to the logits is once again **$p - y$** — now a vector, positive on over-rated classes, negative on the true one, and every logit gets a gradient.
- Practical: subtract the max logit before exponentiating; in practice feed raw logits to the loss function (PyTorch's `CrossEntropyLoss`) and let it do the stable computation.

---

## 9. Exercises

1. For logits $(2, 1, 0)$ we got $p = (0.665, 0.245, 0.090)$. Compute softmax for $(3, 2, 1)$ — same gaps, shifted by 1. You should get *exactly the same distribution*. In one sentence, what property of softmax makes shifts irrelevant?
2. If logits were scaled from $(2,1,0)$ to $(20,10,0)$, describe in one sentence what happens to the distribution — and why feeding such logits straight into $e^{z}$ might get your program killed.
3. We saw $p - y = (0.665, -0.755, 0.090)$ for $y = (0,1,0)$. Why does the term for class 3 — a class that shouldn't win, and isn't the true class — still get a positive gradient on its logit (meaning its logit gets pushed down)? Would that happen with per-class independent sigmoids + per-class BCE?
4. Suppose all logits are equal, $(c, c, c)$. What is softmax's output? What is $p - y$ if the true class is $c_1$? Interpret: which classes get pushed up, which get pushed down, and by how much — and why this is a reasonable "doing nothing is punished" signal.
5. In the limits $T \to 0$ and $T \to \infty$, what does softmax converge to? For both limits, describe in one sentence what sampling next-token from a language model would look like.
6. A colleague proposes "just normalize the logits directly: $p_i = z_i / \sum_j z_j$." It breaks for more than one reason. Name at least two distinct ways this proposal fails as a distribution. (At least one failure should be about negative logits.)

---

## 10. What comes next

Neural networks can only process numbers, yet language, product catalogs, user graphs — the interesting data — is made of discrete symbols. The bridge is the **embedding layer**: a learned lookup table that turns each symbol into a dense trainable vector. The [next note](/posts/ml/2026-09-14-4-embeddings-from-one-hot-to-learned-representations) builds it from one-hot encodings (which we already have), shows that the embedding "lookup" is literally a linear layer, and follows the gradient back to show how the rows get learned.
