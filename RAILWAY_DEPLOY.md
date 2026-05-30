# Railway Deployment Guide — STARFIRE AI OS

This guide connects STARFIRE, Lumisnovacapital_bot, and OSIRIS in a single Railway project.

---

## Step 1 — Create a New Railway Project

1. Go to railway.app → New Project
2. Name it: `starfire-os`
3. This project will host ALL THREE services + shared Redis + PostgreSQL

---

## Step 2 — Add Shared Infrastructure

Inside `starfire-os` project, add plugins:

### PostgreSQL
- Click **+ New** → **Database** → **PostgreSQL**
- Railway auto-provides `DATABASE_URL` (no action needed)

### Redis
- Click **+ New** → **Database** → **Redis**
- Railway auto-provides `REDIS_URL` (no action needed)

---

## Step 3 — Deploy STARFIRE

1. Click **+ New** → **GitHub Repo** → select `rsimonjr10-hub/starfire`
2. Railway detects `railway.json` and builds from `Dockerfile`
3. Set the following environment variables in the STARFIRE service:

```env
APP_ENV=production
APP_SECRET_KEY=<random 32-char string>

# Injected automatically by Railway plugins:
# DATABASE_URL, REDIS_URL

ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=<starfire-bot-token-from-botfather>
TELEGRAM_WEBHOOK_URL=https://<your-starfire-domain>.railway.app

FMP_API_KEY=<your-fmp-api-key>

INTER_SERVICE_SECRET=<random 32-char string — SAME on all three services>

# Set AFTER Lumisnovacapital and OSIRIS are deployed (Step 6):
LUMISCAPITAL_SERVICE_URL=http://lumisnovacapital-bot.railway.internal:8001
OSIRIS_SERVICE_URL=http://osiris.railway.internal:8002

USE_MOCK_BROKER=false
RISK_MAX_DAILY_LOSS_PCT=5.0
RISK_MAX_POSITION_SIZE_PCT=25.0
RISK_MAX_TRADES_PER_DAY=10
```

---

## Step 4 — Deploy Lumisnovacapital_bot

1. In the same `starfire-os` project → **+ New** → **GitHub Repo**
2. Select your Lumisnovacapital_bot repo
3. Set these environment variables:

```env
INTER_SERVICE_SECRET=<same secret as STARFIRE>
FMP_API_KEY=<your-fmp-api-key>
TELEGRAM_BOT_TOKEN=<lumisnovacapital-bot-token>
PORT=8001
```

### Required endpoints to add to Lumisnovacapital_bot

STARFIRE expects these two endpoints on Lumisnovacapital:

```
POST /starfire/command
Headers: X-Service-Secret: <secret>
Body: {"command": "GET_PRICE", "params": {"symbols": "AAPL"}, "user_telegram_id": 123}
Response: {"status": "ok", "data": {...}}

POST /starfire/report
Headers: X-Service-Secret: <secret>
Body: {"report_type": "daily", "user_telegram_id": 123, "params": {}}
Response: {"status": "ok", "sent": true}

GET /health
Response: {"status": "ok"}
```

---

## Step 5 — Deploy OSIRIS

1. In the same `starfire-os` project → **+ New** → **GitHub Repo**
2. Select your OSIRIS repo
3. Set these environment variables:

```env
INTER_SERVICE_SECRET=<same secret as STARFIRE>
BROKER_API_KEY=<alpaca-key>
BROKER_API_SECRET=<alpaca-secret>
PORT=8002
```

### Required endpoints to add to OSIRIS

STARFIRE sends trade intents here:

```
POST /execute
Headers: X-Service-Secret: <secret>
Body: {
  "user_id": 123,
  "symbol": "AAPL",
  "side": "BUY",
  "size_pct": 10.0,
  "intent_payload": {...},
  "secret": "<inter-service-secret>"
}
Response: {
  "status": "FILLED",
  "filled_price": 185.50,
  "quantity": 5.4,
  "slippage": 0.0003,
  "order_id": "..."
}

GET /status
Response: {"status": "ok", "positions": {...}}

GET /health
Response: {"status": "ok"}
```

---

## Step 6 — Wire Services Together

Once all three are deployed, Railway assigns internal hostnames.

In STARFIRE's environment variables, set:
```
LUMISCAPITAL_SERVICE_URL=http://lumisnovacapital-bot.railway.internal:8001
OSIRIS_SERVICE_URL=http://osiris.railway.internal:8002
```

In Lumisnovacapital's variables (if it also calls OSIRIS):
```
OSIRIS_SERVICE_URL=http://osiris.railway.internal:8002
```

Railway internal networking format: `http://<service-name>.railway.internal:<PORT>`

---

## Step 7 — Register Telegram Webhooks

After deploy, register STARFIRE's webhook:

```bash
curl -X POST "https://api.telegram.org/bot<STARFIRE_TOKEN>/setWebhook" \
  -d "url=https://<starfire-domain>.railway.app/webhook/telegram"
```

Or run the helper script locally:
```bash
TELEGRAM_BOT_TOKEN=... TELEGRAM_WEBHOOK_URL=https://... python scripts/setup_telegram_webhook.py
```

---

## Step 8 — Verify Everything

1. Open STARFIRE in Telegram → send `/start`
2. Send `/price AAPL` → should return real price from FMP
3. Check `/admin/status` with the inter-service secret → shows all service health
4. Send `buy 5% AAPL` → STARFIRE proposes → confirm → OSIRIS executes

---

## Architecture on Railway

```
starfire-os (Railway Project)
├── starfire          ← this repo (port 8000)
├── lumisnovacapital  ← your FMP bot (port 8001)
├── osiris            ← your execution bot (port 8002)
├── PostgreSQL        ← shared DB
└── Redis             ← shared event bus
```

All services communicate via Railway's private network — no public exposure needed between services.

---

## Environment Variables Quick Reference

| Variable | Service | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | STARFIRE | Claude API key |
| `TELEGRAM_BOT_TOKEN` | Each bot | Each bot's own token |
| `FMP_API_KEY` | STARFIRE + Lumis | Financial Modeling Prep |
| `INTER_SERVICE_SECRET` | All three | Shared auth between services |
| `LUMISCAPITAL_SERVICE_URL` | STARFIRE | Internal URL of Lumis |
| `OSIRIS_SERVICE_URL` | STARFIRE | Internal URL of OSIRIS |
| `DATABASE_URL` | STARFIRE | Injected by Railway PostgreSQL |
| `REDIS_URL` | STARFIRE + Lumis | Injected by Railway Redis |
