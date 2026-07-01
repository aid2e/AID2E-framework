"""Rule resolution and payload validation for job execution.

Implements template-based command construction and payload
validation for conditional job execution.

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

import re
from typing import Any, Dict, Optional, Tuple
from aid2e.utilities.configurations.workflow_config import JobDefinition
from aid2e.utilities.workflows.execution_logger import ExecutionLogger


class RuleResolutionError(Exception):
    """Raised when rule resolution fails."""
    pass


class PayloadValidationError(Exception):
    """Raised when payload validation fails."""
    pass


def resolve_payload_templates(
    payload: Dict[str, Any],
    context: Dict[str, Any],
    logger: Optional[ExecutionLogger] = None
) -> Dict[str, Any]:
    """Resolve template variables in payload dict.

    Recursively processes payload dict, replacing template variables with
    context values. Supports nested dicts and lists.

    Template Variables:
    - {{job_id}}: Job name
    - {{output_dir}}: Job output directory
    - {{stage_outputs[stage_name]}}: Output path from previous stage
    - {{input_design_params}}: Design parameters file path
    
    Args:
        payload: Payload dict potentially containing template variables
        context: Runtime context dict
        logger: Optional execution logger for logging operations
    
    Returns:
        Dict with all templates resolved
    
    Raises:
        RuleResolutionError: If template variable is undefined in context
    
    Example:
        >>> payload = {
        ...     "input_file": "{{input_design_params}}",
        ...     "output_dir": "{{output_dir}}",
        ...     "job_id": "{{job_id}}"
        ... }
        >>> context = {
        ...     "input_design_params": "/path/to/design.params",
        ...     "output_dir": "/tmp/stage_output",
        ...     "job_id": 0
        ... }
        >>> resolved = resolve_payload_templates(payload, context)
        # resolved = {"input_file": "/path/to/design.params", ...}
    """
    if logger:
        logger.checkpoint(
            stage="payload_template_resolution",
            status="start",
            message="Resolving payload template variables",
            context={"payload_keys": list(payload.keys())}
        )
    
    resolved = {}
    
    for key, value in payload.items():
        if isinstance(value, str):
            # Resolve string templates
            resolved[key] = _resolve_template_string(value, context, logger)
        elif isinstance(value, dict):
            # Recursively resolve nested dicts
            resolved[key] = resolve_payload_templates(value, context, logger)
        elif isinstance(value, list):
            # Resolve list items
            resolved[key] = [
                _resolve_template_string(item, context, logger) if isinstance(item, str) else item
                for item in value
            ]
        else:
            # Non-string values (int, bool, float, etc.) pass through unchanged
            resolved[key] = value
    
    if logger:
        logger.checkpoint(
            stage="payload_template_resolution",
            status="success",
            message="Payload templates resolved successfully",
            context={
                "resolved_keys": list(resolved.keys()),
                "sample_values": {k: str(v)[:50] for k, v in list(resolved.items())[:3]}
            }
        )
    
    return resolved


def _resolve_template_string(
    template: str,
    context: Dict[str, Any],
    logger: Optional[ExecutionLogger] = None
) -> str:
    """Resolve a single template string.
    
    Args:
        template: Template string (e.g., "{{input_design_params}}")
        context: Runtime context
        logger: Optional logger
    
    Returns:
        Resolved string
    
    Raises:
        RuleResolutionError: If variable is undefined
    """
    # Find all template variables: {{var_name}} or {{dict[key]}}
    pattern = r'\{\{([^}]+)\}\}'
    variables = re.findall(pattern, template)
    
    result = template
    for var in variables:
        # Try to get value from context
        value = _get_context_value(var, context)
        if value is None:
            raise RuleResolutionError(f"Undefined template variable: {{{var}}}")
        
        result = result.replace(f"{{{{var}}}}", str(value))
    
    return result


def _get_context_value(var_path: str, context: Dict[str, Any]) -> Any:
    """Get value from context using path notation.
    
    Supports:
    - Simple keys: "job_id"
    - Dict access: "stage_outputs[preparation]"
    - Nested access: "payload[metadata][version]"
    
    Args:
        var_path: Variable path string
        context: Context dict
    
    Returns:
        Value from context, or None if not found
    """
    # Handle dict[key] notation
    if "[" in var_path and "]" in var_path:
        # Extract base name and keys
        match = re.match(r'(\w+)\[([^\]]+)\]', var_path)
        if not match:
            return None
        
        base_name = match.group(1)
        key_path = match.group(2)
        
        if base_name not in context:
            return None
        
        obj = context[base_name]
        
        # Navigate through keys
        for key in key_path.split("]["):
            key = key.strip("]").strip("[")
            if isinstance(obj, dict):
                obj = obj.get(key)
            else:
                return None
            
            if obj is None:
                return None
        
        return obj
    else:
        # Simple key lookup
        return context.get(var_path)


def resolve_job_rule(
    job: JobDefinition,
    context: Dict[str, Any],
    logger: Optional[ExecutionLogger] = None
) -> str:
    """Resolve job rule template to final command.
    
    Implements experimental_stack.py StackLayer pattern for command construction.
    
    Rule Template Variables:
    - {{command}}: Job command
    - {{payload[key]}}: Value from resolved payload
    - {{job_id}}, {{output_dir}}, etc.: Context variables
    
    Args:
        job: JobDefinition with command and optional rule
        context: Runtime context with template variables
        logger: Optional execution logger
    
    Returns:
        Final command string ready for execution
    
    Raises:
        RuleResolutionError: If rule cannot be resolved
    
    Example:
        >>> job = JobDefinition(
        ...     name="test",
        ...     command="python compute.py",
        ...     rule="{{command}} {{payload[input]}} {{payload[output]}}",
        ...     payload={"input": "{{input_design_params}}", "output": "{{output_dir}}"}
        ... )
        >>> context = {
        ...     "input_design_params": "/data/design.params",
        ...     "output_dir": "/tmp/out",
        ...     "job_id": 0
        ... }
        >>> cmd = resolve_job_rule(job, context)
        # cmd = "python compute.py /data/design.params /tmp/out"
    """
    if logger:
        logger.checkpoint(
            stage="rule_resolution",
            status="start",
            message="Resolving job rule template",
            context={"job_name": job.name, "rule": job.rule}
        )
    
    # Step 1: Resolve payload templates with context
    resolved_payload = resolve_payload_templates(job.payload, context, logger)
    
    # Step 2: Determine rule (use default if not specified)
    rule = job.rule or "{{command}}"
    
    if logger:
        logger.log_debug("Using rule template", context={"rule": rule})
    
    # Step 3: Build command by substituting rule template
    # Create substitution dict: {"command": value, "payload": {...}}
    substitution_context = {
        "command": job.command,
        "payload": resolved_payload,
        **context  # Include all context variables
    }
    
    try:
        final_command = _substitute_rule_template(rule, substitution_context)
        
        if logger:
            logger.checkpoint(
                stage="rule_resolution",
                status="success",
                message="Rule template resolved to final command",
                context={
                    "rule": rule,
                    "final_command": final_command,
                    "command_length": len(final_command)
                }
            )
        
        return final_command
    
    except Exception as e:
        if logger:
            logger.checkpoint(
                stage="rule_resolution",
                status="error",
                message=f"Failed to resolve rule: {str(e)}",
                context={"rule": rule},
                details={"error": str(e), "job_name": job.name}
            )
        raise RuleResolutionError(f"Cannot resolve rule '{rule}': {str(e)}")


def _substitute_rule_template(rule: str, context: Dict[str, Any]) -> str:
    """Substitute variables in rule template.
    
    Handles {{command}}, {{payload[key]}}, and other context variables.
    
    Args:
        rule: Rule template string
        context: Substitution context
    
    Returns:
        Substituted command string
    """
    result = rule
    
    # Find all template variables: {var_name} or {dict[key]}
    pattern = r'\{\{([^}]+)\}\}'
    variables = re.findall(pattern, rule)
    
    for var in variables:
        value = _get_context_value(var, context)
        if value is None:
            raise ValueError(f"Undefined variable in rule: {{{{var}}}}")
        
        result = result.replace(f"{{var}}", str(value))
    
    # Clean up multiple spaces
    result = re.sub(r'\s+', ' ', result).strip()
    
    return result


def validate_job_payload(
    job: JobDefinition,
    required_keys: Optional[list[str]] = None,
    context: Optional[Dict[str, Any]] = None,
    logger: Optional[ExecutionLogger] = None
) -> Tuple[bool, Optional[str]]:
    """Validate job payload before execution.
    
    Checks:
    1. Required keys are present in payload
    2. Template variables can be resolved (if context provided)
    3. Payload values are not empty
    
    Args:
        job: JobDefinition to validate
        required_keys: List of required payload keys
        context: Optional context for template validation
        logger: Optional execution logger
    
    Returns:
        Tuple of (is_valid, error_message)
    
    Example:
        >>> job = JobDefinition(
        ...     name="test",
        ...     command="python script.py",
        ...     payload={"input": "/path/to/input"}
        ... )
        >>> is_valid, error = validate_job_payload(job, required_keys=["input"])
        # is_valid = True, error = None
    """
    if logger:
        logger.checkpoint(
            stage="payload_validation",
            status="start",
            message="Validating job payload",
            context={"job_name": job.name, "required_keys": required_keys}
        )
    
    # Check required keys
    if required_keys:
        missing_keys = [key for key in required_keys if key not in job.payload]
        if missing_keys:
            error_msg = f"Missing required payload keys: {missing_keys}"
            if logger:
                logger.checkpoint(
                    stage="payload_validation",
                    status="error",
                    message=error_msg,
                    context={"required_keys": required_keys, "missing_keys": missing_keys}
                )
            return False, error_msg
    
    # Check for empty payload values
    empty_values = [
        (key, value) for key, value in job.payload.items()
        if value is None or (isinstance(value, str) and value.strip() == "")
    ]
    
    if empty_values:
        error_msg = f"Payload contains empty values: {empty_values}"
        if logger:
            logger.checkpoint(
                stage="payload_validation",
                status="warning",
                message=error_msg,
                context={"empty_values": {k: v for k, v in empty_values}}
            )
        # Warning, not error - proceed but log it
    
    # Try to resolve templates if context provided
    if context:
        try:
            resolved = resolve_payload_templates(job.payload, context, logger)
            if logger:
                logger.log_debug("Payload templates resolved during validation")
        except RuleResolutionError as e:
            error_msg = f"Cannot resolve payload templates: {str(e)}"
            if logger:
                logger.checkpoint(
                    stage="payload_validation",
                    status="error",
                    message=error_msg,
                    context={"error": str(e)}
                )
            return False, error_msg
    
    if logger:
        logger.checkpoint(
            stage="payload_validation",
            status="success",
            message="Payload validation passed",
            context={"payload_keys": list(job.payload.keys())}
        )
    
    return True, None
