# Hiro Outfield Chatbot — v3.1 Final

Warm, human-like Telegram bot that speaks as “Hiro” to Jennifer, with admin-only controls, JSONBin persistence, and flexible scheduling.

## ✨ Features
- **Admin-only** scheduling with inline buttons: view → edit time / edit message / delete
- **Clean list view** shows preview, not full text
- **One-field-per-edit** flow with save confirmation
- **All scheduled messages go ONLY to Jennifer** (`TARGET_CHAT_ID`)
- **Affectionate auto-ack** (5–10s after each scheduled message), randomized, gentle
- **Human-like replies** in short bubbles + typing simulation
- **Light tone matching + subtle emoji sprinkle**
- **Debug mode** to skip logging/memory for admin (`/debug_on`, `/debug_off`)
- **/lastseen** – shows when Jennifer last messaged (from Logs bin)
- **/help** – command guide
- **SG timezone** throughout

## 🔐 Environment Variables (Render)
Set these in Render → Environment:
```
OPENAI_API_KEY=...
TELEGRAM_TOKEN=...
JSONBIN_API_KEY=...
MEMORY_BIN_ID=...
LOGS_BIN_ID=...
SCHEDULES_BIN_ID=...
```

> You **do not** need a `.env` file if you configure Environment Vars in Render.

## 🛠️ Commands (Admin only)
- `/help` — show command list
- `/schedule YYYY-MM-DD HH:MM message` — add schedule (24h), also supports `8pm`/`8:30PM`
- `/schedule_list` — compact list with buttons to view/edit/delete
- `/deleteschedule` — delete **all** schedules
- `/lastseen` — show when she last chatted (from logs)
- `/sendlog` — send `chat_logs.json` to admin
- `/debug_on` / `/debug_off` — toggle debug (skips admin memory/logs)

## 🧩 Personalization
Edit near the top of `bot.py`:
- `ADMIN_CHAT_ID = ...` (you)
- `TARGET_CHAT_ID = ...` (Jennifer)
- `NICKNAMES = ["babe", "baby", "my love"]`
- `GIRLFRIEND_PROFILE["short_bio"]` for background/context in the system prompt

## 🚀 Deploy
1. Upload `bot.py` to GitHub (it overwrites the old one)
2. Render auto-deploys (no need to disable auto deploy)
3. Watch logs to confirm “Application started”

## ✅ Quick sanity checks (Render logs)
- “Scheduler started” — APScheduler alive
- `getMe` 200 OK — Telegram token valid
- “Application started” — polling is on
- After `/schedule`: confirm time + message
- At delivery time: “Delivered to her” + your admin confirmation

---

**Note:** This repo should remain private if you store anything sensitive. Tokens **must** live in Render environment vars, not in the repo.
