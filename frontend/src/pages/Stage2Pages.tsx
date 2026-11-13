import React, { useEffect, useState } from "react";
import { apiRequest } from "../services/api";

// 1. Snapshot Management Page
export const SnapshotManagementPage: React.FC = () => {
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const [verifyRes, setVerifyRes] = useState<any>(null);
  const [msg, setMsg] = useState("");

  const load = () => apiRequest<any[]>("/snapshots").then(setSnapshots);
  useEffect(() => {
    load();
  }, []);

  const handleSeal = async () => {
    setMsg("Sealing canonical snapshot & anchoring Merkle root...");
    try {
      const res = await apiRequest<any>("/snapshots/seal", {
        method: "POST",
        body: JSON.stringify({ anchor_onchain: true }),
      });
      setMsg(`Sealed Snapshot v${res.snapshot.version} · Root: ${res.snapshot.global_root.slice(0, 18)}…`);
      load();
    } catch (err: any) {
      setMsg(`Error: ${err.message}`);
    }
  };

  const handleVerify = async (version: number) => {
    const res = await apiRequest<any>(`/snapshots/${version}/verify`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    setVerifyRes(res);
  };

  return (
    <div className="space-y-4 font-mono text-xs">
      <div className="bg-white border border-[#d9d5cb] rounded-md p-4 flex items-center justify-between">
        <div>
          <h2 className="font-bold text-sm">AUTHENTICATED GRAPH SNAPSHOTS (MODULE 1)</h2>
          <p className="text-[#646b73]">
            Canonically ordered adjacency lists, degree commitments, and chained Merkle roots.
          </p>
        </div>
        <button onClick={handleSeal} className="px-4 py-2 bg-brand text-white rounded">
          Seal New Snapshot Version
        </button>
      </div>

      {msg && <div className="p-3 bg-white border border-[#d9d5cb] rounded text-brand">{msg}</div>}

      {verifyRes && (
        <div className="p-4 bg-white border border-[#d9d5cb] rounded space-y-1">
          <div className="font-bold">
            Verification v{verifyRes.version}:{" "}
            <span className={verifyRes.verified ? "text-ok" : "text-bad"}>
              {verifyRes.verified ? "VERIFIED ✓" : "MISMATCH ✗"}
            </span>
          </div>
          <div>Local Consistent: {String(verifyRes.local_consistent)} · On-Chain Match: {String(verifyRes.onchain_match)}</div>
          <div className="text-[#646b73]">{verifyRes.attestation_scope}</div>
        </div>
      )}

      <div className="bg-white border border-[#d9d5cb] rounded-md p-4 overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[#d9d5cb] text-[#646b73]">
              <th className="py-2">VERSION</th>
              <th>NODES / EDGES</th>
              <th>GLOBAL ROOT</th>
              <th>ON-CHAIN TX</th>
              <th>ACTION</th>
            </tr>
          </thead>
          <tbody>
            {snapshots.map((s) => (
              <tr key={s.version} className="border-b border-[#d9d5cb]">
                <td className="py-2 font-bold">v{s.version}</td>
                <td>{s.node_count} / {s.relation_count}</td>
                <td>{s.global_root.slice(0, 22)}…</td>
                <td>{s.commitment?.tx_hash ? `${s.commitment.tx_hash.slice(0, 14)}…` : "Local Only"}</td>
                <td>
                  <button
                    onClick={() => handleVerify(s.version)}
                    className="px-2.5 py-1 border border-[#d9d5cb] rounded hover:border-brand"
                  >
                    Verify Root
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// 2 & 3. Defect Reporting & Inspector Attestation Page
export const DefectAttestationPage: React.FC = () => {
  const [events, setEvents] = useState<any[]>([]);
  const [eventCode, setEventCode] = useState("EVT-2023-114-02");
  const [lotCode, setLotCode] = useState("LOT-2023-114");
  const [snapVersion, setSnapVersion] = useState(1);
  const [severity, setSeverity] = useState(4);
  const [evidencePayload, setEvidencePayload] = useState('{"test":"DSC_cure_profile","deviation_pct":18.4}');
  const [msg, setMsg] = useState("");

  const load = () => apiRequest<any[]>("/defects").then(setEvents);
  useEffect(() => {
    load();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await apiRequest("/defects", {
        method: "POST",
        body: JSON.stringify({
          event_code: eventCode,
          lot_code: lotCode,
          snapshot_version: snapVersion,
          severity,
          evidence_filename: "lab_evidence.json",
          evidence_payload: evidencePayload,
          quorum_required: 2,
        }),
      });
      setMsg(`Defect event ${eventCode} submitted and bound to Snapshot v${snapVersion}.`);
      load();
    } catch (err: any) {
      setMsg(`Error: ${err.message}`);
    }
  };

  const handleAttest = async (code: string, decision: "SUPPORT" | "CONTRADICT", inspectorEmail?: string) => {
    try {
      const res = await apiRequest<any>(`/defects/${code}/attest`, {
        method: "POST",
        body: JSON.stringify({
          decision,
          confidence: 0.95,
          inspector_email: inspectorEmail,
          notes: `Inspector ${decision} attestation`,
        }),
      });
      setMsg(`Attested ${decision} on ${code}. Current status: ${res.status}`);
      load();
    } catch (err: any) {
      setMsg(`Error: ${err.message}`);
    }
  };

  const handleAnchor = async (code: string) => {
    try {
      const res = await apiRequest<any>(`/defects/${code}/anchor`, { method: "POST" });
      setMsg(`Anchored ${code} on-chain! Tx: ${res.onchain_tx_hash}`);
      load();
    } catch (err: any) {
      setMsg(`Error: ${err.message}`);
    }
  };

  return (
    <div className="space-y-6 font-mono text-xs">
      <form onSubmit={handleCreate} className="bg-white border border-[#d9d5cb] rounded-md p-4 space-y-3">
        <h2 className="font-bold text-sm">SUBMIT DEFECT EVENT e = (id, lot, g, c(g), ev, S)</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <input value={eventCode} onChange={(e) => setEventCode(e.target.value)} placeholder="Event ID" className="border border-[#d9d5cb] rounded px-2 py-1.5" required />
          <input value={lotCode} onChange={(e) => setLotCode(e.target.value)} placeholder="Lot Code" className="border border-[#d9d5cb] rounded px-2 py-1.5" required />
          <input type="number" value={snapVersion} onChange={(e) => setSnapVersion(Number(e.target.value))} placeholder="Snapshot v" className="border border-[#d9d5cb] rounded px-2 py-1.5" required />
          <input type="number" min={1} max={5} value={severity} onChange={(e) => setSeverity(Number(e.target.value))} placeholder="Severity (1-5)" className="border border-[#d9d5cb] rounded px-2 py-1.5" required />
        </div>
        <textarea value={evidencePayload} onChange={(e) => setEvidencePayload(e.target.value)} rows={2} className="w-full border border-[#d9d5cb] rounded px-2 py-1.5" />
        <button type="submit" className="px-4 py-2 bg-brand text-white rounded">
          Submit & Hash Evidence
        </button>
      </form>

      {msg && <div className="p-3 bg-white border border-[#d9d5cb] rounded text-brand">{msg}</div>}

      <div className="bg-white border border-[#d9d5cb] rounded-md p-4 overflow-x-auto">
        <h2 className="font-bold text-sm mb-3">DEFECT EVENTS & INSPECTOR QUORUM ATTESTATION</h2>
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[#d9d5cb] text-[#646b73]">
              <th className="py-2">EVENT ID</th>
              <th>LOT / SNAP</th>
              <th>SEVERITY</th>
              <th>QUORUM</th>
              <th>STATUS</th>
              <th>ON-CHAIN TX</th>
              <th>ATTESTATION ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.event_code} className="border-b border-[#d9d5cb]">
                <td className="py-2 font-bold">{e.event_code}</td>
                <td>{e.lot_code} @ v{e.snapshot_version}</td>
                <td>S={e.severity}</td>
                <td>{e.support_count}/{e.quorum_required} SUPPORT</td>
                <td className="font-bold">{e.status}</td>
                <td>{e.onchain_tx_hash ? `${e.onchain_tx_hash.slice(0, 12)}…` : "Pending"}</td>
                <td className="space-x-1 py-1">
                  <button onClick={() => handleAttest(e.event_code, "SUPPORT", "qc@blocktracex.io")} className="px-2 py-1 bg-ok text-white rounded">
                    +Support (QC1)
                  </button>
                  <button onClick={() => handleAttest(e.event_code, "SUPPORT", "qc2@blocktracex.io")} className="px-2 py-1 bg-ok text-white rounded">
                    +Support (QC2)
                  </button>
                  <button onClick={() => handleAttest(e.event_code, "CONTRADICT")} className="px-2 py-1 bg-bad text-white rounded">
                    Contradict
                  </button>
                  <button onClick={() => handleAnchor(e.event_code)} className="px-2 py-1 border border-brand text-brand rounded">
                    Anchor
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// 4 & 5. Bounded Propagation & Active Late-Edge Monitoring Page
export const PropagationLateEdgePage: React.FC = () => {
  const [eventCode, setEventCode] = useState("EVT-2023-114-01");
  const [budgetK, setBudgetK] = useState(3);
  const [budgetM, setBudgetM] = useState(8);
  const [budgetZ, setBudgetZ] = useState(3);
  const [statusData, setStatusData] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [lateEdges, setLateEdges] = useState<any[]>([]);
  const [lateChild, setLateChild] = useState("D-2367");
  const [msg, setMsg] = useState("");

  const refresh = async () => {
    try {
      const st = await apiRequest<any>(`/propagation/${eventCode}/status`);
      setStatusData(st);
      const h = await apiRequest<any[]>(`/propagation/${eventCode}/history`);
      setHistory(h);
    } catch {
      setStatusData(null);
    }
    apiRequest<any[]>("/late-edges").then(setLateEdges).catch(() => {});
  };

  useEffect(() => {
    refresh();
  }, [eventCode]);

  const handleStart = async () => {
    try {
      await apiRequest("/propagation/start", {
        method: "POST",
        body: JSON.stringify({ event_code: eventCode }),
      });
      setMsg(`Initialized persistent cursor κ=(0, 1, LOT-2023-114, 0, 0) for ${eventCode}`);
      refresh();
    } catch (err: any) {
      setMsg(`Error: ${err.message}`);
    }
  };

  const handleContinue = async () => {
    try {
      const res = await apiRequest<any>(`/propagation/${eventCode}/continue`, {
        method: "POST",
        body: JSON.stringify({
          K: budgetK,
          M: budgetM,
          Z: budgetZ,
          expected_lambda: statusData?.state?.cursor?.lambda,
        }),
      });
      setMsg(
        `Segment λ=${res.state.cursor.lambda} complete (${res.stop_reason}). Consumed K=${res.segment_consumed.K}, M=${res.segment_consumed.M}, Z=${res.segment_consumed.Z}.`
      );
      refresh();
    } catch (err: any) {
      setMsg(`Error: ${err.message}`);
    }
  };

  const handleLateEdge = async () => {
    try {
      const res = await apiRequest<any>("/late-edges", {
        method: "POST",
        body: JSON.stringify({
          parent_type: "BATCH",
          parent_code: "2023-0791",
          child_type: "DISPATCH",
          child_code: lateChild,
          quantity_consumed: 150,
          recorded_at_version: 2,
          delay_seconds: 60,
          Amax: 2,
          Tlate: 3600,
        }),
      });
      setMsg(`Late edge registered (2023-0791 -> ${lateChild}). Reopened events: ${res.triggered_events.join(", ") || "None"}`);
      refresh();
    } catch (err: any) {
      setMsg(`Error: ${err.message}`);
    }
  };

  return (
    <div className="space-y-6 font-mono text-xs">
      <div className="bg-white border border-[#d9d5cb] rounded-md p-4 space-y-3">
        <h2 className="font-bold text-sm">BOUNDED PROPAGATION & FIXED-SIZE CURSOR κ = (head, tail, u, δ, λ)</h2>
        <div className="flex flex-wrap items-center gap-3">
          <input value={eventCode} onChange={(e) => setEventCode(e.target.value)} className="border border-[#d9d5cb] rounded px-2 py-1.5" />
          <label>K:<input type="number" value={budgetK} onChange={(e) => setBudgetK(Number(e.target.value))} className="w-16 ml-1 border border-[#d9d5cb] rounded px-2 py-1" /></label>
          <label>M:<input type="number" value={budgetM} onChange={(e) => setBudgetM(Number(e.target.value))} className="w-16 ml-1 border border-[#d9d5cb] rounded px-2 py-1" /></label>
          <label>Z:<input type="number" value={budgetZ} onChange={(e) => setBudgetZ(Number(e.target.value))} className="w-16 ml-1 border border-[#d9d5cb] rounded px-2 py-1" /></label>
          <button onClick={handleStart} className="px-3 py-1.5 bg-slate-800 text-white rounded">Start Cursor</button>
          <button onClick={handleContinue} className="px-3 py-1.5 bg-brand text-white rounded">Execute Segment (Continue)</button>
        </div>

        {statusData && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2 border-t border-[#d9d5cb]">
            <div>
              <div>Status: <b>{statusData.state.status}</b></div>
              <div>Queue Progress: <b>{statusData.queue.processed_count} / {statusData.queue.total_enqueued}</b></div>
            </div>
            <div>
              <div>head={statusData.state.cursor.head}, tail={statusData.state.cursor.tail}, δ={statusData.state.cursor.delta}, λ={statusData.state.cursor.lambda}</div>
              <div>Current u: <b>{statusData.state.cursor.u || "DONE"}</b></div>
            </div>
            <div>
              <div>Cumulative K={statusData.state.totals.nodes_visited}, M={statusData.state.totals.relations_scanned}, Z={statusData.state.totals.classifications}</div>
              <div>Commitment: {statusData.state.state_commitment.slice(0, 18)}…</div>
            </div>
          </div>
        )}
      </div>

      {msg && <div className="p-3 bg-white border border-[#d9d5cb] rounded text-brand">{msg}</div>}

      <div className="bg-white border border-[#d9d5cb] rounded-md p-4 space-y-3">
        <h2 className="font-bold text-sm">ACTIVE LATE-EDGE GATE (Amax=2, Tlate=3600s)</h2>
        <div className="flex flex-wrap items-center gap-2">
          <span>Inject late edge at g+1=2: BATCH:2023-0791 → DISPATCH:</span>
          <input value={lateChild} onChange={(e) => setLateChild(e.target.value)} className="border border-[#d9d5cb] rounded px-2 py-1 w-28" />
          <button onClick={handleLateEdge} className="px-3 py-1.5 bg-warn text-white rounded">
            Register Late Edge & Trigger Gate
          </button>
        </div>
        <div className="space-y-1 pt-2">
          {lateEdges.map((le) => (
            <div key={le.id} className="border-b border-[#d9d5cb] py-1">
              [{le.event_code}] {le.parent_key} → {le.child_key} · <b>{le.status}</b> · {le.note}
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white border border-[#d9d5cb] rounded-md p-4">
        <h2 className="font-bold text-sm mb-2">SEGMENT CONTINUATION HISTORY</h2>
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[#d9d5cb] text-[#646b73]">
              <th className="py-1">λ</th>
              <th>BUDGETS (K/M/Z)</th>
              <th>CONSUMED (K/M/Z)</th>
              <th>STOP REASON</th>
            </tr>
          </thead>
          <tbody>
            {history.map((h) => (
              <tr key={h.id} className="border-b border-[#d9d5cb]">
                <td className="py-1 font-bold">λ={h.segment_lambda}</td>
                <td>{h.budgets.K}/{h.budgets.M}/{h.budgets.Z}</td>
                <td>{h.consumed.K}/{h.consumed.M}/{h.consumed.Z}</td>
                <td>{h.stop_reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// 6 & 7. Unit-Level Exposure & Bayesian Risk Dashboard
export const ExposureBayesianPage: React.FC = () => {
  const [eventCode, setEventCode] = useState("EVT-2023-114-01");
  const [exposures, setExposures] = useState<any[]>([]);
  const [riskResult, setRiskResult] = useState<any>(null);

  const runAnalysis = async () => {
    const expRes = await apiRequest<any>(`/exposure/${eventCode}/compute`, { method: "POST" });
    setExposures(expRes.exposures);
    const rRes = await apiRequest<any>(`/risk/${eventCode}/compute`, {
      method: "POST",
      body: JSON.stringify({
        prior_prob: 0.15,
        sensitivity: 0.92,
        false_support_prob: 0.08,
        anchor_onchain: true,
      }),
    });
    setRiskResult(rRes);
  };

  useEffect(() => {
    apiRequest<any[]>(`/exposure/${eventCode}`).then(setExposures).catch(() => {});
  }, [eventCode]);

  const badgeColor = (cls: string) => {
    if (cls === "RECALL_CANDIDATE") return "text-bad font-bold";
    if (cls === "QUARANTINE") return "text-warn font-bold";
    if (cls === "INSPECT") return "text-brand font-bold";
    return "text-ok";
  };

  return (
    <div className="space-y-6 font-mono text-xs">
      <div className="bg-white border border-[#d9d5cb] rounded-md p-4 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="font-bold text-sm">UNIT-LEVEL EXPOSURE Xℓ(v) & BAYESIAN DEFECT RISK R(v)</h2>
          <p className="text-[#646b73]">
            Computes multi-path deduplicated unit exposure and posterior odds Odds(D|E) = Odds(D)·∏LRⱼ.
          </p>
        </div>
        <div className="flex gap-2">
          <input value={eventCode} onChange={(e) => setEventCode(e.target.value)} className="border border-[#d9d5cb] rounded px-2 py-1.5" />
          <button onClick={runAnalysis} className="px-4 py-1.5 bg-brand text-white rounded">
            Compute Exposure & Bayesian Risk
          </button>
        </div>
      </div>

      {riskResult && (
        <div className="bg-white border border-[#d9d5cb] rounded-md p-4 space-y-2">
          <div className="font-bold text-sm">BAYESIAN POSTERIOR PARAMETERS</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>Prior P(D): <b>{riskResult.bayesian_parameters.prior_probability}</b></div>
            <div>LR Product: <b>{riskResult.bayesian_parameters.likelihood_ratio_product}</b></div>
            <div>Posterior Odds: <b>{riskResult.bayesian_parameters.posterior_odds}</b></div>
            <div>Posterior P(D|E): <b className="text-bad">{(riskResult.bayesian_parameters.posterior_probability * 100).toFixed(2)}%</b></div>
          </div>
          <div className="text-[#646b73] pt-1">{riskResult.model_disclaimer}</div>
        </div>
      )}

      {riskResult?.assessments && (
        <div className="bg-white border border-[#d9d5cb] rounded-md p-4 overflow-x-auto">
          <h2 className="font-bold text-sm mb-2">RISK CLASSIFICATION TABLE: R(v) = S × C(v) × Xℓ(v) × P(Dℓ|E)</h2>
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-[#d9d5cb] text-[#646b73]">
                <th className="py-2">NODE</th>
                <th>S</th>
                <th>C(v)</th>
                <th>Xℓ(v)</th>
                <th>P(Dℓ|E)</th>
                <th>RISK R(v)</th>
                <th>CLASSIFICATION</th>
              </tr>
            </thead>
            <tbody>
              {riskResult.assessments.map((a: any) => (
                <tr key={a.node_key} className="border-b border-[#d9d5cb]">
                  <td className="py-2 font-bold">{a.node_key}</td>
                  <td>{a.inputs.S}</td>
                  <td>{a.inputs.C_v}</td>
                  <td>{(a.inputs.X_l_v * 100).toFixed(1)}%</td>
                  <td>{(a.inputs.posterior_P_D_given_E * 100).toFixed(2)}%</td>
                  <td className="font-bold">{a.risk_score}</td>
                  <td className={badgeColor(a.classification)}>{a.classification}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="bg-white border border-[#d9d5cb] rounded-md p-4 overflow-x-auto">
        <h2 className="font-bold text-sm mb-2">UNIT-LEVEL PROVENANCE EXPOSURE</h2>
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[#d9d5cb] text-[#646b73]">
              <th className="py-2">NODE</th>
              <th>AFFECTED / TOTAL</th>
              <th>EXPOSURE %</th>
              <th>EXPLANATION</th>
            </tr>
          </thead>
          <tbody>
            {exposures.map((e) => (
              <tr key={e.node_key} className="border-b border-[#d9d5cb]">
                <td className="py-2 font-bold">{e.node_key}</td>
                <td>{e.affected_units} / {e.total_units}</td>
                <td>{e.exposure_pct}% ({e.exposure_tier})</td>
                <td>{e.provenance_explanation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// 8. Blockchain Verification Page
export const BlockchainVerificationPage: React.FC = () => {
  const [eventCode, setEventCode] = useState("EVT-2023-114-01");
  const [bundle, setBundle] = useState<any>(null);

  const checkOnChain = async () => {
    const res = await apiRequest<any>(`/verify-onchain/${eventCode}`);
    setBundle(res);
  };

  useEffect(() => {
    checkOnChain();
  }, []);

  return (
    <div className="space-y-4 font-mono text-xs">
      <div className="bg-white border border-[#d9d5cb] rounded-md p-4 flex items-center justify-between">
        <div>
          <h2 className="font-bold text-sm">ON-CHAIN COMMITMENT VERIFICATION</h2>
          <p className="text-[#646b73]">
            Cross-checks off-chain sealed snapshots & defect evidence hashes against ManufacturingRegistry.sol.
          </p>
        </div>
        <div className="flex gap-2">
          <input value={eventCode} onChange={(e) => setEventCode(e.target.value)} className="border border-[#d9d5cb] rounded px-2 py-1.5" />
          <button onClick={checkOnChain} className="px-4 py-1.5 bg-brand text-white rounded">
            Verify On-Chain
          </button>
        </div>
      </div>

      {bundle && (
        <div className="bg-white border border-[#d9d5cb] rounded-md p-4 space-y-3">
          <div>Event: <b>{bundle.event.event_code}</b> · Lot: <b>{bundle.event.lot_code}</b> · Status: <b>{bundle.event.status}</b></div>
          <div>Off-Chain Snapshot Root (v{bundle.snapshot_verification.version}): <b>{bundle.snapshot_verification.sealed_global_root}</b></div>
          <div>Snapshot Integrity: <b className={bundle.snapshot_verification.verified ? "text-ok" : "text-bad"}>{bundle.snapshot_verification.verified ? "VERIFIED ✓" : "FAILED"}</b></div>
          <div>Evidence Hash: <b>{bundle.event.evidence_root_hash}</b></div>
          <div>On-Chain Defect Anchored: <b>{bundle.defect_onchain?.exists ? `YES (Inspector: ${bundle.defect_onchain.inspector})` : "Not yet anchored on local node"}</b></div>
        </div>
      )}
    </div>
  );
};
