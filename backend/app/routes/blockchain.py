from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from app.models import BlockchainTransaction, PurchaseOrder
from app.schemas.validation import RecordTxSchema
from app.blockchain.blockchain_service import BlockchainService
from app.blockchain.contract_service import ContractService
from app.blockchain.transaction_service import TransactionService
from app.services.genealogy_service import compute_snapshot_merkle_root
from app.utils.rbac import roles_required

bc_bp = Blueprint("blockchain", __name__)


@bc_bp.get("/status")
@jwt_required()
def network_status():
    bc = BlockchainService()
    status = bc.get_network_status()
    deployments = bc.load_deployments()
    contracts = {}
    if deployments:
        for name, info in deployments.get("contracts", {}).items():
            contracts[name] = {
                "address": info["address"],
                "abi": info["abi"],
            }
    return jsonify(
        {
            "network": status,
            "contracts": contracts,
            "accounts": deployments.get("accounts", {}) if deployments else {},
        }
    )


@bc_bp.get("/transactions")
@jwt_required()
def list_transactions():
    txs = BlockchainTransaction.query.order_by(BlockchainTransaction.id.desc()).all()
    return jsonify([t.to_dict() for t in txs])


@bc_bp.post("/transactions/record")
@jwt_required()
def record_transaction():
    try:
        data = RecordTxSchema(**(request.get_json() or {}))
    except ValidationError as exc:
        return jsonify({"error": exc.errors()}), 400

    svc = TransactionService()
    rec = svc.record_and_verify_transaction(
        tx_hash=data.tx_hash,
        contract_name=data.contract_name,
        function_name=data.function_name,
        sender_address=data.sender_address,
        reference_id=data.reference_id,
    )
    return jsonify(rec.to_dict()), 201


@bc_bp.get("/snapshot/prepare/<int:version>")
@jwt_required()
def prepare_snapshot(version: int):
    root_hex, meta_hex = compute_snapshot_merkle_root(version)
    return jsonify(
        {
            "version": version,
            "root_hash": root_hex,
            "metadata_hash": meta_hex,
        }
    )


@bc_bp.post("/snapshot/anchor/<int:version>")
@roles_required("Manufacturer", "Admin")
def anchor_snapshot_backend(version: int):
    root_hex, meta_hex = compute_snapshot_merkle_root(version)
    cs = ContractService()
    tx_hash = cs.submit_backend_snapshot(version, root_hex, meta_hex)
    ts = TransactionService()
    rec = ts.record_and_verify_transaction(
        tx_hash=tx_hash,
        contract_name="ManufacturingRegistry",
        function_name="registerSnapshot",
        reference_id=f"SNAPSHOT_V{version}",
    )
    return jsonify(
        {
            "version": version,
            "root_hash": root_hex,
            "metadata_hash": meta_hex,
            "transaction": rec.to_dict(),
        }
    )


@bc_bp.get("/snapshot/<int:version>")
@jwt_required()
def get_snapshot(version: int):
    cs = ContractService()
    return jsonify(cs.get_snapshot_onchain(version))


@bc_bp.get("/escrow/<po_number>")
@jwt_required()
def get_escrow(po_number: str):
    po = PurchaseOrder.query.filter_by(po_number=po_number).first()
    cs = ContractService()
    onchain = cs.get_escrow_onchain(po_number)
    return jsonify(
        {
            "purchase_order": po.to_dict() if po else None,
            "onchain_escrow": onchain,
        }
    )
