import React, { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { apiRequest, getToken } from "./services/api";
import { useMetaMask } from "./hooks/useMetaMask";
import { AppLayout } from "./layouts/AppLayout";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { GenealogyPage } from "./pages/GenealogyPage";
import { OperatorPage } from "./pages/OperatorPage";
import {
  SuppliersPage,
  LotsPage,
  BatchesPage,
  DispatchesPage,
} from "./pages/EntitiesPages";
import {
  ExplorerPage,
  ContractsPage,
  WalletEscrowPage,
} from "./pages/BlockchainPages";
import {
  SnapshotManagementPage,
  DefectAttestationPage,
  PropagationLateEdgePage,
  ExposureBayesianPage,
  BlockchainVerificationPage,
} from "./pages/Stage2Pages";
import {
  PurchaseOrdersPage,
  EscrowManagementPage,
  ComplaintsDisputesSettlementPage,
  AuditLedgerPage,
  ReportsUsersSettingsPage,
} from "./pages/Stage3Pages";

export default function App() {
  const [user, setUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [bcStatus, setBcStatus] = useState<any>(null);
  const wallet = useMetaMask();

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    apiRequest<{ user: any }>("/auth/me")
      .then((res) => setUser(res.user))
      .catch(() => localStorage.removeItem("bt_token"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (user) {
      apiRequest<any>("/blockchain/status").then(setBcStatus).catch(() => {});
    }
  }, [user]);

  const handleLogout = () => {
    localStorage.removeItem("bt_token");
    setUser(null);
  };

  if (loading) return <div className="p-6 font-mono text-sm">Initializing BlockTrace-X...</div>;

  if (!user) {
    return <LoginPage onLogin={setUser} />;
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route
          element={
            <AppLayout
              user={user}
              onLogout={handleLogout}
              wallet={wallet}
              bcStatus={bcStatus}
            />
          }
        >
          <Route path="/" element={<DashboardPage bcStatus={bcStatus} wallet={wallet} />} />
          <Route path="/suppliers" element={<SuppliersPage />} />
          <Route path="/lots" element={<LotsPage />} />
          <Route path="/batches" element={<BatchesPage />} />
          <Route path="/genealogy" element={<GenealogyPage />} />
          <Route path="/operator" element={<OperatorPage />} />
          <Route path="/dispatches" element={<DispatchesPage />} />
          <Route path="/snapshots" element={<SnapshotManagementPage />} />
          <Route path="/defects" element={<DefectAttestationPage />} />
          <Route path="/propagation" element={<PropagationLateEdgePage />} />
          <Route path="/risk" element={<ExposureBayesianPage />} />
          <Route path="/verify" element={<BlockchainVerificationPage />} />
          <Route path="/pos" element={<PurchaseOrdersPage />} />
          <Route path="/escrow" element={<EscrowManagementPage />} />
          <Route path="/complaints" element={<ComplaintsDisputesSettlementPage mode="complaints" />} />
          <Route path="/disputes" element={<ComplaintsDisputesSettlementPage mode="disputes" />} />
          <Route path="/settlement" element={<ComplaintsDisputesSettlementPage mode="settlement" />} />
          <Route path="/explorer" element={<ExplorerPage />} />
          <Route path="/audit" element={<AuditLedgerPage />} />
          <Route path="/reports" element={<ReportsUsersSettingsPage section="reports" bcStatus={bcStatus} />} />
          <Route path="/users" element={<ReportsUsersSettingsPage section="users" bcStatus={bcStatus} />} />
          <Route path="/settings" element={<ReportsUsersSettingsPage section="settings" bcStatus={bcStatus} />} />
          <Route path="/contracts" element={<ContractsPage bcStatus={bcStatus} />} />
          <Route path="/wallet" element={<WalletEscrowPage bcStatus={bcStatus} wallet={wallet} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
