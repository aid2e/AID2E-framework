from typing import Dict, List, Optional, Tuple, Union, Literal, Any
from pydantic import BaseModel, Field, model_validator

# Base class for all design parameters
class BaseParameter(BaseModel):
    """
    Abstract base class for all parameter types.
    Subclasses should define specific parameter characteristics.
    """
    name: str
    type: str  # Discriminator
    value: Union[float, str, int]  # Generic value field
    
    class Config:
        extra = "allow"  # Allow subclasses to add fields


class RangeParameter(BaseParameter):
    """Continuous parameter with min/max bounds."""
    value: float
    bounds: Tuple[float, float]

    @property
    def type(self) -> Literal["range"]:
        return "range"


class ChoiceParameter(BaseParameter):
    """Categorical parameter with discrete choices."""
    value: Union[str, int]
    choices: Union[List[str], List[int]]

    @property
    def type(self) -> Literal["choice"]:
        return "choice"

    @model_validator(mode='after')
    def check_value_choices_consistency(self) -> "ChoiceParameter":
        value = self.value
        choices = self.choices

        for choice in choices:
            is_same = type(value) == type(choice)
            if not is_same:
                raise ValueError("Type of each choice must match type of value ({type(value)}), but {choice} is a {type(choice)}")

        return self


# Generic parameter union (for simple use cases)
Parameter = Union[RangeParameter, ChoiceParameter]


def parse_parameter(name: str, data: dict) -> Parameter:
    """
    Parses a raw dictionary into a Parameter object (RangeParameter or ChoiceParameter).
    Automatically injects the name into the data.
    """
    data["name"] = name

    if "bounds" in data:
        try:
            return RangeParameter(**data)
        except Exception as e:
            raise ValueError(f"Invalid range parameter '{name}': {e}")

    if "choices" in data:
        if not isinstance(data.get("value"), str):
            raise ValueError(
                f"Parameter '{name}' appears to be a choice parameter, but its value `{data.get('value')}` is not a string. "
                f'Wrap it in quotes: value: "{data.get("value")}"'
            )
        try:
            return ChoiceParameter(**data)
        except Exception as e:
            raise ValueError(f"Invalid choice parameter '{name}': {e}")

    raise ValueError(
        f"Parameter '{name}' must have either 'bounds' (for range) or 'choices' (for choice)."
    )

class ContainerConfig(BaseModel):
    bind_paths: List[str] = Field(default_factory=list)
    environment_vars: Dict[str, str] = Field(default_factory=dict)
