# Developer notes

Implementation details and design choices. Setup and usage stay in the
[User Guide](../configuration.md).

- [Configuration](configuration.md): loaders and validation.
- [CLI and runtime](cli.md): orchestration and reporting.
- [Optimizers](optimizers.md): backend contracts, constraints, and state.
- [Schedulers](schedulers.md): execution, registration, and artifacts.
- [Workflows and stacks](workflows.md): contexts, objective plans, and geometry.

To preview or build the docs, install `.[docs]`, then run `mkdocs serve` or
`mkdocs build`. Pages are listed in `mkdocs.yml`; the existing GitHub Actions
workflow publishes changes from `main`.
