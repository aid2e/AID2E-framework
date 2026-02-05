"""Execution logging and checkpointing utilities for workflow jobs.

Provides comprehensive logging with checkpoints, allowing jobs to be traced
and debugged with detailed context at each execution stage.

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class Checkpoint:
    """Represents a checkpoint in job execution.
    
    Attributes:
        stage: Execution stage name (e.g., "rule_resolution", "payload_validation")
        status: Status code ("start", "success", "warning", "error", "skipped")
        timestamp: ISO format timestamp
        message: Human-readable message
        context: Contextual data (job_id, payload, resolved values, etc.)
        details: Additional details (error messages, stack traces, etc.)
    """
    stage: str
    status: str
    timestamp: str
    message: str
    context: Dict[str, Any]
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert checkpoint to dict for JSON serialization."""
        return asdict(self)


class ExecutionLogger:
    """Comprehensive logger for job execution with checkpoints.
    
    Features:
    - Structured logging (JSON-compatible)
    - Checkpoint tracking at each execution stage
    - Context preservation across stages
    - File-based logging with rotation
    - Console logging with color formatting
    
    Example:
        >>> logger = ExecutionLogger(
        ...     job_name="dtlz2_evaluate",
        ...     output_dir="/tmp/stage_output",
        ...     log_level="DEBUG"
        ... )
        >>> logger.checkpoint("rule_resolution", "start", "Resolving rule template")
        >>> logger.log_info("Rule resolved successfully")
        >>> logger.checkpoint("rule_resolution", "success", "Rule resolved")
        >>> checkpoint = logger.get_last_checkpoint()
    """
    
    def __init__(
        self,
        job_name: str,
        output_dir: str,
        log_level: str = "INFO",
        enable_file_logging: bool = True,
        enable_checkpoint_file: bool = True
    ):
        """Initialize execution logger.
        
        Args:
            job_name: Name of the job being executed
            output_dir: Directory for log files
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            enable_file_logging: Whether to log to file
            enable_checkpoint_file: Whether to save checkpoints to JSON file
        """
        self.job_name = job_name
        self.output_dir = Path(output_dir)
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.enable_file_logging = enable_file_logging
        self.enable_checkpoint_file = enable_checkpoint_file
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize logger
        self.logger = logging.getLogger(f"aid2e.{job_name}")
        self.logger.setLevel(self.log_level)
        self.logger.handlers.clear()
        
        # Console handler (always enabled)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.log_level)
        formatter = logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # File handler (if enabled)
        if enable_file_logging:
            log_file = self.output_dir / f"{job_name}_execution.log"
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(self.log_level)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
            self.log_file = log_file
        else:
            self.log_file = None
        
        # Checkpoint tracking
        self.checkpoints: list[Checkpoint] = []
        self.checkpoint_file = self.output_dir / f"{job_name}_checkpoints.json"
        
        # Initial checkpoint: execution started
        self.checkpoint(
            stage="initialization",
            status="start",
            message=f"Job execution started: {job_name}",
            context={"job_name": job_name, "output_dir": str(self.output_dir)}
        )
    
    def checkpoint(
        self,
        stage: str,
        status: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> Checkpoint:
        """Record a checkpoint at current execution stage.
        
        Args:
            stage: Stage name (e.g., "rule_resolution", "payload_validation")
            status: Status code ("start", "success", "warning", "error", "skipped")
            message: Human-readable message
            context: Contextual data (optional)
            details: Additional details (optional)
        
        Returns:
            Checkpoint object created
        """
        checkpoint = Checkpoint(
            stage=stage,
            status=status,
            timestamp=datetime.now().isoformat(),
            message=message,
            context=context or {},
            details=details
        )
        
        self.checkpoints.append(checkpoint)
        
        # Log checkpoint
        log_msg = f"[{stage}:{status}] {message}"
        if context:
            log_msg += f" | context: {json.dumps(context, default=str, indent=0)}"
        
        if status == "error":
            self.logger.error(log_msg)
        elif status == "warning":
            self.logger.warning(log_msg)
        elif status == "skipped":
            self.logger.info(f"[SKIP] {log_msg}")
        else:
            self.logger.info(log_msg)
        
        # Save checkpoints to file
        if self.enable_checkpoint_file:
            self._save_checkpoints()
        
        return checkpoint
    
    def log_debug(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log debug message with optional context."""
        if context:
            message += f" | {json.dumps(context, default=str, indent=0)}"
        self.logger.debug(message)
    
    def log_info(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log info message with optional context."""
        if context:
            message += f" | {json.dumps(context, default=str, indent=0)}"
        self.logger.info(message)
    
    def log_warning(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log warning message with optional context."""
        if context:
            message += f" | {json.dumps(context, default=str, indent=0)}"
        self.logger.warning(message)
    
    def log_error(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log error message with optional context."""
        if context:
            message += f" | {json.dumps(context, default=str, indent=0)}"
        self.logger.error(message)
    
    def get_last_checkpoint(self) -> Optional[Checkpoint]:
        """Get the most recent checkpoint."""
        return self.checkpoints[-1] if self.checkpoints else None
    
    def get_checkpoint_by_stage(self, stage: str) -> list[Checkpoint]:
        """Get all checkpoints for a given stage."""
        return [cp for cp in self.checkpoints if cp.stage == stage]
    
    def get_checkpoints_by_status(self, status: str) -> list[Checkpoint]:
        """Get all checkpoints with a given status."""
        return [cp for cp in self.checkpoints if cp.status == status]
    
    def _save_checkpoints(self):
        """Save all checkpoints to JSON file."""
        try:
            checkpoint_data = {
                "job_name": self.job_name,
                "total_checkpoints": len(self.checkpoints),
                "execution_start": self.checkpoints[0].timestamp if self.checkpoints else None,
                "execution_end": self.checkpoints[-1].timestamp if self.checkpoints else None,
                "checkpoints": [cp.to_dict() for cp in self.checkpoints]
            }
            
            with open(self.checkpoint_file, "w") as f:
                json.dump(checkpoint_data, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Failed to save checkpoints: {e}")
    
    def execution_summary(self) -> Dict[str, Any]:
        """Generate execution summary from checkpoints.
        
        Returns:
            Dict with execution summary (total stages, errors, warnings, etc.)
        """
        summary = {
            "job_name": self.job_name,
            "total_checkpoints": len(self.checkpoints),
            "execution_start": self.checkpoints[0].timestamp if self.checkpoints else None,
            "execution_end": self.checkpoints[-1].timestamp if self.checkpoints else None,
            "status_breakdown": {
                "start": len(self.get_checkpoints_by_status("start")),
                "success": len(self.get_checkpoints_by_status("success")),
                "warning": len(self.get_checkpoints_by_status("warning")),
                "error": len(self.get_checkpoints_by_status("error")),
                "skipped": len(self.get_checkpoints_by_status("skipped"))
            },
            "stages_executed": list(set(cp.stage for cp in self.checkpoints)),
            "has_errors": len(self.get_checkpoints_by_status("error")) > 0
        }
        return summary


def create_job_logger(
    job_name: str,
    output_dir: str,
    log_level: str = "INFO"
) -> ExecutionLogger:
    """Convenience function to create job logger.
    
    Args:
        job_name: Name of the job
        output_dir: Output directory for logs
        log_level: Logging level
    
    Returns:
        ExecutionLogger instance
    """
    return ExecutionLogger(
        job_name=job_name,
        output_dir=output_dir,
        log_level=log_level,
        enable_file_logging=True,
        enable_checkpoint_file=True
    )
