import React, { useState } from "react";
import { apiRequest } from "../services/api";

export const LoginPage: React.FC<{ onLogin: (user: any) => void }> = ({ onLogin }) => {
  const [email, setEmail] = useState("mfg@blocktracex.io");
  const [password, setPassword] = useState("Mfg@123");
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const res = await apiRequest<{ access_token: string; user: any }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      localStorage.setItem("bt_token", res.access_token);
      onLogin(res.user);
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-canvas p-4">
      <div className="bg-white border border-[#d9d5cb] rounded-md p-6 w-full max-w-md shadow-sm">
        <h1 className="font-mono text-xl font-bold mb-1">BlockTrace-X</h1>
        <p className="text-xs text-[#646b73] mb-5">
          Sign in to access the Multi-Parent Manufacturing & Escrow Ledger
        </p>

        {error && (
          <div className="mb-4 p-2.5 bg-red-50 border border-red-200 text-bad text-xs rounded">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-mono text-[#646b73] mb-1">EMAIL</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-[#d9d5cb] rounded px-3 py-2 text-sm"
              required
            />
          </div>
          <div>
            <label className="block text-xs font-mono text-[#646b73] mb-1">PASSWORD</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-[#d9d5cb] rounded px-3 py-2 text-sm"
              required
            />
          </div>
          <button
            type="submit"
            className="w-full bg-brand text-white font-mono text-sm py-2 rounded hover:opacity-95"
          >
            Sign In
          </button>
        </form>

        <div className="mt-5 pt-4 border-t border-[#d9d5cb] text-xs text-[#646b73] space-y-1 font-mono">
          <div className="font-semibold text-ink">Demo Credentials:</div>
          <div>Manufacturer: mfg@blocktracex.io / Mfg@123</div>
          <div>QC Inspector: qc@blocktracex.io / Qc@123</div>
          <div>Supplier S03: s03@blocktracex.io / Sup@123</div>
          <div>Admin: admin@blocktracex.io / Admin@123</div>
        </div>
      </div>
    </div>
  );
};
