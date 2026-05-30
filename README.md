# STARFIRE AI OS

A production-ready AI Operating System powered by Claude.

```
User → Telegram → FastAPI → STARFIRE (Claude) → Decision Engine
                                   ↓
                            Risk Engine Validation
                                   ↓
                            OSIRIS Executor
                                   ↓
                            Broker API (mock/Alpaca)
```

## Architecture

| Component | Role |
|-----------|------|
| **STARFIRE** | Conversational brain (Claude API). Thinks, decides, confirms. |
| **OSIRIS** | Execution-only engine. No AI, no decisions. Pure trade execution. |
| **Risk Engine** | Hard-limit enforcement. Blocks invalid trades before OSIRIS. |
| **Event Bus** | Redis pub/sub. Workers publish events; STARFIRE consumes. |
| **Telegram Bot** | User interface. Supports chat + commands. |
| **PostgreSQL** | Persistent storage for all system state. |

## Core Rule

> **STARFIRE NEVER executes trades. OSIRIS NEVER makes decisions.**

## Quick Start

### Local Development

```bash
cp .env.example .env
# Edit .env with your keys

docker-compose up -d postgres redis
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

### Deploy to Railway

1. Push to GitHub
2. Connect repo to Railway
3. Add PostgreSQL + Redis plugins
4. Set environment variables (see `.env.example`)
5. Railway auto-deploys via `railway.json`

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key |
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_WEBHOOK_URL` | Your Railway deployment URL |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `USE_MOCK_BROKER` | `true` for paper trading |

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Initialize session |
| `/portfolio` | Portfolio snapshot |
| `/tasks` | Pending tasks |
| `/spending` | 30-day spending summary |
| `/goals` | Active goals with progress |
| `/risk` | Current risk limits |

## Risk Limits (enforced, no exceptions)

- Max daily loss: **5%**
- Max position size: **25%**
- Max trades per day: **10**

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/webhook/telegram` | Telegram webhook receiver |
| `GET` | `/api/portfolio/{telegram_id}` | Get portfolio |
| `POST` | `/api/portfolio/update` | Push portfolio snapshot |
| `GET` | `/api/trades/{telegram_id}` | Trade history |
| `GET` | `/api/goals/{telegram_id}` | Active goals |
| `PATCH` | `/api/goals/{id}/progress` | Update goal progress |

## Running Tests

```bash
pytest
```
