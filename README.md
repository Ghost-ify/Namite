# Roblox Username Discord Bot

A Discord bot that automatically finds available Roblox usernames and posts them to your Discord channel.

## Features

- **Automatic Username Generation**: Generates random Roblox-style usernames following platform rules
- **Availability Checking**: Uses Roblox's API to check if usernames are available
- **Discord Integration**: Posts available usernames to your Discord channel
- **Continuous Running**: Designed to run indefinitely on Replit
- **Error Handling**: Handles network issues and API rate limits

## Setup Instructions

### 1. Discord Bot Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a "New Application"
3. Navigate to the "Bot" tab and click "Add Bot"
4. Under the Token section, click "Copy" or "Reset Token" to get your bot token
5. Invite the bot to your server by going to OAuth2 > URL Generator:
   - Select "bot" scope
   - Select the "Send Messages" and "Embed Links" permissions
   - Copy and open the generated URL

### 2. Configuration

1. Create an `.env` file with the following fields:
```
DISCORD_TOKEN=your_bot_token_here
CHANNEL_ID=your_channel_id_here
CHECK_INTERVAL=60
```

2. To get your Channel ID:
   - Enable Developer Mode in Discord (Settings > Advanced)
   - Right-click on your desired channel and select "Copy ID"

### 3. Running the Bot

1. Make sure all dependencies are installed:
   - discord.py
   - python-dotenv
   - aiohttp
2. Run the bot with: `python main.py`

## Customization

- **Check Interval**: Adjust the `CHECK_INTERVAL` in the `.env` file (minimum 10 seconds to avoid rate limits)
- **Username Generation**: Modify `username_generator.py` to change username patterns
- **Embed Appearance**: Edit the embed creation in `bot.py` to customize the appearance of Discord messages

## File Structure

- `main.py` - Entry point that sets up and runs the bot
- `bot.py` - Discord bot implementation and main logic
- `username_generator.py` - Username generation following Roblox rules
- `roblox_api.py` - API integration with Roblox's username validation endpoint

## Troubleshooting

- **Bot Not Starting**: Ensure your Discord token is valid and properly formatted
- **Cannot Find Channel**: Verify the channel ID is correct and the bot has access to that channel
- **API Rate Limiting**: If you see rate limit errors, increase the check interval

---

Created for educational purposes only. This application is not affiliated with Roblox or Discord.