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

import math
import random


# ---------------------------------------------------------------------
# Exact Poisson confidence intervals.
#
# These exist because a ranked table of 20 states invites the reader to
# treat position as meaning, and at these counts it mostly does not.
# Fifteen of the twenty states have intervals covering the national rate:
# their order is noise driven by numerators between 11 and 34 deaths.
# Publishing the rank without the interval is publishing a finding the
# data does not contain.
#
# Garwood/exact rather than normal-approximation, because a normal
# interval on 11 events is wrong in the direction that flatters the
# result, and it cannot represent a zero count at all -- Montana has 0
# undetermined against 426 ruled suicide, and its honest interval runs
# from 0 to 0.87, which comfortably includes the national 0.62.
#
# No scipy: the only hard dependency here is httpx, so the incomplete
# gamma function is implemented directly.
# ---------------------------------------------------------------------

def _gammainc_p(s: float, x: float, iters: int = 500) -> float:
    """Regularized lower incomplete gamma P(s, x)."""
    if x <= 0 or s <= 0:
        return 0.0
    if x < s + 1:  # series expansion
        ap, total, term = s, 1.0 / s, 1.0 / s
        for _ in range(iters):
            ap += 1
            term *= x / ap
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
        return total * math.exp(-x + s * math.log(x) - math.lgamma(s))
    # continued fraction for the upper tail, then complement
    tiny = 1e-300
    b, c, d = x + 1 - s, 1 / tiny, 1 / (x + 1 - s)
    h = d
    for i in range(1, iters):
        an = -i * (i - s)
        b += 2
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15:
            break
    return 1 - math.exp(-x + s * math.log(x) - math.lgamma(s)) * h


def _chi2_ppf(p: float, df: int) -> float:
    if df <= 0:
        return 0.0
    lo, hi = 0.0, max(1000.0, df * 10.0)
    while _gammainc_p(df / 2, hi / 2) < p:
        hi *= 2
    for _ in range(200):
        mid = (lo + hi) / 2
        if _gammainc_p(df / 2, mid / 2) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def poisson_ci(k: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact two-sided interval for a count. k=0 gives a lower bound of 0
    and a real upper bound, which is the whole point of using this."""
    lo = 0.0 if k <= 0 else _chi2_ppf(alpha / 2, 2 * k) / 2
    return lo, _chi2_ppf(1 - alpha / 2, 2 * (k + 1)) / 2


def rate_ci(k: int, denom: int, per: int = 100) -> tuple[float, float] | None:
    """Interval on k/denom, scaled. The denominator is treated as a fixed
    offset: X70 counts are in the thousands and never suppressed, so
    essentially all the uncertainty lives in the rare numerator."""
    if not denom:
        return None
    lo, hi = poisson_ci(k or 0)
    return lo / denom * per, hi / denom * per


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
