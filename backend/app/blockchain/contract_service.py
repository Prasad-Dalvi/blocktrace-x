import os
from web3 import Web3
from app.blockchain.blockchain_service import BlockchainService


class ContractService:
    def __init__(self):
        self.bc = BlockchainService()
        self.w3 = self.bc.w3

    def get_contract(self, contract_name: str):
        deployments = self.bc.load_deployments()
        if not deployments or contract_name not in deployments.get("contracts", {}):
            raise ValueError(f"Contract {contract_name} not deployed or deployment file missing")
        info = deployments["contracts"][contract_name]
        checksum_addr = Web3.to_checksum_address(info["address"])
        return self.w3.eth.contract(address=checksum_addr, abi=info["abi"])

    def _send_operator_tx(self, contract_fn) -> str:
        private_key = os.getenv(
            "DEPLOYER_PRIVATE_KEY",
            "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        )
        account = self.w3.eth.account.from_key(private_key)
        tx = contract_fn.build_transaction(
            {
                "from": account.address,
                "nonce": self.w3.eth.get_transaction_count(account.address),
                "gas": 400000,
                "gasPrice": self.w3.eth.gas_price,
            }
        )
        signed = self.w3.eth.account.sign_transaction(tx, private_key=private_key)
        raw_tx = getattr(signed, "raw_transaction", getattr(signed, "rawTransaction", None))
        tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
        return Web3.to_hex(tx_hash)

    def get_snapshot_onchain(self, version: int) -> dict:
        contract = self.get_contract("ManufacturingRegistry")
        root_hash, meta_hash, ts, registrar, exists = contract.functions.getSnapshot(version).call()
        return {
            "version": version,
            "root_hash": Web3.to_hex(root_hash),
            "metadata_hash": Web3.to_hex(meta_hash),
            "timestamp": ts,
            "registrar": registrar,
            "exists": exists,
        }

    def get_defect_onchain(self, event_code: str) -> dict:
        contract = self.get_contract("ManufacturingRegistry")
        event_id = Web3.keccak(text=event_code)
        lot_h, snap_v, ev_h, sev, ts, inspector, exists = contract.functions.getDefectCommitment(
            event_id
        ).call()
        return {
            "event_code": event_code,
            "event_id": Web3.to_hex(event_id),
            "lot_id_hash": Web3.to_hex(lot_h),
            "snapshot_version": snap_v,
            "evidence_hash": Web3.to_hex(ev_h),
            "severity": sev,
            "timestamp": ts,
            "inspector": inspector,
            "exists": exists,
        }

    def get_escrow_onchain(self, po_number: str) -> dict:
        contract = self.get_contract("SupplyChainEscrow")
        escrow_id = Web3.keccak(text=po_number)
        data = contract.functions.getEscrow(escrow_id).call()
        valid, d_cum, bucket_sum = contract.functions.checkConservationInvariant(escrow_id).call()
        status_map = {
            0: "NONE", 1: "CREATED", 2: "FUNDED", 3: "SHIPPED", 4: "RECEIVED",
            5: "QC_PASSED", 6: "COMPLAINT", 7: "DISPUTED", 8: "SETTLED", 9: "CLOSED"
        }
        return {
            "po_number": po_number,
            "escrow_id": Web3.to_hex(escrow_id),
            "buyer": data[0],
            "supplier": data[1],
            "target_wei": str(data[5]),
            "d_cum_wei": str(data[6]),
            "fa_wei": str(data[7]),
            "fr_wei": str(data[8]),
            "fd_wei": str(data[9]),
            "ps_wei": str(data[10]),
            "pb_wei": str(data[11]),
            "pc_wei": str(data[12]),
            "fa_eth": str(Web3.from_wei(data[7], "ether")),
            "fr_eth": str(Web3.from_wei(data[8], "ether")),
            "fd_eth": str(Web3.from_wei(data[9], "ether")),
            "ps_eth": str(Web3.from_wei(data[10], "ether")),
            "pb_eth": str(Web3.from_wei(data[11], "ether")),
            "pc_eth": str(Web3.from_wei(data[12], "ether")),
            "d_cum_eth": str(Web3.from_wei(data[6], "ether")),
            "status": status_map.get(data[13], "UNKNOWN"),
            "conservation_valid": valid,
        }

    def submit_backend_snapshot(self, version: int, root_hex: str, meta_hex: str) -> str:
        contract = self.get_contract("ManufacturingRegistry")
        root_bytes = bytes.fromhex(root_hex.removeprefix("0x"))
        meta_bytes = bytes.fromhex(meta_hex.removeprefix("0x"))
        return self._send_operator_tx(
            contract.functions.registerSnapshot(version, root_bytes, meta_bytes)
        )

    def submit_defect_commitment(
        self,
        event_id_bytes: bytes,
        lot_id_bytes: bytes,
        snapshot_version: int,
        evidence_bytes: bytes,
        severity: int,
    ) -> str:
        contract = self.get_contract("ManufacturingRegistry")
        return self._send_operator_tx(
            contract.functions.registerDefectCommitment(
                event_id_bytes,
                lot_id_bytes,
                snapshot_version,
                evidence_bytes,
                severity,
            )
        )

    def submit_propagation_commitment(
        self,
        event_id_bytes: bytes,
        snapshot_version: int,
        cursor_bytes: bytes,
        affected_root_bytes: bytes,
        affected_count: int,
    ) -> str:
        contract = self.get_contract("ManufacturingRegistry")
        return self._send_operator_tx(
            contract.functions.registerPropagationCommitment(
                event_id_bytes,
                snapshot_version,
                cursor_bytes,
                affected_root_bytes,
                affected_count,
            )
        )

    def submit_risk_report_commitment(
        self,
        event_id_bytes: bytes,
        snapshot_version: int,
        report_root_bytes: bytes,
    ) -> str:
        contract = self.get_contract("ManufacturingRegistry")
        return self._send_operator_tx(
            contract.functions.registerRiskReportCommitment(
                event_id_bytes,
                snapshot_version,
                report_root_bytes,
            )
        )
