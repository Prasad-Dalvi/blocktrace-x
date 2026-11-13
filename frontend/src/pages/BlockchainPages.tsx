import React, { useEffect, useState } from "react";
import { apiRequest } from "../services/api";

export const ExplorerPage: React.FC = () => {
  const [txs, setTxs] = useState<any[]>([]);
  useEffect(() => {
    apiRequest<any[]>("/blockchain/transactions").then(setTxs);
  }, []);
  return (
    <div className="bg-white border border-[#d9d5cb] rounded-md p-4">
      <h2 className="font-mono font-bold text-sm mb-3">ON-CHAIN TRANSACTION LEDGER</h2>
      <table className="w-full text-xs font-mono text-left border-collapse">
        <thead>
          <tr className="border-b border-[#d9d5cb] text-[#646b73]">
            <th className="py-2">TX HASH</th>
            <th>CONTRACT</th>
            <th>FUNCTION</th>
            <th>REFERENCE</th>
            <th>STATUS</th>
          </tr>
        </thead>
        <tbody>
          {txs.map((t) => (
            <tr key={t.id} className="border-b border-[#d9d5cb]">
              <td className="py-2">{t.tx_hash}</td>
              <td>{t.contract_name}</td>
              <td>{t.function_name}</td>
              <td>{t.reference_id}</td>
              <td className={t.status === "CONFIRMED" ? "text-ok font-bold" : "text-warn"}>
                {t.status}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export const ContractsPage: React.FC<{ bcStatus: any }> = ({ bcStatus }) => {
  const contracts = bcStatus?.contracts || {};
  return (
    <div className="space-y-4">
      {Object.entries(contracts).map(([name, info]: [string, any]) => (
        <div key={name} className="bg-white border border-[#d9d5cb] rounded-md p-4 font-mono text-xs">
          <div className="font-bold text-sm text-brand">{name}</div>
          <div className="mt-1">Deployed Address: <b>{info.address}</b></div>
          <div className="text-[#646b73] mt-1">
            ABI Functions: {info.abi.filter((x: any) => x.type === "function").map((x: any) => x.name).join(", ")}
          </div>
        </div>
      ))}
    </div>
  );
};

export const WalletEscrowPage: React.FC<{ bcStatus: any; wallet: any }> = ({ bcStatus, wallet }) => {
  const [escrowData, setEscrowData] = useState<any>(null);
  const [ethInput, setEthInput] = useState("0.25");
  const [msg, setMsg] = useState("");

  const refresh = () => {
    apiRequest<any>("/blockchain/escrow/PO-1001").then(setEscrowData).catch(() => {});
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleDeposit = async () => {
    try {
      const c = bcStatus?.contracts?.SupplyChainEscrow;
      if (!c || !escrowData?.onchain_escrow?.escrow_id) {
        setMsg("Contract not deployed or Hardhat offline.");
        return;
      }
      const hash = await wallet.depositEscrowEth(
        c.address,
        c.abi,
        escrowData.onchain_escrow.escrow_id,
        ethInput
      );
      setMsg(`Deposited ${ethInput} Test ETH into PO-1001 Escrow! Tx: ${hash}`);
      refresh();
    } catch (err: any) {
      setMsg(`Deposit failed: ${err.message}`);
    }
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 font-mono text-xs">
      <div className="bg-white border border-[#d9d5cb] rounded-md p-4 space-y-3">
        <h2 className="font-bold text-sm">METAMASK WALLET CONNECTION</h2>
        <div>Connected Account: <b>{wallet.account || "Not Connected"}</b></div>
        <div>Chain ID: <b>{wallet.chainId || "N/A (Expected 31337)"}</b></div>
        {wallet.error && <div className="text-bad">{wallet.error}</div>}
        <button
          onClick={wallet.connectWallet}
          className="px-4 py-2 bg-brand text-white rounded"
        >
          Connect MetaMask Wallet
        </button>
      </div>

      <div className="bg-white border border-[#d9d5cb] rounded-md p-4 space-y-3">
        <h2 className="font-bold text-sm">PO-1001 ESCROW TOP-UP (TESTNET ETH)</h2>
        <p className="text-[#646b73]">
          Business PO Value: ₹2,00,000 · On-chain Testnet Deposit (10% Fr reserve, 90% Fa available)
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            value={ethInput}
            onChange={(e) => setEthInput(e.target.value)}
            className="border border-[#d9d5cb] rounded px-3 py-1.5 w-32"
          />
          <button
            onClick={handleDeposit}
            className="px-4 py-1.5 bg-ok text-white rounded"
          >
            Deposit Test ETH
          </button>
        </div>
        {msg && <div className="text-brand break-all">{msg}</div>}
      </div>
    </div>
  );
};
