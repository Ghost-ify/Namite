# Roblox Username Discord Bot

This bot automatically finds available Roblox usernames and posts them to your Discord channel. It also allows users to check specific usernames on demand.

## Features

- **Automatic Username Generation**: Generates random Roblox-compliant usernames (3-6 characters)
- **Availability Checking**: Checks usernames against the Roblox API and reports available ones
- **Database Tracking**: Remembers checked usernames with a 3-day cooldown to avoid duplicates
- **User Pinging**: Pings a designated user for 3-4 character valuable usernames
- **Command System**: Allows members to check specific usernames with the `!roblox check` command
- **Rich Embeds**: Uses Discord embeds with emoji and formatting for better presentation
- **History & Stats**: Tracks statistics and maintains a list of recently found available usernames

## Setup Instructions

1. Create a Discord bot on the [Discord Developer Portal](https://discord.com/developers/applications)
2. Configure your bot token in the `.env` file
3. Set the CHANNEL_ID in the `.env` file to your desired Discord channel
4. Run the bot using `python main.py`

For detailed setup and troubleshooting, see [BOT_SETUP_GUIDE.md](BOT_SETUP_GUIDE.md).

## Commands

- `!roblox check <username>` - Check if a specific username is available
- `!roblox stats` - Show bot statistics
- `!roblox recent` - Show recently found available usernames
- `!roblox help` - Show help information

## Roblox Username Rules

- Length: 3-6 characters
- Allowed characters: letters (a-z, A-Z), numbers (0-9), and underscore (_)
- Cannot be fully numeric
- Cannot start or end with an underscore
- Maximum one underscore

## Technical Information

The bot uses a PostgreSQL database to track username checks and implements a 3-day cooldown before rechecking the same username.

For better performance, it:
- Runs up to 3 concurrent username checks in parallel
- Uses connection pooling for database operations
- Implements an in-memory cache for very recent checks

## Notes for Channel Administrators

To receive pings for valuable 3-4 character usernames, update the user ID in `bot.py` (line 353/200 - look for `<@1017042087469912084>`).

For more details on setting up the correct channel ID, see [CHANNEL_ID_INSTRUCTIONS.md](CHANNEL_ID_INSTRUCTIONS.md).