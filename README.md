# Telegram File Bot

Bot Features:
- TXT split/merge
- XLSX → TXT / Message list
- TXT → XLSX
- Owner-only subscription management
- Trial system
- Real-time activity logging to owner
- Daily summary

## Setup

1. Clone the repo:
   git clone https://github.com/username/telegram_file_bot.git
   cd telegram_file_bot

2. Create virtualenv and install dependencies:
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt

3. Set environment variables in .env file:
   API_ID, API_HASH, BOT_TOKEN, ADMIN_ID

4. Run bot:
   python bot.py
