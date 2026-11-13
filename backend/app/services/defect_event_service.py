from datetime import datetime, timedelta, timezone
from web3 import Web3
from app import db
from app.models import (
    SupplierLot,
    Snapshot,
    DefectEvent,
    Evidence,
    Attestation,
    InspectorVerdict,
)
from app.services.merkle_service import sha256_hex
from app.services.snapshot_verification_service import verify_snapshot_integrity
from app.blockchain.contract_service import ContractService
from app.blockchain.transaction_service import TransactionService


def submit_defect_event(
    event_code: str,
    lot_code: str,
    snapshot_version: int,
    severity: int,
    evidence_filename: str,
    evidence_payload: str,
    created_by: str,
    quorum_required: int = 2,
    challenge_window_seconds: int = 300,
) -> dict:
    if DefectEvent.query.filter_by(event_code=event_code).first():
        raise ValueError(f"Duplicate defect event ID: {event_code}")

    lot = SupplierLot.query.filter_by(lot_code=lot_code).first()
    if not lot:
        raise ValueError(f"Lot {lot_code} not found")

    snap = Snapshot.query.filter_by(version=snapshot_version).first()
    if not snap:
        raise ValueError(f"Snapshot version {snapshot_version} must be sealed before defect binding")

    ver = verify_snapshot_integrity(snapshot_version)
    if not ver["local_consistent"]:
        raise ValueError(f"Snapshot {snapshot_version} failed cryptographic verification")

    if severity < 1 or severity > 5:
        raise ValueError("Severity S must be between 1 and 5")

    ev_hash = sha256_hex(f"EVIDENCE|{event_code}|{evidence_filename}|{evidence_payload}")

    evt = DefectEvent(
        event_code=event_code,
        lot_code=lot_code,
        snapshot_version=snapshot_version,
        snapshot_commitment=snap.global_root,
        evidence_root_hash=ev_hash,
        severity=severity,
        status="PENDING_ATTESTATION",
        quorum_required=quorum_required,
        challenge_window_seconds=challenge_window_seconds,
        challenge_deadline=datetime.now(timezone.utc) + timedelta(seconds=challenge_window_seconds),
        created_by=created_by,
    )
    db.session.add(evt)
    db.session.flush()

    ev = Evidence(
        event_code=event_code,
        filename=evidence_filename,
        raw_payload=evidence_payload,
        sha256_hash=ev_hash,
        uploaded_by=created_by,
    )
    att = Attestation(
        event_code=event_code,
        quorum_met=False,
        attestation_digest=sha256_hex(f"ATT_INIT|{event_code}"),
    )
    db.session.add_all([ev, att])
    db.session.commit()
    return evt.to_dict()


def submit_inspector_verdict(
    event_code: str,
    inspector_email: str,
    decision: str,
    confidence: float = 0.95,
    notes: str = "",
) -> dict:
    evt = DefectEvent.query.filter_by(event_code=event_code).first()
    if not evt:
        raise ValueError(f"Defect event {event_code} not found")

    decision = decision.upper()
    if decision not in ("SUPPORT", "CONTRADICT"):
        raise ValueError("Decision must be SUPPORT or CONTRADICT")

    existing = InspectorVerdict.query.filter_by(
        event_code=event_code, inspector_email=inspector_email
    ).first()
    if existing:
        raise ValueError(f"Inspector {inspector_email} has already submitted a verdict for {event_code}")

    v_hash = sha256_hex(f"VERDICT|{event_code}|{inspector_email}|{decision}|{confidence:.4f}")
    verdict = InspectorVerdict(
        event_code=event_code,
        inspector_email=inspector_email,
        decision=decision,
        confidence=confidence,
        notes=notes,
        verdict_hash=v_hash,
    )
    db.session.add(verdict)
    db.session.flush()

    all_verdicts = InspectorVerdict.query.filter_by(event_code=event_code).all()
    supports = [v for v in all_verdicts if v.decision == "SUPPORT"]
    contradicts = [v for v in all_verdicts if v.decision == "CONTRADICT"]

    att = Attestation.query.filter_by(event_code=event_code).first()
    if len(supports) >= evt.quorum_required and evt.status == "PENDING_ATTESTATION":
        evt.status = "APPROVED"
        if att:
            att.quorum_met = True
            att.attestation_digest = sha256_hex(
                "|".join(sorted(v.verdict_hash for v in supports))
            )
            att.finalized_at = datetime.now(timezone.utc)
    elif len(contradicts) >= evt.quorum_required and evt.status == "PENDING_ATTESTATION":
        evt.status = "REJECTED"

    db.session.commit()

    # Anchor defect commitment on-chain once quorum approves (non-fatal if unavailable)
    if evt.status == "APPROVED" and not evt.onchain_tx_hash:
        try:
            anchor_defect_event_onchain(evt.event_code)
        except Exception:
            pass

    return evt.to_dict()


def anchor_defect_event_onchain(event_code: str) -> dict:
    evt = DefectEvent.query.filter_by(event_code=event_code).first()
    if not evt:
        raise ValueError(f"Defect event {event_code} not found")
    if evt.status not in ("APPROVED", "ANCHORED", "PROPAGATING", "COMPLETED", "REOPENED"):
        raise ValueError(f"Defect event {event_code} has not reached attestation quorum")

    cs = ContractService()
    if not cs.bc.is_connected():
        raise ValueError("Hardhat RPC offline; cannot anchor defect commitment on-chain")

    event_id_bytes = Web3.keccak(text=evt.event_code)
    lot_id_bytes = Web3.keccak(text=evt.lot_code)
    ev_bytes = bytes.fromhex(evt.evidence_root_hash.removeprefix("0x"))

    tx_hash = cs.submit_defect_commitment(
        event_id_bytes=event_id_bytes,
        lot_id_bytes=lot_id_bytes,
        snapshot_version=evt.snapshot_version,
        evidence_bytes=ev_bytes,
        severity=evt.severity,
    )
    ts = TransactionService()
    rec = ts.record_and_verify_transaction(
        tx_hash=tx_hash,
        contract_name="ManufacturingRegistry",
        function_name="registerDefectCommitment",
        reference_id=evt.event_code,
    )
    if rec.status == "CONFIRMED":
        evt.onchain_event_id = Web3.to_hex(event_id_bytes)
        evt.onchain_tx_hash = rec.tx_hash
        if evt.status == "APPROVED":
            evt.status = "ANCHORED"
        db.session.commit()

    return evt.to_dict()
