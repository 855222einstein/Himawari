# NomadeHelpBot Deploy Notes

## Required environment variables

- `API_ID`
- `API_HASH`
- `BOT_TOKEN`
- `MONGO_URI`
- `DB_NAME`
- `OWNER_ID`
- `BOT_USERNAME`
- `LOG_CHAT_ID` — add the bot to this group/channel as admin first. Use a `-100...` Telegram ID.
- `SUDO_USERS` — comma-separated Telegram user IDs.

## Render

Use the included `render.yaml`, or create a Worker service manually:

- Build command: `pip install --upgrade pip && pip install -r requirements.txt`
- Start command: `python main.py`

## Koyeb

Deploy with the included Dockerfile, or use:

- Run command: `python main.py`

## Log channel test

After deploy, send `/logtest` to the bot. If it replies that logging is not working, check that:

1. `LOG_CHAT_ID` is correct.
2. The bot is added to that log group/channel.
3. The bot is admin in private channels.
