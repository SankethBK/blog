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
| 2.2 | `02_a_language_model_without_attention.ipynb` | A language model without attention: char-RNN + BPTT by hand (grad-checked), sampled Shakespeare babble, hidden-state heatmaps, and the star plot — forward echo vs backward gradient both decaying with half-life ≈ 2.3 steps, with σ_max(W_hh) = 4.88 showing the net fighting the tanh gates and losing. | [lab-2.2](/posts/ml/labs/2026-10-27-lab-2-2-language-model-without-attention/) |
| 2.3 | `03_lstms_gates_as_memory_engineering.ipynb` | LSTM cell + BPTT by hand on a copy task with widening gaps. Two failed priors kept in the post (RNN survives G=60 by sculpting a slow blank-transport; a cold-started LSTM can't *learn* to open its belt at G=150). The levers measured: forget-bias +5 → acc 1.000 (blame half-life ≈38 steps vs 2.3; retention 0.96 vs 0.08 in h), curriculum = lottery at tiny scale; gate heatmaps show the conveyor belt plainly. | [lab-2.3](/posts/ml/labs/2026-10-27-lab-2-3-gates-as-memory-engineering/) |
| 2.4 | *(planned)* | Attention from raw tensors: build Q/K/V by hand on a 4-token toy, then a causal self-attention LM; head visualizations; RNN vs LSTM vs attention on the same long-range task. | — |
| 2.5+ | *(planned)* | minimal transformer LM, BPE tokenization, probing/interpretability; PyTorch on MPS once the NumPy ceiling is reached. | — |

## Layout

```
01_how_word_vectors_learn_to_mean.ipynb   lab 2.1 (executed, outputs saved inline)
02_a_language_model_without_attention.ipynb   lab 2.2 (executed, outputs saved inline)
03_lstms_gates_as_memory_engineering.ipynb  lab 2.3 (executed, outputs saved inline)
lm_lab/                                   microworld corpus generator + checkpoint bookkeeping
data/                                     tiny-shakespeare.txt (karpathy/char-rnn corpus; downloaded)
checkpoints/lab21|lab22|lab23/            .npz artifacts + manifest.json
figures/lab21|lab22|lab23/                exported PNGs (also embedded in the notebooks)
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
