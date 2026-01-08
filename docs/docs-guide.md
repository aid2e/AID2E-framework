# AID2E Documentation Guide

This guide explains how to generate, preview, and deploy the AID2E documentation site using MkDocs.

## Prerequisites
- Python 3.8+
- MkDocs tooling (install via project extras):

```bash
pip install -e ".[docs]"
```

## Quick Start
- Preview locally (live-reload on changes):

```bash
./scripts/docs-serve.sh
```

- Build static site into `site/`:

```bash
./scripts/docs-build.sh
```

- Deploy to GitHub Pages (main branch):

```bash
./scripts/docs-deploy-ghpages.sh
```

## Project Layout
- MkDocs config: `mkdocs.yml` (repo root)
- Markdown sources: `docs/` (this directory)
- Built site output: `site/` (created on build)

## Writing Docs
- Add new pages under `docs/` as `.md` files.
- Update navigation in `mkdocs.yml` under the `nav:` section.
- Use Markdown and admonitions (notes, tips) supported by Material theme.

## API Reference (mkdocstrings)
MkDocs is configured to use `mkdocstrings` for Python API docs. Ensure modules are importable:

- Core: `packages/aid2e-core/src`
- Optimizers: `packages/aid2e-optimizers/src`
- Schedulers: `packages/aid2e-schedulers/src`
- Utilities: `packages/aid2e-utilities/src`

## Troubleshooting
- If `mkdocs` is not found, install docs extras: `pip install -e ".[docs]"`.
- If API pages fail to render, verify import paths in `mkdocs.yml` `setup_commands` and that packages are installed in editable mode: `pip install -e .`.
- GitHub Pages must be enabled in the repository settings to deploy with `gh-deploy`.
