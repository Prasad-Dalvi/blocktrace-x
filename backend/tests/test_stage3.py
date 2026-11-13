import pytest
from app import create_app, db
from app.models import Role, User, HashChainedAuditEntry
from app.services.claim_service import file_buyer_complaint, submit_supplier_response
from app.services.dispute_service import authorize_arbitration_decision
from app.services.audit_service import append_audit_entry, verify_audit_ledger


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
        r_buyer = Role(name="Buyer")
        r_sup = Role(name="Supplier")
        r_arb = Role(name="Arbitrator")
        db.session.add_all([r_admin, r_buyer, r_sup, r_arb])
        db.session.flush()

        u_buyer = User(email="buyer@test.io", full_name="Buyer", role_id=r_buyer.id)
        u_buyer.set_password("Test123")
        db.session.add(u_buyer)
        db.session.commit()
        yield app


def test_complaint_dispute_and_audit_tamper_detection(app_ctx):
    c = file_buyer_complaint(
        claim_code="CLM-1001",
        po_number="PO-1001",
        defect_event_code="EVT-2023-114-01",
        buyer_email="buyer@test.io",
        description="Adhesive bonding delamination on D-1264",
        evidence_text='{"batch":"2023-0459"}',
    )
    assert c["status"] == "OPEN"

    # Duplicate complaint rejected
    with pytest.raises(ValueError, match="Duplicate claim code"):
        file_buyer_complaint(
            claim_code="CLM-1001",
            po_number="PO-1001",
            defect_event_code="EVT-2023-114-01",
            buyer_email="buyer@test.io",
            description="Duplicate",
            evidence_text="{}",
        )

    resp = submit_supplier_response("CLM-1001", "s03@test.io", "Disputing root cause", escalate_to_dispute=True)
    assert resp["status"] == "DISPUTED"

    auth = authorize_arbitration_decision(
        claim_code="CLM-1001",
        arbitrator_email="arb@test.io",
        rationale="Split fault 50/50 on disputed 0.6 ETH",
        supplier_payout_eth="0.3",
        buyer_refund_eth="0.3",
    )
    assert auth["settled"] is False

    # Verify audit chain integrity
    ver_ok = verify_audit_ledger()
    assert ver_ok["valid"] is True
    assert ver_ok["checked_entries"] == 3

    # Simulate off-chain audit tampering and verify detection
    entry = HashChainedAuditEntry.query.filter_by(sequence_num=2).first()
    entry.payload_json = '{"tampered": true}'
    db.session.commit()

    ver_bad = verify_audit_ledger()
    assert ver_bad["valid"] is False
    assert ver_bad["broken_at_sequence"] == 2
