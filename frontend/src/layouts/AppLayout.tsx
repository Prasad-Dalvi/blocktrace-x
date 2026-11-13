import React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Wallet, ShieldCheck, LogOut } from "lucide-react";

interface Props {
  user: any;
  onLogout: () => void;
  wallet: ReturnType<typeof import("../hooks/useMetaMask").useMetaMask>;
  bcStatus: any;
}

const navGroups = [
  { to: "/", label: "1. Dashboard" },
  { to: "/suppliers", label: "2. Suppliers" },
  { to: "/lots", label: "3. Lots" },
  { to: "/batches", label: "4. Batches" },
  { to: "/genealogy", label: "5. Trace & Recall" },
  { to: "/operator", label: "6. Operator Entry" },
  { to: "/dispatches", label: "6. Dispatches" },
  { to: "/snapshots", label: "7. Snapshots" },
  { to: "/defects", label: "8-9. Defects & Attest" },
  { to: "/propagation", label: "10-11. Propagation & Gate" },
  { to: "/risk", label: "12-13. Exposure & Risk" },
  { to: "/pos", label: "14. POs" },
  { to: "/escrow", label: "15. Escrow" },
  { to: "/complaints", label: "16. Complaints" },
  { to: "/disputes", label: "17. Disputes" },
  { to: "/settlement", label: "18. Settlement" },
  { to: "/explorer", label: "19. Tx Explorer" },
  { to: "/audit", label: "20. Audit Ledger" },
  { to: "/reports", label: "21. Reports" },
  { to: "/users", label: "22. Users" },
  { to: "/settings", label: "23. Settings" },
  { to: "/contracts", label: "Contracts" },
  { to: "/wallet", label: "Wallet" },
];

export const AppLayout: React.FC<Props> = ({ user, onLogout, wallet, bcStatus }) => {
  return (
    <div className="min-h-screen flex flex-col bg-canvas text-ink">
      <header className="bg-white border-b border-[#d9d5cb] px-6 py-3 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <ShieldCheck className="w-6 h-6 text-brand" />
          <div>
            <h1 className="font-mono font-bold text-lg tracking-tight">BlockTrace-X</h1>
            <p className="text-xs text-[#646b73]">
              Version-Bound Defect Propagation & Auditable Escrow · Complete Platform
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs font-mono">
          <span
            className={`px-2.5 py-1 rounded border ${
              bcStatus?.network?.connected
                ? "bg-emerald-50 text-ok border-emerald-200"
                : "bg-red-50 text-bad border-red-200"
            }`}
          >
            {bcStatus?.network?.connected
              ? `Hardhat #${bcStatus.network.chain_id} · Block #${bcStatus.network.block_number}`
              : "Hardhat Offline"}
          </span>

          <button
            onClick={wallet.connectWallet}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-brand text-white hover:opacity-95"
          >
            <Wallet className="w-3.5 h-3.5" />
            {wallet.account
              ? `${wallet.account.slice(0, 6)}...${wallet.account.slice(-4)}`
              : "Connect MetaMask"}
          </button>

          <div className="border-l border-[#d9d5cb] pl-3 flex items-center gap-2">
            <span className="text-[#646b73]">{user?.role}</span>
            <button onClick={onLogout} className="p-1.5 rounded hover:bg-slate-100 text-[#646b73]" title="Sign Out">
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      <div className="flex-1 flex flex-col md:flex-row">
        <aside className="w-full md:w-56 bg-white border-r border-[#d9d5cb] p-3 flex md:flex-col gap-1 overflow-x-auto">
          {navGroups.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `px-2.5 py-1.5 rounded text-xs font-mono whitespace-nowrap transition-colors ${
                  isActive
                    ? "bg-brand text-white font-semibold"
                    : "text-[#646b73] hover:bg-slate-100 hover:text-ink"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </aside>

        <main className="flex-1 p-6 max-w-7xl w-full mx-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
