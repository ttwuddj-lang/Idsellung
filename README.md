# WasteBotz

Updated build with:
- Deposit transaction IDs (numeric or alphanumeric) followed by screenshot submission.
- Admin deposit approval/decline notifications with buyer mention, username, user ID, amount and transaction ID.
- 30-minute deposit expiry.
- Product stock inventory: stock decreases after purchase and products at zero stock disappear from the user list.
- `/stock` and `/setstock PRODUCT_ID QUANTITY` for admins.
- `/broadcast` for admins: reply to any message (including a forwarded channel message) and send `/broadcast`.
- Force-join protected menu/commands.

Railway start command:
`python -m app.bot`
