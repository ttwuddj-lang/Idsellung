# WasteBotz

Safe Telegram digital-store bot with force-join, wallet/deposit approval, admin fund management and a normal digital-product catalogue.

## Railway
Start command: `python -m app.bot`

Required variables: BOT_TOKEN, MONGO_URI, MONGO_DB, ADMIN_IDS

## Admin commands
- /admin
- /balance <telegram_id or @username>
- /addfunds <telegram_id or @username> <amount>
- /removefunds <telegram_id or @username> <amount>

Deposit requests expire after 30 minutes. Payment screenshots are sent to all configured ADMIN_IDS with Approve/Reject buttons.

This build does not automate Telegram account login, OTP delivery, session handling, or account transfers.
