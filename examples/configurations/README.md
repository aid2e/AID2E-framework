# Example Configuration Files

This directory contains example configuration files for the AID2E framework.

## Available Examples

### 1. DTLZ2 Toy Problem (`dtlz2_optimization.yml`)
A basic multi-objective optimization of the DTLZ2 benchmark problem with 10 variables and 2 objectives.

**Usage:**
```bash
aid2e load examples/configurations/dtlz2_optimization.yml
```

**Features:**
- Generic design space configuration
- Parameter constraints
- Multi-objective Bayesian optimization
- Parallel evaluations

### 2. ePIC Tracking Detector (`epic_tracking_optimization.yml`)
Optimization of ePIC detector tracking system with XML parameter integration.

**Usage:**
```bash
aid2e load examples/configurations/epic_tracking_optimization.yml
```

**Features:**
- ePIC-specific design configuration
- XML file modifications
- Multiple parameter groups (vertex barrel, silicon tracker)
- Complex geometric constraints
- Optimization groups for selective parameter optimization
- Environment setup for ePIC/EIC software

## Configuration Structure

All configuration files follow this structure:

```yaml
problem:
  name: "Problem Name"
  problem_type: "PROBLEM_TYPE"  # e.g., DTLZ2, EPIC_TRACKING
  output_location: "./output/dir"
  work_location: "./work/dir"
  
  design_config:
    # For generic problems:
    design_parameters: {...}
    
    # For ePIC problems:
    epic_design_parameters: {...}
    
    parameter_constraints: [...]
  
  # Optional: for ePIC problems
  epic_configuration:
    singularity_image: "path/to/image.sif"
    epic_install: "path/to/epic"

optimization:
  name: "Optimization Name"
  description: "Description"
  
  optimizer:
    name: "MOBO"  # or "Genetic", "RandomSearch", etc.
    type: "Bayesian"  # or "evolutionary", "grid", etc.
    parameters: {...}
  
  objectives: [...]
  constraints: [...]
  
  n_iterations: 100
  n_initial_samples: 20
  parallel_evaluations: 4
```

## Testing Configurations

To validate a configuration without running:
```bash
aid2e load config.yml --validate-only
```

To see detailed information:
```bash
aid2e info config.yml
```
