"""Synthetic sample data with seeded errors. No real client data.

Two weekly snapshots are generated per pack. Week 2 keeps some week-1 errors
(still open), fixes the rest (resolved) and introduces a few new ones, so the
register can show ageing and resolution. Everything is driven by one seed,
so reruns give identical files.
"""

from __future__ import annotations

import random
import string
from datetime import date, timedelta

import pandas as pd

from .rules import lei_with_check_digits

WEEK1 = date(2026, 10, 19)
WEEK2 = date(2026, 10, 26)

FRONT_OFFICES = ["JCBD", "GCIB Coverage", "Transaction Banking", "Capital Markets"]
DEAL_TEAMS = ["PF Energy", "PF Infrastructure", "PF Renewables"]
COUNTRIES = ["NL", "DE", "FR", "BE", "ES", "IT", "AT", "PL", "JP", "GB"]
SECTORS = ["Offshore wind", "Solar PV", "Toll road", "Fibre network", "Battery storage", "Hospital PPP"]


def _rng(seed: int) -> random.Random:
    return random.Random(seed)


def _lei(r: random.Random) -> str:
    body = "".join(r.choice(string.ascii_uppercase + string.digits) for _ in range(18))
    return lei_with_check_digits(body)


def _split_errors(r: random.Random, ids: list, kinds: list[str], n_w1: int, keep: float, n_new: int):
    """Choose which records carry which error in week 1 and week 2."""
    w1 = {i: r.choice(kinds) for i in r.sample(ids, n_w1)}
    persisting = {i: k for i, k in w1.items() if r.random() < keep}
    fresh_ids = r.sample([i for i in ids if i not in w1], n_new)
    w2 = {**persisting, **{i: r.choice(kinds) for i in fresh_ids}}
    return w1, w2


# ---------- client data ----------

def _client_base(r: random.Random, n: int, as_of: date) -> pd.DataFrame:
    rows = []
    for k in range(n):
        rows.append(
            {
                "cif_id": f"CIF{100000 + k}",
                "legal_name": f"Client Entity {k:04d} B.V.",
                "lei": _lei(r),
                "country": r.choice(COUNTRIES),
                "cif_status": "Active",
                "active_accounts": r.randint(1, 4),
                "signatories": r.randint(1, 5),
                "kyc_review_due": (as_of + timedelta(days=r.randint(20, 700))).isoformat(),
                "front_office": r.choice(FRONT_OFFICES),
            }
        )
    return pd.DataFrame(rows)


def _break_client(df: pd.DataFrame, errors: dict, as_of: date) -> pd.DataFrame:
    df = df.copy()
    idx = {cid: i for i, cid in enumerate(df["cif_id"])}
    for cid, kind in errors.items():
        i = idx[cid]
        if kind == "no_lei":
            df.at[i, "lei"] = ""
        elif kind == "bad_lei":
            lei = df.at[i, "lei"]
            df.at[i, "lei"] = lei[:-2] + ("00" if lei[-2:] != "00" else "11")
        elif kind == "dup_lei":
            df.at[i, "lei"] = df.at[(i + 1) % len(df), "lei"]
        elif kind == "kyc_overdue":
            df.at[i, "kyc_review_due"] = (as_of - timedelta(days=15)).isoformat()
        elif kind == "closed_with_account":
            df.at[i, "cif_status"] = "Closed"
        elif kind == "no_signatory":
            df.at[i, "signatories"] = 0
        elif kind == "bad_country":
            df.at[i, "country"] = "Netherlands"
    return df


def client_data(seed: int = 7, n: int = 500) -> tuple[pd.DataFrame, pd.DataFrame]:
    r = _rng(seed)
    base = _client_base(r, n, WEEK1)
    # Weights mimic a realistic skew: a few causes produce most of the breaks.
    kinds = ["kyc_overdue"] * 5 + ["no_lei"] * 3 + ["no_signatory"] * 2 + ["bad_lei", "dup_lei", "closed_with_account", "bad_country"]
    w1, w2 = _split_errors(r, list(base["cif_id"]), kinds, n_w1=40, keep=0.45, n_new=9)
    return _break_client(base, w1, WEEK1), _break_client(base, w2, WEEK2)


# ---------- reconciliation ----------

def _recon_base(r: random.Random, n: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "account_id": [f"NL{r.randint(10, 99)}MUFG{700000 + k}" for k in range(n)],
            "status": [r.choice(["Active"] * 9 + ["Dormant"]) for _ in range(n)],
            "balance_eur": [round(r.uniform(1_000, 25_000_000), 2) for _ in range(n)],
            "currency": [r.choice(["EUR"] * 6 + ["USD", "JPY", "GBP"]) for _ in range(n)],
            "front_office": [r.choice(FRONT_OFFICES) for _ in range(n)],
        }
    )


def _break_recon(core: pd.DataFrame, errors: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    report = core.copy()
    drop_from_report, drop_from_core = [], []
    for acc, kind in errors.items():
        i = report.index[report["account_id"] == acc][0]
        if kind == "missing_in_report":
            drop_from_report.append(i)
        elif kind == "missing_in_core":
            drop_from_core.append(i)
        elif kind == "status":
            report.at[i, "status"] = "Closed"
        elif kind == "balance":
            report.at[i, "balance_eur"] = round(report.at[i, "balance_eur"] * 0.98, 2)
        elif kind == "currency":
            report.at[i, "currency"] = "USD" if report.at[i, "currency"] != "USD" else "EUR"
    return core.drop(index=drop_from_core).reset_index(drop=True), report.drop(index=drop_from_report).reset_index(drop=True)


def reconciliation(seed: int = 11, n: int = 400):
    r = _rng(seed)
    core = _recon_base(r, n)
    kinds = ["balance"] * 4 + ["missing_in_report"] * 3 + ["status"] * 2 + ["missing_in_core", "currency"]
    w1, w2 = _split_errors(r, list(core["account_id"]), kinds, n_w1=24, keep=0.4, n_new=6)
    return _break_recon(core, w1), _break_recon(core, w2)


# ---------- project finance ----------

def _pf_base(r: random.Random, n: int, as_of: date) -> pd.DataFrame:
    rows = []
    for k in range(n):
        committed = r.choice([50, 75, 120, 180, 250, 400]) * 1_000_000
        close = as_of - timedelta(days=r.randint(200, 2500))
        rows.append(
            {
                "facility_id": f"PF-{2400 + k}",
                "project": f"{r.choice(SECTORS)} Project {k:02d}",
                "country": r.choice(COUNTRIES[:9]),
                "spv_lei": _lei(r),
                "committed_eur": committed,
                "drawn_eur": round(committed * r.uniform(0.3, 0.97), 0),
                "dscr_covenant": 1.20,
                "dscr_actual": round(r.uniform(1.25, 1.9), 2),
                "next_covenant_test": (as_of + timedelta(days=r.randint(10, 180))).isoformat(),
                "insurance_expiry": (as_of + timedelta(days=r.randint(30, 360))).isoformat(),
                "es_category": r.choice(["A", "B", "B", "C"]),
                "financial_close": close.isoformat(),
                "maturity": (close + timedelta(days=365 * r.randint(10, 22))).isoformat(),
                "deal_team": r.choice(DEAL_TEAMS),
            }
        )
    return pd.DataFrame(rows)


def _break_pf(df: pd.DataFrame, errors: dict, as_of: date) -> pd.DataFrame:
    df = df.copy()
    idx = {fid: i for i, fid in enumerate(df["facility_id"])}
    for fid, kind in errors.items():
        i = idx[fid]
        if kind == "overdrawn":
            df.at[i, "drawn_eur"] = df.at[i, "committed_eur"] * 1.03
        elif kind == "dscr":
            df.at[i, "dscr_actual"] = 1.08
        elif kind == "test_overdue":
            df.at[i, "next_covenant_test"] = (as_of - timedelta(days=12)).isoformat()
        elif kind == "insurance":
            df.at[i, "insurance_expiry"] = (as_of - timedelta(days=5)).isoformat()
        elif kind == "es_missing":
            df.at[i, "es_category"] = ""
        elif kind == "maturity":
            df.at[i, "maturity"] = (pd.Timestamp(df.at[i, "financial_close"]) - pd.Timedelta(days=30)).date().isoformat()
        elif kind == "spv_lei":
            df.at[i, "spv_lei"] = "PENDING"
    return df


def project_finance(seed: int = 23, n: int = 60):
    r = _rng(seed)
    base = _pf_base(r, n, WEEK1)
    kinds = ["test_overdue"] * 3 + ["insurance"] * 2 + ["es_missing"] * 2 + ["dscr", "spv_lei", "overdrawn", "maturity"]
    w1, w2 = _split_errors(r, list(base["facility_id"]), kinds, n_w1=10, keep=0.5, n_new=3)
    return _break_pf(base, w1, WEEK1), _break_pf(base, w2, WEEK2)
