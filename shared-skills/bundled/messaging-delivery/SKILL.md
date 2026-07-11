---
name: messaging-delivery
description: Verify and troubleshoot message delivery from Hermes to external messaging platforms (Telegram, Discord, Slack, Signal). Covers the diagnostic ladder from "send failed" to root cause, cross-profile credential visibility, and bot-priming prerequisites. Load when a cron job or manual send needs to reach the user on a messaging platform and delivery fails or is untested.
version: 1.0.0
---

# Messaging delivery — verify and troubleshoot

When you need to send a message to the user via Telegram/Discord/Slack/Signal —
whether from a cron job, a manual `hermes send`, or agent tooling — and delivery
fails or hasn't been tested yet, follow this diagnostic ladder.

## Step 1 — Check the gateway is running

```
hermes gateway status
```

If no gateway is running, start one: `hermes gateway start` (or `hermes gateway run`
for foreground). Cron delivery requires a running gateway on the target profile.

**Cross-profile note:** `hermes gateway status` shows all profiles. The gateway runs
per-profile — a gateway on `default` does NOT serve `research`. If your profile shows
`✗ not running`, that profile's cron jobs won't deliver.

## Step 2 — Verify credentials exist

Credentials live in `~/.hermes/.env` (main) or `~/.hermes/profiles/<profile>/.env`
(per-profile). The per-profile file overrides the main one.

```
grep -i 'TELEGRAM_BOT_TOKEN\|DISCORD_TOKEN\|SLACK_TOKEN' ~/.hermes/.env
grep -i 'TELEGRAM_BOT_TOKEN\|DISCORD_TOKEN\|SLACK_TOKEN' ~/.hermes/profiles/<profile>/.env
```

**Common gotcha:** credentials are set in the main `~/.hermes/.env` but the active
profile's `.env` is empty or missing them. `hermes send` run under that profile then
reports `Platform 'X' is not configured`. Fix: either copy the relevant env vars into
the profile's `.env`, or export them in the shell before calling `hermes send`.

### Cross-profile token extraction (verified pattern)

When credentials live in `~/.hermes/.env` (default profile) but you need to send from
a different profile (e.g. `research`), extract and export them inline:

```bash
TOKEN=$(grep "^TELEGRAM_BOT_TOKEN=" ~/.hermes/.env | head -1 | cut -d= -f2-)
TELEGRAM_BOT_TOKEN="$TOKEN" TELEGRAM_HOME_CHANNEL=<chat_id> \
  hermes send --to telegram "message"
```

**Critical details** (each caused a real failure during setup):
- Use `cut -d= -f2-` (not `-f2`) — grabs everything after the first `=`
- Use `head -1` — without it, trailing newlines cause `Invalid non-printable ASCII character in URL`
- Use `grep "^TELEGRAM_BOT_TOKEN="` (anchored) — avoids matching commented-out lines

## Step 3 — Test with `hermes send`

```
hermes send --to telegram "test message"
hermes send --to telegram:<chat_id> "test message"
hermes send --to discord:#channel "test message"
```

Run `hermes send --list` to see all configured targets.

### `hermes send` syntax

- `hermes send --to <platform> "message"` — sends to the platform's home channel
- `hermes send --to <platform>:<chat_id> "message"` — sends to a specific chat
- `hermes send --to <platform> --file /path/to/file.md` — sends file contents
- `hermes send --to <platform> "MEDIA:/path/to/image.png"` — sends an attachment
- `hermes send --list` / `hermes send --list telegram` — list available targets

## Step 4 — Error → cause → fix matrix

| Error | Root cause | Fix |
|-------|-----------|-----|
| `Platform 'X' is not configured` | Credentials not visible to the active profile | Copy env vars into `~/.hermes/profiles/<profile>/.env`, or export them in shell |
| `Invalid non-printable ASCII character in URL` | Trailing newline in the bot token from `grep` extraction | Use `head -1` and `cut -d= -f2-` (not `-f2`) when extracting tokens from `.env` |
| `Chat not found` (Telegram) | User hasn't started a conversation with the bot | User must open the bot and send `/start` — bots cannot message users who haven't initiated |
| `409 Conflict: terminated by other getUpdates request` | The gateway is already long-polling the bot | This is **normal** when the gateway is running — it means the gateway owns the update stream. Use direct `sendMessage` via `hermes send`, not `getUpdates` |
| `Unauthorized` / `401` | Bot token is wrong or revoked | Re-create the token via BotFather (Telegram) or the platform's dev console |
| `Forbidden: bot was blocked by the user` | User blocked the bot | User must unblock it |

## Step 5 — Bot-priming prerequisite (Telegram/Discord)

**Telegram:** A bot CANNOT initiate a conversation with a user. The user must:
1. Search for the bot (e.g. `@my_hermes_bot`)
2. Send `/start` to it

Until this happens, `sendMessage` returns `Chat not found`. This is a Telegram
platform constraint, not a Hermes bug. Check the bot username with:

```
TOKEN=$(grep "^TELEGRAM_BOT_TOKEN=" ~/.hermes/.env | head -1 | cut -d= -f2-)
curl -s --max-time 5 "https://api.telegram.org/bot${TOKEN}/getMe"
```

This returns the bot's `username` and `id`. Give the username to the user so they
can find and `/start` it.

**Discord:** The bot must share a server with the user and have permission to post
in the target channel.

## Step 6 — Verify the chat ID is correct

The `TELEGRAM_HOME_CHANNEL` env var must be the user's numeric chat ID (for DMs) or
the negative group/supergroup ID (for channels). If it's wrong, messages go nowhere
or to the wrong place. Verify by checking what the gateway sees in its logs:

```
hermes logs --tail 50 | grep -i telegram
```

## Cron delivery targeting

For cron jobs that need to deliver to a messaging platform:

- `deliver='telegram'` — sends to the home channel
- `deliver='telegram:<chat_id>:<thread_id>'` — sends to a specific topic in a forum
- `deliver='all'` — fans out to every connected platform
- `deliver='origin'` — sends back to the originating chat (default)

In TUI/CLI sessions, `deliver='origin'` or default delivery does NOT produce a visible
message in the current session — there is no live-delivery channel. The job's output
is saved (viewable via `cronjob action='list'`) but not shown. To get notified, the
job's `deliver` must target a gateway-connected platform.
