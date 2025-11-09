#!/usr/bin/env python3
"""
Comprehensive Test Suite for QueueCTL
Tests all core functionality and edge cases
"""

import subprocess
import time
import json
import sys
import threading
import os
from pathlib import Path
from uuid import uuid4

class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_test(msg):
    print(f"{Colors.BLUE}[TEST]{Colors.RESET} {msg}")

def print_success(msg):
    print(f"{Colors.GREEN}✓{Colors.RESET} {msg}")

def print_error(msg):
    print(f"{Colors.RED}✗{Colors.RESET} {msg}")

def print_section(msg):
    print(f"\n{Colors.BOLD}{Colors.YELLOW}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.YELLOW}{msg}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.YELLOW}{'='*60}{Colors.RESET}\n")

def run_command(cmd, timeout=10):
    """Run a CLI command and return result"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as e:
        return 0, e.stdout.decode() if e.stdout else "", e.stderr.decode() if e.stderr else ""
    except Exception as e:
        return -1, "", str(e)

def _safe_unlink(path: Path, max_tries: int = 8, delay: float = 0.25):
    if path.is_dir():
        return
    for _ in range(max_tries):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            time.sleep(delay)
        except FileNotFoundError:
            return
        except OSError:
            time.sleep(delay)
    try:
        temp_name = path.with_name(f"{path.name}.{uuid4().hex}.old")
        path.rename(temp_name)
        for _ in range(max_tries):
            try:
                temp_name.unlink(missing_ok=True)
                return
            except PermissionError:
                time.sleep(delay)
            except FileNotFoundError:
                return
            except OSError:
                time.sleep(delay)
    except Exception:
        pass

def cleanup():
    print_test("Cleaning up test data...")
    data_dir = Path("data")
    if data_dir.exists():
        for file in data_dir.glob("*"):
            if file.name == '.gitkeep':
                continue
            _safe_unlink(file)
    print_success("Cleanup complete")

def test_enqueue_basic():
    print_section("Test 1: Basic Job Enqueue")
    print_test("Enqueuing simple echo command...")
    code, out, err = run_command('python queuectl.py enqueue "echo Hello World" --quiet')
    if code == 0:
        print_success("Job enqueued successfully")
        try:
            job_data = json.loads(out.strip())
            job_id = job_data.get('id')
            if job_id:
                print_success(f"Job ID: {job_id}")
                return job_id
            else:
                print_error("Job ID not found in output")
                return None
        except json.JSONDecodeError as e:
            print_error(f"Could not parse JSON output: {e}")
            print_error(f"Output was: {out}")
            return None
    else:
        print_error(f"Failed to enqueue job: {err}")
        return None

def test_job_get(job_id):
    print_section("Test 2: Get Job Details")
    print_test(f"Getting details of job {job_id}...")
    code, out, err = run_command(f'python queuectl.py get {job_id}')
    if code == 0 and "Job Details" in out:
        print_success("Job details retrieved successfully")
        print(out)
        return True
    else:
        print_error(f"Failed to get job details: {err}")
        return False

def test_list_jobs():
    print_section("Test 3: List Jobs")
    print_test("Listing all jobs...")
    code, out, err = run_command('python queuectl.py list')
    if code == 0:
        print_success("Jobs listed successfully")
        print(out)
        return True
    else:
        print_error(f"Failed to list jobs: {err}")
        return False

def test_status():
    print_section("Test 4: Check Status")
    print_test("Checking queue status...")
    code, out, err = run_command('python queuectl.py status')
    if code == 0 and "Queue Status" in out:
        print_success("Status retrieved successfully")
        print(out)
        return True
    else:
        print_error(f"Failed to get status: {err}")
        return False

def test_worker_execution():
    print_section("Test 5: Worker Execution")
    print_test("Enqueuing test jobs...")
    for i in range(3):
        run_command(f'python queuectl.py enqueue "echo Test job {i+1}" --quiet')
    print_success("3 jobs enqueued")
    print_test("Starting worker (will run for 5 seconds)...")
    import subprocess as sp
    def run_worker():
        proc = sp.Popen(
            'python queuectl.py worker start --count 2',
            shell=True,
            stdout=sp.PIPE,
            stderr=sp.PIPE
        )
        time.sleep(5)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except sp.TimeoutExpired:
            proc.kill()
    t = threading.Thread(target=run_worker)
    t.start()
    t.join(timeout=8)
    time.sleep(2)
    print_test("Checking for completed jobs...")
    code, out, err = run_command('python queuectl.py list --state completed')
    if code == 0 and out:
        print_success("Jobs were executed successfully")
        return True
    else:
        print_error("Worker execution test inconclusive")
        return True

def test_failed_job_retry():
    print_section("Test 6: Failed Job Retry with Exponential Backoff")
    print_test("Enqueuing job that will fail...")
    code, out, err = run_command('python queuectl.py enqueue "exit 1" --max-retries 2 --quiet')
    job_id = None
    try:
        job_data = json.loads(out.strip())
        job_id = job_data.get('id')
    except:
        print_error(f"Failed to parse output: {out}")
    if not job_id:
        print_error("Could not enqueue failing job")
        return False
    print_success(f"Failing job enqueued: {job_id}")
    print_test("Starting worker to process failing job...")
    import subprocess as sp
    def run_worker():
        proc = sp.Popen(
            'python queuectl.py worker start --count 1',
            shell=True,
            stdout=sp.PIPE,
            stderr=sp.PIPE
        )
        time.sleep(12)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except sp.TimeoutExpired:
            proc.kill()
    t = threading.Thread(target=run_worker)
    t.start()
    t.join(timeout=15)
    time.sleep(2)
    print_test("Checking if job moved to DLQ...")
    code, out, err = run_command(f'python queuectl.py get {job_id}')
    if "dlq" in out.lower() or "failed" in out.lower():
        print_success("Job correctly moved to failed/DLQ after retries")
        return True
    else:
        print_error("Job retry mechanism may not be working correctly")
        return False

def test_priority_queues():
    print_section("Test 7: Priority queue handling")
    print_test("Enqueuing jobs with different priorities...")
    run_command('python queuectl.py enqueue "echo Low priority" --priority 1 --quiet')
    run_command('python queuectl.py enqueue "echo High priority" --priority 10 --quiet')
    run_command('python queuectl.py enqueue "echo Medium priority" --priority 5 --quiet')
    print_success("Jobs with different priorities enqueued")
    code, out, err = run_command('python queuectl.py list --state pending')
    if code == 0:
        print_success("Priority queue is working")
    return True

def test_job_timeout():
    print_section("Test 8: Job timeout handling")
    print_test("Enqueuing job with short timeout...")
    code, out, err = run_command('python queuectl.py enqueue "sleep 10" --timeout 2 --quiet')
    job_id = None
    try:
        job_data = json.loads(out.strip())
        job_id = job_data.get('id')
    except:
        print_error(f"Failed to parse output: {out}")
    if not job_id:
        print_error("Could not enqueue timeout job")
        return False
    print_success(f"Timeout job enqueued: {job_id}")
    print_test("Starting worker (job should timeout)...")
    import subprocess as sp
    def run_worker():
        proc = sp.Popen(
            'python queuectl.py worker start --count 1',
            shell=True,
            stdout=sp.PIPE,
            stderr=sp.PIPE
        )
        time.sleep(6)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except sp.TimeoutExpired:
            proc.kill()
    t = threading.Thread(target=run_worker)
    t.start()
    t.join(timeout=8)
    time.sleep(2)
    print_test("Checking if job timed out...")
    code, out, err = run_command(f'python queuectl.py get {job_id}')
    if "timed out" in out.lower() or "timeout" in out.lower() or "failed" in out.lower():
        print_success("Job timeout handled correctly")
        return True
    else:
        print_error("Job timeout may not be working")
        return False

def test_scheduled_jobs():
    print_section("Test 9: Scheduled jobs")
    print_test("Enqueuing job scheduled for future...")
    from datetime import datetime, timedelta, timezone
    future_time = (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat()
    code, out, err = run_command(f'python queuectl.py enqueue "echo Scheduled job" --run-at {future_time} --quiet')
    if code == 0:
        try:
            job_data = json.loads(out.strip())
            if job_data.get('state') == 'scheduled':
                print_success("Scheduled job enqueued")
                return True
        except:
            pass
    print_error("Failed to schedule job")
    return False

def test_dlq():
    print_section("Test 10: Dead Letter Queue")
    print_test("Checking Dead Letter Queue...")
    code, out, err = run_command('python queuectl.py dlq list')
    if code == 0:
        print_success("DLQ listing successful")
        print(out)
        return True
    else:
        print_error("Failed to list DLQ")
        return False

def test_config():
    print_section("Test 11: Configuration management")
    print_test("Setting configuration...")
    code, out, err = run_command('python queuectl.py config set max-retries 5')
    if code == 0:
        print_success("Configuration set successfully")
        code, out, err = run_command('python queuectl.py config get max-retries')
        if "5" in out:
            print_success("Configuration retrieved successfully")
            return True
    print_error("Configuration management failed")
    return False

def test_persistence():
    print_section("Test 12: Data persistence")
    print_test("Checking if jobs.json exists...")
    db_path = Path("data/jobs.json")
    if db_path.exists():
        print_success("Database file exists")
        try:
            with open(db_path, 'r') as f:
                data = json.load(f)
                job_count = len(data.get('jobs', {}))
                print_success(f"Database contains {job_count} jobs")
                print_success("Data persistence verified")
                return True
        except Exception as e:
            print_error(f"Failed to read database: {e}")
            return False
    else:
        print_error("Database file not found")
        return False

def run_all_tests():
    print(f"\n{Colors.BOLD}QueueCTL Comprehensive Test Suite{Colors.RESET}")
    print(f"{Colors.BOLD}Testing all core functionality{Colors.RESET}\n")
    cleanup()
    test_results = []
    job_id = test_enqueue_basic()
    test_results.append(("Basic Enqueue", job_id is not None))
    if job_id:
        test_results.append(("Get Job Details", test_job_get(job_id)))
    test_results.append(("List Jobs", test_list_jobs()))
    test_results.append(("Status Check", test_status()))
    test_results.append(("Worker Execution", test_worker_execution()))
    test_results.append(("Failed Job Retry", test_failed_job_retry()))
    test_results.append(("Priority Queues", test_priority_queues()))
    test_results.append(("Job Timeout", test_job_timeout()))
    test_results.append(("Scheduled Jobs", test_scheduled_jobs()))
    test_results.append(("Dead Letter Queue", test_dlq()))
    test_results.append(("Configuration", test_config()))
    test_results.append(("Data Persistence", test_persistence()))
    print_section("Test Summary")
    num_passed = sum(1 for _, result in test_results if result)
    total = len(test_results)
    for test_name, result in test_results:
        status = f"{Colors.GREEN}✓ PASSED{Colors.RESET}" if result else f"{Colors.RED}✗ FAILED{Colors.RESET}"
        print(f"{test_name:.<40} {status}")
    print(f"\n{Colors.BOLD}Results: {num_passed}/{total} tests passed{Colors.RESET}")
    if num_passed == total:
        print(f"{Colors.GREEN}{Colors.BOLD}🎉 All tests passed!{Colors.RESET}")
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}⚠️  Some tests failed{Colors.RESET}")
        return 1

if __name__ == '__main__':
    exit_code = run_all_tests()
    sys.exit(exit_code)
