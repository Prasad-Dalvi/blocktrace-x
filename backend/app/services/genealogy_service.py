import hashlib
import json
import networkx as nx
from app import db
from app.models import (
    SupplierLot,
    ProductionBatch,
    DispatchOrder,
    GenealogyRelation,
)


def _node_key(node_type: str, code: str) -> str:
    return f"{node_type.upper()}:{code}"


def build_networkx_dag() -> nx.DiGraph:
    G = nx.DiGraph()
    for lot in SupplierLot.query.all():
        G.add_node(_node_key("LOT", lot.lot_code), type="LOT", code=lot.lot_code, risk=lot.risk_status)
    for batch in ProductionBatch.query.all():
        G.add_node(_node_key("BATCH", batch.batch_code), type="BATCH", code=batch.batch_code, qc=batch.qc_status, risk=batch.risk_status)
    for disp in DispatchOrder.query.all():
        G.add_node(_node_key("DISPATCH", disp.dispatch_code), type="DISPATCH", code=disp.dispatch_code, risk=disp.risk_status)

    for rel in GenealogyRelation.query.all():
        u = _node_key(rel.parent_type, rel.parent_code)
        v = _node_key(rel.child_type, rel.child_code)
        G.add_edge(u, v, quantity=rel.quantity_consumed, version=rel.snapshot_version)
    return G


def validate_and_create_relation(
    parent_type: str,
    parent_code: str,
    child_type: str,
    child_code: str,
    quantity_consumed: float,
    snapshot_version: int = 1,
) -> GenealogyRelation:
    if quantity_consumed <= 0:
        raise ValueError("Consumed quantity must be strictly positive")

    if parent_type == "LOT" and child_type != "BATCH":
        raise ValueError("Invalid relationship: Supplier LOT can only feed a Production BATCH")
    if parent_type == "BATCH" and child_type not in ("BATCH", "DISPATCH"):
        raise ValueError("Invalid relationship: Production BATCH can only feed another BATCH or DISPATCH")

    if parent_type == "LOT" and not SupplierLot.query.filter_by(lot_code=parent_code).first():
        raise ValueError(f"Parent lot {parent_code} does not exist")
    if parent_type == "BATCH" and not ProductionBatch.query.filter_by(batch_code=parent_code).first():
        raise ValueError(f"Parent batch {parent_code} does not exist")
    if child_type == "BATCH" and not ProductionBatch.query.filter_by(batch_code=child_code).first():
        raise ValueError(f"Child batch {child_code} does not exist")
    if child_type == "DISPATCH" and not DispatchOrder.query.filter_by(dispatch_code=child_code).first():
        raise ValueError(f"Child dispatch {child_code} does not exist")

    existing = GenealogyRelation.query.filter_by(
        parent_type=parent_type,
        parent_code=parent_code,
        child_type=child_type,
        child_code=child_code,
    ).first()
    if existing:
        raise ValueError(f"Duplicate relationship: {parent_code} -> {child_code} already exists")

    G = build_networkx_dag()
    u = _node_key(parent_type, parent_code)
    v = _node_key(child_type, child_code)
    if u == v:
        raise ValueError("Self-loop detected: parent and child cannot be identical")

    G.add_edge(u, v)
    if not nx.is_directed_acyclic_graph(G):
        raise ValueError(f"Cycle detected: adding {parent_code} -> {child_code} violates DAG acyclicity")

    rel = GenealogyRelation(
        parent_type=parent_type,
        parent_code=parent_code,
        child_type=child_type,
        child_code=child_code,
        quantity_consumed=quantity_consumed,
        snapshot_version=snapshot_version,
    )
    db.session.add(rel)
    db.session.commit()
    return rel


def trace_upstream_downstream(node_type: str, code: str) -> dict:
    G = build_networkx_dag()
    key = _node_key(node_type, code)
    if key not in G:
        raise ValueError(f"Node {key} not found in manufacturing graph")

    ancestors = sorted(list(nx.ancestors(G, key)))
    descendants = sorted(list(nx.descendants(G, key)))
    return {
        "node": key,
        "upstream_ancestors": ancestors,
        "downstream_descendants": descendants,
        "upstream_count": len(ancestors),
        "downstream_count": len(descendants),
    }


def compute_snapshot_merkle_root(version: int) -> tuple[str, str]:
    relations = (
        GenealogyRelation.query.filter(GenealogyRelation.snapshot_version <= version)
        .order_by(GenealogyRelation.id.asc())
        .all()
    )
    canonical_edges = [
        f"{r.parent_type}:{r.parent_code}->{r.child_type}:{r.child_code}:{r.quantity_consumed}"
        for r in relations
    ]
    if not canonical_edges:
        canonical_edges = ["GENESIS_EMPTY_GRAPH"]

    layer = [hashlib.sha256(e.encode("utf-8")).digest() for e in canonical_edges]
    while len(layer) > 1:
        next_layer = []
        for i in range(0, len(layer), 2):
            left = layer[i]
            right = layer[i + 1] if i + 1 < len(layer) else left
            next_layer.append(hashlib.sha256(left + right).digest())
        layer = next_layer

    root_hex = "0x" + layer[0].hex()
    meta_payload = json.dumps(
        {"version": version, "edge_count": len(relations)}, sort_keys=True
    ).encode("utf-8")
    meta_hex = "0x" + hashlib.sha256(meta_payload).hexdigest()
    return root_hex, meta_hex
