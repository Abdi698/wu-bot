# 🤫 Confession Bot - Complete Setup Guide

A fully-featured Telegram bot for anonymous confessions with admin approval system.

## 🚀 Quick Deployment

### Method 1: Deploy to Render (Recommended)

1. **Fork this repository** or upload all files to a new GitHub repo

2. **Go to [Render.com](https://render.com)** and:
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Set these details:
     - **Name**: `confession-bot`
     - **Environment**: `Python 3`
     - **Region**: Choose closest to you
     - **Branch**: `main` (or your branch)
     - **Root Directory**: (leave empty)
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `python confession_bot.py`

3. **Set Environment Variables** in Render dashboard:
   - `BOT_TOKEN` - Your bot token from BotFather
   - `ADMIN_CHAT_ID` - Your numeric Telegram ID
   - `CHANNEL_ID` - Your channel numeric ID  
   - `BOT_USERNAME` - Your bot username without @

4. **Click "Create Web Service"** - your bot will deploy automatically!

### Method 2: Run Locally

1. **Install requirements**:
   ```bash
   pip install -r requirements.txt
