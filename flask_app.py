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
        # Get cookie information from roblox_api
        from roblox_api import adaptive_system
        current_time = time.time()

        cookie_status = []
        if adaptive_system and adaptive_system.cookie_status:
            for status in adaptive_system.cookie_status:
                total = status['success_count'] + status['error_count']
                success_rate = (status['success_count'] / max(1, total)) * 100

                # Calculate time since last use
                time_diff = current_time - status['last_used']
                if time_diff < 60:
                    last_used_ago = f"{int(time_diff)}s ago"
                elif time_diff < 3600:
                    last_used_ago = f"{int(time_diff/60)}m ago"
                else:
                    last_used_ago = f"{int(time_diff/3600)}h ago"

                cookie_status.append({
                    'success_rate': success_rate,
                    'cooldown_until': status['cooldown_until'],
                    'last_used_ago': last_used_ago
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
                "current_time": current_time
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

            # Get adaptive learning stats
            adaptive_learning = {}
            try:
                # Check if adaptive state file exists
                if os.path.exists('adaptive_state.json'):
                    import json
                    with open('adaptive_state.json', 'r') as f:
                        state = json.load(f)

                    # Get key parameters
                    adaptive_learning = {
                        'parallel_checks': state.get('parallel_checks', 10),
                        'underscore_probability': state.get('underscore_probability', 0.2),
                        'numeric_probability': state.get('numeric_probability', 0.3),
                        'uppercase_probability': state.get('uppercase_probability', 0.4),
                        'length_weights': state.get('length_weights', {}),
                        'last_updated': state.get('last_updated', 'Unknown')
                    }

                    # Calculate normalized length distribution
                    length_weights = adaptive_learning.get('length_weights', {})
                    if length_weights:
                        total_weight = sum(float(v) for v in length_weights.values())
                        if total_weight > 0:
                            adaptive_learning['length_distribution'] = {
                                k: round(float(v)/total_weight * 100, 1) 
                                for k, v in length_weights.items()
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
                "adaptive_learning": adaptive_learning
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

        /* Roblox username chat color classes */
        .username-color-0 { color: #E74C3C; } /* Red */
        .username-color-1 { color: #3498DB; } /* Blue */
        .username-color-2 { color: #2ECC71; } /* Green */
        .username-color-3 { color: #9B59B6; } /* Purple */
        .username-color-4 { color: #E67E22; } /* Orange */
        .username-color-5 { color: #F1C40F; } /* Yellow */
        .username-color-6 { color: #FF9FF3; } /* Pink */
        .username-color-7 { color: #A47D5E; } /* Almond */

        /* Copy button styling */
        .copy-icon {
            margin-left: 5px;
            font-size: 0.8em;
            opacity: 0.6;
        }
        span[onclick] {
            transition: all 0.2s ease;
        }
        span[onclick]:hover {
            background-color: #343a40;
            transform: scale(1.05);
        }
        .copy-success {
            animation: copy-flash 1s;
        }
        @keyframes copy-flash {
            0% { background-color: #343a40; }
            50% { background-color: #28a745; }
            100% { background-color: #343a40; }
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

        /* Username color classes based on Roblox chat colors */
        .username-color-0 { color: #F54545; } /* Red */
        .username-color-1 { color: #00A2FF; } /* Blue */
        .username-color-2 { color: #02B757; } /* Green */
        .username-color-3 { color: #AC5CB1; } /* Purple */
        .username-color-4 { color: #FF8134; } /* Orange */
        .username-color-5 { color: #FFCC00; } /* Yellow */
        .username-color-6 { color: #FF73BE; } /* Pink */
        .username-color-7 { color: #D4A681; } /* Almond */

        /* Copy success animation */
        .copy-success {
            background-color: #198754 !important;
            color: white !important;
            transition: all 0.3s ease;
        }

        /* Valuable username highlighting */
        .valuable-username {
            font-weight: bold;
            position: relative;
        }

        .valuable-username::before {
            content: "💎";
            position: absolute;
            left: -20px;
            top: 3px;
        }
    </style>
    <meta http-equiv="refresh" content="60">
    <script>
        // Copy to clipboard functionality
        function copyToClipboard(text) {
            // Create a temporary input element
            const input = document.createElement('input');
            input.setAttribute('value', text);
            document.body.appendChild(input);
            input.select();

            // Execute copy command
            document.execCommand('copy');

            // Clean up
            document.body.removeChild(input);

            // Visual feedback
            // Using a safer approach for selector to avoid issues with special characters
            const elements = document.querySelectorAll('span[title="Click to copy"]');
            elements.forEach(element => {
                if (element.textContent.trim().includes(text)) {
                    element.classList.add('copy-success');
                    setTimeout(() => {
                        element.classList.remove('copy-success');
                    }, 1000);

                    // Change icon temporarily
                    const icon = element.querySelector('.copy-icon');
                    if (icon) {
                        const originalText = icon.innerHTML;
                        icon.innerHTML = '✅';
                        setTimeout(() => {
                            icon.innerHTML = originalText;
                        }, 1000);
                    }
                }
            });
        }
    </script>
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

                        {% if stats.adaptive_learning %}
                        <h5>Adaptive Learning System</h5>
                        <div class="row mb-3">
                            <div class="col-md-12">
                                <div class="d-flex flex-wrap">
                                    <div class="text-center p-2 border rounded me-2 mb-2" style="min-width: 125px;">
                                        <div class="stats-number">{{ stats.adaptive_learning.parallel_checks }}</div>
                                        <div class="stats-label">Parallel Checks</div>
                                    </div>
                                    <div class="text-center p-2 border rounded me-2 mb-2" style="min-width: 125px;">
                                        <div class="stats-number">{{ "%.1f"|format(stats.adaptive_learning.underscore_probability * 100) }}%</div>
                                        <div class="stats-label">Underscore Prob.</div>
                                    </div>
                                    <div class="text-center p-2 border rounded me-2 mb-2" style="min-width: 125px;">
                                        <div class="stats-number">{{ "%.1f"|format(stats.adaptive_learning.numeric_probability * 100) }}%</div>
                                        <div class="stats-label">Number Prob.</div>
                                    </div>
                                    <div class="text-center p-2 border rounded mb-2" style="min-width: 125px;">
                                        <div class="stats-number">{{ "%.1f"|format(stats.adaptive_learning.uppercase_probability * 100) }}%</div>
                                        <div class="stats-label">Uppercase Prob.</div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {% if stats.adaptive_learning.length_distribution %}
                        <div class="card mb-3">
                            <div class="card-header py-2">
                                <h6 class="mb-0">Username Length Distribution</h6>
                            </div>
                            <div class="card-body py-2">
                                <div class="progress mb-2" style="height: 25px;">
                                    {% for length, percentage in stats.adaptive_learning.length_distribution.items()|sort %}
                                    <div class="progress-bar bg-{{ ['success', 'info', 'primary', 'warning', 'danger', 'secondary']|random }}" 
                                         role="progressbar" 
                                         style="width: {{ percentage }}%" 
                                         aria-valuenow="{{ percentage }}" 
                                         aria-valuemin="0" 
                                         aria-valuemax="100"
                                         title="Length {{ length }}: {{ percentage }}%">
                                        {{ length }}
                                    </div>
                                    {% endfor %}
                                </div>
                                <div class="small text-muted">
                                    Last updated: {{ stats.adaptive_learning.last_updated|default('Unknown') }}
                                </div>
                            </div>
                        </div>
                        {% endif %}
                        {% endif %}

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

                <!-- Cookie Status -->
                <div class="card stats-card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h4>Cookie Status</h4>
                        <span class="badge bg-primary">{{ stats.cookie_count }} Active</span>
                    </div>
                    <div class="card-body">
                        {% if stats.cookie_status %}
                        <div class="alert alert-info mb-3">
                            {% set working_cookies = stats.cookie_status|selectattr('success_rate')|selectattr('success_rate', 'float')|selectattr('success_rate', '>=', 80.0)|list|length %}
                            {% set degraded_cookies = stats.cookie_status|selectattr('success_rate')|selectattr('success_rate', 'float')|selectattr('success_rate', '>=', 50.0)|selectattr('success_rate', '<', 80.0)|list|length %}
                            {% set poor_cookies = stats.cookie_status|selectattr('success_rate')|selectattr('success_rate', 'float')|selectattr('success_rate', '<', 50.0)|list|length %}
                            <strong>Cookie Status Summary:</strong><br>
                            ✅ Working well: {{ working_cookies }} cookies (80%+ success rate)<br>
                            ⚠️ Degraded: {{ degraded_cookies }} cookies (50-80% success rate)<br>
                            ❌ Poor performance: {{ poor_cookies }} cookies (<50% success rate)
                        </div>
                        <div class="table-responsive">
                            <table class="table table-sm">
                                <thead>
                                    <tr>
                                        <th>Cookie #</th>
                                        <th>Success Rate</th>
                                        <th>Status</th>
                                        <th>Last Used</th>
                                        <th>Success/Error</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for status in stats.cookie_status %}
                                    <tr>
                                        <td>{{ loop.index }}</td>
                                        <td>
                                            <div class="progress" style="height: 15px;">
                                                <div class="progress-bar {% if status.success_rate >= 80 %}bg-success{% elif status.success_rate >= 50 %}bg-warning{% else %}bg-danger{% endif %}" 
                                                     role="progressbar" 
                                                     style="width: {{ status.success_rate }}%"
                                                     aria-valuenow="{{ status.success_rate }}" 
                                                     aria-valuemin="0" 
                                                     aria-valuemax="100">
                                                    {{ "%.1f"|format(status.success_rate) }}%
                                                </div>
                                            </div>
                                        </td>
                                        <td>
                                            {% if status.cooldown_until > current_time %}
                                            <span class="badge bg-warning">Cooldown</span>
                                            {% elif status.success_rate >= 80 %}
                                            <span class="badge bg-success">Healthy</span>
                                            {% elif status.success_rate >= 50 %}
                                            <span class="badge bg-warning">Degraded</span>
                                            {% else %}
                                            <span class="badge bg-danger">Poor</span>
                                            {% endif %}
                                        </td>
                                        <td><small>{{ status.last_used_ago }}</small></td>
                                        <td><small>{{ status.success_count }}/{{ status.error_count }}</small></td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                        {% else %}
                        <div class="alert alert-warning">
                            No cookie status information available
                        </div>
                        {% endif %}
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
                                            <th>Chat Color</th>
                                            <th>Length</th>
                                            <th>Found At</th>
                                            <th>Action</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {% for username in recent_usernames %}
                                            <tr>
                                                <td {% if username.username|length <= 4 %}class="valuable-username"{% endif %}>
                                                    <!-- Show username in its chat color with CSS -->
                                                    <span style="background-color: #f8f9fa; border-radius: 4px; padding: 3px 6px; cursor: pointer;" 
                                                          onclick="copyToClipboard('{{ username.username }}')" 
                                                          title="Click to copy"
                                                          class="username-color-{{ username.color_class }}">
                                                        <code>{{ username.username }}</code>
                                                        <i class="copy-icon">📋</i>
                                                    </span>
                                                </td>
                                                <td>{{ username.chat_color }}</td>
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

                        <h5>🌈 Chat Color Prediction</h5>
                        <p>The bot predicts which chat color each username will have in Roblox using the official algorithm from Roblox's <a href="https://github.com/Roblox/Core-Scripts/blob/master/CoreScriptsRoot/Modules/Chat.lua" target="_blank">Core-Scripts repository</a>.</p>
                        <div class="d-flex flex-wrap">
                            <div class="me-2 mb-2 p-1 border rounded"><span class="me-1">🔴</span>Red</div>
                            <div class="me-2 mb-2 p-1 border rounded"><span class="me-1">🔵</span>Blue</div>
                            <div class="me-2 mb-2 p-1 border rounded"><span class="me-1">🟢</span>Green</div>
                            <div class="me-2 mb-2 p-1 border rounded"><span class="me-1">🟣</span>Purple</div>
                            <div class="me-2 mb-2 p-1 border rounded"><span class="me-1">🟠</span>Orange</div>
                            <div class="me-2 mb-2 p-1 border rounded"><span class="me-1">🟡</span>Yellow</div>
                            <div class="me-2 mb-2 p-1 border rounded"><span class="me-1">🌸</span>Pink</div>
                            <div class="me-2 mb-2 p-1 border rounded"><span class="me-1">🟤</span>Almond</div>
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

    # Add cookie status if not present
    if not stats.get('cookie_status'):
        from roblox_api import adaptive_system
        if adaptive_system and adaptive_system.cookie_status:
            current_time = time.time()
            stats['cookie_status'] = []
            for i, status in enumerate(adaptive_system.cookie_status):
                total = status['success_count'] + status['error_count']
                success_rate = (status['success_count'] / max(1, total)) * 100
                time_diff = current_time - status['last_used']

                if time_diff < 60:
                    last_used_ago = f"{int(timediff)}s ago"
                elif time_diff < 36000:
                    last_used_ago = f"{int(time_diff/60)}m ago"
                else:
                    last_used_ago = f"{int(time_diff/3600)}h ago"

                stats['cookie_status'].append({
                    'success_rate': success_rate,
                    'success_count': status['success_count'],
                    'error_count': status['error_count'],
                    'cooldown_until': status['cooldown_until'],
                    'last_used_ago': last_used_ago
                })

    # Get recently available usernames
    recent_usernames = get_recently_available_usernames(20)  # Show up to 20 recent usernames

    # Format timestamps for display and calculate chat colors
    chat_colors = [
        {"name": "Red", "emoji": "🔴"},
        {"name": "Blue", "emoji": "🔵"},
        {"name": "Green", "emoji": "🟢"},
        {"name": "Purple", "emoji": "🟣"},
        {"name": "Orange", "emoji": "🟠"},
        {"name": "Yellow", "emoji": "🟡"},
        {"name": "Pink", "emoji": "🌸"},
        {"name": "Almond", "emoji": "🟤"}
    ]

    # Function to determine chat color (ported from Roblox source code)
    def get_chat_color(username):
        def get_name_value(pName):
            value = 0
            for index in range(1, len(pName) + 1):
                c_value = ord(pName[index - 1])
                reverse_index = len(pName) - index + 1

                if len(pName) % 2 == 1:
                    reverse_index = reverse_index - 1

                if reverse_index % 4 >= 2:
                    c_value = -c_value

                value = value + c_value

            return value

        # Calculate name value and get color index
        color_offset = 0
        name_value = get_name_value(username)
        color_index = ((name_value + color_offset) % len(chat_colors))

        return chat_colors[color_index]

    for username in recent_usernames:
        username['checked_at'] = username['checked_at'].strftime('%Y-%m-%d %H:%M:%S')
        color = get_chat_color(username['username'])
        username['chat_color'] = f"{color['emoji']} {color['name']}"
        # Add color class for CSS styling (0-7 index based on color name)
        color_index = chat_colors.index(color)
        username['color_class'] = str(color_index)

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