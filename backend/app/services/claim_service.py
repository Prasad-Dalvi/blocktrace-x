from web3 import Web3
from app import db
from app.models import Complaint
from app.services.merkle_service import sha256_hex
from app.blockchain.contract_service import ContractService
from app.blockchain.transaction_service import TransactionService
from app.services.audit_service import append_audit_entry


def file_buyer_complaint(
    claim_code: str,
    po_number: str,
    defect_event_code: str,
    buyer_email: str,
    description: str,
    evidence_text: str,
) -> dict:
    if Complaint.query.filter_by(claim_code=claim_code).first():
        raise ValueError(f"Duplicate claim code: {claim_code}")

    claim_id_bytes = Web3.keccak(text=claim_code)
    escrow_id_bytes = Web3.keccak(text=po_number)
    defect_id_bytes = Web3.keccak(text=defect_event_code)
    ev_hash = sha256_hex(f"COMPLAINT|{claim_code}|{po_number}|{evidence_text}")
    ev_bytes = bytes.fromhex(ev_hash.removeprefix("0x"))

    tx_hash = None
    cs = ContractService()
    if cs.bc.is_connected():
        contract = cs.get_contract("ClaimRegistry")
        tx_hash = cs._send_operator_tx(
            contract.functions.registerClaim(
                claim_id_bytes, escrow_id_bytes, defect_id_bytes, ev_bytes
            )
        )
        ts = TransactionService()
        rec = ts.record_and_verify_transaction(
            tx_hash=tx_hash,
            contract_name="ClaimRegistry",
            function_name="registerClaim",
            reference_id=claim_code,
        )
        if rec.status != "CONFIRMED":
            raise ValueError(f"On-chain registerClaim reverted: {rec.error_message}")

    comp = Complaint(
        claim_code=claim_code,
        claim_id_bytes32=Web3.to_hex(claim_id_bytes),
        po_number=po_number,
        defect_event_code=defect_event_code,
        buyer_email=buyer_email,
        description=description,
        evidence_hash=ev_hash,
        status="OPEN",
        register_tx_hash=tx_hash,
    )
    db.session.add(comp)
    db.session.commit()

    append_audit_entry(
        actor_email=buyer_email,
        category="COMPLAINT",
        action="REGISTER_COMPLAINT",
        payload={"claim_code": claim_code, "po_number": po_number},
        onchain_tx_hash=tx_hash,
    )
    return comp.to_dict()


def submit_supplier_response(
    claim_code: str,
    supplier_email: str,
    response_text: str,
    escalate_to_dispute: bool = True,
) -> dict:
    comp = Complaint.query.filter_by(claim_code=claim_code).first()
    if not comp:
        raise ValueError(f"Complaint {claim_code} not found")

    resp_hash = sha256_hex(f"RESPONSE|{claim_code}|{response_text}")
    resp_bytes = bytes.fromhex(resp_hash.removeprefix("0x"))

    tx_hash = None
    cs = ContractService()
    if cs.bc.is_connected():
        contract = cs.get_contract("ClaimRegistry")
        tx_hash = cs._send_operator_tx(
            contract.functions.submitSupplierResponse(
                Web3.keccak(text=claim_code), resp_bytes, escalate_to_dispute
            )
        )
        ts = TransactionService()
        rec = ts.record_and_verify_transaction(
            tx_hash=tx_hash,
            contract_name="ClaimRegistry",
            function_name="submitSupplierResponse",
            reference_id=claim_code,
        )
        if rec.status != "CONFIRMED":
            raise ValueError(f"On-chain submitSupplierResponse reverted: {rec.error_message}")

        if escalate_to_dispute:
            escrow_c = cs.get_contract("SupplyChainEscrow")
            esc_tx = cs._send_operator_tx(
                escrow_c.functions.escalateToDispute(
                    Web3.keccak(text=comp.po_number), Web3.keccak(text=claim_code)
                )
            )
            ts.record_and_verify_transaction(
                tx_hash=esc_tx,
                contract_name="SupplyChainEscrow",
                function_name="escalateToDispute",
                reference_id=comp.po_number,
            )

    comp.supplier_response = response_text
    comp.supplier_response_hash = resp_hash
    comp.status = "DISPUTED" if escalate_to_dispute else "RESPONDED"
    db.session.commit()

    append_audit_entry(
        actor_email=supplier_email,
        category="DISPUTE",
        action="SUPPLIER_RESPONSE",
        payload={"claim_code": claim_code, "disputed": escalate_to_dispute},
        onchain_tx_hash=tx_hash,
    )
    return comp.to_dict()
