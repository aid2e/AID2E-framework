# User Guide Overview

AID2E describes detector optimization workflows with canonical full
configuration files. A full config defines:

- the problem, design space, objectives, and output paths
- the optimizer backend and iteration settings
- the scheduler used to submit workflow trials
- the workflow stages used to evaluate each optimizer candidate

For the current CLI path, use:

```bash
aid2e optimize config.yml --validate-only
aid2e optimize config.yml
```

`aid2e optimize` owns the full optimization loop: load config, build the
optimizer and scheduler, execute one workflow per optimizer candidate, collect
declared objectives, update the optimizer, and write result artifacts.
