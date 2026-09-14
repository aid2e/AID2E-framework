# AID2E dRICH Example

Run dRICH detector-design optimization with AID2E. The main flow is:

```
workflow.yml -> aid2e optimize -> workflow stages -> objective plan -> optimizer update
```

## Files
- `workflow.yml`: example config optimizer, scheduler, and epic workflow
- `design.params`: geometry parameters and XML edit targets
- `drich_utils.py`: job payloads and objective aggregation
- `script/dRICHAna_bootstrap.cpp`: per-scan analysis code used by the `ana` stage

## ePIC Setup
It is recommended to use the branch of the fork containing a single-mirror dRICH, which is then compatible with the already built versions of EICrecon and IRT available in eic-shell:24.11.1-stable.

The following repository and branch hold the recommended default geometry for the optimization of the dRICH and will need to be downloaded and built prior to running.

Additionally, the dRICH analysis script will need to be built from within eic-shell prior to running the optimization, located in examples/epic/drich/script

```
git clone -b 24.11.1-drich-singlemirror https://github.com/cpecar/epic-geom-drich-mobo.git
./build_epic.sh epic-geom-drich-mobo "$EIC_SOFTWARE"
cd examples/epic/drich/script && make
```

## Run
```
aid2e optimize examples/epic/drich/workflow.yml
```

```mermaid
flowchart TB
  C["workflow.yml"] --> O["aid2e optimize"]
  O --> B["Schedule trial batch"]

  subgraph T["Run one trial workflow"]
    G["geo"]
    G --> S1["sim + rec 1"]
    G --> S2["sim + rec 2"]
    G --> SN["... 8 jobs"]

    S1 --> SF["sim + rec complete"]
    S2 --> SF
    SN --> SF

    SF --> A1["ana 1"]
    SF --> AN["... 4 jobs"]
    A1 --> M["collect objectives"]
    AN --> M
  end

  B --> T
  B --> N["Other trials<br/>same workflow"]
  M --> R["Collect batch results"]
  N --> R
  R --> U["Update optimizer"] --> O
```
