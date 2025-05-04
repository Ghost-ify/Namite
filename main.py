"""
Main entry point for the Roblox Username Discord Bot.
This file initializes and runs the Discord bot.

It also provides a Flask web application to monitor the bot's status.
"""
# Import Flask app for web interface
from flask_app import app
import os
import logging
import asyncio
from dotenv import load_dotenv
from bot import RobloxUsernameBot
from database import init_database
from roblox_api import verify_cookie

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

# Authenticate with Roblox if a cookie is available
async def authenticate_roblox():
    """Authenticate with Roblox using the provided cookie."""
    try:
        result = await verify_cookie()
        if result:
            logger.info("Roblox authentication successful")
        else:
            logger.warning("Roblox authentication failed or cookie not provided")
    except Exception as e:
        logger.error(f"Error during Roblox authentication: {str(e)}")

# Create an event loop to run the authentication
def run_auth():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(authenticate_roblox())
    loop.close()

if __name__ == "__main__":
    logger.info("Starting Roblox Username Discord Bot")
    
    # Run Roblox authentication before starting the bot
    run_auth()
    
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
