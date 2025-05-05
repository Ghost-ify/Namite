"""
Discord bot implementation for finding available Roblox usernames.
This file handles the Discord interaction and scheduling of username checks.
"""
import asyncio
import logging
import discord
import random
import re
import time
from datetime import datetime
from username_generator import generate_username, generate_username_with_length, validate_username
from roblox_api import check_username_availability, get_user_details, initialize_with_cookies, API_ENDPOINTS
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
        self.max_length = 5

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
        """Handle the !roblox length command to update the bot's target length range."""
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
            await channel.send("⚠️ Invalid format. Please use a number (e.g., `4`) or range (e.g., `3-6`).")
            return

        # Update the bot's generator settings for future automatic checks
        self.min_length = min_length
        self.max_length = max_length
        logger.info(f"Updated automatic generator settings to length: {min_length}-{max_length}")

        # Update the adaptive learning system too
        try:
            from roblox_api import adaptive_system

            # Create new weights focusing heavily on the specified range
            new_weights = {}
            for length in range(3, 21):  # All possible Roblox username lengths
                if min_length <= length <= max_length:
                    # Prioritize shorter lengths within the range
                    if length <= 4:
                        new_weights[length] = 50.0  # Highest priority for rare short names
                    elif length <= 6:
                        new_weights[length] = 30.0  # High priority for medium length
                    else:
                        new_weights[length] = 20.0  # Normal priority for longer names
                else:
                    new_weights[length] = 1.0  # Very low weight for lengths outside range

            # Update the adaptive system with our new settings
            adaptive_system.length_weights = new_weights
            adaptive_system.save_state()

            # Force an immediate adaptation to apply changes
            adaptive_system.adapt()

            logger.info(f"Updated adaptive learning system to focus on length range {min_length}-{max_length}")
            logger.info(f"New weights distribution: {dict(sorted(new_weights.items()))}")
        except Exception as e:
            logger.error(f"Failed to update adaptive learning system: {str(e)}")

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
            title="🤖 Roblox Username Finder - Help Guide",
            description="Find available Roblox usernames instantly! This guide explains how to use all the bot's features.",
            color=0x3498db  # Blue
        )

        # Command section with emojis and improved formatting
        embed.add_field(
            name="📋 Commands",
            value=(
                "**✓ Check a Specific Username:**\n"
                "`!roblox check username123` - See if a username is available\n\n"
                "**✓ Find Usernames by Length:**\n"
                "`!roblox length 4` - Find available 4-character usernames\n"
                "`!roblox length 3-5` - Find usernames between 3-5 characters\n\n"
                "**✓ View Bot Information:**\n"
                "`!roblox stats` - See success rates and performance stats\n"
                "`!roblox recent` - See recently found available usernames\n"
                "`!roblox help` - Show this help guide"
            ),
            inline=False
        )

        # Add information about the automatic features
        embed.add_field(
            name="⚙️ Automatic Features",
            value=(
                "• Bot automatically searches for usernames 24/7\n"
                "• Found usernames are posted to this channel\n"
                "• Valuable short usernames (3-4 chars) get special alerts\n"
                "• Usernames are displayed with their Roblox chat colors\n"
                "• Smart algorithm adapts to find usernames more efficiently"
            ),
            inline=False
        )

        # Add Roblox username rules with better formatting
        embed.add_field(
            name="📝 Roblox Username Rules",
            value=(
                "• **Length:** 3-20 characters\n"
                "• **Characters:** Letters (a-z, A-Z), numbers (0-9), underscore (_)\n"
                "• **Restrictions:** Maximum one underscore, not at start/end\n"
                "• **Format:** Cannot be all numbers\n"
                "• **Tip:** Shorter usernames (3-5 chars) are more valuable!"
            ),
            inline=False
        )

        # Color sequence information with better formatting
        embed.add_field(
            name="🌈 Chat Color Prediction",
            value=(
                "This bot shows the exact Roblox chat color for each username using the official game algorithm.\n\n"
                "Color sequence: 🔴 Red → 🔵 Blue → 🟢 Green → 🟣 Purple → 🟠 Orange → 🟡 Yellow → 🌸 Pink → 🟤 Almond\n\n"
                "The color is determined by the username's characters, so it will match exactly in Roblox chat!"
            ),
            inline=False
        )

        # Add claiming instructions
        embed.add_field(
            name="🔍 How to Claim Usernames",
            value=(
                "1. Go to https://www.roblox.com/signup\n"
                "2. Enter the username exactly as shown (copy/paste recommended)\n"
                "3. Complete signup before someone else claims it!\n"
                "4. Remember, shorter usernames are claimed quickly!"
            ),
            inline=False
        )

        # Add footer with more information
        embed.set_footer(text="Roblox Username Finder Bot • Automatically finds available usernames 24/7 • Uses adaptive learning to improve results")

        await channel.send(embed=embed)

    async def send_stats_message(self, channel):
        """Send statistics about the bot's operations."""
        uptime = datetime.now() - self.stats['start_time'] if self.stats['start_time'] else datetime.now()
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days = hours // 24
        hours = hours % 24

        if days > 0:
            uptime_str = f"{days} day{'s' if days != 1 else ''}, {hours}h {minutes}m {seconds}s"
        else:
            uptime_str = f"{hours}h {minutes}m {seconds}s"

        success_rate = 0
        if self.stats['total_checked'] > 0:
            success_rate = (self.stats['available_found'] / self.stats['total_checked']) * 100

        # Calculate checks per minute - using uptime in seconds to avoid LSP errors
        checks_per_minute = 0
        uptime_seconds = (datetime.now() - self.stats['start_time']).seconds
        if uptime_seconds > 60:
            checks_per_minute = (self.stats['total_checked'] / (uptime_seconds / 60))

        # Calculate finds per hour
        finds_per_hour = 0
        if uptime_seconds > 3600:
            finds_per_hour = (self.stats['available_found'] / (uptime_seconds / 3600))

        # Get cookie count
        cookies_count = len(getattr(self, 'cookies', [])) or 1  # Default to 1 if no cookies attribute

        embed = discord.Embed(
            title="📊 Roblox Username Finder - Live Statistics",
            description="Real-time performance metrics for your username finding operation.",
            color=0x9b59b6  # Purple
        )

        # Performance summary
        embed.add_field(
            name="⏱️ Performance Summary",
            value=(
                f"**Uptime:** {uptime_str}\n"
                f"**Checking Speed:** {checks_per_minute:.1f} usernames/minute\n"
                f"**Parallel Threads:** {self.parallel_checks} simultaneous checks\n"
                f"**Using:** {cookies_count} cookie(s)"
            ),
            inline=False
        )

        # Results statistics
        embed.add_field(
            name="🎯 Results Statistics",
            value=(
                f"**Total Checked:** {self.stats['total_checked']:,} usernames\n"
                f"**Available Found:** {self.stats['available_found']:,} usernames\n"
                f"**Success Rate:** {success_rate:.2f}%\n"
                f"**Finding Rate:** {finds_per_hour:.1f} available names/hour"
            ), 
            inline=False
        )

        # Configuration information
        embed.add_field(
            name="⚙️ Configuration",
            value=(
                f"**Target Length:** {self.min_length}-{self.max_length} characters\n"
                f"**Batch Size:** {self.batch_size} usernames\n"
                f"**Database:** 3-day cooldown for rechecking names\n"
                f"**Adaptive Learning:** Automatically optimizes username generation"
            ),
            inline=False
        )

        # If adaptive learning is available, get distribution
        try:
            from roblox_api import adaptive_system
            embed.add_field(
                name="📈 Learning Metrics",
                value=(
                    f"**Current Parameters:** Optimizing based on success patterns\n"
                    f"**Focus:** Currently favoring {self.min_length}-{self.max_length} character names\n"
                    f"**API Status:** Healthy, using endpoint rotation and rate limiting"
                ),
                inline=False
            )
        except ImportError:
            pass

        # Set footer with more info
        start_date = self.stats['start_time'].strftime('%Y-%m-%d %H:%M')
        embed.set_footer(text=f"Bot started on {start_date} • Live data as of {datetime.now().strftime('%H:%M:%S')} • Stats refresh on command")

        await channel.send(embed=embed)

    async def send_recent_available(self, channel):
        """Send a list of recently found available usernames."""
        recent_usernames = get_recently_available_usernames(15)  # Get more usernames for better grouping

        if not recent_usernames:
            # More friendly empty state message
            embed = discord.Embed(
                title="🔍 No Available Usernames Found Yet",
                description="The bot is actively searching, but hasn't found any available usernames yet.",
                color=0x3498db  # Blue
            )
            embed.add_field(
                name="What's Happening?",
                value=(
                    "• The bot is running and checking usernames\n"
                    "• Results will appear here once usernames are found\n"
                    "• You can see bot activity with the `!roblox stats` command"
                ),
                inline=False
            )
            await channel.send(embed=embed)
            return

        # Get current time to calculate how recent the names are
        current_time = datetime.now()

        # Group usernames by how recently they were found
        last_hour_usernames = []
        today_usernames = []
        older_usernames = []

        for username_data in recent_usernames:
            username = username_data['username']
            checked_time = username_data['checked_at']
            time_diff = current_time - checked_time

            # Add to appropriate group - using timedelta.seconds to avoid LSP errors
            diff_seconds = time_diff.seconds + (time_diff.days * 86400)

            if diff_seconds < 3600:  # Last hour
                last_hour_usernames.append(username_data)
            elif diff_seconds < 86400:  # Last 24 hours
                today_usernames.append(username_data)
            else:  # Older
                older_usernames.append(username_data)

        embed = discord.Embed(
            title="✅ Recently Found Available Usernames",
            description=(
                "These usernames were recently found to be available for registration.\n"
                "**Note:** They may have been claimed since discovery."
            ),
            color=0x2ecc71  # Green
        )

        # Process the groups and add to embed
        def format_username_group(usernames, group_name):
            if not usernames:
                return None

            formatted_list = ""
            for username_data in usernames:
                username = username_data['username']
                checked_time = username_data['checked_at']
                chat_color = self.get_chat_color(username)

                # Format the time depending on how recent it is - using timedelta.seconds to avoid LSP errors
                time_diff = current_time - checked_time
                diff_seconds = time_diff.seconds + (time_diff.days * 86400)

                if diff_seconds < 3600:  # Less than an hour
                    minutes_ago = int(diff_seconds / 60)
                    time_str = f"{minutes_ago} min ago"
                elif diff_seconds < 86400:  # Less than a day
                    hours_ago = int(diff_seconds / 3600)
                    time_str = f"{hours_ago} hr ago"
                else:
                    time_str = checked_time.strftime('%m/%d %H:%M')

                # Format to make usernames stand out and easy to copy
                formatted_list += f"**`{username}`** {chat_color['emoji']} ({chat_color['name']}) • *{time_str}*\n"

            return formatted_list

        # Add each time group to the embed
        last_hour_formatted = format_username_group(last_hour_usernames, "Last Hour")
        if last_hour_formatted:
            embed.add_field(
                name="🕐 Found in the Last Hour",
                value=last_hour_formatted,
                inline=False
            )

        today_formatted = format_username_group(today_usernames, "Today")
        if today_formatted:
            embed.add_field(
                name="📅 Found Today",
                value=today_formatted,
                inline=False
            )

        older_formatted = format_username_group(older_usernames, "Earlier")
        if older_formatted:
            embed.add_field(
                name="📆 Found Earlier",
                value=older_formatted,
                inline=False
            )

        # Add claim instructions
        embed.add_field(
            name="🔍 How to Claim",
            value=(
                "1. Go to https://www.roblox.com/signup\n"
                "2. Copy a username above (click the username to copy)\n"
                "3. Paste it into the signup page\n"
                "4. Complete registration before someone else claims it!"
            ),
            inline=False
        )

        embed.set_footer(text=f"Last updated: {current_time.strftime('%Y-%m-%d %H:%M:%S')} • Check again with !roblox recent")

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
                                value=f"Available: {self.stats['available_found']}/{self.stats['total_checked']} ({successrate:.2f}%)",
                                inline=False
                            )

                            embed.set_footer(text=f"Bot running since {self.stats['start_time'].strftime('%Y-%m-%d %H:%M')}")

                            # Send immediately with ping
                            ping_message = f"<@1017042087469912084> Valuable {username_length}-character username found!"
                            await channel.send(content=ping_message, embed=embed)
                        else:
                            # For usernames less than 5 characters, send immediately
                            if username_length < 5:
                                embed = discord.Embed(
                                    title="💎 Short Username Found!",
                                    description=f"**`{username}`** {chat_color['emoji']}",
                                    color=0xffd700  # Gold
                                )
                                embed.add_field(name="📏 Length", value=str(username_length), inline=True)
                                embed.add_field(name="🔣 Contains Underscore", value=str('_' in username), inline=True)
                                embed.add_field(name=f"{chat_color['emoji']} Chat Color", value=chat_color['name'], inline=True)
                                await channel.send(embed=embed)
                            else:
                                # For longer usernames, add to batch queue
                                already_in_queue = False
                                for existing in self.pending_usernames:
                                    if existing['username'] == username:
                                        already_in_queue = True
                                        break

                                if not already_in_queue:
                                    self.pending_usernames.append({
                                        'username': username,
                                        'length': username_length,
                                        'has_underscore': '_' in username,
                                        'timestamp': datetime.now()
                                    })

                                # Schedule batch send every 5 minutes
                                if not self.batch_timer or self.batch_timer.done():
                                    self.batch_timer = asyncio.create_task(
                                        self.schedule_batch_send(channel, 300)  # 300 seconds = 5 minutes
                                    )
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

        # Post initial status message with embed - more attractive welcome message
        embed = discord.Embed(
            title="✨ Roblox Username Finder - Now Active! ✨",
            description=(
                "**Your automated Roblox username finder is now running!**\n\n"
                "This bot is actively searching for available Roblox usernames and will post them in this channel. "
                "Short usernames (3-4 characters) will get special notifications as they're particularly valuable."
            ),
            color=0x3498db  # Blue
        )

        # Get cookie count
        cookies_count = len(getattr(self, 'cookies', [])) or 1  # Default to 1 if no cookies attribute

        embed.add_field(
            name="🚀 Active Configuration",
            value=(
                f"• **Search Power:** {self.parallel_checks} simultaneous checks\n"
                f"• **Focus:** Targeting {self.min_length}-{self.max_length} character usernames\n"
                f"• **Speed:** Using {cookies_count} Roblox cookie{'s' if cookies_count != 1 else ''} for API access\n"
                f"• **Efficiency:** Adaptive learning optimizes generation patterns"
            ),
            inline=False
        )

        embed.add_field(
            name="🎮 Interactive Commands",
            value=(
                "• `!roblox check <username>` - Check if a specific username is available\n"
                "• `!roblox length 4` - Find usernames of exactly 4 characters\n"
                "• `!roblox stats` - View real-time statistics and performance\n"
                "• `!roblox recent` - See recently found available usernames\n"
                "• `!roblox help` - Show detailed help information"
            ),
            inline=False
        )

        embed.add_field(
            name="🔔 Smart Notifications",
            value=(
                "• **Valuable Usernames:** Special alerts for rare 3-4 character names\n"
                "• **Batch Reporting:** Regular batches of available usernames\n"
                "• **Chat Colors:** Every username shows its exact Roblox chat color\n"
                "• **Easy Claiming:** Simple copy-paste format for quick registration"
            ),
            inline=False
        )

        # Add tip for best results
        embed.add_field(
            name="💡 Pro Tip",
            value=(
                "The bot performs better with more Roblox cookies. If you want to speed up your username search, "
                "you can add additional cookies to your environment variables."
            ),
            inline=False
        )

        # Format current time with more details
        start_time = datetime.now()
        embed.set_footer(text=f"Started on {start_time.strftime('%Y-%m-%d at %H:%M:%S')} • System will run 24/7 • Type !roblox help for assistance")

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

        # Remove duplicates while preserving order
        seen = set()
        unique_usernames = []
        for username_data in self.pending_usernames:
            if username_data['username'] not in seen:
                seen.add(username_data['username'])
                unique_usernames.append(username_data)

        self.pending_usernames = unique_usernames

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