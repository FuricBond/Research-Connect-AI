"""
Unit Tests for Phase 2.4M Inter-Annotator Agreement Calculators.
"""
from __future__ import annotations

import pytest

from app.evaluation.agreement import (
    calculate_discipline_agreement,
    calculate_raw_agreement,
    cohens_kappa,
    compute_confusion_matrix,
    fleiss_kappa,
)


class TestInterAnnotatorAgreement:
    """Test suite verifying mathematical correctness of Cohen's and Fleiss' Kappa."""

    def test_perfect_agreement(self) -> None:
        """Verify kappa == 1.0 when raters agree completely."""
        r1 = [3, 2, 0, 1, 3, 2, 0, 1]
        r2 = [3, 2, 0, 1, 3, 2, 0, 1]

        assert calculate_raw_agreement(r1, r2) == 1.0
        assert cohens_kappa(r1, r2) == 1.0

    def test_chance_or_zero_agreement(self) -> None:
        """Verify kappa handles orthogonal or non-correlated judgments."""
        r1 = [3, 3, 0, 0]
        r2 = [0, 0, 3, 3]

        assert calculate_raw_agreement(r1, r2) == 0.0
        assert cohens_kappa(r1, r2) <= 0.0

    def test_substantial_agreement_realistic(self) -> None:
        """Verify kappa on realistic slight disagreement."""
        r1 = [3, 3, 2, 1, 0, 3, 2, 2, 0, 1]
        r2 = [3, 2, 2, 1, 0, 3, 2, 1, 0, 1]  # 2 minor differences

        raw = calculate_raw_agreement(r1, r2)
        kappa = cohens_kappa(r1, r2)
        assert raw == 0.80
        assert 0.70 <= kappa <= 0.85

    def test_fleiss_kappa_calculation(self) -> None:
        """Verify Fleiss' Kappa with 3 raters evaluating 5 subjects into 3 categories."""
        # 5 subjects, categories: [0, 1, 2]
        # 3 raters per subject
        matrix = [
            [0, 0, 3],  # all 3 chose category 2
            [0, 3, 0],  # all 3 chose category 1
            [3, 0, 0],  # all 3 chose category 0
            [0, 1, 2],  # 1 chose cat 1, 2 chose cat 2
            [0, 0, 3],  # all 3 chose category 2
        ]
        fk = fleiss_kappa(matrix)
        assert fk > 0.70

    def test_confusion_matrix_and_discipline_breakdown(self) -> None:
        """Verify confusion matrix generation and discipline-level grouping."""
        r1 = [3, 2, 1, 0]
        r2 = [3, 2, 0, 0]

        cm = compute_confusion_matrix(r1, r2)
        assert cm["raw_agreement"] == 0.75
        assert cm["matrix"][1][0] == 1

        disc_ratings = {
            "Computer Science": [(3, 3), (2, 2), (1, 1), (0, 0)],
            "Medicine": [(3, 3), (2, 1), (1, 1), (0, 0)],
        }
        disc_rep = calculate_discipline_agreement(disc_ratings)
        assert disc_rep["Computer Science"]["cohens_kappa"] == 1.0
        assert disc_rep["Medicine"]["cohens_kappa"] < 1.0
