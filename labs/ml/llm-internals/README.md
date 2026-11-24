# LLM internals — lab series

Hands-on labs for the [ML notes](../../../content/posts/ml/), starting with one
causal attention head and building toward a small decoder and its inference loop.

| # | Notebook | Question | Post |
|---|---|---|---|
| 3.1 | [One head, content lookup](01_one_head_content_lookup.ipynb) | Can one head learn to retrieve a value from an earlier token? Compute one row by hand, train the head, and test it with prompt edits and uniform attention. | [Lab 3.1](../../../content/posts/ml/labs/2026-11-24-lab-3-1-one-head-content-lookup/index.md) |
| 3.2 | [One-block character decoder](02_tiny_decoder.ipynb) | Can preceding characters improve next-character predictions over a count bigram? | [Lab 3.2](../../../content/posts/ml/labs/2026-11-24-lab-3-2-tiny-decoder/index.md) |
| 3.3 | [Decode from one checkpoint](03_decoding_one_checkpoint.ipynb) | How do temperature and top-p change one prediction, and what happens when two continuations diverge? | [Lab 3.3](../../../content/posts/ml/labs/2026-11-24-lab-3-3-decoding/index.md) |

The notebook has saved outputs. `figures/lab31/` contains the exported attention
plot, and `checkpoints/lab31/` contains the initial and trained `.npz` snapshots
and their JSON manifest. Lab 3.1 generates its lookup data from scratch. Lab 3.2 reuses the Tiny Shakespeare file from Lab 2.2 and downloads it on first use if needed. Its loss plot is in `figures/lab32/` and its trained weights, vocabulary, dimensions, and manifest are in `checkpoints/lab32/`.

Lab 3.3 loads the saved Lab 3.2 weights. Its temperature plot is in `figures/lab33/`, and its measured distributions, sample counts, and fork are in `checkpoints/lab33/`.

## Run it

From this directory, reuse the MNIST lab environment for CPU execution:

```bash
source ../mnist-internals/.venv/bin/activate
jupyter lab
```

Select the environment's Python kernel. For a fresh environment, create a venv
and install `requirements.txt`. To run the notebook headlessly:

```bash
python -m nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.kernel_name=python3 01_one_head_content_lookup.ipynb
```

## Generate the blog post

From the repository root with the environment active:

```bash
python scripts/nb2post.py labs/ml/llm-internals/01_one_head_content_lookup.ipynb \
    --category ml/labs --fm-category ml --slug 2026-11-24-lab-3-1-one-head-content-lookup \
    --title "Lab 3.1: Can One Attention Head Learn to Look Up an Answer?" \
    --date 2026-11-24 --tags ml,lab,attention,transformer,llm
```

For Lab 3.2, run:

```bash
python scripts/nb2post.py labs/ml/llm-internals/02_tiny_decoder.ipynb \
    --category ml/labs --fm-category ml --slug 2026-11-24-lab-3-2-tiny-decoder \
    --title "Lab 3.2 — From one attention head to a tiny decoder" \
    --date 2026-11-24 --tags ml,lab,attention,transformer,llm
```

For Lab 3.3, run:

```bash
python scripts/nb2post.py labs/ml/llm-internals/03_decoding_one_checkpoint.ipynb \
    --category ml/labs --fm-category ml --slug 2026-11-24-lab-3-3-decoding \
    --title "Lab 3.3 — How does one model produce different continuations?" \
    --date 2026-11-24 --tags ml,lab,decoding,transformer,llm
```

The converter overwrites the post's Markdown. If you've added handwritten notes,
export to a temporary slug and merge the changes into the annotated post.
