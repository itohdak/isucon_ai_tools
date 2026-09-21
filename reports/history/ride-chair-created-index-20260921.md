# ride-chair-created-index-20260921

- Recorded at: `2026-09-21T02:41:55.409833+00:00`
- Before score: `2076`
- After score: `2192`
- Delta: `116`
- Rollback status: `not_needed`
- Commit: `a3ca81e`
- Before report: `reports/baseline-isucon14-20260921-023808.json`
- After report: `reports/baseline-isucon14-20260921-024119.json`

## Hypothesis

Matching still queried rides with chair_id IS NULL ordered by created_at. Add rides(chair_id, created_at) to remove filesort for matching and chair ride history by created_at.

## Changed Files

- `webapp/sql/1-schema.sql`

## Evidence

```json
{
  "after": {
    "error_counts": "map[]",
    "report": "reports/baseline-isucon14-20260921-024119.json",
    "rides_chair_created_explain": "uses rides_chair_id_created_at_idx without filesort"
  },
  "before": {
    "report": "reports/baseline-isucon14-20260921-023808.json",
    "rides_chair_created_explain": "used rides_chair_id_updated_at_idx but still had Using filesort for chair_id IS NULL ORDER BY created_at"
  },
  "indexes": [
    "rides_chair_id_created_at_idx (chair_id, created_at)"
  ],
  "iteration_report": "reports/iterations/iteration-20260921-024128.md",
  "next_candidates": [
    "COMMIT time",
    "/api/chair/notification",
    "resource load"
  ]
}
```
