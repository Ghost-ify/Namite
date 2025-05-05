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
from username_generator import generate_username, generate_username_with_length, validate_username
from roblox_api import check_username_availability, get_user_details, initialize_with_cookies
from database import get_username_status, get_recently_available_usernames

logger = logging.getLogger('roblox_username_bot')

class RobloxUsernameBot:
    def __init__(self, token, channel_id, check_interval=10, cookies=None):
        """
        Initialize the Roblox Username Discord Bot.
        
        Args:
            token (str): Discord bot token
            channel_id (int): Discord channel ID to post available usernames
            check_interval (int): Time between username checks in seconds
            cookies (list, optional): List of Roblox cookies to use for API requests
        """
        self.token = token
        self.channel_id = channel_id
        self.check_interval = check_interval
        self.cookies = cookies or []
        
        # Initialize the Roblox API with cookies if they exist
        if self.cookies:
            logger.info(f"Initializing Roblox API with {len(self.cookies)} cookies from bot")
            initialize_with_cookies(self.cookies)
        
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
        # Import adaptive learning system
        from roblox_api import adaptive_system
        
        # Get the parallel checks from adaptive learning system (or use default 10)
        params = adaptive_system.get_current_params()
        self.parallel_checks = params.get("parallel_checks", 10)
        
        # Semaphore to limit concurrent API requests
        self.semaphore = None
        
        # For batching available usernames
        self.batch_size = 5
        self.pending_usernames = []
        self.batch_timer = None
        
        # Username generator settings (min and max length)
        self.min_length = 3
        self.max_length = 6
        
        # Roblox chat color algorithm
        self.chat_colors = [
            {"name": "Red", "emoji": "🔴"},
            {"name": "Blue", "emoji": "🔵"},
            {"name": "Green", "emoji": "🟢"},
            {"name": "Purple", "emoji": "🟣"},
            {"name": "Orange", "emoji": "🟠"},
            {"name": "Yellow", "emoji": "🟡"},
            {"name": "Pink", "emoji": "🌸"},
            {"name": "Almond", "emoji": "🟤"}
        ]

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
            
        elif command == "length":
            # Check usernames of specific length
            if len(command_parts) < 2:
                await message.channel.send("⚠️ Please provide a length or length range (e.g., `!roblox length 5` or `!roblox length 5-8`)")
                return
                
            length_param = command_parts[1]
            await self.handle_length_command(message.channel, length_param)
            
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
        checking_message = await channel.send(f"🔍 Checking username: `{username}`...")
        
        try:
            # Get the chat color for this username
            chat_color = self.get_chat_color(username)
            
            # Check the availability
            is_available, status_code, message = await check_username_availability(username)
            
            if is_available:
                # Username is available - show details
                username_length = len(username)
                is_valuable = username_length <= 4
                
                # Create an embed for available username
                embed = discord.Embed(
                    title="✅ Username is Available!",
                    description=f"**{username}** {chat_color['emoji']}",
                    color=0x00ff00  # Green
                )
                
                embed.add_field(name="📏 Length", value=str(username_length), inline=True)
                embed.add_field(name="🔣 Contains Underscore", value=str('_' in username), inline=True)
                embed.add_field(name=f"{chat_color['emoji']} Chat Color", value=chat_color['name'], inline=True)
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
                # Username is not available - try to get user info
                user_details = await get_user_details(username)
                
                if user_details:
                    # User exists - create rich embed with detailed info
                    embed = discord.Embed(
                        title="👤 Existing Roblox User",
                        description=f"**{user_details['username']}** {chat_color['emoji']}",
                        color=0x3498db,  # Blue
                        url=user_details['profile_url']
                    )
                    
                    # Add user info
                    embed.add_field(name="📋 Display Name", value=user_details['display_name'], inline=True)
                    embed.add_field(name="🆔 User ID", value=str(user_details['user_id']), inline=True)
                    embed.add_field(name=f"{chat_color['emoji']} Chat Color", value=chat_color['name'], inline=True)
                    embed.add_field(name="⏱️ Account Age", value=user_details['account_age'], inline=True)
                    
                    # Set user avatar as thumbnail
                    if user_details['avatar_url']:
                        embed.set_thumbnail(url=user_details['avatar_url'])
                    
                    embed.set_footer(text="Account information retrieved from Roblox API")
                    
                    await checking_message.edit(content=None, embed=embed)
                else:
                    # Username is taken but we couldn't get details - create simple embed
                    embed = discord.Embed(
                        title="❌ Username is Unavailable",
                        description=f"**{username}** {chat_color['emoji']}",
                        color=0xff0000  # Red
                    )
                    embed.add_field(name="Reason", value=message, inline=False)
                    embed.add_field(name=f"{chat_color['emoji']} Chat Color", value=chat_color['name'], inline=True)
                    embed.set_footer(text="This username cannot be registered on Roblox")
                    
                    await checking_message.edit(content=None, embed=embed)
        except Exception as e:
            logger.error(f"Error checking username {username}: {str(e)}")
            await checking_message.edit(content=f"⚠️ Error checking username: `{username}`. Please try again later.")
    
    async def handle_length_command(self, channel, length_param):
        """Handle the !roblox length command to check usernames of specific length."""
        # Check if param is a single length or a range
        try:
            if '-' in length_param:
                # A range of lengths
                min_length, max_length = map(int, length_param.split('-'))
                
                # Validate range
                if min_length < 3 or max_length > 20 or min_length > max_length:
                    await channel.send("⚠️ Invalid length range. Min must be ≥3, max must be ≤20, and min must be ≤ max.")
                    return
            else:
                # A single length
                length = int(length_param)
                min_length = max_length = length
                
                # Validate length
                if length < 3 or length > 20:
                    await channel.send("⚠️ Invalid length. Usernames must be between 3 and 20 characters.")
                    return
        except ValueError:
            await channel.send("⚠️ Invalid format. Please specify a number (e.g., `5`) or a range (e.g., `5-8`).")
            return
        
        # Send initial message
        message = await channel.send(f"🔍 Generating and checking usernames with length {min_length}{' to '+str(max_length) if min_length != max_length else ''}...")
        
        # Generate and check 5 usernames with the specified length
        results = []
        errors = 0
        
        for _ in range(5):  # Check 5 usernames
            username = generate_username_with_length(min_length, max_length)
            
            try:
                # Send a typing indicator to show progress
                await channel.trigger_typing()
                
                # Check availability
                is_available, status_code, response_message = await check_username_availability(username)
                
                # Add to results
                results.append({
                    'username': username,
                    'is_available': is_available,
                    'message': response_message
                })
                
                if is_available:
                    self.stats['available_found'] += 1
                
                # Update total checked
                self.stats['total_checked'] += 1
                
            except Exception as e:
                logger.error(f"Error checking username {username}: {str(e)}")
                errors += 1
        
        # Update the bot's generator settings for future automatic checks
        self.min_length = min_length
        self.max_length = max_length
        logger.info(f"Updated automatic generator settings to length: {min_length}-{max_length}")
        
        # Create an embed with the results
        embed = discord.Embed(
            title=f"Username Search Results ({min_length}{'-'+str(max_length) if min_length != max_length else ''} chars)",
            description=f"Checked {len(results)} usernames of specified length\n**Auto-generator now set to this length range**",
            color=0x3498db  # Blue
        )
        
        # Add available usernames
        available = [r for r in results if r['is_available']]
        if available:
            available_text = ""
            for r in available:
                username = r['username']
                chat_color = self.get_chat_color(username)
                available_text += f"• **{username}** {chat_color['emoji']} ({chat_color['name']})\n"
                
            embed.add_field(
                name=f"✅ Available ({len(available)})",
                value=available_text,
                inline=False
            )
        else:
            embed.add_field(
                name="❌ No Available Usernames Found",
                value="None of the generated usernames were available. Try again or try a different length range.",
                inline=False
            )
        
        # Add unavailable usernames
        unavailable = [r for r in results if not r['is_available']]
        if unavailable:
            unavailable_text = '\n'.join([f"• {r['username']}" for r in unavailable[:3]])  # Show only first 3
            if len(unavailable) > 3:
                unavailable_text += f"\n• ...and {len(unavailable) - 3} more"
            embed.add_field(
                name=f"❌ Unavailable ({len(unavailable)})",
                value=unavailable_text,
                inline=False
            )
        
        # Add errors if any
        if errors > 0:
            embed.add_field(
                name="⚠️ Errors",
                value=f"{errors} username(s) could not be checked due to API errors.",
                inline=False
            )
        
        # Add how to claim information
        embed.add_field(
            name="🔍 How to Claim",
            value="Go to https://www.roblox.com/signup and enter an available username before someone else claims it!",
            inline=False
        )
        
        # Edit the original message with the results
        await message.edit(content=None, embed=embed)
    
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
                "🔹 `!roblox length <number>` - Generate and check usernames of a specific length\n"
                "🔹 `!roblox length <min>-<max>` - Check usernames in a length range\n"
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
        
        # Color sequence information
        embed.add_field(
            name="🌈 Chat Color Prediction",
            value=(
                "Usernames display with their exact Roblox chat color using the official game algorithm:\n"
                "🔴 Red → 🔵 Blue → 🟢 Green → 🟣 Purple → 🟠 Orange → 🟡 Yellow → 🌸 Pink → 🟤 Almond"
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
            chat_color = self.get_chat_color(username)
            embed.add_field(
                name=f"{i+1}. {username} {chat_color['emoji']}",
                value=f"Color: {chat_color['name']} | Found at: {timestamp}",
                inline=False
            )
        
        embed.set_footer(text="These usernames may have been claimed since they were found")
        
        await channel.send(embed=embed)

    async def check_username(self, channel):
        """Check a single username and report if available."""
        try:
            # Generate a username using custom length settings
            username = generate_username_with_length(self.min_length, self.max_length)
            
            logger.info(f"Checking availability of username: {username}")
            
            # Check if it's available
            try:
                is_available, status_code, message = await check_username_availability(username)
                
                # Only update stats for successful API calls (not errors)
                if status_code != -1:
                    # Update stats (use atomic operation)
                    self.stats['total_checked'] += 1
                    
                    if is_available:
                        self.stats['available_found'] += 1
                        logger.info(f"Available username found: {username}")
                        
                        # Username properties
                        username_length = len(username)
                        is_valuable = username_length <= 4
                        chat_color = self.get_chat_color(username)
                        
                        # If it's a valuable username (3-4 chars), send immediately with ping
                        if is_valuable:
                            # Create embed for valuable username
                            embed = discord.Embed(
                                title="💎 Rare Short Username Found! 💎",
                                description=f"**`{username}`** {chat_color['emoji']}",
                                color=0xffd700  # Gold color
                            )
                            
                            # Add username in a clear, copyable format
                            embed.add_field(name="📋 Copy Username", value=f"`{username}`", inline=False)
                            
                            # Add details in a more organized way
                            details_value = (
                                f"📏 **Length:** {username_length} characters\n"
                                f"🔣 **Underscore:** {'Yes' if '_' in username else 'No'}\n"
                                f"{chat_color['emoji']} **Chat Color:** {chat_color['name']}\n"
                                f"💎 **Rarity:** High (3-4 character usernames are rare)"
                            )
                            embed.add_field(name="📊 Details", value=details_value, inline=False)
                            
                            # Add timestamp and claim information with clearer instructions
                            claim_instructions = (
                                "1️⃣ Go to https://www.roblox.com/signup\n"
                                "2️⃣ Enter this username exactly as shown\n"
                                "3️⃣ Complete signup before someone else claims it!\n"
                                "⚠️ **Act quickly!** Rare usernames are claimed fast!"
                            )
                            embed.add_field(
                                name="🔍 How to Claim This Username",
                                value=claim_instructions,
                                inline=False
                            )
                            
                            # Add statistics
                            success_rate = (self.stats['available_found'] / self.stats['total_checked']) * 100 if self.stats['total_checked'] > 0 else 0
                            embed.add_field(
                                name="📊 Statistics",
                                value=f"Available: {self.stats['available_found']}/{self.stats['total_checked']} ({success_rate:.2f}%)",
                                inline=False
                            )
                            
                            embed.set_footer(text=f"Bot running since {self.stats['start_time'].strftime('%Y-%m-%d %H:%M')}")
                            
                            # Send immediately with ping
                            ping_message = f"<@1017042087469912084> Valuable {username_length}-character username found!"
                            await channel.send(content=ping_message, embed=embed)
                        else:
                            # For regular usernames, add to the batch queue
                            self.pending_usernames.append({
                                'username': username,
                                'length': username_length,
                                'has_underscore': '_' in username,
                                'timestamp': datetime.now()
                            })
                            
                            # If we've reached our batch size or this is the first username, schedule sending
                            if len(self.pending_usernames) >= self.batch_size:
                                # Send immediately
                                await self.send_batch_usernames(channel)
                            elif len(self.pending_usernames) == 1:
                                # Schedule a send in 2 minutes if more usernames don't fill the batch first
                                if self.batch_timer is not None:
                                    self.batch_timer.cancel()
                                
                                self.batch_timer = asyncio.create_task(self.schedule_batch_send(channel, 120))
                    else:
                        logger.debug(f"Username '{username}' not available. Reason: {message}")
                else:
                    logger.warning(f"API error when checking username '{username}': {message}")
            except Exception as api_error:
                logger.error(f"Error in API call for username {username}: {str(api_error)}")
                
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
            value=f"• Checking up to {self.parallel_checks} usernames in parallel\n• Following 3-20 character username rules\n• 3-day cooldown for rechecking usernames",
            inline=False
        )
        
        embed.add_field(
            name="📣 Notifications",
            value="• Will ping for valuable 3 and 4 character usernames\n• Use `!roblox check <username>` to check specific names",
            inline=False
        )
        
        embed.add_field(
            name="🌈 Chat Color Prediction",
            value="• Displays exact Roblox chat colors using the official game algorithm\n• Colors cycle: 🔴 Red → 🔵 Blue → 🟢 Green → 🟣 Purple → 🟠 Orange → 🟡 Yellow → 🌸 Pink → 🟤 Almond",
            inline=False
        )
        
        embed.set_footer(text=f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        await channel.send(embed=embed)
        
        while True:
            try:
                # Update parameters from adaptive learning system
                try:
                    from roblox_api import adaptive_system
                    params = adaptive_system.get_current_params()
                    adaptive_parallel = params.get("parallel_checks")
                    if adaptive_parallel and adaptive_parallel != self.parallel_checks:
                        logger.info(f"Updating parallel checks from {self.parallel_checks} to {adaptive_parallel} based on adaptive learning")
                        self.parallel_checks = adaptive_parallel
                        # Update semaphore to match new parallel count
                        self.semaphore = asyncio.Semaphore(self.parallel_checks)
                except Exception as e:
                    logger.warning(f"Failed to update parameters from adaptive learning: {e}")
                
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

    async def schedule_batch_send(self, channel, delay_seconds):
        """Schedule a batch send after a delay if batch size is not reached."""
        await asyncio.sleep(delay_seconds)
        if self.pending_usernames and len(self.pending_usernames) > 0:
            await self.send_batch_usernames(channel)

    async def send_batch_usernames(self, channel):
        """Send a batch of available usernames in a single message."""
        if not self.pending_usernames:
            return
            
        # Create a batch embed
        current_time = datetime.now()
        usernames_count = len(self.pending_usernames)
        
        # Create the embed with a more attractive title and description
        embed = discord.Embed(
            title=f"✨ {usernames_count} Available Roblox Usernames! ✨",
            description=(
                "**Here are the latest available usernames our bot found:**\n"
                "• Usernames are sorted by length (shortest first)\n"
                "• Code format makes them easy to copy\n"
                "• Each username shows its Roblox chat color"
            ),
            color=0x00ff00  # Green
        )
        
        # Sort usernames by length (shorter first as they're more valuable)
        sorted_usernames = sorted(self.pending_usernames, key=lambda x: x['length'])
        
        # Group usernames by length for better organization
        usernames_by_length = {}
        for username_data in sorted_usernames:
            length = username_data['length']
            if length not in usernames_by_length:
                usernames_by_length[length] = []
            usernames_by_length[length].append(username_data)
        
        # Display usernames grouped by length
        for length in sorted(usernames_by_length.keys()):
            username_list = ""
            usernames = usernames_by_length[length]
            
            for username_data in usernames:
                username = username_data['username']
                has_underscore = username_data['has_underscore']
                
                # Add formatting with chat color - optimized for easy copying
                chat_color = self.get_chat_color(username)
                special_marker = "🔹" if has_underscore else "🔸"
                # Make username stand out with code block for easy copying
                username_list += f"{special_marker} **`{username}`** {chat_color['emoji']} ({chat_color['name']})\n"
            
            # Add this length group as a field
            rarity = "⭐⭐⭐ RARE!" if length <= 4 else ("⭐⭐ Uncommon" if length <= 6 else "⭐ Common")
            embed.add_field(
                name=f"{length}-Character Usernames ({rarity})",
                value=username_list or "None found in this category",
                inline=False
            )
        
        # Add claim instructions with a clearer format
        claim_instructions = (
            "1️⃣ Go to https://www.roblox.com/signup\n"
            "2️⃣ Copy one of the usernames above\n"
            "3️⃣ Paste it into the username field\n"
            "4️⃣ Complete registration before someone else claims it!\n\n"
            "⚠️ **Remember:** Shorter usernames are claimed faster!"
        )
        embed.add_field(
            name="🔍 How to Claim a Username",
            value=claim_instructions,
            inline=False
        )
        
        # Add statistics with more detail
        cookies_count = len(getattr(self, 'cookies', [])) or 1  # Default to 1 if no cookies attribute
        success_rate = (self.stats['available_found'] / self.stats['total_checked']) * 100 if self.stats['total_checked'] > 0 else 0
        stats_value = (
            f"✅ **Found:** {self.stats['available_found']} available usernames\n"
            f"🔍 **Checked:** {self.stats['total_checked']} total usernames\n"
            f"📊 **Success Rate:** {success_rate:.2f}%\n"
            f"⚙️ **Using:** {cookies_count} cookie(s) for API requests"
        )
        embed.add_field(
            name="📈 Bot Statistics",
            value=stats_value,
            inline=False
        )
        
        # Set footer with timestamp and 3-day cooldown note
        embed.set_footer(text=f"Bot running since {self.stats['start_time'].strftime('%Y-%m-%d %H:%M')} • Batch generated at {current_time.strftime('%Y-%m-%d %H:%M:%S')} • Usernames won't be rechecked for 3 days")
        
        # Send the batch message
        logger.info(f"Sending batch of {usernames_count} available usernames")
        await channel.send(embed=embed)
        
        # Clear the pending usernames list
        self.pending_usernames = []
        
        # Cancel any scheduled batch send
        if self.batch_timer is not None:
            self.batch_timer.cancel()
            self.batch_timer = None
    
    def get_chat_color(self, username):
        """
        Determine the Roblox chat color for a username.
        Colors cycle in this order: Red, Blue, Green, Purple, Orange, Yellow, Pink, Almond
        
        This implementation is based on the official Roblox source code from:
        https://github.com/Roblox/Core-Scripts/blob/master/CoreScriptsRoot/Modules/Chat.lua
        
        Args:
            username (str): The Roblox username to analyze
            
        Returns:
            dict: Dictionary with color name and emoji
        """
        # Direct port from Roblox's official Lua code
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
        
        # Compute name color (direct port from official Roblox code)
        color_offset = 0
        name_value = get_name_value(username)
        color_index = ((name_value + color_offset) % len(self.chat_colors))
        
        return self.chat_colors[color_index]
    
    def run(self):
        """Run the Discord bot."""
        self.client.run(self.token)
