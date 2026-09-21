---
title:  "Lab: Word2Vec's Static Embedding Problem"
date:   2026-09-21T00:00:00+05:30
categories: ["ml"]
tags: ["ml","word2vec","embeddings","lab"]
---

# Lab: Word2Vec's Static Embedding Problem

Word2Vec and GloVe produce **one vector per word**. That is their strength — compact, reusable — and their fundamental weakness: a word with multiple meanings is forced into a single point in space.

This notebook uses tiny synthetic vectors to show the problem before we move to contextual models.

```python
import numpy as np

def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

# Hand-designed 4-dim vectors. 'bank' is forced to sit between two meanings.
embeddings = {
    "river":  np.array([1.0, 0.0, 0.0, 0.0]),
    "stream": np.array([0.9, 0.1, 0.0, 0.0]),
    "money":  np.array([0.0, 1.0, 0.0, 0.0]),
    "cash":   np.array([0.1, 0.9, 0.0, 0.0]),
    "bank":   np.array([0.5, 0.5, 0.0, 0.0]),  # one static compromise
    "cat":    np.array([0.0, 0.0, 1.0, 0.1]),
    "dog":    np.array([0.0, 0.0, 0.9, 0.2]),
}
```

## 1. Polysemy: one vector cannot be in two places at once

In a real corpus, `bank` appears near `river` *and* near `money`. Word2Vec averages the pressure and lands somewhere in between.

```python
print("Similarity of 'bank' to other words:")
for w in ["river", "stream", "money", "cash", "cat", "dog"]:
    print(f"  {w:8s}: {cosine(embeddings['bank'], embeddings[w]):.3f}")
```

    Similarity of 'bank' to other words:
      river   : 0.707
      stream  : 0.781
      money   : 0.707
      cash    : 0.781
      cat     : 0.000
      dog     : 0.000


`bank` ends up roughly similar to *both* river-words and money-words, but it is not a clean member of either cluster. More importantly, downstream layers receive the exact same vector for `bank` regardless of whether the sentence is about a river or a bank account.

## 2. Antonyms can look like synonyms

Words that appear in the *same contexts* get pushed together, even if their meanings are opposite. `hot` and `cold` often appear in the same slot ("it is ___ today"), so a static embedding can place them closer than intuition expects.

```python
# Synthetic extreme: two words share a context slot but are opposites.
# They point in nearly the same direction, while 'river' points elsewhere.
embeddings["hot"]  = np.array([0.20, 0.60, 0.05, 0.00])
embeddings["cold"] = np.array([0.18, 0.55, -0.03, 0.00])

print(f"cosine(hot, cold)  = {cosine(embeddings['hot'], embeddings['cold']):.3f}")
print(f"cosine(hot, river) = {cosine(embeddings['hot'], embeddings['river']):.3f}")

```

    cosine(hot, cold)  = 0.991
    cosine(hot, river) = 0.315


`hot` and `cold` are closer to each other than `hot` is to `river`, even though `hot` and `river` are not opposites. The model only knows usage patterns, not semantics.

## Takeaway

Static embeddings are a useful first compression of distributional similarity, but they cannot represent context-dependent meaning. The next step — attention and Transformers — replaces the single vector with a representation that changes based on neighboring tokens.
