import json
import os
from web3 import Web3
from app import create_app, db
from app.models import (
    Role,
    User,
    Supplier,
    Manufacturer,
    Buyer,
    SupplierLot,
    ProductionBatch,
    PhysicalUnit,
    GenealogyRelation,
    PurchaseOrder,
    DispatchOrder,
    ContractDeployment,
    BlockchainTransaction,
    Snapshot,
    SnapshotCommitment,
    DefectEvent,
    InspectorVerdict,
    EscrowLedger,
)
from app.services.snapshot_service import seal_snapshot
from app.services.defect_event_service import (
    submit_defect_event,
    submit_inspector_verdict,
    anchor_defect_event_onchain,
)
from app.services.audit_service import append_audit_entry
from app.blockchain.contract_service import ContractService
from app.blockchain.transaction_service import TransactionService

PROTOTYPE_BATCHES = [
    {"id": "2023-0101", "m": "MC-04", "u": 502, "qc": "FAIL", "dr": 1.48},
    {"id": "2023-0459", "m": "MC-03", "u": 367, "qc": "FAIL", "dr": 1.79},
    {"id": "2023-0500", "m": "MC-04", "u": 295, "qc": "FAIL", "dr": 5.74},
    {"id": "2023-0501", "m": "MC-03", "u": 535, "qc": "FAIL", "dr": 5.47},
    {"id": "2023-0502", "m": "MC-04", "u": 203, "qc": "FAIL", "dr": 3.66},
    {"id": "2023-0503", "m": "MC-05", "u": 251, "qc": "FAIL", "dr": 5.66},
    {"id": "2023-0791", "m": "MC-05", "u": 235, "qc": "PASS", "dr": 0.46},
    {"id": "2023-1339", "m": "MC-04", "u": 354, "qc": "PASS", "dr": 0.03},
    {"id": "2023-2167", "m": "MC-04", "u": 339, "qc": "PASS", "dr": 0.23},
    {"id": "2023-2729", "m": "MC-03", "u": 359, "qc": "PASS", "dr": 0.20},
    {"id": "2024-3200", "m": "MC-05", "u": 368, "qc": "PASS", "dr": 0.24},
    {"id": "2024-4636", "m": "MC-05", "u": 348, "qc": "PASS", "dr": 0.24},
    {"id": "2024-4695", "m": "MC-02", "u": 348, "qc": "PASS", "dr": 0.10},
    {"id": "2024-4784", "m": "MC-03", "u": 285, "qc": "PASS", "dr": 0.04},
    {"id": "2024-4901", "m": "MC-05", "u": 506, "qc": "PASS", "dr": 0.15},
    {"id": "2024-4921", "m": "MC-05", "u": 334, "qc": "PASS", "dr": 0.23},
    {"id": "2024-5193", "m": "MC-02", "u": 234, "qc": "PASS", "dr": 0.47},
    {"id": "2024-5342", "m": "MC-01", "u": 461, "qc": "PASS", "dr": 0.41},
]

PROTOTYPE_ORDERS = [
    {"id": "D-1264", "c": "BAJAJ", "q": 756, "b": ["2023-0459"]},
    {"id": "D-1451", "c": "BAJAJ", "q": 843, "b": ["2023-2729"]},
    {"id": "D-1847", "c": "TATA", "q": 254, "b": ["2023-0500"]},
    {"id": "D-1921", "c": "MAHINDRA", "q": 769, "b": ["2023-0501"]},
    {"id": "D-2044", "c": "TATA", "q": 697, "b": ["2023-0500"]},
    {"id": "D-2102", "c": "MAHINDRA", "q": 284, "b": ["2023-0502"]},
    {"id": "D-2367", "c": "MAHINDRA", "q": 802, "b": ["2023-0503"]},
]


def _ensure_stage2_seed():
    snapshot = Snapshot.query.filter_by(version=1).first()
    if not snapshot:
        seal_snapshot("mfg@blocktracex.io", version=1, anchor_onchain=True)
        snapshot = Snapshot.query.filter_by(version=1).first()

    commitment = SnapshotCommitment.query.filter_by(snapshot_version=1).first()
    if snapshot and commitment and not commitment.onchain_verified:
        contract_service = ContractService()
        if contract_service.bc.is_connected():
            try:
                onchain = contract_service.get_snapshot_onchain(1)
                if not onchain["exists"]:
                    tx_hash = contract_service.submit_backend_snapshot(
                        1, snapshot.global_root, snapshot.metadata_hash
                    )
                    tx_record = TransactionService().record_and_verify_transaction(
                        tx_hash=tx_hash,
                        contract_name="ManufacturingRegistry",
                        function_name="registerSnapshot",
                        reference_id="SNAPSHOT_V1",
                    )
                    onchain = contract_service.get_snapshot_onchain(1)
                    commitment.tx_hash = tx_record.tx_hash

                matches = onchain["exists"] and (
                    onchain["root_hash"].lower() == snapshot.global_root.lower()
                )
                commitment.onchain_verified = matches
                commitment.verification_note = (
                    "Consistent with on-chain ManufacturingRegistry commitment"
                    if matches
                    else "On-chain commitment mismatch"
                )
                db.session.commit()
            except Exception as exc:
                commitment.verification_note = f"On-chain anchor skipped/failed: {exc}"
                db.session.commit()

    evt = DefectEvent.query.filter_by(event_code="EVT-2023-114-01").first()
    if not evt:
        submit_defect_event(
            event_code="EVT-2023-114-01",
            lot_code="LOT-2023-114",
            snapshot_version=1,
            severity=4,
            evidence_filename="epoxy_402_viscosity_fail.json",
            evidence_payload='{"batch_sample":"LOT-2023-114","shear_strength_mpa":8.2,"threshold_mpa":14.0}',
            created_by="qc@blocktracex.io",
            quorum_required=2,
        )

    for email, confidence, notes in [
        ("qc@blocktracex.io", 0.96, "Shear strength below spec"),
        ("qc2@blocktracex.io", 0.94, "Confirmed delamination on MC-04"),
    ]:
        if not InspectorVerdict.query.filter_by(
            event_code="EVT-2023-114-01", inspector_email=email
        ).first():
            submit_inspector_verdict(
                "EVT-2023-114-01", email, "SUPPORT", confidence, notes
            )

    evt = DefectEvent.query.filter_by(event_code="EVT-2023-114-01").first()
    if evt and evt.status == "APPROVED" and not evt.onchain_tx_hash:
        try:
            anchor_defect_event_onchain(evt.event_code)
        except Exception:
            pass


def seed():
    app = create_app()
    with app.app_context():
        if Role.query.first():
            _ensure_stage2_seed()
            print("Database already seeded (verified Stage 2/3 records).")
            return

        role_names = [
            "Admin",
            "Manufacturer",
            "Supplier",
            "QC Inspector",
            "Buyer",
            "Arbitrator",
        ]
        roles = {}
        for rname in role_names:
            r = Role(name=rname, description=f"{rname} role in BlockTrace-X")
            db.session.add(r)
            roles[rname] = r
        db.session.flush()

        users_spec = [
            ("admin@blocktracex.io", "System Admin", "Admin@123", "Admin", "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"),
            ("mfg@blocktracex.io", "OEM Plant Operations", "Mfg@123", "Manufacturer", "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"),
            ("s03@blocktracex.io", "Supplier S03 Bonding Corp", "Sup@123", "Supplier", "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"),
            ("buyer@blocktracex.io", "Bajaj Auto Procurement", "Buyer@123", "Buyer", "0x90F79bf6EB2c4f870365E785982E1f101E93b906"),
            ("qc@blocktracex.io", "Lead QC Inspector", "Qc@123", "QC Inspector", "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65"),
            ("qc2@blocktracex.io", "Senior Metrology Inspector", "Qc@123", "QC Inspector", "0x976EA74026E726554dB657fA54763abd0C3a0aa9"),
            ("arb@blocktracex.io", "Independent Arbitrator", "Arb@123", "Arbitrator", "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc"),
        ]
        for email, name, pwd, rname, wallet in users_spec:
            u = User(email=email, full_name=name, role_id=roles[rname].id, wallet_address=wallet)
            u.set_password(pwd)
            db.session.add(u)

        s03 = Supplier(
            code="S03",
            name="S03 Industrial Adhesives Ltd.",
            material_category="Adhesive Bonding Agent",
            wallet_address="0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
            tier=1,
        )
        s07 = Supplier(
            code="S07",
            name="S07 Precision Alloy Substrates",
            material_category="Aluminum Housing Casting",
            wallet_address="0x976EA74026E726554dB657fA54763abd0C3a0aa9",
            tier=1,
        )
        db.session.add_all([s03, s07])

        mfg = Manufacturer(
            code="MFG-PUNE-01",
            name="BlockTrace Tier-1 Assembly Plant",
            plant_location="Pune, Maharashtra",
            wallet_address="0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        )
        db.session.add(mfg)

        buyers = {
            "BAJAJ": Buyer(code="BAJAJ", name="Bajaj Auto Ltd.", wallet_address="0x90F79bf6EB2c4f870365E785982E1f101E93b906"),
            "TATA": Buyer(code="TATA", name="Tata Motors Ltd.", wallet_address="0x14dC79964da2C08b23698B3D3cc7Ca32193d9955"),
            "MAHINDRA": Buyer(code="MAHINDRA", name="Mahindra & Mahindra Ltd.", wallet_address="0x23618e81E3f5cdF7f54C3d65f7FBc0aBf5B21E8f"),
        }
        db.session.add_all(buyers.values())
        db.session.flush()

        lot_114 = SupplierLot(
            lot_code="LOT-2023-114",
            supplier_id=s03.id,
            material_name="Adhesive Bonding Agent (Epoxy-402)",
            quantity_received=1250.0,
            unit_of_measure="kg",
            qc_status="FAIL",
            risk_status="AT_RISK",
        )
        lot_209 = SupplierLot(
            lot_code="LOT-2023-209",
            supplier_id=s07.id,
            material_name="CNC Cast Sub-Frame",
            quantity_received=6500.0,
            unit_of_measure="pcs",
            qc_status="PASS",
            risk_status="SAFE",
        )
        db.session.add_all([lot_114, lot_209])
        db.session.flush()

        for idx, b in enumerate(PROTOTYPE_BATCHES):
            pb = ProductionBatch(
                batch_code=b["id"],
                machine_id=b["m"],
                units_produced=b["u"],
                qc_status=b["qc"],
                defect_rate_pct=b["dr"],
                risk_status="SAFE",
                snapshot_version=1,
            )
            db.session.add(pb)
            db.session.flush()

            db.session.add(
                GenealogyRelation(
                    parent_type="LOT",
                    parent_code="LOT-2023-114",
                    child_type="BATCH",
                    child_code=b["id"],
                    quantity_consumed=round(b["u"] * 0.18, 2),
                    snapshot_version=1,
                )
            )
            db.session.add(
                GenealogyRelation(
                    parent_type="LOT",
                    parent_code="LOT-2023-209",
                    child_type="BATCH",
                    child_code=b["id"],
                    quantity_consumed=float(b["u"]),
                    snapshot_version=1,
                )
            )

            if idx < 3:
                for u_idx in range(1, 4):
                    db.session.add(
                        PhysicalUnit(
                            serial_number=f"SN-{b['id']}-{u_idx:04d}",
                            batch_id=pb.id,
                            status="DISPATCHED",
                        )
                    )

        for o in PROTOTYPE_ORDERS:
            disp = DispatchOrder(
                dispatch_code=o["id"],
                buyer_id=buyers[o["c"]].id,
                quantity_pcs=o["q"],
                risk_status="SAFE",
            )
            db.session.add(disp)
            db.session.flush()
            for parent_b in o["b"]:
                db.session.add(
                    GenealogyRelation(
                        parent_type="BATCH",
                        parent_code=parent_b,
                        child_type="DISPATCH",
                        child_code=o["id"],
                        quantity_consumed=float(o["q"]),
                        snapshot_version=1,
                    )
                )

        escrow_id_hex = Web3.to_hex(Web3.keccak(text="PO-1001"))
        po1001 = PurchaseOrder(
            po_number="PO-1001",
            supplier_id=s03.id,
            buyer_id=buyers["BAJAJ"].id,
            lot_id=lot_114.id,
            business_value_inr=200000.0,
            testnet_eth_amount="2.0",
            escrow_id_bytes32=escrow_id_hex,
            status="FUNDED",
        )
        db.session.add(po1001)

        db.session.add(
            EscrowLedger(
                po_number="PO-1001",
                escrow_id_bytes32=escrow_id_hex,
                buyer_address="0x90F79bf6EB2c4f870365E785982E1f101E93b906",
                supplier_address="0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
                target_eth="2.0",
                d_cum_eth="2.0",
                fa_eth="1.8",
                fr_eth="0.2",
                fd_eth="0",
                ps_eth="0",
                pb_eth="0",
                pc_eth="0",
                status="FUNDED",
                conservation_valid=True,
            )
        )

        deploy_file = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "blockchain", "deployments", "localhost.json")
        )
        init_dep_tx = None
        if os.path.exists(deploy_file):
            with open(deploy_file, "r", encoding="utf-8") as f:
                dep = json.load(f)
            for cname, cinfo in dep.get("contracts", {}).items():
                db.session.add(
                    ContractDeployment(
                        contract_name=cname,
                        address=cinfo["address"],
                        network=dep.get("network", "localhost"),
                        chain_id=dep.get("chainId", 31337),
                    )
                )
            init_txs = dep.get("initialTransactions", {})
            if init_txs.get("po1001DepositTx"):
                init_dep_tx = init_txs["po1001DepositTx"]
                db.session.add(
                    BlockchainTransaction(
                        tx_hash=init_dep_tx,
                        contract_name="SupplyChainEscrow",
                        function_name="deposit",
                        sender_address=dep["accounts"]["buyerBajaj"],
                        status="CONFIRMED",
                        reference_id="PO-1001",
                    )
                )

        db.session.commit()

        append_audit_entry(
            actor_email="admin@blocktracex.io",
            category="GENESIS",
            action="SEED_PROTOTYPE_DATA",
            payload={"lot": "LOT-2023-114", "supplier": "S03", "po": "PO-1001", "inr_value": 200000},
            onchain_tx_hash=init_dep_tx,
        )

        _ensure_stage2_seed()
        print("BlockTrace-X Final Stage 1-3 demo database seeded successfully.")


if __name__ == "__main__":
    seed()
