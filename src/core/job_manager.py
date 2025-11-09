"""
Job Manager - Handles job lifecycle and persistence
"""

import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List
from dateutil import parser as date_parser

from .config import Config
from utils.logger import setup_logger

logger = setup_logger(__name__)

class JobManager:
    """Manages job creation, storage, and lifecycle"""
    
    def __init__(self, config: Config):
        self.config = config
        self.db_path = Path(config.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize job database"""
        if not self.db_path.exists():
            self._save_db({'jobs': {}})
            logger.info(f"Initialized new database at {self.db_path}")
    
    def _load_db(self) -> Dict:
        """Load job database from disk"""
        try:
            with open(self.db_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load database: {e}")
            return {'jobs': {}}
    
    def _save_db(self, data: Dict):
        """Save job database to disk"""
        try:
            with open(self.db_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save database: {e}")
    
    def enqueue(
        self, 
        command: str, 
        max_retries: int = 3,
        priority: int = 0,
        timeout: Optional[int] = None,
        run_at: Optional[str] = None
    ) -> str:
        """
        Enqueue a new job
        
        Args:
            command: Shell command to execute
            max_retries: Maximum retry attempts
            priority: Job priority (higher = more important)
            timeout: Job timeout in seconds
            run_at: ISO format timestamp for scheduled execution
            
        Returns:
            Job ID
        """
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        job = {
            'id': job_id,
            'command': command,
            'state': 'pending',
            'priority': priority,
            'attempts': 0,
            'max_retries': max_retries,
            'created_at': now,
            'updated_at': now,
            'output': '',
            'error': '',
        }
        
        if timeout:
            job['timeout'] = timeout
        
        if run_at:
            # Validate and store scheduled time
            try:
                scheduled = date_parser.parse(run_at)
                job['run_at'] = scheduled.isoformat()
                job['state'] = 'scheduled'
            except Exception as e:
                logger.warning(f"Invalid run_at format: {e}, ignoring schedule")
        
        db = self._load_db()
        db['jobs'][job_id] = job
        self._save_db(db)
        
        logger.info(f"Enqueued job {job_id}: {command}")
        return job_id
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get job by ID"""
        db = self._load_db()
        return db['jobs'].get(job_id)
    
    def update_job(self, job_id: str, updates: Dict):
        """Update job fields"""
        db = self._load_db()
        
        if job_id not in db['jobs']:
            logger.warning(f"Attempted to update non-existent job {job_id}")
            return
        
        db['jobs'][job_id].update(updates)
        db['jobs'][job_id]['updated_at'] = datetime.now(timezone.utc).isoformat()
        self._save_db(db)
    
    def list_jobs(self, state: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """
        List jobs, optionally filtered by state
        
        Args:
            state: Filter by job state
            limit: Maximum number of jobs to return
            
        Returns:
            List of jobs
        """
        db = self._load_db()
        jobs = list(db['jobs'].values())
        
        if state:
            jobs = [j for j in jobs if j['state'] == state]
        
        # Sort by priority (desc) then created_at (desc)
        jobs.sort(key=lambda x: (-x.get('priority', 0), x['created_at']), reverse=True)
        
        return jobs[:limit]
    
    def get_next_job(self, worker_id: str) -> Optional[Dict]:
        """
        Get next available job for worker
        Uses locking to prevent duplicate processing
        
        Args:
            worker_id: Unique worker identifier
            
        Returns:
            Next job to process or None
        """
        db = self._load_db()
        now = datetime.now(timezone.utc)
        
        # Find pending jobs, sorted by priority
        pending_jobs = [
            j for j in db['jobs'].values()
            if j['state'] == 'pending'
        ]
        
        # Check scheduled jobs
        scheduled_jobs = [
            j for j in db['jobs'].values()
            if j['state'] == 'scheduled'
        ]
        
        for job in scheduled_jobs:
            try:
                run_at = date_parser.parse(job['run_at'])
                if run_at <= now:
                    job['state'] = 'pending'
                    pending_jobs.append(job)
            except Exception as e:
                logger.error(f"Error parsing run_at for job {job['id']}: {e}")
        
        if not pending_jobs:
            return None
        
        # Sort by priority (higher first), then created_at
        pending_jobs.sort(
            key=lambda x: (-x.get('priority', 0), x['created_at'])
        )
        
        # Lock the first available job
        job = pending_jobs[0]
        job['state'] = 'running'
        job['worker_id'] = worker_id
        job['started_at'] = now.isoformat()
        
        db['jobs'][job['id']] = job
        self._save_db(db)
        
        logger.info(f"Worker {worker_id} acquired job {job['id']}")
        return job
    
    def mark_completed(self, job_id: str, output: str, execution_time: float):
        """Mark job as completed"""
        self.update_job(job_id, {
            'state': 'completed',
            'output': output,
            'completed_at': datetime.now(timezone.utc).isoformat(),
            'execution_time': execution_time
        })
        logger.info(f"Job {job_id} completed successfully")
    
    def mark_failed(self, job_id: str, error: str):
        """
        Mark job as failed and handle retry logic
        Implements exponential backoff
        """
        job = self.get_job(job_id)
        if not job:
            return
        
        job['attempts'] += 1
        job['error'] = error
        
        if job['attempts'] >= job['max_retries']:
            # Move to DLQ
            job['state'] = 'dlq'
            job['dlq_at'] = datetime.now(timezone.utc).isoformat()
            logger.warning(f"Job {job_id} moved to DLQ after {job['attempts']} attempts")
        else:
            # Schedule retry with exponential backoff
            job['state'] = 'failed'
            backoff_delay = self.config.backoff_base ** job['attempts']
            job['retry_after'] = (
                datetime.now(timezone.utc).timestamp() + backoff_delay
            )
            logger.info(
                f"Job {job_id} failed (attempt {job['attempts']}/{job['max_retries']}), "
                f"retrying in {backoff_delay}s"
            )
        
        db = self._load_db()
        db['jobs'][job_id] = job
        db['jobs'][job_id]['updated_at'] = datetime.now(timezone.utc).isoformat()
        self._save_db(db)
    
    def get_retryable_jobs(self) -> List[Dict]:
        """Get failed jobs ready for retry"""
        db = self._load_db()
        now = datetime.now(timezone.utc).timestamp()
        
        retryable = []
        for job in db['jobs'].values():
            if job['state'] == 'failed' and job.get('retry_after', 0) <= now:
                retryable.append(job)
        
        return retryable
    
    def reset_for_retry(self, job_id: str):
        """Reset a failed job to pending state"""
        self.update_job(job_id, {
            'state': 'pending',
            'error': '',
            'retry_after': None
        })
        logger.info(f"Job {job_id} reset for retry")
    
    def retry_job(self, job_id: str) -> bool:
        """Manually retry a job from DLQ or failed state"""
        job = self.get_job(job_id)
        
        if not job or job['state'] not in ['failed', 'dlq']:
            return False
        
        self.update_job(job_id, {
            'state': 'pending',
            'attempts': 0,
            'error': '',
            'retry_after': None
        })
        
        logger.info(f"Job {job_id} manually reset for retry")
        return True
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or scheduled job"""
        job = self.get_job(job_id)
        
        if not job or job['state'] not in ['pending', 'scheduled']:
            return False
        
        self.update_job(job_id, {
            'state': 'cancelled',
            'cancelled_at': datetime.now(timezone.utc).isoformat()
        })
        
        logger.info(f"Job {job_id} cancelled")
        return True
    
    def get_stats(self) -> Dict:
        """Get queue statistics"""
        db = self._load_db()
        jobs = list(db['jobs'].values())
        
        total = len(jobs)
        by_state = {}
        
        for job in jobs:
            state = job['state']
            by_state[state] = by_state.get(state, 0) + 1
        
        completed = by_state.get('completed', 0)
        failed = by_state.get('failed', 0) + by_state.get('dlq', 0)
        
        success_rate = (completed / total * 100) if total > 0 else 0
        
        # Calculate average execution time
        exec_times = [
            j.get('execution_time', 0) 
            for j in jobs 
            if j['state'] == 'completed' and 'execution_time' in j
        ]
        avg_exec_time = sum(exec_times) / len(exec_times) if exec_times else 0
        
        return {
            'total': total,
            'pending': by_state.get('pending', 0),
            'running': by_state.get('running', 0),
            'completed': completed,
            'failed': by_state.get('failed', 0),
            'dlq': by_state.get('dlq', 0),
            'scheduled': by_state.get('scheduled', 0),
            'success_rate': success_rate,
            'avg_execution_time': avg_exec_time
        }
    
    def purge_completed(self) -> int:
        """Remove all completed jobs"""
        db = self._load_db()
        
        before_count = len(db['jobs'])
        db['jobs'] = {
            job_id: job 
            for job_id, job in db['jobs'].items()
            if job['state'] != 'completed'
        }
        after_count = len(db['jobs'])
        
        self._save_db(db)
        
        purged = before_count - after_count
        logger.info(f"Purged {purged} completed jobs")
        
        return purged
