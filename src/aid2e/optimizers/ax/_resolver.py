"""Resolvers for YAML-friendly Ax / BoTorch symbol configuration.

This module keeps the public Ax optimizer config serializable and YAML-friendly
by resolving supported string symbols into the concrete Python classes that Ax's
Modular BoTorch generator expects at runtime.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ax.generators.torch.botorch_modular.acquisition import Acquisition
from ax.generators.torch.botorch_modular.multi_acquisition import MultiAcquisition
from ax.generators.torch.botorch_modular.surrogate import ModelConfig, SurrogateSpec
from botorch.acquisition.analytic import LogExpectedImprovement, PosteriorMean
from botorch.acquisition.logei import (
    qLogExpectedImprovement,
    qLogNoisyExpectedImprovement,
)
from botorch.acquisition.monte_carlo import (
    qExpectedImprovement,
    qNoisyExpectedImprovement,
)
from botorch.acquisition.multi_objective.logei import (
    qLogNoisyExpectedHypervolumeImprovement,
)
from botorch.acquisition.multi_objective.monte_carlo import (
    qNoisyExpectedHypervolumeImprovement,
)
from botorch.models import SingleTaskGP
from botorch.models.fully_bayesian import SaasFullyBayesianSingleTaskGP
from botorch.models.fully_bayesian_multitask import SaasFullyBayesianMultiTaskGP
from botorch.models.map_saas import AdditiveMapSaasSingleTaskGP
from botorch.models.multitask import MultiTaskGP
from botorch.models.transforms.input import Normalize, Warp
from botorch.models.transforms.outcome import Standardize
from gpytorch.kernels import MaternKernel, RBFKernel, ScaleKernel
from gpytorch.likelihoods import GaussianLikelihood
from gpytorch.mlls import ExactMarginalLogLikelihood

SUPPORTED_AX_GENERATORS = {"BOTORCH_MODULAR"}

_AX_ACQUISITION_CLASSES = {
    "Acquisition": Acquisition,
    "MultiAcquisition": MultiAcquisition,
}

_BOTORCH_ACQF_CLASSES = {
    "LogExpectedImprovement": LogExpectedImprovement,
    "PosteriorMean": PosteriorMean,
    "qExpectedImprovement": qExpectedImprovement,
    "qNoisyExpectedImprovement": qNoisyExpectedImprovement,
    "qLogExpectedImprovement": qLogExpectedImprovement,
    "qLogNoisyExpectedImprovement": qLogNoisyExpectedImprovement,
    "qNoisyExpectedHypervolumeImprovement": qNoisyExpectedHypervolumeImprovement,
    "qLogNoisyExpectedHypervolumeImprovement": (
        qLogNoisyExpectedHypervolumeImprovement
    ),
}

_BOTORCH_MODEL_CLASSES = {
    "AdditiveMapSaasSingleTaskGP": AdditiveMapSaasSingleTaskGP,
    "MultiTaskGP": MultiTaskGP,
    "SaasFullyBayesianMultiTaskGP": SaasFullyBayesianMultiTaskGP,
    "SaasFullyBayesianSingleTaskGP": SaasFullyBayesianSingleTaskGP,
    "SingleTaskGP": SingleTaskGP,
}

_INPUT_TRANSFORM_CLASSES = {
    "Normalize": Normalize,
    "Warp": Warp,
}

_OUTCOME_TRANSFORM_CLASSES = {
    "Standardize": Standardize,
}

_COVAR_MODULE_CLASSES = {
    "MaternKernel": MaternKernel,
    "RBFKernel": RBFKernel,
    "ScaleKernel": ScaleKernel,
}

_LIKELIHOOD_CLASSES = {
    "GaussianLikelihood": GaussianLikelihood,
}

_MLL_CLASSES = {
    "ExactMarginalLogLikelihood": ExactMarginalLogLikelihood,
}


def validate_generator_name(generator_name: str) -> str:
    """Normalize and validate the configured Ax generator name."""
    normalized = str(generator_name).strip().upper()
    if normalized not in SUPPORTED_AX_GENERATORS:
        supported = ", ".join(sorted(SUPPORTED_AX_GENERATORS))
        raise ValueError(
            f"Unsupported Ax generator '{generator_name}'. "
            f"Supported values for this backend are: {supported}."
        )
    return normalized


def resolve_generator_kwargs(
    *, generator_name: str, generator_kwargs: dict[str, Any] | None
) -> dict[str, Any]:
    """Resolve YAML-friendly generator kwargs into Ax runtime objects."""
    resolved = deepcopy(generator_kwargs or {})
    generator_name = validate_generator_name(generator_name)
    if generator_name != "BOTORCH_MODULAR":
        return resolved

    if "acquisition_class" in resolved:
        resolved["acquisition_class"] = _resolve_symbol(
            resolved["acquisition_class"],
            registry=_AX_ACQUISITION_CLASSES,
            kind="Ax acquisition class",
        )

    if "botorch_acqf_class" in resolved:
        resolved["botorch_acqf_class"] = _resolve_symbol(
            resolved["botorch_acqf_class"],
            registry=_BOTORCH_ACQF_CLASSES,
            kind="BoTorch acquisition function",
        )

    if "botorch_acqf_classes_with_options" in resolved:
        resolved["botorch_acqf_classes_with_options"] = [
            _resolve_botorch_acqf_entry(entry)
            for entry in resolved["botorch_acqf_classes_with_options"]
        ]

    if "surrogate_spec" in resolved:
        resolved["surrogate_spec"] = _resolve_surrogate_spec(resolved["surrogate_spec"])

    return resolved


def _resolve_botorch_acqf_entry(entry: Any) -> tuple[type[Any], dict[str, Any]]:
    """Resolve one MultiAcquisition entry from YAML-friendly form."""
    if isinstance(entry, dict):
        class_value = entry.get("class")
        options = dict(entry.get("options") or {})
    elif isinstance(entry, (list, tuple)) and len(entry) == 2:
        class_value, options = entry
        options = dict(options or {})
    else:
        raise ValueError(
            "Entries in 'botorch_acqf_classes_with_options' must be provided as "
            "{'class': <name>, 'options': {...}} or [<name>, {...}]."
        )

    resolved_class = _resolve_symbol(
        class_value,
        registry=_BOTORCH_ACQF_CLASSES,
        kind="BoTorch acquisition function",
    )
    return resolved_class, options


def _resolve_surrogate_spec(raw_value: Any) -> SurrogateSpec:
    """Resolve a SurrogateSpec payload from YAML-friendly form."""
    if isinstance(raw_value, SurrogateSpec):
        return raw_value
    if not isinstance(raw_value, dict):
        raise ValueError(
            "'surrogate_spec' must be a mapping or an Ax SurrogateSpec instance."
        )

    payload = deepcopy(raw_value)
    payload["model_configs"] = [
        _resolve_model_config(config) for config in payload.get("model_configs", [])
    ]

    metric_to_model_configs = payload.get("metric_to_model_configs") or {}
    if metric_to_model_configs:
        payload["metric_to_model_configs"] = {
            metric_name: [_resolve_model_config(config) for config in configs]
            for metric_name, configs in metric_to_model_configs.items()
        }

    return SurrogateSpec(**payload)


def _resolve_model_config(raw_value: Any) -> ModelConfig:
    """Resolve a ModelConfig payload from YAML-friendly form."""
    if isinstance(raw_value, ModelConfig):
        return raw_value
    if not isinstance(raw_value, dict):
        raise ValueError(
            "Entries in 'model_configs' must be mappings or Ax ModelConfig instances."
        )

    payload = deepcopy(raw_value)

    if "botorch_model_class" in payload:
        payload["botorch_model_class"] = _resolve_symbol(
            payload["botorch_model_class"],
            registry=_BOTORCH_MODEL_CLASSES,
            kind="BoTorch model class",
        )

    if "mll_class" in payload:
        payload["mll_class"] = _resolve_symbol(
            payload["mll_class"],
            registry=_MLL_CLASSES,
            kind="GPyTorch marginal log likelihood class",
        )

    if "covar_module_class" in payload:
        payload["covar_module_class"] = _resolve_symbol(
            payload["covar_module_class"],
            registry=_COVAR_MODULE_CLASSES,
            kind="GPyTorch covariance module class",
        )

    if "likelihood_class" in payload:
        payload["likelihood_class"] = _resolve_symbol(
            payload["likelihood_class"],
            registry=_LIKELIHOOD_CLASSES,
            kind="GPyTorch likelihood class",
        )

    if "input_transform_classes" in payload and payload["input_transform_classes"] is not None:
        payload["input_transform_classes"] = [
            _resolve_symbol(
                transform_class,
                registry=_INPUT_TRANSFORM_CLASSES,
                kind="BoTorch input transform class",
            )
            for transform_class in payload["input_transform_classes"]
        ]

    if (
        "outcome_transform_classes" in payload
        and payload["outcome_transform_classes"] is not None
    ):
        payload["outcome_transform_classes"] = [
            _resolve_symbol(
                transform_class,
                registry=_OUTCOME_TRANSFORM_CLASSES,
                kind="BoTorch outcome transform class",
            )
            for transform_class in payload["outcome_transform_classes"]
        ]

    return ModelConfig(**payload)


def _resolve_symbol(
    value: Any,
    *,
    registry: dict[str, Any],
    kind: str,
) -> Any:
    """Resolve one configured symbol against a fixed registry."""
    if not isinstance(value, str):
        return value

    if value in registry:
        return registry[value]

    supported = ", ".join(sorted(registry))
    raise ValueError(f"Unsupported {kind} '{value}'. Supported values: {supported}.")
