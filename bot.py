"""
Discord bot implementation for finding available Roblox usernames.
This file handles the Discord interaction and scheduling of username checks.
"""
import asyncio
import logging
import discord
import random
import re
from datetime import datetime
from username_generator import generate_username, validate_username
from roblox_api import check_username_availability
from database import get_username_status, get_recently_available_usernames

logger = logging.getLogger('roblox_username_bot')

class RobloxUsernameBot:
    def __init__(self, token, channel_id, check_interval=10):
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
        
        # Initialize Discord client with intents
        intents = discord.Intents.default()
        # Try to enable message_content intent (for commands)
        try:
            intents.message_content = True
            logger.info("Message content intent enabled")
        except Exception as e:
            logger.warning(f"Could not enable message content intent: {str(e)}")
            logger.warning("Command functionality will be limited. Please enable MESSAGE CONTENT INTENT in Discord Developer Portal.")
            
        self.client = discord.Client(intents=intents)
        
        # Set up event handlers
        self.client.event(self.on_ready)
        self.client.event(self.on_error)
        
        # Only set up message handler if needed
        try:
            # Try to register the message handler
            self.client.event(self.on_message)
            logger.info("Message handler registered successfully")
        except Exception as e:
            logger.warning(f"Could not register message handler. Commands will not work: {str(e)}")
        
        # Track statistics
        self.stats = {
            'total_checked': 0,
            'available_found': 0,
            'start_time': None
        }
        
        # Flag to indicate if the username check task is running
        self.task_running = False
        
        # Number of parallel username checks to perform
        self.parallel_checks = 5
        
        # Semaphore to limit concurrent API requests
        self.semaphore = None

    async def on_ready(self):
        """Event handler for when the Discord bot is ready."""
        logger.info(f"Bot logged in as {self.client.user}")
        self.stats['start_time'] = datetime.now()
        
        # List all guilds (servers) and channels the bot can see
        logger.info("Listing all available guilds and channels:")
        if not self.client.guilds:
            logger.warning("Bot is not a member of any guilds (Discord servers)!")
            logger.warning("Please make sure you've invited the bot to your server.")
            logger.warning("See BOT_SETUP_GUIDE.md for instructions on how to invite your bot.")
        
        for guild in self.client.guilds:
            logger.info(f"Guild: {guild.name} (ID: {guild.id})")
            if not guild.text_channels:
                logger.warning(f"No text channels found in guild {guild.name}")
            
            for channel in guild.text_channels:
                logger.info(f"  - Channel: {channel.name} (ID: {channel.id})")
                
        # Try to fetch the channel directly from Discord (alternative method)
        try:
            direct_channel = self.client.get_channel(self.channel_id)
            if direct_channel:
                logger.info(f"Successfully found channel via get_channel: {direct_channel.name}")
            else:
                logger.warning(f"get_channel returned None for ID: {self.channel_id}")
                
                # Try a different method - fetch all channels
                all_channels = [channel for guild in self.client.guilds for channel in guild.text_channels]
                logger.info(f"Total channels accessible: {len(all_channels)}")
                
                # Log some channels for reference
                for i, channel in enumerate(all_channels[:5]):  # Log up to 5 channels
                    logger.info(f"Available channel #{i+1}: {channel.name} (ID: {channel.id})")
        except Exception as e:
            logger.error(f"Error while attempting to diagnose channel access: {str(e)}")
        
        # Start the username checking task if it's not already running
        if not self.task_running:
            self.task_running = True
            self.client.loop.create_task(self.check_usernames_task())

    async def on_error(self, event, *args, **kwargs):
        """Event handler for Discord errors."""
        logger.error(f"Discord error in {event}: {str(args[0])}")
        
    async def on_message(self, message):
        """Handle incoming Discord messages and commands."""
        # Ignore messages from the bot itself
        if message.author == self.client.user:
            return
            
        # Command prefix
        prefix = "!roblox"
        
        # Check if the message starts with the command prefix
        if not message.content.startswith(prefix):
            return
            
        # Parse the command
        command_parts = message.content[len(prefix):].strip().split()
        if not command_parts:
            # Just the prefix with no command
            await self.send_help_message(message.channel)
            return
            
        command = command_parts[0].lower()
        
        # Handle different commands
        if command == "check":
            # Check a specific username
            if len(command_parts) < 2:
                await message.channel.send("⚠️ Please provide a username to check. Example: `!roblox check username123`")
                return
                
            username = command_parts[1]
            await self.handle_check_command(message.channel, username)
            
        elif command == "help" or command == "?":
            # Show help message
            await self.send_help_message(message.channel)
            
        elif command == "stats":
            # Show bot statistics
            await self.send_stats_message(message.channel)
            
        elif command == "recent":
            # Show recently found available usernames
            await self.send_recent_available(message.channel)
            
        else:
            # Unknown command
            await message.channel.send(f"⚠️ Unknown command: `{command}`. Type `!roblox help` for a list of commands.")
    
    async def handle_check_command(self, channel, username):
        """Handle the !roblox check command to check a specific username."""
        # Validate the username format
        if not validate_username(username):
            await channel.send(f"⚠️ Invalid username format: `{username}`. Usernames must be 3-20 characters, can only contain letters, numbers, and one underscore (not at start/end), and cannot be all numbers.")
            return
            
        # Send a "checking" message
        checking_message = await channel.send(f"🔍 Checking availability of username: `{username}`...")
        
        try:
            # Check the availability
            is_available, status_code, message = await check_username_availability(username)
            
            if is_available:
                # Username properties
                username_length = len(username)
                is_valuable = username_length <= 4
                
                # Create an embed for available username
                embed = discord.Embed(
                    title="✅ Username is Available!",
                    description=f"**{username}**",
                    color=0x00ff00  # Green
                )
                
                embed.add_field(name="📏 Length", value=str(username_length), inline=True)
                embed.add_field(name="🔣 Contains Underscore", value=str('_' in username), inline=True)
                embed.add_field(name="💎 Valuable", value=str(is_valuable), inline=True)
                
                embed.add_field(
                    name="🔍 How to Claim",
                    value="Go to https://www.roblox.com/signup and enter this username before someone else claims it!",
                    inline=False
                )
                
                embed.set_footer(text="This username is available for registration on Roblox")
                
                # Determine if we should ping for this username
                if is_valuable:
                    ping_message = f"<@1017042087469912084> Valuable {username_length}-character username found!"
                    await checking_message.edit(content=ping_message, embed=embed)
                else:
                    await checking_message.edit(content=None, embed=embed)
            else:
                # Create an embed for unavailable username
                embed = discord.Embed(
                    title="❌ Username is Unavailable",
                    description=f"**{username}**",
                    color=0xff0000  # Red
                )
                embed.add_field(name="Reason", value=message, inline=False)
                embed.set_footer(text="This username cannot be registered on Roblox")
                
                await checking_message.edit(content=None, embed=embed)
        except Exception as e:
            logger.error(f"Error checking username {username}: {str(e)}")
            await checking_message.edit(content=f"⚠️ Error checking username: `{username}`. Please try again later.")
    
    async def send_help_message(self, channel):
        """Send help information about the bot and its commands."""
        embed = discord.Embed(
            title="🤖 Roblox Username Bot - Help",
            description="This bot helps you find available Roblox usernames.",
            color=0x3498db  # Blue
        )
        
        embed.add_field(
            name="Commands",
            value=(
                "🔹 `!roblox check <username>` - Check if a specific username is available\n"
                "🔹 `!roblox stats` - Show bot statistics\n"
                "🔹 `!roblox recent` - Show recently found available usernames\n"
                "🔹 `!roblox help` - Show this help message"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Username Rules",
            value=(
                "- Length: 3-20 characters\n"
                "- Allowed: letters, numbers, one underscore\n"
                "- No underscore at start/end\n"
                "- Cannot be all numbers"
            ),
            inline=False
        )
        
        embed.set_footer(text="Bot automatically checks random usernames in the background")
        
        await channel.send(embed=embed)
    
    async def send_stats_message(self, channel):
        """Send statistics about the bot's operations."""
        uptime = datetime.now() - self.stats['start_time'] if self.stats['start_time'] else datetime.now()
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"
        
        success_rate = 0
        if self.stats['total_checked'] > 0:
            success_rate = (self.stats['available_found'] / self.stats['total_checked']) * 100
        
        embed = discord.Embed(
            title="📊 Roblox Username Bot - Statistics",
            color=0x9b59b6  # Purple
        )
        
        embed.add_field(name="Uptime", value=uptime_str, inline=True)
        embed.add_field(name="Total Checked", value=str(self.stats['total_checked']), inline=True)
        embed.add_field(name="Available Found", value=str(self.stats['available_found']), inline=True)
        embed.add_field(name="Success Rate", value=f"{success_rate:.2f}%", inline=True)
        embed.add_field(name="Parallel Checks", value=str(self.parallel_checks), inline=True)
        embed.add_field(name="Check Interval", value=f"{self.check_interval}s", inline=True)
        
        embed.set_footer(text=f"Bot running since {self.stats['start_time'].strftime('%Y-%m-%d %H:%M')}")
        
        await channel.send(embed=embed)
    
    async def send_recent_available(self, channel):
        """Send a list of recently found available usernames."""
        recent_usernames = get_recently_available_usernames(10)
        
        if not recent_usernames:
            await channel.send("❓ No available usernames found yet. The bot will keep checking!")
            return
            
        embed = discord.Embed(
            title="🎯 Recently Found Available Usernames",
            description="These usernames were recently found to be available:",
            color=0x2ecc71  # Green
        )
        
        for i, username_data in enumerate(recent_usernames):
            username = username_data['username']
            timestamp = username_data['checked_at'].strftime('%Y-%m-%d %H:%M:%S')
            embed.add_field(
                name=f"{i+1}. {username}",
                value=f"Found at: {timestamp}",
                inline=False
            )
        
        embed.set_footer(text="These usernames may have been claimed since they were found")
        
        await channel.send(embed=embed)

    async def check_username(self, channel):
        """Check a single username and report if available."""
        try:
            # Generate a username
            username = generate_username()
            
            # Update stats (use atomic operation)
            self.stats['total_checked'] += 1
            
            logger.info(f"Checking availability of username: {username}")
            
            # Check if it's available
            is_available, status_code, message = await check_username_availability(username)
            
            if is_available:
                self.stats['available_found'] += 1
                logger.info(f"Available username found: {username}")
                
                # Create an embed message for the available username
                embed = discord.Embed(
                    title="✨ Available Roblox Username Found! ✨",
                    description=f"**{username}**",
                    color=0x00ff00  # Green color
                )
                
                # Add username properties
                username_length = len(username)
                is_valuable = username_length <= 4
                
                embed.add_field(name="📏 Length", value=str(username_length), inline=True)
                embed.add_field(name="🔣 Contains Underscore", value=str('_' in username), inline=True)
                embed.add_field(name="💎 Valuable", value=str(is_valuable), inline=True)
                
                # Add timestamp and additional information
                embed.add_field(
                    name="🔍 How to Claim",
                    value="Go to https://www.roblox.com/signup and enter this username before someone else claims it!",
                    inline=False
                )
                
                # Add statistics
                success_rate = (self.stats['available_found'] / self.stats['total_checked']) * 100
                embed.add_field(
                    name="📊 Statistics",
                    value=f"Available: {self.stats['available_found']}/{self.stats['total_checked']} ({success_rate:.2f}%)",
                    inline=False
                )
                
                embed.set_footer(text=f"Bot running since {self.stats['start_time'].strftime('%Y-%m-%d %H:%M')}")
                
                # Determine if we should ping for this username
                # Ping for 3-4 character usernames as they're more valuable
                if is_valuable:
                    ping_message = f"<@1017042087469912084> Valuable {username_length}-character username found!"
                    await channel.send(content=ping_message, embed=embed)
                else:
                    await channel.send(embed=embed)
            else:
                logger.debug(f"Username '{username}' not available. Reason: {message}")
                
            return True
        except Exception as e:
            logger.error(f"Error checking username: {str(e)}")
            return False
    
    async def check_usernames_task(self):
        """Background task to periodically check for available usernames."""
        logger.info(f"Starting username check task (interval: {self.check_interval}s)")
        channel = self.client.get_channel(self.channel_id)
        
        if not channel:
            logger.error(f"Could not find channel with ID {self.channel_id}")
            return
        
        logger.info(f"Will post available usernames to channel: {channel.name}")
        
        # Initialize semaphore for parallel requests
        self.semaphore = asyncio.Semaphore(self.parallel_checks)
        
        # Post initial status message with embed
        embed = discord.Embed(
            title="🤖 Roblox Username Bot Started",
            description="The bot is now searching for available Roblox usernames.",
            color=0x3498db  # Blue
        )
        
        embed.add_field(
            name="🔍 Search Strategy",
            value=f"• Checking up to {self.parallel_checks} usernames in parallel\n• Following 3-6 character username rules\n• 3-day cooldown for rechecking usernames",
            inline=False
        )
        
        embed.add_field(
            name="📣 Notifications",
            value="• Will ping for valuable 3 and 4 character usernames\n• Use `!roblox check <username>` to check specific names",
            inline=False
        )
        
        embed.set_footer(text=f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        await channel.send(embed=embed)
        
        while True:
            try:
                # Create a batch of username checking tasks
                tasks = []
                for _ in range(self.parallel_checks):
                    tasks.append(self.check_username(channel))
                
                # Run checks in parallel
                await asyncio.gather(*tasks)
                
                # Minimal delay between batches to avoid hitting rate limits
                jitter = random.uniform(0.05, 0.2)  # Very small jitter for max speed
                await asyncio.sleep(jitter)
                
            except Exception as e:
                logger.error(f"Error in username check task: {str(e)}")
                # Wait a bit and continue
                await asyncio.sleep(2)

    def run(self):
        """Run the Discord bot."""
        self.client.run(self.token)
