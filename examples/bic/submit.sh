#!/bin/bash
#SBATCH --account=<account>
#SBATCH --partition=<partition>
#SBATCH --time=04:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=4
#SBATCH --mail-user=<your@email.com>
#SBATCH --mail-type=END,FAIL
#SBATCH --output=/where/the/stdout/goes
#SBATCH --error=/where/the/stderr/goes

aid2e optimize workflow.yml
