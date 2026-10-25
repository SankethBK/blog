#!/usr/bin/env python3
"""
Convert an executed Jupyter notebook into a Hugo page bundle.

Usage:
    python scripts/nb2post.py notebooks/ml/my-lab.ipynb \
        --slug 2026-09-20-lab-my-lab \
        --title "My Lab Title" \
        --tags "ml","word2vec","embeddings"

Requirements:
    pip install jupyter nbconvert

What it does:
    1. Runs `jupyter nbconvert --to markdown --no-prompt` on the notebook.
    2. Creates a Hugo page bundle at content/posts/<category>/<slug>/.
    3. Moves generated image assets into the bundle.
    4. Prepends frontmatter to index.md.
"""

import argparse
import datetime
import pathlib
import re
import shutil
import subprocess
import sys


def require_nbconvert():
    try:
        subprocess.run(
            [sys.executable, "-m", "nbconvert", "--version"],
            check=True,
            capture_output=True,
        )
    except Exception:
        print("Error: nbconvert not found for this Python interpreter.")
        print("Install it in your environment:  pip install jupyter nbconvert")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Convert an executed Jupyter notebook to a Hugo page bundle."
    )
    parser.add_argument("notebook", type=pathlib.Path, help="Path to .ipynb file")
    parser.add_argument("--slug", required=True, help="Directory name for the bundle")
    parser.add_argument("--title", required=True, help="Post title")
    parser.add_argument("--category", default="ml", help="Hugo posts subfolder")
    parser.add_argument(
        "--date",
        default=datetime.datetime.now().strftime("%Y-%m-%d"),
        help="Publish date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--tags",
        default="",
        help='Comma-separated tags, e.g. "ml,word2vec"',
    )
    parser.add_argument(
        "--fm-category",
        default=None,
        help="Category to write in frontmatter (defaults to --category). Use when the "
        "directory nesting differs from the taxonomy, e.g. --category ml/labs --fm-category ml",
    )
    args = parser.parse_args()

    require_nbconvert()

    if not args.notebook.exists():
        print(f"Notebook not found: {args.notebook}")
        sys.exit(1)

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    bundle_dir = repo_root / "content" / "posts" / args.category / args.slug
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # nbconvert writes the .md and a <stem>_files/ folder next to the output.
    tmp_md = bundle_dir / f"{args.notebook.stem}.md"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "nbconvert",
            "--to",
            "markdown",
            "--no-prompt",
            str(args.notebook),
            "--output",
            str(tmp_md),
        ],
        check=True,
    )

    # Move any generated image folder into the bundle so relative links resolve.
    files_dir = args.notebook.parent / f"{args.notebook.stem}_files"
    target_files = bundle_dir / f"{args.notebook.stem}_files"
    if files_dir.exists():
        if target_files.exists():
            shutil.rmtree(target_files)
        shutil.move(files_dir, target_files)

    md_text = tmp_md.read_text()

    # nbconvert writes image links as *absolute* paths when --output is absolute
    # (they point into the bundle dir), which Hugo then serves verbatim as
    # /Users/... . Strip the bundle prefix so links are bundle-relative.
    md_text = md_text.replace(f"{bundle_dir}/", "")

    # Jupyter HTML image tags can point to files relative to the notebook
    # (for example, ../../../assets/images/diagram.png). Those paths are not
    # valid relative to the generated page bundle, so copy local image assets
    # into the bundle and make the references bundle-relative.
    image_src_pattern = re.compile(r'(<img\b[^>]*?\bsrc=["\'])([^"\']+)(["\'])', re.IGNORECASE)

    def bundle_local_image(match):
        src = match.group(2)
        if "://" in src or src.startswith(("/", "#", "data:")):
            return match.group(0)

        source_image = (args.notebook.parent / src).resolve()
        if not source_image.is_file():
            return match.group(0)

        target_image = bundle_dir / source_image.name
        if source_image != target_image.resolve():
            shutil.copy2(source_image, target_image)
        return f"{match.group(1)}{source_image.name}{match.group(3)}"

    md_text = image_src_pattern.sub(bundle_local_image, md_text)

    # nbconvert markdown links to images like: ![png](my-lab_4_1.png)
    # Those paths are now relative to the markdown file, so they stay valid
    # inside the bundle.

    tag_list = [f'"{t.strip()}"' for t in args.tags.split(",") if t.strip()]
    tags_line = ",".join(tag_list) if tag_list else ""

    fm_category = args.fm_category or args.category
    frontmatter = f"""---
title:  "{args.title}"
date:   {args.date}T00:00:00+05:30
categories: ["{fm_category}"]
tags: [{tags_line}]
---

"""

    index_md = bundle_dir / "index.md"
    index_md.write_text(frontmatter + md_text)
    tmp_md.unlink(missing_ok=True)

    print(f"Created page bundle: {bundle_dir}")
    print(f"Index: {index_md}")


if __name__ == "__main__":
    main()
