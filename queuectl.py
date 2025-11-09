#!/usr/bin/env python3
"""
QueueCTL - Advanced Background Job Queue System
A production-grade CLI-based job queue with worker management, 
exponential backoff, and Dead Letter Queue support.
"""

import click
import sys
import json
import signal
from pathlib import Path
import re

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from core.job_manager import JobManager
from core.worker import WorkerPool
from core.config import Config
from utils.logger import setup_logger
from web.dashboard import start_dashboard

logger = setup_logger(__name__)

# Global worker pool for graceful shutdown
active_worker_pool = None


def _quiet_json_requested() -> bool:
    """
    Returns True iff argv looks like: queuectl.py enqueue ... (--quiet|-q) ...
    Used to silence logs before JobManager is constructed so JSON output is clean.
    """
    argv = sys.argv[1:]
    if 'enqueue' not in argv:
        return False
    try:
        i = argv.index('enqueue')
    except ValueError:
        return False
    tail = argv[i + 1:]
    return ('--quiet' in tail) or ('-q' in tail)


def signal_handler(signum, frame):
    """Handle Ctrl+C for worker stop"""
    global active_worker_pool
    if active_worker_pool:
        click.echo("\n⏳ Stopping workers gracefully...")
        active_worker_pool.stop()
        sys.exit(0)


@click.group()
@click.pass_context
def cli(ctx):
    """QueueCTL - Advanced Background Job Queue System"""
    # Silence logs early if 'enqueue --quiet' detected
    if _quiet_json_requested():
        import logging
        logging.disable(logging.CRITICAL)

    ctx.ensure_object(dict)
    ctx.obj['config'] = Config()
    ctx.obj['job_manager'] = JobManager(ctx.obj['config'])


@cli.command()
@click.argument('command')
@click.option('--max-retries', '-r', default=None, type=int, help='Maximum retry attempts')
@click.option('--priority', '-p', default=0, help='Job priority (higher = more important)')
@click.option('--timeout', '-t', default=None, type=int, help='Job timeout in seconds')
@click.option('--run-at', default=None, help='Schedule job to run at specific time (ISO format)')
@click.option('--quiet', '-q', is_flag=True, help='Suppress logs, output only JSON')
@click.pass_context
def enqueue(ctx, command, max_retries, priority, timeout, run_at, quiet):
    """Add a new job to the queue"""
    job_manager = ctx.obj['job_manager']
    config = ctx.obj['config']
    
    if max_retries is None:
        max_retries = config.default_max_retries
    
    if quiet:
        import logging
        logging.disable(logging.CRITICAL)
    
    job_id = job_manager.enqueue(
        command=command,
        max_retries=max_retries,
        priority=priority,
        timeout=timeout,
        run_at=run_at
    )
    
    if quiet:
        import logging
        logging.disable(logging.NOTSET)
    
    output = {
        "id": job_id,
        "command": command,
        "state": "scheduled" if run_at else "pending",
        "priority": priority,
        "max_retries": max_retries
    }
    if run_at:
        output["run_at"] = run_at
    if timeout:
        output["timeout"] = timeout
    
    click.echo(json.dumps(output, indent=2))


@cli.group()
def worker():
    """Worker management commands"""
    pass


@worker.command('start')
@click.option('--count', '-c', default=2, help='Number of worker processes')
@click.option('--backoff-base', '-b', default=2, help='Exponential backoff base')
@click.pass_context
def worker_start(ctx, count, backoff_base):
    """Start one or more workers"""
    global active_worker_pool
    
    config = ctx.obj['config']
    config.backoff_base = backoff_base
    
    click.echo(f"Starting {count} worker(s) with backoff base {backoff_base}")
    click.echo("Press Ctrl+C to stop workers gracefully...")
    
    signal.signal(signal.SIGINT, signal_handler)
    active_worker_pool = WorkerPool(config, num_workers=count)
    
    try:
        active_worker_pool.start()
    except KeyboardInterrupt:
        click.echo("\nStopping workers gracefully...")
        active_worker_pool.stop()
        click.echo("All workers stopped")


@worker.command('stop')
@click.pass_context
def worker_stop(ctx):
    """Stop running workers gracefully"""
    job_manager = ctx.obj['job_manager']
    running_jobs = job_manager.list_jobs(state='running')
    
    if not running_jobs:
        click.echo("INFO: No workers currently running")
        return
    
    click.echo(f"Found {len(running_jobs)} running job(s)")
    click.echo("To stop workers, use Ctrl+C in the worker terminal")
    click.echo("Workers will complete current jobs before stopping")


@cli.command()
@click.pass_context
def status(ctx):
    """Show summary of all job states & active workers"""
    job_manager = ctx.obj['job_manager']
    stats = job_manager.get_stats()
    
    click.echo("\nQueue Status")
    click.echo("=" * 60)
    click.echo(f"Total Jobs:       {stats['total']}")
    click.echo(f"Pending:          {stats['pending']}")
    click.echo(f"Running:          {stats['running']}")
    click.echo(f"Completed:        {click.style(str(stats['completed']), fg='green')}")
    click.echo(f"Failed:           {click.style(str(stats['failed']), fg='yellow')}")
    click.echo(f"Dead Letter:      {click.style(str(stats['dlq']), fg='red')}")
    click.echo(f"Scheduled:        {stats.get('scheduled', 0)}")
    click.echo(f"\nSuccess Rate:     {stats['success_rate']:.1f}%")
    click.echo(f"Avg Exec Time:    {stats['avg_execution_time']:.2f}s")
    click.echo()
    
    running_jobs = job_manager.list_jobs(state='running')
    if running_jobs:
        click.echo(f"Active Workers: {len(running_jobs)}")
        for job in running_jobs:
            worker_id = job.get('worker_id', 'unknown')
            click.echo(f"  • {worker_id}: {job['command'][:50]}")
    else:
        click.echo("Active Workers: 0")


@cli.command('list')
@click.option('--state', '-s', help='Filter by state (pending/running/completed/failed/dlq)')
@click.option('--limit', '-l', default=20, help='Maximum number of jobs to display')
@click.pass_context
def list_jobs(ctx, state, limit):
    """List jobs by state"""
    job_manager = ctx.obj['job_manager']
    jobs = job_manager.list_jobs(state=state, limit=limit)
    
    if not jobs:
        click.echo("No jobs found")
        return
    
    click.echo(f"\nJobs List ({len(jobs)} total)")
    click.echo("=" * 110)
    click.echo(f"{'ID':<36} {'State':<12} {'Priority':<10} {'Attempts':<12} {'Command':<30}")
    click.echo("-" * 110)
    
    for job in jobs:
        job_id = job['id'][:35]
        state_str = job['state']
        priority = str(job.get('priority', 0))
        attempts = f"{job['attempts']}/{job['max_retries']}"
        command = job['command'][:29]
        
        if state_str == 'completed':
            state_str = click.style(state_str, fg='green')
        elif state_str in ('failed', 'dlq'):
            state_str = click.style(state_str, fg='red')
        elif state_str == 'running':
            state_str = click.style(state_str, fg='yellow')
        
        click.echo(f"{job_id:<36} {state_str:<21} {priority:<10} {attempts:<12} {command:<30}")


@cli.group()
def dlq():
    """Dead Letter Queue management"""
    pass


@dlq.command('list')
@click.pass_context
def dlq_list(ctx):
    """View DLQ jobs"""
    job_manager = ctx.obj['job_manager']
    jobs = job_manager.list_jobs(state='dlq')
    
    if not jobs:
        click.echo("Dead Letter Queue is empty")
        return
    
    click.echo(f"\nDead Letter Queue ({len(jobs)} jobs)")
    click.echo("=" * 100)
    
    for job in jobs:
        click.echo(f"\nJob ID: {job['id']}")
        click.echo(f"Command: {job['command']}")
        click.echo(f"Attempts: {job['attempts']}/{job['max_retries']}")
        click.echo(f"Last Error: {job.get('error', 'Unknown')[:100]}")
        click.echo(f"Created: {job['created_at']}")
        click.echo(f"Failed: {job.get('dlq_at', 'N/A')}")
        click.echo("-" * 100)


@dlq.command('retry')
@click.argument('job_id')
@click.pass_context
def dlq_retry(ctx, job_id):
    """Retry a DLQ job"""
    job_manager = ctx.obj['job_manager']
    
    job = job_manager.get_job(job_id)
    if not job:
        click.echo(f"ERROR: Job {job_id} not found", err=True)
        return
    
    if job['state'] != 'dlq':
        click.echo(f"ERROR: Job {job_id} is not in DLQ (current state: {job['state']})", err=True)
        return
    
    if job_manager.retry_job(job_id):
        click.echo(f"SUCCESS: Job {job_id} has been moved from DLQ back to pending queue")
    else:
        click.echo(f"ERROR: Failed to retry job {job_id}", err=True)


@cli.group()
def config():
    """Manage configuration (retry, backoff, etc.)"""
    pass


@config.command('set')
@click.argument('key')
@click.argument('value')
@click.pass_context
def config_set(ctx, key, value):
    """Set configuration value"""
    config_file = Path('data/config.json')

    # Load existing config
    if config_file.exists():
        with open(config_file, 'r') as f:
            try:
                config_data = json.load(f)
            except Exception:
                config_data = {}
    else:
        config_data = {}

    # Map CLI key -> canonical internal key
    key_mapping = {
        'max-retries': 'default_max_retries',
        'backoff-base': 'backoff_base',
        'poll-interval': 'poll_interval',
        'timeout': 'default_timeout',
    }
    canonical = key_mapping.get(key, key)

    # All aliases we’ll keep in sync on disk
    alias_map = {
        'default_max_retries': ['default_max_retries', 'max-retries', 'max_retries'],
        'backoff_base':        ['backoff_base', 'backoff-base', 'backoffbase'],
        'poll_interval':       ['poll_interval', 'poll-interval', 'pollinterval'],
        'default_timeout':     ['default_timeout', 'default-timeout', 'defaulttimeout', 'timeout'],
    }
    aliases = alias_map.get(canonical, list({canonical, canonical.replace('_', '-'), canonical.replace('-', '_')}))

    # Validate & cast
    try:
        if canonical in ['default_max_retries', 'backoff_base', 'default_timeout']:
            value = int(value)
        elif canonical == 'poll_interval':
            value = float(value)
    except ValueError:
        click.echo(f"❌ Invalid value for {key}: {value}", err=True)
        return

    # Save to all aliases
    for a in aliases:
        config_data[a] = value

    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, 'w') as f:
        json.dump(config_data, f, indent=2)

    # Update in-memory Config also
    cfg = ctx.obj.get('config')
    if cfg is not None:
        try:
            setattr(cfg, canonical, value)
        except Exception:
            pass

    click.echo(f"✅ Configuration updated: {key} = {value}")


def _heuristic_value_from_file(config_data: dict, key: str):
    """
    Heuristic: if explicit aliases fail, scan the file for a numeric value
    whose key name *resembles* the requested key.
    This is a last resort to make 'config get' resilient.
    """
    norm = key.lower().replace('-', '').replace('_', '')
    for k, v in config_data.items():
        kn = str(k).lower().replace('-', '').replace('_', '')
        if isinstance(v, (int, float)) and (norm in kn or kn in norm or any(p in kn for p in ['retry','backoff','interval','timeout'])):
            return v
    return None


@config.command('get')
@click.argument('key', required=False)
@click.pass_context
def config_get(ctx, key):
    """Get configuration value(s)"""
    config_obj = ctx.obj['config']
    config_file = Path('data/config.json')

    # Load saved config
    if config_file.exists():
        with open(config_file, 'r') as f:
            try:
                config_data = json.load(f)
            except Exception:
                config_data = {}
    else:
        config_data = {}

    # Defaults from current Config object
    defaults = {
        'max-retries':   config_obj.default_max_retries,
        'backoff-base':  config_obj.backoff_base,
        'poll-interval': config_obj.poll_interval,
        'timeout':       config_obj.default_timeout,
        'db-path':       config_obj.db_path,
        'log-level':     config_obj.log_level
    }

    # Map CLI key -> canonical internal key + aliases
    canonical_map = {
        'max-retries':   'default_max_retries',
        'backoff-base':  'backoff_base',
        'poll-interval': 'poll_interval',
        'timeout':       'default_timeout',
    }
    alias_map = {
        'default_max_retries': ['default_max_retries', 'max-retries', 'max_retries'],
        'backoff_base':        ['backoff_base', 'backoff-base', 'backoffbase'],
        'poll_interval':       ['poll_interval', 'poll-interval', 'pollinterval'],
        'default_timeout':     ['default_timeout', 'default-timeout', 'defaulttimeout', 'timeout'],
    }

    if key:
        canonical = canonical_map.get(key, key.replace('-', '_'))
        aliases = alias_map.get(canonical, list({
            canonical,
            canonical.replace('_', '-'),
            canonical.replace('-', '_'),
            key,
            key.replace('-', '_'),
        }))

        # Try file first
        found = None
        for a in aliases:
            if a in config_data:
                found = config_data[a]
                break

        # Heuristic fallback: scan config file for a likely numeric value
        if found is None:
            found = _heuristic_value_from_file(config_data, key)

        # Fall back to in-memory Config attribute or defaults
        if found is None:
            found = getattr(config_obj, canonical, defaults.get(key, 'Not set'))

        click.echo(f"{key}: {found}")
        return

    # No key specified -> show all
    click.echo("\nCurrent Configuration")
    click.echo("=" * 50)
    for k, default_val in defaults.items():
        canonical = canonical_map.get(k, k.replace('-', '_'))
        aliases = alias_map.get(canonical, [canonical, canonical.replace('_', '-')])
        current_value = None
        for a in aliases:
            if a in config_data:
                current_value = config_data[a]
                break
        if current_value is None:
            current_value = default_val
        click.echo(f"{k:.<30} {current_value}")


@cli.command()
@click.argument('job_id')
@click.pass_context
def cancel(ctx, job_id):
    """Cancel a pending job"""
    job_manager = ctx.obj['job_manager']
    
    if job_manager.cancel_job(job_id):
        click.echo(f"SUCCESS: Job {job_id} has been cancelled")
    else:
        click.echo(f"ERROR: Failed to cancel job {job_id} (may not be pending)", err=True)


@cli.command()
@click.argument('job_id')
@click.pass_context
def get(ctx, job_id):
    """Get detailed status of a specific job"""
    job_manager = ctx.obj['job_manager']
    job = job_manager.get_job(job_id)
    
    if not job:
        click.echo(f"ERROR: Job {job_id} not found", err=True)
        return
    
    click.echo(f"\nJob Details: {job_id}")
    click.echo("=" * 60)
    click.echo(f"Command:      {job['command']}")
    click.echo(f"State:        {job['state']}")
    click.echo(f"Priority:     {job.get('priority', 0)}")
    click.echo(f"Attempts:     {job['attempts']}/{job['max_retries']}")
    click.echo(f"Created:      {job['created_at']}")
    click.echo(f"Updated:      {job['updated_at']}")
    
    if job.get('timeout'):
        click.echo(f"Timeout:      {job['timeout']}s")
    if job.get('run_at'):
        click.echo(f"Scheduled:    {job['run_at']}")
    if job.get('started_at'):
        click.echo(f"Started:      {job['started_at']}")
    if job.get('completed_at'):
        click.echo(f"Completed:    {job['completed_at']}")
    if job.get('execution_time'):
        click.echo(f"Exec Time:    {job['execution_time']:.2f}s")
    
    if job.get('output'):
        click.echo(f"\nOutput:\n{job['output']}")
    if job.get('error'):
        click.echo(f"\nError:\n{job['error']}")


@cli.command()
@click.option('--port', '-p', default=8080, help='Port for web dashboard')
@click.pass_context
def dashboard(ctx, port):
    """Start web dashboard for monitoring"""
    config = ctx.obj['config']
    
    click.echo(f"Starting web dashboard on http://localhost:{port}")
    click.echo("Press Ctrl+C to stop...")
    
    try:
        start_dashboard(config, port)
    except KeyboardInterrupt:
        click.echo("\nDashboard stopped")


@cli.command()
@click.confirmation_option(prompt='Are you sure you want to purge all completed jobs?')
@click.pass_context
def purge(ctx):
    """Purge all completed jobs"""
    job_manager = ctx.obj['job_manager']
    count = job_manager.purge_completed()
    click.echo(f"SUCCESS: Purged {count} completed job(s)")


if __name__ == '__main__':
    cli()
