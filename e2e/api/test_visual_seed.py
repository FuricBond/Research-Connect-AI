"""P12: the data the visual suite photographs (frontend/e2e/visual.spec.ts): the demo set and the corpus.

Marked `visual`, so the API suite leaves it out; `python e2e/run_e2e.py --suites visual` runs only this
before the screenshots, so no other test's accounts or activity appear in them.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.visual


def test_the_demo_set_and_the_corpus_are_in_place(demo_seeded, corpus) -> None:
    assert corpus, "the visual suite searches the corpus"
