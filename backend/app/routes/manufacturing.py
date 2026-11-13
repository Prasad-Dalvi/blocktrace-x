from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from pydantic import ValidationError
from app import db
from app.models import (
    Supplier,
    Buyer,
    SupplierLot,
    ProductionBatch,
    OperatorBatchEntry,
    PhysicalUnit,
    GenealogyRelation,
    PurchaseOrder,
    DispatchOrder,
    QualityInspection,
    AuditLog,
)
from app.schemas.validation import (
    CreateLotSchema,
    CreateBatchSchema,
    CreateRelationSchema,
    CreateDispatchSchema,
    OperatorBatchSchema,
)
from app.services.genealogy_service import (
    validate_and_create_relation,
    trace_upstream_downstream,
)
from app.services.csv_dataset_service import CsvDatasetError, get_csv_dataset
from app.utils.rbac import roles_required

mfg_bp = Blueprint("manufacturing", __name__)


@mfg_bp.get("/summary")
@jwt_required()
def dashboard_summary():
    summary = get_csv_dataset().summary()
    summary["operator_batches_count"] = OperatorBatchEntry.query.count()
    summary["batches_count"] += summary["operator_batches_count"]
    summary["purchase_orders"] = [p.to_dict() for p in PurchaseOrder.query.all()]
    return jsonify(
        summary
    )


@mfg_bp.get("/suppliers")
@jwt_required()
def list_suppliers():
    return jsonify(
        [
            {
                "id": supplier["supplier_id"],
                "code": supplier["supplier_id"],
                "name": supplier["supplier_name"],
                "material_category": supplier["material_supplied"],
                "lead_time_days": supplier["lead_time_days"],
                "approved_status": supplier["approved_status"],
                "wallet_address": None,
            }
            for supplier in get_csv_dataset().suppliers
        ]
    )


@mfg_bp.get("/lots")
@jwt_required()
def list_lots():
    return jsonify(
        [
            {
                "id": lot["lot_code"],
                "lot_code": lot["lot_code"],
                "supplier_code": lot["supplier_id"] or "CONFLICT",
                "supplier_name": lot["supplier_name"] or "Conflicting source records",
                "material_name": lot["material_name"],
                "quantity_received": lot["quantity_received"],
                "unit_of_measure": lot["unit_of_measure"],
                "qc_status": lot["qc_status"],
                "risk_status": lot["risk_status"],
                "resolution_status": lot["resolution_status"],
                "source_row_count": lot["source_row_count"],
            }
            for lot in get_csv_dataset().lots
        ]
    )


@mfg_bp.post("/lots")
@roles_required("Manufacturer", "Supplier")
def create_lot():
    try:
        data = CreateLotSchema(**(request.get_json() or {}))
    except ValidationError as exc:
        return jsonify({"error": exc.errors()}), 400

    supplier = Supplier.query.filter_by(code=data.supplier_code).first()
    if not supplier:
        return jsonify({"error": f"Supplier {data.supplier_code} not found"}), 404
    if SupplierLot.query.filter_by(lot_code=data.lot_code).first():
        return jsonify({"error": f"Lot {data.lot_code} already exists"}), 400

    lot = SupplierLot(
        lot_code=data.lot_code,
        supplier_id=supplier.id,
        material_name=data.material_name,
        quantity_received=data.quantity_received,
        unit_of_measure=data.unit_of_measure,
    )
    db.session.add(lot)
    db.session.commit()
    return jsonify(lot.to_dict()), 201


@mfg_bp.get("/batches")
@jwt_required()
def list_batches():
    dataset = get_csv_dataset()
    lot_code = request.args.get("lot")
    batches = dataset.batches
    if lot_code:
        batches = [batch for batch in batches if batch["input_lot_ref"] == lot_code]
    operator_entries = OperatorBatchEntry.query.order_by(OperatorBatchEntry.id.desc()).all()
    if lot_code:
        operator_entries = [entry for entry in operator_entries if entry.input_lot_ref == lot_code]
    limit = request.args.get("limit", type=int)
    if limit:
        page_limit = max(1, min(limit, 500))
        batches = batches[:page_limit]
        operator_entries = operator_entries[:page_limit]
    return jsonify(
        [
            {
                "id": batch["source_row"],
                "batch_code": batch["batch_id"],
                "machine_id": batch["machine_id"],
                "units_produced": batch["units_produced"],
                "qc_status": batch["qc_status"],
                "defect_rate_pct": batch["defect_rate_pct"],
                "risk_status": "AT_RISK" if batch["qc_status"] == "FAIL" else "SAFE",
                "snapshot_version": 1,
                **batch,
            }
            for batch in batches
        ]
        + [
            {
                **entry.to_dict(),
                "batch_id": entry.batch_code,
                "qc_status": "PENDING",
                "defect_rate_pct": 0.0,
                "risk_status": "PENDING",
                "batch_id_imputed": False,
                "defect_type": None,
            }
            for entry in operator_entries
        ]
    )


@mfg_bp.get("/operator-batches")
@jwt_required()
def list_operator_batches():
    return jsonify(
        [
            entry.to_dict()
            for entry in OperatorBatchEntry.query.order_by(OperatorBatchEntry.id.desc()).all()
        ]
    )


@mfg_bp.post("/operator-batches")
@roles_required("Manufacturer")
def create_operator_batch():
    try:
        data = OperatorBatchSchema(**(request.get_json() or {}))
    except ValidationError as exc:
        return jsonify({"error": exc.errors()}), 400

    existing = OperatorBatchEntry.query.filter_by(batch_code=data.batch_code).first()
    if existing:
        return jsonify(existing.to_dict()), 200
    if ProductionBatch.query.filter_by(batch_code=data.batch_code).first():
        return jsonify({"error": f"Batch {data.batch_code} already exists"}), 409
    if data.batch_code in get_csv_dataset().batch_id_set:
        return jsonify({"error": f"Batch {data.batch_code} already exists in the source files"}), 409
    lot = get_csv_dataset().lot_by_code.get(data.input_lot_ref)
    if not lot:
        return jsonify({"error": f"Lot {data.input_lot_ref} was not found in the source files"}), 400
    if lot["resolution_status"] == "unresolved_conflict":
        return jsonify({"error": f"Lot {data.input_lot_ref} has conflicting supplier/material records"}), 400

    claims = get_jwt()
    entry = OperatorBatchEntry(
        batch_code=data.batch_code,
        production_date=data.production_date,
        shift=data.shift,
        machine_id=data.machine_id,
        operator_id=data.operator_id,
        input_lot_ref=data.input_lot_ref,
        units_produced=data.units_produced,
        cycle_time_min=data.cycle_time_min,
        created_by=claims.get("email", "unknown"),
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify(entry.to_dict()), 201


@mfg_bp.post("/batches")
@roles_required("Manufacturer")
def create_batch():
    try:
        data = CreateBatchSchema(**(request.get_json() or {}))
    except ValidationError as exc:
        return jsonify({"error": exc.errors()}), 400

    if ProductionBatch.query.filter_by(batch_code=data.batch_code).first():
        return jsonify({"error": f"Batch {data.batch_code} already exists"}), 400

    batch = ProductionBatch(
        batch_code=data.batch_code,
        machine_id=data.machine_id,
        units_produced=data.units_produced,
        qc_status=data.qc_status.upper(),
        defect_rate_pct=data.defect_rate_pct,
    )
    db.session.add(batch)
    db.session.commit()
    return jsonify(batch.to_dict()), 201


@mfg_bp.get("/units")
@jwt_required()
def list_units():
    units = PhysicalUnit.query.limit(100).all()
    return jsonify(
        [
            {
                "id": u.id,
                "serial_number": u.serial_number,
                "batch_code": u.batch.batch_code if u.batch else None,
                "status": u.status,
            }
            for u in units
        ]
    )


@mfg_bp.get("/relations")
@jwt_required()
def list_relations():
    return jsonify([r.to_dict() for r in GenealogyRelation.query.all()])


@mfg_bp.post("/relations")
@roles_required("Manufacturer")
def add_relation():
    try:
        data = CreateRelationSchema(**(request.get_json() or {}))
    except ValidationError as exc:
        return jsonify({"error": exc.errors()}), 400

    rel = validate_and_create_relation(
        parent_type=data.parent_type,
        parent_code=data.parent_code,
        child_type=data.child_type,
        child_code=data.child_code,
        quantity_consumed=data.quantity_consumed,
        snapshot_version=data.snapshot_version,
    )
    return jsonify(rel.to_dict()), 201


@mfg_bp.get("/dispatches")
@jwt_required()
def list_dispatches():
    dataset = get_csv_dataset()
    results = []
    for dispatch in dataset.dispatches:
        linked_batches = [
            dataset.batch_by_code[code]
            for code in dispatch["linked_batch_refs"]
        ]
        at_risk = any(
            batch["qc_status"] == "FAIL"
            or batch["input_lot_ref"] == "LOT-2023-114"
            for batch in linked_batches
        )
        results.append(
            {
                "id": dispatch["source_row"],
                "dispatch_code": dispatch["order_id"],
                "buyer_code": dispatch["customer_id"].removeprefix("OEM-"),
                "buyer_name": dispatch["customer_name"],
                "quantity_pcs": dispatch["quantity"],
                "risk_status": "AT_RISK" if at_risk else "SAFE",
                "source_batches": dispatch["linked_batch_refs"],
                "unresolved_batch_refs": dispatch["unresolved_batch_refs"],
                "dispatch_date": dispatch["dispatch_date"],
                "product_type": dispatch["product_type"],
                "vehicle_number": dispatch["vehicle_number"],
            }
        )
    return jsonify(results)


@mfg_bp.get("/dataset/status")
@jwt_required()
def csv_dataset_status():
    return jsonify(get_csv_dataset().summary())


@mfg_bp.get("/trace/dispatch/<dispatch_code>")
@jwt_required()
def trace_csv_dispatch(dispatch_code: str):
    try:
        return jsonify(get_csv_dataset().trace_dispatch(dispatch_code))
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except CsvDatasetError as exc:
        return jsonify({"error": str(exc)}), 503


@mfg_bp.get("/alerts/lot/<lot_code>")
@jwt_required()
def alert_csv_lot(lot_code: str):
    try:
        return jsonify(get_csv_dataset().alert_lot(lot_code))
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except CsvDatasetError as exc:
        return jsonify({"error": str(exc)}), 503


@mfg_bp.post("/dispatches")
@roles_required("Manufacturer")
def create_dispatch():
    try:
        data = CreateDispatchSchema(**(request.get_json() or {}))
    except ValidationError as exc:
        return jsonify({"error": exc.errors()}), 400

    buyer = Buyer.query.filter_by(code=data.buyer_code).first()
    if not buyer:
        return jsonify({"error": f"Buyer {data.buyer_code} not found"}), 404
    if DispatchOrder.query.filter_by(dispatch_code=data.dispatch_code).first():
        return jsonify({"error": f"Dispatch {data.dispatch_code} already exists"}), 400

    disp = DispatchOrder(
        dispatch_code=data.dispatch_code,
        buyer_id=buyer.id,
        quantity_pcs=data.quantity_pcs,
    )
    db.session.add(disp)
    db.session.flush()

    for b_code in data.parent_batches:
        validate_and_create_relation("BATCH", b_code, "DISPATCH", disp.dispatch_code, float(data.quantity_pcs))

    return jsonify(disp.to_dict()), 201


@mfg_bp.get("/genealogy/graph")
@jwt_required()
def full_genealogy_graph():
    lots = [l.to_dict() for l in SupplierLot.query.all()]
    batches = [b.to_dict() for b in ProductionBatch.query.all()]
    dispatches = [d.to_dict() for d in DispatchOrder.query.all()]
    relations = [r.to_dict() for r in GenealogyRelation.query.all()]
    return jsonify(
        {
            "lots": lots,
            "batches": batches,
            "dispatches": dispatches,
            "relations": relations,
        }
    )


@mfg_bp.get("/genealogy/trace/<node_type>/<node_code>")
@jwt_required()
def trace_node(node_type: str, node_code: str):
    result = trace_upstream_downstream(node_type.upper(), node_code)
    return jsonify(result)


@mfg_bp.post("/qc/inspect-lot/<lot_code>")
@roles_required("QC Inspector", "Manufacturer")
def inspect_lot(lot_code: str):
    body = request.get_json() or {}
    result = body.get("result", "FAIL").upper()
    if result not in ("PASS", "FAIL"):
        return jsonify({"error": "result must be PASS or FAIL"}), 400

    lot = SupplierLot.query.filter_by(lot_code=lot_code).first()
    if not lot:
        return jsonify({"error": f"Lot {lot_code} not found"}), 404

    lot.qc_status = result
    lot.risk_status = "AT_RISK" if result == "FAIL" else "SAFE"

    trace = trace_upstream_downstream("LOT", lot_code)
    for desc in trace["downstream_descendants"]:
        dtype, dcode = desc.split(":", 1)
        if dtype == "BATCH":
            b = ProductionBatch.query.filter_by(batch_code=dcode).first()
            if b:
                b.risk_status = "AT_RISK" if result == "FAIL" else "SAFE"
        elif dtype == "DISPATCH":
            d = DispatchOrder.query.filter_by(dispatch_code=dcode).first()
            if d:
                d.risk_status = "AT_RISK" if result == "FAIL" else "SAFE"

    claims = get_jwt()
    qi = QualityInspection(
        target_type="LOT",
        target_code=lot_code,
        inspector_email=claims.get("email", "qc@blocktracex.io"),
        result=result,
        notes=body.get("notes", ""),
    )
    db.session.add(qi)
    db.session.add(
        AuditLog(
            actor_email=claims.get("email", "qc@blocktracex.io"),
            action=f"LOT_QC_{result}",
            details=f"Lot {lot_code} marked {result}; {len(trace['downstream_descendants'])} descendants updated",
        )
    )
    db.session.commit()
    return jsonify({"lot": lot.to_dict(), "impact": trace})
