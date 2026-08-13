"""Tests for PanDAiDDS scheduler configuration."""

import os
import pytest
from unittest.mock import patch

from aid2e.schedulers.PanDAiDDS.config import PanDAiDDSRunnerConfig


class TestPanDAiDDSRunnerConfig:
    """Test suite for PanDAiDDS configuration model."""
    
    def test_name_auto_generation_from_system_username(self):
        """Test that name is auto-generated from system username."""
        with patch("getpass.getuser", return_value="testuser"):
            config = PanDAiDDSRunnerConfig()
            assert config.name == "user.testuser.aid2e_job"
    
    def test_name_auto_generation_from_env_variable(self):
        """Test that PANDA_USERNAME env variable overrides system username."""
        with patch.dict(os.environ, {"PANDA_USERNAME": "envuser"}):
            config = PanDAiDDSRunnerConfig()
            assert config.name == "user.envuser.aid2e_job"

    def test_name_validation_valid_prefix(self):
        """Test that valid names starting with 'user.' are accepted."""
        config = PanDAiDDSRunnerConfig(name="user.myname.experiment")
        assert config.name == "user.myname.experiment"
    
    def test_name_validation_invalid_prefix(self):
        """Test that names not starting with 'user.' are rejected."""
        with pytest.raises(ValueError, match="must start with 'user\\."):
            PanDAiDDSRunnerConfig(name="invalid.name")
    
    def test_name_validation_empty_string(self):
        """Test that empty string triggers auto-generation."""
        config = PanDAiDDSRunnerConfig(name="")
        assert config.name.startswith("user.")
        assert ".aid2e_job" in config.name
    
    def test_name_with_multiple_dots(self):
        """Test that names with multiple dots are accepted if prefix is valid."""
        config = PanDAiDDSRunnerConfig(name="user.john.doe.experiment.test")
        assert config.name == "user.john.doe.experiment.test"
    
    def test_env_variable_takes_precedence_over_system(self):
        """Test that PANDA_USERNAME takes precedence over getpass.getuser()."""
        with patch("getpass.getuser", return_value="systemuser"):
            with patch.dict(os.environ, {"PANDA_USERNAME": "envuser"}):
                config = PanDAiDDSRunnerConfig()
                assert config.name == "user.envuser.aid2e_job"
    
    def test_explicit_name_overrides_auto_generation(self):
        """Test that explicitly provided name overrides auto-generation."""
        with patch.dict(os.environ, {"PANDA_USERNAME": "envuser"}):
            config = PanDAiDDSRunnerConfig(name="user.explicit.name")
            assert config.name == "user.explicit.name"
    
    def test_other_fields_defaults(self):
        """Test that other fields have expected defaults."""
        config = PanDAiDDSRunnerConfig()
        init_env_list = [
            "source setup_aid2e.sh;",
            "bash install_aid2e_dependencies.sh;",
        ]
        assert config.init_env == " ".join(init_env_list) + " "
        assert config.cloud is None
        assert config.queue is None
        assert config.source_dir is not None  # Auto-set to project root
        assert os.path.isabs(config.source_dir)  # Should be absolute path
        assert config.source_dir_parent_level == 1
        assert config.max_walltime is None
        assert config.core_count == 1
        assert config.total_memory == 4000
        assert config.enable_separate_log is True
        assert config.job_dir is None
    
    def test_source_dir_auto_set_to_project_root(self):
        """Test that source_dir defaults to the project root."""
        config = PanDAiDDSRunnerConfig()
        expected = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        assert config.source_dir == expected
    
    def test_source_dir_from_env_variable(self):
        """Test that PANDA_SOURCE_DIR env variable overrides auto-setting."""
        with patch.dict(os.environ, {"PANDA_SOURCE_DIR": "/custom/source/dir"}):
            config = PanDAiDDSRunnerConfig()
            assert config.source_dir == "/custom/source/dir"
    
    def test_source_dir_explicit_override(self):
        """Test that explicit source_dir overrides auto-setting."""
        config = PanDAiDDSRunnerConfig(source_dir="/explicit/path")
        assert config.source_dir == "/explicit/path"
    
    def test_full_config_with_custom_name(self):
        """Test creating a full configuration with custom name."""
        config = PanDAiDDSRunnerConfig(
            name="user.scientist.epic_tracking",
            cloud="US",
            queue="BNL_PanDA_1",
            source_dir="/custom/source",
            max_walltime=7200,
            core_count=4,
            total_memory=8000,
            enable_separate_log=True,
            job_dir="/tmp/panda_jobs",
        )
        assert config.name == "user.scientist.epic_tracking"
        assert config.cloud == "US"
        assert config.queue == "BNL_PanDA_1"
        assert config.source_dir == "/custom/source"
        assert config.max_walltime == 7200
        assert config.core_count == 4
        assert config.total_memory == 8000
        assert config.job_dir == "/tmp/panda_jobs"
