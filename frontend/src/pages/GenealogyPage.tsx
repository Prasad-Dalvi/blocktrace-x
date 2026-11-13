import React, { useEffect, useState } from "react";
import { apiRequest } from "../services/api";

export const GenealogyPage: React.FC = () => {
  const [dispatchCode, setDispatchCode] = useState("D-1847");
  const [lotCode, setLotCode] = useState("LOT-2023-114");
  const [trace, setTrace] = useState<any>(null);
  const [alert, setAlert] = useState<any>(null);
  const [traceError, setTraceError] = useState("");
  const [alertError, setAlertError] = useState("");

  const loadTrace = async (code = dispatchCode) => {
    setTraceError("");
    try {
      setTrace(await apiRequest<any>(`/manufacturing/trace/dispatch/${encodeURIComponent(code)}`));
    } catch (error: any) {
      setTrace(null);
      setTraceError(error.message);
    }
  };

  const loadAlert = async (code = lotCode) => {
    setAlertError("");
    try {
      setAlert(await apiRequest<any>(`/manufacturing/alerts/lot/${encodeURIComponent(code)}`));
    } catch (error: any) {
      setAlert(null);
      setAlertError(error.message);
    }
  };

  useEffect(() => {
    void loadTrace("D-1847");
    void loadAlert("LOT-2023-114");
  }, []);

  return (
    <div className="space-y-6 font-mono text-xs">
      <header className="border-b border-[#d9d5cb] pb-4">
        <h2 className="font-bold text-base">DISPATCH TRACE & RECALL</h2>
        <p className="mt-1 text-[#646b73]">CSV-backed production lineage and downstream exposure</p>
      </header>

      <section className="space-y-3">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            void loadTrace();
          }}
        >
          <label className="grid gap-1">
            <span className="text-[#646b73]">DISPATCH ORDER</span>
            <input value={dispatchCode} onChange={(event) => setDispatchCode(event.target.value)} className="w-56 border border-[#d9d5cb] px-2 py-2" />
          </label>
          <button type="submit" className="bg-brand px-4 py-2 text-white">Trace upstream</button>
        </form>

        {traceError && <p role="alert" className="text-bad">{traceError}</p>}
        {trace && (
          <div className="space-y-4 border-t border-[#d9d5cb] pt-4">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              <div><span className="text-[#646b73]">CUSTOMER</span><p className="mt-1 font-bold">{trace.dispatch.customer_id}</p></div>
              <div><span className="text-[#646b73]">SHIPMENT DATE</span><p className="mt-1">{trace.dispatch.dispatch_date}</p></div>
              <div><span className="text-[#646b73]">PRODUCT</span><p className="mt-1">{trace.dispatch.product_type}</p></div>
              <div><span className="text-[#646b73]">QUANTITY</span><p className="mt-1">{trace.dispatch.quantity}</p></div>
              <div><span className="text-[#646b73]">VEHICLE</span><p className="mt-1">{trace.dispatch.vehicle_number}</p></div>
            </div>

            {trace.chains.map((chain: any) => (
              <article key={chain.batch.batch_id} className="border-y border-[#d9d5cb] py-4">
                <div className="grid gap-4 lg:grid-cols-3">
                  <div>
                    <p className="text-[#646b73]">PRODUCTION BATCH</p>
                    <h3 className="mt-1 text-sm font-bold">{chain.batch.batch_id}</h3>
                    <p className="mt-2">{chain.batch.production_date} · Shift {chain.batch.shift}</p>
                    <p>{chain.batch.machine_id} · Operator {chain.batch.operator_id}</p>
                    <p>{chain.batch.units_produced} units · {chain.batch.cycle_time_min} min cycle</p>
                    {chain.batch.batch_id_imputed && <p className="mt-2 text-amber-700">Batch ID inferred from same-row QC record</p>}
                  </div>
                  <div>
                    <p className="text-[#646b73]">RAW MATERIAL LOT</p>
                    <h3 className="mt-1 text-sm font-bold">{chain.lot?.lot_code || chain.batch.input_lot_ref}</h3>
                    <p className="mt-2">{chain.supplier?.supplier_name || "Supplier unresolved"} ({chain.supplier?.supplier_id || "source conflict"})</p>
                    <p>{chain.lot?.material_name || "No matching receipt"}</p>
                    <p>{chain.lot?.receipt_date || ""} · Grade {chain.lot?.quality_grade || "unknown"}</p>
                    <p className={chain.lot_resolution === "complaint_ground_truth" ? "mt-2 text-ok" : "mt-2 text-amber-700"}>
                      Resolution: {chain.lot_resolution}
                    </p>
                  </div>
                  <div>
                    <p className="text-[#646b73]">QC INSPECTION</p>
                    <h3 className={`mt-1 text-sm font-bold ${chain.qc.status === "FAIL" ? "text-bad" : "text-ok"}`}>
                      {chain.qc.status} · {chain.qc.defect_rate_pct}%
                    </h3>
                    <p className="mt-2">{chain.qc.defect_type || "No defect type"}</p>
                    <p>Source label: {chain.qc.defect_type_raw || "-"}</p>
                    <p>{chain.qc.inspection_date} · Inspector {chain.qc.inspector_id}</p>
                    <p>Rework: {chain.qc.rework_flag}</p>
                  </div>
                </div>
              </article>
            ))}
            {trace.unresolved_batch_refs.length > 0 && (
              <p className="text-amber-700">Unmatched batch references: {trace.unresolved_batch_refs.join(", ")}</p>
            )}
            {trace.related_complaints.map((complaint: any) => (
              <p key={complaint.complaint_id} className="border-l-2 border-bad pl-3">
                {complaint.complaint_id}: {complaint.defect_description} · INR {complaint.financial_impact_inr.toLocaleString()}
              </p>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3 border-t border-[#d9d5cb] pt-5">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            void loadAlert();
          }}
        >
          <label className="grid gap-1">
            <span className="text-[#646b73]">CONTAMINATION LOT</span>
            <input value={lotCode} onChange={(event) => setLotCode(event.target.value)} className="w-56 border border-[#d9d5cb] px-2 py-2" />
          </label>
          <button type="submit" className="bg-bad px-4 py-2 text-white">Trace downstream exposure</button>
        </form>

        {alertError && <p role="alert" className="text-bad">{alertError}</p>}
        {alert && (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-x-6 gap-y-2 border-y border-[#d9d5cb] py-3">
              <p><b>{alert.affected_batches.length}</b> affected batches</p>
              <p><b>{alert.affected_dispatches.length}</b> linked dispatch orders</p>
              <p>{alert.lot.resolution_status}: {alert.supplier?.supplier_name || "supplier conflict"}</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-[#d9d5cb] text-[#646b73]">
                    <th className="py-2">ORDER</th><th>OEM</th><th>SHIPMENT DATE</th><th>PRODUCT</th><th>QUANTITY</th><th>AFFECTED BATCHES</th>
                  </tr>
                </thead>
                <tbody>
                  {alert.affected_dispatches.map((order: any) => (
                    <tr key={order.order_id} className="border-b border-[#d9d5cb]">
                      <td className="py-2 font-bold">{order.order_id}</td>
                      <td>{order.customer_id}</td><td>{order.dispatch_date}</td><td>{order.product_type}</td>
                      <td>{order.quantity}</td><td>{order.affected_batch_refs.join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {alert.related_complaints.map((complaint: any) => (
              <p key={complaint.complaint_id} className="text-[#646b73]">
                Historical complaint {complaint.complaint_id}: affected orders {complaint.affected_order_ids.join(", ")} · INR {complaint.financial_impact_inr.toLocaleString()}
              </p>
            ))}
            <p className="text-amber-700">
              Dataset note: {alert.unmatched_batch_references_in_dataset.toLocaleString()} dispatch batch references elsewhere in the source files remain unresolved and are not treated as linked.
            </p>
          </div>
        )}
      </section>

      {trace?.data_quality && (
        <details className="border-t border-[#d9d5cb] pt-4 text-[#646b73]">
          <summary className="cursor-pointer font-bold">SOURCE CLEANING NOTES</summary>
          <p className="mt-2">{trace.data_quality.imputation_policy}</p>
          <p className="mt-1">{trace.data_quality.lot_resolution_policy}</p>
          <p className="mt-1">{trace.data_quality.date_policy}</p>
        </details>
      )}
    </div>
  );
};
