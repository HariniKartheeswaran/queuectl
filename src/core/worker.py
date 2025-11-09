"""
Worker Process - Executes jobs from the queue
"""

import time
import signal
import subprocess
import multiprocessing as mp
from datetime import datetime
from typing import Optional

from .config import Config
from .job_manager import JobManager
from utils.logger import setup_logger

logger = setup_logger(__name__)

class Worker:
    """Individual worker process that executes jobs"""
    
    def __init__(self, worker_id: str, config: Config):
        self.worker_id = worker_id
        self.config = config
        self.job_manager = JobManager(config)
        self.running = True
        self.current_job = None
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Worker {self.worker_id} received shutdown signal")
        self.running = False
    
    def run(self):
        """Main worker loop"""
        logger.info(f"Worker {self.worker_id} started")
        
        while self.running:
            try:
                # Check for retryable jobs first
                retryable_jobs = self.job_manager.get_retryable_jobs()
                for job in retryable_jobs:
                    self.job_manager.reset_for_retry(job['id'])
                
                # Get next job
                job = self.job_manager.get_next_job(self.worker_id)
                
                if job:
                    self.current_job = job
                    self._execute_job(job)
                    self.current_job = None
                else:
                    # No jobs available, sleep briefly
                    time.sleep(self.config.poll_interval)
                    
            except Exception as e:
                logger.error(f"Worker {self.worker_id} error: {e}", exc_info=True)
                time.sleep(1)
        
        # Graceful shutdown
        if self.current_job:
            logger.info(f"Worker {self.worker_id} finishing current job before exit")
            # Current job will complete in _execute_job
        
        logger.info(f"Worker {self.worker_id} stopped")
    
    def _execute_job(self, job: dict):
        """
        Execute a job command
        
        Args:
            job: Job dictionary containing command and metadata
        """
        job_id = job['id']
        command = job['command']
        timeout = job.get('timeout')
        
        logger.info(f"Worker {self.worker_id} executing job {job_id}: {command}")
        
        start_time = time.time()
        
        try:
            # Execute command with optional timeout
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False  # Don't raise on non-zero exit
            )
            
            execution_time = time.time() - start_time
            
            # Check exit code
            if result.returncode == 0:
                # Success
                output = result.stdout.strip() if result.stdout else "Command executed successfully"
                self.job_manager.mark_completed(job_id, output, execution_time)
                logger.info(
                    f"Job {job_id} completed successfully in {execution_time:.2f}s"
                )
            else:
                # Command failed
                error = result.stderr.strip() if result.stderr else f"Command exited with code {result.returncode}"
                self.job_manager.mark_failed(job_id, error)
                logger.warning(
                    f"Job {job_id} failed with exit code {result.returncode}"
                )
                
        except subprocess.TimeoutExpired:
            # Job timeout
            execution_time = time.time() - start_time
            error = f"Job timed out after {timeout} seconds"
            self.job_manager.mark_failed(job_id, error)
            logger.warning(f"Job {job_id} timed out after {timeout}s")
            
        except FileNotFoundError:
            # Command not found
            execution_time = time.time() - start_time
            error = f"Command not found: {command}"
            self.job_manager.mark_failed(job_id, error)
            logger.warning(f"Job {job_id} failed: command not found")
            
        except Exception as e:
            # Unexpected error
            execution_time = time.time() - start_time
            error = f"Unexpected error: {str(e)}"
            self.job_manager.mark_failed(job_id, error)
            logger.error(f"Job {job_id} failed with unexpected error: {e}", exc_info=True)


class WorkerPool:
    """Manages multiple worker processes"""
    
    def __init__(self, config: Config, num_workers: int = 2):
        self.config = config
        self.num_workers = num_workers
        self.workers = []
        self.processes = []
    
    def start(self):
        """Start all worker processes"""
        logger.info(f"Starting worker pool with {self.num_workers} workers")
        
        for i in range(self.num_workers):
            worker_id = f"worker-{i+1}"
            process = mp.Process(
                target=self._run_worker,
                args=(worker_id, self.config)
            )
            process.start()
            self.processes.append(process)
            logger.info(f"Started {worker_id} (PID: {process.pid})")
        
        # Wait for all processes
        for process in self.processes:
            process.join()
    
    def _run_worker(self, worker_id: str, config: Config):
        """Worker process entry point"""
        worker = Worker(worker_id, config)
        worker.run()
    
    def stop(self):
        """Stop all worker processes gracefully"""
        logger.info("Stopping worker pool...")
        
        # Send termination signal to all processes
        for process in self.processes:
            if process.is_alive():
                process.terminate()
        
        # Wait for graceful shutdown with timeout
        timeout = 30  # 30 seconds for graceful shutdown
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
