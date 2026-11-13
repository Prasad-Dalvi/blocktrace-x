import pytest
from app import create_app, db
from app.models import (
    Role,
    User,
    Supplier,
    Buyer,
    SupplierLot,
    ProductionBatch,
    DispatchOrder,
    GenealogyRelation,
)
from app.services.snapshot_service import seal_snapshot
from app.services.snapshot_verification_service import verify_snapshot_integrity
from app.services.defect_event_service import submit_defect_event, submit_inspector_verdict
from app.services.propagation_service import start_propagation, continue_propagation
from app.services.late_edge_service import register_late_edge_and_check_gate
from app.services.exposure_service import compute_unit_level_exposure
from app.services.bayesian_risk_service import compute_bayesian_risk


@pytest.fixture
def app_ctx():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.app_context():
        r_admin = Role(name="Admin")
        r_mfg = Role(name="Manufacturer")
        r_qc = Role(name="QC Inspector")
        db.session.add_all([r_admin, r_mfg, r_qc])
        db.session.flush()

        u_mfg = User(email="mfg@test.io", full_name="Mfg", role_id=r_mfg.id)
        u_mfg.set_password("Test123")
        u_qc1 = User(email="qc1@test.io", full_name="QC 1", role_id=r_qc.id)
        u_qc1.set_password("Test123")
        u_qc2 = User(email="qc2@test.io", full_name="QC 2", role_id=r_qc.id)
        u_qc2.set_password("Test123")
        db.session.add_all([u_mfg, u_qc1, u_qc2])

        s03 = Supplier(code="S03", name="Supplier S03", material_category="Adhesive")
        s07 = Supplier(code="S07", name="Supplier S07", material_category="Substrate")
        bajaj = Buyer(code="BAJAJ", name="Bajaj Auto")
        db.session.add_all([s03, s07, bajaj])
        db.session.flush()

        lot1 = SupplierLot(lot_code="LOT-2023-114", supplier_id=s03.id, material_name="Adhesive", quantity_received=1000.0)
        lot2 = SupplierLot(lot_code="LOT-2023-209", supplier_id=s07.id, material_name="Casting", quantity_received=2000.0)
        b1 = ProductionBatch(batch_code="2023-0101", machine_id="MC-04", units_produced=500, qc_status="FAIL")
        b2 = ProductionBatch(batch_code="2023-0459", machine_id="MC-03", units_produced=367, qc_status="FAIL")
        b_late = ProductionBatch(batch_code="2024-9999", machine_id="MC-05", units_produced=400, qc_status="PASS")
        d1 = DispatchOrder(dispatch_code="D-1264", buyer_id=bajaj.id, quantity_pcs=756)
        db.session.add_all([lot1, lot2, b1, b2, b_late, d1])
        db.session.flush()

        # Multi-parent edges: LOT-2023-114 & LOT-2023-209 -> 2023-0101, 2023-0459 -> D-1264
        db.session.add_all(
            [
                GenealogyRelation(parent_type="LOT", parent_code="LOT-2023-114", child_type="BATCH", child_code="2023-0101", quantity_consumed=90.0),
                GenealogyRelation(parent_type="LOT", parent_code="LOT-2023-209", child_type="BATCH", child_code="2023-0101", quantity_consumed=500.0),
                GenealogyRelation(parent_type="LOT", parent_code="LOT-2023-114", child_type="BATCH", child_code="2023-0459", quantity_consumed=66.0),
                GenealogyRelation(parent_type="BATCH", parent_code="2023-0101", child_type="DISPATCH", child_code="D-1264", quantity_consumed=300.0),
                GenealogyRelation(parent_type="BATCH", parent_code="2023-0459", child_type="DISPATCH", child_code="D-1264", quantity_consumed=456.0),
            ]
        )
        db.session.commit()
        yield app


def test_snapshot_merkle_and_verification(app_ctx):
    sealed = seal_snapshot("mfg@test.io", version=1, anchor_onchain=False)
    root = sealed["snapshot"]["global_root"]
    assert root.startswith("0x") and len(root) == 66

    ok_res = verify_snapshot_integrity(1, expected_root=root)
    assert ok_res["verified"] is True

    bad_res = verify_snapshot_integrity(1, expected_root="0x" + ("ff" * 32))
    assert bad_res["verified"] is False


def test_defect_quorum_bounded_propagation_late_edge_exposure_and_bayesian(app_ctx):
    seal_snapshot("mfg@test.io", version=1, anchor_onchain=False)

    # Submit defect event bound to snapshot v1
    evt = submit_defect_event(
        event_code="EVT-001",
        lot_code="LOT-2023-114",
        snapshot_version=1,
        severity=4,
        evidence_filename="lab.json",
        evidence_payload='{"shear":8.1}',
        created_by="qc1@test.io",
        quorum_required=2,
    )
    assert evt["status"] == "PENDING_ATTESTATION"

    # First verdict -> still pending quorum
    v1 = submit_inspector_verdict("EVT-001", "qc1@test.io", "SUPPORT", 0.95)
    assert v1["status"] == "PENDING_ATTESTATION"

    # Second verdict -> quorum met -> APPROVED
    v2 = submit_inspector_verdict("EVT-001", "qc2@test.io", "SUPPORT", 0.90)
    assert v2["status"] == "APPROVED"

    # Start propagation & enforce K=1, M=1, Z=1 budgets across segments
    st0 = start_propagation("EVT-001")
    assert st0["cursor"]["lambda"] == 0

    seg1 = continue_propagation("EVT-001", budget_k=1, budget_m=1, budget_z=1, expected_lambda=0)
    assert seg1["consumed"] if "consumed" in seg1 else seg1["segment_consumed"]["M"] == 1
    assert seg1["state"]["cursor"]["lambda"] == 1

    # Stale cursor rejection
    with pytest.raises(ValueError, match="Stale cursor rejected"):
        continue_propagation("EVT-001", budget_k=1, budget_m=1, budget_z=1, expected_lambda=0)

    # Complete initial propagation
    for _ in range(10):
        step = continue_propagation("EVT-001", budget_k=5, budget_m=10, budget_z=5)
        if step["state"]["status"] == "COMPLETED":
            break
    assert step["state"]["status"] == "COMPLETED"

    # Mandatory Late-Edge Gate Test (Module 4):
    # Register downstream relation at g+1=2 from affected batch 2023-0101 -> 2024-9999
    le_res = register_late_edge_and_check_gate(
        parent_type="BATCH",
        parent_code="2023-0101",
        child_type="BATCH",
        child_code="2024-9999",
        quantity_consumed=120.0,
        recorded_at_version=2,
        delay_seconds=45,
        a_max_versions=2,
        t_late_seconds=3600,
    )
    assert "EVT-001" in le_res["triggered_events"]

    # Continue reopened propagation and verify 2024-9999 is included
    re_step = continue_propagation("EVT-001", budget_k=5, budget_m=10, budget_z=5)
    assert re_step["state"]["status"] == "COMPLETED"

    # Unit-Level Exposure with multi-path deduplication (D-1264 reached via 2023-0101 and 2023-0459)
    exposures = compute_unit_level_exposure("EVT-001")
    exp_map = {e["node_key"]: e for e in exposures}
    assert "BATCH:2024-9999" in exp_map
    assert exp_map["DISPATCH:D-1264"]["exposure_fraction"] == 1.0

    # Bayesian posterior & risk classification
    risk_out = compute_bayesian_risk(
        "EVT-001",
        prior_prob=0.15,
        sensitivity=0.92,
        false_support_prob=0.08,
        anchor_onchain=False,
    )
    # 2 SUPPORT verdicts -> LR = (0.92/0.08)^2 = 132.25; prior_odds = 0.15/0.85 = 0.17647
    # posterior_odds = 23.338 -> P(D|E) = 23.338 / 24.338 = 0.9589
    assert risk_out["bayesian_parameters"]["posterior_probability"] > 0.95
    disp_risk = next(a for a in risk_out["assessments"] if a["node_key"] == "DISPATCH:D-1264")
    # R(D-1264) = 4 * 1.5 * 1.0 * 0.9589 = 5.753 -> RECALL_CANDIDATE
    assert disp_risk["classification"] == "RECALL_CANDIDATE"
