#!/usr/bin/env python3
"""
Worker Process - Executes jobs from the queue (Windows-safe)
"""

from __future__ import annotations

import os
import sys
import time
import signal
import platform
import subprocess
import multiprocessing as mp
from typing import Dict, Any
from pathlib import Path

# Ensure src/ is importable in spawned children
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from .config import Config
from .job_manager import JobManager
from utils.logger import setup_logger

logger = setup_logger(__name__)

# On Windows, be explicit: processes are spawned and must pickle targets/args
if platform.system() == "Windows":
    try:
        mp.set_start_method("spawn", force=True)
    except RuntimeError:
        # Start method may already be set by parent; that's fine.
        pass


def _cfg_to_primitives(cfg: Config) -> Dict[str, Any]:
    """Extract only picklable fields needed by workers."""
    return {
        "db_path": getattr(cfg, "db_path", "data/jobs.json"),
        "default_max_retries": int(getattr(cfg, "default_max_retries", 3)),
        "backoff_base": int(getattr(cfg, "backoff_base", 2)),
        "poll_interval": float(getattr(cfg, "poll_interval", 0.5)),
        "default_timeout": getattr(cfg, "default_timeout", None),
        "log_level": getattr(cfg, "log_level", "INFO"),
    }


def _cfg_from_primitives(d: Dict[str, Any]) -> Config:
    """Rebuild a Config instance from primitives (inside child)."""
    cfg = Config()
    for k, v in d.items():
        try:
            setattr(cfg, k, v)
        except Exception:
            pass
    return cfg


class Worker:
    """Individual worker process that executes jobs"""

    def __init__(self, worker_id: str, config: Config):
        self.worker_id = worker_id
        self.config = config
        self.job_manager = JobManager(config)
        self.running = True
        self.current_job = None

        # Setup signal handlers for graceful shutdown (child process)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        setup_logger(__name__).info(f"Worker {self.worker_id} received shutdown signal")
        self.running = False

    def run(self):
        """Main worker loop"""
        log = setup_logger(__name__)
        log.info(f"Worker {self.worker_id} started")

        while self.running:
            try:
                # Check for retryable jobs first
                for job in self.job_manager.get_retryable_jobs():
                    self.job_manager.reset_for_retry(job["id"])

                # Get next job
                job = self.job_manager.get_next_job(self.worker_id)

                if job:
                    self.current_job = job
                    self._execute_job(job)
                    self.current_job = None
                else:
                    # No jobs available, sleep briefly
                    time.sleep(float(self.config.poll_interval))

            except Exception as e:
                log.error(f"Worker {self.worker_id} error: {e}", exc_info=True)
                time.sleep(1)

        # Graceful shutdown
        if self.current_job:
            log.info(f"Worker {self.worker_id} finishing current job before exit")
            # Current job will complete in _execute_job

        log.info(f"Worker {self.worker_id} stopped")

    def _execute_job(self, job: dict):
        """
        Execute a job command

        Args:
            job: Job dictionary containing command and metadata
        """
        log = setup_logger(__name__)
        job_id = job["id"]
        command = job["command"]
        timeout = job.get("timeout") or getattr(self.config, "default_timeout", None)

        log.info(f"Worker {self.worker_id} executing job {job_id}: {command}")

        start_time = time.time()

        try:
            # Execute command with optional timeout
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout if (timeout and timeout > 0) else None,
                check=False,  # Don't raise on non-zero exit
            )

            execution_time = time.time() - start_time

            # Check exit code
            if result.returncode == 0:
                output = result.stdout.strip() if result.stdout else "Command executed successfully"
                self.job_manager.mark_completed(job_id, output, execution_time)
                log.info(f"Job {job_id} completed successfully in {execution_time:.2f}s")
            else:
                error = result.stderr.strip() if result.stderr else f"Command exited with code {result.returncode}"
                self.job_manager.mark_failed(job_id, error)
                log.warning(f"Job {job_id} failed with exit code {result.returncode}")

        except subprocess.TimeoutExpired:
            error = f"Job timed out after {timeout} seconds"
            self.job_manager.mark_failed(job_id, error)
            log.warning(f"Job {job_id} timed out after {timeout}s")

        except FileNotFoundError:
            error = f"Command not found: {command}"
            self.job_manager.mark_failed(job_id, error)
            log.warning(f"Job {job_id} failed: command not found")

        except Exception as e:
            error = f"Unexpected error: {str(e)}"
            self.job_manager.mark_failed(job_id, error)
            log.error(f"Job {job_id} failed with unexpected error: {e}", exc_info=True)


def _worker_entry(worker_id: str, cfg_primitives: Dict[str, Any]) -> None:
    """
    Top-level process entry (must be picklable).
    Rebuild Config/JobManager/logger in the child and run the loop.
    """
    # Child logger name can be unique per worker if you want
    setup_logger(f"{__name__}.{worker_id}")
    cfg = _cfg_from_primitives(cfg_primitives)
    Worker(worker_id, cfg).run()


class WorkerPool:
    """Manages multiple worker processes (Windows-safe)"""

    def __init__(self, config: Config, num_workers: int = 2):
        self.config = config
        self.num_workers = int(num_workers)
        self.processes = []

    def start(self):
        """Start all worker processes"""
        logger.info(f"Starting worker pool with {self.num_workers} workers")

        cfg_primitives = _cfg_to_primitives(self.config)

        for i in range(self.num_workers):
            worker_id = f"worker-{i+1}"
            # IMPORTANT: use top-level function & only primitives as args
            process = mp.Process(
                target=_worker_entry,
                args=(worker_id, cfg_primitives),
                name=worker_id,
                daemon=True,  # let OS clean up if parent dies
            )
            process.start()
            self.processes.append(process)
            logger.info(f"Started {worker_id} (PID: {process.pid})")

        # Wait for all processes
        for process in self.processes:
            process.join()

    def stop(self):
        """Stop all worker processes gracefully"""
        logger.info("Stopping worker pool...")

        # Send termination to all processes
        for process in self.processes:
            if process.is_alive():
                process.terminate()

        # Wait for graceful shutdown with timeout
        timeout = 30  # seconds
        start_time = time.time()

        for process in self.processes:
            remaining_time = timeout - (time.time() - start_time)
            if remaining_time > 0 and process.is_alive():
                process.join(timeout=remaining_time)

            # Force kill if still alive
            if process.is_alive():
                logger.warning(f"Force killing worker (PID: {process.pid})")
                process.kill()
                process.join()

        logger.info("All workers stopped")
