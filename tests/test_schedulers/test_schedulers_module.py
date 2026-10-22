"""Tests for aid2e.schedulers module."""

import pytest


def test_schedulers_module_import():
    """Test that aid2e.schedulers module can be imported."""
    import aid2e.schedulers
    assert aid2e.schedulers is not None


def test_schedulers_module_has_version():
    """Test that aid2e.schedulers has a version attribute."""
    import aid2e.schedulers
    assert hasattr(aid2e.schedulers, '__version__')
    assert isinstance(aid2e.schedulers.__version__, str)


def test_schedulers_module_structure():
    """Test that schedulers module has expected structure."""
    import aid2e.schedulers
    # Module should be importable and have basic attributes
    assert hasattr(aid2e.schedulers, '__name__')
    assert aid2e.schedulers.__name__ == 'aid2e.schedulers'


def test_from_schedulers_import():
    """Test importing from aid2e.schedulers works."""
    from aid2e import schedulers
    assert schedulers is not None
    assert hasattr(schedulers, '__version__')


def test_slurm_accounting_timing(monkeypatch):
    from types import SimpleNamespace
    from aid2e.schedulers.Slurm import SlurmScheduler

    response = SimpleNamespace(returncode=0, stdout="12345|COMPLETED|0:0|2026-10-22T10:00:00|Unknown|2026-10-22T10:03:00|Unknown|")
    monkeypatch.setattr("aid2e.schedulers.Slurm.runner.subprocess.run", lambda *args, **kwargs: response)
    timing = SlurmScheduler()._query_sacct_state("12345")["accounting"]
    assert timing["submitted_at"] == "2026-10-22T10:00:00+00:00"
    assert timing["started_at"] == "2026-10-22T10:03:00+00:00"
    assert timing["queue_seconds"] == 180.0
