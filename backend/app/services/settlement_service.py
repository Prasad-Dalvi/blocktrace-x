from web3 import Web3
from app import db
from app.models import Complaint, DisputeResolution
from app.blockchain.contract_service import ContractService
from app.blockchain.transaction_service import TransactionService
from app.services.escrow_service import sync_escrow_from_chain
from app.services.audit_service import append_audit_entry


def execute_onchain_settlement(claim_code: str, actor_email: str) -> dict:
    comp = Complaint.query.filter_by(claim_code=claim_code).first()
    if not comp:
        raise ValueError(f"Complaint {claim_code} not found")

    res = DisputeResolution.query.filter_by(claim_code=claim_code).first()
    if not res:
        raise ValueError(f"No arbitration decision found for {claim_code}")
    if res.settled:
        raise ValueError(f"Idempotency guard: claim {claim_code} is already settled")

    cs = ContractService()
    if not cs.bc.is_connected():
        raise ValueError("Hardhat node offline; cannot execute on-chain settlement")

    contract = cs.get_contract("SupplyChainEscrow")
    escrow_id = Web3.keccak(text=comp.po_number)
    claim_id = Web3.keccak(text=claim_code)

    tx_hash = cs._send_operator_tx(contract.functions.settleClaim(escrow_id, claim_id))
    ts = TransactionService()
    tx_rec = ts.record_and_verify_transaction(
        tx_hash=tx_hash,
        contract_name="SupplyChainEscrow",
        function_name="settleClaim",
        reference_id=claim_code,
    )
    if tx_rec.status != "CONFIRMED":
        raise ValueError(f"On-chain settleClaim reverted: {tx_rec.error_message}")

    res.settled = True
    res.settlement_tx_hash = tx_rec.tx_hash
    comp.status = "SETTLED"
    db.session.commit()

    escrow_state = sync_escrow_from_chain(comp.po_number, tx_hash=tx_rec.tx_hash)
    append_audit_entry(
        actor_email=actor_email,
        category="SETTLEMENT",
        action="EXECUTE_SETTLEMENT",
        payload={"claim_code": claim_code, "po_number": comp.po_number, "escrow_status": escrow_state["status"]},
        onchain_tx_hash=tx_rec.tx_hash,
    )

    return {
        "resolution": res.to_dict(),
        "escrow": escrow_state,
        "transaction": tx_rec.to_dict(),
    }
