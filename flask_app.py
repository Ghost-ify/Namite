"""
Flask web application for the Roblox Username Discord Bot.
This provides a web interface to monitor the bot's status and view statistics.
"""
import os
import time
from datetime import datetime, timedelta
from flask import Flask, render_template_string
from dotenv import load_dotenv
from database import get_db_connection, init_database
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Load environment variables
load_dotenv()

# Initialize database when Flask app starts
init_database()

# Create and configure the Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', 'dev-key-for-testing')

def get_bot_statistics():
    """Get statistics about the bot's operations from the database."""
    try:
        # Get cookie information from roblox_api
        from roblox_api import adaptive_system
        current_time = time.time()
        start_time = time.time() # Added start time initialization

        cookie_status = []
        if adaptive_system and adaptive_system.cookie_status:
            for status in adaptive_system.cookie_status:
                total = max(1, status['success_count'] + status['error_count'])
                error_rate = (status['error_count'] / total) * 100

                # Calculate time since last use
                time_diff = current_time - status['last_used']
                if time_diff < 60:
                    last_used_ago = f"{int(time_diff)}s ago"
                elif time_diff < 3600:
                    last_used_ago = f"{int(time_diff/60)}m ago"
                else:
                    last_used_ago = f"{int(time_diff/3600)}h ago"

                cookie_status.append({
                    'error_rate': error_rate,
                    'cooldown_until': status['cooldown_until'],
                    'last_used_ago': last_used_ago,
                    'success_count': status['success_count'],
                    'error_count': status['error_count']
                })

        conn = get_db_connection()
        if not conn:
            return {
                "total_checked": 0,
                "available_found": 0,
                "checks_last_24h": 0,
                "available_last_24h": 0,
                "errors_count": 0,
                "errors_last_24h": 0,
                "success_rate": 0,
                "success_rate_24h": 0,
                "api_status": "Unknown",
                "cookie_count": len(cookie_status),
                "cookie_status": cookie_status,
                "current_time": current_time,
                "start_time": start_time # Added start_time to the dictionary
            }

        cursor = conn.cursor()

        try:
            # Get total checked
            cursor.execute("SELECT COUNT(*) FROM checked_usernames")
            total_checked = cursor.fetchone()[0] or 0

            # Get available found
            cursor.execute("SELECT COUNT(*) FROM checked_usernames WHERE is_available = TRUE")
            available_found = cursor.fetchone()[0] or 0

            # Get error count
            cursor.execute(
                "SELECT COUNT(*) FROM checked_usernames WHERE status_code = 0 OR status_code >= 400"
            )
            errors_count = cursor.fetchone()[0] or 0

            # Get checks in last 24 hours
            cursor.execute(
                "SELECT COUNT(*) FROM checked_usernames WHERE checked_at >= %s",
                (datetime.now() - timedelta(days=1),)
            )
            checks_last_24h = cursor.fetchone()[0] or 0

            # Get available in last 24 hours
            cursor.execute(
                "SELECT COUNT(*) FROM checked_usernames WHERE is_available = TRUE AND checked_at >= %s",
                (datetime.now() - timedelta(days=1),)
            )
            available_last_24h = cursor.fetchone()[0] or 0

            # Get errors in last 24 hours
            cursor.execute(
                "SELECT COUNT(*) FROM checked_usernames WHERE (status_code = 0 OR status_code >= 400) AND checked_at >= %s",
                (datetime.now() - timedelta(days=1),)
            )
            errors_last_24h = cursor.fetchone()[0] or 0

            # Calculate success rates safely
            valid_checks = max(1, total_checked - errors_count)
            valid_checks_24h = max(1, checks_last_24h - errors_last_24h)

            success_rate = (available_found / valid_checks * 100)
            success_rate_24h = (available_last_24h / valid_checks_24h * 100)

            # Check API status based on recent errors
            cursor.execute(
                "SELECT COUNT(*) FROM checked_usernames WHERE checked_at >= %s",
                (datetime.now() - timedelta(minutes=5),)
            )
            recent_checks = cursor.fetchone()[0] or 0

            cursor.execute(
                "SELECT COUNT(*) FROM checked_usernames WHERE (status_code = 0 OR status_code >= 400) AND checked_at >= %s",
                (datetime.now() - timedelta(minutes=5),)
            )
            recent_errors = cursor.fetchone()[0] or 0

            # Determine API status
            api_status = "Healthy"
            if recent_checks > 0:
                error_rate = (recent_errors / max(1, recent_checks)) * 100
                if error_rate > 50:
                    api_status = "Critical"
                elif error_rate > 20:
                    api_status = "Degraded"
            elif errors_last_24h > 0:
                api_status = "Unknown (No Recent Checks)"

            # Get adaptive learning stats
            adaptive_learning = {}
            try:
                if os.path.exists('adaptive_state.json'):
                    import json
                    with open('adaptive_state.json', 'r') as f:
                        state = json.load(f)
                    adaptive_learning = {
                        'parallel_checks': state.get('parallel_checks', 10),
                        'underscore_probability': state.get('underscore_probability', 0.2),
                        'numeric_probability': state.get('numeric_probability', 0.3),
                        'uppercase_probability': state.get('uppercase_probability', 0.4),
                        'last_updated': state.get('last_updated', 'Unknown')
                    }
            except Exception as e:
                app.logger.error(f"Error loading adaptive learning state: {str(e)}")
                adaptive_learning = {'error': str(e)}

            return {
                "total_checked": total_checked,
                "available_found": available_found,
                "checks_last_24h": checks_last_24h,
                "available_last_24h": available_last_24h,
                "errors_count": errors_count,
                "errors_last_24h": errors_last_24h,
                "success_rate": success_rate,
                "success_rate_24h": success_rate_24h,
                "api_status": api_status,
                "adaptive_learning": adaptive_learning,
                "cookie_count": len(cookie_status),
                "cookie_status": cookie_status,
                "current_time": current_time,
                "start_time": start_time # Added start_time to the dictionary
            }
        finally:
            conn.close()
    except Exception as e:
        app.logger.error(f"Error getting statistics: {str(e)}")
        return {
            "total_checked": 0,
            "available_found": 0,
            "checks_last_24h": 0,
            "available_last_24h": 0,
            "errors_count": 0,
            "errors_last_24h": 0,
            "success_rate": 0,
            "success_rate_24h": 0,
            "api_status": "Error"
        }

# Dashboard HTML template
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Roblox Username Bot - Dashboard</title>
    <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
    <style>
        body {
            padding: 2rem;
            color: #e6e6e6;
            background-color: #1c1c1c;
        }
        .app-container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .stat-card {
            background: #2d2d2d;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .stat-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }
        .stat-item {
            background: #363636;
            padding: 1.25rem;
            border-radius: 6px;
            text-align: center;
        }
        .stat-value {
            font-size: 2rem;
            font-weight: bold;
            margin-bottom: 0.5rem;
            color: #00ff9d;
        }
        .stat-label {
            color: #a6a6a6;
            font-size: 0.9rem;
        }
        .progress {
            height: 0.75rem;
            background-color: #363636;
        }
        .progress-bar {
            transition: width 0.3s ease;
        }
        .cookie-status {
            display: flex;
            align-items: center;
            padding: 0.75rem;
            border-radius: 6px;
            margin-bottom: 0.5rem;
            background: #363636;
        }
        .status-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 1rem;
        }
        .status-healthy { background-color: #00ff9d; }
        .status-degraded { background-color: #ffd700; }
        .status-poor { background-color: #ff4d4d; }
    </style>
    <meta http-equiv="refresh" content="60">
</head>
<body>
    <div class="app-container">
        <div class="stat-card">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h1 class="m-0">Roblox Username Bot Analytics</h1>
                <button class="btn btn-sm btn-outline-secondary" onclick="location.reload()">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-arrow-clockwise" viewBox="0 0 16 16">
                        <path fill-rule="evenodd" d="M8 3a5 5 0 1 0 4.546 2.914.5.5 0 0 1 .908-.417A6 6 0 1 1 8 2v1z"/>
                        <path d="M8 4.466V.534a.25.25 0 0 1 .41-.192l2.36 1.966c.12.1.12.284 0 .384L8.41 4.658A.25.25 0 0 1 8 4.466z"/>
                    </svg>
                    Refresh
                </button>
            </div>
            <div class="text-muted">Last updated: {{ current_time }}</div>
        </div>

        <!-- Performance Stats -->
        <div class="stat-card">
            <h4>Performance Metrics</h4>
            <div class="stat-grid">
                <div class="stat-item">
                    <div class="stat-value">{{ stats.total_checked }}</div>
                    <div class="stat-label">Total Checks</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{{ stats.available_found }}</div>
                    <div class="stat-label">Available Found</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{{ "%.1f"|format(stats.success_rate) }}%</div>
                    <div class="stat-label">Success Rate</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{{ stats.checks_last_24h }}</div>
                    <div class="stat-label">24h Checks</div>
                </div>
            </div>
        </div>

        <!-- API Status -->
        <div class="stat-card">
            <h4>System Health</h4>
            <div class="cookie-status">
                <div class="status-indicator {{ 'status-healthy' if stats.api_status == 'Healthy' else 'status-degraded' if stats.api_status == 'Degraded' else 'status-poor' }}"></div>
                <div>API Status: {{ stats.api_status }}</div>
            </div>
            <div class="progress mb-3">
                <div class="progress-bar bg-success" style="width: {{ stats.success_rate }}%"></div>
            </div>
        </div>

        <!-- Cookie Performance -->
        <div class="stat-card">
            <h4>Cookie Performance</h4>
            <div class="row">
                <div class="col-md-12">
                    <div class="alert alert-info">
                        <h5>Cookie Health Overview</h5>
                        <div class="d-flex justify-content-between">
                            <div>Total Requests: <span class="badge bg-primary">{{ stats.total_checked }}</span></div>
                            <div>Error Rate: <span class="badge bg-{{ 'success' if (stats.errors_count / stats.total_checked * 100) < 20 else 'warning' if (stats.errors_count / stats.total_checked * 100) < 50 else 'danger' }}">{{ "%.1f"|format(stats.errors_count / stats.total_checked * 100) }}%</span></div>
                            <div>Active Cookies: <span class="badge bg-info">{{ stats.cookie_count }}</span></div>
                        </div>
                        <div class="mt-2">
                            <h6>Performance Metrics</h6>
                            <div class="d-flex justify-content-between">
                                <div>Average Checks/Min: <span class="badge bg-success">{{ "%.1f"|format(stats.checks_last_24h / (24 * 60)) }}</span></div>
                                <div>Per Cookie: <span class="badge bg-info">{{ "%.1f"|format((stats.checks_last_24h / (24 * 60)) / max(1, stats.cookie_count)) }}</span></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <table class="table table-dark table-striped">
                <thead>
                    <tr>
                        <th>Cookie #</th>
                        <th>Error Rate</th>
                        <th>Checks/min</th>
                        <th>Status</th>
                        <th>Last Error</th>
                    </tr>
                </thead>
                <tbody>
                    {% for status in stats.cookie_status %}
                        {% set error_rate = status.error_count / max(1, (status.error_count + status.success_count)) * 100 %}
                        <tr>
                            <td>{{ loop.index }}</td>
                            <td>
                                <div class="progress" style="height: 20px;">
                                    <div class="progress-bar bg-{{ 'success' if error_rate < 20 else 'warning' if error_rate < 50 else 'danger' }}" 
                                         role="progressbar" 
                                         style="width: {{ error_rate }}%">
                                        {{ "%.1f"|format(error_rate) }}%
                                    </div>
                                </div>
                            </td>
                            <td>{{ ((status.success_count + status.error_count) / max(1, (24 * 60)))|round(1) }}</td>
                            <td>
                                {% if status.cooldown_until|float > current_time|float %}
                                    <span class="badge bg-warning">Cooldown</span>
                                {% elif error_rate < 20 %}
                                    <span class="badge bg-success">Healthy</span>
                                {% elif error_rate < 50 %}
                                    <span class="badge bg-warning">Degraded</span>
                                {% else %}
                                    <span class="badge bg-danger">Poor</span>
                                {% endif %}
                            </td>
                            <td>{{ status.last_used_ago }}</td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def dashboard():
    """Display the bot dashboard with stats."""
    stats = get_bot_statistics()
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    return render_template_string(
        DASHBOARD_HTML,
        stats=stats,
        current_time=current_time,
        max=max
    )

@app.route('/health')
def health():
    """Simple health check endpoint."""
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except Exception as e:
        logger.error(f"Flask application error: {str(e)}")
        raise