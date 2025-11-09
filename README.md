# 🚀 QueueCTL - Advanced Background Job Queue System

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)


A production-grade CLI-based background job queue system with worker management, exponential backoff retry logic, Dead Letter Queue (DLQ), and real-time web monitoring dashboard.

## ✨ Features

### Core Features ✅ (All Required)
- **Job Queue Management** - Enqueue, list, and monitor background jobs
- **Multi-Worker Support** - Run multiple concurrent worker processes with `worker start --count`
- **Worker Control** - Start and stop workers gracefully
- **Intelligent Retry Logic** - Exponential backoff with configurable retry attempts
- **Dead Letter Queue** - Automatic isolation of permanently failed jobs
- **Persistent Storage** - JSON-based storage survives system restarts
- **CLI Interface** - Complete command-line interface matching task specifications
- **Configuration Management** - Runtime configuration via `config set/get` commands

### Bonus Features 🌟 (All Included)
- **Priority Queues** - Execute high-priority jobs first
- **Job Timeouts** - Automatic timeout handling for long-running jobs
- **Scheduled Jobs** - Delay job execution to specific timestamps
- **Job Output Logging** - Capture and store stdout/stderr from executed commands
- **Real-time Metrics** - Success rates, execution times, and queue statistics
- **Web Dashboard** - Beautiful monitoring interface with auto-refresh
- **Graceful Shutdown** - Workers complete current jobs before terminating
- **Comprehensive Logging** - Both console and file-based logging

## 🏗️ Architecture

```
┌─────────────┐
│   CLI       │
│  Interface  │
└──────┬──────┘
       │
       ▼
┌─────────────┐      ┌──────────────┐
│     Job     │◄────►│   jobs.json  │
│   Manager   │      │  (Persistent │
└──────┬──────┘      │   Storage)   │
       │             └──────────────┘
       │
       ▼
┌─────────────┐
│   Worker    │
│    Pool     │
└──────┬──────┘
       │
   ┌───┴───┬───────┬───────┐
   ▼       ▼       ▼       ▼
Worker-1 Worker-2 ... Worker-N
```

### Job Lifecycle

```
enqueue → pending → running → completed
                       │
                       └─→ failed ──┐
                          (retry)   │
                             ↑      │
                             └──────┘
                                    │
                             (max retries)
                                    │
                                    ▼
                                   DLQ
```

## 📋 Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Git

## 🚀 Quick Start (Windows)

### Step 1: Clone Repository

```cmd
git clone https://github.com/YOUR_USERNAME/queuectl.git
cd queuectl
```

### Step 2: Run Setup Script

```cmd
setup.bat
```

This will:
- Create virtual environment
- Install dependencies
- Run tests
- Verify everything works

### Step 3: Test the Installation

```cmd
python queuectl.py --help
```

## 💻 Command Reference

### 1. Enqueue Jobs

```bash
# Basic job (outputs JSON)
python queuectl.py enqueue "echo Hello World"

# Job with options
python queuectl.py enqueue "python script.py" --max-retries 5 --priority 10

# Job with timeout
python queuectl.py enqueue "long-task.sh" --timeout 60

# Scheduled job
python queuectl.py enqueue "backup.sh" --run-at "2025-11-10T02:00:00Z"
```

**Output (JSON):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "command": "echo Hello World",
  "state": "pending",
  "priority": 0,
  "max_retries": 3
}
```

### 2. Worker Management

```bash
# Start workers (as per task spec)
python queuectl.py worker start --count 3

# Start with custom backoff
python queuectl.py worker start --count 2 --backoff-base 3

# Stop workers (shows how to stop)
python queuectl.py worker stop
```

### 3. Check Status

```bash
# Show summary of all job states & active workers
python queuectl.py status
```

**Output:**
```
📊 Queue Status
============================================================
Total Jobs:       25
Pending:          5
Running:          2
Completed:        15
Failed:           2
Dead Letter:      1
Scheduled:        0

Success Rate:     88.2%
Avg Exec Time:    2.34s

Active Workers: 2
  • worker-1: python task.py
  • worker-2: echo processing...
```

### 4. Get Job Details

```bash
# Get detailed information about specific job
python queuectl.py get <JOB_ID>
```

### 5. List Jobs

```bash
# List all jobs
python queuectl.py list

# Filter by state
python queuectl.py list --state pending
python queuectl.py list --state running
python queuectl.py list --state completed
python queuectl.py list --state failed

# Limit results
python queuectl.py list --limit 10
```

### 6. Dead Letter Queue

```bash
# View DLQ jobs (as per task spec)
python queuectl.py dlq list

# Retry job from DLQ (as per task spec)
python queuectl.py dlq retry <JOB_ID>
```

### 7. Configuration Management

```bash
# Set configuration (as per task spec)
python queuectl.py config set max-retries 5
python queuectl.py config set backoff-base 3

# Get configuration
python queuectl.py config get max-retries
python queuectl.py config get  # Show all config
```

### 8. Cancel Job

```bash
python queuectl.py cancel <JOB_ID>
```

### 9. Web Dashboard (Bonus)

```bash
# Start dashboard
python queuectl.py dashboard

# Custom port
python queuectl.py dashboard --port 3000
```

Access at: `http://localhost:8080`

### 10. Purge Completed Jobs (Bonus)

```bash
python queuectl.py purge
```

## 🧪 Testing

### Run Automated Tests

```bash
python test_queuectl.py
```

This runs 12 comprehensive tests covering:
- ✅ Basic job enqueue
- ✅ Get job details
- ✅ List jobs
- ✅ Status check
- ✅ Worker execution
- ✅ Retry with exponential backoff
- ✅ Priority queue ordering
- ✅ Job timeout handling
- ✅ Scheduled jobs
- ✅ Dead Letter Queue
- ✅ Configuration management
- ✅ Data persistence

### Manual Testing Scenarios

#### Scenario 1: Basic Workflow

```bash
# Terminal 1: Start workers
python queuectl.py worker start --count 2

# Terminal 2: Enqueue jobs
python queuectl.py enqueue "echo Job 1"
python queuectl.py enqueue "echo Job 2" --priority 10
python queuectl.py enqueue "python -c \"print('Hello');\""

# Check status
python queuectl.py status

# View results
python queuectl.py list --state completed
```

#### Scenario 2: Failed Job Handling

```bash
# Terminal 1: Start worker
python queuectl.py worker start --count 1

# Terminal 2: Create failing job
python queuectl.py enqueue "exit 1" --max-retries 3

# Watch logs - exponential backoff in action:
# Attempt 1: Immediate
# Attempt 2: After 2 seconds (2^1)
# Attempt 3: After 4 seconds (2^2)
# Then moved to DLQ

# Check DLQ
python queuectl.py dlq list

# Retry from DLQ
python queuectl.py dlq retry <JOB_ID>
```

#### Scenario 3: Priority Queue

```bash
# Enqueue with different priorities
python queuectl.py enqueue "echo Low" --priority 1
python queuectl.py enqueue "echo High" --priority 10
python queuectl.py enqueue "echo Medium" --priority 5

# Start worker - processes by priority
python queuectl.py worker start --count 1
```

## ⚙️ Configuration

### Environment Variables

```bash
# Windows PowerShell
$env:QUEUECTL_DB_PATH = "data/jobs.json"
$env:QUEUECTL_BACKOFF_BASE = "2"
$env:QUEUECTL_MAX_RETRIES = "3"

# Windows Command Prompt
set QUEUECTL_DB_PATH=data/jobs.json
set QUEUECTL_BACKOFF_BASE=2
```

### Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `QUEUECTL_DB_PATH` | `data/jobs.json` | Job database file path |
| `QUEUECTL_POLL_INTERVAL` | `1.0` | Worker polling interval (seconds) |
| `QUEUECTL_BACKOFF_BASE` | `2` | Exponential backoff base |
| `QUEUECTL_MAX_RETRIES` | `3` | Default maximum retries |
| `QUEUECTL_TIMEOUT` | `300` | Default timeout (seconds) |
| `QUEUECTL_LOG_LEVEL` | `INFO` | Logging level |
| `QUEUECTL_LOG_FILE` | `data/queuectl.log` | Log file path |

## 📊 Data Persistence

Jobs are stored in `data/jobs.json`:

```json
{
  "jobs": {
    "550e8400-e29b-41d4-a716-446655440000": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "command": "echo Hello",
      "state": "completed",
      "priority": 0,
      "attempts": 1,
      "max_retries": 3,
      "created_at": "2025-11-09T10:30:00Z",
      "updated_at": "2025-11-09T10:30:05Z",
      "output": "Hello",
      "execution_time": 0.05
    }
  }
}
```

## 🔧 Implementation Details

### Exponential Backoff

```
delay = base^attempts seconds

Examples (base=2):
- Attempt 1: Immediate
- Attempt 2: 2 seconds (2^1)
- Attempt 3: 4 seconds (2^2)
- Attempt 4: 8 seconds (2^3)
```

### Concurrency & Locking

- Jobs transition to `running` state when acquired
- Only `pending` jobs can be acquired
- Multiple workers process jobs without race conditions
- JSON file provides atomic writes

### Graceful Shutdown

Workers handle `SIGINT` (Ctrl+C):
1. Stop accepting new jobs
2. Complete current job
3. Clean exit

## 🎯 Design Decisions

### Why JSON Storage?

**Pros:**
- Zero external dependencies
- Human-readable
- Portable
- Version control friendly

**Cons:**
- Not for high throughput (>1000 jobs/sec)

**For production:** Use SQLite, PostgreSQL, or Redis

### Why Process-based Workers?

**Pros:**
- True parallelism (bypasses GIL)
- Process isolation
- Easy horizontal scaling

**Cons:**
- Higher memory overhead than threads

## 🐛 Troubleshooting

### Issue: "python: command not found"

```cmd
# Use py launcher
py queuectl.py --help
```

### Issue: Permission denied (PowerShell)

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Issue: Import errors

```cmd
# Verify virtual environment is activated
venv\Scripts\activate

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

## 📚 Project Structure

```
queuectl/
├── queuectl.py                 # Main CLI (matches task specs)
├── src/
│   ├── core/
│   │   ├── job_manager.py      # Job lifecycle management
│   │   ├── worker.py           # Worker processes
│   │   └── config.py           # Configuration
│   ├── utils/
│   │   └── logger.py           # Logging
│   └── web/
│       └── dashboard.py        # Web dashboard
├── data/
│   ├── jobs.json               # Job database (auto-created)
│   └── queuectl.log            # Logs
├── test_queuectl.py            # Test suite
├── requirements.txt            # Dependencies
├── setup.bat                   # Windows setup script
├── queuectl.bat                # Wrapper for shorter commands
├── README.md                   # This file
└── .gitignore                  # Git ignore rules
```

## 🎓 What This Demonstrates

- **CLI Development** - Production-grade command-line tools
- **Concurrent Processing** - Multi-process worker pools
- **State Management** - Complex job lifecycle
- **Error Handling** - Retry logic and graceful degradation
- **System Design** - Queue patterns and architecture
- **Testing** - Comprehensive test coverage

## 📝 Future Enhancements

- [ ] SQLite/PostgreSQL backend
- [ ] Redis-based queue
- [ ] Distributed workers
- [ ] Job dependencies
- [ ] Webhook notifications
- [ ] Prometheus metrics
- [ ] Docker containerization


**⭐ Star this repository if you found it helpful!**
