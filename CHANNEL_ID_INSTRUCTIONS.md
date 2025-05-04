# How to Get Your Discord Channel ID

To make the bot work properly, you need to provide your Discord Channel ID in the `.env` file. Here's how to get it:

## Step 1: Enable Developer Mode in Discord

1. Open Discord
2. Click on the gear icon (User Settings) in the bottom left
3. Select "Advanced" from the sidebar
4. Toggle ON "Developer Mode"

## Step 2: Get Your Channel ID

1. Right-click on the channel where you want the bot to post available usernames
2. Select "Copy ID" from the context menu
3. The channel ID is now in your clipboard

## Step 3: Update Your .env File

1. Open the `.env` file in this project
2. Replace the placeholder in the `CHANNEL_ID=` line with your actual channel ID
3. Save the file
4. Restart the bot

## Example

Your `.env` file should look something like this:

```
DISCORD_TOKEN=your_discord_bot_token
CHANNEL_ID=1234567890123456789
CHECK_INTERVAL=60
```

Make sure there are no spaces or quotes around the values.