# Scaling Traceability to Ten Production Lines

## Current Baseline
The local demo reads six CSVs, normalizes them in memory, and serves the source records through the trace and recall APIs. The 5,400 production rows are adequate for a local demonstration, but a process-local cache and CSV files are not a multi-line production store. Operator entries are saved server-side; offline drafts are held in the browser until connectivity returns.

## Target Design
1. Keep the CSV import as a versioned ingestion boundary. Validate headers, row counts, date parsing, identifiers, and cross-file references before publishing a dataset version.
2. Store canonical suppliers, receipts, production runs, QC inspections, dispatches, and complaints in PostgreSQL. Retain immutable source-row identifiers and original values for audit and correction.
3. Use stable IDs and unique constraints for lots, batches, and dispatches. Put uncertain matches in a review queue with candidate evidence; never silently promote an ambiguous match to a verified genealogy edge.
4. Keep shop-floor writes append-only with an idempotency key. A local outbox syncs when online; the server acknowledges each record and returns validation errors for operator correction.
5. Index `lot_number`, `input_lot_ref`, `batch_id`, and `order_id`; materialize the lot-to-batch-to-dispatch traversal for recall queries and refresh it after validated imports.
6. Partition ingestion by line and shift, while preserving a global lot/batch graph. Enforce role-based access and audit who entered, corrected, or approved each record.
7. Measure the 30-second trace objective with realistic concurrent reads, imports, and recall fan-out. Add pagination and cached summaries; do not load the complete graph into the browser.

## Rollout Gates
Begin with one line and compare imported totals against shift registers. Require a reviewed match rate and documented exception count before enabling automatic recall decisions. Expand to ten lines only after offline synchronization, conflict review, backup/restore, access control, and the 30-second query target pass operational tests.