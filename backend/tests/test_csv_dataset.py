from app.services.csv_dataset_service import CsvTraceabilityDataset


def test_dispatch_trace_matches_silent_recall_anchor():
    dataset = CsvTraceabilityDataset()

    trace = dataset.trace_dispatch("D-1847")

    assert trace["dispatch"]["customer_id"] == "OEM-TATA"
    assert trace["chains"][0]["batch"]["batch_id"] == "BATCH-2023-0500"
    assert trace["chains"][0]["batch"]["machine_id"] == "MC-04"
    assert trace["chains"][0]["batch"]["shift"] == "C"
    assert trace["chains"][0]["lot"]["lot_code"] == "LOT-2023-114"
    assert trace["chains"][0]["supplier"]["supplier_id"] == "S03"
    assert trace["chains"][0]["qc"]["status"] == "FAIL"
    assert trace["chains"][0]["qc"]["defect_rate_pct"] == 5.74
    assert trace["chains"][0]["qc"]["defect_type"] == "surface_delamination"


def test_lot_alert_traces_all_source_linked_dispatches():
    dataset = CsvTraceabilityDataset()

    alert = dataset.alert_lot("LOT-2023-114")

    batch_ids = {batch["batch_id"] for batch in alert["affected_batches"]}
    assert {
        "BATCH-2023-0500",
        "BATCH-2023-0501",
        "BATCH-2023-0502",
        "BATCH-2023-0503",
    } <= batch_ids
    assert len(batch_ids) == 20
    assert {order["order_id"] for order in alert["affected_dispatches"]} == {
        "D-1264",
        "D-1451",
        "D-1847",
        "D-1921",
        "D-2044",
        "D-2102",
        "D-2367",
    }
    assert alert["supplier"]["supplier_id"] == "S03"


def test_dataset_reports_missing_ids_and_unresolved_source_conflicts():
    dataset = CsvTraceabilityDataset()

    assert dataset.quality_report["missing_production_batch_ids"] == 678
    assert dataset.quality_report["imputed_batch_ids"] == 678
    assert dataset.quality_report["unresolved_production_rows"] == 0
    assert dataset.quality_report["unmatched_dispatch_batch_references"] == 1039
    assert dataset.quality_report["unresolved_lot_conflicts"] > 0

def test_operator_batch_entry_is_authenticated_and_retry_safe():
    from flask_jwt_extended import create_access_token

    from app import create_app, db
    from app.models import Role, User

    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.app_context():
        role = Role(name="Manufacturer")
        db.session.add(role)
        db.session.flush()
        user = User(email="operator@test.io", full_name="Operator", role_id=role.id)
        user.set_password("Test123")
        db.session.add(user)
        db.session.commit()
        token = create_access_token(
            identity=str(user.id),
            additional_claims={"role": "Manufacturer", "email": user.email},
        )

    client = app.test_client()
    headers = {"Authorization": f"Bearer {token}"}
    entry = {
        "batch_code": "BATCH-MANUAL-TEST-001",
        "production_date": "2026-11-13",
        "shift": "A",
        "machine_id": "MC-01",
        "operator_id": "OP-TEST",
        "input_lot_ref": "LOT-2023-114",
        "units_produced": 10,
        "cycle_time_min": 12.5,
    }

    created = client.post("/api/manufacturing/operator-batches", json=entry, headers=headers)
    retried = client.post("/api/manufacturing/operator-batches", json=entry, headers=headers)

    assert created.status_code == 201
    assert created.json["batch_code"] == entry["batch_code"]
    assert retried.status_code == 200
    assert client.get("/api/manufacturing/operator-batches", headers=headers).json == [created.json]