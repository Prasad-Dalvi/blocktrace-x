# BlockTrace-X — Stage 2 Specification & Verification

## 1. Canonical Graph Snapshot Encoding (`snapshot_service.py`, `merkle_service.py`)
- Nodes sorted lexicographically by `<TYPE>:<CODE>`.
- Outgoing adjacency lists sorted ascending by `child_key`.
- Node leaf: `SHA256("NODE|<g>|<node_key>|<out_degree>|<sorted_children_csv>")`.
- Relation leaf: `SHA256("REL|<g>|<parent_key>|<child_key>|<qty:.6f>")`.
- Global root: `SHA256("GLOBAL|<g>|<nodes_merkle_root>|<relations_merkle_root>")`.
- Chained commitment: `SHA256("CHAIN|<g>|<prev_global_root>|<global_root>")`.

## 2. Defect Event & Inspector Quorum (`defect_event_service.py`)
- Implements $e = (\text{id}, \text{lot}, g, c(g), \text{ev}, S)$ with configurable `quorum_required` and `challenge_window_seconds`.
- Anchors `registerDefectCommitment` on `ManufacturingRegistry.sol` once quorum approves.

## 3. Bounded Defect Propagation (`propagation_service.py`)
- Fixed-size cursor $\kappa = (\text{head}, \text{tail}, u, \delta, \lambda)$ persisted in PostgreSQL/SQLite.
- Enforces three independent segment budgets: $K$ (node visits), $M$ (relation scans), and $Z$ (classification touches).
- Rejects stale $\lambda$ or tampered state commitments.

## 4. Active Late-Edge Gate (`late_edge_service.py`)
- Evaluates $\Delta g = g_{\text{rec}} - g \le A_{\max}$ and $\text{delay} \le T_{\text{late}}$.
- Enqueues late downstream edges and reopens `COMPLETED` events to `REOPENED` so continuation segments include newly discovered descendants.

## 5. Unit-Level Exposure & Bayesian Risk (`exposure_service.py`, `bayesian_risk_service.py`)
- $X_\ell(v) = \text{affected physical units} / \text{total physical units}$ deduplicated across multi-parent DAG paths.
- $\text{Odds}(D \mid E) = \text{Odds}(D) \prod_j LR_j$, $P(D \mid E) = \frac{\text{Odds}(D \mid E)}{1 + \text{Odds}(D \mid E)}$, and $R(v) = S \cdot C(v) \cdot X_\ell(v) \cdot P(D_\ell \mid E)$.
