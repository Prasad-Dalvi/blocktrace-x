import React, { useEffect, useState } from "react";
import { apiRequest } from "../services/api";

// 14. Purchase Orders Page
export const PurchaseOrdersPage: React.FC = () => {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    apiRequest<any[]>("/escrow/all").then(setRows);
  }, []);
  return (
    <div className="bg-white border border-[#d9d5cb] rounded-md p-4 font-mono text-xs">
      <h2 className="font-bold text-sm mb-3">PURCHASE ORDERS & ESCROW MAPPING</h2>
      <table className="w-full text-left border-collapse">
        <thead>
          <tr className="border-b border-[#d9d5cb] text-[#646b73]">
            <th className="py-2">PO NUMBER</th>
            <th>SUPPLIER / BUYER</th>
            <th>LOT</th>
            <th>BUSINESS VALUE</th>
            <th>TESTNET ETH</th>
            <th>ESCROW STATUS</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.purchase_order.po_number} className="border-b border-[#d9d5cb]">
              <td className="py-2 font-bold">{r.purchase_order.po_number}</td>
              <td>{r.purchase_order.supplier_code} → {r.purchase_order.buyer_code}</td>
              <td>{r.purchase_order.lot_code}</td>
              <td>₹{Number(r.purchase_order.business_value_inr).toLocaleString("en-IN")}</td>
              <td>{r.purchase_order.testnet_eth_amount} ETH</td>
              <td className="font-bold text-brand">{r.escrow?.status || r.purchase_order.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

// 15. Escrow Management (Six-Bucket Conservation & Lifecycle)
export const EscrowManagementPage: React.FC = () => {
  const [rows, setRows] = useState<any[]>([]);
  const [amountEth, setAmountEth] = useState("0.6");
  const [msg, setMsg] = useState("");

  const load = () => apiRequest<any[]>("/escrow/all").then(setRows);
  useEffect(() => {
    load();
  }, []);

  const runAction = async (poNumber: string, action: string, passed = true) => {
    setMsg(`Submitting on-chain transaction: ${action} for ${poNumber}...`);
    try {
      const res = await apiRequest<any>(`/escrow/${poNumber}/action`, {
        method: "POST",
        body: JSON.stringify({ action, amount_eth: amountEth, passed }),
      });
      setMsg(`Confirmed ${action}! Tx: ${res.transaction.tx_hash} · New State: ${res.escrow.status}`);
      load();
    } catch (err: any) {
      setMsg(`Transaction Error: ${err.message}`);
    }
  };

  return (
    <div className="space-y-4 font-mono text-xs">
      <div className="bg-white border border-[#d9d5cb] rounded-md p-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-bold text-sm">SOLIDITY SIX-BUCKET ESCROW CUSTODY (Dcum = Ps + Pb + Pc + Fd + Fr + Fa)</h2>
          <p className="text-[#646b73]">State transitions executed directly on SupplyChainEscrow.sol on Hardhat.</p>
        </div>
        <div className="flex items-center gap-2">
          <span>Amount (ETH):</span>
          <input value={amountEth} onChange={(e) => setAmountEth(e.target.value)} className="border border-[#d9d5cb] rounded px-2 py-1 w-24" />
        </div>
      </div>

      {msg && <div className="p-3 bg-white border border-[#d9d5cb] rounded text-brand break-all">{msg}</div>}

      {rows.map((r) => {
        const e = r.escrow;
        if (!e) return null;
        return (
          <div key={e.po_number} className="bg-white border border-[#d9d5cb] rounded-md p-4 space-y-4">
            <div className="flex justify-between items-center">
              <div className="font-bold text-sm">{e.po_number} · State: <span className="text-brand">{e.status}</span></div>
              <div className={e.conservation_valid ? "text-ok font-bold" : "text-bad font-bold"}>
                Conservation Invariant (Dcum = {e.buckets.D_cum} ETH): {e.conservation_valid ? "HOLDING ✓" : "VIOLATED"}
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
              <div className="p-2 border border-[#d9d5cb] rounded"><div className="text-[#646b73]">Fa (Available)</div><b>{e.buckets.Fa} ETH</b></div>
              <div className="p-2 border border-[#d9d5cb] rounded"><div className="text-[#646b73]">Fr (Reserve)</div><b>{e.buckets.Fr} ETH</b></div>
              <div className="p-2 border border-[#d9d5cb] rounded"><div className="text-[#646b73]">Fd (Frozen)</div><b className="text-bad">{e.buckets.Fd} ETH</b></div>
              <div className="p-2 border border-[#d9d5cb] rounded"><div className="text-[#646b73]">Ps (Supplier)</div><b className="text-ok">{e.buckets.Ps} ETH</b></div>
              <div className="p-2 border border-[#d9d5cb] rounded"><div className="text-[#646b73]">Pb (Refund)</div><b>{e.buckets.Pb} ETH</b></div>
              <div className="p-2 border border-[#d9d5cb] rounded"><div className="text-[#646b73]">Pc (3rd Party)</div><b>{e.buckets.Pc} ETH</b></div>
            </div>

            <div className="flex flex-wrap gap-2">
              <button onClick={() => runAction(e.po_number, "ship")} className="px-3 py-1.5 border border-[#d9d5cb] rounded hover:border-brand">1. Mark Shipped</button>
              <button onClick={() => runAction(e.po_number, "receive")} className="px-3 py-1.5 border border-[#d9d5cb] rounded hover:border-brand">2. Confirm Receipt</button>
              <button onClick={() => runAction(e.po_number, "release_supplier")} className="px-3 py-1.5 bg-ok text-white rounded">Release Supplier (Fa→Ps)</button>
              <button onClick={() => runAction(e.po_number, "qc", false)} className="px-3 py-1.5 bg-bad text-white rounded">QC Fail & Freeze (→Fd)</button>
              <button onClick={() => runAction(e.po_number, "freeze")} className="px-3 py-1.5 bg-warn text-white rounded">Freeze Disputed (→Fd)</button>
              <button onClick={() => runAction(e.po_number, "close")} className="px-3 py-1.5 bg-slate-800 text-white rounded">Close Escrow</button>
            </div>
          </div>
        );
      })}
    </div>
  );
};

// 16 & 17 & 18. Complaints, Disputes & Settlement Pages
export const ComplaintsDisputesSettlementPage: React.FC<{ mode: "complaints" | "disputes" | "settlement" }> = ({ mode }) => {
  const [complaints, setComplaints] = useState<any[]>([]);
  const [disputes, setDisputes] = useState<any[]>([]);
  const [claimCode, setClaimCode] = useState("CLM-2023-114");
  const [description, setDescription] = useState("Bonding agent LOT-2023-114 failed shear test across 6 batches");
  const [supplierResp, setSupplierResp] = useState("Requesting independent arbitration review of curing profile");
  const [rationale, setRationale] = useState("Partial supplier fault verified; split 0.3 ETH buyer refund / 0.3 ETH supplier release");
  const [supPay, setSupPay] = useState("0.3");
  const [buyRef, setBuyRef] = useState("0.3");
  const [msg, setMsg] = useState("");

  const load = () => {
    apiRequest<any[]>("/complaints").then(setComplaints);
    apiRequest<any[]>("/disputes").then(setDisputes);
  };
  useEffect(() => {
    load();
  }, []);

  const submitComplaint = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await apiRequest<any>("/complaints", {
        method: "POST",
        body: JSON.stringify({
          claim_code: claimCode,
          po_number: "PO-1001",
          defect_event_code: "EVT-2023-114-01",
          description,
          evidence_text: '{"affected_orders":["D-1264","D-1847","D-1921"]}',
        }),
      });
      setMsg(`Complaint ${res.claim_code} registered on ClaimRegistry! Tx: ${res.register_tx_hash || "Recorded"}`);
      load();
    } catch (err: any) {
      setMsg(`Error: ${err.message}`);
    }
  };

  const respondDispute = async (code: string) => {
    try {
      await apiRequest(`/complaints/${code}/respond`, {
        method: "POST",
        body: JSON.stringify({ response_text: supplierResp, escalate_to_dispute: true }),
      });
      setMsg(`Supplier response logged and ${code} escalated to DISPUTED.`);
      load();
    } catch (err: any) {
      setMsg(`Error: ${err.message}`);
    }
  };

  const authorizeAward = async (code: string) => {
    try {
      const res = await apiRequest<any>(`/disputes/${code}/authorize`, {
        method: "POST",
        body: JSON.stringify({
          rationale,
          supplier_payout_eth: supPay,
          buyer_refund_eth: buyRef,
          third_party_comp_eth: "0",
        }),
      });
      setMsg(`Arbitration decision authorized on ClaimRegistry! Tx: ${res.authorize_tx_hash || "Authorized"}`);
      load();
    } catch (err: any) {
      setMsg(`Error: ${err.message}`);
    }
  };

  const settleNow = async (code: string) => {
    try {
      const res = await apiRequest<any>(`/settlements/${code}/execute`, { method: "POST" });
      setMsg(`On-chain ETH settlement confirmed! Tx: ${res.transaction.tx_hash}`);
      load();
    } catch (err: any) {
      setMsg(`Settlement Blocked/Error: ${err.message}`);
    }
  };

  return (
    <div className="space-y-6 font-mono text-xs">
      {msg && <div className="p-3 bg-white border border-[#d9d5cb] rounded text-brand break-all">{msg}</div>}

      {mode === "complaints" && (
        <form onSubmit={submitComplaint} className="bg-white border border-[#d9d5cb] rounded-md p-4 space-y-3">
          <h2 className="font-bold text-sm">FILE BUYER COMPLAINT & REGISTER CLAIM ON-CHAIN</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input value={claimCode} onChange={(e) => setClaimCode(e.target.value)} className="border border-[#d9d5cb] rounded px-2 py-1.5" required />
            <input value={description} onChange={(e) => setDescription(e.target.value)} className="border border-[#d9d5cb] rounded px-2 py-1.5" required />
          </div>
          <button type="submit" className="px-4 py-2 bg-brand text-white rounded">Submit Complaint Claim</button>
        </form>
      )}

      {mode === "disputes" && (
        <div className="bg-white border border-[#d9d5cb] rounded-md p-4 space-y-3">
          <h2 className="font-bold text-sm">SUPPLIER RESPONSE & ARBITRATOR RESOLUTION</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <input value={supplierResp} onChange={(e) => setSupplierResp(e.target.value)} placeholder="Supplier Response" className="border border-[#d9d5cb] rounded px-2 py-1.5" />
            <input value={supPay} onChange={(e) => setSupPay(e.target.value)} placeholder="Supplier ETH" className="border border-[#d9d5cb] rounded px-2 py-1.5" />
            <input value={buyRef} onChange={(e) => setBuyRef(e.target.value)} placeholder="Buyer Refund ETH" className="border border-[#d9d5cb] rounded px-2 py-1.5" />
          </div>
          <input value={rationale} onChange={(e) => setRationale(e.target.value)} className="w-full border border-[#d9d5cb] rounded px-2 py-1.5" />
        </div>
      )}

      <div className="bg-white border border-[#d9d5cb] rounded-md p-4 overflow-x-auto">
        <h2 className="font-bold text-sm mb-3">ACTIVE CLAIMS & DISPUTE PIPELINE</h2>
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[#d9d5cb] text-[#646b73]">
              <th className="py-2">CLAIM ID</th>
              <th>PO / DEFECT</th>
              <th>STATUS</th>
              <th>DESCRIPTION</th>
              <th>WORKFLOW ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {complaints.map((c) => (
              <tr key={c.claim_code} className="border-b border-[#d9d5cb]">
                <td className="py-2 font-bold">{c.claim_code}</td>
                <td>{c.po_number} · {c.defect_event_code}</td>
                <td className="font-bold">{c.status}</td>
                <td>{c.description}</td>
                <td className="space-x-1 py-1">
                  <button onClick={() => respondDispute(c.claim_code)} className="px-2 py-1 bg-warn text-white rounded">Supplier Dispute</button>
                  <button onClick={() => authorizeAward(c.claim_code)} className="px-2 py-1 bg-brand text-white rounded">Arbitrator Authorize</button>
                  <button onClick={() => settleNow(c.claim_code)} className="px-2 py-1 bg-ok text-white rounded">Execute Settlement</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {disputes.length > 0 && (
        <div className="bg-white border border-[#d9d5cb] rounded-md p-4 overflow-x-auto">
          <h2 className="font-bold text-sm mb-2">AUTHORIZED ARBITRATION AWARDS & ON-CHAIN SETTLEMENTS</h2>
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-[#d9d5cb] text-[#646b73]">
                <th className="py-2">CLAIM</th>
                <th>SUPPLIER ETH</th>
                <th>BUYER REFUND ETH</th>
                <th>SETTLED</th>
                <th>SETTLEMENT TX HASH</th>
              </tr>
            </thead>
            <tbody>
              {disputes.map((d) => (
                <tr key={d.claim_code} className="border-b border-[#d9d5cb]">
                  <td className="py-2 font-bold">{d.claim_code}</td>
                  <td>{d.supplier_payout_eth} ETH</td>
                  <td>{d.buyer_refund_eth} ETH</td>
                  <td className={d.settled ? "text-ok font-bold" : "text-warn"}>{d.settled ? "CONFIRMED ✓" : "PENDING"}</td>
                  <td>{d.settlement_tx_hash || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

// 20. Tamper-Evident Audit Ledger Page
export const AuditLedgerPage: React.FC = () => {
  const [entries, setEntries] = useState<any[]>([]);
  const [ver, setVer] = useState<any>(null);

  useEffect(() => {
    apiRequest<any[]>("/audit-ledger").then(setEntries);
    apiRequest<any>("/audit-ledger/verify").then(setVer);
  }, []);

  return (
    <div className="space-y-4 font-mono text-xs">
      {ver && (
        <div className="bg-white border border-[#d9d5cb] rounded-md p-4">
          <div className="font-bold text-sm">
            OFF-CHAIN SHA-256 AUDIT CHAIN INTEGRITY:{" "}
            <span className={ver.valid ? "text-ok" : "text-bad"}>{ver.valid ? "VERIFIED ✓" : "TAMPERED ✗"}</span>
          </div>
          <div className="text-[#646b73] mt-1">{ver.ledger_type} · Entries verified: {ver.checked_entries}</div>
        </div>
      )}
      <div className="bg-white border border-[#d9d5cb] rounded-md p-4 overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[#d9d5cb] text-[#646b73]">
              <th className="py-2">#</th>
              <th>CATEGORY</th>
              <th>ACTION</th>
              <th>ACTOR</th>
              <th>LINKED ON-CHAIN TX</th>
              <th>ENTRY SHA-256</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id} className="border-b border-[#d9d5cb]">
                <td className="py-2 font-bold">#{e.sequence_num}</td>
                <td>{e.category}</td>
                <td>{e.action}</td>
                <td>{e.actor_email}</td>
                <td>{e.onchain_tx_hash ? `${e.onchain_tx_hash.slice(0, 14)}…` : "Off-chain"}</td>
                <td>{e.entry_hash.slice(0, 18)}…</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// 21, 22, 23. Reports, Users & Settings Pages
export const ReportsUsersSettingsPage: React.FC<{ section: "reports" | "users" | "settings"; bcStatus: any }> = ({ section, bcStatus }) => {
  const [users, setUsers] = useState<any[]>([]);
  useEffect(() => {
    if (section === "users") {
      apiRequest<any[]>("/users").then(setUsers).catch(() => {});
    }
  }, [section]);

  if (section === "users") {
    return (
      <div className="bg-white border border-[#d9d5cb] rounded-md p-4 font-mono text-xs">
        <h2 className="font-bold text-sm mb-3">ROLE-BASED ACCESS CONTROL USERS</h2>
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[#d9d5cb] text-[#646b73]">
              <th className="py-2">NAME</th>
              <th>EMAIL</th>
              <th>ROLE</th>
              <th>BOUND WALLET</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-[#d9d5cb]">
                <td className="py-2 font-bold">{u.full_name}</td>
                <td>{u.email}</td>
                <td>{u.role}</td>
                <td>{u.wallet_address}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (section === "settings") {
    return (
      <div className="bg-white border border-[#d9d5cb] rounded-md p-4 font-mono text-xs space-y-2">
        <h2 className="font-bold text-sm">SYSTEM & BLOCKCHAIN CONFIGURATION</h2>
        <div>RPC Endpoint: <b>{bcStatus?.network?.rpc_url || "http://127.0.0.1:8545"}</b></div>
        <div>Chain ID: <b>{bcStatus?.network?.chain_id || 31337}</b></div>
        <div>Late-Edge Gate Defaults: <b>Amax = 2 versions, Tlate = 3600 seconds</b></div>
        <div>Bayesian Defaults: <b>Prior = 0.15, Sensitivity = 0.92, False-Support = 0.08</b></div>
      </div>
    );
  }

  return (
    <div className="bg-white border border-[#d9d5cb] rounded-md p-4 font-mono text-xs space-y-3">
      <h2 className="font-bold text-sm">EXPORTABLE COMPLIANCE & PROVENANCE REPORTS</h2>
      <p className="text-[#646b73]">Generate JSON audit bundles combining Merkle snapshot proofs, Bayesian risk classifications, and EVM settlement receipts.</p>
      <a
        href="http://localhost:5000/api/health"
        target="_blank"
        rel="noreferrer"
        className="inline-block px-4 py-2 bg-brand text-white rounded"
      >
        Inspect Live Backend Telemetry Endpoint
      </a>
    </div>
  );
};
