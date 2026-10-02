"""
Research refresh (F-3) — the opt-in embedding warm-up in the application lifespan.

The warm-up must be off by default, must never hold up startup when it is on, and must log
rather than raise when the model cannot be loaded. The real model is never loaded here: the
loader is replaced, so these tests make no network calls and need no model weights.
"""
from __future__ import annotations

import logging
import threading

from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.main import app
from app.scheduler import lifecycle


def test_the_warm_up_is_off_by_default():
    assert Settings.model_fields["embedding_warmup_on_startup"].default is False


def test_a_disabled_warm_up_starts_no_thread_and_loads_nothing(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(lifecycle, "load_embedding_model", lambda: calls.append(1))
    monkeypatch.setattr(settings, "embedding_warmup_on_startup", False)

    assert lifecycle.start_embedding_warmup(settings) is None
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
    assert calls == []


def test_an_enabled_warm_up_does_not_block_startup(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def slow_loader() -> None:
        started.set()
        release.wait(timeout=30)
        finished.set()

    monkeypatch.setattr(lifecycle, "load_embedding_model", slow_loader)
    monkeypatch.setattr(settings, "embedding_warmup_on_startup", True)
    try:
        with TestClient(app) as client:
            # The API serves while the loader is still blocked.
            assert started.wait(timeout=10), "the enabled warm-up never started"
            assert client.get("/api/health").status_code == 200
            assert not finished.is_set()
    finally:
        release.set()
    assert finished.wait(timeout=10)


def test_the_warm_up_runs_on_a_daemon_thread(monkeypatch):
    done = threading.Event()
    monkeypatch.setattr(lifecycle, "load_embedding_model", done.set)
    monkeypatch.setattr(settings, "embedding_warmup_on_startup", True)

    thread = lifecycle.start_embedding_warmup(settings)
    assert thread is not None and thread.daemon
    thread.join(timeout=10)
    assert done.is_set()


def test_a_failing_loader_is_logged_not_raised(monkeypatch, caplog):
    def broken_loader() -> None:
        raise RuntimeError("model files missing")

    monkeypatch.setattr(lifecycle, "load_embedding_model", broken_loader)
    monkeypatch.setattr(settings, "embedding_warmup_on_startup", True)
    caplog.set_level(logging.INFO, logger=lifecycle.logger.name)
    # Capture the lifespan's own thread, so it is joined while the loader is still patched.
    started_threads: list[threading.Thread | None] = []
    original_start = lifecycle.start_embedding_warmup

    def capturing_start(cfg: Settings) -> threading.Thread | None:
        started_threads.append(original_start(cfg))
        return started_threads[-1]

    monkeypatch.setattr(lifecycle, "start_embedding_warmup", capturing_start)

    with TestClient(app) as client:
        assert len(started_threads) == 1 and started_threads[0] is not None
        started_threads[0].join(timeout=10)
        assert client.get("/api/health").status_code == 200

    failures = [r for r in caplog.records if "warm-up failed" in r.getMessage()]
    assert failures and all(r.levelno == logging.WARNING for r in failures)
    assert any("model files missing" in str(r.exc_info[1]) for r in failures if r.exc_info)


def test_a_successful_warm_up_logs_its_elapsed_time(monkeypatch, caplog):
    monkeypatch.setattr(lifecycle, "load_embedding_model", lambda: None)
    caplog.set_level(logging.INFO, logger=lifecycle.logger.name)

    lifecycle.warm_up_embedding_model()

    assert any(
        r.levelno == logging.INFO and "warm-up finished in" in r.getMessage() for r in caplog.records
    )
