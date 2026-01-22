"""SCHEDULER API QUICK REFERENCE

Quick guide for using the AID2E scheduler system.

=============================================================================
BASIC USAGE
=============================================================================

1. Direct Instantiation
   -----------------------
   from aid2e.schedulers import JobLibScheduler
   from aid2e.utilities.configurations.scheduler_config import JobLibRunnerConfig
   
   config = JobLibRunnerConfig(n_jobs=4, backend='loky', timeout=600)
   scheduler = JobLibScheduler(config=config)
   
   result = scheduler.run_stage(
       stage_name='evaluate',
       job_definitions=[
           {
               'name': 'eval_1',
               'command': 'python scripts/compute.py',
               'payload': {'x': 1.0, 'y': 2.0},
               'outputs': [{'path': 'result.json', 'format': 'json'}]
           }
       ],
       parallelism_policy={'max_concurrent': 4, 'retry_max': 2, 'timeout_sec': 300},
       working_dir='/path/to/work'
   )
   
   print(f"Success: {result.success}")
   print(f"Jobs: {len(result.job_statuses)}")
   print(f"Artifacts: {result.artifacts}")

2. Via Registry
   -----------
   from aid2e.schedulers import get_scheduler
   
   SchedulerClass = get_scheduler('joblib')  # Get class from registry
   scheduler = SchedulerClass(config=...)
   result = scheduler.run_stage(...)

=============================================================================
DATA MODELS
=============================================================================

JobLibRunnerConfig
  - n_jobs: int = -1 (use all processors)
  - backend: str = 'loky' (loky, threading, multiprocessing)
  - timeout: Optional[int] = None (timeout per job in seconds)
  - verbose: int = 0 (verbosity level 0-11)

SchedulerConfiguration
  - runner_type: Literal['JobLibRunner', 'SlurmRunner', 'PanDAiDDSRunner']
  - joblib: Optional[JobLibRunnerConfig]
  - slurm: Optional[SlurmRunnerConfig]
  - panda: Optional[PanDAiDDSRunnerConfig]
  - max_retries: int = 3
  - output_location: str = './scheduler_output'
  - monitor_interval: int = 30

ParallelismPolicy (in StageDefinition)
  - max_concurrent: int = 4 (max jobs in parallel)
  - retry_max: int = 2 (retries on failure)
  - timeout_sec: int = 300 (per-job timeout)

JobStatus
  - job_id: str
  - status: str ('queued', 'running', 'completed', 'failed', 'cancelled')
  - return_code: Optional[int]
  - stdout: Optional[str]
  - stderr: Optional[str]
  - metrics: Optional[Dict[str, Any]]

StageExecutionResult
  - stage_name: str
  - job_statuses: List[JobStatus]
  - artifacts: Dict[str, Any] (path -> content)
  - success: bool
  - error_message: Optional[str]

=============================================================================
REGISTRY API
=============================================================================

register_scheduler(name: str, scheduler_class: Type[BaseScheduler]) -> None
  Register a new scheduler type
  
  Example:
    from my_schedulers import MyScheduler
    register_scheduler('my_scheduler', MyScheduler)

get_scheduler(name: str) -> Type[BaseScheduler]
  Get scheduler class by name
  Raises KeyError if not found
  
  Example:
    SchedulerClass = get_scheduler('joblib')
    scheduler = SchedulerClass(config=...)

list_registered_schedulers() -> Dict[str, Type[BaseScheduler]]
  Get all registered schedulers
  
  Example:
    for name, cls in list_registered_schedulers().items():
        print(f"{name}: {cls.__name__}")

is_scheduler_registered(name: str) -> bool
  Check if scheduler is registered
  
  Example:
    if is_scheduler_registered('slurm'):
        scheduler = get_scheduler('slurm')(config=...)

=============================================================================
JOB DEFINITION STRUCTURE
=============================================================================

job_def = {
    'name': 'job_name',                          # Required: job identifier
    'command': 'python script.py',              # Required: shell command
    'payload': {'key': 'value'},                # Optional: command arguments
    'resources': {'memory': '4GB'},             # Optional: resource spec
    'outputs': [                                # Optional: output artifacts
        {
            'path': 'result.json',
            'format': 'json'                    # json, yaml, csv
        }
    ]
}

Notes:
- command: Any shell-executable string (bash, python, etc)
- payload: Passed via JOB_PAYLOAD environment variable as JSON
- outputs: Paths relative to working_dir; collected after job completes
- resources: Executor-specific (JobLib ignores, SLURM uses for sbatch)

=============================================================================
PARALLEL EXECUTION EXAMPLES
=============================================================================

1. Execute 3 Jobs in Parallel (2 workers)
   -----------------------------------------
   scheduler = JobLibScheduler(JobLibRunnerConfig(n_jobs=2))
   
   result = scheduler.run_stage(
       stage_name='parallel_eval',
       job_definitions=[
           {'name': f'job_{i}', 'command': f'echo {i}', ...}
           for i in range(3)
       ]
   )
   # Two jobs run concurrently, third waits

2. Respect max_concurrent Policy
   ------------------------------------
   result = scheduler.run_stage(
       stage_name='stage',
       job_definitions=[...],
       parallelism_policy={'max_concurrent': 4, ...}
   )
   # JobLib n_jobs set to 4 during this stage

3. Timeout Per Job
   ----------------
   config = JobLibRunnerConfig(timeout=300)  # 5 minute timeout
   scheduler = JobLibScheduler(config=config)
   result = scheduler.run_stage(...)  # Each job killed after 5 min

=============================================================================
INTEGRATION WITH WORKFLOWS
=============================================================================

In WorkflowDefinition:
  stages=[
      StageDefinition(
          name='evaluate',
          jobs=[JobDefinition(...)],
          parallelism=ParallelismPolicy(max_concurrent=4),
          scheduler=SchedulerConfiguration(
              runner_type='JobLibRunner',
              joblib=JobLibRunnerConfig(n_jobs=-1)
          )
      )
  ]

In SchedulerConfiguration:
  config = SchedulerConfiguration(
      runner_type='JobLibRunner',
      joblib=JobLibRunnerConfig(n_jobs=4),
      max_retries=3
  )
  SchedulerClass = get_scheduler(config.runner_type)
  scheduler = SchedulerClass(config.joblib)

=============================================================================
ERROR HANDLING
=============================================================================

Failures:
  result = scheduler.run_stage(...)
  
  if not result.success:
      print(f"Error: {result.error_message}")
      for status in result.job_statuses:
          if status.status == 'failed':
              print(f"Job {status.job_id}: exit {status.return_code}")
              print(f"stderr: {status.stderr}")

Timeouts:
  Job timeouts appear as:
  - status.status == 'failed'
  - status.return_code == -1
  - status.stderr contains timeout message

Registry Errors:
  try:
      SchedulerClass = get_scheduler('nonexistent')
  except KeyError as e:
      print(f"Scheduler not registered: {e}")

=============================================================================
EXTENDING WITH CUSTOM SCHEDULER
=============================================================================

1. Create Custom Scheduler
   ----------------------
   from aid2e.schedulers import BaseScheduler, JobStatus, StageExecutionResult
   
   class MyScheduler(BaseScheduler):
       def run_stage(self, stage_name, job_definitions, parallelism_policy, working_dir):
           # Custom implementation
           return StageExecutionResult(
               stage_name=stage_name,
               job_statuses=[...],
               artifacts={...},
               success=True
           )
       
       def check_status(self, job_id):
           # Check job status
           return JobStatus(job_id=job_id, status='completed', return_code=0)
       
       def cancel_job(self, job_id):
           # Cancel job
           return False

2. Register Custom Scheduler
   -------------------------
   from aid2e.schedulers import register_scheduler
   
   register_scheduler('my_scheduler', MyScheduler)

3. Use Custom Scheduler
   --------------------
   from aid2e.schedulers import get_scheduler
   
   SchedulerClass = get_scheduler('my_scheduler')
   scheduler = SchedulerClass(config=...)
   result = scheduler.run_stage(...)

=============================================================================
FUTURE SCHEDULERS (Planned)
=============================================================================

SlurmScheduler
  runner_type: 'SlurmRunner'
  config: SlurmRunnerConfig
  - Submit jobs via sbatch
  - Monitor with squeue
  - Retrieve artifacts from compute nodes

PanDAiDDSScheduler
  runner_type: 'PanDAiDDSRunner'
  config: PanDAiDDSRunnerConfig
  - Submit to PanDA/iDDS distributed system
  - Job tracking via PanDA
  - Results from PanDA storage

=============================================================================
LOGGING
=============================================================================

Enable scheduler logging:
  import logging
  logging.basicConfig(level=logging.INFO)
  
  scheduler = JobLibScheduler()
  result = scheduler.run_stage(...)
  # Logs:
  # INFO: Running stage 'X' with N jobs
  # INFO: Max concurrent: Y, Max retries: Z
  # INFO: Executing job 'Y': command

=============================================================================
"""
