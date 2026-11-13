import React, { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { apiRequest } from "../services/api";

export const SuppliersPage: React.FC = () => {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => {
    apiRequest<any[]>("/manufacturing/suppliers").then(setItems);
  }, []);
  return (
    <div className="bg-white border border-[#d9d5cb] rounded-md p-4">
      <h2 className="font-mono font-bold text-sm mb-3">SUPPLIERS</h2>
      <table className="w-full text-xs font-mono text-left border-collapse">
        <thead>
          <tr className="border-b border-[#d9d5cb] text-[#646b73]">
            <th className="py-2">CODE</th>
            <th>NAME</th>
            <th>MATERIAL</th>
            <th>WALLET</th>
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.id} className="border-b border-[#d9d5cb]">
              <td className="py-2 font-bold">{s.code}</td>
              <td>{s.name}</td>
              <td>{s.material_category}</td>
              <td>{s.wallet_address}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export const LotsPage: React.FC = () => {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => {
    apiRequest<any[]>("/manufacturing/lots").then(setItems);
  }, []);
  return (
    <div className="bg-white border border-[#d9d5cb] rounded-md p-4">
      <h2 className="font-mono font-bold text-sm mb-3">SUPPLIER LOTS</h2>
      <table className="w-full text-xs font-mono text-left border-collapse">
        <thead>
          <tr className="border-b border-[#d9d5cb] text-[#646b73]">
            <th className="py-2">LOT CODE</th>
            <th>SUPPLIER</th>
            <th>MATERIAL</th>
            <th>QUANTITY</th>
            <th>QC STATUS</th>
            <th>RISK</th>
            <th>DATA RESOLUTION</th>
          </tr>
        </thead>
        <tbody>
          {items.map((l) => (
            <tr key={l.id} className="border-b border-[#d9d5cb]">
              <td className="py-2 font-bold">{l.lot_code}</td>
              <td>{l.supplier_code}</td>
              <td>{l.material_name}</td>
              <td>{l.quantity_received} {l.unit_of_measure}</td>
              <td>{l.qc_status}</td>
              <td className={l.risk_status === "AT_RISK" ? "text-bad font-bold" : "text-ok"}>
                {l.risk_status}
              </td>
              <td>{l.resolution_status} · {l.source_row_count} source rows</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export const BatchesPage: React.FC = () => {
  const [items, setItems] = useState<any[]>([]);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  useEffect(() => {
    apiRequest<any[]>("/manufacturing/batches").then(setItems);
  }, []);
  const filtered = items.filter((batch) =>
    [batch.batch_code, batch.input_lot_ref, batch.machine_id, batch.shift, batch.operator_id]
      .join(" ")
      .toLowerCase()
      .includes(query.trim().toLowerCase())
  );
  const pageSize = 50;
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const visible = filtered.slice(page * pageSize, (page + 1) * pageSize);
  return (
    <div className="bg-white border border-[#d9d5cb] rounded-md p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-mono font-bold text-sm">PRODUCTION BATCHES ({items.length.toLocaleString()} CSV ROWS)</h2>
        <input value={query} onChange={(event) => { setQuery(event.target.value); setPage(0); }} placeholder="Filter batch, lot, machine, shift, operator" className="w-full max-w-sm border border-[#d9d5cb] px-2 py-1.5 font-mono text-xs" />
      </div>
      <div className="overflow-x-auto">
      <table className="w-full text-xs font-mono text-left border-collapse">
        <thead>
          <tr className="border-b border-[#d9d5cb] text-[#646b73]">
            <th className="py-2">BATCH ID</th>
            <th>MACHINE</th>
            <th>SHIFT</th>
            <th>OPERATOR</th>
            <th>PRODUCTION DATE</th>
            <th>INPUT LOT</th>
            <th>UNITS</th>
            <th>QC / DEFECT RATE</th>
            <th>RISK</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((b) => (
            <tr key={b.id} className="border-b border-[#d9d5cb]">
              <td className="py-2 font-bold">{b.batch_code}</td>
              <td>{b.machine_id}</td>
              <td>{b.shift}</td>
              <td>{b.operator_id}</td>
              <td>{b.production_date}</td>
              <td>{b.input_lot_ref}</td>
              <td>{b.units_produced}</td>
              <td className={b.qc_status === "FAIL" ? "text-bad font-bold" : "text-ok"}>
                {b.qc_status} · {b.defect_rate_pct}% · {b.defect_type || "-"}
              </td>
              <td>{b.risk_status}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <div className="flex items-center justify-end gap-3 text-xs font-mono">
        <span>{filtered.length ? page * pageSize + 1 : 0}-{Math.min((page + 1) * pageSize, filtered.length)} of {filtered.length.toLocaleString()}</span>
        <button aria-label="Previous batch page" title="Previous page" disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))} className="p-1 disabled:opacity-40"><ChevronLeft className="h-4 w-4" /></button>
        <button aria-label="Next batch page" title="Next page" disabled={page + 1 >= pageCount} onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))} className="p-1 disabled:opacity-40"><ChevronRight className="h-4 w-4" /></button>
      </div>
    </div>
  );
};

export const DispatchesPage: React.FC = () => {
  const [items, setItems] = useState<any[]>([]);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  useEffect(() => {
    apiRequest<any[]>("/manufacturing/dispatches").then(setItems);
  }, []);
  const filtered = items.filter((dispatch) =>
    [dispatch.dispatch_code, dispatch.buyer_code, dispatch.product_type, dispatch.source_batches.join(" ")]
      .join(" ")
      .toLowerCase()
      .includes(query.trim().toLowerCase())
  );
  const pageSize = 50;
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const visible = filtered.slice(page * pageSize, (page + 1) * pageSize);
  return (
    <div className="bg-white border border-[#d9d5cb] rounded-md p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-mono font-bold text-sm">DISPATCH ORDERS ({items.length.toLocaleString()} CSV ROWS)</h2>
        <input value={query} onChange={(event) => { setQuery(event.target.value); setPage(0); }} placeholder="Filter order, OEM, product, or batch" className="w-full max-w-sm border border-[#d9d5cb] px-2 py-1.5 font-mono text-xs" />
      </div>
      <div className="overflow-x-auto">
      <table className="w-full text-xs font-mono text-left border-collapse">
        <thead>
          <tr className="border-b border-[#d9d5cb] text-[#646b73]">
            <th className="py-2">DISPATCH ID</th>
            <th>OEM BUYER</th>
            <th>SHIPMENT DATE</th>
            <th>PRODUCT</th>
            <th>QUANTITY</th>
            <th>VEHICLE</th>
            <th>SOURCE BATCHES</th>
            <th>RISK STATUS</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((d) => (
            <tr key={d.id} className="border-b border-[#d9d5cb]">
              <td className="py-2 font-bold">{d.dispatch_code}</td>
              <td>{d.buyer_code} ({d.buyer_name})</td>
              <td>{d.dispatch_date}</td>
              <td>{d.product_type}</td>
              <td>{d.quantity_pcs} pcs</td>
              <td>{d.vehicle_number}</td>
              <td>{(d.source_batches || []).join(", ")}</td>
              <td className={d.risk_status === "AT_RISK" ? "text-bad font-bold" : "text-ok"}>
                {d.risk_status}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <div className="flex items-center justify-end gap-3 text-xs font-mono">
        <span>{filtered.length ? page * pageSize + 1 : 0}-{Math.min((page + 1) * pageSize, filtered.length)} of {filtered.length.toLocaleString()}</span>
        <button aria-label="Previous dispatch page" title="Previous page" disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))} className="p-1 disabled:opacity-40"><ChevronLeft className="h-4 w-4" /></button>
        <button aria-label="Next dispatch page" title="Next page" disabled={page + 1 >= pageCount} onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))} className="p-1 disabled:opacity-40"><ChevronRight className="h-4 w-4" /></button>
      </div>
    </div>
  );
};
