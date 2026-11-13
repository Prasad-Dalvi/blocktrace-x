from web3.exceptions import TransactionNotFound
from app import db
from app.models import BlockchainTransaction
from app.blockchain.blockchain_service import BlockchainService


class TransactionService:
    def __init__(self):
        self.bc = BlockchainService()
        self.w3 = self.bc.w3

    def record_and_verify_transaction(
        self,
        tx_hash: str,
        contract_name: str,
        function_name: str,
        sender_address: str | None = None,
        reference_id: str | None = None,
    ) -> BlockchainTransaction:
        record = BlockchainTransaction.query.filter_by(tx_hash=tx_hash).first()
        if not record:
            record = BlockchainTransaction(
                tx_hash=tx_hash,
                contract_name=contract_name,
                function_name=function_name,
                sender_address=sender_address,
                reference_id=reference_id,
                status="PENDING",
            )
            db.session.add(record)

        if self.bc.is_connected():
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
                record.block_number = receipt["blockNumber"]
                record.gas_used = receipt["gasUsed"]
                if receipt["status"] == 1:
                    record.status = "CONFIRMED"
                else:
                    record.status = "FAILED"
                    record.error_message = "Transaction reverted on EVM (status=0)"
            except TransactionNotFound:
                record.status = "PENDING"
            except Exception as exc:
                record.status = "FAILED"
                record.error_message = str(exc)

        db.session.commit()
        return record
