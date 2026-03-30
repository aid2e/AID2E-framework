"""Test ePIC environment configuration."""

import yaml

from aid2e.utilities.epic_utils.epic_env_config import (
    EpicEnvConfig,
    EpicEnvConfigLoader,
)

def _sample_epic_env_payload() -> dict:
    """Build ePIC environment configuration."""
    return {
        "epic_environment": {
            "eic_shell": "/home/eic/.bin/eic-shell",
            "epic_install": "/home/eic/epic",
            "epic_config": "epic_full", 
        }
    }

def test_epic_env_config_loader(tmp_path):
    """Validate EpicEnvConfigLoader."""
    config_path = tmp_path /  "epic_env.config"
    config_path.write_text(yaml.safe_dump(_sample_epic_env_payload()))

    config = EpicEnvConfigLoader.load(str(config_path))
    assert isinstance(config, EpicEnvConfig)
    assert "/home/eic/.bin/eic-shell" == config.eic_shell
    assert "/home/eic/epic" == config.epic_install
    assert "epic_full" == config.epic_config
