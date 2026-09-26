"""
Final stage: writes the docs/data/*.json files the GitHub Pages frontend
reads. This is the ONLY thing that touches docs/ — the frontend never
calls a provider API directly (spec section 24).
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def export_all(predictions: list[dict], coupons: list[dict], backtest_report: dict,
               provider_status: list[dict], docs_data_dir: str = "docs/data") -> None:
    out = Path(docs_data_dir)
    now = datetime.now(timezone.utc).isoformat()

    # only PLAY-decision, best-classification candidates surface as "AI picks"
    picks = [p for p in predictions if p["decision"] == "PLAY"]

    _write(out / "latest.json", {"generated_at": now, "picks": picks})
    _write(out / "coupons.json", {"generated_at": now, "coupons": coupons})
    _write(out / "results.json", {"generated_at": now, "report": backtest_report})
    _write(out / "system.json", {"generated_at": now, "providers": provider_status})
