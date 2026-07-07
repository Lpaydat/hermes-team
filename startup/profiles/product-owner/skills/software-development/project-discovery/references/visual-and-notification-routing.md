# Visual Layer + Notification Routing for Multi-Project Agent Teams

How to give the user visual oversight of their beads issue tracker and route
agent notifications across multiple profiles. Captured from a real setup session.

## Part 1: Beadbox — Native Desktop GUI for Beads

### What it provides (that `bd list` CLI can't)

- **Epic tree view** — parent → child hierarchy with completion %, dependency chains
- **Pipeline stages** — every issue tracked from open → in progress → QA → closed
- **Agent status cards** — which profile is working on what right now
- **Multi-project workspaces** — switch between projects in one app
- **Live WebSocket updates** — changes from `bd` appear in <2 seconds, no refresh

### Installation on Arch Linux (COSMIC / Wayland / AMD)

**The AppImage bundles its own WebKitGTK (Ubuntu build) which conflicts with
system Mesa EGL on AMD Radeon + Wayland, causing `EGL_BAD_PARAMETER` → blank
screen.** This is NOT fixable with `WEBKIT_DISABLE_DMABUF_RENDERER=1`,
`LIBGL_ALWAYS_SOFTWARE=1`, or `GDK_BACKEND=x11` — the failure is at EGL init,
before those flags take effect.

**Working approach: extract the `.deb` package instead.** The `.deb` binary
links against the system WebKitGTK (no bundled conflict):

```bash
# Download the .deb (not the AppImage)
curl -L -o /tmp/beadbox.deb \
  "https://github.com/beadbox/beadbox/releases/download/v0.24.1/beadbox_0.24.1_Linux_amd64.deb"

# Extract
mkdir -p /tmp/beadbox-deb && cd /tmp/beadbox-deb
ar x /tmp/beadbox.deb
tar xf data.tar.*

# Install to system paths (what the .deb expects)
sudo cp usr/bin/beadbox /usr/bin/beadbox
sudo cp -r usr/lib/Beadbox /usr/lib/Beadbox
sudo cp usr/share/applications/Beadbox.desktop /usr/share/applications/
```

**bd PATH issue:** The Tauri app's startup diagnostics may report `bd: NOT FOUND
ON PATH` even when `~/go/bin` is in the shell PATH. This is because the Tauri
runtime constructs its own PATH from a limited set of directories. Fix with a
wrapper script:

```bash
#!/bin/bash
# /usr/bin/beadbox-wrapper
export PATH="/home/<user>/go/bin:$PATH"
exec /usr/bin/beadbox "$@"
```

Update the `.desktop` file to use `Exec=beadbox-wrapper`.

**If the native window still doesn't render** (blank on COSMIC/Wayland), fall
back to running the embedded Next.js server directly and opening it in a
browser:

```bash
cd /usr/lib/Beadbox/server
PATH="/home/<user>/go/bin:$PATH" /usr/lib/Beadbox/node server.js
# Opens at http://127.0.0.1:3000
```

### Web-only fallback (if native binary also has rendering issues)

On COSMIC compositor (Wayland), the native Tauri window may launch (all 3
processes — main, WebKitWebProcess, Node server — running) but produce no
visible window or a blank window. xdotool (X11-only) can't see Wayland
windows to verify. In this case, the web fallback is the reliable path:

```bash
# Kill any native instance
pkill -f "beadbox" 2>/dev/null

# Run just the Next.js server from the extracted AppImage or .deb install
# The server is at /usr/lib/Beadbox/server/ (from .deb) or ~/.local/share/beadbox-server/ (from AppImage extraction)
cd /usr/lib/Beadbox/server
PATH="/home/<user>/go/bin:$PATH" nohup /usr/lib/Beadbox/node server.js &
# Open http://127.0.0.1:3000 in any browser — full UI, all features
```

The web mode is functionally identical to the desktop app — same Next.js
frontend, same WebSocket updates, same beads integration. The only thing
missing is the native window chrome.

**Diagnostic for blank screen:**
- `EGL_BAD_PARAMETER` at startup = bundled WebKit conflicts with system Mesa (AppImage only)
- Process running but no window = COSMIC/Wayland compositor not mapping the GTK window
- `bd: NOT FOUND` in diagnostics = Tauri runtime strips PATH; use wrapper script
- Native binary (from .deb) using system WebKit = no EGL error, but may still not render window on COSMIC

### Fish shell alias

Create `~/.config/fish/functions/beadbox.fish`:

```fish
function beadbox --description 'Launch Beadbox desktop app'
    if pgrep -f "beadbox" >/dev/null 2>&1
        echo "Beadbox is already running"
        return 0
    end
    PATH="/home/<user>/go/bin:$PATH" nohup /usr/bin/beadbox >/dev/null 2>&1 &
    disown
    echo "Beadbox launched"
end
```

## Part 2: Gateway Routing — Telegram vs Discord for Multi-Profile Teams

### The core problem

With 1 Telegram bot serving all profiles, messages from product-owner,
tech-lead, and researcher all arrive from the same bot identity. There's no
visual separation between "who said what".

### Why Discord fits a "company in Discord" pattern better

| Dimension | Telegram (1 bot) | Discord (channels + bots) |
|-----------|------------------|---------------------------|
| Profile identity | Same bot, prefix in text | Each profile routed to its own channel |
| Structure | Flat topics | Server → category → channel → thread |
| Project separation | Awkward | Natural (category per project) |
| Company mimic | Flat | Hierarchical |

### Recommended Discord server structure

```
🏢 COMPANY HQ (server)
├── 📋 PRODUCT
│   ├── #sprint-review     ← weekly steward cron posts here
│   ├── #hygiene-alerts    ← watchdog cron posts here
│   └── #decisions
├── 🔧 ENGINEERING
│   ├── #<project-1>       ← one channel per active project
│   └── #<project-2>
├── 🤖 AGENTS
│   ├── #product-owner
│   ├── #tech-lead
│   ├── #researcher
│   └── #scout
```

**Channel lifecycle:** When a project is deleted, delete its Discord channel
immediately. Do NOT leave stale channels — they create confusion and make
the user think the system isn't tracking what's active.

### Hermes gateway configuration

**Single-dispatcher posture:** Only one gateway (typically `default` profile)
owns the kanban dispatcher. Others set `kanban.dispatch_in_gateway: false` in
`~/.hermes/config.yaml` to avoid SQLite contention.

**Cron delivery routing:** Each cron job's `deliver` field controls where output
goes. Set it to the platform:channel combination:

- `deliver='discord'` → uses `DISCORD_HOME_CHANNEL` from env
- `deliver='telegram'` → uses `TELEGRAM_HOME_CHANNEL` from env
- `deliver='local'` → saves to reports dir only (user never sees it unless they
  check files — avoid this for user-facing reports)

**Key env vars** (in `~/.hermes/.env`):

```
DISCORD_BOT_TOKEN=<token>
DISCORD_HOME_CHANNEL=<channel_id>
DISCORD_ALLOWED_USERS=<user_id>
```

**Multi-profile approach — start with 1 bot, channel-based routing.** Messages
in `#product-owner` are obviously from that profile. Create separate bots per
profile only if the shared identity feels insufficient after trying it.

### Bot setup steps

**Step 1 — Invite the bot (manual, needs browser):**

1. Get the bot's client ID: `curl -s -H "Authorization: Bot $DISCORD_BOT_TOKEN" https://discord.com/api/v10/users/@me`
2. Generate invite URL with permissions integer:
   - Send Messages (2048) + Read Message History (1024) + Embed Links (16384) + Attach Files (32768) + Manage Threads (1<<34)
   - URL: `https://discord.com/oauth2/authorize?client_id=<ID>&permissions=<PERMS>&scope=bot%20applications.commands`
3. Open in browser → select server → authorize

**Step 2 — Create server structure (automated via Discord API):**

Once the bot is in a server, you can create categories and channels
programmatically — no need for the user to do it manually:

```bash
GUILD_ID="<server-id>"

# Create a category (type 4)
curl -s -X POST -H "Authorization: Bot $DISCORD_BOT_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name": "PRODUCT", "type": 4}' \
    "https://discord.com/api/v10/guilds/$GUILD_ID/channels"

# Create a text channel under a category (type 0, parent_id = category ID)
curl -s -X POST -H "Authorization: Bot $DISCORD_BOT_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name": "hygiene-alerts", "type": 0, "parent_id": "<category-id>"}' \
    "https://discord.com/api/v10/guilds/$GUILD_ID/channels"

# Delete a channel (when a project is removed)
curl -s -X DELETE -H "Authorization: Bot $DISCORD_BOT_TOKEN" \
    "https://discord.com/api/v10/channels/<channel-id>"

# Send a rich embed message
curl -s -X POST -H "Authorization: Bot $DISCORD_BOT_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"embeds": [{"title": "...", "description": "...", "color": 15548997}]}' \
    "https://discord.com/api/v10/channels/<channel-id>/messages"
```

**Step 3 — Configure Hermes:**

```bash
# Set home channel in .env
echo "DISCORD_HOME_CHANNEL=<channel-id>" >> ~/.hermes/.env

# Cron delivery routing: use platform:guild:channel format
# In cronjob tool: deliver="discord:<guild-id>:<channel-id>"

# Restart gateway
hermes gateway restart
```

**Step 4 — Test delivery:**

Send a test message to the channel via the API (above) to confirm the
bot can post before relying on cron delivery.

### Trade-off: mobile push

Telegram has better mobile push reliability than Discord. For critical alerts
(build failures, blocked tasks), consider keeping Telegram as a secondary
"pager" channel for urgent-only notifications, with Discord for the full
company structure.
