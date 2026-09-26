# AI Football Predictor

A GitHub Actions–run pipeline that pulls real football data from multiple
providers, produces its own statistical (Poisson / Dixon-Coles / Elo)
market probabilities, compares them against real bookmaker odds, and
publishes the result to a static GitHub Pages frontend. No LLM guesses
scores, no automated betting, no exact-score predictions.

> **2026-09-26 update:** the provider clients were rewritten against each
> API's real, current documentation (GoalDir/BSD, The Odds API, API-Football,
> SportAPI.ai). The first version guessed at plausible-looking field names
> and shapes, which caused GoalDir fixtures to come back as "0 valid, 50
> rejected" — the real `/events/` response uses flat `event_date` /
> `home_score` / `away_score` fields and has no `league_name` at all (that's
> resolved separately via `/leagues/`). See "What changed" below for the
> full list of fixes.

## What's real vs. what's a stub

| Layer | Status |
|---|---|
| `src/core/*` (cache, rate limiter, API manager, validation) | Fully implemented, pure Python, no dependencies beyond `requests` |
| `src/models/*` (Poisson, Dixon-Coles, Elo, calibration) | Fully implemented and numerically verified |
| `src/engine/*` (market/value/risk/coupon engines) | Fully implemented |
| `src/learning/*` (episodes, backtest) | Fully implemented |
| `src/providers/*` | Endpoint paths, auth, pagination, error shapes and rate-limit headers verified against each provider's live docs (2026-09-25) — see per-file docstrings for source links. **You still need your own API keys.** |
| `src/pipeline/*` + `scripts/run_pipeline.py` | Wires everything together end-to-end, including league-name resolution and real per-fixture odds fetch; verified with a mocked GoalDir response (see "What changed") |
| Team-strength / feature building from real historical data | **Not implemented yet** — still placeholder league-average strengths (see "What to build next") |
| `docs/` frontend | Static site (HTML/CSS/JS, no build step) with sample data in `docs/data/*.json` |

## What changed (provider fixes)

Each fix below was a real bug caused by guessing at API shapes instead of reading the current docs:

- **GoalDir/BSD** (`src/providers/goaldir.py`)
  - Event list fields are `event_date`, flat `home_score`/`away_score`, and
    **no `league_name`** — `normalize.py` now maps these correctly, and a new
    `fetch_league_name_lookup()` resolves league names from `/leagues/`
    separately (cached ~24h).
  - `validate_fixture` no longer rejects a fixture for missing `league_name`
    — only `league_id` is required, since that's actually what the API sends.
  - Query parameters are validated client-side against GoalDir's documented
    `accepted_parameters` list — GoalDir's API rejects unknown params with a
    `400` rather than ignoring them.
  - Pagination (`{count, next, previous, results}`) is now followed properly.
  - Rate-limit headers are IETF structured fields (`RateLimit-Policy` /
    `RateLimit: "football";r=...;t=...`), not `x-requests-remaining` —
    `rate_limiter.py` now parses all three header styles used across providers.
  - Odds are fetched per-fixture via the real `/events/{id}/odds/` consensus
    shortcut and mapped onto our internal market names
    (`home_win → 1x2_home`, `over_15_goals → over_1.5`, etc.) in `fetch.py`.
- **The Odds API** (`src/providers/odds_api.py`) — confirmed correct already
  (host, `apiKey` query param, `markets × regions` cost formula, response
  headers); added `/events` (free) and per-event odds helper methods.
- **API-Football** (`src/providers/api_football.py`) — added the RapidAPI
  auth variant (`API_FOOTBALL_VIA_RAPIDAPI=1`), business-error checking
  (`errors` can be populated on a `200`), and dropped the unsupported
  bare `from`/`to` fixtures call in favor of `league+season+from/to` or a
  single `date` — API-Football has no documented from/to-without-league mode.
- **SportAPI.ai** (`src/providers/sportapi.py`) — fixed the base URL
  (`https://sportapi.ai/api/`, not the bare domain) and rewrote every
  endpoint as the real path-based routes (`/fixtures/date/{date}`,
  `/fixtures/h2h/{team1}/{team2}`, etc.) instead of invented query filters.

Verified end-to-end with a mocked GoalDir response (real field shapes, no
network needed): fixture validates, league name resolves, odds map onto the
right markets, and a pick is generated with a correct decision — see the
git history of this file for the exact test script if you want to rerun it.

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
