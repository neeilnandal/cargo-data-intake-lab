"""IntegrityGate engine.

Runs a pack of named, reason-coded rules over a table and returns an
exception register: one row per broken rule per record, with an owner,
a severity and an age. Comparing two runs shows which breaks are new,
which are still open and which were resolved.

The design mirrors cargo-data-intake-lab: every rejection carries a
reason, reruns on the same input give the same output, and the rules
live in plain data so a reviewer can read them without reading code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

import pandas as pd

REGISTER_COLUMNS = [
    "pack",
    "record_id",
    "rule_code",
    "reason",
    "severity",
    "owner",
    "first_seen",
    "as_of",
    "age_days",
    "status",
]


@dataclass(frozen=True)
class Rule:
    """One control. `check` returns a boolean Series: True means the record breaks the rule."""

    code: str
    reason: str
    severity: str  # "High" or "Medium"
    check: Callable[[pd.DataFrame, date], pd.Series]


@dataclass(frozen=True)
class RulePack:
    name: str
    id_column: str
    owner_column: str
    rules: tuple[Rule, ...]


def run_pack(pack: RulePack, data: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """Apply every rule in the pack and return the exception register for this run."""
    if pack.id_column not in data.columns:
        raise KeyError(f"{pack.name}: id column '{pack.id_column}' missing")
    if data[pack.id_column].duplicated().any():
        raise ValueError(f"{pack.name}: duplicate record ids, rerun would not be deterministic")

    rows = []
    for rule in pack.rules:
        mask = rule.check(data, as_of).fillna(False).astype(bool)
        for _, rec in data.loc[mask].iterrows():
            rows.append(
                {
                    "pack": pack.name,
                    "record_id": rec[pack.id_column],
                    "rule_code": rule.code,
                    "reason": rule.reason,
                    "severity": rule.severity,
                    "owner": rec.get(pack.owner_column, "UNASSIGNED") or "UNASSIGNED",
                    "first_seen": as_of,
                    "as_of": as_of,
                    "age_days": 0,
                    "status": "NEW",
                }
            )
    register = pd.DataFrame(rows, columns=REGISTER_COLUMNS)
    return register.sort_values(["pack", "rule_code", "record_id"]).reset_index(drop=True)


def carry_forward(previous: pd.DataFrame, current: pd.DataFrame) -> pd.DataFrame:
    """Merge a new run with the last register.

    A break seen before keeps its first_seen date and becomes OPEN, so its age grows.
    A break that has disappeared is kept once as RESOLVED, so fixes are visible.
    """
    key = ["pack", "record_id", "rule_code"]
    if previous is None or previous.empty:
        return current.copy()

    prev_open = previous[previous["status"] != "RESOLVED"]
    merged = current.merge(
        prev_open[key + ["first_seen"]].rename(columns={"first_seen": "prev_first_seen"}),
        on=key,
        how="left",
    )
    seen = merged["prev_first_seen"].notna()
    merged.loc[seen, "first_seen"] = merged.loc[seen, "prev_first_seen"]
    merged.loc[seen, "status"] = "OPEN"
    merged = merged.drop(columns="prev_first_seen")

    as_of = current["as_of"].iloc[0] if not current.empty else prev_open["as_of"].max()
    resolved = prev_open.merge(current[key], on=key, how="left", indicator=True)
    resolved = resolved[resolved["_merge"] == "left_only"].drop(columns="_merge")
    resolved = resolved.assign(as_of=as_of, status="RESOLVED")

    out = pd.concat([merged, resolved], ignore_index=True)[REGISTER_COLUMNS]
    out["age_days"] = (pd.to_datetime(out["as_of"]) - pd.to_datetime(out["first_seen"])).dt.days
    return out.sort_values(["status", "pack", "rule_code", "record_id"]).reset_index(drop=True)


def summarise(register: pd.DataFrame, records_checked: dict[str, int]) -> pd.DataFrame:
    """One line per pack: how many records, how many clean, how many breaks, how old."""
    lines = []
    for pack, n in records_checked.items():
        r = register[register["pack"] == pack]
        live = r[r["status"] != "RESOLVED"]
        broken_records = live["record_id"].nunique()
        lines.append(
            {
                "pack": pack,
                "records_checked": n,
                "records_clean": n - broken_records,
                "clean_rate_pct": round(100 * (n - broken_records) / n, 1) if n else 0.0,
                "open_breaks": len(live),
                "new_breaks": int((live["status"] == "NEW").sum()),
                "resolved_since_last_run": int((r["status"] == "RESOLVED").sum()),
                "high_severity_open": int((live["severity"] == "High").sum()),
                "median_age_days_open": float(live["age_days"].median()) if len(live) else 0.0,
                "reason_coded_pct": 100.0 if len(live) == 0 else round(100 * live["reason"].notna().mean(), 1),
                "top_cause": live["rule_code"].value_counts().idxmax() if len(live) else "-",
            }
        )
    return pd.DataFrame(lines)
