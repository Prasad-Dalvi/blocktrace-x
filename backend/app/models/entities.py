from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


def utcnow():
    return datetime.now(timezone.utc)


class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    wallet_address = db.Column(db.String(64), nullable=True)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    role = db.relationship("Role", backref="users")
    created_at = db.Column(db.DateTime, default=utcnow)

    def set_password(self, raw_password: str):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "wallet_address": self.wallet_address,
            "role": self.role.name if self.role else None,
        }


class Supplier(db.Model):
    __tablename__ = "suppliers"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    material_category = db.Column(db.String(120), nullable=False)
    wallet_address = db.Column(db.String(64))
    tier = db.Column(db.Integer, default=1)

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "material_category": self.material_category,
            "wallet_address": self.wallet_address,
            "tier": self.tier,
        }


class Manufacturer(db.Model):
    __tablename__ = "manufacturers"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    plant_location = db.Column(db.String(120))
    wallet_address = db.Column(db.String(64))


class Buyer(db.Model):
    __tablename__ = "buyers"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    wallet_address = db.Column(db.String(64))

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "wallet_address": self.wallet_address,
        }


class SupplierLot(db.Model):
    __tablename__ = "supplier_lots"
    id = db.Column(db.Integer, primary_key=True)
    lot_code = db.Column(db.String(64), unique=True, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=False)
    supplier = db.relationship("Supplier", backref="lots")
    material_name = db.Column(db.String(120), nullable=False)
    quantity_received = db.Column(db.Float, nullable=False)
    unit_of_measure = db.Column(db.String(20), default="kg")
    qc_status = db.Column(db.String(32), default="PENDING")
    risk_status = db.Column(db.String(32), default="SAFE")
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "lot_code": self.lot_code,
            "supplier_code": self.supplier.code if self.supplier else None,
            "supplier_name": self.supplier.name if self.supplier else None,
            "material_name": self.material_name,
            "quantity_received": self.quantity_received,
            "unit_of_measure": self.unit_of_measure,
            "qc_status": self.qc_status,
            "risk_status": self.risk_status,
        }


class ProductionBatch(db.Model):
    __tablename__ = "production_batches"
    id = db.Column(db.Integer, primary_key=True)
    batch_code = db.Column(db.String(64), unique=True, nullable=False)
    machine_id = db.Column(db.String(32), nullable=False)
    units_produced = db.Column(db.Integer, nullable=False)
    qc_status = db.Column(db.String(32), default="PASS")
    defect_rate_pct = db.Column(db.Float, default=0.0)
    risk_status = db.Column(db.String(32), default="SAFE")
    snapshot_version = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "batch_code": self.batch_code,
            "machine_id": self.machine_id,
            "units_produced": self.units_produced,
            "qc_status": self.qc_status,
            "defect_rate_pct": self.defect_rate_pct,
            "risk_status": self.risk_status,
            "snapshot_version": self.snapshot_version,
        }


class OperatorBatchEntry(db.Model):
    __tablename__ = "operator_batch_entries"
    id = db.Column(db.Integer, primary_key=True)
    batch_code = db.Column(db.String(64), unique=True, nullable=False)
    production_date = db.Column(db.Date, nullable=False)
    shift = db.Column(db.String(8), nullable=False)
    machine_id = db.Column(db.String(32), nullable=False)
    operator_id = db.Column(db.String(32), nullable=False)
    input_lot_ref = db.Column(db.String(64), nullable=False)
    units_produced = db.Column(db.Integer, nullable=False)
    cycle_time_min = db.Column(db.Float, nullable=False)
    created_by = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "batch_code": self.batch_code,
            "production_date": self.production_date.isoformat(),
            "shift": self.shift,
            "machine_id": self.machine_id,
            "operator_id": self.operator_id,
            "input_lot_ref": self.input_lot_ref,
            "units_produced": self.units_produced,
            "cycle_time_min": self.cycle_time_min,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PhysicalUnit(db.Model):
    __tablename__ = "physical_units"
    id = db.Column(db.Integer, primary_key=True)
    serial_number = db.Column(db.String(64), unique=True, nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey("production_batches.id"), nullable=False)
    batch = db.relationship("ProductionBatch", backref="physical_units")
    status = db.Column(db.String(32), default="IN_STOCK")


class GenealogyRelation(db.Model):
    __tablename__ = "genealogy_relations"
    id = db.Column(db.Integer, primary_key=True)
    parent_type = db.Column(db.String(32), nullable=False)
    parent_code = db.Column(db.String(64), nullable=False)
    child_type = db.Column(db.String(32), nullable=False)
    child_code = db.Column(db.String(64), nullable=False)
    quantity_consumed = db.Column(db.Float, nullable=False)
    snapshot_version = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            "parent_type", "parent_code", "child_type", "child_code",
            name="uq_genealogy_edge",
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "parent_type": self.parent_type,
            "parent_code": self.parent_code,
            "child_type": self.child_type,
            "child_code": self.child_code,
            "quantity_consumed": self.quantity_consumed,
            "snapshot_version": self.snapshot_version,
        }


class PurchaseOrder(db.Model):
    __tablename__ = "purchase_orders"
    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(64), unique=True, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey("buyers.id"), nullable=False)
    lot_id = db.Column(db.Integer, db.ForeignKey("supplier_lots.id"), nullable=True)
    business_value_inr = db.Column(db.Float, nullable=False)
    testnet_eth_amount = db.Column(db.String(32), nullable=False)
    escrow_id_bytes32 = db.Column(db.String(66), nullable=True)
    status = db.Column(db.String(32), default="CREATED")

    supplier = db.relationship("Supplier")
    buyer = db.relationship("Buyer")
    lot = db.relationship("SupplierLot")

    def to_dict(self):
        return {
            "id": self.id,
            "po_number": self.po_number,
            "supplier_code": self.supplier.code if self.supplier else None,
            "buyer_code": self.buyer.code if self.buyer else None,
            "lot_code": self.lot.lot_code if self.lot else None,
            "business_value_inr": self.business_value_inr,
            "testnet_eth_amount": self.testnet_eth_amount,
            "escrow_id_bytes32": self.escrow_id_bytes32,
            "status": self.status,
        }


class DispatchOrder(db.Model):
    __tablename__ = "dispatch_orders"
    id = db.Column(db.Integer, primary_key=True)
    dispatch_code = db.Column(db.String(64), unique=True, nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey("buyers.id"), nullable=False)
    buyer = db.relationship("Buyer", backref="dispatch_orders")
    quantity_pcs = db.Column(db.Integer, nullable=False)
    risk_status = db.Column(db.String(32), default="SAFE")
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "dispatch_code": self.dispatch_code,
            "buyer_code": self.buyer.code if self.buyer else None,
            "buyer_name": self.buyer.name if self.buyer else None,
            "quantity_pcs": self.quantity_pcs,
            "risk_status": self.risk_status,
        }


class QualityInspection(db.Model):
    __tablename__ = "quality_inspections"
    id = db.Column(db.Integer, primary_key=True)
    target_type = db.Column(db.String(32), nullable=False)
    target_code = db.Column(db.String(64), nullable=False)
    inspector_email = db.Column(db.String(120), nullable=False)
    result = db.Column(db.String(16), nullable=False)
    notes = db.Column(db.Text)
    onchain_event_id = db.Column(db.String(66))
    tx_hash = db.Column(db.String(66))
    created_at = db.Column(db.DateTime, default=utcnow)


class ContractDeployment(db.Model):
    __tablename__ = "contract_deployments"
    id = db.Column(db.Integer, primary_key=True)
    contract_name = db.Column(db.String(64), unique=True, nullable=False)
    address = db.Column(db.String(64), nullable=False)
    network = db.Column(db.String(32), default="localhost")
    chain_id = db.Column(db.Integer, default=31337)
    updated_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "contract_name": self.contract_name,
            "address": self.address,
            "network": self.network,
            "chain_id": self.chain_id,
        }


class BlockchainTransaction(db.Model):
    __tablename__ = "blockchain_transactions"
    id = db.Column(db.Integer, primary_key=True)
    tx_hash = db.Column(db.String(66), unique=True, nullable=False)
    contract_name = db.Column(db.String(64), nullable=False)
    function_name = db.Column(db.String(64), nullable=False)
    sender_address = db.Column(db.String(64))
    status = db.Column(db.String(20), default="PENDING")
    block_number = db.Column(db.Integer, nullable=True)
    gas_used = db.Column(db.Integer, nullable=True)
    reference_id = db.Column(db.String(128), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "tx_hash": self.tx_hash,
            "contract_name": self.contract_name,
            "function_name": self.function_name,
            "sender_address": self.sender_address,
            "status": self.status,
            "block_number": self.block_number,
            "gas_used": self.gas_used,
            "reference_id": self.reference_id,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    actor_email = db.Column(db.String(120), nullable=False)
    action = db.Column(db.String(120), nullable=False)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)
