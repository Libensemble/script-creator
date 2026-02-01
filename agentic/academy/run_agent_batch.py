#!/usr/bin/env python3
"""
Academy agent for running libEnsemble agent tests as batch jobs.

This script:
1. Submits batch jobs to Aurora (or runs locally for testing)
2. Runs libe_agent_basic_auto.py as the inner agent
3. Designed to support multiple job types with different node counts

Usage:
    Local:  python run_agent_batch.py
    Aurora: ACADEMY_ENDPOINT=<endpoint_id> python run_agent_batch.py
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import os
import subprocess
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from academy.agent import action
from academy.agent import Agent
from academy.exchange.cloud.client import HttpExchangeFactory
from academy.handle import Handle
from academy.logging import init_logging
from academy.manager import Manager
from globus_compute_sdk import Executor as GCExecutor


# =============================================================================
# CONFIGURATION - Set these before running
# =============================================================================

# OpenAI API key for the inner agent
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

# PBS configuration
PBS_PROJECT = 'myproject'      # -A flag
PBS_QUEUE = 'debug'            # -q flag
PBS_WALLTIME = '00:15:00'      # -l walltime
PBS_MAX_NODES = 2              # -l select (max nodes the agent can use)

# Inner agent configuration
INNER_AGENT_SCRIPT = 'libe_agent_basic_auto.py'
TEST_SCRIPTS_DIR = 'tests/scripts_with_errors'

# =============================================================================

EXCHANGE_ADDRESS = 'https://exchange.academy-agents.org'
logger = logging.getLogger(__name__)


class JobConfig:
    """Configuration for a batch job."""
    def __init__(
        self,
        job_type: str,
        nodes: int,
        walltime: str = PBS_WALLTIME,
        queue: str = PBS_QUEUE,
    ):
        self.job_type = job_type
        self.nodes = min(nodes, PBS_MAX_NODES)
        self.walltime = walltime
        self.queue = queue


class BatchJobAgent(Agent):
    """Agent that submits and manages batch jobs."""

    def __init__(self) -> None:
        super().__init__()
        self.job_history = []

    @action
    async def run_agent_test(self, job_config: dict) -> dict:
        """
        Run the inner agent test.
        
        In remote mode: submits a PBS batch job
        In local mode: runs the inner agent directly
        """
        config = JobConfig(**job_config)
        
        if 'PBS_O_WORKDIR' in os.environ or self._is_remote():
            return await self._run_batch_job(config)
        else:
            return await self._run_local(config)

    async def _run_local(self, config: JobConfig) -> dict:
        """Run the inner agent locally (for testing)."""
        logger.info(f'Running locally: {config.job_type} with {config.nodes} nodes')
        
        # Find the inner agent script
        script_dir = Path(__file__).parent.parent
        agent_script = script_dir / INNER_AGENT_SCRIPT
        test_dir = script_dir / TEST_SCRIPTS_DIR
        
        if not agent_script.exists():
            return {
                'status': 'error',
                'message': f'Agent script not found: {agent_script}',
            }
        
        if not test_dir.exists():
            return {
                'status': 'error',
                'message': f'Test scripts not found: {test_dir}',
            }
        
        # Set up environment
        env = os.environ.copy()
        if OPENAI_API_KEY:
            env['OPENAI_API_KEY'] = OPENAI_API_KEY
        
        # Run the inner agent
        cmd = ['python', str(agent_script), '--scripts', str(test_dir)]
        logger.info(f'Executing: {" ".join(cmd)}')
        
        result = subprocess.run(
            cmd,
            cwd=script_dir,
            capture_output=True,
            text=True,
            env=env,
        )
        
        success = result.returncode == 0
        self.job_history.append({
            'job_type': config.job_type,
            'nodes': config.nodes,
            'success': success,
        })
        
        return {
            'status': 'success' if success else 'failed',
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
        }

    async def _run_batch_job(self, config: JobConfig) -> dict:
        """Submit and run a PBS batch job."""
        logger.info(f'Submitting batch job: {config.job_type} with {config.nodes} nodes')
        
        # Generate PBS script
        pbs_script = self._generate_pbs_script(config)
        pbs_file = Path('run_job.pbs')
        pbs_file.write_text(pbs_script)
        
        # Submit the job
        result = subprocess.run(
            ['qsub', str(pbs_file)],
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            return {
                'status': 'submit_failed',
                'stderr': result.stderr,
            }
        
        job_id = result.stdout.strip()
        logger.info(f'Submitted job: {job_id}')
        
        # Wait for job completion (poll qstat)
        await self._wait_for_job(job_id)
        
        # Read results
        output_file = Path('job_output.txt')
        output = output_file.read_text() if output_file.exists() else 'No output'
        
        self.job_history.append({
            'job_type': config.job_type,
            'nodes': config.nodes,
            'job_id': job_id,
        })
        
        return {
            'status': 'completed',
            'job_id': job_id,
            'output': output,
        }

    def _generate_pbs_script(self, config: JobConfig) -> str:
        """Generate a PBS batch script."""
        return f"""#!/bin/bash -l
#PBS -l select={config.nodes}
#PBS -l walltime={config.walltime}
#PBS -q {config.queue}
#PBS -A {PBS_PROJECT}
#PBS -o job_output.txt
#PBS -e job_error.txt

module load frameworks

export MPICH_GPU_SUPPORT_ENABLED=1
export OPENAI_API_KEY="{OPENAI_API_KEY}"

cd $PBS_O_WORKDIR

python {INNER_AGENT_SCRIPT} --scripts {TEST_SCRIPTS_DIR} > job_output.txt 2>&1
"""

    async def _wait_for_job(self, job_id: str, poll_interval: int = 10) -> None:
        """Wait for a PBS job to complete."""
        while True:
            result = subprocess.run(
                ['qstat', job_id],
                capture_output=True,
                text=True,
            )
            # Job no longer in queue means it completed
            if result.returncode != 0 or job_id not in result.stdout:
                break
            await asyncio.sleep(poll_interval)

    def _is_remote(self) -> bool:
        """Check if running on a remote system (Aurora)."""
        # Check for common HPC environment indicators
        return any(var in os.environ for var in ['PBS_NODEFILE', 'SLURM_JOB_ID'])

    @action
    async def get_job_history(self) -> list:
        """Return the history of jobs run by this agent."""
        return self.job_history


class WorkflowAgent(Agent):
    """
    Coordinator agent for multi-stage workflows.
    
    Future use: run sampling (many nodes) then optimization (fewer nodes).
    """

    def __init__(self, batch_agent: Handle[BatchJobAgent]) -> None:
        super().__init__()
        self.batch_agent = batch_agent

    @action
    async def run_single_test(self, nodes: int = 1) -> dict:
        """Run a single agent test."""
        result = await self.batch_agent.run_agent_test({
            'job_type': 'single_test',
            'nodes': nodes,
        })
        return result

    @action
    async def run_sampling_then_optimize(
        self,
        sampling_nodes: int,
        optimize_nodes: int,
    ) -> dict:
        """
        Run sampling with many nodes, then optimization with fewer.
        
        Future implementation for multi-stage workflows.
        """
        # Stage 1: Sampling
        logger.info(f'Stage 1: Sampling with {sampling_nodes} nodes')
        sampling_result = await self.batch_agent.run_agent_test({
            'job_type': 'sampling',
            'nodes': sampling_nodes,
        })
        
        if sampling_result.get('status') != 'success':
            return {
                'status': 'failed',
                'stage': 'sampling',
                'result': sampling_result,
            }
        
        # Stage 2: Optimization
        logger.info(f'Stage 2: Optimization with {optimize_nodes} nodes')
        optimize_result = await self.batch_agent.run_agent_test({
            'job_type': 'optimization',
            'nodes': optimize_nodes,
        })
        
        return {
            'status': 'completed',
            'sampling': sampling_result,
            'optimization': optimize_result,
        }


async def main() -> int:
    init_logging(logging.INFO)

    # Check for required configuration
    if not OPENAI_API_KEY:
        logger.warning('OPENAI_API_KEY not set - inner agent may fail')

    if 'ACADEMY_ENDPOINT' in os.environ:
        executor = GCExecutor(os.environ['ACADEMY_ENDPOINT'])
        mode = 'Remote (Aurora)'
    else:
        mp_context = multiprocessing.get_context('spawn')
        executor = ProcessPoolExecutor(
            max_workers=3,
            initializer=init_logging,
            mp_context=mp_context,
        )
        mode = 'Local'

    logger.info(f'Running in {mode} mode')

    async with await Manager.from_exchange_factory(
        factory=HttpExchangeFactory(
            EXCHANGE_ADDRESS,
            auth_method='globus',
        ),
        executors=executor,
    ) as manager:
        # Launch agents
        batch_agent = await manager.launch(BatchJobAgent)
        workflow_agent = await manager.launch(
            WorkflowAgent,
            args=(batch_agent,),
        )

        # Run a single test
        logger.info('Starting agent test run')
        result = await workflow_agent.run_single_test(nodes=PBS_MAX_NODES)
        
        logger.info(f'Result: {result}')
        
        # Write results
        with open('batch_result.txt', 'w') as f:
            f.write('=' * 60 + '\n')
            f.write(f'Mode: {mode}\n')
            f.write(f'Status: {result.get("status", "unknown")}\n')
            if 'stdout' in result:
                f.write(f'\nOutput:\n{result["stdout"]}\n')
            if 'stderr' in result and result['stderr']:
                f.write(f'\nErrors:\n{result["stderr"]}\n')
            f.write('=' * 60 + '\n')
        
        exit_code = 0 if result.get('status') == 'success' else 1
        return exit_code

    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
