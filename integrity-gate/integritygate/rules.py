"""Rule packs. Each rule is a named control with a plain-English reason.

client_data     -> client master (CIF, accounts, signatories, KYC). CSO Data Integrity.
reconciliation  -> core banking extract vs downstream report. Operations / Middle Office.
project_finance -> facility register for project finance loans. GCIB product teams.

All thresholds here are illustrative. In a bank they come from the procedures
and the data owners, not from the analyst.
"""

from __future__ import annotations

import re
from datetime import date

import pandas as pd

from .engine import Rule, RulePack


# ---------- LEI check digits (ISO 17442 uses ISO 7064 MOD 97-10) ----------

def _lei_to_number(text: str) -> int:
    return int("".join(str(int(ch, 36)) for ch in text))


def lei_is_valid(lei: object) -> bool:
    if not isinstance(lei, str) or not re.fullmatch(r"[A-Z0-9]{18}[0-9]{2}", lei):
        return False
    return _lei_to_number(lei) % 97 == 1


def lei_with_check_digits(prefix18: str) -> str:
    """Append the two check digits to an 18-character LEI body."""
    remainder = _lei_to_number(prefix18 + "00") % 97
    return prefix18 + f"{98 - remainder:02d}"


def _blank(s: pd.Series) -> pd.Series:
    return s.isna() | (s.astype(str).str.strip() == "")


def _before(s: pd.Series, as_of: date) -> pd.Series:
    return pd.to_datetime(s, errors="coerce") < pd.Timestamp(as_of)


# ---------- Pack 1: client data (CSO Data Integrity) ----------

CLIENT_DATA = RulePack(
    name="client_data",
    id_column="cif_id",
    owner_column="front_office",
    rules=(
        Rule("CD01", "Legal entity has no LEI", "High",
             lambda d, t: _blank(d["lei"])),
        Rule("CD02", "LEI fails ISO 17442 check digits", "High",
             lambda d, t: ~_blank(d["lei"]) & ~d["lei"].map(lei_is_valid)),
        Rule("CD03", "Same LEI on more than one CIF (possible duplicate client)", "High",
             lambda d, t: ~_blank(d["lei"]) & d["lei"].duplicated(keep=False)),
        Rule("CD04", "KYC review date has passed", "High",
             lambda d, t: (d["cif_status"] == "Active") & _before(d["kyc_review_due"], t)),
        Rule("CD05", "CIF is closed but an account is still active", "High",
             lambda d, t: (d["cif_status"] == "Closed") & (d["active_accounts"] > 0)),
        Rule("CD06", "Active account with no authorised signatory", "Medium",
             lambda d, t: (d["active_accounts"] > 0) & (d["signatories"] == 0)),
        Rule("CD07", "Registered country missing or not ISO 3166 alpha-2", "Medium",
             lambda d, t: ~d["country"].fillna("").str.fullmatch(r"[A-Z]{2}")),
    ),
)


# ---------- Pack 2: reconciliation (Operations / Middle Office) ----------

def build_reconciliation_frame(core: pd.DataFrame, report: pd.DataFrame) -> pd.DataFrame:
    """Outer-join the system of record with the downstream report on account_id."""
    joined = core.merge(report, on="account_id", how="outer", suffixes=("_core", "_report"), indicator=True)
    joined["owner"] = joined["front_office_core"].fillna(joined["front_office_report"])
    return joined


BALANCE_TOLERANCE_EUR = 1.00

RECONCILIATION = RulePack(
    name="reconciliation",
    id_column="account_id",
    owner_column="owner",
    rules=(
        Rule("RC01", "Account in core system but missing from report", "High",
             lambda d, t: d["_merge"] == "left_only"),
        Rule("RC02", "Account in report but not in core system", "High",
             lambda d, t: d["_merge"] == "right_only"),
        Rule("RC03", "Account status differs between systems", "Medium",
             lambda d, t: (d["_merge"] == "both") & (d["status_core"] != d["status_report"])),
        Rule("RC04", f"Balance differs by more than EUR {BALANCE_TOLERANCE_EUR:.2f}", "High",
             lambda d, t: (d["_merge"] == "both")
             & ((d["balance_eur_core"] - d["balance_eur_report"]).abs() > BALANCE_TOLERANCE_EUR)),
        Rule("RC05", "Currency differs between systems", "Medium",
             lambda d, t: (d["_merge"] == "both") & (d["currency_core"] != d["currency_report"])),
    ),
)


# ---------- Pack 3: project finance facility register (GCIB) ----------

PROJECT_FINANCE = RulePack(
    name="project_finance",
    id_column="facility_id",
    owner_column="deal_team",
    rules=(
        Rule("PF01", "Drawn amount exceeds commitment", "High",
             lambda d, t: d["drawn_eur"] > d["committed_eur"]),
        Rule("PF02", "Reported DSCR below the covenant minimum", "High",
             lambda d, t: d["dscr_actual"] < d["dscr_covenant"]),
        Rule("PF03", "Covenant compliance test is overdue", "High",
             lambda d, t: _before(d["next_covenant_test"], t)),
        Rule("PF04", "Project insurance certificate has expired", "High",
             lambda d, t: _before(d["insurance_expiry"], t)),
        Rule("PF05", "Environmental and social category (A/B/C) not recorded", "Medium",
             lambda d, t: ~d["es_category"].isin(["A", "B", "C"])),
        Rule("PF06", "Maturity date falls before financial close", "Medium",
             lambda d, t: pd.to_datetime(d["maturity"], errors="coerce")
             < pd.to_datetime(d["financial_close"], errors="coerce")),
        Rule("PF07", "Sponsor or borrower SPV LEI missing or invalid", "Medium",
             lambda d, t: ~d["spv_lei"].map(lei_is_valid)),
    ),
)

ALL_PACKS = {p.name: p for p in (CLIENT_DATA, RECONCILIATION, PROJECT_FINANCE)}


def rule_catalogue() -> pd.DataFrame:
    rows = [
        {"pack": p.name, "rule_code": r.code, "reason": r.reason, "severity": r.severity, "owner_field": p.owner_column}
        for p in ALL_PACKS.values()
        for r in p.rules
    ]
    return pd.DataFrame(rows)
