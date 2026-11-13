from web3 import Web3
from app import db
from app.models import PurchaseOrder, EscrowLedger
from app.blockchain.contract_service import ContractService
from app.blockchain.transaction_service import TransactionService
from app.services.audit_service import append_audit_entry


STATUS_MAP = {
    0: "NONE",
    1: "CREATED",
    2: "FUNDED",
    3: "SHIPPED",
    4: "RECEIVED",
    5: "QC_PASSED",
    6: "COMPLAINT",
    7: "DISPUTED",
    8: "SETTLED",
    9: "CLOSED",
}


def sync_escrow_from_chain(po_number: str, tx_hash: str | None = None) -> dict:
    cs = ContractService()
    escrow_id = Web3.keccak(text=po_number)
    escrow_hex = Web3.to_hex(escrow_id)

    if not cs.bc.is_connected():
        ledger = EscrowLedger.query.filter_by(po_number=po_number).first()
        if not ledger:
            raise ValueError(f"Hardhat offline and no cached escrow for {po_number}")
        return ledger.to_dict()

    contract = cs.get_contract("SupplyChainEscrow")
    data = contract.functions.getEscrow(escrow_id).call()
    valid, _, _ = contract.functions.checkConservationInvariant(escrow_id).call()

    ledger = EscrowLedger.query.filter_by(po_number=po_number).first()
    if not ledger:
        ledger = EscrowLedger(
            po_number=po_number,
            escrow_id_bytes32=escrow_hex,
            buyer_address=data[0],
            supplier_address=data[1],
            target_eth=str(Web3.from_wei(data[5], "ether")),
        )
        db.session.add(ledger)

    ledger.d_cum_eth = str(Web3.from_wei(data[6], "ether"))
    ledger.fa_eth = str(Web3.from_wei(data[7], "ether"))
    ledger.fr_eth = str(Web3.from_wei(data[8], "ether"))
    ledger.fd_eth = str(Web3.from_wei(data[9], "ether"))
    ledger.ps_eth = str(Web3.from_wei(data[10], "ether"))
    ledger.pb_eth = str(Web3.from_wei(data[11], "ether"))
    ledger.pc_eth = str(Web3.from_wei(data[12], "ether"))
    ledger.status = STATUS_MAP.get(data[13], "UNKNOWN")
    ledger.conservation_valid = bool(valid)
    if tx_hash:
        ledger.last_tx_hash = tx_hash

    po = PurchaseOrder.query.filter_by(po_number=po_number).first()
    if po:
        po.status = ledger.status

    db.session.commit()
    return ledger.to_dict()


def execute_escrow_action(
    po_number: str,
    action: str,
    actor_email: str,
    amount_eth: str | None = None,
    passed: bool = True,
    ref_text: str = "",
) -> dict:
    cs = ContractService()
    if not cs.bc.is_connected():
        raise ValueError("Hardhat node is offline")

    contract = cs.get_contract("SupplyChainEscrow")
    escrow_id = Web3.keccak(text=po_number)

    if action == "ship":
        fn = contract.functions.markShipment(escrow_id, Web3.keccak(text=ref_text or f"SHIP-{po_number}"))
        fn_name = "markShipment"
    elif action == "receive":
        fn = contract.functions.confirmReceipt(escrow_id, Web3.keccak(text=ref_text or f"RECV-{po_number}"))
        fn_name = "confirmReceipt"
    elif action == "qc":
        freeze_wei = Web3.to_wei(amount_eth or "0", "ether")
        fn = contract.functions.registerQcResult(escrow_id, passed, freeze_wei)
        fn_name = "registerQcResult"
    elif action == "warranty":
        fn = contract.functions.allocateWarrantyReserve(escrow_id, Web3.to_wei(amount_eth or "0.1", "ether"))
        fn_name = "allocateWarrantyReserve"
    elif action == "freeze":
        fn = contract.functions.freezeDisputedFunds(escrow_id, Web3.to_wei(amount_eth or "0.5", "ether"))
        fn_name = "freezeDisputedFunds"
    elif action == "release_supplier":
        fn = contract.functions.releaseSupplierPayment(escrow_id, Web3.to_wei(amount_eth or "0.5", "ether"))
        fn_name = "releaseSupplierPayment"
    elif action == "refund_buyer":
        fn = contract.functions.refundBuyer(escrow_id, Web3.to_wei(amount_eth or "0.2", "ether"))
        fn_name = "refundBuyer"
    elif action == "close":
        fn = contract.functions.closeEscrow(escrow_id)
        fn_name = "closeEscrow"
    else:
        raise ValueError(f"Unsupported escrow action: {action}")

    tx_hash = cs._send_operator_tx(fn)
    ts = TransactionService()
    rec = ts.record_and_verify_transaction(
        tx_hash=tx_hash,
        contract_name="SupplyChainEscrow",
        function_name=fn_name,
        reference_id=po_number,
    )
    if rec.status != "CONFIRMED":
        raise ValueError(f"On-chain transaction failed/reverted: {rec.error_message}")

    synced = sync_escrow_from_chain(po_number, tx_hash=rec.tx_hash)
    append_audit_entry(
        actor_email=actor_email,
        category="ESCROW",
        action=f"ESCROW_{action.upper()}",
        payload={"po_number": po_number, "amount_eth": amount_eth, "status": synced["status"]},
        onchain_tx_hash=rec.tx_hash,
    )
    return {"transaction": rec.to_dict(), "escrow": synced}
