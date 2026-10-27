# LM internals — lab series

Hands-on labs following the [language-model theory notes](../../../../content/posts/ml/)
(embeddings, attention, transformer block, LM training). Organizing question of the series:
*why did neural sequence models move from carrying everything through one recurrent state to
retrieving with attention — and what did each architecture actually buy?*

Same ritual as `labs/ml/mnist-internals`: pure NumPy, gradients checked numerically before any
claim is trusted, every figure and checkpoint saved.

## Labs

| # | Notebook | Question it answers | Post |
|---|----------|---------------------|------|
| 2.1 | `01_how_word_vectors_learn_to_mean.ipynb` | How does a row of numbers come to *mean* anything? SGNS from scratch on a grammar we control; the Levy–Goldberg reveal (corr(E·Uᵀ, PMI−log k) = 0.95; SVD of counts as a gradient-free baseline); analogy arithmetic measured rather than demoed (offsets parallel at cos 0.94–0.99; ranking brittle); bias as controlled experiment. | [lab-2.1](/posts/ml/labs/2026-10-27-lab-2-1-how-word-vectors-learn-to-mean/) |
| 2.2 | *(planned)* | A language model without attention: char-level RNN, backprop-through-time by hand, and the measured death of gradient signal with dependency distance (synthetic memory task). | — |
| 2.3 | *(planned)* | LSTM gates as memory engineering: same task, same traces, what the cell state actually fixes — and what it doesn't. | — |
| 2.4 | *(planned)* | Attention from raw tensors: build Q/K/V by hand on a 4-token toy, then a causal self-attention LM; head visualizations; RNN vs LSTM vs attention on the same long-range task. | — |
| 2.5+ | *(planned)* | minimal transformer LM, BPE tokenization, probing/interpretability; PyTorch on MPS once the NumPy ceiling is reached. | — |

## Layout

```
01_how_word_vectors_learn_to_mean.ipynb   lab 2.1 (executed, outputs saved inline)
lm_lab/                                   microworld corpus generator + checkpoint bookkeeping
checkpoints/lab21/                        .npz artifacts (E/U tables, PMI matrix, sweeps) + manifest.json
figures/lab21/                            exported PNGs (also embedded in the notebook)
requirements.txt
```

## Run it

This project reuses the shared, fully pinned environment from the sibling MNIST lab
(same package set). From this folder:

```bash
../mnist-internals/.venv/bin/jupyter lab   # kernel: "Python (lm-labs shared)"
```

or headless re-execution:

```bash
../mnist-internals/.venv/bin/jupyter nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.kernel_name=lm-internals 01_how_word_vectors_learn_to_mean.ipynb
```

Blog posts are regenerated with `scripts/nb2post.py` at the repo root — same invocation pattern
as `labs/ml/mnist-internals/README.md` documents.
