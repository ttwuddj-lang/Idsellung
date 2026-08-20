# Waste Botz

Admin catalogue: country, product name, price; add/edit/delete/enable/disable.
Payment settings: UPI, QR, instructions, min/max deposit.
MongoDB-backed wallet, deposits, orders and support.
Force join @jp_network.

This build does not automate Telegram account login, OTPs, session strings, 2FA passwords, or account transfers.


## Admin user funds

Admins can manage user wallet funds from `/admin` → **Manage User Funds**.

Commands:
- `/balance USER_ID_OR_USERNAME`
- `/addfunds USER_ID_OR_USERNAME AMOUNT`
- `/removefunds USER_ID_OR_USERNAME AMOUNT`

Fund changes are recorded in MongoDB `wallet_transactions`. Removing more than the user's balance is blocked. Deposit requests remain valid for 30 minutes.
