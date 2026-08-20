"""
The two statistics this project needs, and no library to get them.

Spearman rather than Pearson because the undetermined ratio is a bounded,
right-skewed rate over 29 states and one Alaska is enough to invent a
Pearson correlation out of nothing. Rank correlation asks the weaker
question -- do states that certify more deaths under coroners tend to
rank higher -- which is the only question 29 points can answer.

The p-value is a permutation test, not a table lookup, because with n=29
the asymptotic approximation is doing more work than the data. Shuffling
the labels 20,000 times and counting how often chance beats the observed
correlation needs no distributional assumption and is the same test
whether or not the data are normal.

Seeded, so the number in the README is the number you get.
"""

from __future__ import annotations

import random


def rank(values: list[float]) -> list[float]:
    """Ranks, ties averaged. Ties matter here: elected_share is 0.0 for
    every fully-medical-examiner state, so a quarter of the column is one
    tie group."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def spearman(x: list[float], y: list[float]) -> float:
    rx, ry = rank(x), rank(y)
    n = len(x)
    if n < 3:
        return 0.0
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else 0.0


def permutation_p(x: list[float], y: list[float], rho: float,
                  trials: int = 20000, seed: int = 7) -> float:
    """Two-sided: how often does shuffling produce a correlation at least
    this strong in either direction. The +1s keep it from ever returning
    exactly zero, which would be a claim the test cannot make."""
    rng = random.Random(seed)
    y = list(y)
    hits = 0
    for _ in range(trials):
        rng.shuffle(y)
        if abs(spearman(x, y)) >= abs(rho):
            hits += 1
    return (hits + 1) / (trials + 1)


def correlate(x: list[float], y: list[float]) -> dict:
    """Canonicalises pair order first. Spearman does not care what order
    the states arrive in, but a seeded shuffle does, so without this the
    same data reached through two different ORDER BY clauses reports two
    different p-values. A published number that moves when a query is
    rewritten is not a published number."""
    pairs = sorted(zip(x, y))
    x = [p[0] for p in pairs]
    y = [p[1] for p in pairs]
    rho = spearman(x, y)
    return {"n": len(x), "rho": round(rho, 3),
            "p": round(permutation_p(x, y, rho), 4)}
