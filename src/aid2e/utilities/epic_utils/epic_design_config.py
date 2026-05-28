#!/usr/bin/env python3
"""
ePIC-specific design configuration. Extends the base
DesignConfig from the configurations module.
"""

from typing import ClassVar, Dict, List, Optional, Tuple, Union, Any
from pydantic import BaseModel, Field, RootModel, model_validator
from pathlib import Path
import yaml
import os
import re

from aid2e.utilities.configurations.base_models import BaseParameter, RangeParameter, ChoiceParameter
from aid2e.utilities.configurations.design_config import DesignConfig, DesignConfigLoader, ParameterConstraint


class EpicRangeParameter(RangeParameter):
    """
    Parameter with XML modification capability for ePIC detector.
    Extends RangeParameter with XML path, file path, and unit information.
    """
    xml_path: str  # XPath to XML element, e.g., "//constant[@name='...']/@value"
    unit: Optional[str] = None  # e.g., "mm", "cm", "um"
    attribute: Optional[str] = "value"  # the attribute of XML element to set, e.g. value

    @property
    def type(self) -> str:
        return "epic_range"

class EpicChoiceParameter(ChoiceParameter):
    """
    Parameter with XML modification capability for ePIC detector.
    Extends ChoiceParameter with XML path, file path, and unit information.
    """
    xml_path: str  # XPath to XML element, e.g., "//constant[@name='...']/@value"
    unit: Optional[str] = None  # e.g., "mm", "cm", "um"
    attribute: Optional[str] = "value"  # the attribute of XML element to set, e.g. value

    @property
    def type(self) -> str:
        return "epic_choice"


# Generic ePIC parameter
EpicParameter = Union[EpicRangeParameter, EpicChoiceParameter]


class EpicParameterGroup(BaseModel):
    """
    Group of ePIC parameters that share the same XML file.
    """
    file_path: str  # Path to XML file, can include $DETECTOR_PATH
    parameters: Dict[str, EpicParameter]


class EpicDesignParameters(RootModel[Dict[str, EpicParameterGroup]]):
    """
    Collection of ePIC parameter groups.
    """
    key: ClassVar[str] = 'epic_design_parameters'

    @model_validator(mode="before")
    @classmethod
    def inject_qualified_names(cls, values: Dict[str, dict]):
        """
        Injects full qualified names like 'group.param' into each parameter.
        This ensures parameters are uniquely identified.
        """
        for group_name, group_data in values.items():
            param_dict = group_data.get("parameters", {})
            for param_name, param_data in param_dict.items():
                if isinstance(param_data, dict) and "name" not in param_data:
                    param_data["name"] = f"{group_name}.{param_name}"
        return values


class EpicDesignConfig(DesignConfig):
    """
    ePIC-specific design configuration with XML integration.
    Extends DesignConfig with XML modification capabilities and optimization groups.
    
    Note: Uses 'epic_design_parameters' instead of 'design_parameters' to distinguish
    from generic configs in YAML files.
    """
    # Override to use ePIC-specific parameters
    design_parameters: Optional[Any] = None  # Set to None to avoid conflicts
    epic_design_parameters: EpicDesignParameters
    key: ClassVar[str] = 'epic_design_space'

    def get_flat_parameters(self) -> Dict[str, BaseParameter]:
        """Returns a flat dictionary of all parameters keyed by their qualified name."""
        flat = {}
        for group in self.epic_design_parameters.root.values():
            for param in group.parameters.values():
                flat[param.name] = param
        return flat

    def get_parameter_names(self) -> List[str]:
        """Get all parameter qualified names."""
        return list(self.get_flat_parameters().keys())
    
    def get_xml_modifications(self, param_values: Optional[Dict[str, float]] = None) -> Dict[str, List[Tuple[str, str, str, Any]]]:
        """
        Get XML modifications for given parameter values.
        
        Args:
            param_values: Dictionary of qualified parameter names to values.
                         If None, uses default values from config.
            
        Returns:
            Dictionary mapping file_path -> [(xml_path, attribute, unit, new_value), ...]
        """
        if param_values is None:
            # Use default values from config
            param_values = {name: param.value for name, param in self.get_flat_parameters().items()}
        
        modifications = {}

        for group_name, group in self.epic_design_parameters.root.items():
            # Expand environment variables in file path
            file_path = os.path.expandvars(group.file_path)
            
            if file_path not in modifications:
                modifications[file_path] = []
            
            for param_name, param in group.parameters.items():
                qualified_name = f"{group_name}.{param_name}"
                if qualified_name in param_values:
                    new_value = param_values[qualified_name]
                    modifications[file_path].append((
                        param.xml_path,
                        param.attribute,
                        param.unit or "",
                        new_value
                    ))
        
        return modifications
    
    def get_file_paths(self) -> List[str]:
        """Get all unique file paths referenced in the configuration."""
        return list(set(
            os.path.expandvars(group.file_path)
            for group in self.epic_design_parameters.root.values()
        ))


class EpicDesignConfigLoader(DesignConfigLoader):
    """
    Loader for ePIC design configurations. Can load either from
    external files or inline YAML blocks. instantiates EpicDesignConfig
    objects.
    """
    space_key = EpicDesignConfig.key
    param_key = EpicDesignParameters.key

    @staticmethod
    def load(design_data: Dict[str, Any] = None, file_path: str = None) -> "EpicDesignConfig":
        """
        Load an ePIC design configuration.
        """
        data = EpicDesignConfigLoader._process_inputs(design_data, file_path)
        return EpicDesignConfig(**data)
