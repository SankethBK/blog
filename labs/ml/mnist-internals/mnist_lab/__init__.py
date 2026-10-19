"""Helpers for the MNIST internals lab series.

Deliberately boring infrastructure lives here (downloading/parsing MNIST,
matplotlib styling, checkpoint bookkeeping) so that the notebooks can spend
their code cells on the actual subject: the model and its weights.
"""

from .data import load_mnist, filter_classes, one_hot
from .plot import show_grid, show_templates, show_confusion, save_fig
from .checkpoints import save_ckpt, load_ckpt, manifest

__all__ = [
    "load_mnist",
    "filter_classes",
    "one_hot",
    "show_grid",
    "show_templates",
    "show_confusion",
    "save_fig",
    "save_ckpt",
    "load_ckpt",
    "manifest",
]
