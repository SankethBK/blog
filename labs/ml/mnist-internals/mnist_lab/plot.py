"""Matplotlib helpers for the MNIST labs.

All image grids default to showing a (n, 784) array as 28x28 digits.
`show_templates` is the workhorse: it shows signed weight rows with a
diverging colormap, centred and scaled per-panel so each template is
individually readable, with the same shared scale annotated.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

IMG = (28, 28)


def _as_images(vecs: np.ndarray) -> np.ndarray:
    v = np.asarray(vecs)
    if v.ndim == 1:
        v = v[None, :]
    return v.reshape(-1, *IMG)


def show_grid(images, titles=None, ncols=10, suptitle=None, cmap="gray", figsize=None):
    imgs = _as_images(images)
    n = len(imgs)
    ncols = min(ncols, n)
    nrows = int(np.ceil(n / ncols))
    figsize = figsize or (1.6 * ncols, 1.9 * nrows)
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, squeeze=False)
    for i, ax in enumerate(axes.flat):
        ax.axis("off")
        if i >= n:
            continue
        ax.imshow(imgs[i], cmap=cmap, vmin=0, vmax=1)
        if titles is not None:
            ax.set_title(str(titles[i]), fontsize=9)
    if suptitle:
        fig.suptitle(suptitle)
    fig.tight_layout()
    return fig


def show_templates(W, row_labels=None, suptitle=None, cmap="RdBu", per_row_scale=True):
    """Show each row of W as a 28x28 image with a diverging colormap.

    Red = negative weight (a pixel of ink here votes AGAINST the class),
    blue = positive weight (votes FOR the class). By default each row is
    scaled to its own max magnitude so small rows stay readable.
    """
    W = np.atleast_2d(np.asarray(W))
    imgs = W.reshape(-1, *IMG)
    n = len(imgs)
    fig, axes = plt.subplots(1, n, figsize=(1.9 * n, 2.2), squeeze=False)
    lim = np.abs(W).max() if not per_row_scale else None
    for i, ax in enumerate(axes.flat):
        this = np.abs(imgs[i]).max() if per_row_scale else lim
        ax.imshow(imgs[i], cmap=cmap, vmin=-this, vmax=this)
        label = row_labels[i] if row_labels is not None else str(i)
        ax.set_title(str(label), fontsize=10)
        ax.set_xticks([])
        ax.set_yticks([])
    if suptitle:
        fig.suptitle(suptitle)
    fig.tight_layout()
    return fig


def signed_heatmap(vec, ax=None, title=None, cmap="RdBu_r", shape=IMG):
    """One signed 28x28 map (a template, a contribution map, ...) with colorbar."""
    if ax is None:
        _, ax = plt.subplots(figsize=(2.6, 2.6))
    m = np.asarray(vec).reshape(shape)
    lim = np.abs(m).max()
    lim = lim if lim > 0 else 1.0
    im = ax.imshow(m, cmap=cmap, vmin=-lim, vmax=lim)
    ax.set_xticks([])
    ax.set_yticks([])
    if title:
        ax.set_title(title, fontsize=9)
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    return ax


def show_confusion(cm, classes, ax=None, title=None):
    if ax is None:
        _, ax = plt.subplots(figsize=(5.5, 5))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(classes)), classes)
    ax.set_yticks(range(len(classes)), classes)
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    n = cm.sum(1, keepdims=True)
    frac = np.divide(cm, np.maximum(n, 1))
    thresh = cm.max() / 2 if cm.max() > 0 else 0
    for i in range(len(classes)):
        for j in range(len(classes)):
            ax.text(j, i, f"{cm[i, j]}\n({frac[i, j]:.0%})", ha="center", va="center",
                    fontsize=7, color="white" if cm[i, j] > thresh else "black")
    if title:
        ax.set_title(title)
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    return ax


def save_fig(fig, path, dpi=140):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    print(f"saved figure -> {path}")
