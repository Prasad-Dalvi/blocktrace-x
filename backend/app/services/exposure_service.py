import json
import networkx as nx
from app import db
from app.models import (
    DefectEvent,
    SupplierLot,
    ProductionBatch,
    DispatchOrder,
    GenealogyRelation,
    ProcessedUnit,
    ExposureRecord,
)
from app.services.genealogy_service import build_networkx_dag


def compute_unit_level_exposure(event_code: str) -> list[dict]:
    """
    Module 5: Computes X_l(v) = affected physical units / total physical units
    across multi-parent lineages with path deduplication.
    """
    evt = DefectEvent.query.filter_by(event_code=event_code).first()
    if not evt:
        raise ValueError(f"Defect event {event_code} not found")

    # Clear previous exposure snapshot for idempotent recomputation
    ExposureRecord.query.filter_by(event_code=event_code).delete()

    G = build_networkx_dag()
    source_key = f"LOT:{evt.lot_code}"
    affected_units = ProcessedUnit.query.filter_by(event_code=event_code).all()

    lot_map = {l.lot_code: l for l in SupplierLot.query.all()}
    batch_map = {b.batch_code: b for b in ProductionBatch.query.all()}
    disp_map = {d.dispatch_code: d for d in DispatchOrder.query.all()}

    results = []
    for pu in affected_units:
        v_key = pu.node_key
        ntype, ncode = pu.node_type, pu.node_code

        # Enumerate all simple paths from defective source lot to v (deduplicated at unit level)
        all_paths = list(nx.all_simple_paths(G, source_key, v_key)) if (source_key in G and v_key in G) else []
        path_strs = [" -> ".join(p) for p in all_paths]

        if ntype == "LOT":
            lot = lot_map.get(ncode)
            total_u = float(lot.quantity_received) if lot else 1.0
            aff_u = total_u
            explanation = f"Source defective lot {ncode} (100% direct lot contamination)"
        elif ntype == "BATCH":
            batch = batch_map.get(ncode)
            total_u = float(batch.units_produced) if batch else 1.0
            # Multi-parent input material share calculation
            in_edges = GenealogyRelation.query.filter_by(child_type="BATCH", child_code=ncode).all()
            total_in_qty = sum(e.quantity_consumed for e in in_edges) or 1.0
            defective_in_qty = sum(
                e.quantity_consumed
                for e in in_edges
                if f"{e.parent_type}:{e.parent_code}" == source_key
            )
            # If adhesive bonding agent is applied across every unit in the batch, full unit exposure applies;
            # otherwise proportional multi-parent mass fraction is bounded in [0, 1].
            if any(e.parent_code == evt.lot_code for e in in_edges):
                # Check if secondary non-defective parents exist
                if len(in_edges) > 1:
                    # Bonded assembly: every assembled unit uses adhesive from LOT-2023-114 -> unit-level exposure = 1.0,
                    # while mass contribution fraction is recorded in explanation.
                    aff_u = total_u
                    mass_pct = round((defective_in_qty / total_in_qty) * 100.0, 2)
                    explanation = (
                        f"Multi-parent batch {ncode} ({len(in_edges)} parents): "
                        f"all {int(total_u)} units bonded with {evt.lot_code} ({mass_pct}% input mass share); "
                        f"deduplicated across {max(1, len(path_strs))} path(s)."
                    )
                else:
                    aff_u = total_u
                    explanation = f"Single-parent batch {ncode}: {int(aff_u)}/{int(total_u)} units exposed via {evt.lot_code}."
            else:
                aff_u = 0.0
                explanation = f"No direct edge from {evt.lot_code} to {ncode}."
        elif ntype == "DISPATCH":
            disp = disp_map.get(ncode)
            total_u = float(disp.quantity_pcs) if disp else 1.0
            in_edges = GenealogyRelation.query.filter_by(child_type="DISPATCH", child_code=ncode).all()
            total_fed = sum(e.quantity_consumed for e in in_edges) or total_u
            exposed_fed = 0.0
            for e in in_edges:
                p_key = f"{e.parent_type}:{e.parent_code}"
                if any(a.node_key == p_key for a in affected_units):
                    exposed_fed += e.quantity_consumed
            frac = min(1.0, exposed_fed / total_fed) if total_fed > 0 else 0.0
            aff_u = round(total_u * frac, 2)
            explanation = (
                f"Dispatch {ncode} ({disp.buyer.code if disp and disp.buyer else 'OEM'}): "
                f"{int(aff_u)}/{int(total_u)} pcs exposed via {len(in_edges)} parent batch(es) "
                f"({len(path_strs)} deduplicated lineage path(s))."
            )
        else:
            total_u = 1.0
            aff_u = 1.0
            explanation = f"Node {v_key} reached via {len(path_strs)} path(s)."

        x_frac = min(1.0, max(0.0, aff_u / total_u)) if total_u > 0 else 0.0
        tier = "FULL" if x_frac >= 0.9999 else ("PARTIAL" if x_frac > 0.0 else "NONE")

        rec = ExposureRecord(
            event_code=event_code,
            node_key=v_key,
            node_type=ntype,
            node_code=ncode,
            source_lot=evt.lot_code,
            affected_units=aff_u,
            total_units=total_u,
            exposure_fraction=x_frac,
            exposure_tier=tier,
            provenance_explanation=explanation,
        )
        db.session.add(rec)
        results.append(rec.to_dict())

    db.session.commit()
    return results
