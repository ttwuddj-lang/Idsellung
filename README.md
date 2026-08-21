# WasteBotz

Railway start command:

python -m app.bot

Required environment variables: BOT_TOKEN, MONGO_URI, ADMIN_IDS.
Optional: MONGO_DB, UPI_ID.

Admin inventory: /admin -> Add Account / Remove Account / Account Stock.

IMPORTANT: This project must not install the standalone `bson` PyPI package. PyMongo supplies its own `bson` package. The Railway build command removes any stale standalone `bson` package from a cached environment before reinstalling the requirements.
