from datetime import datetime, timezone
from app import db


def utcnow():
    return datetime.now(timezone.utc)


class EscrowLedger(db.Model):
    __tablename__ = "escrow_ledgers"
    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(64), unique=True, nullable=False)
    escrow_id_bytes32 = db.Column(db.String(66), unique=True, nullable=False)
    buyer_address = db.Column(db.String(64), nullable=False)
    supplier_address = db.Column(db.String(64), nullable=False)
    target_eth = db.Column(db.String(32), nullable=False)
    d_cum_eth = db.Column(db.String(32), default="0")
    fa_eth = db.Column(db.String(32), default="0")
    fr_eth = db.Column(db.String(32), default="0")
    fd_eth = db.Column(db.String(32), default="0")
    ps_eth = db.Column(db.String(32), default="0")
    pb_eth = db.Column(db.String(32), default="0")
    pc_eth = db.Column(db.String(32), default="0")
    status = db.Column(db.String(32), default="CREATED")
    conservation_valid = db.Column(db.Boolean, default=True)
    last_tx_hash = db.Column(db.String(66), nullable=True)
    updated_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "po_number": self.po_number,
            "escrow_id_bytes32": self.escrow_id_bytes32,
            "buyer_address": self.buyer_address,
            "supplier_address": self.supplier_address,
            "target_eth": self.target_eth,
            "buckets": {
                "D_cum": self.d_cum_eth,
                "Fa": self.fa_eth,
                "Fr": self.fr_eth,
                "Fd": self.fd_eth,
                "Ps": self.ps_eth,
                "Pb": self.pb_eth,
                "Pc": self.pc_eth,
            },
            "status": self.status,
            "conservation_valid": self.conservation_valid,
            "last_tx_hash": self.last_tx_hash,
        }


class Complaint(db.Model):
    __tablename__ = "complaints"
    id = db.Column(db.Integer, primary_key=True)
    claim_code = db.Column(db.String(64), unique=True, nullable=False)
    claim_id_bytes32 = db.Column(db.String(66), unique=True, nullable=False)
    po_number = db.Column(db.String(64), nullable=False)
    defect_event_code = db.Column(db.String(64), nullable=False)
    buyer_email = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    evidence_hash = db.Column(db.String(66), nullable=False)
    supplier_response = db.Column(db.Text, nullable=True)
    supplier_response_hash = db.Column(db.String(66), nullable=True)
    manufacturer_notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(32), default="OPEN")  # OPEN | RESPONDED | DISPUTED | AUTHORIZED | SETTLED
    register_tx_hash = db.Column(db.String(66), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "claim_code": self.claim_code,
            "claim_id_bytes32": self.claim_id_bytes32,
            "po_number": self.po_number,
            "defect_event_code": self.defect_event_code,
            "buyer_email": self.buyer_email,
            "description": self.description,
            "evidence_hash": self.evidence_hash,
            "supplier_response": self.supplier_response,
            "manufacturer_notes": self.manufacturer_notes,
            "status": self.status,
            "register_tx_hash": self.register_tx_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DisputeResolution(db.Model):
    __tablename__ = "dispute_resolutions"
    id = db.Column(db.Integer, primary_key=True)
    claim_code = db.Column(db.String(64), unique=True, nullable=False)
    arbitrator_email = db.Column(db.String(120), nullable=False)
    rationale = db.Column(db.Text, nullable=False)
    decision_commitment = db.Column(db.String(66), nullable=False)
    supplier_payout_eth = db.Column(db.String(32), nullable=False)
    buyer_refund_eth = db.Column(db.String(32), nullable=False)
    third_party_comp_eth = db.Column(db.String(32), default="0")
    third_party_recipient = db.Column(db.String(64), nullable=True)
    authorize_tx_hash = db.Column(db.String(66), nullable=True)
    settled = db.Column(db.Boolean, default=False)
    settlement_tx_hash = db.Column(db.String(66), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "claim_code": self.claim_code,
            "arbitrator_email": self.arbitrator_email,
            "rationale": self.rationale,
            "decision_commitment": self.decision_commitment,
            "supplier_payout_eth": self.supplier_payout_eth,
            "buyer_refund_eth": self.buyer_refund_eth,
            "third_party_comp_eth": self.third_party_comp_eth,
            "third_party_recipient": self.third_party_recipient,
            "authorize_tx_hash": self.authorize_tx_hash,
            "settled": self.settled,
            "settlement_tx_hash": self.settlement_tx_hash,
        }


class HashChainedAuditEntry(db.Model):
    """
    Off-chain tamper-evident SHA-256 hash-chained audit ledger.
    Explicitly distinguished from the decentralized EVM smart contract ledger.
    """
    __tablename__ = "hash_chained_audit_entries"
    id = db.Column(db.Integer, primary_key=True)
    sequence_num = db.Column(db.Integer, unique=True, nullable=False)
    actor_email = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(64), nullable=False)
    action = db.Column(db.String(120), nullable=False)
    payload_json = db.Column(db.Text, nullable=False)
    onchain_tx_hash = db.Column(db.String(66), nullable=True)
    prev_hash = db.Column(db.String(66), nullable=False)
    entry_hash = db.Column(db.String(66), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "sequence_num": self.sequence_num,
            "actor_email": self.actor_email,
            "category": self.category,
            "action": self.action,
            "payload_json": self.payload_json,
            "onchain_tx_hash": self.onchain_tx_hash,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
