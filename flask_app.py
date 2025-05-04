"""
Flask web application for the Roblox Username Discord Bot.
This provides a web interface to monitor the bot's status, view statistics,
and see recently found available usernames.
"""
import os
import time
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify
from dotenv import load_dotenv
from database import get_recently_available_usernames, get_db_connection, init_database

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
                "api_status": "Unknown"
            }
            
        cursor = conn.cursor()
        
        try:
            # Get total checked
            cursor.execute("SELECT COUNT(*) FROM checked_usernames")
            total_checked = cursor.fetchone()[0] or 0
            
            # Get available found
            cursor.execute("SELECT COUNT(*) FROM checked_usernames WHERE is_available = TRUE")
            available_found = cursor.fetchone()[0] or 0
            
            # Get error count (status_code 0 or >= 400 indicates errors)
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
            
            # Calculate success rate (excluding errors)
            valid_checks = total_checked - errors_count
            valid_checks_24h = checks_last_24h - errors_last_24h
            
            success_rate = (available_found / valid_checks * 100) if valid_checks > 0 else 0
            success_rate_24h = (available_last_24h / valid_checks_24h * 100) if valid_checks_24h > 0 else 0
            
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
                error_rate = (recent_errors / recent_checks) * 100
                if error_rate > 50:
                    api_status = "Critical"
                elif error_rate > 20:
                    api_status = "Degraded"
            elif errors_last_24h > 0:
                api_status = "Unknown (No Recent Checks)"
            
            return {
                "total_checked": total_checked,
                "available_found": available_found,
                "checks_last_24h": checks_last_24h,
                "available_last_24h": available_last_24h,
                "errors_count": errors_count,
                "errors_last_24h": errors_last_24h,
                "success_rate": success_rate,
                "success_rate_24h": success_rate_24h,
                "api_status": api_status
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
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        .stats-card {
            margin-bottom: 1.5rem;
        }
        .valuable-username {
            font-weight: bold;
            color: #ffc107;
        }
        .stats-number {
            font-size: 1.5rem;
            font-weight: bold;
        }
        .stats-label {
            font-size: 0.9rem;
            opacity: 0.8;
        }
        .refresh-button {
            margin-bottom: 1rem;
        }
        .api-status {
            padding: 0.5rem;
            border-radius: 0.25rem;
            margin-bottom: 0.5rem;
        }
        .api-enabled {
            background-color: rgba(40, 167, 69, 0.2);
        }
        .api-disabled {
            background-color: rgba(220, 53, 69, 0.2);
        }
        .progress {
            height: 0.5rem;
        }
    </style>
    <meta http-equiv="refresh" content="60">
</head>
<body data-bs-theme="dark">
    <div class="container">
        <div class="row">
            <div class="col-12 mb-4">
                <div class="d-flex justify-content-between align-items-center">
                    <h1>Roblox Username Bot Dashboard</h1>
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
        </div>

        <div class="row">
            <div class="col-md-6">
                <!-- Bot Status -->
                <div class="card stats-card">
                    <div class="card-header">
                        <h4>Bot Status</h4>
                    </div>
                    <div class="card-body">
                        <div class="alert alert-success" role="alert">
                            <h5 class="alert-heading">✅ Bot Active</h5>
                            <p>The bot is continuously checking for available Roblox usernames and posting findings to Discord.</p>
                        </div>
                        
                        {% if stats.api_status == "Healthy" %}
                        <div class="alert alert-success mb-3" role="alert">
                            <h5 class="alert-heading">✅ API Status: Healthy</h5>
                            <p class="mb-0">The Roblox API connections are working properly.</p>
                        </div>
                        {% elif stats.api_status == "Degraded" %}
                        <div class="alert alert-warning mb-3" role="alert">
                            <h5 class="alert-heading">⚠️ API Status: Degraded</h5>
                            <p class="mb-0">The Roblox API is experiencing some issues. Some checks may fail.</p>
                        </div>
                        {% elif stats.api_status == "Critical" %}
                        <div class="alert alert-danger mb-3" role="alert">
                            <h5 class="alert-heading">🚫 API Status: Critical</h5>
                            <p class="mb-0">The Roblox API is experiencing significant issues. Most checks are failing.</p>
                        </div>
                        {% else %}
                        <div class="alert alert-secondary mb-3" role="alert">
                            <h5 class="alert-heading">❓ API Status: {{ stats.api_status }}</h5>
                            <p class="mb-0">Unable to determine the current API status.</p>
                        </div>
                        {% endif %}
                        
                        <div class="d-flex justify-content-between align-items-center mb-3">
                            <div class="text-center p-3 border rounded flex-fill me-2">
                                <div class="stats-number">{{ stats.total_checked }}</div>
                                <div class="stats-label">Total Checks</div>
                            </div>
                            <div class="text-center p-3 border rounded flex-fill me-2">
                                <div class="stats-number">{{ stats.available_found }}</div>
                                <div class="stats-label">Available Found</div>
                            </div>
                            <div class="text-center p-3 border rounded flex-fill">
                                <div class="stats-number">{{ "%.2f"|format(stats.success_rate) }}%</div>
                                <div class="stats-label">Success Rate</div>
                            </div>
                        </div>
                        
                        <div class="text-muted small mb-2">* Success rate excludes error responses from calculations.</div>
                        
                        <h5>24-Hour Activity</h5>
                        <div class="d-flex justify-content-between align-items-center mb-3">
                            <div class="text-center p-2 border rounded flex-fill me-2">
                                <div class="stats-number">{{ stats.checks_last_24h }}</div>
                                <div class="stats-label">Recent Checks</div>
                            </div>
                            <div class="text-center p-2 border rounded flex-fill me-2">
                                <div class="stats-number">{{ stats.available_last_24h }}</div>
                                <div class="stats-label">Recent Finds</div>
                            </div>
                            <div class="text-center p-2 border rounded flex-fill">
                                <div class="stats-number">{{ stats.errors_last_24h }}</div>
                                <div class="stats-label">API Errors</div>
                            </div>
                        </div>
                        
                        <div class="progress mb-1">
                            <div class="progress-bar bg-success" role="progressbar" style="width: {{ stats.success_rate_24h }}%" 
                                 aria-valuenow="{{ stats.success_rate_24h }}" aria-valuemin="0" aria-valuemax="100"></div>
                        </div>
                        <div class="text-muted small text-end">24h Success Rate: {{ "%.2f"|format(stats.success_rate_24h) }}%</div>
                        
                        {% if stats.errors_last_24h > 0 %}
                        <div class="alert alert-warning mt-3">
                            <h6 class="alert-heading">⚠️ API Errors Detected</h6>
                            <p class="mb-0">Some username checks have failed due to API errors ({{ stats.errors_last_24h }} in the last 24 hours). The bot will automatically retry and adapt to changing API conditions.</p>
                        </div>
                        {% endif %}
                    </div>
                </div>
                
                <!-- Configuration -->
                <div class="card stats-card">
                    <div class="card-header">
                        <h4>Configuration</h4>
                    </div>
                    <div class="card-body">
                        <ul class="list-group list-group-flush">
                            <li class="list-group-item d-flex justify-content-between align-items-center">
                                <div>
                                    <strong>Discord Connection</strong>
                                    <div class="text-muted small">Bot is posting to your Discord channel</div>
                                </div>
                                <span class="badge bg-success">Active</span>
                            </li>
                            <li class="list-group-item d-flex justify-content-between align-items-center">
                                <div>
                                    <strong>Channel ID</strong>
                                    <div class="text-muted small">Target Discord channel</div>
                                </div>
                                <span class="badge bg-secondary">{{ channel_id }}</span>
                            </li>
                            <li class="list-group-item d-flex justify-content-between align-items-center">
                                <div>
                                    <strong>Check Interval</strong>
                                    <div class="text-muted small">Time between batch checks</div>
                                </div>
                                <span class="badge bg-info">{{ check_interval }}s</span>
                            </li>
                            <li class="list-group-item d-flex justify-content-between align-items-center">
                                <div>
                                    <strong>Username Length</strong>
                                    <div class="text-muted small">Valid username character count</div>
                                </div>
                                <span class="badge bg-primary">3-20 characters</span>
                            </li>
                        </ul>
                    </div>
                </div>
            </div>
            
            <div class="col-md-6">
                <!-- Recently Available Usernames -->
                <div class="card stats-card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h4>Recently Available Usernames</h4>
                        <span class="badge bg-success">{{ recent_usernames|length }} found</span>
                    </div>
                    <div class="card-body">
                        {% if recent_usernames %}
                            <div class="table-responsive">
                                <table class="table table-striped table-hover">
                                    <thead>
                                        <tr>
                                            <th>Username</th>
                                            <th>Length</th>
                                            <th>Found At</th>
                                            <th>Action</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {% for username in recent_usernames %}
                                            <tr>
                                                <td {% if username.username|length <= 4 %}class="valuable-username"{% endif %}>
                                                    {{ username.username }}
                                                </td>
                                                <td>{{ username.username|length }}</td>
                                                <td>{{ username.checked_at }}</td>
                                                <td>
                                                    <a href="https://www.roblox.com/signup" target="_blank" class="btn btn-sm btn-outline-primary">
                                                        Claim
                                                    </a>
                                                </td>
                                            </tr>
                                        {% endfor %}
                                    </tbody>
                                </table>
                            </div>
                            <div class="alert alert-warning mt-3" role="alert">
                                <small>⚠️ These usernames may have been claimed since they were found. Try to claim them quickly!</small>
                            </div>
                        {% else %}
                            <div class="alert alert-info" role="alert">
                                No available usernames found yet. The bot will continue checking and display results here when found.
                            </div>
                        {% endif %}
                    </div>
                </div>
                
                <!-- Instructions -->
                <div class="card stats-card">
                    <div class="card-header">
                        <h4>Instructions</h4>
                    </div>
                    <div class="card-body">
                        <p>The bot is fully autonomous and runs in the background. You can use these Discord commands:</p>
                        <div class="bg-dark p-3 rounded mb-3">
                            <code>!roblox check &lt;username&gt;</code> - Check if a specific username is available<br>
                            <code>!roblox length &lt;number&gt;</code> - Generate and check usernames of specific length<br>
                            <code>!roblox length &lt;min&gt;-&lt;max&gt;</code> - Check usernames in a length range<br>
                            <code>!roblox stats</code> - Show bot statistics<br>
                            <code>!roblox recent</code> - Show recently found usernames<br>
                            <code>!roblox help</code> - Show help message
                        </div>
                        
                        <h5>Username Rules</h5>
                        <ul>
                            <li>Length: 3-20 characters</li>
                            <li>Allowed characters: letters, numbers, and underscore (_)</li>
                            <li>Cannot start or end with an underscore</li>
                            <li>Maximum one underscore</li>
                            <li>Cannot be all numbers</li>
                        </ul>
                        
                        <div class="alert alert-secondary" role="alert">
                            <small>💎 Usernames with 3-4 characters are considered more valuable and will trigger Discord pings.</small>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def dashboard():
    """Display the bot dashboard with stats and recent available usernames."""
    # Get configuration values
    check_interval = os.environ.get('CHECK_INTERVAL', '60')
    channel_id = os.environ.get('CHANNEL_ID', 'Not configured')
    
    # Get statistics
    stats = get_bot_statistics()
    
    # Get recently available usernames
    recent_usernames = get_recently_available_usernames(20)  # Show up to 20 recent usernames
    
    # Format timestamps for display
    for username in recent_usernames:
        username['checked_at'] = username['checked_at'].strftime('%Y-%m-%d %H:%M:%S')
    
    # Get generator settings
    min_length = os.environ.get('MIN_LENGTH', '3') 
    max_length = os.environ.get('MAX_LENGTH', '6')
    batch_size = os.environ.get('BATCH_SIZE', '5')
    
    # Current time for display
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    return render_template_string(
        DASHBOARD_HTML, 
        channel_id=channel_id,
        check_interval=check_interval,
        stats=stats,
        recent_usernames=recent_usernames,
        current_time=current_time,
        min_length=min_length,
        max_length=max_length,
        batch_size=batch_size
    )

@app.route('/health')
def health():
    """Simple health check endpoint."""
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)