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

# Set check interval (in seconds) - default is 60s
try:
    check_interval = int(os.getenv('CHECK_INTERVAL', '60'))
    if check_interval < 10:
        logger.warning("CHECK_INTERVAL too low, setting to minimum of 10 seconds")
        check_interval = 10
except ValueError:
    logger.warning("Invalid CHECK_INTERVAL value, defaulting to 60 seconds")
    check_interval = 60

if __name__ == "__main__":
    logger.info("Starting Roblox Username Discord Bot")
    bot = RobloxUsernameBot(
        token=discord_token,
        channel_id=channel_id,
        check_interval=check_interval
    )
    
    try:
        bot.run()
    except Exception as e:
        logger.error(f"Bot crashed: {str(e)}")
        exit(1)
