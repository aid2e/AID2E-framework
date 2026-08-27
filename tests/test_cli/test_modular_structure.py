"""
Unit tests for modular CLI structure.

Tests command registration, imports, and modular organization.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

# Test both import patterns
from aid2e.cli.aid2e_cli import cli as cli_direct
from aid2e.cli import cli as cli_package


DTLZ2_CONFIG = (
    Path(__file__).parents[2]
    / "examples"
    / "dtlz2"
    / "dtlz2_optimization.yml"
)


class TestCLIStructure:
    """Test CLI organization and command registration."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
    
    def test_cli_group_exists(self):
        """Main CLI group should exist."""
        assert cli_direct is not None
        assert callable(cli_direct)
    
    def test_both_import_patterns_work(self):
        """Both import patterns should return same CLI."""
        assert cli_direct is cli_package
    
    def test_cli_help(self):
        """CLI should display help message."""
        result = self.runner.invoke(cli_direct, ["--help"])
        assert result.exit_code == 0
        assert "AID2E" in result.output
        assert "AI assisted Detector Design for EIC" in result.output
    
    def test_version_option(self):
        """CLI should support --version flag."""
        result = self.runner.invoke(cli_direct, ["--version"])
        assert result.exit_code == 0
        assert "aid2e" in result.output.lower()


class TestCommandRegistration:
    """Test that all commands are properly registered."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
    
    def get_registered_commands(self):
        """Get list of registered command names."""
        return list(cli_direct.commands.keys())
    
    def test_config_commands_registered(self):
        """Config commands should be registered."""
        commands = self.get_registered_commands()
        assert "describe" in commands
        assert "inspect" in commands
        assert "validate" in commands
    
    def test_workflow_commands_registered(self):
        """Workflow commands should be registered."""
        commands = self.get_registered_commands()
        assert "optimize" in commands
    
    def test_utility_commands_registered(self):
        """Utility commands should be registered."""
        commands = self.get_registered_commands()
        assert "list" in commands
        assert "version" in commands
    
    def test_all_expected_commands_present(self):
        """All expected commands should be present."""
        expected = {
            "describe", "inspect", "validate",  # config
            "optimize",                          # workflow
            "list", "version"                    # utility
        }
        commands = set(self.get_registered_commands())
        assert expected.issubset(commands)


class TestConfigCommands:
    """Test config inspection commands."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
    
    def test_describe_command_exists(self):
        """Describe command should be accessible and read canonical designs."""
        result = self.runner.invoke(cli_direct, ["describe", "--help"])
        assert result.exit_code == 0
        assert "Describe the contents" in result.output

        result = self.runner.invoke(cli_direct, ["describe", str(DTLZ2_CONFIG)])
        assert result.exit_code == 0
        assert "Design: inline (10 parameters)" in result.output
    
    def test_inspect_command_exists(self, tmp_path):
        """Inspect command should be accessible and apply section filters."""
        result = self.runner.invoke(cli_direct, ["inspect", "--help"])
        assert result.exit_code == 0
        assert "detailed information" in result.output

        config_path = tmp_path / "optimizer.yml"
        config_path.write_text(
            "optimizer:\n"
            "  name: ax\n"
            "  type: bayesian\n"
            "  parameters:\n"
            "    n_iterations: 5\n"
        )
        result = self.runner.invoke(
            cli_direct,
            ["inspect", str(config_path), "--section", "optimizer"],
        )
        assert result.exit_code == 0
        assert "Algorithm: ax (bayesian)" in result.output
        assert "n_iterations: 5" in result.output

        result = self.runner.invoke(
            cli_direct,
            ["inspect", str(config_path), "--section", "design"],
        )
        assert result.exit_code == 1
        assert "not available in an optimizer configuration" in result.output
    
    def test_validate_command_exists(self):
        """Validate command should be accessible."""
        result = self.runner.invoke(cli_direct, ["validate", "--help"])
        assert result.exit_code == 0
        assert "Validate" in result.output
    
    def test_describe_missing_file(self):
        """Describe should error on missing file."""
        result = self.runner.invoke(cli_direct, ["describe", "nonexistent.yml"])
        assert result.exit_code != 0
    
    def test_validate_missing_file(self, tmp_path):
        """Validate should reject missing files and unknown structures."""
        result = self.runner.invoke(cli_direct, ["validate", "nonexistent.yml"])
        assert result.exit_code != 0

        config_path = tmp_path / "unknown.yml"
        config_path.write_text("unknown:\n  value: 1\n")
        result = self.runner.invoke(cli_direct, ["validate", str(config_path)])
        assert result.exit_code == 1
        assert "Unknown configuration type" in result.output


class TestWorkflowCommands:
    """Test workflow execution commands."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
    
    def test_optimize_command_exists(self):
        """Optimize command should be accessible."""
        result = self.runner.invoke(cli_direct, ["optimize", "--help"])
        assert result.exit_code == 0
        assert "optimization" in result.output.lower()
    
    def test_optimize_has_validate_only_option(self):
        """Optimize should have --validate-only option."""
        result = self.runner.invoke(cli_direct, ["optimize", "--help"])
        assert "--validate-only" in result.output
    
    def test_optimize_has_verbosity_option(self, tmp_path):
        """Optimize should expose verbosity and write configured logs."""
        result = self.runner.invoke(cli_direct, ["optimize", "--help"])
        assert "--verbosity" in result.output or "-v" in result.output

        log_path = tmp_path / "aid2e.log"
        result = self.runner.invoke(
            cli_direct,
            [
                "optimize",
                str(DTLZ2_CONFIG),
                "--validate-only",
                "--log",
                str(log_path),
            ],
        )
        assert result.exit_code == 0
        assert "Configuration validated" in log_path.read_text()


class TestUtilityCommands:
    """Test utility commands."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
    
    def test_list_command_exists(self):
        """List command should be accessible."""
        result = self.runner.invoke(cli_direct, ["list", "--help"])
        assert result.exit_code == 0
    
    def test_list_no_args(self):
        """List without args should show all categories."""
        result = self.runner.invoke(cli_direct, ["list"])
        assert result.exit_code == 0
        assert "Optimizers" in result.output
        assert "Templates" in result.output
        assert "Problem Types" in result.output
    
    def test_list_optimizers(self):
        """List optimizers should show optimizer info."""
        result = self.runner.invoke(cli_direct, ["list", "optimizers"])
        assert result.exit_code == 0
        assert "ax" in result.output
        assert "Bayesian" in result.output
        assert "pymoo" in result.output
        assert "Evolutionary" in result.output
    
    def test_list_templates(self):
        """List templates should show template info."""
        result = self.runner.invoke(cli_direct, ["list", "templates"])
        assert result.exit_code == 0
        assert "dtlz2" in result.output or "basic" in result.output
    
    def test_list_problems(self):
        """List problems should show problem types."""
        result = self.runner.invoke(cli_direct, ["list", "problems"])
        assert result.exit_code == 0
        assert "toy" in result.output or "custom" in result.output
    
    def test_version_command(self):
        """Version command should display version."""
        result = self.runner.invoke(cli_direct, ["version"])
        assert result.exit_code == 0
        assert "AID2E" in result.output



class TestHelpOrganization:
    """Test that help output is well organized."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
    
    def test_help_shows_command_categories(self):
        """Main help should show command categories."""
        result = self.runner.invoke(cli_direct, ["--help"])
        assert result.exit_code == 0
        # Check for category headers
        output_lower = result.output.lower()
        assert "configuration" in output_lower or "config" in output_lower
        assert "workflow" in output_lower or "execution" in output_lower
        assert "utilit" in output_lower
    
    def test_help_shows_all_commands(self):
        """Main help should list all commands."""
        result = self.runner.invoke(cli_direct, ["--help"])
        assert result.exit_code == 0
        
        expected_commands = ["describe", "inspect", "validate", "optimize", "list", "version"]
        for cmd in expected_commands:
            assert cmd in result.output


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""
    
    def test_entry_point_import(self):
        """Entry point import pattern should work."""
        from aid2e.cli.aid2e_cli import cli
        assert cli is not None
        assert callable(cli)
    
    def test_package_import(self):
        """Package import pattern should work."""
        from aid2e.cli import cli
        assert cli is not None
        assert callable(cli)
    
    def test_commands_accessible_from_cli(self):
        """Commands should be accessible from main cli object."""
        assert hasattr(cli_direct, "commands")
        assert "describe" in cli_direct.commands
        assert "optimize" in cli_direct.commands
