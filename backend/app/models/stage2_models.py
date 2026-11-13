from datetime import datetime, timezone
from app import db


def utcnow():
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------------------
# MODULE 1: AUTHENTICATED GRAPH SNAPSHOTS
# ------------------------------------------------------------------------------
class Snapshot(db.Model):
    __tablename__ = "snapshots"
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.Integer, unique=True, nullable=False)
    node_count = db.Column(db.Integer, nullable=False)
    relation_count = db.Column(db.Integer, nullable=False)
    nodes_merkle_root = db.Column(db.String(66), nullable=False)
    relations_merkle_root = db.Column(db.String(66), nullable=False)
    global_root = db.Column(db.String(66), nullable=False)
    prev_global_root = db.Column(db.String(66), nullable=False)
    chained_commitment = db.Column(db.String(66), nullable=False)
    metadata_hash = db.Column(db.String(66), nullable=False)
    sealed_by = db.Column(db.String(120), nullable=False)
    sealed_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "version": self.version,
            "node_count": self.node_count,
            "relation_count": self.relation_count,
            "nodes_merkle_root": self.nodes_merkle_root,
            "relations_merkle_root": self.relations_merkle_root,
            "global_root": self.global_root,
            "prev_global_root": self.prev_global_root,
            "chained_commitment": self.chained_commitment,
            "metadata_hash": self.metadata_hash,
            "sealed_by": self.sealed_by,
            "sealed_at": self.sealed_at.isoformat() if self.sealed_at else None,
        }


class SnapshotNode(db.Model):
    __tablename__ = "snapshot_nodes"
    id = db.Column(db.Integer, primary_key=True)
    snapshot_version = db.Column(db.Integer, db.ForeignKey("snapshots.version"), nullable=False, index=True)
    canonical_index = db.Column(db.Integer, nullable=False)
    node_key = db.Column(db.String(96), nullable=False)
    node_type = db.Column(db.String(32), nullable=False)
    node_code = db.Column(db.String(64), nullable=False)
    out_degree = db.Column(db.Integer, nullable=False)
    leaf_hash = db.Column(db.String(66), nullable=False)


class SnapshotRelation(db.Model):
    __tablename__ = "snapshot_relations"
    id = db.Column(db.Integer, primary_key=True)
    snapshot_version = db.Column(db.Integer, db.ForeignKey("snapshots.version"), nullable=False, index=True)
    canonical_index = db.Column(db.Integer, nullable=False)
    parent_key = db.Column(db.String(96), nullable=False)
    child_key = db.Column(db.String(96), nullable=False)
    quantity_consumed = db.Column(db.Float, nullable=False)
    relation_hash = db.Column(db.String(66), nullable=False)


class SnapshotCommitment(db.Model):
    __tablename__ = "snapshot_commitments"
    id = db.Column(db.Integer, primary_key=True)
    snapshot_version = db.Column(db.Integer, db.ForeignKey("snapshots.version"), unique=True, nullable=False)
    global_root = db.Column(db.String(66), nullable=False)
    tx_hash = db.Column(db.String(66), nullable=True)
    onchain_verified = db.Column(db.Boolean, default=False)
    verification_note = db.Column(db.Text, nullable=True)
    anchored_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "snapshot_version": self.snapshot_version,
            "global_root": self.global_root,
            "tx_hash": self.tx_hash,
            "onchain_verified": self.onchain_verified,
            "verification_note": self.verification_note,
            "anchored_at": self.anchored_at.isoformat() if self.anchored_at else None,
        }


# ------------------------------------------------------------------------------
# MODULE 2: DEFECT EVENTS & INSPECTOR ATTESTATION
# ------------------------------------------------------------------------------
class DefectEvent(db.Model):
    """
    Research tuple: e = (id, lot, g, c(g), ev, S)
    """
    __tablename__ = "defect_events"
    id = db.Column(db.Integer, primary_key=True)
    event_code = db.Column(db.String(64), unique=True, nullable=False)
    lot_code = db.Column(db.String(64), nullable=False)
    snapshot_version = db.Column(db.Integer, nullable=False)
    snapshot_commitment = db.Column(db.String(66), nullable=False)  # c(g)
    evidence_root_hash = db.Column(db.String(66), nullable=False)   # ev
    severity = db.Column(db.Integer, nullable=False)                # S in {1..5}
    status = db.Column(db.String(32), default="PENDING_ATTESTATION")
    # PENDING_ATTESTATION -> APPROVED -> ANCHORED -> PROPAGATING -> COMPLETED -> REOPENED
    quorum_required = db.Column(db.Integer, default=2)
    challenge_window_seconds = db.Column(db.Integer, default=300)
    challenge_deadline = db.Column(db.DateTime, nullable=True)
    onchain_event_id = db.Column(db.String(66), nullable=True)
    onchain_tx_hash = db.Column(db.String(66), nullable=True)
    created_by = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        support_count = sum(1 for v in self.verdicts if v.decision == "SUPPORT")
        contradict_count = sum(1 for v in self.verdicts if v.decision == "CONTRADICT")
        return {
            "id": self.id,
            "event_code": self.event_code,
            "lot_code": self.lot_code,
            "snapshot_version": self.snapshot_version,
            "snapshot_commitment": self.snapshot_commitment,
            "evidence_root_hash": self.evidence_root_hash,
            "severity": self.severity,
            "status": self.status,
            "quorum_required": self.quorum_required,
            "support_count": support_count,
            "contradict_count": contradict_count,
            "challenge_window_seconds": self.challenge_window_seconds,
            "challenge_deadline": self.challenge_deadline.isoformat() if self.challenge_deadline else None,
            "onchain_event_id": self.onchain_event_id,
            "onchain_tx_hash": self.onchain_tx_hash,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Evidence(db.Model):
    __tablename__ = "defect_evidence"
    id = db.Column(db.Integer, primary_key=True)
    event_code = db.Column(db.String(64), db.ForeignKey("defect_events.event_code"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(120), default="application/json")
    raw_payload = db.Column(db.Text, nullable=False)
    sha256_hash = db.Column(db.String(66), nullable=False)
    uploaded_by = db.Column(db.String(120), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=utcnow)


class Attestation(db.Model):
    __tablename__ = "attestations"
    id = db.Column(db.Integer, primary_key=True)
    event_code = db.Column(db.String(64), db.ForeignKey("defect_events.event_code"), unique=True, nullable=False)
    quorum_met = db.Column(db.Boolean, default=False)
    attestation_digest = db.Column(db.String(66), nullable=False)
    finalized_at = db.Column(db.DateTime, nullable=True)


class InspectorVerdict(db.Model):
    __tablename__ = "inspector_verdicts"
    id = db.Column(db.Integer, primary_key=True)
    event_code = db.Column(db.String(64), db.ForeignKey("defect_events.event_code"), nullable=False)
    event = db.relationship("DefectEvent", backref="verdicts")
    inspector_email = db.Column(db.String(120), nullable=False)
    decision = db.Column(db.String(16), nullable=False)  # SUPPORT | CONTRADICT
    confidence = db.Column(db.Float, default=0.95)
    notes = db.Column(db.Text)
    verdict_hash = db.Column(db.String(66), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    __table_args__ = (
        db.UniqueConstraint("event_code", "inspector_email", name="uq_inspector_event_verdict"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "event_code": self.event_code,
            "inspector_email": self.inspector_email,
            "decision": self.decision,
            "confidence": self.confidence,
            "notes": self.notes,
            "verdict_hash": self.verdict_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ------------------------------------------------------------------------------
# MODULE 3: BOUNDED DEFECT PROPAGATION & CURSOR kappa = (head, tail, u, delta, lambda)
# ------------------------------------------------------------------------------
class PropagationState(db.Model):
    __tablename__ = "propagation_states"
    id = db.Column(db.Integer, primary_key=True)
    event_code = db.Column(db.String(64), unique=True, nullable=False)
    snapshot_version = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(32), default="READY")  # READY | PAUSED | COMPLETED | REOPENED

    # Fixed-size cursor kappa = (head, tail, u, delta, lambda)
    cursor_head = db.Column(db.Integer, default=0)
    cursor_tail = db.Column(db.Integer, default=0)
    cursor_u = db.Column(db.String(96), default="")       # Current node being scanned
    cursor_delta = db.Column(db.Integer, default=0)       # Adjacency offset in u's outgoing edges
    cursor_lambda = db.Column(db.Integer, default=0)      # Monotonic segment sequence number

    # Cumulative consumption across segments
    total_nodes_visited = db.Column(db.Integer, default=0)
    total_relations_scanned = db.Column(db.Integer, default=0)
    total_classifications = db.Column(db.Integer, default=0)

    state_commitment = db.Column(db.String(66), nullable=False)
    onchain_tx_hash = db.Column(db.String(66), nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "event_code": self.event_code,
            "snapshot_version": self.snapshot_version,
            "status": self.status,
            "cursor": {
                "head": self.cursor_head,
                "tail": self.cursor_tail,
                "u": self.cursor_u,
                "delta": self.cursor_delta,
                "lambda": self.cursor_lambda,
            },
            "totals": {
                "nodes_visited": self.total_nodes_visited,
                "relations_scanned": self.total_relations_scanned,
                "classifications": self.total_classifications,
            },
            "state_commitment": self.state_commitment,
            "onchain_tx_hash": self.onchain_tx_hash,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class PropagationQueueItem(db.Model):
    __tablename__ = "propagation_queue_items"
    id = db.Column(db.Integer, primary_key=True)
    event_code = db.Column(db.String(64), nullable=False, index=True)
    queue_index = db.Column(db.Integer, nullable=False)
    node_key = db.Column(db.String(96), nullable=False)
    depth = db.Column(db.Integer, default=0)
    source_path = db.Column(db.Text, default="")
    enqueued_via = db.Column(db.String(32), default="SNAPSHOT")  # SNAPSHOT | LATE_EDGE
    processed = db.Column(db.Boolean, default=False)

    __table_args__ = (
        db.UniqueConstraint("event_code", "queue_index", name="uq_prop_queue_idx"),
    )


class ProcessedUnit(db.Model):
    __tablename__ = "processed_units"
    id = db.Column(db.Integer, primary_key=True)
    event_code = db.Column(db.String(64), nullable=False, index=True)
    node_key = db.Column(db.String(96), nullable=False)
    node_type = db.Column(db.String(32), nullable=False)
    node_code = db.Column(db.String(64), nullable=False)
    classification = db.Column(db.String(32), default="AFFECTED")
    adjacency_complete = db.Column(db.Boolean, default=False)
    segment_lambda = db.Column(db.Integer, nullable=False)
    provenance_paths = db.Column(db.Text, default="[]")
    created_at = db.Column(db.DateTime, default=utcnow)

    __table_args__ = (
        db.UniqueConstraint("event_code", "node_key", name="uq_processed_event_node"),
    )

    def to_dict(self):
        return {
            "event_code": self.event_code,
            "node_key": self.node_key,
            "node_type": self.node_type,
            "node_code": self.node_code,
            "classification": self.classification,
            "adjacency_complete": self.adjacency_complete,
            "segment_lambda": self.segment_lambda,
            "provenance_paths": self.provenance_paths,
        }


class ContinuationHistory(db.Model):
    __tablename__ = "continuation_history"
    id = db.Column(db.Integer, primary_key=True)
    event_code = db.Column(db.String(64), nullable=False, index=True)
    segment_lambda = db.Column(db.Integer, nullable=False)
    budget_k = db.Column(db.Integer, nullable=False)
    budget_m = db.Column(db.Integer, nullable=False)
    budget_z = db.Column(db.Integer, nullable=False)
    used_k = db.Column(db.Integer, nullable=False)
    used_m = db.Column(db.Integer, nullable=False)
    used_z = db.Column(db.Integer, nullable=False)
    stop_reason = db.Column(db.String(64), nullable=False)
    cursor_before = db.Column(db.Text, nullable=False)
    cursor_after = db.Column(db.Text, nullable=False)
    state_commitment = db.Column(db.String(66), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "event_code": self.event_code,
            "segment_lambda": self.segment_lambda,
            "budgets": {"K": self.budget_k, "M": self.budget_m, "Z": self.budget_z},
            "consumed": {"K": self.used_k, "M": self.used_m, "Z": self.used_z},
            "stop_reason": self.stop_reason,
            "cursor_before": self.cursor_before,
            "cursor_after": self.cursor_after,
            "state_commitment": self.state_commitment,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ------------------------------------------------------------------------------
# MODULE 4: ACTIVE LATE-EDGE GATE
# ------------------------------------------------------------------------------
class LateEdge(db.Model):
    __tablename__ = "late_edges"
    id = db.Column(db.Integer, primary_key=True)
    event_code = db.Column(db.String(64), nullable=False, index=True)
    parent_key = db.Column(db.String(96), nullable=False)
    child_key = db.Column(db.String(96), nullable=False)
    quantity_consumed = db.Column(db.Float, nullable=False)
    recorded_at_version = db.Column(db.Integer, nullable=False)
    delay_seconds = db.Column(db.Integer, default=0)
    within_gate = db.Column(db.Boolean, default=True)
    status = db.Column(db.String(32), default="PENDING")  # PENDING | ENQUEUED | IGNORED_OUT_OF_WINDOW
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "event_code": self.event_code,
            "parent_key": self.parent_key,
            "child_key": self.child_key,
            "quantity_consumed": self.quantity_consumed,
            "recorded_at_version": self.recorded_at_version,
            "delay_seconds": self.delay_seconds,
            "within_gate": self.within_gate,
            "status": self.status,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ------------------------------------------------------------------------------
# MODULE 5 & 6: UNIT-LEVEL EXPOSURE & BAYESIAN RISK ASSESSMENT
# ------------------------------------------------------------------------------
class ExposureRecord(db.Model):
    __tablename__ = "exposure_records"
    id = db.Column(db.Integer, primary_key=True)
    event_code = db.Column(db.String(64), nullable=False, index=True)
    node_key = db.Column(db.String(96), nullable=False)
    node_type = db.Column(db.String(32), nullable=False)
    node_code = db.Column(db.String(64), nullable=False)
    source_lot = db.Column(db.String(64), nullable=False)
    affected_units = db.Column(db.Float, nullable=False)
    total_units = db.Column(db.Float, nullable=False)
    exposure_fraction = db.Column(db.Float, nullable=False)  # X_l(v) in [0, 1]
    exposure_tier = db.Column(db.String(24), nullable=False)  # FULL | PARTIAL | NONE
    provenance_explanation = db.Column(db.Text, nullable=False)
    computed_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "event_code": self.event_code,
            "node_key": self.node_key,
            "node_type": self.node_type,
            "node_code": self.node_code,
            "source_lot": self.source_lot,
            "affected_units": self.affected_units,
            "total_units": self.total_units,
            "exposure_fraction": round(self.exposure_fraction, 6),
            "exposure_pct": round(self.exposure_fraction * 100.0, 2),
            "exposure_tier": self.exposure_tier,
            "provenance_explanation": self.provenance_explanation,
        }


class RiskAssessment(db.Model):
    __tablename__ = "risk_assessments"
    id = db.Column(db.Integer, primary_key=True)
    event_code = db.Column(db.String(64), nullable=False, index=True)
    node_key = db.Column(db.String(96), nullable=False)
    severity_s = db.Column(db.Float, nullable=False)
    criticality_c = db.Column(db.Float, nullable=False)
    exposure_x = db.Column(db.Float, nullable=False)
    prior_prob = db.Column(db.Float, nullable=False)
    likelihood_ratio_prod = db.Column(db.Float, nullable=False)
    posterior_odds = db.Column(db.Float, nullable=False)
    posterior_prob = db.Column(db.Float, nullable=False)
    risk_score = db.Column(db.Float, nullable=False)
    classification = db.Column(db.String(32), nullable=False)  # MONITOR | INSPECT | QUARANTINE | RECALL_CANDIDATE
    report_hash = db.Column(db.String(66), nullable=False)
    onchain_tx_hash = db.Column(db.String(66), nullable=True)
    computed_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "event_code": self.event_code,
            "node_key": self.node_key,
            "inputs": {
                "S": self.severity_s,
                "C_v": self.criticality_c,
                "X_l_v": round(self.exposure_x, 6),
                "prior_P_D": round(self.prior_prob, 6),
                "LR_product": round(self.likelihood_ratio_prod, 6),
                "posterior_odds": round(self.posterior_odds, 6),
                "posterior_P_D_given_E": round(self.posterior_prob, 6),
            },
            "risk_score": round(self.risk_score, 4),
            "classification": self.classification,
            "report_hash": self.report_hash,
            "onchain_tx_hash": self.onchain_tx_hash,
        }
