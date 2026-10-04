"""
Fix 7/9 — wall-clock performance budgets run on their own.

The budget tests time code in milliseconds and fail under CPU contention, so they carry the
`perf` marker, the default run leaves them out (`addopts = -m "not perf"`), and `pytest -m perf`
runs them. Their budgets are unchanged; this only guards that the marker stays where it is.
"""
from __future__ import annotations

import configparser
import importlib
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]

PERF_TESTS = [
    ("tests.test_recommendation_ranker", "TestRankingPerformanceMicroBenchmark.test_ranking_execution_budget"),
    ("tests.test_diversity_novelty", "TestDiversityPerformanceScaling.test_reranking_execution_time"),
    ("tests.test_phase3_9_hardening", "test_performance_benchmarks_zero_n_plus_one"),
    ("tests.test_personalization_calibration", "test_performance_and_scaling_benchmarks"),
    ("tests.test_personalization_governance", "test_performance_and_scaling_benchmarks"),
    ("tests.test_risk_evidence_extraction", "TestDeterminismAndPerformance.test_batch_performance_zero_queries"),
    ("tests.test_personalization_quality", "test_scaling_benchmarks"),
    ("tests.test_suspicious_graph_intelligence", "TestGraphPerformanceAndScaling.test_graph_batch_scaling_performance"),
]


def test_the_default_run_excludes_perf_and_the_marker_is_registered():
    ini = configparser.ConfigParser()
    ini.read(BACKEND / "pytest.ini", encoding="utf-8")
    assert ini["pytest"]["addopts"].strip() == '-m "not perf"'
    markers = [line.split(":", 1)[0].strip() for line in ini["pytest"]["markers"].strip().splitlines()]
    assert "perf" in markers


@pytest.mark.parametrize(("module", "qualname"), PERF_TESTS)
def test_each_wall_clock_budget_carries_the_perf_marker(module: str, qualname: str):
    target = importlib.import_module(module)
    for part in qualname.split("."):
        target = getattr(target, part)
    assert "perf" in {mark.name for mark in getattr(target, "pytestmark", [])}, qualname
