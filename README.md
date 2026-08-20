# WasteBotz

## Run

python -m app.bot

Set BOT_TOKEN, MONGO_URI and ADMIN_IDS in Railway Variables.

## Payment flow
Amount -> Transaction ID -> Screenshot -> Admin Approve/Decline.
Numeric transaction IDs are handled correctly and are not treated as deposit amounts.
