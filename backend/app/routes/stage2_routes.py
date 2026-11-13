from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from app.models import (
    Snapshot,
    SnapshotCommitment,
    DefectEvent,
    InspectorVerdict,
    PropagationState,
    PropagationQueueItem,
    ProcessedUnit,
    ContinuationHistory,
    LateEdge,
    ExposureRecord,
    RiskAssessment,
)
from app.services.snapshot_service import seal_snapshot
from app.services.snapshot_verification_service import verify_snapshot_integrity
from app.services.defect_event_service import (
    submit_defect_event,
    submit_inspector_verdict,
    anchor_defect_event_onchain,
)
from app.services.propagation_service import start_propagation, continue_propagation
from app.services.late_edge_service import register_late_edge_and_check_gate
from app.services.exposure_service import compute_unit_level_exposure
from app.services.bayesian_risk_service import compute_bayesian_risk
from app.blockchain.contract_service import ContractService
from app.utils.rbac import roles_required

s2_bp = Blueprint("stage2", __name__)


# ------------------------------------------------------------------------------
# MODULE 1: SNAPSHOTS
# ------------------------------------------------------------------------------
@s2_bp.get("/snapshots")
@jwt_required()
def list_snapshots():
    snaps = Snapshot.query.order_by(Snapshot.version.desc()).all()
    out = []
    for s in snaps:
        comm = SnapshotCommitment.query.filter_by(snapshot_version=s.version).first()
        item = s.to_dict()
        item["commitment"] = comm.to_dict() if comm else None
        out.append(item)
    return jsonify(out)


@s2_bp.post("/snapshots/seal")
@roles_required("Manufacturer", "Admin")
def api_seal_snapshot():
    body = request.get_json() or {}
    claims = get_jwt()
    res = seal_snapshot(
        sealed_by=claims.get("email", "mfg@blocktracex.io"),
        version=body.get("version"),
        anchor_onchain=bool(body.get("anchor_onchain", True)),
    )
    return jsonify(res), 201


@s2_bp.post("/snapshots/<int:version>/verify")
@jwt_required()
def api_verify_snapshot(version: int):
    body = request.get_json() or {}
    res = verify_snapshot_integrity(version, expected_root=body.get("expected_root"))
    return jsonify(res)


# ------------------------------------------------------------------------------
# MODULE 2: DEFECT EVENTS & INSPECTOR ATTESTATIONS
# ------------------------------------------------------------------------------
@s2_bp.get("/defects")
@jwt_required()
def list_defect_events():
    events = DefectEvent.query.order_by(DefectEvent.id.desc()).all()
    return jsonify([e.to_dict() for e in events])


@s2_bp.post("/defects")
@roles_required("QC Inspector", "Manufacturer")
def api_submit_defect():
    body = request.get_json() or {}
    claims = get_jwt()
    evt = submit_defect_event(
        event_code=body["event_code"],
        lot_code=body["lot_code"],
        snapshot_version=int(body["snapshot_version"]),
        severity=int(body.get("severity", 4)),
        evidence_filename=body.get("evidence_filename", "qc_report.json"),
        evidence_payload=body.get("evidence_payload", "{}"),
        created_by=claims.get("email", "qc@blocktracex.io"),
        quorum_required=int(body.get("quorum_required", 2)),
        challenge_window_seconds=int(body.get("challenge_window_seconds", 300)),
    )
    return jsonify(evt), 201


@s2_bp.get("/defects/<event_code>/verdicts")
@jwt_required()
def list_verdicts(event_code: str):
    verdicts = InspectorVerdict.query.filter_by(event_code=event_code).all()
    return jsonify([v.to_dict() for v in verdicts])


@s2_bp.post("/defects/<event_code>/attest")
@roles_required("QC Inspector", "Manufacturer", "Admin")
def api_attest_defect(event_code: str):
    body = request.get_json() or {}
    claims = get_jwt()
    inspector_email = body.get("inspector_email") or claims.get("email", "qc@blocktracex.io")
    evt = submit_inspector_verdict(
        event_code=event_code,
        inspector_email=inspector_email,
        decision=body["decision"],
        confidence=float(body.get("confidence", 0.95)),
        notes=body.get("notes", ""),
    )
    return jsonify(evt)


@s2_bp.post("/defects/<event_code>/anchor")
@roles_required("QC Inspector", "Manufacturer", "Admin")
def api_anchor_defect(event_code: str):
    evt = anchor_defect_event_onchain(event_code)
    return jsonify(evt)


# ------------------------------------------------------------------------------
# MODULE 3: BOUNDED DEFECT PROPAGATION
# ------------------------------------------------------------------------------
@s2_bp.post("/propagation/start")
@roles_required("Manufacturer", "QC Inspector")
def api_start_propagation():
    body = request.get_json() or {}
    state = start_propagation(body["event_code"])
    return jsonify(state), 201


@s2_bp.post("/propagation/<event_code>/continue")
@roles_required("Manufacturer", "QC Inspector")
def api_continue_propagation(event_code: str):
    body = request.get_json() or {}
    res = continue_propagation(
        event_code=event_code,
        budget_k=int(body.get("K", 5)),
        budget_m=int(body.get("M", 10)),
        budget_z=int(body.get("Z", 5)),
        expected_lambda=body.get("expected_lambda"),
        expected_commitment=body.get("expected_commitment"),
    )
    return jsonify(res)


@s2_bp.get("/propagation/<event_code>/status")
@jwt_required()
def api_propagation_status(event_code: str):
    state = PropagationState.query.filter_by(event_code=event_code).first()
    if not state:
        raise ValueError(f"No propagation state found for {event_code}")
    q_total = PropagationQueueItem.query.filter_by(event_code=event_code).count()
    q_done = PropagationQueueItem.query.filter_by(event_code=event_code, processed=True).count()
    return jsonify(
        {
            "state": state.to_dict(),
            "queue": {
                "total_enqueued": q_total,
                "processed_count": q_done,
                "remaining": q_total - q_done,
            },
        }
    )


@s2_bp.get("/propagation/<event_code>/history")
@jwt_required()
def api_propagation_history(event_code: str):
    rows = (
        ContinuationHistory.query.filter_by(event_code=event_code)
        .order_by(ContinuationHistory.segment_lambda.asc())
        .all()
    )
    return jsonify([r.to_dict() for r in rows])


@s2_bp.get("/propagation/<event_code>/affected")
@jwt_required()
def api_propagation_affected(event_code: str):
    rows = ProcessedUnit.query.filter_by(event_code=event_code).all()
    return jsonify([r.to_dict() for r in rows])


# ------------------------------------------------------------------------------
# MODULE 4: ACTIVE LATE-EDGE GATE
# ------------------------------------------------------------------------------
@s2_bp.get("/late-edges")
@jwt_required()
def api_list_late_edges():
    rows = LateEdge.query.order_by(LateEdge.id.desc()).all()
    return jsonify([r.to_dict() for r in rows])


@s2_bp.post("/late-edges")
@roles_required("Manufacturer")
def api_register_late_edge():
    body = request.get_json() or {}
    res = register_late_edge_and_check_gate(
        parent_type=body["parent_type"],
        parent_code=body["parent_code"],
        child_type=body["child_type"],
        child_code=body["child_code"],
        quantity_consumed=float(body["quantity_consumed"]),
        recorded_at_version=int(body["recorded_at_version"]),
        delay_seconds=int(body.get("delay_seconds", 30)),
        a_max_versions=int(body.get("Amax", 2)),
        t_late_seconds=int(body.get("Tlate", 3600)),
    )
    return jsonify(res), 201


# ------------------------------------------------------------------------------
# MODULE 5 & 6: EXPOSURE & BAYESIAN RISK
# ------------------------------------------------------------------------------
@s2_bp.post("/exposure/<event_code>/compute")
@jwt_required()
def api_compute_exposure(event_code: str):
    rows = compute_unit_level_exposure(event_code)
    return jsonify({"event_code": event_code, "exposures": rows})


@s2_bp.get("/exposure/<event_code>")
@jwt_required()
def api_get_exposure(event_code: str):
    rows = ExposureRecord.query.filter_by(event_code=event_code).all()
    return jsonify([r.to_dict() for r in rows])


@s2_bp.post("/risk/<event_code>/compute")
@jwt_required()
def api_compute_risk(event_code: str):
    body = request.get_json() or {}
    res = compute_bayesian_risk(
        event_code=event_code,
        prior_prob=float(body.get("prior_prob", 0.15)),
        sensitivity=float(body.get("sensitivity", 0.92)),
        false_support_prob=float(body.get("false_support_prob", 0.08)),
        anchor_onchain=bool(body.get("anchor_onchain", False)),
    )
    return jsonify(res)


@s2_bp.get("/risk/<event_code>")
@jwt_required()
def api_get_risk(event_code: str):
    rows = RiskAssessment.query.filter_by(event_code=event_code).all()
    return jsonify([r.to_dict() for r in rows])


# ------------------------------------------------------------------------------
# MODULE 7: ON-CHAIN VERIFICATION ENDPOINT
# ------------------------------------------------------------------------------
@s2_bp.get("/verify-onchain/<event_code>")
@jwt_required()
def api_verify_onchain_bundle(event_code: str):
    evt = DefectEvent.query.filter_by(event_code=event_code).first()
    if not evt:
        raise ValueError(f"Defect event {event_code} not found")
    snap_ver = verify_snapshot_integrity(evt.snapshot_version)
    cs = ContractService()
    defect_onchain = None
    if cs.bc.is_connected():
        try:
            defect_onchain = cs.get_defect_onchain(event_code)
        except Exception:
            defect_onchain = None
    return jsonify(
        {
            "event": evt.to_dict(),
            "snapshot_verification": snap_ver,
            "defect_onchain": defect_onchain,
        }
    )
