"""
Flask web application for the Roblox Username Discord Bot.
This provides a simple web interface to monitor the bot's status.
"""
import os
from flask import Flask, render_template_string, jsonify
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create and configure the Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', 'dev-key-for-testing')

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
        }
        .stats-card {
            margin-bottom: 1.5rem;
        }
    </style>
</head>
<body data-bs-theme="dark">
    <div class="container">
        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h1 class="h3 mb-0">Roblox Username Bot Dashboard</h1>
                    </div>
                    <div class="card-body">
                        <div class="alert alert-success" role="alert">
                            <h4 class="alert-heading">Bot Status</h4>
                            <p>Your Roblox Username Bot is currently running in the background!</p>
                            <hr>
                            <p class="mb-0">The bot is continuously checking for available Roblox usernames and will post any findings to your Discord channel.</p>
                        </div>
                        
                        <div class="card stats-card">
                            <div class="card-header">
                                <h4>Configuration</h4>
                            </div>
                            <div class="card-body">
                                <ul class="list-group list-group-flush">
                                    <li class="list-group-item d-flex justify-content-between align-items-center">
                                        Discord Connection
                                        <span class="badge bg-success">Active</span>
                                    </li>
                                    <li class="list-group-item d-flex justify-content-between align-items-center">
                                        Channel ID
                                        <span class="badge bg-secondary">{{ channel_id }}</span>
                                    </li>
                                    <li class="list-group-item d-flex justify-content-between align-items-center">
                                        Check Interval
                                        <span class="badge bg-info">{{ check_interval }} seconds</span>
                                    </li>
                                </ul>
                            </div>
                        </div>
                        
                        <div class="card stats-card">
                            <div class="card-header">
                                <h4>Instructions</h4>
                            </div>
                            <div class="card-body">
                                <p>The bot is autonomous and doesn't require any interaction through this interface.</p>
                                <p>You can monitor available usernames in your Discord channel.</p>
                                <p>If you want to make changes to the bot configuration:</p>
                                <ol>
                                    <li>Edit the <code>.env</code> file</li>
                                    <li>Restart the bot using the "run_discord_bot" workflow</li>
                                </ol>
                            </div>
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
    """Display the bot dashboard."""
    check_interval = os.environ.get('CHECK_INTERVAL', '60')
    channel_id = os.environ.get('CHANNEL_ID', 'Not configured')
    
    return render_template_string(
        DASHBOARD_HTML, 
        channel_id=channel_id,
        check_interval=check_interval
    )

@app.route('/health')
def health():
    """Simple health check endpoint."""
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)