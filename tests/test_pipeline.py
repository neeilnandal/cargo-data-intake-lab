import csv
import tempfile
import unittest
from pathlib import Path

from pipeline import DATA_DIR, run_pipeline, validate_row, POUNDS_TO_KG


class TestCargoPipeline(unittest.TestCase):

    def test_valid_weight_conversion(self):
        record = {
            "client": "client_b",
            "source_row": 2,
            "shipment_id": "AWB100",
            "origin": "LHR",
            "destination": "DXB",
            "weight": "1200",
        }

        result, error = validate_row(record, "lb")

        self.assertIsNone(error)
        self.assertAlmostEqual(
            result["weight_kg"],
            round(1200 * POUNDS_TO_KG, 3),
        )

    def test_missing_destination_rejected(self):
        record = {
            "client": "client_a",
            "source_row": 2,
            "shipment_id": "AWB100",
            "origin": "AMS",
            "destination": "",
            "weight": "850",
        }

        result, error = validate_row(record, "kg")

        self.assertIsNone(result)
        self.assertEqual(error, "missing_destination")

    def test_negative_weight_rejected(self):
        record = {
            "client": "client_a",
            "source_row": 2,
            "shipment_id": "AWB101",
            "origin": "AMS",
            "destination": "JFK",
            "weight": "-20",
        }

        result, error = validate_row(record, "kg")

        self.assertIsNone(result)
        self.assertEqual(
            error, "nonpositive_or_nonfinite_weight"
        )

    def test_pipeline_counts_and_duplicates(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            summary = run_pipeline(DATA_DIR, output)

            self.assertEqual(summary["input_records"], 8)
            self.assertEqual(summary["accepted_records"], 4)
            self.assertEqual(summary["rejected_records"], 4)

            with (output / "rejected.csv").open(
                newline="", encoding="utf-8"
            ) as file:
                rejected = list(csv.DictReader(file))

            reasons = [row["reason"] for row in rejected]

            self.assertIn("duplicate_shipment_id", reasons)
            self.assertIn("missing_destination", reasons)
            self.assertIn("invalid_weight", reasons)

    def test_rerun_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)

            first = run_pipeline(DATA_DIR, output)
            first_csv = (output / "accepted.csv").read_bytes()

            second = run_pipeline(DATA_DIR, output)
            second_csv = (output / "accepted.csv").read_bytes()

            self.assertEqual(first, second)
            self.assertEqual(first_csv, second_csv)

    def test_missing_column_raises_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "data"
            data.mkdir()

            (data / "client_a.csv").write_text(
            "shipment_id,origin,weight_kg\n"
            "AWB001,AMS,100\n",
                encoding="utf-8",
            )

            (data / "client_b.csv").write_text(
                (DATA_DIR / "client_b.csv").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError, "missing columns"
            ):
                run_pipeline(data, root / "output")
    def test_non_ascii_airport_rejected(self):
        record = {
            "client": "client_a",
            "source_row": 2,
            "shipment_id": "AWB100",
            "origin": "ÄMS",
            "destination": "JFK",
            "weight": "100",
        }

        valid, error = validate_row(record, "kg")
        self.assertIsNone(valid)
        self.assertEqual(error, "invalid_origin")

    def test_tiny_weight_rejected(self):
        record = {
            "client": "client_a",
            "source_row": 2,
            "shipment_id": "AWB101",
            "origin": "AMS",
            "destination": "JFK",
            "weight": "0.00001",
        }

        valid, error = validate_row(record, "kg")
        self.assertIsNone(valid)
        self.assertEqual(error, "weight_below_precision")


     def test_duplicate_csv_headers_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "data"
            data.mkdir()

            (data / "client_a.csv").write_text(
            "shipment_id,origin,origin,"
            "destination,weight_kg\n"
            "AWB001,AMS,FRA,JFK,100\n",
            encoding="utf-8",
            )

            (data / "client_b.csv").write_text(
                (DATA_DIR / "client_b.csv").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError, "duplicate CSV column names"
            ):
                run_pipeline(data, root / "output")
                

    def test_invalid_weight_text_rejected(self):
        record = {
            "client": "client_a",
            "source_row": 2,
            "shipment_id": "AWB102",
            "origin": "AMS",
            "destination": "JFK",
            "weight": "not-a-number",
        }

        valid, error = validate_row(record, "kg")

        self.assertIsNone(valid)
        self.assertEqual(error, "invalid_weight")

if __name__ == "__main__":
    unittest.main()
