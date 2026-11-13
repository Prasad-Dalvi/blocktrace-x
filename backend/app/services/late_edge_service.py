from datetime import datetime, timezone
from app import db
from app.models import (
    DefectEvent,
    PropagationState,
    PropagationQueueItem,
    ProcessedUnit,
    LateEdge,
)
from app.services.genealogy_service import validate_and_create_relation
from app.services.propagation_service import _compute_cursor_commitment


def register_late_edge_and_check_gate(
    parent_type: str,
    parent_code: str,
    child_type: str,
    child_code: str,
    quantity_consumed: float,
    recorded_at_version: int,
    delay_seconds: int = 30,
    a_max_versions: int = 2,
    t_late_seconds: int = 3600,
) -> dict:
    """
    Module 4: Active Late-Edge Gate.
    1. Persists the new downstream relation in the live manufacturing DAG.
    2. Queries ActiveEventMap (all DefectEvents where parent_key is affected or queued).
    3. Checks gate thresholds: (recorded_at_version - evt.snapshot_version) <= Amax
       and delay_seconds <= Tlate.
    4. Logs LateEdge, inserts parent/child into persistent queue if needed, and
       reopens COMPLETED propagation states so subsequent continuations traverse it.
    """
    rel = validate_and_create_relation(
        parent_type=parent_type,
        parent_code=parent_code,
        child_type=child_type,
        child_code=child_code,
        quantity_consumed=quantity_consumed,
        snapshot_version=recorded_at_version,
    )

    parent_key = f"{parent_type.upper()}:{parent_code}"
    child_key = f"{child_type.upper()}:{child_code}"

    # ActiveEventMap lookup: find events where parent_key is already affected or queued
    candidate_events = (
        db.session.query(DefectEvent)
        .join(ProcessedUnit, ProcessedUnit.event_code == DefectEvent.event_code)
        .filter(ProcessedUnit.node_key == parent_key)
        .all()
    )

    triggered_events = []
    for evt in candidate_events:
        version_delta = recorded_at_version - evt.snapshot_version
        within_gate = (0 <= version_delta <= a_max_versions) and (delay_seconds <= t_late_seconds)

        le = LateEdge(
            event_code=evt.event_code,
            parent_key=parent_key,
            child_key=child_key,
            quantity_consumed=quantity_consumed,
            recorded_at_version=recorded_at_version,
            delay_seconds=delay_seconds,
            within_gate=within_gate,
            status="PENDING" if within_gate else "IGNORED_OUT_OF_WINDOW",
            note=(
                f"Gate OPEN (Δg={version_delta}<=Amax={a_max_versions}, delay={delay_seconds}s<=Tlate={t_late_seconds}s)"
                if within_gate
                else f"Gate CLOSED (Δg={version_delta}, delay={delay_seconds}s)"
            ),
        )
        db.session.add(le)
        db.session.flush()

        if within_gate:
            state = PropagationState.query.filter_by(event_code=evt.event_code).first()
            if state:
                # Re-enqueue parent_key (or directly enqueue child_key) if parent already finished scanning
                already_queued = PropagationQueueItem.query.filter_by(
                    event_code=evt.event_code, node_key=child_key
                ).first()
                if not already_queued:
                    q_item = PropagationQueueItem(
                        event_code=evt.event_code,
                        queue_index=state.cursor_tail,
                        node_key=child_key,
                        depth=1,
                        source_path=f"{parent_key} =[LATE_EDGE@g{recorded_at_version}]=> {child_key}",
                        enqueued_via="LATE_EDGE",
                        processed=False,
                    )
                    db.session.add(q_item)
                    if state.cursor_head == state.cursor_tail:
                        state.cursor_u = child_key
                        state.cursor_delta = 0
                    state.cursor_tail += 1

                le.status = "ENQUEUED"
                if state.status == "COMPLETED":
                    state.status = "REOPENED"
                    state.completed_at = None
                    evt.status = "REOPENED"
                state.state_commitment = _compute_cursor_commitment(state)

            triggered_events.append(evt.event_code)

    db.session.commit()
    return {
        "relation": rel.to_dict(),
        "triggered_events": triggered_events,
    }
