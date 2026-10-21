
import csv
import json
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

POUNDS_TO_KG = 0.45359237

CLIENT_CONFIG = {
    "client_a": {
        "file": "client_a.csv",
        "columns": {
            "shipment_id": "shipment_id",
            "origin": "origin",
            "destination": "destination",
            "weight": "weight_kg",
        },
        "unit": "kg",
    },
    "client_b": {
        "file": "client_b.csv",
        "columns": {
            "shipment_id": "airwaybill",
            "origin": "from_airport",
            "destination": "to_airport",
            "weight": "weight_lb",
        },
        "unit": "lb",
    },
}

OUTPUT_FIELDS = [
    "client",
    "source_row",
    "shipment_id",
    "origin",
    "destination",
    "weight_kg",
]

REJECTED_FIELDS = [
    "client",
    "source_row",
    "shipment_id",
    "reason",
]


def normalise_row(row, config, client, source_row):
    """Map customer-specific fields into one schema."""
    mapping = config["columns"]

    record = {
        "client": client,
        "source_row": source_row,
    }

    for target, source in mapping.items():
        record[target] = (row.get(source) or "").strip()

    record["origin"] = record["origin"].upper()
    record["destination"] = record["destination"].upper()

    return record


def validate_row(record, unit):
    """Return (valid_record, error_reason)."""
    for field in ("shipment_id", "origin", "destination"):
        if not record[field]:
            return None, f"missing_{field}"

    for field in ("origin", "destination"):
        value = record[field]
        if len(value) != 3 or not value.isalpha():
            return None, f"invalid_{field}"

    if not record["weight"]:
    return None, "missing_weight"

try:
    weight = float(record["weight"])
except ValueError:
    return None, "invalid_weight"

    if not (0 < weight < float("inf")):
        return None, "nonpositive_or_nonfinite_weight"

    if unit == "lb":
        weight *= POUNDS_TO_KG

    valid = {
        "client": record["client"],
        "source_row": record["source_row"],
        "shipment_id": record["shipment_id"],
        "origin": record["origin"],
        "destination": record["destination"],
        "weight_kg": round(weight, 3),
    }

    return valid, None


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run_pipeline(data_dir=DATA_DIR, output_dir=OUTPUT_DIR):
    """Process inputs and return a run summary."""
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)

    accepted = []
    rejected = []
    seen = set()
    counts = {}

    for client, config in CLIENT_CONFIG.items():
        source = data_dir / config["file"]
        count = 0

        with source.open(
            newline="", encoding="utf-8-sig"
        ) as file:
            reader = csv.DictReader(file)

            if not reader.fieldnames:
                raise ValueError(f"{client}: empty schema")

            required = set(config["columns"].values())
            missing = required - set(reader.fieldnames)
            
            unexpected = set(reader.fieldnames) - required

            if unexpected:
                logging.warning(
                     "%s: unexpected source columns: %s",
                     client,
                     sorted(unexpected),
                )
            if missing:
                raise ValueError(
                    f"{client}: missing columns {sorted(missing)}"
                )

            for row_number, row in enumerate(reader, start=2):
                count += 1

                # Catch malformed rows with too many fields.
                if None in row:
                    rejected.append({
                        "client": client,
                        "source_row": row_number,
                        "shipment_id": "",
                        "reason": "malformed_row",
                    })
                    continue

                record = normalise_row(
                    row, config, client, row_number
                )

                valid, reason = validate_row(
                    record, config["unit"]
                )

                if valid:
                    key = (client, valid["shipment_id"])

                    if key in seen:
                        reason = "duplicate_shipment_id"
                    else:
                        seen.add(key)
                        accepted.append(valid)

                if reason:
                    rejected.append({
                        "client": client,
                        "source_row": row_number,
                        "shipment_id": record["shipment_id"],
                        "reason": reason,
                    })

        counts[client] = count
        logging.info("%s: read %s records", client, count)

    summary = {
        "input_records": sum(counts.values()),
        "accepted_records": len(accepted),
        "rejected_records": len(rejected),
        "by_client": counts,
    }

    
    if (
        summary["input_records"]
        != summary["accepted_records"]
        + summary["rejected_records"]
):
        raise RuntimeError(
        "Record reconciliation failed: input count "
        "does not equal accepted plus rejected count"
    )    
    

    output_dir.mkdir(parents=True, exist_ok=True)

    write_csv(
        output_dir / "accepted.csv",
        OUTPUT_FIELDS,
        accepted,
    )

    write_csv(
        output_dir / "rejected.csv",
        REJECTED_FIELDS,
        rejected,
    )

    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    print(json.dumps(run_pipeline(), indent=2))
    
