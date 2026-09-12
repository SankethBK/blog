---
title:  "Computational Graphs, Part 3: A Single Neuron and Logistic Regression"
date:   2026-09-12
categories: ["ml"]
tags: ["ml", "computational-graphs", "neuron", "logistic-regression", "backpropagation"]

---

# Computational Graphs, Part 3: A Single Neuron and Logistic Regression

The [previous note](/posts/ml/2026-09-12-1-branching-why-gradients-add) showed how gradients add when one input feeds multiple operations. With that in place, we can now look at a real model: a single neuron. We will draw it as a graph, run the forward pass and backward pass by hand, and then connect it back to the logistic regression from the [first note](/posts/ml/2026-09-07-1-ml-refresher-linear-logistic-regression).

---

## 1. What you will learn

- How a single neuron is a small computational graph.
- The forward pass through a weighted sum and an activation function.
- The backward pass through the same graph.
- Why logistic regression is exactly a one-neuron network with sigmoid activation.
- How the cross-entropy loss fits into the graph as an extra node.
- Why the gradient formula from logistic regression matches the chain-rule result.

---

## 2. A single neuron

A neuron with two inputs has three steps:

1. Compute a weighted sum of the inputs plus a bias.
2. Pass that sum through an activation function.
3. The result is the neuron's output.

For inputs $x_1$ and $x_2$, weights $w_1$ and $w_2$, and bias $b$:

$$
z = w_1 x_1 + w_2 x_2 + b
$$

$$
a = g(z)
$$

The graph is:

```text
x₁ ──► (*) ──┐
             │
w₁ ──► (*) ──┤
             │
x₂ ──► (*) ──┼──► (+) ──► z ──► g ──► a
             │             ▲
w₂ ──► (*) ──┤             │
             │             │
b  ──────────┘             │
                           │
                           │
                           (loss node comes later)
```

Each `(*)` is a multiplication, the `(+)` adds four terms, and `g` is the activation function.

---

## 3. Forward pass with concrete numbers

Pick values:

$$
x_1 = 1, \quad x_2 = -1, \quad w_1 = 2, \quad w_2 = 3, \quad b = -1
$$

Use the sigmoid as the activation function:

$$
g(z) = \sigma(z) = \frac{1}{1 + e^{-z}}
$$

**Step 1: weighted sum.**

$$
z = w_1 x_1 + w_2 x_2 + b
$$

$$
z = 2(1) + 3(-1) + (-1) = 2 - 3 - 1 = -2
$$

**Step 2: activation.**

$$
a = \sigma(-2) = \frac{1}{1 + e^{2}} \approx 0.1192
$$

So the neuron outputs approximately $0.1192$.

Because the sigmoid maps any real number to a value between 0 and 1, this output can be interpreted as a probability.

---

## 4. Backward pass: sensitivities of the activation

Suppose we want to know how the output $a$ changes when the weights change. We need the partial derivatives:

$$
\frac{\partial a}{\partial w_1}, \quad \frac{\partial a}{\partial w_2}, \quad \frac{\partial a}{\partial b}
$$

The path from each weight to $a$ goes through $z$:

```text
wᵢ ──► (+) ──► z ──► g ──► a
```

So for each weight:

$$
\frac{\partial a}{\partial w_i} = \frac{\partial a}{\partial z} \cdot \frac{\partial z}{\partial w_i}
$$

First, compute $\frac{\partial a}{\partial z}$. For the sigmoid, this has a convenient form:

$$
\frac{\partial \sigma(z)}{\partial z} = \sigma(z)(1 - \sigma(z)) = a(1 - a)
$$

With $a \approx 0.1192$:

$$
\frac{\partial a}{\partial z} = 0.1192 \cdot (1 - 0.1192) \approx 0.1050
$$

Next, compute how $z$ changes with each parameter:

$$
\frac{\partial z}{\partial w_1} = x_1 = 1
$$

$$
\frac{\partial z}{\partial w_2} = x_2 = -1
$$

$$
\frac{\partial z}{\partial b} = 1
$$

Now combine:

$$
\frac{\partial a}{\partial w_1} = 0.1050 \cdot 1 = 0.1050
$$

$$
\frac{\partial a}{\partial w_2} = 0.1050 \cdot (-1) = -0.1050
$$

$$
\frac{\partial a}{\partial b} = 0.1050 \cdot 1 = 0.1050
$$

These tell us how fast the neuron's output changes if we nudge each parameter, assuming we only care about $a$ and not yet about any loss.

---

## 5. Adding a loss node

A neuron by itself just makes a prediction. To train it, we need a **loss function** that measures how far the prediction is from the target.

For binary classification, the loss is the same cross-entropy we saw in logistic regression. If the true label is $y$ and the predicted probability is $a$:

$$
L = -\big[ y \log(a) + (1 - y) \log(1 - a) \big]
$$

The full graph now looks like:

```text
x₁, x₂, w₁, w₂, b ──► neuron ──► a ──► (loss) ──► L
                                      ▲
                                      │
                                      y
```

We want the gradients of the loss with respect to the parameters:

$$
\frac{\partial L}{\partial w_1}, \quad \frac{\partial L}{\partial w_2}, \quad \frac{\partial L}{\partial b}
$$

The path is now:

```text
wᵢ ──► (+) ──► z ──► g ──► a ──► (loss) ──► L
```

---

## 6. Backward pass through the loss and activation

Start at the loss node and work backward.

**Sensitivity of loss to activation:**

$$
\frac{\partial L}{\partial a}
= -\frac{y}{a} + \frac{1 - y}{1 - a}
$$

This comes from differentiating $-\big[ y \log(a) + (1 - y) \log(1 - a) \big]$.

Use $y = 1$ and $a \approx 0.1192$:

$$
\frac{\partial L}{\partial a} = -\frac{1}{0.1192} \approx -8.389
$$

What does this mean? The loss decreases as $a$ increases, because the true label is $y = 1$ and the prediction is currently too low.

**Sensitivity of loss to the pre-activation $z$:**

$$
\frac{\partial L}{\partial z}
= \frac{\partial L}{\partial a} \cdot \frac{\partial a}{\partial z}
= (-8.389) \cdot (0.1050)
\approx -0.8808
$$

There is a useful shortcut here. For the sigmoid followed by cross-entropy, the algebra simplifies:

$$
\frac{\partial L}{\partial z} = a - y
$$

With $a \approx 0.1192$ and $y = 1$:

$$
\frac{\partial L}{\partial z} = 0.1192 - 1 = -0.8808
$$

The two methods give the same answer. The shortcut is faster, but the long way shows you where it comes from.

---

## 7. Gradients with respect to the parameters

Now use $\frac{\partial L}{\partial z}$ and the local sensitivities of $z$:

$$
\frac{\partial L}{\partial w_1}
= \frac{\partial L}{\partial z} \cdot \frac{\partial z}{\partial w_1}
= (a - y) \cdot x_1
= -0.8808 \cdot 1
= -0.8808
$$

$$
\frac{\partial L}{\partial w_2}
= \frac{\partial L}{\partial z} \cdot \frac{\partial z}{\partial w_2}
= (a - y) \cdot x_2
= -0.8808 \cdot (-1)
= 0.8808
$$

$$
\frac{\partial L}{\partial b}
= \frac{\partial L}{\partial z} \cdot \frac{\partial z}{\partial b}
= (a - y) \cdot 1
= -0.8808
$$

These are the gradients we would use in a gradient-descent step.

---

## 8. Connection to logistic regression

Compare this to the logistic regression note. There, for one training example, the gradient was:

$$
\frac{\partial L}{\partial w} = (p - y) \, x
$$

$$
\frac{\partial L}{\partial b} = p - y
$$

where $p = \sigma(X w + b)$.

That is exactly what we just derived. A single neuron with sigmoid activation and cross-entropy loss **is** logistic regression. The only difference is that here we spelled out every operation as a node in a graph.

In the older notation:

- $z = X w + b$ is the weighted sum.
- $p = \sigma(z)$ is the activation output.
- $L$ is the cross-entropy loss.
- The gradient $p - y$ is the signal that flows backward from the loss through the sigmoid.

The graph view makes the same rule feel mechanical instead of memorized.

---

## 9. What the backward pass is doing

Here is what each backward-pass quantity represents:

- $\frac{\partial L}{\partial a}$: how the loss changes if the neuron's output changes.
- $\frac{\partial L}{\partial z}$: how the loss changes if the pre-activation changes. This is the "error signal" that arrives at the weighted-sum node.
- $\frac{\partial L}{\partial w_i}$: how the loss changes if a particular weight changes. This is what we need to update the weight.

The graph structure guarantees that we can compute every one of these by multiplying local sensitivities. We never had to differentiate the entire expression in one step.

---

## 10. What comes next

A single neuron gives logistic regression. A neural network is what you get when you stack many neurons and add hidden layers. The same forward-pass and backward-pass machinery scales to those larger graphs, because each node still only needs its own local rule.

The next note will look at why this scales and where automatic differentiation comes in.

---

## 11. Exercises

1. Recompute the forward and backward pass for the same neuron but with $x_1 = 2$, $x_2 = 1$, $w_1 = 1$, $w_2 = -1$, $b = 0$, and true label $y = 0$. Find $\frac{\partial L}{\partial w_1}$, $\frac{\partial L}{\partial w_2}$, and $\frac{\partial L}{\partial b}$.
2. Explain in your own words why $\frac{\partial L}{\partial z} = a - y$ for sigmoid activation and cross-entropy loss. Do not just quote the formula; trace through the two factors $\frac{\partial L}{\partial a}$ and $\frac{\partial a}{\partial z}$.
3. In the graph, the weighted-sum node $(+)$ sends the same gradient $\frac{\partial L}{\partial z}$ to all three of its parameter inputs, but each parameter ends up with a different gradient. Why?
