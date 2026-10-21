# Cargo Data Intake Lab

A lightweight, tested Python data-engineering demonstrator for multi-client data ingestion, standardisation, validation and exception handling.

## 1. Problem

When customer datasets enter operational software products, field names, measurement units and data quality can differ.

This project demonstrates how heterogeneous synthetic cargo datasets can be transformed into consistent, validated and traceable records before downstream processing.

## 2. Features

- Ingests CSV files from two simulated cargo-data customers.
- Maps different customer column names into a canonical schema.
- Converts weight measurements from pounds to kilograms.
- Validates required fields, airport-code formats and numeric weights.
- Detects duplicate shipment identifiers within each customer source.
- Separates valid records from rejected records.
- Generates record-level error reasons and processing summaries.
- Detects missing required source columns.
- Produces deterministic results across repeated executions.
- Includes six automated unit tests.

## 3. Technology

- Python 3.10+
- Python standard library (`csv`, `json`, `logging`, `pathlib`)
- `unittest` for automated testing

No external Python packages, API keys or cloud infrastructure are required.

## 4. Repository structure

```text
cargo-data-intake-lab/
├── pipeline.py
├── README.md
├── .gitignore
├── data/
│   ├── client_a.csv
│   └── client_b.csv
└── tests/
    ├── __init__.py
    └── test_pipeline.py
```

The `output/` directory is generated when the pipeline runs.

## 5. Run the pipeline

From the repository root:

```bash
python pipeline.py
```

Expected output with the supplied synthetic dataset:

```json
{
  "input_records": 8,
  "accepted_records": 4,
  "rejected_records": 4,
  "by_client": {
    "client_a": 4,
    "client_b": 4
  }
}
```

The pipeline creates:

- `output/accepted.csv` — validated canonical records
- `output/rejected.csv` — rejected records and error reasons
- `output/summary.json` — processing statistics

## 6. Run automated tests

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

**Validation result:** All six tests passed during development in Google Colab.

Tests cover:

1. Pounds-to-kilograms conversion.
2. Missing destination detection.
3. Negative weight rejection.
4. Input reconciliation and duplicate detection.
5. Deterministic reruns.
6. Missing required source-column detection.

## 7. Engineering decisions

**Client-specific mappings:** Configuration separates customer source-field names from the canonical output schema.

**Validation before output:** Invalid records are isolated rather than silently accepted.

**Traceability:** Rejection reports identify source clients, row numbers, shipment identifiers and error reasons.

**Data integrity:** An explicit reconciliation check verifies that accepted and rejected record counts equal the number of processed input records.

**Repeatability:** Reprocessing the same files overwrites the output files with deterministic results rather than appending records.

## 8. Scope and limitations

This project uses entirely synthetic data and is intended as a small engineering demonstration.

- Duplicate detection is limited to shipment IDs within each customer and execution.
- Three-letter airport codes are format-validated, not checked against an official IATA registry.
- Output files are not transactionally written.
- The implementation is not a production orchestration or streaming system.
- No real airline, customer or commercially confidential data is used.

Potential extensions include database-backed idempotency, atomic outputs, richer schema contracts, CI automation and operational monitoring.

## 9. Project motivation

This project explores a practical engineering problem in aviation and logistics: converting heterogeneous customer inputs into consistent, explainable and dependable data products.

It builds on data-ingestion and transformation concepts explored in my [Streamlit Economic Explorer](https://github.com/neeilnandal/streamlit-economic-explorer), with additional emphasis on validation, exception handling and repeatable execution.

## 10. Independence statement

This is an independent portfolio demonstration. It is not affiliated with, commissioned by or developed using internal systems or data belonging to Rotate or any other aviation company.

## Author

Neeil Nandal

[GitHub Profile](https://github.com/neeilnandal)
