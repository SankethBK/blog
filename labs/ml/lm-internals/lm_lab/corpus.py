"""A microworld language whose grammar we control (Lab 2.1).

The point: every structural claim the lab makes about embeddings can be
checked against GROUND TRUTH that we placed there by hand.

Structure baked in:
  * two social tiers  : royalty (king, queen, ...) vs commoners (man, woman, ...)
  * a gender axis     : male words co-occur with he/his/him, female with she/her
  * professions       : gender-neutral co-occurrence by default; `profession_bias`
                        makes doctor/nurse (etc.) co-occur with one gender's
                        pronouns, for the "embeddings are mirrors" experiment
  * fruit             : a separate semantic island
  * function words    : the/a/in/on/... cluster as contextually uninformative

generate_corpus() returns a list of sentences, each a list of tokens.
"""

from __future__ import annotations

import numpy as np

ROYAL_M = ["king", "prince", "duke", "lord"]
ROYAL_F = ["queen", "princess", "duchess", "lady"]
COMMON_M = ["man", "boy", "father", "son"]
COMMON_F = ["woman", "girl", "mother", "daughter"]
PROF = ["doctor", "nurse", "teacher", "merchant", "sailor", "baker"]
FRUIT = ["apple", "orange", "banana", "plum", "peach", "pear"]

PERSONS_M = ROYAL_M + COMMON_M
PERSONS_F = ROYAL_F + COMMON_F
PERSONS = PERSONS_M + PERSONS_F
ENTITY = ROYAL_M + ROYAL_F + COMMON_M + COMMON_F + PROF + FRUIT

GENDER_OF = {w: "m" for w in PERSONS_M} | {w: "f" for w in PERSONS_F}
ROLE_OF = ({w: "royalty" for w in ROYAL_M + ROYAL_F}
           | {w: "commoner" for w in COMMON_M + COMMON_F}
           | {w: "profession" for w in PROF}
           | {w: "fruit" for w in FRUIT})
# distributional twin-classes: words that the microworld makes interchangeable everywhere
TIER_GENDER_OF = ({w: "royal_m" for w in ROYAL_M} | {w: "royal_f" for w in ROYAL_F}
                  | {w: "common_m" for w in COMMON_M} | {w: "common_f" for w in COMMON_F})
# male/female pairs sharing a tier, for analogy evaluation and the gender axis
GENDER_PAIRS = [("king", "queen"), ("prince", "princess"), ("duke", "duchess"), ("lord", "lady"),
                ("man", "woman"), ("boy", "girl"), ("father", "mother"), ("son", "daughter")]

PRONOUN = {"m": ("he", "his", "him"), "f": ("she", "her", "her")}


def generate_corpus(n_sentences: int = 12000, seed: int = 0,
                    profession_bias: dict[str, float] | None = None) -> list[list[str]]:
    """Generate the microworld corpus.

    profession_bias: optional {profession: P(the co-occurring pronoun is male)}.
    Default None -> 0.5 for every profession (gender-neutral contexts).
    """
    rng = np.random.default_rng(seed)
    bias = dict(profession_bias or {})
    sents: list[list[str]] = []

    def pick(templates):
        return templates[rng.integers(0, len(templates))]

    for _ in range(n_sentences):
        t = rng.random()
        if t < 0.14:                                   # royalty tier-contexts
            r = ROYAL_M + ROYAL_F
            r = r[rng.integers(0, len(r))]
            sents.append(pick([
                ["the", r, "rules", "the", "kingdom"],
                ["the", r, "sits", "on", "the", "throne"],
                ["the", r, "wears", "the", "crown"],
                ["the", r, "commands", "the", "court"],
                ["the", r, "guards", "the", "castle"],
            ]))
        elif t < 0.28:                                 # commoner tier-contexts
            c = COMMON_M + COMMON_F
            c = c[rng.integers(0, len(c))]
            sents.append(pick([
                ["the", c, "walks", "the", "road"],
                ["the", c, "works", "in", "the", "field"],
                ["the", c, "crosses", "the", "market"],
                ["the", c, "tends", "the", "garden"],
                ["the", c, "fishes", "by", "the", "river"],
            ]))
        elif t < 0.50:                                 # gender-bearing pronoun contexts
            p = PERSONS[rng.integers(0, len(PERSONS))]
            subj, poss, obj = PRONOUN[GENDER_OF[p]]
            sents.append(pick([
                ["the", p, "raises", poss, "voice"],
                ["the", p, "opens", poss, "book"],
                ["the", p, "carries", poss, "coat"],
                [subj, "greets", "the", p],
                ["the", p, "smiles", "at", obj],
            ]))
        elif t < 0.64:                                 # professions
            pr = PROF[rng.integers(0, len(PROF))]
            p = PERSONS[rng.integers(0, len(PERSONS))]
            p_male = bias.get(pr, 0.5)
            g = "m" if rng.random() < p_male else "f"
            subj, poss, obj = PRONOUN[g]
            tmpl = [
                ["the", pr, "visits", "the", p],
                ["the", p, "calls", "the", pr],
                ["the", pr, "packs", poss, "bag"],
                ["the", pr, "earns", poss, "wage"],
            ]
            if p_male != 0.5:   # biased world: pronoun-bearing templates fire more often
                tmpl += [["the", pr, "packs", poss, "bag"],
                         ["the", pr, "earns", poss, "wage"]]
            sents.append(pick(tmpl))
        elif t < 0.80:                                 # fruit island
            f = FRUIT[rng.integers(0, len(FRUIT))]
            p = PERSONS[rng.integers(0, len(PERSONS))]
            sents.append(pick([
                ["the", p, "eats", "the", f],
                ["the", f, "grows", "in", "the", "orchard"],
                ["the", p, "peels", "a", f],
                [f, "is", "sweet", "and", "ripe"],
            ]))
        else:                                          # bare social mixing (keeps tiers connected)
            i, j = rng.choice(len(PERSONS), 2, replace=False)
            a, b = PERSONS[i], PERSONS[j]
            sents.append(pick([
                ["the", a, "meets", "the", b],
                ["the", a, "sees", "the", b, "today"],
                ["the", a, "and", "the", b, "talk"],
            ]))
    return sents


def build_vocab(sents: list[list[str]]) -> tuple[dict[str, int], list[str], np.ndarray]:
    """word -> id, id -> word, term counts."""
    counts: dict[str, int] = {}
    for s in sents:
        for w in s:
            counts[w] = counts.get(w, 0) + 1
    vocab = sorted(counts)
    w2i = {w: i for i, w in enumerate(vocab)}
    freq = np.array([counts[w] for w in vocab], dtype=np.float64)
    return w2i, vocab, freq
