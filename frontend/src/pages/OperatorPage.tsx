import React, { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { apiRequest } from "../services/api";

type BatchDraft = {
  batch_code: string;
  production_date: string;
  shift: string;
  machine_id: string;
  operator_id: string;
  input_lot_ref: string;
  units_produced: number;
  cycle_time_min: number;
};

const OUTBOX_KEY = "blocktrace_operator_outbox";
const LOTS_CACHE_KEY = "blocktrace_operator_lots";

const labels = {
  en: {
    title: "Shop-floor batch entry",
    subtitle: "Record a production run; drafts stay on this device while offline.",
    batch: "Batch ID",
    date: "Production date",
    shift: "Shift",
    machine: "Machine ID",
    operator: "Operator ID",
    lot: "Input lot",
    units: "Units produced",
    cycle: "Cycle time (minutes)",
    save: "Save batch",
    sync: "Sync pending entries",
    online: "Online",
    offline: "Offline",
    pending: "Pending on this device",
    recent: "Recently synced batches",
    noRecent: "No operator batches synced yet.",
    savedOffline: "Saved on this device. It will sync when a connection is available.",
    savedOnline: "Batch saved to the server.",
    synced: "Pending entries synced.",
    syncError: "Could not sync yet. The entry remains saved on this device.",
  },
  mr: {
    title: "उत्पादन बॅच नोंद",
    subtitle: "उत्पादनाची नोंद करा. इंटरनेट नसताना नोंद या उपकरणावर जतन होईल.",
    batch: "बॅच आयडी",
    date: "उत्पादन तारीख",
    shift: "शिफ्ट",
    machine: "मशीन आयडी",
    operator: "ऑपरेटर आयडी",
    lot: "कच्च्या मालाचा लॉट",
    units: "उत्पादित नग",
    cycle: "चक्र वेळ (मिनिटे)",
    save: "बॅच जतन करा",
    sync: "प्रलंबित नोंदी समक्रमित करा",
    online: "ऑनलाइन",
    offline: "ऑफलाइन",
    pending: "या उपकरणावरील प्रलंबित नोंदी",
    recent: "अलीकडे समक्रमित बॅच",
    noRecent: "अद्याप कोणतीही बॅच समक्रमित नाही.",
    savedOffline: "या उपकरणावर जतन केले. इंटरनेट उपलब्ध झाल्यावर समक्रमित होईल.",
    savedOnline: "बॅच सर्व्हरवर जतन केली.",
    synced: "प्रलंबित नोंदी समक्रमित झाल्या.",
    syncError: "समक्रमण झाले नाही. नोंद या उपकरणावर जतन आहे.",
  },
};

function readLocal<T>(key: string, fallback: T): T {
  try {
    const stored = localStorage.getItem(key);
    return stored ? (JSON.parse(stored) as T) : fallback;
  } catch {
    return fallback;
  }
}

function newBatchCode(): string {
  const suffix = Math.random().toString(36).slice(2, 6).toUpperCase();
  return `BATCH-MANUAL-${Date.now()}-${suffix}`;
}

export const OperatorPage: React.FC = () => {
  const [language, setLanguage] = useState<"en" | "mr">("en");
  const [online, setOnline] = useState(navigator.onLine);
  const [lots, setLots] = useState<any[]>(() => readLocal(LOTS_CACHE_KEY, []));
  const [pending, setPending] = useState<BatchDraft[]>(() => readLocal(OUTBOX_KEY, []));
  const [recent, setRecent] = useState<any[]>([]);
  const [message, setMessage] = useState("");
  const [form, setForm] = useState<BatchDraft>({
    batch_code: newBatchCode(),
    production_date: new Date().toISOString().slice(0, 10),
    shift: "A",
    machine_id: "MC-01",
    operator_id: "",
    input_lot_ref: "LOT-2023-114",
    units_produced: 1,
    cycle_time_min: 1,
  });
  const text = labels[language];

  const loadRecent = async () => {
    try {
      setRecent(await apiRequest<any[]>("/manufacturing/operator-batches"));
    } catch {
      setRecent([]);
    }
  };

  const syncPending = async () => {
    if (!navigator.onLine) return;
    const queued = readLocal<BatchDraft[]>(OUTBOX_KEY, []);
    const remaining: BatchDraft[] = [];
    for (const draft of queued) {
      try {
        await apiRequest("/manufacturing/operator-batches", {
          method: "POST",
          body: JSON.stringify(draft),
        });
      } catch {
        remaining.push(draft);
      }
    }
    localStorage.setItem(OUTBOX_KEY, JSON.stringify(remaining));
    setPending(remaining);
    if (remaining.length === 0 && queued.length > 0) setMessage(text.synced);
    await loadRecent();
  };

  useEffect(() => {
    const updateConnection = () => {
      setOnline(navigator.onLine);
      if (navigator.onLine) void syncPending();
    };
    window.addEventListener("online", updateConnection);
    window.addEventListener("offline", updateConnection);
    void loadRecent();
    apiRequest<any[]>("/manufacturing/lots")
      .then((sourceLots) => {
        setLots(sourceLots);
        localStorage.setItem(LOTS_CACHE_KEY, JSON.stringify(sourceLots));
      })
      .catch(() => {});
    return () => {
      window.removeEventListener("online", updateConnection);
      window.removeEventListener("offline", updateConnection);
    };
  }, []);

  const updateForm = (field: keyof BatchDraft, value: string | number) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setMessage("");
    const draft = { ...form, batch_code: form.batch_code.trim() || newBatchCode() };
    if (!navigator.onLine) {
      const next = [...readLocal<BatchDraft[]>(OUTBOX_KEY, []), draft];
      localStorage.setItem(OUTBOX_KEY, JSON.stringify(next));
      setPending(next);
      setMessage(text.savedOffline);
    } else {
      try {
        await apiRequest("/manufacturing/operator-batches", {
          method: "POST",
          body: JSON.stringify(draft),
        });
        setMessage(text.savedOnline);
        await loadRecent();
      } catch (error: any) {
        setMessage(error.message);
        return;
      }
    }
    setForm((current) => ({ ...current, batch_code: newBatchCode(), operator_id: "" }));
  };

  return (
    <div className="space-y-6 font-mono text-xs">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-[#d9d5cb] pb-4">
        <div>
          <h2 className="font-bold text-base">{text.title}</h2>
          <p className="mt-1 text-[#646b73]">{text.subtitle}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className={online ? "text-ok" : "text-bad"}>{online ? text.online : text.offline}</span>
          <div className="inline-flex border border-[#d9d5cb]" role="group" aria-label="Language">
            <button type="button" onClick={() => setLanguage("en")} aria-pressed={language === "en"} className={`px-3 py-1.5 ${language === "en" ? "bg-brand text-white" : "bg-white"}`}>EN</button>
            <button type="button" onClick={() => setLanguage("mr")} aria-pressed={language === "mr"} className={`px-3 py-1.5 ${language === "mr" ? "bg-brand text-white" : "bg-white"}`}>मराठी</button>
          </div>
        </div>
      </header>

      <form onSubmit={submit} className="grid max-w-4xl grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <label className="grid gap-1"><span>{text.batch}</span><input required value={form.batch_code} onChange={(event) => updateForm("batch_code", event.target.value)} className="border border-[#d9d5cb] px-2 py-2" /></label>
        <label className="grid gap-1"><span>{text.date}</span><input required type="date" value={form.production_date} onChange={(event) => updateForm("production_date", event.target.value)} className="border border-[#d9d5cb] px-2 py-2" /></label>
        <label className="grid gap-1"><span>{text.shift}</span><select value={form.shift} onChange={(event) => updateForm("shift", event.target.value)} className="border border-[#d9d5cb] px-2 py-2"><option>A</option><option>B</option><option>C</option></select></label>
        <label className="grid gap-1"><span>{text.machine}</span><input required value={form.machine_id} onChange={(event) => updateForm("machine_id", event.target.value)} className="border border-[#d9d5cb] px-2 py-2" /></label>
        <label className="grid gap-1"><span>{text.operator}</span><input required value={form.operator_id} onChange={(event) => updateForm("operator_id", event.target.value)} className="border border-[#d9d5cb] px-2 py-2" /></label>
        <label className="grid gap-1"><span>{text.lot}</span><select required value={form.input_lot_ref} onChange={(event) => updateForm("input_lot_ref", event.target.value)} className="border border-[#d9d5cb] px-2 py-2">{lots.filter((lot) => lot.resolution_status !== "unresolved_conflict").map((lot) => <option key={lot.lot_code} value={lot.lot_code}>{lot.lot_code} · {lot.resolution_status}</option>)}</select></label>
        <label className="grid gap-1"><span>{text.units}</span><input required type="number" min="1" step="1" value={form.units_produced} onChange={(event) => updateForm("units_produced", Number(event.target.value))} className="border border-[#d9d5cb] px-2 py-2" /></label>
        <label className="grid gap-1"><span>{text.cycle}</span><input required type="number" min="0.1" step="0.1" value={form.cycle_time_min} onChange={(event) => updateForm("cycle_time_min", Number(event.target.value))} className="border border-[#d9d5cb] px-2 py-2" /></label>
        <div className="flex items-end"><button type="submit" className="bg-brand px-4 py-2 text-white">{text.save}</button></div>
      </form>

      {message && <p role="status" className="border-t border-[#d9d5cb] pt-3">{message}</p>}

      <section className="space-y-3 border-t border-[#d9d5cb] pt-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="font-bold">{text.pending}: {pending.length}</h3>
          <button type="button" onClick={() => void syncPending()} disabled={!online || pending.length === 0} title={text.sync} aria-label={text.sync} className="p-2 text-brand disabled:opacity-40"><RefreshCw className="h-4 w-4" /></button>
        </div>
        {pending.map((draft) => <p key={draft.batch_code}>{draft.batch_code} · {draft.input_lot_ref} · {draft.units_produced} units</p>)}
      </section>

      <section className="space-y-3 border-t border-[#d9d5cb] pt-4">
        <h3 className="font-bold">{text.recent}</h3>
        {recent.length === 0 && <p className="text-[#646b73]">{text.noRecent}</p>}
        {recent.slice(0, 10).map((entry) => (
          <div key={entry.batch_code} className="flex flex-wrap gap-x-5 gap-y-1 border-b border-[#d9d5cb] py-2">
            <b>{entry.batch_code}</b><span>{entry.production_date} · {entry.shift}</span>
            <span>{entry.machine_id} · {entry.operator_id}</span><span>{entry.input_lot_ref}</span>
            <span>{entry.units_produced} units</span>
          </div>
        ))}
      </section>
    </div>
  );
};