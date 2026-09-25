from __future__ import annotations
import math
import json
import os
import statistics
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import numpy as np
from curl_cffi import requests
from flask import Flask, jsonify
from flask_cors import CORS
import sys

# ============================================================
# CONFIG
# ============================================================
API_BASE = "https://sports.bzzoiro.com/api/v2"
API_KEY = (
    os.getenv("GOALDIR_API_KEY") or os.getenv("BSD_API_KEY") or ""
).strip()
PORT = int(os.getenv("PORT", "5000"))
HISTORY_SEASONS = int(os.getenv("HISTORY_SEASONS", "3"))
MIN_HISTORY = int(os.getenv("MIN_HISTORY", "8"))
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.55"))
MIN_EDGE = float(os.getenv("MIN_EDGE", "0.025"))
MAX_GOALS = 8

SESSION = requests.Session()
if API_KEY:
    SESSION.headers.update({
        "Authorization": f"Token {API_KEY}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

app = Flask(__name__)
CORS(app)

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
# HTTP & CLOUDFLARE BYPASS
# ============================================================
def api_get(path, params=None):
    if not API_KEY:
        raise RuntimeError("GOALDIR/BSD API_KEY is missing.")
    params = dict(params or {})
    key = path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
    cached = cache_get(key)
    if cached is not None:
        return cached

    url = API_BASE.rstrip("/") + "/" + path.lstrip("/")
    response = SESSION.get(
        url,
        params=params,
        impersonate="chrome120",
        timeout=30,
    )
    if response.status_code in (401, 403):
        raise RuntimeError(f"BSD API auth/access error ({response.status_code}).")
    if response.status_code == 429:
        raise RuntimeError("BSD API rate limit reached (429).")
    response.raise_for_status()
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"BSD returned invalid JSON for {path}.") from exc
    cache_put(key, data)
    return data

def extract_results(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("results", "data", "events", "fixtures", "items", "seasons"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []

def fetch_all(path, params=None, max_pages=100):
    base_params = dict(params or {})
    limit = min(int(base_params.get("limit", 200)), 200)
    base_params["limit"] = limit
    all_rows = []
    for page in range(max_pages):
        page_params = dict(base_params)
        page_params["offset"] = page * limit
        payload = api_get(path, page_params)
        rows = extract_results(payload)
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < limit:
            break
    return all_rows

# ============================================================
# NORMALIZATION & PARSING
# ============================================================
def norm(value):
    if value is None:
        return ""
    value = str(value).lower().strip()
    table = str.maketrans({
        "á": "a", "à": "a", "ä": "a", "â": "a", "ã": "a",
        "é": "e", "è": "e", "ë": "e", "ê": "e",
        "í": "i", "ì": "i", "ï": "i", "î": "i",
        "ó": "o", "ò": "o", "ö": "o", "ô": "o", "õ": "o",
        "ú": "u", "ù": "u", "ü": "u", "û": "u",
        "ñ": "n", "ç": "c", "ş": "s", "ğ": "g", "ı": "i",
    })
    value = value.translate(table)
    for char in ("-", "_", "/", ".", ",", ":", "(", ")"):
        value = value.replace(char, " ")
    return " ".join(value.split())

def team_ref(team_id, name):
    if team_id is not None:
        return f"id:{team_id}"
    return f"name:{norm(name)}"

LEAGUE_ALIASES = {
    "premier league": "epl", "championship": "elc", "la liga": "laliga",
    "bundesliga": "bundesliga", "serie a": "seriea", "ligue 1": "ligue1",
    "eredivisie": "eredivisie", "primeira liga": "primeira", "super lig": "superlig",
    "uefa champions league": "ucl", "europa league": "uel"
}

def league_match(name):
    n = norm(name)
    return LEAGUE_ALIASES.get(n) or next((k for alias, k in LEAGUE_ALIASES.items() if n.startswith(alias)), "other")

def event_home(event):
    home = event.get("home") or event.get("home_team")
    if isinstance(home, dict):
        return home.get("name") or home.get("short_name")
    return event.get("home_team_name") or home

def event_away(event):
    away = event.get("away") or event.get("away_team")
    if isinstance(away, dict):
        return away.get("name") or away.get("short_name")
    return event.get("away_team_name") or away

def score(event, side):
    key = "home_score" if side == "home" else "away_score"
    val = event.get(key)
    if val is None:
        scores = event.get("score") or event.get("scores")
        if isinstance(scores, dict):
            val = scores.get(side) or scores.get("home" if side == "home" else "away")
    if isinstance(val, dict):
        val = val.get("current") or val.get("display") or val.get("score")
    try:
        return int(val) if val is not None and int(val) >= 0 else None
    except (TypeError, ValueError):
        return None

def normalize_event(event):
    if not isinstance(event, dict):
        return None
    home, away = event_home(event), event_away(event)
    if not home or not away:
        return None
    league_name = event.get("league_name") or (event.get("league") if isinstance(event.get("league"), str) else event.get("league", {}).get("name", ""))
    return {
        "id": event.get("id") or event.get("event_id"),
        "home": str(home),
        "away": str(away),
        "home_id": event.get("home_id") or event.get("home_team_id"),
        "away_id": event.get("away_id") or event.get("away_team_id"),
        "league_name": league_name,
        "league": league_match(league_name),
        "date": event.get("kickoff") or event.get("start_time") or event.get("date"),
        "status": event.get("status"),
        "home_score": score(event, "home"),
        "away_score": score(event, "away"),
    }

# ============================================================
# DATA LOADING (HISTORY & UPCOMING)
# ============================================================
def load_leagues():
    rows = fetch_all("/leagues/", {"limit": 200})
    result = []
    for row in rows:
        if not isinstance(row, dict): continue
        name = row.get("name") or row.get("title") or ""
        lid = row.get("id")
        if lid is not None:
            result.append({"id": lid, "name": name, "key": league_match(name)})
    return result

def load_history():
    leagues = load_leagues()
    history = []
    for league in leagues:
        lid = league["id"]
        try:
            seasons_payload = api_get(f"/leagues/{lid}/seasons/")
            s_rows = extract_results(seasons_payload)
            s_rows.sort(key=lambda x: x.get("year", 0), reverse=True)
            for season in s_rows[:HISTORY_SEASONS]:
                sid = season.get("id")
                if sid is None: continue
                events = fetch_all("/events/", {"league_id": lid, "season_id": sid, "status": "finished", "limit": 200})
                for raw in events:
                    ev = normalize_event(raw)
                    if ev and ev["home_score"] is not None and ev["away_score"] is not None:
                        history.append({
                            "event_id": ev["id"], "date": ev["date"], "home": ev["home"], "away": ev["away"],
                            "home_id": ev["home_id"], "away_id": ev["away_id"], "hg": ev["home_score"], "ag": ev["away_score"]
                        })
        except Exception:
            continue
    history.sort(key=lambda x: x["date"] or "")
    return history

def load_upcoming():
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=2)
    events = fetch_all("/events/", {
        "date_from": now.strftime("%Y-%m-%d"),
        "date_to": end.strftime("%Y-%m-%d"),
        "status": "upcoming",
        "limit": 200,
    })
    return [normalize_event(r) for r in events if normalize_event(r)]

def parse_odds(payload):
    res = {"home": None, "draw": None, "away": None, "over25": None, "under25": None, "bttsYes": None, "bttsNo": None}
    if not isinstance(payload, dict): return res
    odds = payload.get("odds", {})
    if not isinstance(odds, dict): return res
    for k, ak in [("home_win", "home"), ("draw", "draw"), ("away_win", "away"), ("over_25_goals", "over25"), ("under_25_goals", "under25"), ("btts_yes", "bttsYes"), ("btts_no", "bttsNo")]:
        try:
            val = float(odds.get(k))
            if 1.01 <= val <= 1000: res[ak] = val
        except (TypeError, ValueError): pass
    return res

# ============================================================
# KALE MODEL (ELO + DIXON-COLES)
# ============================================================
def train_state(history):
    teams = defaultdict(lambda: {
        "elo": 1500.0, "gf": deque(maxlen=10), "ga": deque(maxlen=10),
        "home_gf": deque(maxlen=10), "home_ga": deque(maxlen=10),
        "away_gf": deque(maxlen=10), "away_ga": deque(maxlen=10),
        "results": deque(maxlen=10), "games": 0
    })
    for row in history:
        h, a = team_ref(row.get("home_id"), row["home"]), team_ref(row.get("away_id"), row["away"])
        hg, ag = float(row["hg"]), float(row["ag"])
        H, A = teams[h], teams[a]
        exp = 1.0 / (1.0 + 10.0 ** (-((H["elo"] + 55.0) - A["elo"]) / 400.0))
        act = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
        diff = 20.0 * (act - exp)
        H["elo"] += diff
        A["elo"] -= diff
        H["gf"].append(hg); H["ga"].append(ag)
        A["gf"].append(ag); A["ga"].append(hg)
        H["home_gf"].append(hg); H["home_ga"].append(ag)
        A["away_gf"].append(ag); A["away_ga"].append(hg)
        H["results"].append(act); A["results"].append(1.0 - act)
        H["games"] += 1; A["games"] += 1
    return teams

def poisson(k, lam):
    return math.exp(-lam) * (lam ** k) / math.factorial(k) if lam > 0 else 0.0

def predict_fixture(fixture, teams):
    hkey, akey = team_ref(fixture.get("home_id"), fixture["home"]), team_ref(fixture.get("away_id"), fixture["away"])
    H, A = teams.get(hkey), teams.get(akey)
    if not H or not A or H["games"] < MIN_HISTORY or A["games"] < MIN_HISTORY:
        return {"available": False, "reason": "Yetersiz geçmiş maç verisi (minimum maç eşiği altında)."}
    
    ha, hd = statistics.mean(H["home_gf"] or [1.25]), statistics.mean(H["home_ga"] or [1.25])
    aa, ad = statistics.mean(A["away_gf"] or [1.10]), statistics.mean(A["away_ga"] or [1.25])
    lh = max(0.2, min(4.5, (0.45 * ha + 0.25 * ad + 0.30 * 1.3) * (0.85 + 0.30 * (1/(1+10**(-(H["elo"]+55 - A["elo"])/400))))))
    la = max(0.2, min(4.5, (0.45 * aa + 0.25 * hd + 0.30 * 1.2) * (1.05 - 0.25 * (1/(1+10**(-(H["elo"]+55 - A["elo"])/400))))))

    m = np.zeros((MAX_GOALS + 1, MAX_GOALS + 1))
    for h in range(MAX_GOALS + 1):
        for a in range(MAX_GOALS + 1):
            tau = 1 - (lh * la * -0.08) if h==0 and a==0 else (1 + lh * -0.08 if h==0 and a==1 else (1 + la * -0.08 if h==1 and a==0 else (1 - (-0.08) if h==1 and a==1 else 1.0)))
            m[h, a] = poisson(h, lh) * poisson(a, la) * tau
    m /= m.sum()

    home_p, draw_p, away_p, over_p, btts_y = 0.0, 0.0, 0.0, 0.0, 0.0
    for h in range(MAX_GOALS + 1):
        for a in range(MAX_GOALS + 1):
            p = float(m[h, a])
            if h > a: home_p += p
            elif h == a: draw_p += p
            else: away_p += p
            if h + a > 2: over_p += p
            if h > 0 and a > 0: btts_y += p

    score_idx = np.unravel_index(np.argmax(m), m.shape)
    one_x_two = max(home_p, draw_p, away_p)
    conf = 0.60 * one_x_two + 0.20 * (1 - abs(over_p - 0.5)) + 0.20 * min(1.0, (H["games"] + A["games"]) / 80.0)

    reason = f"Ev sahibi form/hücum (λ={lh:.2f}), deplasman savunma zayıflığına karşı üstün. Son 10 maçlık veriler, Elo dereceleri ve Dixon-Coles Poisson dağılımı baz alınarak skor {score_idx[0]}-{score_idx[1]} öngörülmüştür."

    return {
        "available": True,
        "lambda_home": round(lh, 2),
        "lambda_away": round(la, 2),
        "most_likely": f"{score_idx[0]}-{score_idx[1]}",
        "probabilities": {"home": home_p, "draw": draw_p, "away": away_p, "over25": over_p, "under25": 1-over_p, "bttsYes": btts_y, "bttsNo": 1-btts_y},
        "confidence": round(conf, 4),
        "reason": reason
    }

def build_coupons(fixtures):
    accumulator_legs = []
    matches_titles = []
    total_conf = 0.0
    for fix in fixtures:
        p = fix.get("prediction", {})
        if not p.get("available"): continue
        probs = p["probabilities"]
        h_p, d_p, a_p = probs["home"], probs["draw"], probs["away"]
        
        best_market = "MS 1" if h_p >= max(d_p, a_p) else ("MS 2" if a_p >= max(h_p, d_p) else "MS X")
        if p["confidence"] >= 0.58 and len(accumulator_legs) < 4:
            accumulator_legs.append(f"{fix['home']} vs {fix['away']} ({best_market})")
            matches_titles.append(f"{fix['home']} - {fix['away']}")
            total_conf += p["confidence"]

    coupons = []
    if accumulator_legs:
        avg_conf = total_conf / len(accumulator_legs)
        coupons.append({
            "title": "Günün 4'lü Değer Kombinesi",
            "combined_confidence": round(avg_conf, 4),
            "matches": matches_titles
        })
    return coupons

def evaluate_stats(history_sample):
    wins, losses = 0, 0
    for row in history_sample[-30:]:
        hg, ag = row["hg"], row["ag"]
        if hg != ag:
            wins += 1
        else:
            losses += 1
    return {"wins": wins, "losses": losses}

# ============================================================
# MAIN CLI RUNNER (WRITES TO docs/data/latest.json or data/latest.json)
# ============================================================
if __name__ == "__main__":
    if not API_KEY:
        print("ERROR: GOALDIR_API_KEY / BSD_API_KEY is not set.")
        sys.exit(1)
        
    print("KALE Motoru çalıştırılıyor...")
    history = load_history()
    print(f"Geçmiş maçlar yüklendi: {len(history)} adet.")
    
    teams = train_state(history)
    print("Model eğitildi.")
    
    fixtures = load_upcoming()
    print(f"Gelecek maçlar yüklendi: {len(fixtures)} adet.")
    
    output = []
    for fix in fixtures[:50]:
        pred = predict_fixture(fix, teams)
        fix["prediction"] = pred
        output.append(fix)
        
    coupons = build_coupons(output)
    stats = evaluate_stats(history)
    
    payload = {
        "prediction_engine": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "historical_matches": len(history),
        "upcoming_matches": len(output),
        "stats": stats,
        "coupons": coupons,
        "fixtures": output
    }
    
    # Hedef dizin kontrolü (workflow için hem data/ hem docs/data/ desteklenir)
    os.makedirs("data", exist_ok=True)
    os.makedirs("docs/data", exist_ok=True)
    
    with open("data/latest.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        
    with open("docs/data/latest.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        
    print("Başarılı! Veriler JSON dosyalarına yazıldı.")
    sys.exit(0)
