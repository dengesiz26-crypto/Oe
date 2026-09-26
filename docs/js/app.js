/* Shared data-loading + render helpers. The frontend ONLY ever reads
   docs/data/*.json — it never calls a provider API directly. */

async function loadJSON(path) {
  try {
    const res = await fetch(path, { cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    return await res.json();
  } catch (e) {
    console.warn("Could not load", path, e);
    return null;
  }
}

function classBadgeClass(classification) {
  return "badge badge-" + classification.replace(/\s+/g, "");
}

function decisionBadgeClass(decision) {
  return "badge " + (decision === "PLAY" ? "badge-PLAY" : "badge-NOBET");
}

function fmtPct(v) {
  return (v * 100).toFixed(1) + "%";
}

function fmtOdds(v) {
  return v == null ? "—" : v.toFixed(2);
}

function fmtEdge(v) {
  const sign = v > 0 ? "+" : "";
  return sign + (v * 100).toFixed(1) + "%";
}

function fmtKickoff(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) +
    " · " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function marketLabel(market) {
  const map = {
    "1x2_home": "Home", "1x2_draw": "Draw", "1x2_away": "Away",
    "btts_yes": "BTTS Yes", "btts_no": "BTTS No",
  };
  if (map[market]) return map[market];
  if (market.startsWith("over_")) return "Over " + market.split("_")[1];
  if (market.startsWith("under_")) return "Under " + market.split("_")[1];
  if (market.startsWith("home_team_over_")) return "Home Team Over " + market.split("_").pop();
  if (market.startsWith("away_team_over_")) return "Away Team Over " + market.split("_").pop();
  return market;
}

function pickCardHTML(p) {
  return `
    <div class="card pick-card">
      <div>
        <div class="pick-teams">${p.home_team} — ${p.away_team}</div>
        <div class="pick-meta">${p.league} · ${fmtKickoff(p.kickoff_utc)}</div>
      </div>
      <span class="${classBadgeClass(p.classification)}">${p.classification}</span>

      <div class="pick-market">${marketLabel(p.market)}</div>
      <span class="${decisionBadgeClass(p.decision)}">${p.decision}</span>

      <div class="pick-figures">
        <div class="figure"><span class="label">AI Probability</span><span class="value">${fmtPct(p.probability)}</span></div>
        <div class="figure"><span class="label">Bookmaker Odds</span><span class="value">${fmtOdds(p.odds)}</span></div>
        <div class="figure"><span class="label">Fair Odds</span><span class="value">${fmtOdds(p.fair_odds)}</span></div>
        <div class="figure"><span class="label">Edge</span><span class="value ${p.edge > 0 ? "pos" : "neg"}">${fmtEdge(p.edge)}</span></div>
        <div class="figure"><span class="label">Risk</span><span class="value">${p.risk_level}</span></div>
      </div>
    </div>`;
}
