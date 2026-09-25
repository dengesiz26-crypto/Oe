from __future__ import annotations

import math
import os
import statistics
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import numpy as np
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS


# ============================================================
# CONFIG
# ============================================================

API_BASE = "https://sports.bzzoiro.com/api/v2"

API_KEY = (
    os.getenv("GOALDIR_API_KEY")
    or os.getenv("BSD_API_KEY")
    or ""
).strip()

PORT = int(os.getenv("PORT", "5000"))

HISTORY_SEASONS = int(
    os.getenv("HISTORY_SEASONS", "3")
)

MIN_HISTORY = int(
    os.getenv("MIN_HISTORY", "8")
)

MIN_CONFIDENCE = float(
    os.getenv("MIN_CONFIDENCE", "0.55")
)

MIN_EDGE = float(
    os.getenv("MIN_EDGE", "0.025")
)

MAX_GOALS = 8

SESSION = requests.Session()

if API_KEY:
    SESSION.headers.update({
        "Authorization": f"Token {API_KEY}",
        "Accept": "application/json",
    })


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)
CORS(app)


# ============================================================
# CACHE
# ============================================================

CACHE = {}


def cache_get(key):
    item = CACHE.get(key)

    if not item:
        return None

    return item["value"]


def cache_put(key, value):
    CACHE[key] = {
        "value": value,
        "created": datetime.now(timezone.utc),
    }


# ============================================================
# HTTP
# ============================================================

def api_get(path, params=None):
    if not API_KEY:
        raise RuntimeError(
            "GOALDIR_API_KEY is missing."
        )

    key = path + "?" + "&".join(
        f"{k}={v}"
        for k, v in sorted(
            (params or {}).items()
        )
    )

    cached = cache_get(key)

    if cached is not None:
        return cached

    url = API_BASE.rstrip("/") + "/" + path.lstrip("/")

    response = SESSION.get(
        url,
        params=params or {},
        timeout=30,
    )

    if response.status_code == 401:
        raise RuntimeError(
            "GOALDIR API authentication failed (401)."
        )

    if response.status_code == 403:
        raise RuntimeError(
            "GOALDIR API access denied (403)."
        )

    if response.status_code == 429:
        raise RuntimeError(
            "GOALDIR API rate limit reached (429)."
        )

    response.raise_for_status()

    data = response.json()

    cache_put(key, data)

    return data


# ============================================================
# PAGINATION
# ============================================================

def extract_results(payload):
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in (
        "results",
        "data",
        "events",
        "fixtures",
        "items",
    ):
        value = payload.get(key)

        if isinstance(value, list):
            return value

    return []


def fetch_all(path, params=None, max_pages=100):
    params = dict(params or {})

    limit = min(
        int(params.get("limit", 200)),
        200,
    )

    params["limit"] = limit

    all_rows = []

    for page in range(max_pages):
        params["offset"] = page * limit

        payload = api_get(
            path,
            params,
        )

        rows = extract_results(payload)

        if not rows:
            break

        all_rows.extend(rows)

        if len(rows) < limit:
            break

    return all_rows


# ============================================================
# NORMALIZATION
# ============================================================

def norm(value):
    if value is None:
        return ""

    value = str(value).lower().strip()

    table = str.maketrans({
        "á": "a",
        "à": "a",
        "ä": "a",
        "â": "a",
        "ã": "a",
        "é": "e",
        "è": "e",
        "ë": "e",
        "ê": "e",
        "í": "i",
        "ì": "i",
        "ï": "i",
        "î": "i",
        "ó": "o",
        "ò": "o",
        "ö": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
        "ù": "u",
        "ü": "u",
        "û": "u",
        "ñ": "n",
        "ç": "c",
        "ş": "s",
        "ğ": "g",
        "ı": "i",
    })

    return value.translate(table)


def team_key(name):
    return norm(name)


# ============================================================
# LEAGUES
# ============================================================

LEAGUE_ALIASES = {
    "premier league": "epl",
    "english premier league": "epl",

    "championship": "elc",

    "league one": "el1",
    "league one england": "el1",

    "la liga": "laliga",
    "laliga": "laliga",

    "la liga 2": "laliga2",
    "segunda division": "laliga2",

    "bundesliga": "bundesliga",

    "2 bundesliga": "bundesliga2",
    "2. bundesliga": "bundesliga2",

    "serie a": "seriea",
    "italy serie a": "seriea",

    "serie b": "serieb",

    "ligue 1": "ligue1",
    "france ligue 1": "ligue1",

    "ligue 2": "ligue2",

    "eredivisie": "eredivisie",

    "primeira liga": "primeira",
    "liga portugal": "primeira",

    "super lig": "superlig",
    "turkish super lig": "superlig",
    "turkiye super lig": "superlig",
    "trendyol super lig": "superlig",

    "jupiler pro league": "proleague",
    "belgian pro league": "proleague",

    "scottish premiership": "spl",
    "premiership": "spl",

    "greek super league": "slgreece",
    "super league greece": "slgreece",

    "swiss super league": "ssl",

    "danish superliga": "superliga",
    "superliga": "superliga",

    "allsvenskan": "allsvenskan",

    "eliteserien": "eliteserien",

    "ekstraklasa": "ekstraklasa",

    "liga i": "ligai",
    "romanian liga i": "ligai",

    "russian premier league": "rpl",

    "major league soccer": "mls",
    "mls": "mls",

    "liga mx": "ligamx",

    "brasileirao": "brasileirao",
    "brazilian serie a": "brasileirao",

    "j1 league": "j1",

    "saudi pro league": "splksa",

    "a league": "aleague",
    "a league men": "aleague",

    "uefa champions league": "ucl",
    "champions league": "ucl",

    "uefa europa league": "uel",
    "europa league": "uel",

    "uefa conference league": "uecl",
    "conference league": "uecl",

    "uefa nations league": "unl",
    "nations league": "unl",

    "fa cup": "facup",
    "copa del rey": "copa",
    "dfb pokal": "dfb",
    "coppa italia": "coppa",
}


def league_match(name):
    n = norm(name)

    if not n:
        return None

    if n in LEAGUE_ALIASES:
        return LEAGUE_ALIASES[n]

    for alias, key in LEAGUE_ALIASES.items():
        a = norm(alias)

        if n == a:
            return key

        if n.startswith(a + " "):
            return key

    return None


# ============================================================
# EVENT FIELDS
# ============================================================

def event_id(event):
    return (
        event.get("id")
        or event.get("event_id")
    )


def event_home(event):
    if isinstance(
        event.get("home_team"),
        dict,
    ):
        return event["home_team"].get("name")

    return (
        event.get("home_team_name")
        or event.get("home")
    )


def event_away(event):
    if isinstance(
        event.get("away_team"),
        dict,
    ):
        return event["away_team"].get("name")

    return (
        event.get("away_team_name")
        or event.get("away")
    )


def event_home_id(event):
    if isinstance(
        event.get("home_team"),
        dict,
    ):
        return event["home_team"].get("id")

    return event.get("home_team_id")


def event_away_id(event):
    if isinstance(
        event.get("away_team"),
        dict,
    ):
        return event["away_team"].get("id")

    return event.get("away_team_id")


def event_league(event):
    league = event.get("league")

    if isinstance(league, dict):
        return (
            league.get("name")
            or league.get("title")
            or ""
        )

    return (
        event.get("league_name")
        or event.get("competition_name")
        or ""
    )


def event_league_id(event):
    league = event.get("league")

    if isinstance(league, dict):
        return league.get("id")

    return event.get("league_id")


def event_date(event):
    return (
        event.get("kickoff")
        or event.get("date")
        or event.get("start_time")
        or event.get("datetime")
    )


def score(event, side):
    key = (
        "home_score"
        if side == "home"
        else "away_score"
    )

    value = event.get(key)

    if value is None:
        scores = event.get("score")

        if isinstance(scores, dict):
            value = scores.get(side)

    try:
        if value is None:
            return None

        return int(value)

    except Exception:
        return None


def normalize_event(event):
    home = event_home(event)
    away = event_away(event)

    if not home or not away:
        return None

    return {
        "id": event_id(event),
        "home": str(home),
        "away": str(away),
        "home_id": event_home_id(event),
        "away_id": event_away_id(event),
        "league_id": event_league_id(event),
        "league_name": event_league(event),
        "league": league_match(
            event_league(event)
        ),
        "date": event_date(event),
        "status": event.get("status"),
        "home_score": score(
            event,
            "home",
        ),
        "away_score": score(
            event,
            "away",
        ),
        "raw": event,
    }


# ============================================================
# LEAGUE DISCOVERY
# ============================================================

def load_leagues():
    rows = fetch_all(
        "/leagues/",
        {
            "limit": 200,
        },
    )

    result = []

    for row in rows:
        name = (
            row.get("name")
            or row.get("title")
            or ""
        )

        key = league_match(name)

        if not key:
            continue

        result.append({
            "id": row.get("id"),
            "name": name,
            "key": key,
            "country": row.get(
                "country"
            ),
        })

    return result


def current_season(league_id):
    payload = api_get(
        f"/leagues/{league_id}/season/"
    )

    if isinstance(payload, dict):
        if "id" in payload:
            return payload

        data = payload.get("data")

        if isinstance(data, dict):
            return data

    return None


def seasons(league_id):
    payload = api_get(
        f"/leagues/{league_id}/seasons/"
    )

    rows = extract_results(payload)

    if isinstance(payload, list):
        rows = payload

    return rows


# ============================================================
# REAL HISTORICAL DATA
# ============================================================

def load_history():
    leagues = load_leagues()

    history = []

    for league in leagues:

        lid = league["id"]

        try:
            season_rows = seasons(lid)

        except Exception:
            continue

        season_rows = [
            x for x in season_rows
            if isinstance(x, dict)
        ]

        season_rows.sort(
            key=lambda x: (
                x.get("year")
                or 0
            ),
            reverse=True,
        )

        season_rows = season_rows[
            :HISTORY_SEASONS
        ]

        for season in season_rows:

            sid = season.get("id")

            if sid is None:
                continue

            try:
                events = fetch_all(
                    "/events/",
                    {
                        "league_id": lid,
                        "season_id": sid,
                        "status": "finished",
                        "limit": 200,
                    },
                )

            except Exception:
                continue

            for raw in events:

                event = normalize_event(
                    raw
                )

                if not event:
                    continue

                hg = event["home_score"]
                ag = event["away_score"]

                if hg is None or ag is None:
                    continue

                if hg < 0 or ag < 0:
                    continue

                history.append({
                    "event_id": event["id"],
                    "date": event["date"],
                    "league_id": lid,
                    "league": league["key"],
                    "home": event["home"],
                    "away": event["away"],
                    "home_id": event["home_id"],
                    "away_id": event["away_id"],
                    "hg": hg,
                    "ag": ag,
                })

    unique = {}

    for row in history:
        if row["event_id"] is not None:
            unique[
                str(row["event_id"])
            ] = row

    history = list(
        unique.values()
    )

    history.sort(
        key=lambda x: (
            x["date"] or ""
        )
    )

    return history


# ============================================================
# UPCOMING REAL FIXTURES
# ============================================================

def load_upcoming():
    now = datetime.now(
        timezone.utc
    )

    end = now + timedelta(
        days=2
    )

    events = fetch_all(
        "/events/",
        {
            "date_from":
                now.strftime("%Y-%m-%d"),
            "date_to":
                end.strftime("%Y-%m-%d"),
            "status": "upcoming",
            "limit": 200,
        },
    )

    result = []

    for raw in events:

        event = normalize_event(
            raw
        )

        if not event:
            continue

        if not event["league"]:
            continue

        result.append(event)

    result.sort(
        key=lambda x: (
            x["date"] or ""
        )
    )

    unique = {}

    for item in result:
        if item["id"] is not None:
            unique[
                str(item["id"])
            ] = item

    return list(
        unique.values()
    )


# ============================================================
# LIVE
# ============================================================

def load_live():
    payload = api_get(
        "/events/live/"
    )

    rows = extract_results(
        payload
    )

    result = []

    for raw in rows:

        event = normalize_event(
            raw
        )

        if event:
            result.append(event)

    return result


# ============================================================
# ODDS
# ============================================================

def load_event_odds(event_id):
    payload = api_get(
        f"/events/{event_id}/odds/"
    )

    return payload


def number(value):
    try:
        value = float(value)

    except Exception:
        return None

    if not math.isfinite(value):
        return None

    if value < 1.01:
        return None

    if value > 1000:
        return None

    return value


def odds_rows(payload):
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in (
        "results",
        "data",
        "odds",
    ):
        value = payload.get(key)

        if isinstance(value, list):
            return value

    return []


def parse_odds(payload):
    rows = odds_rows(payload)

    result = {
        "home": None,
        "draw": None,
        "away": None,
        "over25": None,
        "under25": None,
        "bttsYes": None,
        "bttsNo": None,
    }

    for row in rows:

        if not isinstance(row, dict):
            continue

        market = str(
            row.get("market")
            or ""
        ).lower()

        outcome = str(
            row.get("outcome")
            or ""
        )

        value = number(
            row.get(
                "decimal_odds"
            )
        )

        if value is None:
            value = number(
                row.get("odds")
            )

        if value is None:
            continue

        if market == "1x2":

            if outcome == "HOME":
                result["home"] = max(
                    result["home"] or 0,
                    value,
                )

            elif outcome == "DRAW":
                result["draw"] = max(
                    result["draw"] or 0,
                    value,
                )

            elif outcome == "AWAY":
                result["away"] = max(
                    result["away"] or 0,
                    value,
                )

        elif market == "over_under_25":

            if outcome == "over":
                result["over25"] = max(
                    result["over25"] or 0,
                    value,
                )

            elif outcome == "under":
                result["under25"] = max(
                    result["under25"] or 0,
                    value,
                )

        elif market == "btts":

            if outcome == "yes":
                result["bttsYes"] = max(
                    result["bttsYes"] or 0,
                    value,
                )

            elif outcome == "no":
                result["bttsNo"] = max(
                    result["bttsNo"] or 0,
                    value,
                )

    return result


# ============================================================
# TEAM STATE
# ============================================================

def empty_team():
    return {
        "elo": 1500.0,
        "home_elo": 1500.0,
        "away_elo": 1500.0,

        "gf": deque(maxlen=10),
        "ga": deque(maxlen=10),

        "home_gf": deque(maxlen=10),
        "home_ga": deque(maxlen=10),

        "away_gf": deque(maxlen=10),
        "away_ga": deque(maxlen=10),

        "results": deque(maxlen=10),

        "games": 0,
    }


def team_stats():
    return defaultdict(
        empty_team
    )


def avg(values, fallback):
    if not values:
        return fallback

    return float(
        sum(values) / len(values)
    )


# ============================================================
# ELO
# ============================================================

ELO_K = 20.0
HOME_ADVANTAGE = 55.0


def elo_probability(
    home_elo,
    away_elo,
):
    diff = (
        home_elo
        + HOME_ADVANTAGE
        - away_elo
    )

    return 1.0 / (
        1.0
        + 10.0 ** (-diff / 400.0)
    )


# ============================================================
# MODEL TRAINING
# ============================================================

def train_state(history):
    teams = team_stats()

    for row in history:

        h = team_key(
            row["home"]
        )

        a = team_key(
            row["away"]
        )

        hg = float(row["hg"])
        ag = float(row["ag"])

        H = teams[h]
        A = teams[a]

        expected = elo_probability(
            H["elo"],
            A["elo"],
        )

        actual = (
            1.0
            if hg > ag
            else 0.5
            if hg == ag
            else 0.0
        )

        change = (
            ELO_K
            * (
                actual
                - expected
            )
        )

        H["elo"] += change
        A["elo"] -= change

        H["home_elo"] += change
        A["away_elo"] -= change

        H["gf"].append(hg)
        H["ga"].append(ag)

        A["gf"].append(ag)
        A["ga"].append(hg)

        H["home_gf"].append(hg)
        H["home_ga"].append(ag)

        A["away_gf"].append(ag)
        A["away_ga"].append(hg)

        H["results"].append(
            actual
        )

        A["results"].append(
            1.0
            if ag > hg
            else 0.5
            if hg == ag
            else 0.0
        )

        H["games"] += 1
        A["games"] += 1

    return teams


# ============================================================
# DIXON-COLES
# ============================================================

def poisson(k, lam):
    if lam <= 0:
        return 0.0

    return (
        math.exp(-lam)
        * lam ** k
        / math.factorial(k)
    )


def dc_tau(
    home_goals,
    away_goals,
    lh,
    la,
    rho=-0.08,
):

    if (
        home_goals == 0
        and away_goals == 0
    ):
        return (
            1
            - lh * la * rho
        )

    if (
        home_goals == 0
        and away_goals == 1
    ):
        return (
            1
            + lh * rho
        )

    if (
        home_goals == 1
        and away_goals == 0
    ):
        return (
            1
            + la * rho
        )

    if (
        home_goals == 1
        and away_goals == 1
    ):
        return 1 - rho

    return 1.0


def matrix(
    lambda_home,
    lambda_away,
):

    m = np.zeros(
        (
            MAX_GOALS + 1,
            MAX_GOALS + 1,
        )
    )

    for h in range(
        MAX_GOALS + 1
    ):
        for a in range(
            MAX_GOALS + 1
        ):

            m[h, a] = (
                poisson(
                    h,
                    lambda_home,
                )
                * poisson(
                    a,
                    lambda_away,
                )
                * dc_tau(
                    h,
                    a,
                    lambda_home,
                    lambda_away,
                )
            )

    total = m.sum()

    if total > 0:
        m /= total

    return m


def market_probabilities(m):

    home = 0.0
    draw = 0.0
    away = 0.0

    over25 = 0.0
    under25 = 0.0

    btts_yes = 0.0

    for h in range(
        MAX_GOALS + 1
    ):
        for a in range(
            MAX_GOALS + 1
        ):

            p = float(
                m[h, a]
            )

            if h > a:
                home += p

            elif h == a:
                draw += p

            else:
                away += p

            if h + a > 2:
                over25 += p

            else:
                under25 += p

            if h > 0 and a > 0:
                btts_yes += p

    return {
        "home": home,
        "draw": draw,
        "away": away,
        "over25": over25,
        "under25": under25,
        "bttsYes": btts_yes,
        "bttsNo": 1.0 - btts_yes,
    }


# ============================================================
# KALE PREDICTION
# ============================================================

def predict_fixture(
    fixture,
    teams,
):

    hkey = team_key(
        fixture["home"]
    )

    akey = team_key(
        fixture["away"]
    )

    H = teams.get(hkey)
    A = teams.get(akey)

    if H is None or A is None:
        return {
            "available": False,
            "reason": "insufficient_team_history",
        }

    if (
        H["games"] < MIN_HISTORY
        or A["games"] < MIN_HISTORY
    ):
        return {
            "available": False,
            "reason": "insufficient_team_history",
        }

    home_attack = avg(
        H["home_gf"],
        avg(H["gf"], 1.25),
    )

    home_defense = avg(
        H["home_ga"],
        avg(H["ga"], 1.25),
    )

    away_attack = avg(
        A["away_gf"],
        avg(A["gf"], 1.10),
    )

    away_defense = avg(
        A["away_ga"],
        avg(A["ga"], 1.25),
    )

    league_home = (
        avg(H["gf"], 1.35)
        + avg(A["ga"], 1.25)
    ) / 2.0

    league_away = (
        avg(A["gf"], 1.10)
        + avg(H["ga"], 1.25)
    ) / 2.0

    form_h = avg(
        H["results"],
        0.5,
    )

    form_a = avg(
        A["results"],
        0.5,
    )

    form_delta = (
        form_h - form_a
    )

    elo_p = elo_probability(
        H["elo"],
        A["elo"],
    )

    elo_home_multiplier = (
        0.85
        + 0.30 * elo_p
    )

    elo_away_multiplier = (
        1.05
        - 0.25 * elo_p
    )

    lambda_home = (
        0.45 * home_attack
        + 0.25 * away_defense
        + 0.30 * league_home
    )

    lambda_away = (
        0.45 * away_attack
        + 0.25 * home_defense
        + 0.30 * league_away
    )

    lambda_home *= (
        elo_home_multiplier
        * (
            1
            + 0.18 * form_delta
        )
    )

    lambda_away *= (
        elo_away_multiplier
        * (
            1
            - 0.18 * form_delta
        )
    )

    lambda_home = max(
        0.20,
        min(
            4.5,
            lambda_home,
        ),
    )

    lambda_away = max(
        0.20,
        min(
            4.5,
            lambda_away,
        ),
    )

    m = matrix(
        lambda_home,
        lambda_away,
    )

    probs = market_probabilities(
        m
    )

    score_index = np.unravel_index(
        np.argmax(m),
        m.shape,
    )

    one_x_two = max(
        probs["home"],
        probs["draw"],
        probs["away"],
    )

    confidence = (
        0.60 * one_x_two
        + 0.20 * (
            1
            - abs(
                probs["over25"]
                - 0.5
            )
        )
        + 0.20 * min(
            1.0,
            (
                H["games"]
                + A["games"]
            ) / 80.0,
        )
    )

    return {
        "available": True,

        "lambda_home":
            round(
                lambda_home,
                4,
            ),

        "lambda_away":
            round(
                lambda_away,
                4,
            ),

        "most_likely":
            f"{score_index[0]}-{score_index[1]}",

        "probabilities": {
            k: round(
                float(v),
                6,
            )
            for k, v in probs.items()
        },

        "confidence":
            round(
                float(confidence),
                6,
            ),

        "history": {
            "home_games":
                H["games"],
            "away_games":
                A["games"],
        },
    }


# ============================================================
# VALUE
# ============================================================

def calculate_value(
    probability,
    odds,
):
    if (
        probability is None
        or odds is None
        or odds <= 1
    ):
        return None

    return (
        probability
        * odds
        - 1.0
    )


def attach_value(
    prediction,
    odds,
):

    if not prediction.get(
        "available"
    ):
        return prediction

    probs = prediction[
        "probabilities"
    ]

    mappings = {
        "home": "home",
        "draw": "draw",
        "away": "away",
        "over25": "over25",
        "under25": "under25",
        "bttsYes": "bttsYes",
        "bttsNo": "bttsNo",
    }

    values = []

    for market, prob_key in mappings.items():

        odd = odds.get(market)

        if odd is None:
            continue

        probability = probs.get(
            prob_key
        )

        edge = calculate_value(
            probability,
            odd,
        )

        if edge is None:
            continue

        values.append({
            "market": market,
            "probability":
                probability,
            "odds": odd,
            "edge":
                round(
                    edge,
                    6,
                ),
        })

    values.sort(
        key=lambda x: x["edge"],
        reverse=True,
    )

    prediction["value"] = values

    prediction["qualified"] = [
        x for x in values
        if (
            x["edge"] >= MIN_EDGE
            and prediction[
                "confidence"
            ] >= MIN_CONFIDENCE
        )
    ]

    return prediction


# ============================================================
# WALK FORWARD
# ============================================================

def walk_forward(history):

    if len(history) < 100:
        return {
            "available": False,
            "reason":
                "not_enough_historical_matches",
            "matches":
                len(history),
        }

    start = max(
        80,
        int(
            len(history) * 0.70
        ),
    )

    evaluated = 0
    correct_1x2 = 0

    brier = []

    for i in range(
        start,
        len(history),
    ):

        training = history[:i]

        state = train_state(
            training
        )

        actual = history[i]

        fixture = {
            "home":
                actual["home"],
            "away":
                actual["away"],
        }

        pred = predict_fixture(
            fixture,
            state,
        )

        if not pred.get(
            "available"
        ):
            continue

        p = pred[
            "probabilities"
        ]

        hg = actual["hg"]
        ag = actual["ag"]

        if hg > ag:
            actual_market = "home"
        elif hg == ag:
            actual_market = "draw"
        else:
            actual_market = "away"

        predicted_market = max(
            (
                "home",
                "draw",
                "away",
            ),
            key=lambda x: p[x],
        )

        evaluated += 1

        if (
            predicted_market
            == actual_market
        ):
            correct_1x2 += 1

        target = {
            "home": 1.0
                if actual_market == "home"
                else 0.0,

            "draw": 1.0
                if actual_market == "draw"
                else 0.0,

            "away": 1.0
                if actual_market == "away"
                else 0.0,
        }

        brier.append(
            (
                (p["home"] - target["home"])
                ** 2
                + (
                    p["draw"]
                    - target["draw"]
                ) ** 2
                + (
                    p["away"]
                    - target["away"]
                ) ** 2
            ) / 3.0
        )

    if evaluated == 0:
        return {
            "available": False,
            "reason": "no_valid_evaluations",
        }

    return {
        "available": True,
        "matches": evaluated,
        "accuracy_1x2":
            round(
                correct_1x2
                / evaluated,
                6,
            ),
        "brier_1x2":
            round(
                statistics.mean(
                    brier
                ),
                6,
            ),
    }


# ============================================================
# ENGINE
# ============================================================

def run_engine():

    history = load_history()

    if not history:
        raise RuntimeError(
            "GOALDIR returned no real historical matches."
        )

    state = train_state(
        history
    )

    fixtures = load_upcoming()

    output = []

    for fixture in fixtures:

        try:
            prediction = predict_fixture(
                fixture,
                state,
            )

            if prediction.get(
                "available"
            ):

                try:
                    odds_payload = (
                        load_event_odds(
                            fixture["id"]
                        )
                    )

                    odds = parse_odds(
                        odds_payload
                    )

                except Exception:
                    odds = {}

                prediction = attach_value(
                    prediction,
                    odds,
                )

                fixture["odds"] = odds

            fixture["prediction"] = (
                prediction
            )

            output.append(
                fixture
            )

        except Exception as exc:

            fixture["prediction"] = {
                "available": False,
                "reason":
                    f"prediction_error:{exc}",
            }

            output.append(
                fixture
            )

    validation = walk_forward(
        history
    )

    return {
        "generated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "source":
            "GOALDIR/BSD Football API v2",

        "prediction_engine":
            "KALE",

        "goal_api_predictions_used":
            False,

        "historical_matches":
            len(history),

        "upcoming_matches":
            len(output),

        "validation":
            validation,

        "fixtures":
            output,
    }


# ============================================================
# ROUTES
# ============================================================

@app.get("/api/health")
def health():

    return jsonify({
        "ok": True,
        "api":
            "GOALDIR/BSD v2",
        "base":
            API_BASE,
        "api_key_configured":
            bool(API_KEY),
        "prediction_engine":
            "KALE",
        "external_predictions":
            False,
    })


@app.get("/api/run")
def api_run():

    try:
        result = run_engine()

        return jsonify({
            "ok": True,
            **result,
        })

    except Exception as exc:

        return jsonify({
            "ok": False,
            "error":
                str(exc),
        }), 500


@app.get("/api/live")
def api_live():

    try:

        live = load_live()

        return jsonify({
            "ok": True,
            "source":
                "GOALDIR/BSD v2",
            "matches":
                live,
        })

    except Exception as exc:

        return jsonify({
            "ok": False,
            "error":
                str(exc),
        }), 500


@app.get("/api/validate")
def api_validate():

    try:

        history = load_history()

        result = walk_forward(
            history
        )

        return jsonify({
            "ok": True,
            "source":
                "real GOALDIR historical data",
            "validation":
                result,
        })

    except Exception as exc:

        return jsonify({
            "ok": False,
            "error":
                str(exc),
        }), 500


# ============================================================
# FRONTEND
# ============================================================

@app.get("/")
def index():

    return """
<!doctype html>
<html lang="en">

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<title>KALE — Live Value Engine</title>

<style>

:root{
    --bg:#0a0c10;
    --surface:#12151c;
    --border:#252b35;
    --text:#edf1f7;
    --muted:#8993a3;
    --good:#7ee787;
    --bad:#ff7b72;
    --accent:#58a6ff;
}

*{
    box-sizing:border-box;
}

body{
    margin:0;
    background:var(--bg);
    color:var(--text);
    font-family:
        Arial,
        Helvetica,
        sans-serif;
}

header{
    position:sticky;
    top:0;
    z-index:10;
    padding:18px;
    background:rgba(10,12,16,.97);
    border-bottom:1px solid var(--border);
}

h1{
    margin:0;
    font-size:22px;
}

.subtitle{
    margin-top:6px;
    color:var(--muted);
    font-size:12px;
}

.controls{
    display:flex;
    gap:8px;
    margin-top:14px;
}

button{
    border:1px solid var(--border);
    border-radius:8px;
    padding:10px 14px;
    background:#171c24;
    color:white;
    cursor:pointer;
}

button:hover{
    background:#202631;
}

#status{
    padding:14px 16px;
    color:var(--muted);
    font-size:13px;
}

#app{
    padding:0 14px 30px;
    display:grid;
    gap:12px;
}

.card{
    background:var(--surface);
    border:1px solid var(--border);
    border-radius:12px;
    padding:14px;
}

.league{
    color:var(--muted);
    font-size:11px;
    margin-bottom:8px;
}

.match{
    font-weight:700;
    font-size:16px;
}

.date{
    color:var(--muted);
    font-size:11px;
    margin-top:5px;
}

.section{
    border-top:1px solid var(--border);
    margin-top:12px;
    padding-top:12px;
}

.row{
    display:flex;
    justify-content:space-between;
    gap:12px;
    margin:6px 0;
    font-size:13px;
}

.good{
    color:var(--good);
}

.muted{
    color:var(--muted);
}

.error{
    color:var(--bad);
}

.badge{
    display:inline-block;
    margin-top:8px;
    padding:4px 7px;
    border-radius:6px;
    border:1px solid var(--border);
    color:var(--muted);
    font-size:10px;
}

.value{
    margin-top:12px;
}

.validation{
    margin:14px;
    padding:12px;
    background:var(--surface);
    border:1px solid var(--border);
    border-radius:10px;
}

</style>

</head>

<body>

<header>

<h1>KALE — Live Value Engine</h1>

<div class="subtitle">
Real GOALDIR/BSD data ·
KALE Dixon-Coles + Elo + Form
</div>

<div class="controls">

<button onclick="runEngine()">
RUN ENGINE
</button>

<button onclick="loadLive()">
LIVE
</button>

<button onclick="validate()">
VALIDATE
</button>

</div>

</header>

<div id="status">
Ready.
</div>

<div id="app"></div>

<script>

const app =
    document.getElementById("app");

const status =
    document.getElementById("status");


function esc(value){

    return String(value ?? "")
        .replaceAll("&","&amp;")
        .replaceAll("<","&lt;")
        .replaceAll(">","&gt;")
        .replaceAll('"',"&quot;")
        .replaceAll("'","&#039;");
}


function pct(value){

    return (
        Number(value || 0)
        * 100
    ).toFixed(1) + "%";
}


async function runEngine(){

    app.innerHTML = "";

    status.textContent =
        "Loading real GOALDIR data and training KALE...";

    try{

        const response =
            await fetch("/api/run");

        const data =
            await response.json();

        if(!data.ok){
            throw new Error(
                data.error
            );
        }

        renderValidation(
            data.validation
        );

        renderFixtures(
            data.fixtures
        );

        status.textContent =
            `${data.upcoming_matches} real upcoming matches · `
            + `${data.historical_matches} real historical matches`;

    }catch(error){

        status.innerHTML =
            `<span class="error">${
                esc(error.message)
            }</span>`;
    }
}


async function loadLive(){

    app.innerHTML = "";

    status.textContent =
        "Loading real live GOALDIR data...";

    try{

        const response =
            await fetch("/api/live");

        const data =
            await response.json();

        if(!data.ok){
            throw new Error(
                data.error
            );
        }

        status.textContent =
            `${data.matches.length} live matches`;

        for(
            const match
            of data.matches
        ){

            const card =
                document.createElement(
                    "div"
                );

            card.className =
                "card";

            card.innerHTML = `

                <div class="league">
                    ${esc(
                        match.league_name
                    )}
                </div>

                <div class="match">
                    ${esc(
                        match.home
                    )}
                    vs
                    ${esc(
                        match.away
                    )}
                </div>

                <div class="row section">
                    <span>
                        Score
                    </span>

                    <strong>
                        ${
                            match.home_score
                            ?? "-"
                        }
                        -
                        ${
                            match.away_score
                            ?? "-"
                        }
                    </strong>
                </div>

                <div class="badge">
                    GOALDIR LIVE
                </div>
            `;

            app.appendChild(
                card
            );
        }

    }catch(error){

        status.innerHTML =
            `<span class="error">${
                esc(error.message)
            }</span>`;
    }
}


function renderValidation(
    validation
){

    if(
        !validation
        || !validation.available
    ){
        return;
    }

    const box =
        document.createElement(
            "div"
        );

    box.className =
        "validation";

    box.innerHTML = `

        <strong>
            KALE walk-forward validation
        </strong>

        <div class="row">
            <span>
                Evaluated matches
            </span>

            <span>
                ${
                    validation.matches
                }
            </span>
        </div>

        <div class="row">
            <span>
                1X2 accuracy
            </span>

            <span>
                ${
                    (
                        Number(
                            validation.accuracy_1x2
                        ) * 100
                    ).toFixed(2)
                }%
            </span>
        </div>

        <div class="row">
            <span>
                Brier score
            </span>

            <span>
                ${
                    Number(
                        validation.brier_1x2
                    ).toFixed(4)
                }
            </span>
        </div>

    `;

    app.appendChild(
        box
    );
}


function renderFixtures(
    fixtures
){

    for(
        const fixture
        of fixtures
    ){

        const p =
            fixture.prediction;

        const card =
            document.createElement(
                "div"
            );

        card.className =
            "card";

        if(
            !p
            || !p.available
        ){

            card.innerHTML = `

                <div class="league">
                    ${esc(
                        fixture.league_name
                    )}
                </div>

                <div class="match">
                    ${esc(
                        fixture.home
                    )}
                    vs
                    ${esc(
                        fixture.away
                    )}
                </div>

                <div class="muted section">
                    Prediction withheld:
                    ${
                        esc(
                            p?.reason
                            || "insufficient evidence"
                        )
                    }
                </div>

            `;

            app.appendChild(
                card
            );

            continue;
        }

        const probs =
            p.probabilities || {};

        let values = "";

        for(
            const v
            of (
                p.qualified
                || []
            )
        ){

            values += `

                <div class="row">

                    <span>
                        ${esc(
                            v.market
                        )}
                    </span>

                    <span class="good">

                        ${Number(
                            v.odds
                        ).toFixed(2)}

                        ·

                        ${pct(
                            v.probability
                        )}

                        ·

                        ${pct(
                            v.edge
                        )}

                    </span>

                </div>

            `;
        }

        card.innerHTML = `

            <div class="league">
                ${esc(
                    fixture.league_name
                )}
            </div>

            <div class="match">
                ${esc(
                    fixture.home
                )}
                vs
                ${esc(
                    fixture.away
                )}
            </div>

            <div class="date">
                ${esc(
                    fixture.date
                )}
            </div>

            <div class="section">

                <div class="row">
                    <span>
                        KALE most likely score
                    </span>

                    <strong>
                        ${esc(
                            p.most_likely
                        )}
                    </strong>
                </div>

                <div class="row">
                    <span>
                        Home λ
                    </span>

                    <span>
                        ${Number(
                            p.lambda_home
                        ).toFixed(2)}
                    </span>
                </div>

                <div class="row">
                    <span>
                        Away λ
                    </span>

                    <span>
                        ${Number(
                            p.lambda_away
                        ).toFixed(2)}
                    </span>
                </div>

                <div class="row">
                    <span>
                        1
                    </span>

                    <span>
                        ${pct(
                            probs.home
                        )}
                    </span>
                </div>

                <div class="row">
                    <span>
                        X
                    </span>

                    <span>
                        ${pct(
                            probs.draw
                        )}
                    </span>
                </div>

                <div class="row">
                    <span>
                        2
                    </span>

                    <span>
                        ${pct(
                            probs.away
                        )}
                    </span>
                </div>

                <div class="row">
                    <span>
                        Over 2.5
                    </span>

                    <span>
                        ${pct(
                            probs.over25
                        )}
                    </span>
                </div>

                <div class="row">
                    <span>
                        Under 2.5
                    </span>

                    <span>
                        ${pct(
                            probs.under25
                        )}
                    </span>
                </div>

                <div class="row">
                    <span>
                        BTTS Yes
                    </span>

                    <span>
                        ${pct(
                            probs.bttsYes
                        )}
                    </span>
                </div>

                <div class="row">
                    <span>
                        Model confidence
                    </span>

                    <span>
                        ${pct(
                            p.confidence
                        )}
                    </span>
                </div>

            </div>

            <div class="value section">

                ${
                    values
                    ? values
                    : `
                        <span class="muted">
                            No verified value edge.
                        </span>
                    `
                }

            </div>

            <div class="badge">
                Prediction:
                KALE
            </div>

            <div class="badge">
                Data:
                GOALDIR
            </div>

        `;

        app.appendChild(
            card
        );
    }
}


async function validate(){

    status.textContent =
        "Running real historical walk-forward validation...";

    try{

        const response =
            await fetch(
                "/api/validate"
            );

        const data =
            await response.json();

        if(!data.ok){
            throw new Error(
                data.error
            );
        }

        app.innerHTML = "";

        renderValidation(
            data.validation
        );

        status.textContent =
            "Validation completed using real historical GOALDIR data.";

    }catch(error){

        status.innerHTML =
            `<span class="error">${
                esc(error.message)
            }</span>`;
    }
}


runEngine();

setInterval(
    runEngine,
    10 * 60 * 1000
);

</script>

</body>

</html>
"""


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    if not API_KEY:
        print(
            "ERROR: GOALDIR_API_KEY is not set."
        )

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
    )
