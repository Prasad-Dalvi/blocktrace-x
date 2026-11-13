from app import db
from app.models import Snapshot, SnapshotNode, SnapshotRelation, SnapshotCommitment
from app.services.merkle_service import sha256_hex, build_merkle_tree
from app.blockchain.contract_service import ContractService


def verify_snapshot_integrity(version: int, expected_root: str | None = None) -> dict:
    snap = Snapshot.query.filter_by(version=version).first()
    if not snap:
        raise ValueError(f"Snapshot version {version} not found")

    nodes = (
        SnapshotNode.query.filter_by(snapshot_version=version)
        .order_by(SnapshotNode.canonical_index.asc())
        .all()
    )
    rels = (
        SnapshotRelation.query.filter_by(snapshot_version=version)
        .order_by(SnapshotRelation.canonical_index.asc())
        .all()
    )

    recomputed_nodes_root, _ = build_merkle_tree([n.leaf_hash for n in nodes])
    recomputed_rels_root, _ = build_merkle_tree([r.relation_hash for r in rels])
    recomputed_global = sha256_hex(
        f"GLOBAL|{version}|{recomputed_nodes_root}|{recomputed_rels_root}"
    )

    local_consistent = (
        recomputed_nodes_root == snap.nodes_merkle_root
        and recomputed_rels_root == snap.relations_merkle_root
        and recomputed_global == snap.global_root
    )

    if expected_root and expected_root.lower() != snap.global_root.lower():
        return {
            "version": version,
            "verified": False,
            "local_consistent": local_consistent,
            "reason": "Provided root hash does not match sealed snapshot global_root",
            "sealed_global_root": snap.global_root,
            "provided_root": expected_root,
        }

    onchain_match = None
    onchain_root = None
    cs = ContractService()
    if cs.bc.is_connected():
        try:
            onchain_data = cs.get_snapshot_onchain(version)
            if onchain_data["exists"]:
                onchain_root = onchain_data["root_hash"]
                onchain_match = onchain_root.lower() == snap.global_root.lower()
                comm = SnapshotCommitment.query.filter_by(snapshot_version=version).first()
                if comm:
                    comm.onchain_verified = bool(onchain_match)
                    db.session.commit()
        except Exception:
            onchain_match = None

    verified = local_consistent and (onchain_match is not False)
    return {
        "version": version,
        "verified": verified,
        "local_consistent": local_consistent,
        "onchain_match": onchain_match,
        "sealed_global_root": snap.global_root,
        "recomputed_global_root": recomputed_global,
        "onchain_root": onchain_root,
        "attestation_scope": "Cryptographic commitment verifies structural consistency with sealed representation, not physical sensor truthfulness.",
    }
