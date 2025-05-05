"""
Flask web application for the Roblox Username Discord Bot.
This provides a web interface to monitor the bot's status and view statistics.
"""
import os
import time
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify
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

            # Get checks in last 5 minutes
            cursor.execute(
                "SELECT COUNT(*) FROM checked_usernames WHERE checked_at >= %s",
                (datetime.now() - timedelta(minutes=5),)
            )
            checks_last_24h = cursor.fetchone()[0] or 0

            # Get available in last 5 minutes
            cursor.execute(
                "SELECT COUNT(*) FROM checked_usernames WHERE is_available = TRUE AND checked_at >= %s",
                (datetime.now() - timedelta(minutes=5),)
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
    <title>Username Bot Dashboard</title>
    <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
    <style>
        body {
            padding: 1rem;
            color: #e6e6e6;
            background-color: #1c1c1c;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
        }
        .app-container {
            max-width: 1000px;
            margin: 0 auto;
        }
        .dashboard-card {
            background: #2d2d2d;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1rem;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
        }
        .stat-box {
            background: #363636;
            padding: 1.25rem;
            border-radius: 8px;
            text-align: center;
        }
        .stat-number {
            font-size: 1.8rem;
            font-weight: 600;
            color: #00ff9d;
            margin-bottom: 0.5rem;
        }
        .stat-label {
            color: #a6a6a6;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .status-badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 999px;
            font-size: 0.875rem;
            font-weight: 500;
        }
        .status-healthy { background-color: #00ff9d33; color: #00ff9d; }
        .status-degraded { background-color: #ffd70033; color: #ffd700; }
        .status-error { background-color: #ff4d4d33; color: #ff4d4d; }
        .cookie-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1rem;
        }
        .cookie-card {
            background: #363636;
            padding: 1rem;
            border-radius: 8px;
        }
    </style>
    <meta http-equiv="refresh" content="30">
</head>
<body>
    <div class="app-container">
        <div class="dashboard-card">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h2 class="m-0">Username Bot Status</h2>
                <span class="status-badge {{ 'status-healthy' if stats.api_status == 'Healthy' else 'status-degraded' if stats.api_status == 'Degraded' else 'status-error' }}">
                    {{ stats.api_status }}
                </span>
            </div>
        </div>

        <div class="dashboard-card">
            <h4 class="mb-3">Performance Overview</h4>
            <div class="stats-grid">
                <div class="stat-box">
                    <div class="stat-number">{{ stats.checks_last_24h }}</div>
                    <div class="stat-label">Checks/Min</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{{ "%.1f"|format(stats.success_rate) }}%</div>
                    <div class="stat-label">Success Rate</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{{ stats.available_found }}</div>
                    <div class="stat-label">Names Found</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{{ stats.cookie_count }}</div>
                    <div class="stat-label">Active Cookies</div>
                </div>
            </div>
        </div>

        <div class="dashboard-card">
            <h4 class="mb-3">Cookie Status</h4>
            <div class="cookie-grid">
                        {% for status in stats.cookie_status %}
                    {% set error_rate = status.error_count / max(1, (status.error_count + status.success_count)) * 100 %}
                    {% set checks_per_min = ((status.success_count|default(0) + status.error_count|default(0)) / 5)|round(1) %}
                    <div class="cookie-card">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <strong>Cookie #{{ loop.index }}</strong>
                            <span class="status-badge {{ 'status-healthy' if error_rate < 20 else 'status-degraded' if error_rate < 50 else 'status-error' }}">
                                {{ "%.1f"|format(error_rate) }}% Errors
                            </span>
                        </div>
                        <div class="d-flex justify-content-between text-muted">
                            <small>{{ checks_per_min }} checks/min</small>
                            <small>Last used: {{ status.last_used_ago }}</small>
                        </div>
                    </div>
                {% endfor %}
            </div>
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