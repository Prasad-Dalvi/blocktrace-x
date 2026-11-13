import json
from datetime import datetime, timezone
from web3 import Web3
from app import db
from app.models import (
    DefectEvent,
    Snapshot,
    SnapshotNode,
    SnapshotRelation,
    PropagationState,
    PropagationQueueItem,
    ProcessedUnit,
    ContinuationHistory,
    LateEdge,
)
from app.services.merkle_service import sha256_hex, build_merkle_tree
from app.blockchain.contract_service import ContractService
from app.blockchain.transaction_service import TransactionService


def _compute_cursor_commitment(state: PropagationState) -> str:
    payload = (
        f"CURSOR|{state.event_code}|{state.snapshot_version}|{state.status}|"
        f"{state.cursor_head}|{state.cursor_tail}|{state.cursor_u}|"
        f"{state.cursor_delta}|{state.cursor_lambda}"
    )
    return sha256_hex(payload)


def start_propagation(event_code: str) -> dict:
    evt = DefectEvent.query.filter_by(event_code=event_code).first()
    if not evt:
        raise ValueError(f"Defect event {event_code} not found")
    if evt.status not in ("APPROVED", "ANCHORED", "PROPAGATING", "REOPENED"):
        raise ValueError(f"Defect event {event_code} must be APPROVED before propagation")

    existing = PropagationState.query.filter_by(event_code=event_code).first()
    if existing:
        return existing.to_dict()

    snap = Snapshot.query.filter_by(version=evt.snapshot_version).first()
    if not snap:
        raise ValueError(f"Snapshot version {evt.snapshot_version} not found")

    root_node_key = f"LOT:{evt.lot_code}"
    snap_node = SnapshotNode.query.filter_by(
        snapshot_version=evt.snapshot_version, node_key=root_node_key
    ).first()
    if not snap_node:
        raise ValueError(f"Source node {root_node_key} absent in snapshot v{evt.snapshot_version}")

    q0 = PropagationQueueItem(
        event_code=event_code,
        queue_index=0,
        node_key=root_node_key,
        depth=0,
        source_path=root_node_key,
        enqueued_via="SNAPSHOT",
        processed=False,
    )
    db.session.add(q0)

    state = PropagationState(
        event_code=event_code,
        snapshot_version=evt.snapshot_version,
        status="READY",
        cursor_head=0,
        cursor_tail=1,
        cursor_u=root_node_key,
        cursor_delta=0,
        cursor_lambda=0,
        state_commitment="0x" + ("00" * 32),
    )
    state.state_commitment = _compute_cursor_commitment(state)
    evt.status = "PROPAGATING"
    db.session.add(state)
    db.session.commit()
    return state.to_dict()


def continue_propagation(
    event_code: str,
    budget_k: int = 5,
    budget_m: int = 10,
    budget_z: int = 5,
    expected_lambda: int | None = None,
    expected_commitment: str | None = None,
) -> dict:
    """
    Executes one bounded traversal segment enforcing three independent budgets:
      K: node visits
      M: relation scans
      Z: classification touches
    Resumes strictly from fixed-size cursor kappa = (head, tail, u, delta, lambda).
    """
    if budget_k <= 0 or budget_m <= 0 or budget_z <= 0:
        raise ValueError("Budgets K, M, Z must all be positive integers")

    # Row-level lock / optimistic concurrency validation
    state = (
        PropagationState.query.filter_by(event_code=event_code)
        .with_for_update()
        .first()
    )
    if not state:
        raise ValueError(f"Propagation state for {event_code} not initialized")

    evt = DefectEvent.query.filter_by(event_code=event_code).first()
    if not evt or evt.snapshot_version != state.snapshot_version:
        raise ValueError("Event identity or snapshot version mismatch")

    if expected_lambda is not None and expected_lambda != state.cursor_lambda:
        raise ValueError(
            f"Stale cursor rejected: expected lambda={expected_lambda}, current lambda={state.cursor_lambda}"
        )

    recomputed_comm = _compute_cursor_commitment(state)
    if recomputed_comm != state.state_commitment:
        raise ValueError("Cursor state commitment integrity failure")
    if expected_commitment and expected_commitment.lower() != state.state_commitment.lower():
        raise ValueError("Stale state commitment provided by caller")

    if state.status == "COMPLETED":
        # Check if any pending late edges exist before allowing completion
        pending_le = LateEdge.query.filter_by(event_code=event_code, status="PENDING").count()
        if pending_le == 0:
            return {
                "state": state.to_dict(),
                "segment_consumed": {"K": 0, "M": 0, "Z": 0},
                "stop_reason": "ALREADY_COMPLETED",
            }
        state.status = "REOPENED"

    cursor_before = json.dumps(state.to_dict()["cursor"])
    used_k = 0
    used_m = 0
    used_z = 0
    stop_reason = "QUEUE_EXHAUSTED"

    while state.cursor_head < state.cursor_tail:
        q_item = PropagationQueueItem.query.filter_by(
            event_code=event_code, queue_index=state.cursor_head
        ).first()
        if not q_item:
            state.cursor_head += 1
            continue

        u_key = q_item.node_key
        if state.cursor_u != u_key:
            state.cursor_u = u_key
            state.cursor_delta = 0

        # Starting or resuming node visit consumes K if delta == 0
        if state.cursor_delta == 0:
            if used_k >= budget_k:
                stop_reason = "BUDGET_K_EXHAUSTED"
                break
            used_k += 1

        # Classify node u if not yet classified
        proc_u = ProcessedUnit.query.filter_by(
            event_code=event_code, node_key=u_key
        ).first()
        if not proc_u:
            if used_z >= budget_z:
                stop_reason = "BUDGET_Z_EXHAUSTED"
                break
            used_z += 1
            ntype, ncode = u_key.split(":", 1)
            proc_u = ProcessedUnit(
                event_code=event_code,
                node_key=u_key,
                node_type=ntype,
                node_code=ncode,
                classification="AFFECTED",
                adjacency_complete=False,
                segment_lambda=state.cursor_lambda + 1,
                provenance_paths=json.dumps([q_item.source_path]),
            )
            db.session.add(proc_u)
            db.session.flush()
        else:
            # Multi-path deduplication: append novel provenance path without duplicate classification
            paths = json.loads(proc_u.provenance_paths or "[]")
            if q_item.source_path and q_item.source_path not in paths:
                paths.append(q_item.source_path)
                proc_u.provenance_paths = json.dumps(paths)

        # Build canonical outgoing adjacency list for u: SnapshotRelations + enqueued LateEdges
        snap_rels = (
            SnapshotRelation.query.filter_by(
                snapshot_version=state.snapshot_version, parent_key=u_key
            )
            .order_by(SnapshotRelation.canonical_index.asc())
            .all()
        )
        late_rels = (
            LateEdge.query.filter_by(
                event_code=event_code, parent_key=u_key, within_gate=True
            )
            .order_by(LateEdge.id.asc())
            .all()
        )

        outgoing: list[tuple[str, str]] = [(r.child_key, "SNAPSHOT") for r in snap_rels]
        for lr in late_rels:
            if not any(o[0] == lr.child_key for o in outgoing):
                outgoing.append((lr.child_key, "LATE_EDGE"))
            if lr.status == "PENDING":
                lr.status = "ENQUEUED"

        # Scan outgoing relations starting from cursor_delta
        budget_hit = False
        while state.cursor_delta < len(outgoing):
            if used_m >= budget_m:
                stop_reason = "BUDGET_M_EXHAUSTED"
                budget_hit = True
                break

            child_key, via = outgoing[state.cursor_delta]
            used_m += 1
            state.cursor_delta += 1

            # Enqueue child if not already queued
            already_queued = PropagationQueueItem.query.filter_by(
                event_code=event_code, node_key=child_key
            ).first()
            if not already_queued:
                new_path = f"{q_item.source_path} -> {child_key}"
                new_item = PropagationQueueItem(
                    event_code=event_code,
                    queue_index=state.cursor_tail,
                    node_key=child_key,
                    depth=q_item.depth + 1,
                    source_path=new_path,
                    enqueued_via=via,
                    processed=False,
                )
                db.session.add(new_item)
                state.cursor_tail += 1

        if budget_hit:
            break

        # Adjacency scan for u is now complete -> mark unit fully processed & advance head
        proc_u.adjacency_complete = True
        q_item.processed = True
        state.cursor_head += 1
        state.cursor_delta = 0
        if state.cursor_head < state.cursor_tail:
            nxt = PropagationQueueItem.query.filter_by(
                event_code=event_code, queue_index=state.cursor_head
            ).first()
            state.cursor_u = nxt.node_key if nxt else ""
        else:
            state.cursor_u = ""

    # Update monotonic segment counter & cumulative stats
    state.cursor_lambda += 1
    state.total_nodes_visited += used_k
    state.total_relations_scanned += used_m
    state.total_classifications += used_z

    # Completion guard: cannot complete if queue has items or pending late edges remain
    pending_late_edges = LateEdge.query.filter_by(
        event_code=event_code, status="PENDING", within_gate=True
    ).count()

    if state.cursor_head >= state.cursor_tail and pending_late_edges == 0:
        state.status = "COMPLETED"
        state.completed_at = datetime.now(timezone.utc)
        evt.status = "COMPLETED"
    else:
        state.status = "PAUSED"

    state.state_commitment = _compute_cursor_commitment(state)
    cursor_after = json.dumps(state.to_dict()["cursor"])

    hist = ContinuationHistory(
        event_code=event_code,
        segment_lambda=state.cursor_lambda,
        budget_k=budget_k,
        budget_m=budget_m,
        budget_z=budget_z,
        used_k=used_k,
        used_m=used_m,
        used_z=used_z,
        stop_reason=stop_reason,
        cursor_before=cursor_before,
        cursor_after=cursor_after,
        state_commitment=state.state_commitment,
    )
    db.session.add(hist)
    db.session.commit()

    # Anchor propagation completion commitment on-chain when completed
    if state.status == "COMPLETED" and evt.onchain_tx_hash:
        _anchor_propagation_completion(state)

    return {
        "state": state.to_dict(),
        "segment_consumed": {"K": used_k, "M": used_m, "Z": used_z},
        "stop_reason": stop_reason,
    }


def _anchor_propagation_completion(state: PropagationState):
    cs = ContractService()
    if not cs.bc.is_connected():
        return
    affected = (
        ProcessedUnit.query.filter_by(event_code=state.event_code)
        .order_by(ProcessedUnit.node_key.asc())
        .all()
    )
    leaves = [sha256_hex(f"AFFECTED|{state.event_code}|{a.node_key}") for a in affected]
    affected_root, _ = build_merkle_tree(leaves)
    try:
        tx_hash = cs.submit_propagation_commitment(
            event_id_bytes=Web3.keccak(text=state.event_code),
            snapshot_version=state.snapshot_version,
            cursor_bytes=bytes.fromhex(state.state_commitment.removeprefix("0x")),
            affected_root_bytes=bytes.fromhex(affected_root.removeprefix("0x")),
            affected_count=len(affected),
        )
        ts = TransactionService()
        rec = ts.record_and_verify_transaction(
            tx_hash=tx_hash,
            contract_name="ManufacturingRegistry",
            function_name="registerPropagationCommitment",
            reference_id=state.event_code,
        )
        if rec.status == "CONFIRMED":
            state.onchain_tx_hash = rec.tx_hash
            db.session.commit()
    except Exception:
        pass
