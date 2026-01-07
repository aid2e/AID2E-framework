# AID2E Framework

AI assisted Detector Design for EIC (AID2E) is a modular toolkit for building detector design and optimization workflows. Documentation (To be up): https://aid2e.github.io/AID2E-framework

## Project Structure

- `docs/` user-guide, tutorials, API reference, and assets published to the docs site
- `examples/` runnable configs and templates for end-to-end workflows (EPIC, MOBO, DTLZ2, etc.)
- `packages/` monorepo packages (installable wheels)
  - `aid2e-core/` core domain models, config parsing/validation, shared CLI entrypoints
  - `aid2e-optimizers/` optimization algorithms and interfaces (MOBO/MOEA)
  - `aid2e-schedulers/` scheduler adapters (joblib, panda, slurm) with a uniform submission API
  - `aid2e-utilities/` cross-cutting helpers (config templating, EPIC utilities)
- `tests/` top-level integration tests exercising cross-package workflows
- `work/`, `output/` generated artifacts from runs; `ignore/` holds legacy configs slated for migration

## Development and Integration Plan

- **Contracts first:** Stabilize core config schemas and typed models in `aid2e-core`; keep optimizer and scheduler interfaces defined here to avoid circular dependencies.
- **Plugin discovery:** Expose optimizer and scheduler implementations via Python entry points (e.g., `aid2e.optimizers`, `aid2e.schedulers`) so runtime components can be loaded dynamically.
- **Package boundaries:**
  - `aid2e-optimizers` depends only on `aid2e-core`; no direct coupling to schedulers.
  - `aid2e-schedulers` depends only on `aid2e-core`; keep job submission fakes/mocks for tests.
  - `aid2e-utilities` houses optional helpers; promote stable pieces into `aid2e-core` over time.
- **Testing strategy:**
  - Unit tests live in each package under `tests/` with deterministic fixtures mirroring `examples/` assets.
  - Top-level `tests/` run cross-package integration (optimizer + scheduler + core configs) to guard compatibility.
- **Versioning and releases:** Align package versions (0.0.x initially) and release in lockstep when core contracts change. Optionally publish a meta-package that pins the set, or provide extras such as `pip install aid2e-core[optimizers,schedulers,utilities]`.
- **Documentation and examples:** Keep `examples/` runnable; link examples into `docs/` tutorials; generate API reference from docstrings; ensure package READMEs point to relevant docs sections.

## Milestone Plan and Current Progress

- **Current focus:** aid2e-utilities toy Bayesian Optimization example with Ax to validate configs and optimizer plumbing.
- **Upcoming sequence:** ePIC configuration tracker, scheduler integration, then expanding the optimizer catalog.
- **Documentation:** keep tutorials and examples aligned with each milestone; plan to open issues with subtasks for tracking.

Progress checklist:
- [x] design_config base — done
- [x] problem_config base — done
- [ ] optimizer config base — to do
- [ ] scheduler config base — to do
- [ ] container config base — to do
- [ ] workflow config base — to do
- [ ] scheduler (GitHub repo) integration — to do
- [ ] epic_design_config — to do
- [ ] epic_problem_config — to do
- [ ] epic workflow config — to do

## Getting Started

1) Install from source or individual wheels under `packages/`.
2) Run a basic example (e.g., `examples/basic`) to verify the toolchain end to end.
3) Explore tutorials and user guide in `docs/` for EPIC tracking and multi-objective optimization workflows.

## Contributing

- Follow package boundaries and interface contracts described above.
- Add tests alongside new features and update relevant examples.
- Coordinate API changes across packages and update docs before release.