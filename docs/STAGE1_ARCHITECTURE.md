# Stage 1 Architecture & Invariant Verification

## 1. Six-Bucket Escrow Conservation Invariant
Every purchase order escrow $e$ tracks six non-negative `uint256` wei buckets:
- $F_a$: Available funds
- $F_r$: Warranty reserve
- $F_d$: Disputed (frozen) funds
- $P_s$: Cumulative supplier payments
- $P_b$: Cumulative buyer refunds
- $P_c$: Third-party compensation

At every block state transition, `SupplyChainEscrow.sol` enforces:
$$D_{\text{cum}} = P_s + P_b + P_c + F_d + F_r + F_a$$

## 2. Independent Replay-Protected Settlement
`SupplyChainEscrow.settleClaim(poId, claimId)` queries `IClaimAuthorization(claimRegistry).isSettlementAuthorized(claimId, poId)` directly on-chain and records `settledClaims[claimId] = true` before executing checks-effects-interactions ETH transfers. Neither off-chain APIs nor untrusted callers can trigger duplicate settlements.
