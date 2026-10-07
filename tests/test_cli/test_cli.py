"""Tests for aid2e.cli CLI functionality."""

import pytest
from click.testing import CliRunner
from aid2e.cli.aid2e_cli import cli


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


def test_cli_help(runner):
    """Test CLI help command."""
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert 'AID2E' in result.output
    assert 'Usage:' in result.output
    assert 'mcp' in result.output


def test_cli_version(runner):
    """Test CLI version command."""
    result = runner.invoke(cli, ['--version'])
    assert result.exit_code == 0
    assert 'version' in result.output.lower()


def test_cli_version_subcommand(runner):
    """Test CLI version subcommand."""
    result = runner.invoke(cli, ['version'])
    assert result.exit_code == 0


def test_mcp_help_is_always_available(runner):
    """The MCP command must be discoverable even before extras are installed."""
    result = runner.invoke(cli, ['mcp', '--help'])
    assert result.exit_code == 0
    assert 'Run the AID2E MCP server.' in result.output


