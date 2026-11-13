import json
from app import db
from app.models import HashChainedAuditEntry
from app.services.merkle_service import sha256_hex


def append_audit_entry(
    actor_email: str,
    category: str,
    action: str,
    payload: dict,
    onchain_tx_hash: str | None = None,
) -> HashChainedAuditEntry:
    last = (
        HashChainedAuditEntry.query.order_by(HashChainedAuditEntry.sequence_num.desc())
        .first()
    )
    seq = (last.sequence_num + 1) if last else 1
    prev_h = last.entry_hash if last else "0x" + ("00" * 32)
    payload_str = json.dumps(payload, sort_keys=True)
    entry_h = sha256_hex(
        f"AUDIT|{seq}|{actor_email}|{category}|{action}|{payload_str}|{onchain_tx_hash or ''}|{prev_h}"
    )
    rec = HashChainedAuditEntry(
        sequence_num=seq,
        actor_email=actor_email,
        category=category,
        action=action,
        payload_json=payload_str,
        onchain_tx_hash=onchain_tx_hash,
        prev_hash=prev_h,
        entry_hash=entry_h,
    )
    db.session.add(rec)
    db.session.commit()
    return rec


def verify_audit_ledger() -> dict:
    entries = (
        HashChainedAuditEntry.query.order_by(HashChainedAuditEntry.sequence_num.asc())
        .all()
    )
    expected_prev = "0x" + ("00" * 32)
    for idx, entry in enumerate(entries, start=1):
        if entry.sequence_num != idx:
            return {
                "valid": False,
                "checked_entries": len(entries),
                "broken_at_sequence": entry.sequence_num,
                "reason": f"Sequence gap/reordering detected at #{entry.sequence_num} (expected #{idx})",
            }
        if entry.prev_hash != expected_prev:
            return {
                "valid": False,
                "checked_entries": len(entries),
                "broken_at_sequence": entry.sequence_num,
                "reason": f"Previous hash mismatch at #{entry.sequence_num}",
            }
        recomputed = sha256_hex(
            f"AUDIT|{entry.sequence_num}|{entry.actor_email}|{entry.category}|{entry.action}|{entry.payload_json}|{entry.onchain_tx_hash or ''}|{entry.prev_hash}"
        )
        if recomputed != entry.entry_hash:
            return {
                "valid": False,
                "checked_entries": len(entries),
                "broken_at_sequence": entry.sequence_num,
                "reason": f"Payload tampering detected at #{entry.sequence_num}",
            }
        expected_prev = entry.entry_hash

    return {
        "valid": True,
        "checked_entries": len(entries),
        "head_hash": expected_prev,
        "ledger_type": "Off-chain SHA-256 tamper-evident audit chain (distinct from on-chain EVM contracts)",
    }
