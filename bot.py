"""
Discord bot implementation for finding available Roblox usernames.
This file handles the Discord interaction and scheduling of username checks.
"""
import asyncio
import logging
import discord
import random
from datetime import datetime
from username_generator import generate_username
from roblox_api import check_username_availability

logger = logging.getLogger('roblox_username_bot')

class RobloxUsernameBot:
    def __init__(self, token, channel_id, check_interval=60):
        """
        Initialize the Roblox Username Discord Bot.
        
        Args:
            token (str): Discord bot token
            channel_id (int): Discord channel ID to post available usernames
            check_interval (int): Time between username checks in seconds
        """
        self.token = token
        self.channel_id = channel_id
        self.check_interval = check_interval
        
        # Initialize Discord client with default intents
        # No need for message_content privileged intent since we're not reading messages
        intents = discord.Intents.default()
        self.client = discord.Client(intents=intents)
        
        # Set up event handlers
        self.client.event(self.on_ready)
        self.client.event(self.on_error)
        
        # Track statistics
        self.stats = {
            'total_checked': 0,
            'available_found': 0,
            'start_time': None
        }
        
        # Flag to indicate if the username check task is running
        self.task_running = False

    async def on_ready(self):
        """Event handler for when the Discord bot is ready."""
        logger.info(f"Bot logged in as {self.client.user}")
        self.stats['start_time'] = datetime.now()
        
        # Start the username checking task if it's not already running
        if not self.task_running:
            self.task_running = True
            self.client.loop.create_task(self.check_usernames_task())

    async def on_error(self, event, *args, **kwargs):
        """Event handler for Discord errors."""
        logger.error(f"Discord error in {event}: {str(args[0])}")

    async def check_usernames_task(self):
        """Background task to periodically check for available usernames."""
        logger.info(f"Starting username check task (interval: {self.check_interval}s)")
        channel = self.client.get_channel(self.channel_id)
        
        if not channel:
            logger.error(f"Could not find channel with ID {self.channel_id}")
            return
        
        logger.info(f"Will post available usernames to channel: {channel.name}")
        
        # Post initial status message
        await channel.send(f"🤖 **Roblox Username Bot Started**\nChecking for available usernames every {self.check_interval} seconds...")
        
        while True:
            try:
                # Generate a username
                username = generate_username()
                self.stats['total_checked'] += 1
                
                logger.info(f"Checking availability of username: {username}")
                
                # Check if it's available
                is_available, status_code, message = await check_username_availability(username)
                
                if is_available:
                    self.stats['available_found'] += 1
                    logger.info(f"Available username found: {username}")
                    
                    # Create an embed message for the available username
                    embed = discord.Embed(
                        title="Available Roblox Username Found!",
                        description=f"**{username}**",
                        color=0x00ff00  # Green color
                    )
                    
                    embed.add_field(name="Length", value=str(len(username)), inline=True)
                    embed.add_field(name="Contains Underscore", value=str('_' in username), inline=True)
                    embed.set_footer(text=f"Bot running since {self.stats['start_time'].strftime('%Y-%m-%d %H:%M')}")
                    
                    # Add statistics
                    success_rate = (self.stats['available_found'] / self.stats['total_checked']) * 100
                    embed.add_field(
                        name="Statistics",
                        value=f"Available: {self.stats['available_found']}/{self.stats['total_checked']} ({success_rate:.2f}%)",
                        inline=False
                    )
                    
                    await channel.send(embed=embed)
                else:
                    logger.debug(f"Username '{username}' not available. Reason: {message}")
                
                # Add some randomness to the check interval to avoid detection patterns
                jitter = random.uniform(-2, 5)
                adjusted_interval = max(10, self.check_interval + jitter)  # Ensure minimum of 10 seconds
                
                await asyncio.sleep(adjusted_interval)
                
            except Exception as e:
                logger.error(f"Error in username check task: {str(e)}")
                # Wait a bit and continue
                await asyncio.sleep(10)

    def run(self):
        """Run the Discord bot."""
        self.client.run(self.token)
