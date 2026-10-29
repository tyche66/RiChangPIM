"""Pure validation tests for the production product-image migration script."""

import csv

import pytest

from app.scripts.migrate_duplicate_product_images import (
    EXPECTED_PAIR_COUNT,
    MigrationSafetyError,
    load_pairs,
)


def _write_pairs(path, count: int = EXPECTED_PAIR_COUNT) -> None:
    fields = [
        "pair_index",
        "source_product_id",
        "target_product_id",
        "source_product_no",
        "target_product_no",
        "product_name",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index in range(1, count + 1):
            writer.writerow(
                {
                    "pair_index": index,
                    "source_product_id": f"00000000-0000-0000-0000-{index:012d}",
                    "target_product_id": f"10000000-0000-0000-0000-{index:012d}",
                    "source_product_no": f"P-{index}",
                    "target_product_no": str(index),
                    "product_name": f"产品 {index}",
                }
            )


def test_load_pairs_requires_the_complete_audit_set(tmp_path):
    path = tmp_path / "pairs.csv"
    _write_pairs(path, count=EXPECTED_PAIR_COUNT - 1)

    with pytest.raises(MigrationSafetyError, match="expected 240 audited pairs"):
        load_pairs(path)


def test_load_pairs_validates_number_invariant_and_order(tmp_path):
    path = tmp_path / "pairs.csv"
    _write_pairs(path)
    pairs = load_pairs(path)

    assert len(pairs) == EXPECTED_PAIR_COUNT
    assert pairs[0].source_no == "P-1"
    assert pairs[-1].target_no == str(EXPECTED_PAIR_COUNT)

    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    rows[0]["source_product_no"] = "WRONG-1"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(MigrationSafetyError, match="violates the P- invariant"):
        load_pairs(path)


def test_load_pairs_rejects_reused_product_ids(tmp_path):
    path = tmp_path / "pairs.csv"
    _write_pairs(path)
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    rows[1]["source_product_id"] = rows[0]["source_product_id"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(MigrationSafetyError, match="reuses a product id"):
        load_pairs(path)
