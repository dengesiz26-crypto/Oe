# AI Football Predictor

A GitHub Actions–run pipeline that pulls real football data from multiple
providers, produces its own statistical (Poisson / Dixon-Coles / Elo)
market probabilities, compares them against real bookmaker odds, and
publishes the result to a static GitHub Pages frontend. No LLM guesses
scores, no automated betting, no exact-score predictions — see
`docs-plan.md`-style notes inline in the code for the full rationale.

## What's real vs. what's a stub

This repo is a **working scaffold**, not a finished production system —
being upfront about that:

| Layer | Status |
|---|---|
| `src/core/*` (cache, rate limiter, API manager, validation) | Fully implemented, pure Python, unit-testable, no dependencies beyond `requests` |
| `src/models/*` (Poisson, Dixon-Coles, Elo, calibration) | Fully implemented and numerically verified (see below) |
| `src/engine/*` (market/value/risk/coupon engines) | Fully implemented |
| `src/learning/*` (episodes, backtest) | Fully implemented |
| `src/providers/*` | Real endpoint/auth wiring per each API's documented contract, but **you must supply your own API keys** — the HTTP calls are untested against live traffic in this environment (no network access here) |
| `src/pipeline/*` + `scripts/run_pipeline.py` | Wires everything together end-to-end; runs safely with **zero** API keys set (does a clean no-op dry run instead of crashing) |
| Team-strength / feature building from real historical data | **Not implemented yet** — `run_pipeline.py` currently uses placeholder league-average strengths. This is the next real piece of work (see below) |
| `docs/` frontend | Fully built static site (HTML/CSS/JS, no build step) with sample data in `docs/data/*.json` so you can see it working before wiring real data |

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in whichever provider keys you have
python scripts/run_pipeline.py
```

With no keys set, this runs cleanly end-to-end and writes empty-but-valid
JSON to `docs/data/`. Open `docs/index.html` via a local server (not
`file://`, browsers block `fetch()` of local JSON on the file protocol):

```bash
cd docs && python3 -m http.server 8000
# then open http://localhost:8000
```

## Architecture

```
GoalDir/BSD  API-Football  The Odds API  SportAPI.ai
        \        |             |            /
                    API MANAGER
        (cache -> quota/rate limit -> priority -> retry/backoff)
                         |
                DATA VALIDATION (reject/quarantine)
                         |
                  NORMALIZED STORE
                         |
     FEATURE ENGINE (Elo / Poisson strengths / Dixon-Coles / form)
                         |
                 PROBABILITY MODEL
                         |
              VALUE ENGINE (fair odds / edge)
                         |
               RISK ENGINE (BANKO/STANDARD/IDEAL/RISKLI/UZAK DUR)
                         |
                 COUPON ENGINE
                         |
              docs/data/*.json  --(git commit)-->  GitHub Pages
                         |
              EPISODES -> SETTLEMENT -> BACKTEST -> (feeds calibration)
```

## Provider setup

Each provider client (`src/providers/*.py`) documents its own base URL,
auth header, and the exact fields it maps into our canonical fixture
schema. Set the corresponding environment variable / GitHub secret and
it activates automatically — nothing else to change:

- `GOALDIR_API_KEY` — primary data source (fixtures, odds, standings, live)
- `ODDS_API_KEY` — market price verification (mind the market×region credit cost)
- `API_FOOTBALL_KEY` — secondary verification only (100 req/day free tier — the code deliberately avoids bulk pulls from this one)
- `SPORTAPI_KEY` — tertiary verification (stats, H2H)

## Design decisions worth knowing about

- **MIN_ODDS = 1.25** (`src/core/config.py`) — a high-probability pick at
  too-low a price is a probability read, not a betting recommendation.
  Change this in one place.
- **Classification bands are provisional.** `settings.classification_bands`
  in `config.py` holds the ≥65/60/55/48% cutoffs from the original spec.
  `src/learning/backtest.py` computes Brier/LogLoss/ECE/ROI so you can
  actually test whether those cutoffs are calibrated once you have
  settled episodes — don't treat them as final.
- **No leakage guard.** `src/core/validation.py::enforce_no_leakage`
  exists specifically so a post-kickoff lineup or live stat can never
  feed a pre-match prediction. Call it when building features.
- **The frontend never calls a provider API.** It only ever reads
  `docs/data/*.json`, which only the GitHub Actions pipeline writes.

## What to build next (in priority order)

1. **Historical bootstrap** — a one-time script to pull ~50k historical
   matches (`data/historical/`) and fit real Elo ratings + attack/defence
   strengths, replacing the `TeamStrength(attack=1.0, defence=1.0)`
   placeholder in `scripts/run_pipeline.py`.
2. **Feature engine** — recent form, home/away split, opponent-adjusted
   goals, xG where available; wire `enforce_no_leakage` in here.
3. **Odds wiring** — populate `market_odds` in `run_pipeline.py` from
   `OddsApiProvider.get_odds()` / GoalDir best-odds, mapped onto the same
   market keys the market engine produces (`over_1.5`, `1x2_home`, etc).
4. **Walk-forward calibration** — once real episodes accumulate, refit
   the Dixon-Coles `rho` and re-check the classification bands against
   `walk_forward_report()`.
