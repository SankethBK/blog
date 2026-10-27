# MNIST internals — lab series

Hands-on labs for the [ML notes](../../content/posts/ml/) on this blog. Guiding question:
*what do the weights of a neural network actually represent, and how do they change as the
network learns new things?*

No frameworks: pure NumPy, float64, gradients checked numerically. Runs on anything
(developed on a MacBook M3; nothing hardware-specific).

## Labs

| # | Notebook | Question it answers | Post |
|---|----------|---------------------|------|
| 1.1 | `01_what_do_weights_represent.ipynb` | What *is* a weight row? (Spoiler: a matched-filter photograph of its class, contrast-carved against rivals.) Watch the 10 rows develop from noise during training; decompose a prediction into per-pixel votes. | [lab-1.1](/posts/ml/labs/2026-10-19-lab-1-mnist-from-pixels-to-neural-network/) |
| 1.2 | `02_teach_1_2_then_3.ipynb` | Teach it only 1s and 2s, then introduce 3. Mirror-image two-class weights (cos = −0.98), new-class re-carving (Δ‖W‖/‖W‖ = 0.65–0.78 at fixed accuracy), catastrophic forgetting disassembled (the virgin class wins because it *never learned to say no*), and the rehearsal fix. | [lab-1.2](/posts/ml/labs/2026-10-19-lab-2-continual-learning-1-2-then-3/) |
| 1.3 | `03_one_hidden_layer_features.ipynb` | Add one hidden layer and weights stop being photographs. W₁ as class-agnostic stroke fragments (spatially coherent, not sparse — permutation-tested), W₂ as unreadable routing, dataset top-responders, activation maximization built from scratch (and proven redundant on layer 1), regularized class dreams, causal lesion studies (41 shared units; kill them → selective collapses), error analysis 791 → 277. | [lab-1.3](/posts/ml/labs/2026-10-27-lab-3-from-templates-to-features/) |
| 1.4 | *(planned)* | Same model in PyTorch on the M3's GPU (MPS), then a CNN — weight sharing finally delivers the textbook translation-invariant edge filters; probing the hidden representation space (t-SNE, linear probes). | — |

## Layout

```
01_what_do_weights_represent.ipynb   lab 1 (executed, outputs saved inline)
02_teach_1_2_then_3.ipynb            lab 2 (executed, outputs saved inline)
mnist_lab/                           shared helpers: IDX parsing, plotting, checkpoint bookkeeping
data/                                raw MNIST .gz (auto-downloaded; gitignored)
checkpoints/lab01, lab02/            .npz weight snapshots + manifest.json
figures/lab01, lab02/                exported PNGs (also embedded in the notebooks)
requirements.txt
```

## Run it

```bash
cd labs/ml/mnist-internals
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
jupyter lab            # kernel: "Python (mnist-internals)"
```

One-shot re-execution without opening Jupyter:

```bash
jupyter nbconvert --to notebook --execute --inplace 01_what_do_weights_represent.ipynb
```

## Regenerating the blog posts

From the repo root:

```bash
labs/ml/mnist-internals/.venv/bin/python scripts/nb2post.py \
    labs/ml/mnist-internals/01_what_do_weights_represent.ipynb \
    --category ml/labs --fm-category ml \
    --slug 2026-10-19-lab-1-mnist-from-pixels-to-neural-network \
    --title "..." --date 2026-10-19 --tags ...
```

(`--fm-category` keeps the Hugo taxonomy at `ml` while the bundle lives under
`posts/ml/labs/`; nb2post also strips nbconvert's absolute image paths so links
are bundle-relative.)

## Reading (collected from the labs)

- Olah et al., *Feature Visualization* (Distill 2017) — https://distill.pub/2017/feature-visualization/
- Olah et al., *The Building Blocks of Interpretability* (Distill 2018)
- *Zoom In: An Introduction to Circuits* (Distill 2020)
- Anthropic, *Toy Models of Superposition* (2022) — why features superpose; the real reason LLMs are opaque
- McCloskey & Cohen (1989); French (1999) — catastrophic interference/forgetting
- Kirkpatrick et al., *Overcoming catastrophic forgetting* (PNAS 2017) — EWC
- Wu et al., *Large Scale Incremental Learning / BiC* (CVPR 2019) — new-class logit inflation
- LeCun et al., *Gradient-Based Learning Applied to Document Recognition* (1998)
