import unittest
from datetime import date

import pandas as pd

from integritygate import samples
from integritygate.engine import carry_forward, run_pack, summarise
from integritygate.rules import (
    CLIENT_DATA,
    PROJECT_FINANCE,
    RECONCILIATION,
    build_reconciliation_frame,
    lei_is_valid,
    lei_with_check_digits,
)

AS_OF = date(2026, 10, 26)


def client(**overrides):
    row = {
        "cif_id": "CIF1", "legal_name": "Test B.V.", "lei": lei_with_check_digits("ABCDEFGHIJ12345678"),
        "country": "NL", "cif_status": "Active", "active_accounts": 1, "signatories": 2,
        "kyc_review_due": "2027-06-01", "front_office": "JCBD",
    }
    row.update(overrides)
    return row


class LeiTests(unittest.TestCase):
    def test_real_published_lei_is_valid(self):
        # GLEIF's own LEI, from the public register
        self.assertTrue(lei_is_valid("506700GE1G29325QX363"))

    def test_generated_check_digits_are_valid(self):
        self.assertTrue(lei_is_valid(lei_with_check_digits("5493001KJTIIGC8Y1R")))

    def test_altered_lei_is_rejected(self):
        self.assertFalse(lei_is_valid("506700GE1G29325QX364"))
        self.assertFalse(lei_is_valid("PENDING"))
        self.assertFalse(lei_is_valid(None))


class ClientRuleTests(unittest.TestCase):
    def codes(self, rows):
        return set(run_pack(CLIENT_DATA, pd.DataFrame(rows), AS_OF)["rule_code"])

    def test_clean_record_has_no_breaks(self):
        self.assertEqual(self.codes([client()]), set())

    def test_each_seeded_error_maps_to_one_reason(self):
        self.assertEqual(self.codes([client(lei="")]), {"CD01"})
        self.assertEqual(self.codes([client(kyc_review_due="2026-10-01")]), {"CD04"})
        self.assertEqual(self.codes([client(cif_status="Closed")]), {"CD05"})
        self.assertEqual(self.codes([client(signatories=0)]), {"CD06"})
        self.assertEqual(self.codes([client(country="Netherlands")]), {"CD07"})

    def test_duplicate_lei_flags_both_records(self):
        reg = run_pack(CLIENT_DATA, pd.DataFrame([client(), client(cif_id="CIF2")]), AS_OF)
        self.assertEqual(sorted(reg.loc[reg.rule_code == "CD03", "record_id"]), ["CIF1", "CIF2"])

    def test_owner_is_the_front_office(self):
        reg = run_pack(CLIENT_DATA, pd.DataFrame([client(lei="")]), AS_OF)
        self.assertEqual(reg.iloc[0]["owner"], "JCBD")

    def test_duplicate_ids_are_refused(self):
        with self.assertRaises(ValueError):
            run_pack(CLIENT_DATA, pd.DataFrame([client(), client()]), AS_OF)


class ReconciliationTests(unittest.TestCase):
    def test_missing_and_mismatched_accounts(self):
        core = pd.DataFrame({"account_id": ["A", "B", "C"], "status": ["Active"] * 3,
                             "balance_eur": [100.0, 200.0, 300.0], "currency": ["EUR"] * 3,
                             "front_office": ["JCBD"] * 3})
        report = pd.DataFrame({"account_id": ["A", "B", "D"], "status": ["Active", "Closed", "Active"],
                               "balance_eur": [100.5, 250.0, 50.0], "currency": ["EUR"] * 3,
                               "front_office": ["JCBD"] * 3})
        reg = run_pack(RECONCILIATION, build_reconciliation_frame(core, report), AS_OF)
        got = set(zip(reg["record_id"], reg["rule_code"]))
        self.assertEqual(got, {("C", "RC01"), ("D", "RC02"), ("B", "RC03"), ("B", "RC04")})


class ProjectFinanceTests(unittest.TestCase):
    def test_covenant_and_exposure_breaks(self):
        base = {"facility_id": "PF-1", "project": "Solar", "country": "ES",
                "spv_lei": lei_with_check_digits("ABCDEFGHIJ12345678"), "committed_eur": 100.0,
                "drawn_eur": 90.0, "dscr_covenant": 1.2, "dscr_actual": 1.4, "next_covenant_test": "2027-01-01",
                "insurance_expiry": "2027-03-01", "es_category": "B", "financial_close": "2024-01-01",
                "maturity": "2040-01-01", "deal_team": "PF Energy"}
        bad = dict(base, facility_id="PF-2", drawn_eur=110.0, dscr_actual=1.05, es_category="")
        reg = run_pack(PROJECT_FINANCE, pd.DataFrame([base, bad]), AS_OF)
        self.assertEqual(set(reg["record_id"]), {"PF-2"})
        self.assertEqual(set(reg["rule_code"]), {"PF01", "PF02", "PF05"})


class AgeingTests(unittest.TestCase):
    def test_new_open_resolved_and_age(self):
        wk1 = run_pack(CLIENT_DATA, pd.DataFrame([client(lei=""), client(cif_id="CIF2", signatories=0)]), date(2026, 10, 19))
        wk2_raw = run_pack(CLIENT_DATA, pd.DataFrame([client(lei=""), client(cif_id="CIF2"),
                                                      client(cif_id="CIF3", country="NLD")]), AS_OF)
        wk2 = carry_forward(wk1, wk2_raw).set_index(["record_id", "rule_code"])
        self.assertEqual(wk2.loc[("CIF1", "CD01"), "status"], "OPEN")
        self.assertEqual(wk2.loc[("CIF1", "CD01"), "age_days"], 7)
        self.assertEqual(wk2.loc[("CIF2", "CD06"), "status"], "RESOLVED")
        self.assertEqual(wk2.loc[("CIF3", "CD07"), "status"], "NEW")


class DeterminismTests(unittest.TestCase):
    def test_same_seed_same_output(self):
        a, _ = samples.client_data()
        b, _ = samples.client_data()
        pd.testing.assert_frame_equal(run_pack(CLIENT_DATA, a, AS_OF), run_pack(CLIENT_DATA, b, AS_OF))

    def test_every_break_is_reason_coded(self):
        _, c2 = samples.client_data()
        reg = run_pack(CLIENT_DATA, c2, samples.WEEK2)
        s = summarise(reg, {"client_data": len(c2)})
        self.assertEqual(s.iloc[0]["reason_coded_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
