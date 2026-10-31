"""Spending guard.

Every paid call goes through `BudgetGuard.authorize()` first. It:
  1. estimates the cost,
  2. checks it against per-run, daily and monthly caps in settings.toml,
  3. refuses unless the user passed --approve-spend.
Actual spend (from Apify's run record, Claude's token usage, Hunter's credits)
is appended to data/spend_ledger.jsonl so the caps track real money.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class SpendNotApproved(Exception):
    """Raised when a paid step is attempted without approval or over budget."""


@dataclass
class Estimate:
    service: str        # "apify" | "claude" | "hunter"
    description: str
    amount: float       # USD, or credits for hunter
    unit: str = "usd"


class BudgetGuard:
    def __init__(self, ledger_path: Path, budget: dict, approved: bool = False):
        self.ledger_path = Path(ledger_path)
        self.budget = budget
        self.approved = approved

    # ---------- ledger ----------
    def _entries(self) -> list[tuple[int, dict]]:
        """Parsed ledger lines. Lines that aren't valid JSON objects are skipped with a warning."""
        if not self.ledger_path.exists():
            return []
        entries = []
        for n, line in enumerate(self.ledger_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                print(f"[budget] warning: skipping ledger line {n} (not valid JSON)", file=sys.stderr)
                continue
            if not isinstance(e, dict):
                print(f"[budget] warning: skipping ledger line {n} (not a JSON object)", file=sys.stderr)
                continue
            entries.append((n, e))
        return entries

    def spent(self, service: str, period: str) -> float:
        now = datetime.now(timezone.utc)
        prefix = now.strftime("%Y-%m-%d") if period == "day" else now.strftime("%Y-%m")
        total = 0.0
        for n, e in self._entries():
            if e.get("service") != service or not str(e.get("at", "")).startswith(prefix):
                continue
            # "usd" is a legacy key from hand-written lines; "amount" is what record() writes.
            amount = e.get("amount", e.get("usd"))
            try:
                total += float(amount)
            except (TypeError, ValueError):
                print(f"[budget] warning: skipping ledger line {n} (no usable 'amount' or 'usd')", file=sys.stderr)
        return total

    def record(self, service: str, amount: float, description: str, unit: str = "usd", meta: dict | None = None) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "at": datetime.now(timezone.utc).isoformat(),
            "service": service,
            "amount": round(float(amount), 6),
            "unit": unit,
            "description": description,
            "meta": meta or {},
        }
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    # ---------- caps ----------
    def caps(self, service: str) -> dict:
        b = self.budget
        if service == "hunter":
            return {"monthly": b.get("hunter_monthly_credits", 0)}
        return {
            "run": b.get(f"{service}_per_run_usd", 0),
            "daily": b.get(f"{service}_daily_usd", 0),
            "monthly": b.get(f"{service}_monthly_usd", 0),
        }

    def remaining(self, service: str) -> float:
        caps = self.caps(service)
        left = [caps["monthly"] - self.spent(service, "month")]
        if "daily" in caps:
            left.append(caps["daily"] - self.spent(service, "day"))
        if "run" in caps:
            left.append(caps["run"])
        return max(0.0, min(left))

    def check(self, est: Estimate) -> list[str]:
        """Return a list of problems (empty = within budget)."""
        problems = []
        caps = self.caps(est.service)
        if "run" in caps and est.amount > caps["run"]:
            problems.append(f"{est.service}: this run (~{est.amount:.2f}) is over the per-run cap ({caps['run']:.2f})")
        if "daily" in caps:
            day = self.spent(est.service, "day")
            if day + est.amount > caps["daily"]:
                problems.append(f"{est.service}: today {day:.2f} + {est.amount:.2f} would pass the daily cap ({caps['daily']:.2f})")
        month = self.spent(est.service, "month")
        if month + est.amount > caps["monthly"]:
            problems.append(f"{est.service}: this month {month:.2f} + {est.amount:.2f} would pass the monthly cap ({caps['monthly']:.2f})")
        return problems

    def authorize(self, est: Estimate) -> None:
        unit = "credits" if est.unit == "credits" else "USD"
        print(f"[budget] {est.description}: estimated {est.amount:.4f} {unit}")
        problems = self.check(est)
        if problems:
            raise SpendNotApproved("Over budget, not running:\n  - " + "\n  - ".join(problems))
        if not self.approved:
            raise SpendNotApproved(
                "Paid step not run. Re-run the same command with --approve-spend to allow it."
            )
