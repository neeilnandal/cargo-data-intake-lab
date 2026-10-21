import csv
import tempfile
import unittest
from pathlib import Path

from pipeline import DATA_DIR, POUNDS_TO_KG, run_pipeline, validate_row


class TestCargoPipeline(unittest.TestCase):
    def record(self, **overrides):
        example = {"client": "client_a", "source_row": 2, "shipment_id": "AWB100", "origin": "AMS", "destination": "JFK", "weight": "100"}
        example.update(overrides)
        return example

    def test_valid_weight_conversion(self):
        result, error = validate_row(self.record(weight="1200"), "lb")
        self.assertIsNone(error)
        self.assertAlmostEqual(result["weight_kg"], round(1200 * POUNDS_TO_KG, 3))

    def test_missing_destination_rejected(self):
        valid, error = validate_row(self.record(destination=""), "kg")
        self.assertIsNone(valid)
        self.assertEqual(error, "missing_destination")

    def test_negative_weight_rejected(self):
        valid, error = validate_row(self.record(weight="-20"), "kg")
        self.assertIsNone(valid)
        self.assertEqual(error, "nonpositive_or_nonfinite_weight")

    def test_pipeline_counts_and_duplicates(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            summary = run_pipeline(DATA_DIR, output)
            self.assertEqual(summary["input_records"], 8)
            self.assertEqual(summary["accepted_records"], 4)
            self.assertEqual(summary["rejected_records"], 4)
            with (output / "rejected.csv").open(newline="", encoding="utf-8") as file:
                reasons = [row["reason"] for row in csv.DictReader(file)]
            for reason in ("duplicate_shipment_id", "missing_destination", "invalid_weight"):
                self.assertIn(reason, reasons)

    def test_rerun_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            first = run_pipeline(DATA_DIR, output)
            first_csv = (output / "accepted.csv").read_bytes()
            second = run_pipeline(DATA_DIR, output)
            self.assertEqual(first, second)
            self.assertEqual(first_csv, (output / "accepted.csv").read_bytes())

    def test_missing_column_raises_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "data"
            data.mkdir()
            (data / "client_a.csv").write_text("shipment_id,origin,weight_kg\nAWB001,AMS,100\n", encoding="utf-8")
            (data / "client_b.csv").write_text((DATA_DIR / "client_b.csv").read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing columns"):
                run_pipeline(data, root / "output")

    def test_non_ascii_airport_rejected(self):
        valid, error = validate_row(self.record(origin="ÄMS"), "kg")
        self.assertIsNone(valid)
        self.assertEqual(error, "invalid_origin")

    def test_tiny_weight_rejected(self):
        valid, error = validate_row(self.record(weight="0.00001"), "kg")
        self.assertIsNone(valid)
        self.assertEqual(error, "weight_below_precision")

    def test_duplicate_csv_headers_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "data"
            data.mkdir()
            (data / "client_a.csv").write_text("shipment_id,origin,origin,destination,weight_kg\nAWB001,AMS,FRA,JFK,100\n", encoding="utf-8")
            (data / "client_b.csv").write_text((DATA_DIR / "client_b.csv").read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate CSV column names"):
                run_pipeline(data, root / "output")

    def test_invalid_weight_text_rejected(self):
        valid, error = validate_row(self.record(weight="not-a-number"), "kg")
        self.assertIsNone(valid)
        self.assertEqual(error, "invalid_weight")


if __name__ == "__main__":
    unittest.main()
