import React, { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { apiRequest } from "../services/api";

export const DashboardPage: React.FC<{ bcStatus: any; wallet: any }> = ({ bcStatus, wallet }) => {
  const [summary, setSummary] = useState<any>(null);
  const [batches, setBatches] = useState<any[]>([]);
  const [escrow, setEscrow] = useState<any>(null);
  const [txMsg, setTxMsg] = useState<string>("");

  const loadData = async () => {
    const [sumRes, batchRes] = await Promise.all([
      apiRequest<any>("/manufacturing/summary"),
      apiRequest<any[]>("/manufacturing/batches?lot=LOT-2023-114"),
    ]);
    setSummary(sumRes);
    setBatches(batchRes);
    try {
      const escRes = await apiRequest<any>("/blockchain/escrow/PO-1001");
      setEscrow(escRes);
    } catch {
      setEscrow(null);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleAnchorSnapshot = async () => {
    setTxMsg("Preparing Merkle snapshot v2...");
    try {
      const prep = await apiRequest<any>("/blockchain/snapshot/prepare/2");
      const mfgContract = bcStatus?.contracts?.ManufacturingRegistry;
      if (wallet.account && mfgContract) {
        const hash = await wallet.submitSnapshotMetaMask(
          mfgContract.address,
          mfgContract.abi,
          2,
          prep.root_hash,
          prep.metadata_hash
        );
        setTxMsg(`MetaMask Snapshot v2 anchored! Tx: ${hash}`);
      } else {
        const res = await apiRequest<any>("/blockchain/snapshot/anchor/2", { method: "POST" });
        setTxMsg(`Backend Operator anchored Snapshot v2! Tx: ${res.transaction.tx_hash}`);
      }
    } catch (err: any) {
      setTxMsg(`Error: ${err.message}`);
    }
  };

  if (!summary) return <div className="font-mono text-sm">Loading BlockTrace-X telemetry...</div>;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white border border-[#d9d5cb] rounded-md p-4">
          <div className="text-xs font-mono text-[#646b73]">PRIMARY LOT</div>
          <div className="text-xl font-mono font-bold mt-1">LOT-2023-114</div>
          <div className="text-xs text-[#646b73] mt-1">Supplier S03 · Bonding Agent</div>
        </div>
        <div className="bg-white border border-[#d9d5cb] rounded-md p-4">
          <div className="text-xs font-mono text-[#646b73]">PRODUCTION BATCHES</div>
          <div className="text-xl font-mono font-bold mt-1">{summary.batches_count}</div>
          <div className="text-xs text-bad mt-1">{summary.failed_qc_batches} QC Failed Batches</div>
        </div>
        <div className="bg-white border border-[#d9d5cb] rounded-md p-4">
          <div className="text-xs font-mono text-[#646b73]">DISPATCH ORDERS</div>
          <div className="text-xl font-mono font-bold mt-1">{summary.dispatch_orders_count} Orders</div>
          <div className="text-xs text-[#646b73] mt-1">
            {summary.total_dispatched_pcs.toLocaleString()} pcs shipped
          </div>
        </div>
        <div className="bg-white border border-[#d9d5cb] rounded-md p-4">
          <div className="text-xs font-mono text-[#646b73]">PO-1001 VALUE / ESCROW</div>
          <div className="text-xl font-mono font-bold mt-1">₹2,00,000</div>
          <div className="text-xs text-ok mt-1">
            On-chain Test Escrow: {escrow?.onchain_escrow?.d_cum_eth || "2.0"} ETH
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white border border-[#d9d5cb] rounded-md p-4">
          <h2 className="font-mono text-xs text-[#646b73] mb-3">
            LOT-2023-114 DESCENDANT BATCH DEFECT RATES (%)
          </h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={batches}>
                <XAxis dataKey="batch_code" tick={{ fontSize: 10 }} interval={2} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="defect_rate_pct" name="Defect Rate %">
                  {batches.map((entry, idx) => (
                    <Cell
                      key={idx}
                      fill={entry.qc_status === "FAIL" ? "#c2332b" : "#1d7a4d"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-white border border-[#d9d5cb] rounded-md p-4 flex flex-col justify-between">
          <div>
            <h2 className="font-mono text-xs text-[#646b73] mb-3">
              ON-CHAIN SNAPSHOT & SIX-BUCKET ESCROW
            </h2>
            {escrow?.onchain_escrow ? (
              <div className="space-y-2 text-xs font-mono">
                <div>Status: <b>{escrow.onchain_escrow.status}</b></div>
                <div>Fa (Available): <b>{escrow.onchain_escrow.fa_eth} ETH</b></div>
                <div>Fr (Warranty Reserve): <b>{escrow.onchain_escrow.fr_eth} ETH</b></div>
                <div>Fd (Disputed Frozen): <b>{escrow.onchain_escrow.fd_eth} ETH</b></div>
                <div>Ps (Supplier Paid): <b>{escrow.onchain_escrow.ps_eth} ETH</b></div>
                <div>Pb (Buyer Refunded): <b>{escrow.onchain_escrow.pb_eth} ETH</b></div>
                <div>Pc (3rd Party Comp): <b>{escrow.onchain_escrow.pc_eth} ETH</b></div>
                <div className="pt-1 text-ok">
                  Invariant Dcum = ΣBuckets: {escrow.onchain_escrow.conservation_valid ? "VERIFIED ✓" : "VIOLATED"}
                </div>
              </div>
            ) : (
              <p className="text-xs text-[#646b73]">
                Start Hardhat node and deploy contracts to inspect live ETH escrow buckets.
              </p>
            )}
          </div>

          <div className="mt-4 pt-3 border-t border-[#d9d5cb]">
            <button
              onClick={handleAnchorSnapshot}
              className="w-full bg-brand text-white font-mono text-xs py-2 rounded hover:opacity-95"
            >
              Anchor Snapshot Commitment On-Chain
            </button>
            {txMsg && (
              <p className="mt-2 text-xs font-mono break-all text-brand">{txMsg}</p>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-2 border-t border-[#d9d5cb] pt-3 font-mono text-xs text-[#646b73]">
        <span>CSV batches: {summary.batches_count.toLocaleString()}</span>
        <span>Imputed batch IDs: {summary.data_quality.imputed_batch_ids.toLocaleString()}</span>
        <span>Unresolved dispatch refs: {summary.data_quality.unmatched_dispatch_batch_references.toLocaleString()}</span>
        <span>Ambiguous lot codes: {summary.data_quality.unresolved_lot_conflicts.toLocaleString()}</span>
      </div>
    </div>
  );
};
