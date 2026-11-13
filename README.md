# BlockTrace-X — Complete Platform (Stages 1, 2 & 3)

**Version-Bound Defect Propagation and Auditable Escrow Accounting in Multi-Parent Manufacturing Genealogies**

## Complete Windows PowerShell Quickstart

### 1. Start Local Hardhat Ethereum Network & Deploy Contracts
Open **PowerShell Terminal 1**:
```powershell
cd blockchain
npm install
npx hardhat compile
npx hardhat test
npx hardhat node
```
Open **PowerShell Terminal 2** (keep Terminal 1 running):
```powershell
cd blockchain
npx hardhat run scripts/deploy.ts --network localhost
```

### 2. Start Python 3.12 Flask Backend & Run Automated Tests
Open **PowerShell Terminal 3**:
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item ..\.env.example .env
python seed_demo.py
pytest -v
python run.py
```

### 3. Start React + Vite Frontend
Open **PowerShell Terminal 4**:
```powershell
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

## CSV-Backed Recall Trace
The operational supplier, lot, batch, dispatch, dashboard, trace, and recall views read the six source files in `datafile/`. Restart the Flask backend after editing those files so its in-process dataset cache is refreshed. Open **5. Trace & Recall** to trace dispatch `D-1847` upstream or inspect downstream exposure for `LOT-2023-114`.

The loader preserves ambiguous source data instead of silently inventing links:
- The 678 missing production batch IDs are filled from the QC batch ID at the same row only when unused. All 4,722 populated production/QC IDs align on their shared row.
- Complaint `C001` is the documented ground truth for resolving `LOT-2023-114` to supplier `S03` and adhesive. Other lot codes with conflicting supplier/material rows are marked unresolved.
- Numeric dates where both day and month are 12 or lower are interpreted day-first and counted in the data-quality summary.
- Dispatch batch references not present in the production data remain unresolved and are excluded from trace results. The current source files contain 1,039 such references.
- The current source graph links 20 batches and 7 dispatches to `LOT-2023-114`; this is the complete set of matching CSV rows, including rows beyond the four batches highlighted in the brief.
- **6. Operator Entry** provides English/Marathi manual batch entry. Offline drafts remain in browser local storage and sync when the connection returns; they are stored separately and do not modify the source CSVs.

Stage 2 snapshots and Stage 3 escrow/dispute records remain database-backed; the CSV-backed pages are read-only views of the supplied operational source files.

### 4. Configure MetaMask for Local Hardhat
1. Open MetaMask -> **Add Network** -> **Add a network manually**:
   - **Network Name:** `Hardhat Localhost`
   - **RPC URL:** `http://127.0.0.1:8545`
   - **Chain ID:** `31337`
   - **Currency Symbol:** `ETH`
2. Import Hardhat Account #1 (Manufacturer) or Account #3 (Buyer BAJAJ) using the private keys printed in Terminal 1 (`npx hardhat node`).

### 5. Docker Compose Deployment (PostgreSQL + Hardhat + Flask + React)
```powershell
docker compose up --build
```

## Demo Credentials
| Role | Email | Password |
| :--- | :--- | :--- |
| Admin | `admin@blocktracex.io` | `Admin@123` |
| Manufacturer | `mfg@blocktracex.io` | `Mfg@123` |
| Supplier (S03) | `s03@blocktracex.io` | `Sup@123` |
| QC Inspector 1 | `qc@blocktracex.io` | `Qc@123` |
| QC Inspector 2 | `qc2@blocktracex.io` | `Qc@123` |
| Buyer (BAJAJ) | `buyer@blocktracex.io` | `Buyer@123` |
| Arbitrator | `arb@blocktracex.io` | `Arb@123` |

## Known Scope & Architectural Boundaries
- On-chain commitments (`ManufacturingRegistry.sol`) prove cryptographic consistency with sealed snapshot representations and quorum-approved defect hashes; physical sensor accuracy depends on off-chain calibration and multi-inspector attestation.
- Off-chain SHA-256 hash-chained audit records (`HashChainedAuditEntry`) provide tamper-evident local auditability and link to EVM transaction hashes, distinct from the decentralized Hardhat/Ethereum smart contracts.
