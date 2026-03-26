# Deploy On Reflex Cloud

This app is prepared for Reflex Cloud deployment with:

- a top-level [`requirements.txt`](/Users/aaustin2/mlb-betting-model/requirements.txt)
- cloud-safe Reflex config in [`rxconfig.py`](/Users/aaustin2/mlb-betting-model/rxconfig.py)
- centralized environment access in [`app/runtime_env.py`](/Users/aaustin2/mlb-betting-model/app/runtime_env.py)
- startup readiness checks in [`reflex_app/services/startup_checks.py`](/Users/aaustin2/mlb-betting-model/reflex_app/services/startup_checks.py)

## Prerequisites

- Python 3.11 recommended
- Reflex `0.6.6` or newer
- A working The Odds API key if you want live odds refresh

Current pinned Reflex version:

```text
reflex==0.8.28.post1
```

## Required Environment Variables

Required for core app persistence:

- `MLB_MODEL_DB_PATH`
  Example: `/data/mlb_betting_model.sqlite`

Optional but recommended:

- `ODDS_API_KEY`
  Enables live board odds refresh and detailed totals fetches
- `API_URL`
  Public backend URL override for hosted browser traffic
- `DEPLOY_URL`
  Public frontend URL override for deployment metadata
- `DATABASE_URL`
  Optional future-facing database setting. The current build supports `sqlite` only.
  Example: `sqlite:////data/mlb_betting_model.sqlite`
- `MLB_MODEL_HISTORY_DIR`
  Optional legacy history directory

Notes:

- If `DATABASE_URL` is set, it takes priority over `MLB_MODEL_DB_PATH`.
- Non-sqlite `DATABASE_URL` schemes are rejected at startup so deployment failures are clear.
- Missing `ODDS_API_KEY` does not block the app. The board falls back to cache / no-live-odds mode gracefully.

## Local Test Command

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the app locally:

```bash
reflex run
```

Useful local environment example:

```bash
export MLB_MODEL_DB_PATH="$PWD/db/mlb_betting_model.sqlite"
export ODDS_API_KEY="your_real_key"
reflex run
```

## Reflex Cloud Deploy Flow

1. Authenticate:

```bash
reflex login
```

2. Set or update secrets in Reflex Cloud before deploy.

Recommended approach:

- use the Reflex Cloud dashboard secrets UI, or
- use the Reflex Cloud CLI secret command documented here:
  [Secrets](https://reflex.dev/docs/ai-builder/features/secrets/)

At minimum, configure:

- `MLB_MODEL_DB_PATH`
- `ODDS_API_KEY` if live odds should work in production
- `API_URL` and `DEPLOY_URL` only if you need explicit public URL overrides

3. Deploy:

```bash
reflex deploy
```

If you need to re-deploy after changing secrets, re-run:

```bash
reflex deploy
```

## Secrets Guidance

- Never hardcode API keys in code, config, or `cloud.yml`.
- Keep production values in Reflex Cloud secrets only.
- The app logs only whether a secret is present or missing. It never prints secret values.

## Persistence Notes

The Reflex app currently persists these features in SQLite:

- tracked performance snapshots: `performance_bets`
- graded results and CLV updates: `performance_bets`
- cached live odds and quota snapshots: `odds_api_cache`
- prediction / market history already stored in the existing project tables

Current production-ready behavior:

- the database path is environment-driven
- startup verifies database connectivity
- schema initialization runs automatically

Important limitation:

- the current app is still SQLite-backed
- for durable multi-instance production storage, keep the env interface the same and replace the SQLite connection layer later
- this release is structured so that future database driver work is isolated behind env/config and connection helpers

## Startup Checks

At app startup, Reflex logs:

- Reflex version compatibility
- whether `ODDS_API_KEY` is present
- whether `DATABASE_URL` is present
- database scheme and resolved SQLite target
- database connection status
- key service initialization status

These messages are concise and deployment-friendly, and they do not print secret values.

## Post-Deploy Smoke Test Checklist

- [ ] App loads successfully on the deployed Reflex Cloud URL
- [ ] No startup errors appear in deployment logs
- [ ] Dashboard and Daily Matchups render without crashing
- [ ] Manual live odds refresh works when `ODDS_API_KEY` is configured
- [ ] Missing live odds falls back gracefully when `ODDS_API_KEY` is absent or the API is unavailable
- [ ] `Save Board Snapshot` writes tracked rows successfully
- [ ] Tracked rows appear on the Performance tab
- [ ] `Grade Results` runs without crashing
- [ ] Closing odds / CLV render on tracked rows when available
- [ ] Performance delete actions still work

## Quick Troubleshooting

If live odds do not refresh:

- confirm `ODDS_API_KEY` is set in Reflex Cloud
- check logs for `[Reflex Odds]` messages
- confirm the board is falling back to cache instead of crashing

If the app fails at startup:

- confirm `MLB_MODEL_DB_PATH` points to a writable location
- remove unsupported `DATABASE_URL` schemes
- check logs for `[Startup]` messages

If snapshots or grading fail:

- confirm the database path is writable
- check logs for `[Reflex Performance]` messages
