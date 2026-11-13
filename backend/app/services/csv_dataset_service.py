import csv
import re
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[3] / "datafile"
CSV_FILES = {
    "suppliers": "supplier_master.csv",
    "receipts": "raw_materials_log.csv",
    "production": "production_log.csv",
    "inspections": "qc_inspection.csv",
    "dispatches": "dispatch_log.csv",
    "complaints": "defect_complaints.csv",
}

OEM_NAMES = {
    "OEM-BAJAJ": "Bajaj Auto Ltd.",
    "OEM-TATA": "Tata Motors Ltd.",
    "OEM-MAHINDRA": "Mahindra & Mahindra Ltd.",
}


class CsvDatasetError(ValueError):
    pass


def _read_csv(data_dir: Path, filename: str) -> list[dict[str, str]]:
    path = data_dir / filename
    if not path.is_file():
        raise CsvDatasetError(f"Required CSV file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise CsvDatasetError(f"CSV file has no header: {filename}")
        return [
            {key: (value or "").strip() for key, value in row.items() if key}
            for row in reader
        ]


def _parse_source_date(value: str) -> tuple[str | None, str]:
    value = value.strip()
    if not value:
        return None, "missing"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value).isoformat(), "iso"
        except ValueError:
            return None, "invalid"

    match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", value)
    if not match:
        return None, "invalid"

    first, second, year = (int(part) for part in match.groups())
    if first > 12:
        day, month, resolution = first, second, "day_first"
    elif second > 12:
        month, day, resolution = first, second, "month_first"
    else:
        day, month, resolution = first, second, "ambiguous_assumed_day_first"

    try:
        return date(year, month, day).isoformat(), resolution
    except ValueError:
        return None, "invalid"


def _normalize_defect(value: str) -> str | None:
    if not value.strip():
        return None
    normalized = re.sub(r"[^a-z]", "", value.lower())
    if "delam" in normalized:
        return "surface_delamination"
    return normalized or None


class CsvTraceabilityDataset:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self.source_rows = {
            name: _read_csv(data_dir, filename)
            for name, filename in CSV_FILES.items()
        }
        self.suppliers = self._normalize_suppliers()
        self.supplier_by_id = {item["supplier_id"]: item for item in self.suppliers}
        self.complaints = self._normalize_complaints()
        self.lots = self._normalize_lots()
        self.lot_by_code = {item["lot_code"]: item for item in self.lots}
        self.batches = self._normalize_batches()
        self.batch_by_code = {item["batch_id"]: item for item in self.batches}
        self.dispatches = self._normalize_dispatches()
        self.dispatch_by_code = {item["order_id"]: item for item in self.dispatches}
        self.quality_report = self._build_quality_report()

    def _normalize_suppliers(self) -> list[dict[str, Any]]:
        return [
            {
                "supplier_id": row["supplier_id"],
                "supplier_name": row["supplier_name"],
                "material_supplied": row["material_supplied"],
                "lead_time_days": int(row["lead_time_days"]),
                "approved_status": row["approved_status"],
            }
            for row in self.source_rows["suppliers"]
        ]

    def _normalize_complaints(self) -> list[dict[str, Any]]:
        complaints = []
        for row_number, row in enumerate(self.source_rows["complaints"], start=1):
            complaints.append(
                {
                    **row,
                    "source_row": row_number,
                    "complaint_date": _parse_source_date(row["complaint_date"])[0],
                    "affected_order_ids": [
                        code.strip()
                        for code in row["affected_order_ids"].split(",")
                        if code.strip()
                    ],
                    "financial_impact_inr": float(row["financial_impact_inr"]),
                }
            )
        return complaints

    def _normalize_lots(self) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        missing_lot_rows = 0
        for row_number, row in enumerate(self.source_rows["receipts"], start=1):
            if not row["lot_number"]:
                missing_lot_rows += 1
                continue
            received_date, date_resolution = _parse_source_date(row["receipt_date"])
            grouped[row["lot_number"]].append(
                {
                    **row,
                    "source_row": row_number,
                    "received_date": received_date,
                    "date_resolution": date_resolution,
                    "quantity_kg": float(row["quantity_kg"]),
                }
            )

        scenario_sources: dict[str, tuple[str, str]] = {}
        for complaint in self.complaints:
            root_cause = complaint["root_cause_identified"]
            lot_match = re.search(r"LOT-[A-Z0-9-]+", root_cause.upper())
            supplier_match = re.search(r"\bS\d{2}\b", root_cause.upper())
            if lot_match and supplier_match:
                scenario_sources[lot_match.group()] = (
                    supplier_match.group(),
                    "complaint_ground_truth",
                )

        lots = []
        for lot_code, receipts in grouped.items():
            combinations = {
                (row["supplier_id"], row["material_type"])
                for row in receipts
            }
            selected = None
            resolution = "unresolved_conflict"
            if len(combinations) == 1:
                selected = receipts[0]
                resolution = "single_supplier_material"
            elif lot_code in scenario_sources:
                supplier_id, _ = scenario_sources[lot_code]
                candidates = [
                    row
                    for row in receipts
                    if row["supplier_id"] == supplier_id
                    and "adhesive" in row["material_type"].lower()
                ]
                if candidates:
                    selected = candidates[0]
                    resolution = "complaint_ground_truth"

            supplier = self.supplier_by_id.get(selected["supplier_id"]) if selected else None
            lots.append(
                {
                    "lot_code": lot_code,
                    "supplier_id": selected["supplier_id"] if selected else None,
                    "supplier_name": supplier["supplier_name"] if supplier else None,
                    "material_name": selected["material_type"] if selected else "Conflicting source records",
                    "quantity_received": selected["quantity_kg"] if selected else None,
                    "unit_of_measure": "kg",
                    "receipt_date": selected["received_date"] if selected else None,
                    "quality_grade": selected["quality_grade"] if selected else None,
                    "qc_status": "FAIL" if resolution == "complaint_ground_truth" else "REVIEW" if not selected else "PENDING",
                    "risk_status": "AT_RISK" if resolution == "complaint_ground_truth" else "DATA_REVIEW" if not selected else "SAFE",
                    "resolution_status": resolution,
                    "source_row_count": len(receipts),
                    "candidate_supplier_ids": sorted({row["supplier_id"] for row in receipts}),
                    "source_rows": [row["source_row"] for row in receipts],
                }
            )
        self.missing_lot_rows = missing_lot_rows
        return sorted(lots, key=lambda item: item["lot_code"])

    def _normalize_batches(self) -> list[dict[str, Any]]:
        quality_rows = self.source_rows["inspections"]
        if len(quality_rows) != len(self.source_rows["production"]):
            raise CsvDatasetError(
                "Production and QC files must have matching row counts for same-row batch ID recovery"
            )

        used_ids: set[str] = set()
        batches = []
        self.missing_batch_ids = 0
        self.imputed_batch_ids = 0
        self.id_alignment_mismatches = 0
        defect_labels = Counter()

        for row_number, (production, inspection) in enumerate(
            zip(self.source_rows["production"], quality_rows), start=1
        ):
            original_batch_id = production["batch_id"]
            batch_id = original_batch_id
            imputed = False
            link_method = "source_batch_id"
            if not batch_id:
                self.missing_batch_ids += 1
                candidate = inspection["batch_id"]
                if candidate and candidate not in used_ids:
                    batch_id = candidate
                    imputed = True
                    link_method = "same_row_qc_batch_id"
                    self.imputed_batch_ids += 1

            if original_batch_id and original_batch_id != inspection["batch_id"]:
                self.id_alignment_mismatches += 1

            raw_defect = inspection["defect_type"]
            normalized_defect = _normalize_defect(raw_defect)
            if raw_defect:
                defect_labels[raw_defect] += 1

            production_date, production_date_resolution = _parse_source_date(production["date"])
            inspection_date, inspection_date_resolution = _parse_source_date(
                inspection["inspection_date"]
            )
            status = inspection["pass_fail"].strip().upper()
            batches.append(
                {
                    "batch_id": batch_id,
                    "source_batch_id": original_batch_id or None,
                    "batch_id_imputed": imputed,
                    "batch_link_method": link_method,
                    "source_row": row_number,
                    "production_date": production_date,
                    "production_date_resolution": production_date_resolution,
                    "shift": production["shift"],
                    "machine_id": production["machine_id"],
                    "operator_id": production["operator_id"],
                    "input_lot_ref": production["input_lot_ref"],
                    "units_produced": int(production["units_produced"]),
                    "cycle_time_min": float(production["cycle_time_min"]),
                    "qc_status": status,
                    "inspection_date": inspection_date,
                    "inspection_date_resolution": inspection_date_resolution,
                    "inspector_id": inspection["inspector_id"],
                    "defect_type_raw": raw_defect or None,
                    "defect_type": normalized_defect,
                    "defect_rate_pct": float(inspection["defect_rate_pct"]),
                    "rework_flag": inspection["rework_flag"],
                }
            )
            if batch_id:
                used_ids.add(batch_id)

        self.qc_defect_labels = dict(defect_labels)
        self.unresolved_batch_rows = sum(1 for batch in batches if not batch["batch_id"])
        self.batch_id_set = {batch["batch_id"] for batch in batches if batch["batch_id"]}
        return batches

    def _normalize_dispatches(self) -> list[dict[str, Any]]:
        dispatches = []
        self.unmatched_dispatch_references = 0
        for row_number, row in enumerate(self.source_rows["dispatches"], start=1):
            batch_refs = [
                code.strip()
                for code in row["batch_ref"].split(",")
                if code.strip()
            ]
            linked = [code for code in batch_refs if code in self.batch_id_set]
            unresolved = [code for code in batch_refs if code not in self.batch_id_set]
            self.unmatched_dispatch_references += len(unresolved)
            dispatched_date, date_resolution = _parse_source_date(row["dispatch_date"])
            customer_id = row["customer_id"]
            dispatches.append(
                {
                    "order_id": row["order_id"],
                    "customer_id": customer_id,
                    "customer_name": OEM_NAMES.get(customer_id, customer_id),
                    "product_type": row["product_type"],
                    "quantity": int(row["quantity"]),
                    "dispatch_date": dispatched_date,
                    "dispatch_date_resolution": date_resolution,
                    "batch_refs": batch_refs,
                    "linked_batch_refs": linked,
                    "unresolved_batch_refs": unresolved,
                    "vehicle_number": row["vehicle_number"],
                    "source_row": row_number,
                }
            )
        return dispatches

    def _build_quality_report(self) -> dict[str, Any]:
        dates = [
            (row["receipt_date"], "raw_materials_log")
            for row in self.source_rows["receipts"]
        ]
        dates.extend(
            (row["date"], "production_log")
            for row in self.source_rows["production"]
        )
        dates.extend(
            (row["inspection_date"], "qc_inspection")
            for row in self.source_rows["inspections"]
        )
        dates.extend(
            (row["dispatch_date"], "dispatch_log")
            for row in self.source_rows["dispatches"]
        )
        ambiguous_dates = sum(
            1 for value, _ in dates if _parse_source_date(value)[1] == "ambiguous_assumed_day_first"
        )
        conflict_lots = sum(
            1 for lot in self.lots if lot["resolution_status"] == "unresolved_conflict"
        )
        return {
            "source_rows": {name: len(rows) for name, rows in self.source_rows.items()},
            "missing_lot_numbers": self.missing_lot_rows,
            "missing_production_batch_ids": self.missing_batch_ids,
            "imputed_batch_ids": self.imputed_batch_ids,
            "unresolved_production_rows": self.unresolved_batch_rows,
            "production_qc_id_mismatches": self.id_alignment_mismatches,
            "unmatched_dispatch_batch_references": self.unmatched_dispatch_references,
            "unresolved_lot_conflicts": conflict_lots,
            "ambiguous_dates_assumed_day_first": ambiguous_dates,
            "qc_defect_label_variants": self.qc_defect_labels,
            "imputation_policy": (
                "A missing production batch ID is filled from the QC batch ID at the same row only when that ID is unused. "
                "All populated same-row production/QC IDs are also checked for alignment."
            ),
            "lot_resolution_policy": (
                "Conflicting lot records are not merged. C001 is used as ground truth for LOT-2023-114 and its S03 adhesive record."
            ),
            "date_policy": (
                "ISO dates are preserved; unambiguous numeric dates use their valid day/month order; "
                "numeric dates with both fields <= 12 are assumed day-first and counted here."
            ),
        }

    def summary(self) -> dict[str, Any]:
        return {
            "suppliers_count": len(self.suppliers),
            "lots_count": len(self.lots),
            "batches_count": len(self.batches),
            "failed_qc_batches": sum(batch["qc_status"] == "FAIL" for batch in self.batches),
            "at_risk_batches": sum(
                batch["qc_status"] == "FAIL"
                or batch["input_lot_ref"] == "LOT-2023-114"
                for batch in self.batches
            ),
            "dispatch_orders_count": len(self.dispatches),
            "total_dispatched_pcs": sum(order["quantity"] for order in self.dispatches),
            "data_quality": self.quality_report,
        }

    def trace_dispatch(self, dispatch_code: str) -> dict[str, Any]:
        dispatch = self.dispatch_by_code.get(dispatch_code)
        if not dispatch:
            raise KeyError(f"Dispatch order {dispatch_code} was not found in dispatch_log.csv")

        chains = []
        unresolved_batch_refs = []
        for batch_code in dispatch["batch_refs"]:
            batch = self.batch_by_code.get(batch_code)
            if not batch:
                unresolved_batch_refs.append(batch_code)
                continue
            lot = self.lot_by_code.get(batch["input_lot_ref"])
            supplier = self.supplier_by_id.get(lot["supplier_id"]) if lot and lot["supplier_id"] else None
            chains.append(
                {
                    "batch": batch,
                    "lot": lot,
                    "supplier": supplier,
                    "lot_resolution": lot["resolution_status"] if lot else "missing_receipt",
                    "qc": {
                        "status": batch["qc_status"],
                        "inspection_date": batch["inspection_date"],
                        "inspector_id": batch["inspector_id"],
                        "defect_type": batch["defect_type"],
                        "defect_type_raw": batch["defect_type_raw"],
                        "defect_rate_pct": batch["defect_rate_pct"],
                        "rework_flag": batch["rework_flag"],
                    },
                }
            )

        related_complaints = [
            complaint
            for complaint in self.complaints
            if dispatch_code in complaint["affected_order_ids"]
        ]
        return {
            "dispatch": dispatch,
            "chains": chains,
            "unresolved_batch_refs": unresolved_batch_refs,
            "related_complaints": related_complaints,
            "data_quality": self.quality_report,
        }

    def alert_lot(self, lot_code: str) -> dict[str, Any]:
        lot = self.lot_by_code.get(lot_code)
        if not lot:
            raise KeyError(f"Lot {lot_code} was not found in raw_materials_log.csv")

        batches = [
            batch for batch in self.batches if batch["input_lot_ref"] == lot_code
        ]
        affected_batch_ids = {batch["batch_id"] for batch in batches}
        orders = []
        for dispatch in self.dispatches:
            affected_refs = [
                ref for ref in dispatch["linked_batch_refs"] if ref in affected_batch_ids
            ]
            if affected_refs:
                orders.append({**dispatch, "affected_batch_refs": affected_refs})

        related_complaints = [
            complaint
            for complaint in self.complaints
            if lot_code in complaint["root_cause_identified"]
        ]
        return {
            "lot": lot,
            "supplier": self.supplier_by_id.get(lot["supplier_id"]) if lot["supplier_id"] else None,
            "affected_batches": batches,
            "affected_dispatches": orders,
            "related_complaints": related_complaints,
            "unmatched_batch_references_in_dataset": self.unmatched_dispatch_references,
            "data_quality": self.quality_report,
        }


@lru_cache(maxsize=1)
def get_csv_dataset() -> CsvTraceabilityDataset:
    return CsvTraceabilityDataset()