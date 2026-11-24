"""Reproducible CPU setup and artifact bookkeeping for the LLM labs."""
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
from IPython.display import Image, display
from torch.nn import functional as F

from .gpt import GPT

sys.path.insert(0, str(Path("../lm-internals").resolve()))
from lm_lab import load_ckpt, save_ckpt


def record(lab, name, **arrays):
    return save_ckpt(Path("checkpoints") / f"lab{lab}", name,
                     **{key: np.asarray(value) for key, value in arrays.items()})


def show(lab, name):
    path = Path("figures") / f"lab{lab}" / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=135)
    plt.close()
    display(Image(filename=str(path)))


def corpus():
    path = Path("../lm-internals/data/tiny-shakespeare.txt")
    if not path.exists():
        from urllib.request import urlopen
        with urlopen("https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt", timeout=60) as response:
            text = response.read().decode("utf8")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf8")
    return path.read_text(encoding="utf8")


def windows(ids, starts, length=32):
    rows = ids[starts[:, None] + torch.arange(length + 1)]
    return rows[:, :-1], rows[:, 1:]


def loss(model, batch):
    x, y = batch
    return F.cross_entropy(model(x).flatten(0, 1), y.flatten())


def loads_base():
    saved = load_ckpt("checkpoints/lab39/dense_base.npz")
    model = GPT(len(saved["alphabet"]), 32, 32, 4, 2)
    model.load_state_dict({k: torch.from_numpy(saved[k]) for k in model.state_dict()})
    return model, saved["alphabet"].tolist()


def adaptation(alphabet):
    """Same uppercase dialogue windows and batch schedule for full tuning and LoRA."""
    text = corpus()
    start = 8 * len(text) // 10
    split = 9 * len(text) // 10
    index = {ch: i for i, ch in enumerate(alphabet)}
    def encode(part):
        return torch.tensor([index[ch] for ch in part.upper()])
    train, test = encode(text[start:split]), encode(text[split:])
    rng = torch.Generator().manual_seed(310)
    schedule = torch.randint(len(train)-32, (120, 32), generator=rng)
    held = windows(test, torch.linspace(0, len(test)-33, 128).long())
    return train, schedule, held


def fit_adaptation(model, alphabet, lr):
    train, schedule, held = adaptation(alphabet)
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=lr)
    scores = []
    for step, starts in enumerate(schedule):
        if step % 20 == 0:
            with torch.no_grad():
                scores.append(loss(model, held).item())
        opt.zero_grad()
        loss(model, windows(train, starts)).backward()
        opt.step()
    with torch.no_grad():
        scores.append(loss(model, held).item())
    state_bytes = sum(t.numel()*t.element_size() for state in opt.state.values()
                      for t in state.values() if torch.is_tensor(t))
    return scores, sum(p.numel() for p in params), state_bytes
