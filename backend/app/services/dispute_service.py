from web3 import Web3
from app import db
from app.models import Complaint, DisputeResolution
from app.services.merkle_service import sha256_hex
from app.blockchain.contract_service import ContractService
from app.blockchain.transaction_service import TransactionService
from app.services.audit_service import append_audit_entry


def authorize_arbitration_decision(
    claim_code: str,
    arbitrator_email: str,
    rationale: str,
    supplier_payout_eth: str,
    buyer_refund_eth: str,
    third_party_comp_eth: str = "0",
    third_party_recipient: str = "0x0000000000000000000000000000000000000000",
) -> dict:
    comp = Complaint.query.filter_by(claim_code=claim_code).first()
    if not comp:
        raise ValueError(f"Claim {claim_code} not found")
    if DisputeResolution.query.filter_by(claim_code=claim_code).first():
        raise ValueError(f"Arbitration decision already authorized for {claim_code}")

    decision_hash = sha256_hex(
        f"DECISION|{claim_code}|{supplier_payout_eth}|{buyer_refund_eth}|{third_party_comp_eth}|{rationale}"
    )
    decision_bytes = bytes.fromhex(decision_hash.removeprefix("0x"))

    sup_wei = Web3.to_wei(supplier_payout_eth, "ether")
    buy_wei = Web3.to_wei(buyer_refund_eth, "ether")
    comp_wei = Web3.to_wei(third_party_comp_eth, "ether")
    recip = Web3.to_checksum_address(
        third_party_recipient or "0x0000000000000000000000000000000000000000"
    )

    tx_hash = None
    cs = ContractService()
    if cs.bc.is_connected():
        contract = cs.get_contract("ClaimRegistry")
        tx_hash = cs._send_operator_tx(
            contract.functions.authorizeSettlement(
                Web3.keccak(text=claim_code),
                decision_bytes,
                sup_wei,
                buy_wei,
                comp_wei,
                recip,
            )
        )
        ts = TransactionService()
        rec = ts.record_and_verify_transaction(
            tx_hash=tx_hash,
            contract_name="ClaimRegistry",
            function_name="authorizeSettlement",
            reference_id=claim_code,
        )
        if rec.status != "CONFIRMED":
            raise ValueError(f"On-chain authorizeSettlement reverted: {rec.error_message}")

    res = DisputeResolution(
        claim_code=claim_code,
        arbitrator_email=arbitrator_email,
        rationale=rationale,
        decision_commitment=decision_hash,
        supplier_payout_eth=supplier_payout_eth,
        buyer_refund_eth=buyer_refund_eth,
        third_party_comp_eth=third_party_comp_eth,
        third_party_recipient=recip,
        authorize_tx_hash=tx_hash,
        settled=False,
    )
    comp.status = "AUTHORIZED"
    db.session.add(res)
    db.session.commit()

    append_audit_entry(
        actor_email=arbitrator_email,
        category="ARBITRATION",
        action="AUTHORIZE_SETTLEMENT",
        payload={
            "claim_code": claim_code,
            "supplier_payout_eth": supplier_payout_eth,
            "buyer_refund_eth": buyer_refund_eth,
            "third_party_comp_eth": third_party_comp_eth,
        },
        onchain_tx_hash=tx_hash,
    )
    return res.to_dict()
