# Discord Bot Setup Guide

This guide will help you set up your Roblox Username Discord Bot correctly.

## Step 1: Configure Bot Permissions

Your bot needs the right permissions to access your Discord server and channels:

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your bot application
3. Navigate to "Bot" in the left sidebar
4. Under "Privileged Gateway Intents", enable:
   - SERVER MEMBERS INTENT
   - MESSAGE CONTENT INTENT
5. Click "Save Changes"

## Step 2: Invite the Bot to Your Server

1. In the Discord Developer Portal, select your application
2. Navigate to "OAuth2" → "URL Generator" in the left sidebar
3. Under "SCOPES", select:
   - `bot`
4. Under "BOT PERMISSIONS", select:
   - View Channels
   - Send Messages
   - Embed Links
   - Read Message History
5. Copy the generated URL at the bottom of the page
6. Open the URL in your browser
7. Select the server where you want to add the bot
8. Complete the authorization process

## Step 3: Configure the Channel ID

The bot needs the correct channel ID to post available usernames:

1. Open Discord
2. Go to Settings → Advanced
3. Enable "Developer Mode"
4. Right-click on the channel where you want the bot to post usernames
5. Select "Copy ID"
6. Update the `.env` file in your Replit project:
   ```
   CHANNEL_ID=your_channel_id_here
   ```

## Step 4: Verify Bot Access

Make sure the bot:
1. Is present in your server (appears in the member list)
2. Has permission to view and send messages in the specified channel
3. Is online (green dot next to its name)

## Troubleshooting

**Bot not posting messages?**
- Check if you used the correct Channel ID
- Ensure the bot has permission to view and send messages in that channel
- Verify the bot is online in your server

**Bot reports no guilds?**
- Invite the bot to your server using the OAuth2 URL from Step 2

**Channel ID error?**
- Make sure you're using the ID of a text channel, not a voice channel or category
- Channel IDs are numeric only (e.g., `1234567890123456789`)

If you continue to have issues, check the logs for specific error messages.