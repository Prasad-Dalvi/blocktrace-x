import { useState, useCallback } from "react";
import { BrowserProvider, Contract, parseEther } from "ethers";
import { apiRequest } from "../services/api";

declare global {
  interface Window {
    ethereum?: any;
  }
}

export function useMetaMask() {
  const [account, setAccount] = useState<string | null>(null);
  const [chainId, setChainId] = useState<string | null>(null);
  const [latestTx, setLatestTx] = useState<{ hash: string; status: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const connectWallet = useCallback(async () => {
    setError(null);
    if (!window.ethereum) {
      setError("MetaMask not detected. Install MetaMask and switch to Hardhat Localhost (Chain ID 31337).");
      return;
    }
    try {
      const provider = new BrowserProvider(window.ethereum);
      const accounts = await provider.send("eth_requestAccounts", []);
      const network = await provider.getNetwork();
      setAccount(accounts[0]);
      setChainId(network.chainId.toString());
    } catch (err: any) {
      setError(err.message || "Failed to connect MetaMask");
    }
  }, []);

  const submitSnapshotMetaMask = useCallback(
    async (
      contractAddress: string,
      abi: any,
      version: number,
      rootHash: string,
      metadataHash: string
    ) => {
      if (!window.ethereum) throw new Error("MetaMask required");
      const provider = new BrowserProvider(window.ethereum);
      const signer = await provider.getSigner();
      const contract = new Contract(contractAddress, abi, signer);

      const tx = await contract.registerSnapshot(version, rootHash, metadataHash);
      setLatestTx({ hash: tx.hash, status: "PENDING" });

      await apiRequest("/blockchain/transactions/record", {
        method: "POST",
        body: JSON.stringify({
          tx_hash: tx.hash,
          contract_name: "ManufacturingRegistry",
          function_name: "registerSnapshot",
          sender_address: await signer.getAddress(),
          reference_id: `SNAPSHOT_V${version}`,
        }),
      });

      const receipt = await tx.wait();
      const finalStatus = receipt?.status === 1 ? "CONFIRMED" : "FAILED";
      setLatestTx({ hash: tx.hash, status: finalStatus });

      await apiRequest("/blockchain/transactions/record", {
        method: "POST",
        body: JSON.stringify({
          tx_hash: tx.hash,
          contract_name: "ManufacturingRegistry",
          function_name: "registerSnapshot",
          sender_address: await signer.getAddress(),
          reference_id: `SNAPSHOT_V${version}`,
        }),
      });

      return tx.hash;
    },
    []
  );

  const depositEscrowEth = useCallback(
    async (contractAddress: string, abi: any, escrowIdBytes32: string, ethAmount: string) => {
      if (!window.ethereum) throw new Error("MetaMask required");
      const provider = new BrowserProvider(window.ethereum);
      const signer = await provider.getSigner();
      const contract = new Contract(contractAddress, abi, signer);

      const tx = await contract.deposit(escrowIdBytes32, 1000, {
        value: parseEther(ethAmount),
      });
      setLatestTx({ hash: tx.hash, status: "PENDING" });
      await tx.wait();
      setLatestTx({ hash: tx.hash, status: "CONFIRMED" });

      await apiRequest("/blockchain/transactions/record", {
        method: "POST",
        body: JSON.stringify({
          tx_hash: tx.hash,
          contract_name: "SupplyChainEscrow",
          function_name: "deposit",
          sender_address: await signer.getAddress(),
          reference_id: "PO-1001",
        }),
      });
      return tx.hash;
    },
    []
  );

  return {
    account,
    chainId,
    latestTx,
    error,
    connectWallet,
    submitSnapshotMetaMask,
    depositEscrowEth,
  };
}
