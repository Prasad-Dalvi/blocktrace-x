from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from app import db
from app.models import (
    User,
    PurchaseOrder,
    EscrowLedger,
    Complaint,
    DisputeResolution,
    HashChainedAuditEntry,
)
from app.services.escrow_service import sync_escrow_from_chain, execute_escrow_action
from app.services.claim_service import file_buyer_complaint, submit_supplier_response
from app.services.dispute_service import authorize_arbitration_decision
from app.services.settlement_service import execute_onchain_settlement
from app.services.audit_service import verify_audit_ledger
from app.utils.rbac import roles_required

s3_bp = Blueprint("stage3", __name__)


@s3_bp.get("/escrow/all")
@jwt_required()
def list_all_escrows():
    pos = PurchaseOrder.query.all()
    out = []
    for p in pos:
        try:
            synced = sync_escrow_from_chain(p.po_number)
        except Exception:
            ledger = EscrowLedger.query.filter_by(po_number=p.po_number).first()
            synced = ledger.to_dict() if ledger else None
        out.append({"purchase_order": p.to_dict(), "escrow": synced})
    return jsonify(out)


@s3_bp.post("/escrow/<po_number>/action")
@jwt_required()
def trigger_escrow_action(po_number: str):
    body = request.get_json() or {}
    claims = get_jwt()
    res = execute_escrow_action(
        po_number=po_number,
        action=body["action"],
        actor_email=claims.get("email", "mfg@blocktracex.io"),
        amount_eth=body.get("amount_eth"),
        passed=bool(body.get("passed", True)),
        ref_text=body.get("ref_text", ""),
    )
    return jsonify(res)


@s3_bp.get("/complaints")
@jwt_required()
def list_complaints():
    return jsonify([c.to_dict() for c in Complaint.query.order_by(Complaint.id.desc()).all()])


@s3_bp.post("/complaints")
@roles_required("Buyer", "Manufacturer", "Admin")
def create_complaint():
    body = request.get_json() or {}
    claims = get_jwt()
    res = file_buyer_complaint(
        claim_code=body["claim_code"],
        po_number=body["po_number"],
        defect_event_code=body["defect_event_code"],
        buyer_email=claims.get("email", "buyer@blocktracex.io"),
        description=body["description"],
        evidence_text=body.get("evidence_text", "{}"),
    )
    return jsonify(res), 201


@s3_bp.post("/complaints/<claim_code>/respond")
@roles_required("Supplier", "Manufacturer", "Admin")
def respond_complaint(claim_code: str):
    body = request.get_json() or {}
    claims = get_jwt()
    res = submit_supplier_response(
        claim_code=claim_code,
        supplier_email=claims.get("email", "s03@blocktracex.io"),
        response_text=body["response_text"],
        escalate_to_dispute=bool(body.get("escalate_to_dispute", True)),
    )
    return jsonify(res)


@s3_bp.get("/disputes")
@jwt_required()
def list_disputes():
    resolutions = DisputeResolution.query.order_by(DisputeResolution.id.desc()).all()
    return jsonify([r.to_dict() for r in resolutions])


@s3_bp.post("/disputes/<claim_code>/authorize")
@roles_required("Arbitrator", "Admin")
def authorize_dispute(claim_code: str):
    body = request.get_json() or {}
    claims = get_jwt()
    res = authorize_arbitration_decision(
        claim_code=claim_code,
        arbitrator_email=claims.get("email", "arb@blocktracex.io"),
        rationale=body["rationale"],
        supplier_payout_eth=str(body["supplier_payout_eth"]),
        buyer_refund_eth=str(body["buyer_refund_eth"]),
        third_party_comp_eth=str(body.get("third_party_comp_eth", "0")),
        third_party_recipient=body.get(
            "third_party_recipient", "0x0000000000000000000000000000000000000000"
        ),
    )
    return jsonify(res), 201


@s3_bp.post("/settlements/<claim_code>/execute")
@roles_required("Manufacturer", "Arbitrator", "Admin")
def execute_settlement(claim_code: str):
    claims = get_jwt()
    res = execute_onchain_settlement(
        claim_code=claim_code,
        actor_email=claims.get("email", "mfg@blocktracex.io"),
    )
    return jsonify(res)


@s3_bp.get("/audit-ledger")
@jwt_required()
def get_audit_ledger():
    entries = (
        HashChainedAuditEntry.query.order_by(HashChainedAuditEntry.sequence_num.desc())
        .all()
    )
    return jsonify([e.to_dict() for e in entries])


@s3_bp.get("/audit-ledger/verify")
@jwt_required()
def verify_audit():
    return jsonify(verify_audit_ledger())


@s3_bp.get("/users")
@roles_required("Admin")
def list_users():
    return jsonify([u.to_dict() for u in User.query.all()])
