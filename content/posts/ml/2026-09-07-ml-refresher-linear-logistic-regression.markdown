---
title:  "ML Refresher: Linear and Logistic Regression"
date:   2026-09-07
categories: ["ml"]
tags: ["ml", "linear-regression", "logistic-regression", "gradient-descent", "numpy"]

---

# ML Refresher: Linear and Logistic Regression

This is the first note in the ML → Deep Learning → Transformers → LLMs series. The goal is to rebuild working memory of the basics before we get to neural networks: what a model is, how a loss function measures error, and how gradient descent tunes parameters.

We will implement linear regression and logistic regression from scratch in NumPy, then compare with scikit-learn. If the code and gradients feel obvious, you are ready for the next note (computational graphs and backprop). If not, this is exactly the foundation to lock down first.

---

## 1. What you will learn

- How linear regression models a continuous target.
- How logistic regression turns a continuous score into a probability.
- Mean squared error and binary cross-entropy losses.
- Gradient descent vs. the normal equation for linear regression.
- Why logistic regression uses the sigmoid and cross-entropy together.
- L2 regularization and why we usually do not regularize the bias.

---

## 2. Linear regression

We have a dataset of `n` examples. Each example has `d` input features and a real-valued target.

```text
X  shape: (n, d)   — input matrix
y  shape: (n,)     — target vector
w  shape: (d,)     — weights we want to learn
b  scalar          — bias offset
```

The model predicts:

$$
\hat{y} = X w + b
$$

In vectorized NumPy this is `X @ w + b`. The bias `b` is broadcast across all examples.

### 2.1 Loss: mean squared error (MSE)

$$
L(w, b) = \frac{1}{n} \sum_{i=1}^{n} (\hat{y}_i - y_i)^2
        = \frac{1}{n} \\| \hat{y} - y \\|^2
$$

This measures the average squared distance between predictions and targets. Squaring penalizes large errors more than small ones and makes the gradient smooth.

### 2.2 Optimization: gradient descent

Take the gradient of the loss with respect to `w` and `b`:

$$
\frac{\partial L}{\partial w} = \frac{2}{n} X^T (\hat{y} - y)
\qquad
\frac{\partial L}{\partial b} = \frac{2}{n} \sum_{i=1}^{n} (\hat{y}_i - y_i)
$$

> This formula is derived from the chain rule of calculus. In $\frac{\partial L}{\partial w}$, since $\hat{y} = Xw + b$, we have $\frac{\partial \hat{y}}{\partial w} = X^T$. Similarly, in $\frac{\partial L}{\partial b}$, we have $\frac{\partial \hat{y}}{\partial b} = 1$.

Then update the parameters with learning rate $\alpha$:

$$
w \leftarrow w - \alpha \frac{\partial L}{\partial w}
\qquad
b \leftarrow b - \alpha \frac{\partial L}{\partial b}
$$


> The learning rate $\alpha$ controls how big a step we take in the direction of the negative gradient. A larger learning rate converges faster but may overshoot the minimum, while a smaller learning rate converges slower but is more stable.

> This is the core idea that keeps repeating across all of machine learning: we take the gradient of the loss function with respect to the parameters, and then update the parameters in the direction of the negative gradient to minimize the loss.

> Why does this work? First of all we have defined L(w,b) such that it is always positive. The goal is to minimize L(w,b). Why can't we just set the derivative of L(w,b) to 0 and solve for w and b? Because L(w,b) is a complex function of w and b, and we can't solve for w and b analytically. So, we use gradient descent to iteratively update w and b until we reach the minimum. And moreover, the solution wouldn't exist in most of the practical datasets.

> The reason that this works is, we know that a derivative of a function at a point gives us the slope of the tangent line at that point. If the derivative is positive, the function is increasing at that point, and if the derivative is negative, the function is decreasing at that point. So, if we move in the direction of the negative gradient, we are moving in the direction of the steepest decrease, which means we are moving towards the minimum.

> While doing so, we might overshoot the minimum, and end up at a point where the loss is higher than the previous point. This is where the learning rate comes into play. A larger learning rate converges faster but may overshoot the minimum, while a smaller learning rate converges slower but is more stable. Another interesting thing to observe here is: by making the step size proportional to the slope, as the slope flattens the value of step decreases naturally even with a constant learning rate. 

> The problem with local minimas: The main drawback of gradient descent is that it can get stuck in local minima. A local minimum is a point where the function is smaller than all nearby points, but not necessarily the smallest point in the entire domain. In machine learning, this can happen when the loss function has multiple local minima, and the algorithm converges to a suboptimal solution. A simplest fix for this is to run gradient descent multiple times with different initializations, and pick the solution with the lowest loss. (Don't be skeptical because of this, gradient descent is still one of the best and most widely used optimization algorithms in machine learning.)

> To make sense of partial derivates: Imagine only 2 inputs x and y and the z axis is the cost function's value. As x and y varies we get a different z. Now imagine z has bowl shape somewhere, by partially differentiating the function, once w.r.t x and then w.r.t y, what we get is “What happens to the loss if I move along this one axis while freezing everything else?” ∂L/∂x = slope if I walk east/west, ∂L/∂y = slope if I walk north/south, gradient = [∂L/∂x, ∂L/∂y]. Now we move both x and y independently in the direction of decreasing slope - net result will be movement towards a point which will have lesser value of z than before. 
> The magnitude of slope indicates how steep it is, and the direction says whether its increasing or decreasing. 

> Now to extend this idea to multi-dimension input, differentiating the function w.r.t to one of the input parameter means freezing all the planes and considering only one plane at a time. 
> For a model like
>
> $$
> \hat{y} = w_0x_0 + w_1x_1 + w_2x_2 + \cdots + w_dx_d + b
> $$
>
> you can absolutely think of gradient descent as computing each parameter’s update independently:
> $$
> w_0 \leftarrow w_0 - \alpha\frac{\partial L}{\partial w_0}
> $$
> $$
> w_1 \leftarrow w_1 - \alpha\frac{\partial L}{\partial w_1}
> $$
>
> The vectorized version:
> $$
> \mathbf{w} \leftarrow \mathbf{w} - \alpha\nabla_{\mathbf{w}} L
> $$
> is essentially doing all those scalar updates in one operation.
>
> The reason b (bias) is treated as separate parameter is because its $x^{0}$ and the formula for its partial derivate is different compared to all other inputs. 

### 2.3 Alternative: the normal equation

For linear regression only, there is a closed-form solution. If we augment `X` with a column of ones so that `w` absorbs `b`, the optimal weights are:

$$
w^* = (X^T X)^{-1} X^T y
$$

This gives the exact minimum in one step, but it costs $O(d^3)$ to invert and fails if $X^T X$ is singular. Gradient descent is slower per run but scales to huge $d$ and online data.

> Don't overthink this formula, remember that this matrix itself already contains enough information to solve it (eg: imagine what Cramer's theorem does, it treats that the equations themselves already contain all info to solve them). This is just another way 
> Start from what you already know
>
> For linear regression:
>
> $$
> \hat{y} = Xw + b
> $$
>
> and we’re trying to minimize MSE:
>
> $$
> L(w) = \frac{1}{n}\\|Xw - y\\|^2
> $$
>
> Gradient descent says:
>
> Keep calculating the gradient and moving opposite to it until the gradient becomes zero.
>
> So at the minimum:
>
> $$
> \nabla L(w) = 0
> $$
>
> For linear regression, we can actually solve that equation algebraically instead of taking thousands of little steps.
>
> ---
>
> Let’s ignore the bias for a second.
>
> Say:
>
> $$
> L(w) = \\|Xw - y\\|^2
> $$
>
> Expand it:
>
> $$
> L(w) = (Xw - y)^T(Xw - y)
> $$
>
> which becomes:
>
> $$
> w^T X^T X w - 2y^T Xw + y^T y
> $$
>
> Now differentiate with respect to $w$:
>
> $$
> \nabla L = 2X^T Xw - 2X^T y
> $$
>
> At the minimum:
>
> $$
> 2X^T Xw - 2X^T y = 0
> $$
>
> Cancel 2:
>
> $$
> X^T Xw = X^T y
> $$
>
> And now this is just a system of linear equations.
>
> Multiply both sides by $(X^T X)^{-1}$:
>
> $$
> \boxed{w = (X^T X)^{-1} X^T y}
> $$
>
> That’s the normal equation.

> Some matrix multiplication prerequisite to make this clear
>
> 1. Why does ||v||² become vᵀv?
>
> If
>
> $$
> v =
> \begin{bmatrix}
> v_1 \\\\
> v_2 \\\\
> v_3
> \end{bmatrix}
> $$
>
> then
>
> $$
> \\|v\\|^2 = v_1^2 + v_2^2 + v_3^2
> $$
>
> Now transpose $v$:
>
> $$
> v^T =
> \begin{bmatrix}
> v_1 & v_2 & v_3
> \end{bmatrix}
> $$
>
> Multiply:
>
> $$
> v^T v =
> \begin{bmatrix}
> v_1 & v_2 & v_3
> \end{bmatrix}
> \begin{bmatrix}
> v_1 \\\\
> v_2 \\\\
> v_3
> \end{bmatrix}
> $$
>
> which gives:
>
> $$
> v_1^2 + v_2^2 + v_3^2
> $$
>
> So:
>
> $$
> \boxed{\\|v\\|^2 = v^T v}
> $$
>
> Therefore, if
>
> $$
> v = Xw - y
> $$
>
> then:
>
> $$
> L(w) = \\|Xw - y\\|^2
> $$
>
> becomes:
>
> $$
> L(w) = (Xw - y)^T(Xw - y)
> $$
>
> Nothing fancy yet.
>
> ---
>
> 2. Now the part you’re stuck on: the transpose
>
> We have:
>
> $$
> (Xw - y)^T
> $$
>
> There is a very important rule:
>
> $$
> \boxed{(ABC)^T = C^T B^T A^T}
> $$
>
> Transpose reverses the order.
>
> For example:
>
> $$
> (AB)^T = B^T A^T
> $$
>
> So:
>
> $$
> (Xw)^T = w^T X^T
> $$
>
> because the original order is:
>
> $X \mathbin{\to} w$
>
> and after transpose:
>
> $w^T \mathbin{\to} X^T$
>
> Therefore:
>
> $$
> \begin{aligned}
> (Xw - y)^T
> &= (Xw)^T - y^T \\\\
> &= w^T X^T - y^T
> \end{aligned}
> $$
>
> So our expression becomes:
>
> $$
> (w^T X^T - y^T)(Xw - y)
> $$
>
> Now it’s just FOIL, exactly like ordinary algebra.


---

## 3. Logistic regression

Logistic regression is for classification, not regression. The target `y` is 0 or 1. The model still computes a linear score `z = X w + b`, but then squashes it through the sigmoid to produce a probability.

$$
\sigma(z) = \frac{1}{1 + e^{-z}}
$$

$$
P(y=1 \mid x) = \sigma(X w + b)
$$

The sigmoid maps any real number into `(0, 1)`.

### 3.1 Loss: binary cross-entropy

For one example:

$$
L_i = -\big[ y_i \log(p_i) + (1 - y_i) \log(1 - p_i) \big]
$$

For the whole dataset, average it:

$$
L = -\frac{1}{n} \sum_{i=1}^{n} \big[ y_i \log(p_i) + (1 - y_i) \log(1 - p_i) \big]
$$

If the true label is 1 and the model predicts `p ≈ 1`, the loss is near 0. If the model predicts `p ≈ 0`, the loss blows up. This is exactly the behavior we want for binary classification.

### 3.2 Gradient for logistic regression

The gradient turns out to have almost the same shape as linear regression, just with a different prediction function:

$$
\frac{\partial L}{\partial w} = \frac{1}{n} X^T (p - y)
\qquad
\frac{\partial L}{\partial b} = \frac{1}{n} \sum_{i=1}^{n} (p_i - y_i)
$$

Where $p = \sigma(X w + b)$. Notice there is no factor of 2 because the cross-entropy derivative cancels the sigmoid derivative.

> It seems like these formulas came out of the blue after linear regression, but there is a really nice chain of ideas behind it
>
> The first thought which comes to mind is: why can't we use the linear regression as it is for classification? The way to imagine this is, instead of drawing a line to fit all the points as best as possible, we need to draw a line to separate out the 2 groups as best as possible

```text
Logistic regression: separates the classes

    y       x /       
    |   o    / x                          
    |  o    / x                            
    |   o  /   x x         
    | o   /  x                             
    |  o /  o                                
    +---------------- x                    
                                                                                         +---------------- x1
```

> This idea in itself is not a bad one: But let's imagine what does it take to implement this i.e., instead of telling linear regression, don't try to minimize the distance b/w line and points, instead try to draw the line such that most of the points towards a given side of the line belongs to one of the classes. 
>
> We might think the limitation here is that what if the decision boundary is a circle? A line can never approximate it? 
> True, but same limitation exists with linear regression as well, that's when we switch to higher order polynomials. 
>
> There is a bigger problem here. If we think about what linear regression actually did, in simple words we know the input parameter(s) - the x-axis, based on some approximated line, it would tell us the predicted value - i.e., the y-axis. Now the repsentation we have for logistic regression here is we are using x and y axis to represent input features, i.e., we already know where the point falls in the graph, since the line learnt from weights cuts the entire plane into 2 halves we can still tell which group a point belongs to based on towards which side it falls.
>
> This seems perfectly reasonable, until we start thinking how are we going to train it? 
>
> The first concrete thing here is that the Logistic regression keeps the line — its decision boundary is still a straight line wᵀx + b = 0.
> What changes is 
> a. how the output is interpreted (probability, not a raw number)
> b. how the line is found (maximizing likelihood of the correct labels, not minimizing squared vertical distance). 
>
> To describe it in more detail
>
> Problem 1 — the output is unbounded. A linear model predicts ŷ = wᵀx + b ∈ (−∞, ∞). You get "probabilities" like −3 or 7.2. A probability must live in (0, 1), so something must squash the real line down. (This problem might seem solvable: if a point is close to the decision boundary then we have very less confidence that it belongs to this class, but if its farther from the decision boundary we are more confident - Turns out this is a correct idea, and logistic regression actually keeps it, so problem 1 is not a strong claim) 
>
> Problem 2 - The cost funnction, instead of minimizing the MSE, it should now focus on classification. For eg, a decision boundary where each side of the boundary contains half of the data points for each class is a worst decision boundary and should get maximum penalty, while a decision boundary which cuts the plane such that each side has 80% of one class should get much lesser penalty. Another characteristic of the loss function should be, let's say there is another decision boundary which also cuts the plane such that each side has 80% data points of one class, but the way it cuts is different - there are no data points near to the decision boundary - all of them are located significantly farther than line compared to the first one - in this case the second line should get even less penalty. 
>
> There is a hidden problem within our 2nd problem: we said points closer to line should get less confidence and points farther to line should get higher confidence? But if we think about it, how near is near and how far is far exactly? Meaning the distance itself is relative, if all points are close to line and one point is little bit more close, then there is no strong reason to penalize it heavily, compared to a case where most of the points are farther, but only one point is closer. 
>
> So the solution to this hidden problem is to express distance as a probability but also considering the relative distance to other points of same class. Let's ask what function behaves in such a way? 
>
> Let's clear up some notation before we get our hands dirty in this
> In linear regression, `y = wᵀx + b` means:
> - `x` is the input (x-axis)
> - `y` is the output (y-axis)
> - the line lives in input × output space
>
> In logistic regression, `z = wᵀx + b` means:
>
> - `x₁, x₂` are both inputs (both axes of the feature plane)
> - `z` is not plotted — it's a computed scalar
> - the line lives entirely in input × input space
>
> **z = signed distance to the boundary line** 
>
> Now the way we calculate this signed distance to the boundary line is pretty interesting 
>
> If we assume the equation of line to be **Ax + By + C = 0**, then the magnitude of perpendicular distance b/w any point **(x1, y1)** and the line is given by 
>
> $$
> d = \frac{|Ax_1 + By_1 + C|}{\sqrt{A^2 + B^2}}
> $$
>
> Now this formula is difficult to make sense of for someone who has vector algebra knowledge is rusty from 10 years ago, but i trust the math and take it granted because i already spent 1 night trying to understand it. 
>
> Now remove the modulo because we are interested in the signed distance, and if we look at the denominator, its constant for a given line. Since we are dealing with relative distances, we can just ignore the denominator as well. So our formula simplifies to $$d = Ax_1 + By_1 + C$$
>
> That means all we are doing is plugging the point into the equation of the line, if the point lies on the line it will give us 0, because that's the equation, otherwise it will give us something proportional to the perpendicular signed distance. 
>
> Now extending the same logic, the perpendicular signed distance for **z = wᵀx + b** would have been  
> $$
> d = \frac{{|w^Tx + b|}}{||w||}
> $$
>
> With same logic we can simplify it to 
>
> $$d = w^Tx + b$$
>
> Till now we were talking about z = wᵀx + b, now we need a function h(z), what are the requirements for our function?
> 1. h(z) ∈ (0, 1)          must be a valid probability
> 2. h(0) = 0.5             on the boundary, maximum uncertainty
> 3. h(z) → 1 as z → +∞    far on one side → very confident
> 4. h(z) → 0 as z → -∞    far on other side → very confident the other way
> 5. monotone, smooth        so gradient descent can work through it (This is a whole next level problem, we will get here)
>
> Now all the properties above are exactly the properties of the sigmoid function. It has an **S** shape, crosses the y-axis at 0.5, approaches 1 as $x \to +\infty$, and approaches 0 as $x \to -\infty$.
>
> The sigmoid is defined as:
>
> $$
> \sigma(z) = \frac{1}{1 + e^{-z}}
> $$
>
> Now we encode the signed distance into the sigmoid.
> $$
> h(z) = \frac{1}{1 + e^{-(w^Tx + b)}}
> $$
>
> **Many diagrams and youtube videos show sigmoid as a decision boundary, showing that sigmoid does not mess up when there are outliers, this is wrong! this is what started confusing me yesterday. Sigmoid is never the decision boundary, it's the way we express the distance to decision boundary as probability.**
>
> ### Now the loss function
>
> Let's see what happens if we try to use the same loss function as regression
>
> $$
> L(w, b) = \frac{1}{n} \sum_{i=1}^{n} (h(z) - y_i)^2
> $$
>
> Now this let's try to identify the issues with it. 
>
> Let;s say we have 2 classes y ∈ {0,1}. We refine the meaning of `h(z)` as` p(y = 1|x,w,b)` meaning its output is indication of what's the probability that this point belongs to the class `y = 1`, if `p = 0.8` it means we are 80% sure it belongs to the class `y = 1`. Similarly `p = 0.2` means, we are 20% sure that it belongs to the class `y = 1`. See how are are not talkign about `y = 0` at all, but for a binary classification, it automatically means the probability of class `y = 0` is `1 - p`. 
>
> Now the reason, MSE seems to work is because if the model predicts the class correctly `h(z) = 0.9` and `y = 1` will only get a tiny penalty. `h(z) = 0.1` and `y = 0` is a similar case. Notice the neat hack where p apporaching 0 also means `y = 0`. So penalty wise we seem sorted. 
>
> Let's see some more cases
> ```
> h(z) = 0.9,  y = 1   →   (0.9 - 1)²  = 0.01   ✓ low penalty, correct
> h(z) = 0.1,  y = 0   →   (0.1 - 0)²  = 0.01   ✓ low penalty, correct
> h(z) = 0.1,  y = 1   →   (0.1 - 1)²  = 0.81   wrong, gets penalty 
> h(z) = 0.9,  y = 0   →   (0.9 - 0)²  = 0.81   wrong, gets penalty
> ```
> So far MSE looks reasonable. Here's the actual problem.
>
> The worst case under MSE is `(0 - 1)² = 1` or `(1 - 0)² = 1`. No matter how confidently wrong the model is, the loss never exceeds 1. The model can be 99% sure of the wrong class and the penalty is just `0.99² ≈ 0.98` — barely worse than being 90% sure of the wrong class `(0.81)`.
>
> MSE doesn't scream when the model is confidently wrong. It just shrugs.
>
> What you actually want from a loss for classification:
>
> ```
> confidently correct   →   loss near 0
> uncertain             →   moderate loss
> confidently wrong     →   loss → ∞
> ```
> That last line is what MSE can never give you, because it's a squared difference between two numbers that both live in `(0, 1)`.
>
> Cross-entropy gives you exactly this:
> `L = -log(h(z))        when y = 1`
> 
> If `h(z) = 0.99` (confidently correct) → `-log(0.99) ≈ 0.01`, tiny.
> If `h(z) = 0.5` (uncertain) → `-log(0.5) ≈ 0.69`, moderate.
> If `h(z) = 0.01` (confidently wrong) → `-log(0.01) ≈ 4.6`, huge.
> If `h(z) → 0` (maximally wrong) → `-log(0) → ∞, explodes`.
>
> When `y = 0`, we can tweak the formula to `L = -log(1 - h(z))`. 
>
> We can encode both of them in a single formula 
>
> $$
> L = -[y_i log(h(z)) + (1 - y_i) log(1 - h(z))]
> $$
>
>
> Hopefully this deep dive pays off while neural networks. 


---

## 4. Regularization

Models with many parameters can memorize noise in the training data. L2 regularization penalizes large weights:

$$
L_{\text{reg}} = L + \lambda \\|w\\|^2
$$

The gradient update becomes:

$$
w \leftarrow w - \alpha \big( \nabla_w L + 2 \lambda w \big)
$$

We usually do not regularize the bias `b`, because shifting the prediction up or down is not a complexity issue.

> A note: 
> Some textbooks write $w^Tx + b$ as just $θ^Tx$. They appear to skip the bias entirely, but its just a clear way to hide it, the way bias can be hidden is by adding an extra column of 1's in input `x`, the end result of multiplication remains same. 
