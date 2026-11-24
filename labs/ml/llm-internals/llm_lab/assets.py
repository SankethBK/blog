"""Fetch the two public GPT-2 files used in the tokenizer and parity labs."""
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen
from shutil import copyfileobj

REVISION = "607a30d783dfa663caf39e06633721c8d4cfcd7e"


def asset(name):
    if name not in {"tokenizer.json", "model.safetensors"}:
        raise ValueError(name)
    path = Path("data/gpt2") / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/openai-community/gpt2/resolve/{REVISION}/{name}"
        with urlopen(url, timeout=90) as src, NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            try:
                copyfileobj(src, tmp)
                tmp.flush()
                Path(tmp.name).replace(path)
            finally:
                Path(tmp.name).unlink(missing_ok=True)
    return path
