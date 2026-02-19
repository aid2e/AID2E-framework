#!/usr/bin/env python3
"""Verify PanDAiDDS name auto-generation functionality."""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aid2e.schedulers.PanDAiDDS.config import PanDAiDDSRunnerConfig


def test_auto_generation():
    """Test auto-generation of PanDA job name."""
    print("Test 1: Auto-generation from system username")
    # Clear any existing PANDA_USERNAME env var for this test
    saved_env = os.environ.pop("PANDA_USERNAME", None)
    
    config1 = PanDAiDDSRunnerConfig()
    print(f"  Generated name: {config1.name}")
    assert config1.name.startswith("user."), f"Name should start with 'user.', got: {config1.name}"
    assert ".aid2e_job" in config1.name, f"Name should end with '.aid2e_job', got: {config1.name}"
    print("  ✓ PASSED\n")
    
    # Restore env var if it existed
    if saved_env:
        os.environ["PANDA_USERNAME"] = saved_env


def test_env_override():
    """Test environment variable override."""
    print("Test 2: Override with PANDA_USERNAME environment variable")
    os.environ["PANDA_USERNAME"] = "testuser123"
    config2 = PanDAiDDSRunnerConfig()
    print(f"  Generated name: {config2.name}")
    assert config2.name == "user.testuser123.aid2e_job", f"Expected 'user.testuser123.aid2e_job', got: {config2.name}"
    print("  ✓ PASSED\n")
    del os.environ["PANDA_USERNAME"]


def test_explicit_name():
    """Test explicit name validation."""
    print("Test 3: Valid explicit name")
    config3 = PanDAiDDSRunnerConfig(name="user.myname.experiment")
    print(f"  Configured name: {config3.name}")
    assert config3.name == "user.myname.experiment"
    print("  ✓ PASSED\n")


def test_invalid_name():
    """Test invalid name rejection."""
    print("Test 4: Invalid name (should fail)")
    try:
        config4 = PanDAiDDSRunnerConfig(name="invalid.name")
        print("  ✗ FAILED - Should have raised ValueError")
        sys.exit(1)
    except ValueError as e:
        print(f"  Caught expected error: {e}")
        print("  ✓ PASSED\n")


def test_full_config():
    """Test full configuration."""
    print("Test 5: Full configuration with all fields")
    config5 = PanDAiDDSRunnerConfig(
        name="user.scientist.epic_tracking",
        cloud="US",
        queue="BNL_PanDA_1",
        max_walltime=7200,
        core_count=4,
        total_memory=8000,
        enable_separate_log=True,
        job_dir="/tmp/panda_jobs",
    )
    print(f"  Name: {config5.name}")
    print(f"  Cloud: {config5.cloud}")
    print(f"  Queue: {config5.queue}")
    print(f"  Max walltime: {config5.max_walltime}")
    print(f"  Core count: {config5.core_count}")
    print(f"  Total memory: {config5.total_memory}")
    assert config5.name == "user.scientist.epic_tracking"
    assert config5.cloud == "US"
    assert config5.queue == "BNL_PanDA_1"
    print("  ✓ PASSED\n")


if __name__ == "__main__":
    print("="*70)
    print("PanDAiDDS Configuration - Username Auto-Generation Tests")
    print("="*70)
    print()
    
    try:
        test_auto_generation()
        test_env_override()
        test_explicit_name()
        test_invalid_name()
        test_full_config()
        
        print("="*70)
        print("✅ All tests passed!")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
