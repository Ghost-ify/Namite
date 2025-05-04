# How to Find Your Discord Channel ID

## Step-by-Step Instructions

### 1. Enable Developer Mode in Discord

First, you need to enable Developer Mode to access channel IDs:

1. Open Discord
2. Click on the gear icon (User Settings) in the bottom left
3. In the left sidebar, scroll down and click on "Advanced" under "App Settings"
4. Toggle ON "Developer Mode"
5. Close User Settings

### 2. Get Your Channel ID

Now you can copy the ID of the channel where you want the bot to post usernames:

1. Right-click on the desired text channel in your server
2. Select "Copy ID" from the context menu
3. The channel ID is now copied to your clipboard

### 3. Update Your Environment Variables

1. In your Replit project, find the `.env` file
2. Update the CHANNEL_ID value with your copied channel ID:
   ```
   CHANNEL_ID=1234567890123456789
   ```
   (Replace with your actual channel ID)
3. Save the changes

### 4. Important Tips

- Channel IDs are long numbers (usually 18-19 digits)
- Make sure you're copying a TEXT channel ID (not a voice channel or category)
- The bot must be a member of the server containing this channel
- The bot needs permission to view and send messages in this channel

### 5. Visual Guide

![Discord Channel ID Location](https://i.imgur.com/eJEMSHg.png)

*Note: The actual menu appearance may vary slightly depending on your Discord version and theme.*

If you've followed these steps correctly, the bot should be able to post messages to your selected channel once it's running.