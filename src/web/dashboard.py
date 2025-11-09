"""
Web Dashboard - Simple monitoring interface
"""

from flask import Flask, render_template_string, jsonify
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import Config
from core.job_manager import JobManager

app = Flask(__name__)
config = None
job_manager = None

# HTML Template
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>QueueCTL Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { 
            max-width: 1400px; 
            margin: 0 auto; 
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px 40px;
        }
        .header h1 { 
            font-size: 32px; 
            margin-bottom: 10px;
            font-weight: 700;
        }
        .header p { opacity: 0.9; font-size: 16px; }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            padding: 30px 40px;
            background: #f8f9fa;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }
        .stat-card:hover { transform: translateY(-4px); }
        .stat-label {
            font-size: 13px;
            color: #6c757d;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }
        .stat-value {
            font-size: 32px;
            font-weight: 700;
            color: #212529;
        }
        .stat-card.pending .stat-value { color: #ffc107; }
        .stat-card.running .stat-value { color: #17a2b8; }
        .stat-card.completed .stat-value { color: #28a745; }
        .stat-card.failed .stat-value { color: #dc3545; }
        .jobs-section {
            padding: 30px 40px;
        }
        .section-title {
            font-size: 20px;
            font-weight: 600;
            margin-bottom: 20px;
            color: #212529;
        }
        .job-table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .job-table th {
            background: #f8f9fa;
            padding: 15px;
            text-align: left;
            font-weight: 600;
            color: #495057;
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .job-table td {
            padding: 15px;
            border-top: 1px solid #e9ecef;
            color: #212529;
        }
        .job-table tr:hover { background: #f8f9fa; }
        .badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }
        .badge.pending { background: #fff3cd; color: #856404; }
        .badge.running { background: #d1ecf1; color: #0c5460; }
        .badge.completed { background: #d4edda; color: #155724; }
        .badge.failed { background: #f8d7da; color: #721c24; }
        .badge.dlq { background: #721c24; color: white; }
        .badge.scheduled { background: #e7e7ff; color: #4c4cff; }
        .refresh-info {
            text-align: center;
            padding: 20px;
            color: #6c757d;
            font-size: 14px;
        }
        .truncate {
            max-width: 300px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .auto-refresh {
            animation: pulse 2s infinite;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 QueueCTL Dashboard</h1>
            <p>Real-time job queue monitoring and statistics</p>
        </div>
        
        <div class="stats" id="stats">
            <div class="stat-card">
                <div class="stat-label">Total Jobs</div>
                <div class="stat-value" id="total">-</div>
            </div>
            <div class="stat-card pending">
                <div class="stat-label">Pending</div>
                <div class="stat-value" id="pending">-</div>
            </div>
            <div class="stat-card running">
                <div class="stat-label">Running</div>
                <div class="stat-value" id="running">-</div>
            </div>
            <div class="stat-card completed">
                <div class="stat-label">Completed</div>
                <div class="stat-value" id="completed">-</div>
            </div>
            <div class="stat-card failed">
                <div class="stat-label">Failed/DLQ</div>
                <div class="stat-value" id="failed">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Success Rate</div>
                <div class="stat-value" id="success-rate">-</div>
            </div>
        </div>
        
        <div class="jobs-section">
            <h2 class="section-title">Recent Jobs</h2>
            <table class="job-table">
                <thead>
                    <tr>
                        <th>Job ID</th>
                        <th>Command</th>
                        <th>State</th>
                        <th>Priority</th>
                        <th>Attempts</th>
                        <th>Created</th>
                    </tr>
                </thead>
                <tbody id="jobs-tbody">
                    <tr><td colspan="6" style="text-align: center; padding: 40px;">Loading jobs...</td></tr>
                </tbody>
            </table>
        </div>
        
        <div class="refresh-info auto-refresh">
            ↻ Auto-refreshing every 5 seconds
        </div>
    </div>
    
    <script>
        async function fetchStats() {
            const response = await fetch('/api/stats');
            const data = await response.json();
            
            document.getElementById('total').textContent = data.total;
            document.getElementById('pending').textContent = data.pending;
            document.getElementById('running').textContent = data.running;
            document.getElementById('completed').textContent = data.completed;
            document.getElementById('failed').textContent = data.failed + data.dlq;
            document.getElementById('success-rate').textContent = data.success_rate.toFixed(1) + '%';
        }
        
        async function fetchJobs() {
            const response = await fetch('/api/jobs');
            const jobs = await response.json();
            
            const tbody = document.getElementById('jobs-tbody');
            
            if (jobs.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 40px;">No jobs found</td></tr>';
                return;
            }
            
            tbody.innerHTML = jobs.map(job => `
                <tr>
                    <td><code style="font-size: 11px;">${job.id.substring(0, 8)}</code></td>
                    <td><div class="truncate" title="${job.command}">${job.command}</div></td>
                    <td><span class="badge ${job.state}">${job.state}</span></td>
                    <td>${job.priority || 0}</td>
                    <td>${job.attempts}/${job.max_retries}</td>
                    <td>${new Date(job.created_at).toLocaleString()}</td>
                </tr>
            `).join('');
        }
        
        function refresh() {
            fetchStats();
            fetchJobs();
        }
        
        // Initial load
        refresh();
        
        // Auto-refresh every 5 seconds
        setInterval(refresh, 5000);
    </script>
</body>
</html>
"""

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template_string(DASHBOARD_TEMPLATE)

@app.route('/api/stats')
def api_stats():
    """Get queue statistics"""
    stats = job_manager.get_stats()
    return jsonify(stats)

@app.route('/api/jobs')
def api_jobs():
    """Get recent jobs"""
    jobs = job_manager.list_jobs(limit=50)
    return jsonify(jobs)

def start_dashboard(cfg: Config, port: int = 8080):
    """Start the dashboard server"""
    global config, job_manager
    config = cfg
    job_manager = JobManager(config)
    
    app.run(host='0.0.0.0', port=port, debug=False)
