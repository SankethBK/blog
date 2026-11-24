# LLM internals — lab series

Hands-on labs for the [ML notes](../../../content/posts/ml/), starting with one
causal attention head and building toward a small decoder and its inference loop.

| # | Notebook | Question | Post |
|---|---|---|---|
| 3.1 | [One head, content lookup](01_one_head_content_lookup.ipynb) | Can one head learn to retrieve a value from an earlier token? Compute one row by hand, train the head, and test it with prompt edits and uniform attention. | [Lab 3.1](../../../content/posts/ml/labs/2026-11-24-lab-3-1-one-head-content-lookup/index.md) |
| 3.2 | [One-block character decoder](02_tiny_decoder.ipynb) | Can preceding characters improve next-character predictions over a count bigram? | [Lab 3.2](../../../content/posts/ml/labs/2026-11-24-lab-3-2-tiny-decoder/index.md) |
| 3.3 | [Decode from one checkpoint](03_decoding_one_checkpoint.ipynb) | How do temperature and top-p change one prediction, and what happens when two continuations diverge? | [Lab 3.3](../../../content/posts/ml/labs/2026-11-24-lab-3-3-decoding/index.md) |
| 3.4 | [When can a decoder reuse its past?](04_kv_cache.ipynb) | When do old positions stay valid? | [Lab 3.4](../../../content/posts/ml/labs/2026-11-24-lab-3-4-kv-cache/index.md) |
| 3.5 | [How does text become GPT-2 token IDs?](05_byte_pair_encoding.ipynb) | How do learned byte merges change IDs? | [Lab 3.5](../../../content/posts/ml/labs/2026-11-24-lab-3-5-byte-pair-encoding/index.md) |
| 3.6 | [Can two attention heads fit in one projection?](06_multi_head_attention.ipynb) | Does packing heads preserve their outputs? | [Lab 3.6](../../../content/posts/ml/labs/2026-11-24-lab-3-6-multi-head-attention/index.md) |
| 3.7 | [Where do the parameters in GPT-2 go?](07_miniature_gpt.ipynb) | Where do the parameters and residual updates go? | [Lab 3.7](../../../content/posts/ml/labs/2026-11-24-lab-3-7-miniature-gpt/index.md) |
| 3.8 | [Can our decoder reproduce GPT-2 small?](08_gpt2_checkpoint.ipynb) | Do all 12 blocks and the logits agree? | [Lab 3.8](../../../content/posts/ml/labs/2026-11-24-lab-3-8-gpt2-checkpoint/index.md) |
| 3.9 | [What does one training update do?](09_dense_training.ipynb) | Can a dense model generalize beyond one batch? | [Lab 3.9](../../../content/posts/ml/labs/2026-11-24-lab-3-9-dense-training/index.md) |
| 3.10 | [How does a pretrained model adapt?](10_full_fine_tuning.ipynb) | What changes when every parameter can move? | [Lab 3.10](../../../content/posts/ml/labs/2026-11-24-lab-3-10-full-fine-tuning/index.md) |
| 3.11 | [Can a rank-four adapter learn the same task?](11_lora.ipynb) | How far can low-rank QKV updates go? | [Lab 3.11](../../../content/posts/ml/labs/2026-11-24-lab-3-11-lora/index.md) |
| 3.12 | [Which expert gets the token and the gradient?](12_mixture_of_experts.ipynb) | Which experts receive tokens and gradients? | [Lab 3.12](../../../content/posts/ml/labs/2026-11-24-lab-3-12-mixture-of-experts/index.md) |

The notebook has saved outputs. `figures/lab31/` contains the exported attention
plot, and `checkpoints/lab31/` contains the initial and trained `.npz` snapshots
and their JSON manifest. Lab 3.1 generates its lookup data from scratch. Lab 3.2 reuses the Tiny Shakespeare file from Lab 2.2 and downloads it on first use if needed. Its loss plot is in `figures/lab32/` and its trained weights, vocabulary, dimensions, and manifest are in `checkpoints/lab32/`.

Lab 3.3 loads the saved Lab 3.2 weights. Its temperature plot is in `figures/lab33/`, and its measured distributions, sample counts, and fork are in `checkpoints/lab33/`.

Labs 3.4–3.12 each have an executed notebook, a figure, and an NPZ artifact with a manifest under `figures/lab<number>/` and `checkpoints/lab<number>/`. Lab 3.4 uses the 3.2 weights. Labs 3.5 and 3.8 use the public GPT-2 tokenizer. Lab 3.8 also downloads the 523 MiB GPT-2 small checkpoint into ignored `data/gpt2/` on first use. The reference library and the PyTorch implementation run side by side on CPU.

Lab 3.9 trains the small Shakespeare base. Labs 3.10 and 3.11 compare full tuning and LoRA using the same base and adaptation data. Lab 3.12 branches from 3.9 to study routing independently. `llm_lab/gpt.py` contains the shared GPT architecture and `llm_lab/experiments.py` contains the batch, evaluation, and artifact helpers.

## Run it

From this directory, reuse the MNIST lab environment for CPU execution:

```bash
source ../mnist-internals/.venv/bin/activate
python -m pip install -r requirements.txt
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
