# Telegram Store Bot

MongoDB-backed starter bot with custom deposits, payment screenshot review, wallet, products, orders, refunds, and 5-minute support sessions.

## Setup
1. Copy `.env.example` to `.env`.
2. Set BOT_TOKEN, MONGO_URI, MONGO_DB, ADMIN_IDS, and UPI_ID.
3. `pip install -r requirements.txt`
4. `python -m app.bot`

Add products to MongoDB collection `products` with fields: `name`, `price`, `active`.

This version intentionally does not handle Telegram login OTPs, 2FA passwords, session strings, account credentials, or account-transfer automation.


## Force channel join

On `/start`, users are shown the Waste Botz image and asked to join `@jp_network`. They must tap Verify after joining. The bot checks membership using Telegram's Bot API. For reliable membership checks, add the bot as an administrator in the channel. After verification, the bot sends the main menu and command list.

The start image is the supplied Waste Botz image URL.


## In-bot Payment Settings

Admin: send `/admin` to open Payment Settings.
- 💳 UPI ID — change it directly
- 📷 QR Code — upload/change it directly
- 💬 Payment Instructions — edit directly
- 💰 Minimum Deposit — set directly
- 💰 Maximum Deposit — set directly; `0` means no limit

Settings are stored in MongoDB and persist across restarts/redeploys.
