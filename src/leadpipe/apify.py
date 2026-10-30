"""Thin Apify REST client. Every call is budget-checked before it starts.

Two layers of protection on each run:
  * our own BudgetGuard (per-run / daily / monthly caps, --approve-spend), and
  * Apify's server-side `maxTotalChargeUsd` + `maxItems`, so even a buggy loop
    can't spend more than the approved amount on Apify's side.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from .budget import BudgetGuard, Estimate

API = "https://api.apify.com/v2"


class ApifyError(Exception):
    pass


class ApifyClient:
    def __init__(self, token: str | None, guard: BudgetGuard, raw_dir: Path, timeout_s: int = 900):
        self.token = token
        self.guard = guard
        self.raw_dir = Path(raw_dir)
        self.timeout_s = timeout_s

    def _headers(self) -> dict:
        if not self.token:
            raise ApifyError("APIFY_TOKEN is not set. Add it to .env (see .env.example).")
        return {"Authorization": f"Bearer {self.token}"}

    def run_actor(self, actor: str, run_input: dict, max_items: int, price_per_item: float, label: str) -> list[dict]:
        """Run an Actor to completion and return its dataset items."""
        est_cost = round(max_items * price_per_item, 4)
        self.guard.authorize(Estimate("apify", f"{label} via {actor} (max {max_items} items)", est_cost))

        actor_path = actor.replace("/", "~")
        params = {
            "maxItems": max_items,
            # Apify stops charging once this is reached (pay-per-event Actors).
            "maxTotalChargeUsd": f"{est_cost:.4f}",
            "timeout": self.timeout_s,
        }
        r = requests.post(f"{API}/acts/{actor_path}/runs", params=params, json=run_input,
                          headers=self._headers(), timeout=60)
        if r.status_code >= 400:
            raise ApifyError(f"Could not start {actor}: {r.status_code} {r.text[:300]}")
        run = r.json()["data"]
        run_id = run["id"]
        print(f"[apify] started {actor} run {run_id}")

        deadline = time.time() + self.timeout_s + 120
        while run["status"] in ("READY", "RUNNING"):
            if time.time() > deadline:
                raise ApifyError(f"Run {run_id} took too long; check it in the Apify console.")
            r = requests.get(f"{API}/actor-runs/{run_id}", params={"waitForFinish": 60},
                             headers=self._headers(), timeout=90)
            r.raise_for_status()
            run = r.json()["data"]

        items: list[dict] = []
        if run.get("defaultDatasetId"):
            r = requests.get(f"{API}/datasets/{run['defaultDatasetId']}/items",
                             params={"clean": "true", "format": "json"},
                             headers=self._headers(), timeout=120)
            r.raise_for_status()
            items = r.json()

        # Record spend conservatively: the larger of Apify's reported usage and items x price.
        reported = float(run.get("usageTotalUsd") or 0)
        actual = max(reported, len(items) * price_per_item)
        self.guard.record("apify", actual, f"{label} ({actor})",
                          meta={"run_id": run_id, "status": run["status"], "items": len(items),
                                "usageTotalUsd": reported})
        self._save_raw(label, actor, run_input, run, items)

        if run["status"] != "SUCCEEDED":
            print(f"[apify] warning: run {run_id} ended {run['status']} with {len(items)} items")
        return items

    def _save_raw(self, label: str, actor: str, run_input: dict, run: dict, items: list) -> None:
        """Keep every paid result on disk so we never have to pay to fetch it again."""
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        folder = self.raw_dir / day
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{label.replace(' ', '_')}_{run['id']}.json"
        (folder / name).write_text(json.dumps(
            {"actor": actor, "input": run_input, "run": {k: run.get(k) for k in
             ("id", "status", "startedAt", "finishedAt", "usageTotalUsd", "defaultDatasetId")},
             "items": items}, indent=1, ensure_ascii=False))
