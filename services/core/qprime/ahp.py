"""Analytic Hierarchy Process (AHP) utilities.

Q-PRIME derives the criteria weights (temporal QoC, content QoC, privacy)
either directly from user-supplied values or from a pairwise comparison
matrix using Saaty's AHP method. This module is a cleaned-up port of the
functions used for the experiments in the paper, including
the consistency-ratio computation.
"""

from typing import List, Sequence, Tuple

# Saaty's random consistency index, indexed by matrix order n.
RI_TABLE = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24}

CRITERIA = ("temporal", "spatial", "privacy")


def ahp_weights_from_matrix(A: Sequence[Sequence[float]]) -> List[float]:
    """Compute AHP priority weights from a pairwise comparison matrix ``A``.

    Uses the column-normalisation / row-average approximation of the
    principal eigenvector, as in the paper's implementation.
    """
    n = len(A)
    col_sums = [sum(A[i][j] for i in range(n)) for j in range(n)]
    norm = [
        [(A[i][j] / col_sums[j]) if col_sums[j] != 0 else 0.0 for j in range(n)]
        for i in range(n)
    ]
    weights = [sum(norm[i]) / n for i in range(n)]
    total = sum(weights) if sum(weights) > 0 else 1.0
    return [w / total for w in weights]


def ahp_weights_and_consistency(
    A: Sequence[Sequence[float]],
) -> Tuple[List[float], float, float, float]:
    """Return ``(weights, lambda_max, CI, CR)`` for pairwise matrix ``A``.

    ``CR < 0.10`` is conventionally considered acceptably consistent.
    """
    W = ahp_weights_from_matrix(A)
    n = len(A)
    Aw = [sum(A[i][j] * W[j] for j in range(n)) for i in range(n)]
    ratios = [(Aw[i] / W[i]) if W[i] != 0 else 0.0 for i in range(n)]
    lambda_max = sum(ratios) / n if n > 0 else 0.0
    CI = (lambda_max - n) / (n - 1) if n > 1 else 0.0
    RI = RI_TABLE.get(n, 1.12)
    CR = CI / RI if RI != 0 else 0.0
    return W, lambda_max, CI, CR


def matrix_from_judgements(ts: float, tp: float, sp: float) -> List[List[float]]:
    """Build a 3x3 pairwise matrix from three Saaty-scale judgements.

    Parameters mean "how much more important is X than Y" (values in
    1/9 .. 9):

    - ``ts``: temporal vs spatial (content)
    - ``tp``: temporal vs privacy
    - ``sp``: spatial (content) vs privacy
    """
    for v in (ts, tp, sp):
        if v <= 0:
            raise ValueError("pairwise judgements must be positive")
    return [
        [1.0, ts, tp],
        [1.0 / ts, 1.0, sp],
        [1.0 / tp, 1.0 / sp, 1.0],
    ]


def validate_matrix(A: Sequence[Sequence[float]]) -> None:
    """Raise ``ValueError`` if ``A`` is not a positive reciprocal 3x3 matrix."""
    if len(A) != 3 or any(len(row) != 3 for row in A):
        raise ValueError("AHP matrix must be 3x3 (temporal, spatial, privacy)")
    for i in range(3):
        for j in range(3):
            v = float(A[i][j])
            if v <= 0:
                raise ValueError("AHP matrix entries must be positive")
            if i == j and abs(v - 1.0) > 1e-9:
                raise ValueError("AHP matrix diagonal must be 1")
