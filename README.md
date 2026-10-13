# Main-2 Telegram bot — Render deployment

## Important security note
The old bot token was present in the uploaded source. Treat it as compromised: open **@BotFather**, revoke the old token with `/revoke`, generate a new token, and set only the new token as the Render `BOT_TOKEN` environment variable. Do not commit `.env` or any real token to GitHub.

## Files
- `Main-2.py` — patched bot source (token is read from environment)
- `requirements.txt` — Python dependencies
- `render.yaml` — Render Background Worker blueprint and persistent disk
- `.env.example` — environment variable template; contains placeholders only

## Deploy from a phone
1. Create a new GitHub repository and upload these files from this folder. Do **not** upload a real `.env` file.
2. In Render, choose **New + → Blueprint** and connect that repository, or create a **Background Worker** manually.
3. For a manual worker use:
   - Build command: `pip install -r requirements.txt`
   - Start command: `python Main-2.py`
   - Runtime: Python
4. Add environment variables in Render:
   - `BOT_TOKEN`: the newly generated token from BotFather
   - `ADMIN_ID`: your numeric Telegram user ID
   - `DATABASE_PATH`: `/var/data/Galu.db`
   - `FAMGATEWAY_API_KEY`: optional until you have a valid key
5. Attach a persistent disk mounted at `/var/data` (1 GB is enough to start). Without a persistent disk, a SQLite database can be lost when the service is replaced or redeployed.
6. Deploy and open the Render logs. Successful startup should pass configuration checks and begin Telegram polling.

## Fresh database
The app creates its SQLite tables on first startup at `DATABASE_PATH`. Because this is a new database, old users, products, keys, transactions, and settings are not imported.

## Payment configuration
Automatic FamGateway verification will not work until a valid `FAMGATEWAY_API_KEY` is configured. Test payment flow with a small amount before real use. Do not treat a browser return page alone as proof of payment.

## Validation performed
The patched file was checked with Python bytecode compilation. This confirms Python syntax, not successful live Telegram API calls or every runtime feature. After deployment, inspect logs and test `/start`, admin actions, database writes, and payment verification separately.
