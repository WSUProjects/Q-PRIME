import sys

import pytest

from qprime import ahp


def test_weights_sum_to_one():
    A = [[1, 2, 3], [1 / 2, 1, 2], [1 / 3, 1 / 2, 1]]
    W = ahp.ahp_weights_from_matrix(A)
    assert abs(sum(W) - 1.0) < 1e-9


def test_paper_priority_matrix():
    """The 1-2-3 Saaty matrix used for the paper's AHP priority profiles
    yields weights ~ (0.54, 0.30, 0.16) with CR ~ 0.0079."""
    A = [[1, 2, 3], [1 / 2, 1, 2], [1 / 3, 1 / 2, 1]]
    W, lambda_max, CI, CR = ahp.ahp_weights_and_consistency(A)
    assert W[0] == pytest.approx(0.54, abs=0.01)
    assert W[1] == pytest.approx(0.30, abs=0.01)
    assert W[2] == pytest.approx(0.16, abs=0.01)
    assert CR == pytest.approx(0.0079, abs=0.002)
    assert CR < 0.10


def test_equal_matrix_gives_equal_weights():
    A = [[1.0] * 3 for _ in range(3)]
    W, _, _, CR = ahp.ahp_weights_and_consistency(A)
    for w in W:
        assert w == pytest.approx(1 / 3, abs=1e-9)
    assert CR == pytest.approx(0.0, abs=1e-9)


def test_matrix_from_judgements_reciprocal():
    A = ahp.matrix_from_judgements(2, 3, 2)
    assert A[1][0] == pytest.approx(0.5)
    assert A[2][0] == pytest.approx(1 / 3)
    ahp.validate_matrix(A)


def test_validate_rejects_bad_matrix():
    with pytest.raises(ValueError):
        ahp.validate_matrix([[1, 2], [0.5, 1]])
    with pytest.raises(ValueError):
        ahp.validate_matrix([[1, -2, 3], [1, 1, 1], [1, 1, 1]])
