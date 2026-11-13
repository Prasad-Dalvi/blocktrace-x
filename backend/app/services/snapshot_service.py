import json
from app import db
from app.models import (
    SupplierLot,
    ProductionBatch,
    DispatchOrder,
    GenealogyRelation,
    Snapshot,
    SnapshotNode,
    SnapshotRelation,
    SnapshotCommitment,
)
from app.services.merkle_service import sha256_hex, build_merkle_tree
from app.blockchain.contract_service import ContractService
from app.blockchain.transaction_service import TransactionService


def _canonical_nodes_and_edges():
    """
    Canonical encoding rules (deterministic lexicographical sorting):
    - Node key: '<TYPE>:<CODE>' sorted ascending by node_key.
    - Outgoing adjacency list per node sorted ascending by child_key.
    - Node leaf encoding: 'NODE|<version>|<node_key>|<out_degree>|<sorted_children_csv>'
    - Relation encoding: 'REL|<version>|<parent_key>|<child_key>|<qty:.6f>'
    """
    raw_nodes: dict[str, tuple[str, str]] = {}
    for lot in SupplierLot.query.all():
        raw_nodes[f"LOT:{lot.lot_code}"] = ("LOT", lot.lot_code)
    for batch in ProductionBatch.query.all():
        raw_nodes[f"BATCH:{batch.batch_code}"] = ("BATCH", batch.batch_code)
    for disp in DispatchOrder.query.all():
        raw_nodes[f"DISPATCH:{disp.dispatch_code}"] = ("DISPATCH", disp.dispatch_code)

    adj: dict[str, list[tuple[str, float]]] = {k: [] for k in raw_nodes}
    all_rels = GenealogyRelation.query.all()
    for r in all_rels:
        pk = f"{r.parent_type}:{r.parent_code}"
        ck = f"{r.child_type}:{r.child_code}"
        if pk in adj:
            adj[pk].append((ck, float(r.quantity_consumed)))

    for k in adj:
        adj[k].sort(key=lambda item: item[0])

    sorted_node_keys = sorted(raw_nodes.keys())
    sorted_edges = sorted(
        [
            (f"{r.parent_type}:{r.parent_code}", f"{r.child_type}:{r.child_code}", float(r.quantity_consumed))
            for r in all_rels
        ],
        key=lambda e: (e[0], e[1]),
    )
    return sorted_node_keys, raw_nodes, adj, sorted_edges


def seal_snapshot(
    sealed_by: str,
    version: int | None = None,
    anchor_onchain: bool = True,
) -> dict:
    latest = db.session.query(db.func.max(Snapshot.version)).scalar() or 0
    target_version = version if version is not None else latest + 1

    if Snapshot.query.filter_by(version=target_version).first():
        raise ValueError(f"Snapshot version {target_version} is immutable and already sealed")

    prev_snap = Snapshot.query.filter_by(version=target_version - 1).first()
    prev_root = prev_snap.global_root if prev_snap else "0x" + ("00" * 32)

    sorted_keys, raw_nodes, adj, sorted_edges = _canonical_nodes_and_edges()

    node_leaves: list[str] = []
    node_rows: list[SnapshotNode] = []
    for idx, nkey in enumerate(sorted_keys):
        ntype, ncode = raw_nodes[nkey]
        neighbors = adj[nkey]
        out_deg = len(neighbors)
        children_csv = ",".join(c[0] for c in neighbors)
        canonical_str = f"NODE|{target_version}|{nkey}|{out_deg}|{children_csv}"
        leaf_h = sha256_hex(canonical_str)
        node_leaves.append(leaf_h)
        node_rows.append(
            SnapshotNode(
                snapshot_version=target_version,
                canonical_index=idx,
                node_key=nkey,
                node_type=ntype,
                node_code=ncode,
                out_degree=out_deg,
                leaf_hash=leaf_h,
            )
        )

    rel_leaves: list[str] = []
    rel_rows: list[SnapshotRelation] = []
    for idx, (pk, ck, qty) in enumerate(sorted_edges):
        canonical_rel = f"REL|{target_version}|{pk}|{ck}|{qty:.6f}"
        rel_h = sha256_hex(canonical_rel)
        rel_leaves.append(rel_h)
        rel_rows.append(
            SnapshotRelation(
                snapshot_version=target_version,
                canonical_index=idx,
                parent_key=pk,
                child_key=ck,
                quantity_consumed=qty,
                relation_hash=rel_h,
            )
        )

    nodes_root, _ = build_merkle_tree(node_leaves)
    rels_root, _ = build_merkle_tree(rel_leaves)
    global_root = sha256_hex(f"GLOBAL|{target_version}|{nodes_root}|{rels_root}")
    chained_commitment = sha256_hex(f"CHAIN|{target_version}|{prev_root}|{global_root}")
    metadata_hash = sha256_hex(
        json.dumps(
            {
                "version": target_version,
                "nodes": len(node_rows),
                "relations": len(rel_rows),
                "nodes_root": nodes_root,
                "relations_root": rels_root,
            },
            sort_keys=True,
        )
    )

    snap = Snapshot(
        version=target_version,
        node_count=len(node_rows),
        relation_count=len(rel_rows),
        nodes_merkle_root=nodes_root,
        relations_merkle_root=rels_root,
        global_root=global_root,
        prev_global_root=prev_root,
        chained_commitment=chained_commitment,
        metadata_hash=metadata_hash,
        sealed_by=sealed_by,
    )
    db.session.add(snap)
    db.session.flush()
    db.session.add_all(node_rows)
    db.session.add_all(rel_rows)

    commitment_rec = SnapshotCommitment(
        snapshot_version=target_version,
        global_root=global_root,
        onchain_verified=False,
        verification_note="Sealed locally; awaiting on-chain anchor",
    )
    db.session.add(commitment_rec)
    db.session.commit()

    if anchor_onchain:
        cs = ContractService()
        if cs.bc.is_connected():
            try:
                tx_hash = cs.submit_backend_snapshot(target_version, global_root, metadata_hash)
                ts = TransactionService()
                tx_rec = ts.record_and_verify_transaction(
                    tx_hash=tx_hash,
                    contract_name="ManufacturingRegistry",
                    function_name="registerSnapshot",
                    reference_id=f"SNAPSHOT_V{target_version}",
                )
                onchain = cs.get_snapshot_onchain(target_version)
                matches = onchain["exists"] and (
                    onchain["root_hash"].lower() == global_root.lower()
                )
                commitment_rec.tx_hash = tx_rec.tx_hash
                commitment_rec.onchain_verified = matches
                commitment_rec.verification_note = (
                    "Consistent with on-chain ManufacturingRegistry commitment"
                    if matches
                    else "On-chain commitment mismatch"
                )
                db.session.commit()
            except Exception as exc:
                commitment_rec.verification_note = f"On-chain anchor skipped/failed: {exc}"
                db.session.commit()

    return {
        "snapshot": snap.to_dict(),
        "commitment": commitment_rec.to_dict(),
    }
