"""
Main entry point for the Roblox Username Discord Bot.
This file initializes and runs the Discord bot.

It also provides a Flask web application to monitor the bot's status.
"""
# Import Flask app for web interface
from flask_app import app
import os
import logging
from dotenv import load_dotenv
from bot import RobloxUsernameBot
from database import init_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('roblox_username_bot')

# Load environment variables
load_dotenv()
discord_token = os.getenv('DISCORD_TOKEN')
channel_id = os.getenv('CHANNEL_ID')

# Log environment variables (without revealing token)
logger.info(f"Discord token loaded: {'Yes' if discord_token else 'No'}")
logger.info(f"Channel ID configured: {channel_id}")

if not discord_token:
    logger.error("DISCORD_TOKEN environment variable not set")
    exit(1)

if not channel_id:
    logger.error("CHANNEL_ID environment variable not set")
    exit(1)

try:
    channel_id = int(channel_id)
except ValueError:
    logger.error("CHANNEL_ID must be an integer")
    exit(1)

# Set check interval (in seconds) - default is 5s for fast operation
try:
    check_interval = int(os.getenv('CHECK_INTERVAL', '5'))
    if check_interval < 1:
        logger.warning("CHECK_INTERVAL too low, setting to minimum of 1 second")
        check_interval = 1
except ValueError:
    logger.warning("Invalid CHECK_INTERVAL value, defaulting to 5 seconds")
    check_interval = 5

# Initialize the database tables
init_database()

if __name__ == "__main__":
    logger.info("Starting Roblox Username Discord Bot")
    
    # Check for all Roblox cookies (no arbitrary limit)
    roblox_cookies = []
    
    # Scan all environment variables for Roblox cookies
    all_cookies = {}
    for env_var, value in os.environ.items():
        if env_var.startswith('ROBLOX_COOKIE'):
            try:
                if env_var == 'ROBLOX_COOKIE':
                    index = 0  # Main cookie gets index 0
                else:
                    # Extract number after 'ROBLOX_COOKIE'
                    index_str = env_var[13:]
                    if index_str:
                        index = int(index_str)
                    else:
                        logger.warning(f"Invalid cookie variable name format: {env_var}")
                        continue

                # Store cookie with its index for sorting later
                if value and len(value) > 50:  # Basic validation
                    all_cookies[index] = value
                    logger.info(f"Found valid cookie {env_var} (length: {len(value)})")
                else:
                    logger.warning(f"Skipping cookie {env_var} because it appears invalid (length: {len(value) if value else 0})")
            except ValueError:
                logger.warning(f"Skipping invalid cookie variable: {env_var}")
                continue

    # Sort cookies by index and add to list
    for index in sorted(all_cookies.keys()):
        roblox_cookies.append(all_cookies[index])
    
    # Count all available cookies in environment variables (for verification)
    cookie_count = 0
    for key in os.environ:
        if key.startswith("ROBLOX_COOKIE") and len(os.environ[key]) > 50:
            cookie_count += 1
    
    if cookie_count != len(roblox_cookies):
        logger.warning(f"Found {cookie_count} cookies in environment but only loaded {len(roblox_cookies)} valid cookies")
    
    if roblox_cookies:
        logger.info(f"Found {len(roblox_cookies)} Roblox cookies, will be used for API requests")
        for i, cookie in enumerate(roblox_cookies):
            logger.info(f"Cookie {i+1} loaded successfully (length: {len(cookie)})")
    else:
        logger.warning("No valid Roblox cookies found. Bot will operate in unauthenticated mode with lower success rates.")
    
    # Initialize the bot with cookies
    bot = RobloxUsernameBot(
        token=discord_token,
        channel_id=channel_id,
        check_interval=check_interval,
        cookies=roblox_cookies
    )
    
    try:
        bot.run()
    except Exception as e:
        logger.error(f"Bot crashed: {str(e)}")
        exit(1)
