"""Tiny checkpoint bookkeeping: .npz files plus a JSON manifest.
(Identical to the mnist-internals version — kept local so this project stands alone.)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np


def save_ckpt(ckpt_dir, name, step=None, metrics=None, **arrays) -> Path:
    ckpt_dir = Path(ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    path = ckpt_dir / f"{name}.npz"
    np.savez(path, **arrays)

    mpath = ckpt_dir / "manifest.json"
    entries = json.loads(mpath.read_text()) if mpath.exists() else []
    entries = [e for e in entries if e["name"] != name]
    entries.append(
        {
            "name": name,
            "step": step,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "metrics": metrics or {},
            "arrays": {k: list(v.shape) for k, v in arrays.items()},
        }
    )
    mpath.write_text(json.dumps(entries, indent=2))
    return path


def load_ckpt(path) -> dict:
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


def manifest(ckpt_dir):
    mpath = Path(ckpt_dir) / "manifest.json"
    if not mpath.exists():
        return []
    return json.loads(mpath.read_text())
