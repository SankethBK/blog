"""Download and parse the original MNIST IDX files (no torchvision needed).

The IDX format is LeCun's own container from the 90s: a 4-byte magic number
that encodes the dtype and the number of dimensions, big-endian dimension
sizes, then raw bytes. Parsing it ourselves is three lines of struct +
numpy and demystifies where the data actually comes from.

Mirror used: the ossci-datasets S3 bucket (same one torchvision uses).
"""

from __future__ import annotations

import gzip
import struct
import urllib.request
from pathlib import Path

import numpy as np

BASE_URL = "https://ossci-datasets.s3.amazonaws.com/mnist"
FILES = {
    "train_images": "train-images-idx3-ubyte.gz",
    "train_labels": "train-labels-idx1-ubyte.gz",
    "test_images": "t10k-images-idx3-ubyte.gz",
    "test_labels": "t10k-labels-idx1-ubyte.gz",
}

_DTYPES = {0x08: np.uint8, 0x09: np.int8, 0x0B: ">i2", 0x0C: ">i4", 0x0D: ">f4", 0x0E: ">f8"}


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url} -> {dest}")
    urllib.request.urlretrieve(url, dest)


def _read_idx(path: Path) -> np.ndarray:
    """Parse an IDX file (possibly gzipped) into an ndarray."""
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    zero, zero, dtype_code, n_dims = struct.unpack(">BBBB", raw[:4])
    assert zero == 0 and zero == 0, f"bad magic in {path}"
    dims = struct.unpack(f">{n_dims}I", raw[4 : 4 + 4 * n_dims])
    body = raw[4 + 4 * n_dims :]
    arr = np.frombuffer(body, dtype=np.dtype(_DTYPES[dtype_code]))
    return arr.reshape(dims)


def _ensure(root: Path) -> dict[str, Path]:
    paths = {}
    for key, fname in FILES.items():
        p = root / fname
        if not p.exists():
            _download(f"{BASE_URL}/{fname}", p)
        paths[key] = p
    return paths


def load_mnist(data_dir: str | Path = "data", normalize: bool = True):
    """Return (x_train, y_train, x_test, y_test).

    x_* : float32 arrays of shape (n, 784), pixels scaled to [0, 1]
          (or [0, 255] if normalize=False).
    y_* : int64 arrays of shape (n,) with the digit label.
    """
    root = Path(data_dir)
    files = _ensure(root)

    x_train = _read_idx(files["train_images"]).reshape(60_000, -1)
    x_test = _read_idx(files["test_images"]).reshape(10_000, -1)
    y_train = _read_idx(files["train_labels"]).astype(np.int64)
    y_test = _read_idx(files["test_labels"]).astype(np.int64)

    x_train = x_train.astype(np.float32)
    x_test = x_test.astype(np.float32)
    if normalize:
        x_train /= 255.0
        x_test /= 255.0
    return x_train, y_train, x_test, y_test


def filter_classes(x, y, classes):
    """Keep only examples whose label is in `classes`, and relabel them 0..k-1.

    Returns (x_sub, y_sub_relabeled, classes) so callers always know the
    old-label -> new-row mapping.
    """
    classes = list(classes)
    mask = np.isin(y, classes)
    lut = {c: i for i, c in enumerate(classes)}
    return x[mask], np.array([lut[v] for v in y[mask]], dtype=np.int64), classes


def one_hot(y: np.ndarray, n_classes: int) -> np.ndarray:
    out = np.zeros((y.shape[0], n_classes), dtype=np.float64)
    out[np.arange(y.shape[0]), y] = 1.0
    return out
