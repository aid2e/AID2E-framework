# Example 3 : B0 far-forward tracking system

This folder integrates the optimization of B0 within the AID2E-framework.

Parameters: position of 4 disks (z1, z2, z3, z4).

Objective (placeholder) : geometrical lever arm.

## Validation state

- b0_ax_joblib.yml : 
    - fully validated through `aid2e validate` + `optimize`
    - `eic-shell` + `epic` loading managed
    - placeholder objective (lever arm) 

- b0_ax_panda.yml :
    - fully validated through `aid2e validate` + `optimize`
    - `eic-shell` + `epic` loading managed
    - placeholder objective (lever arm)
    - example: https://pandamon01.sdcc.bnl.gov/job?pandaid=4101255 

- b0_ax_slurm.yml :
    - iFarm only (so far)
    - fully validated through `aid2e validate` + `optimize`
    - `eic-shell` + `epic` loading managed
    - placeholder objective (lever arm)

- b0_pymoo_xxx : to be done 