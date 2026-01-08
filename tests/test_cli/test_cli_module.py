"""Tests for aid2e.cli module."""

import pytest


def test_cli_module_import():
    """Test that aid2e.cli module can be imported."""
    import aid2e.cli
    assert aid2e.cli is not None


def test_cli_module_has_version():
    """Test that aid2e.cli has a version attribute."""
    import aid2e.cli
    assert hasattr(aid2e.cli, '__version__')
    assert isinstance(aid2e.cli.__version__, str)


def test_cli_module_import():
    """Test that CLI module can be imported."""
    from aid2e.cli import aid2e_cli
    assert aid2e_cli is not None


def test_cli_has_main_function():
    """Test that CLI module has the main cli function."""
    from aid2e.cli.aid2e_cli import cli
    assert callable(cli)


def test_cli_is_click_group():
    """Test that CLI is a Click group."""
    import click
    from aid2e.cli.aid2e_cli import cli
    assert isinstance(cli, click.Group)
