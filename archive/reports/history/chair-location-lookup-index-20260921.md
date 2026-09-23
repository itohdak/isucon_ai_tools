# chair-location-lookup-index-20260921

- Recorded at: `2026-09-21T02:45:46.335608+00:00`
- Before score: `2192`
- After score: `2637`
- Delta: `445`
- Rollback status: `not_needed`
- Commit: `b8a01f3`
- Before report: `reports/baseline-isucon14-20260921-024119.json`
- After report: `reports/baseline-isucon14-20260921-024509.json`

## Hypothesis

The app repeatedly fetches the latest location for a chair. Add chair_locations(chair_id, created_at) to remove full scan/filesort for latest-location lookup.

## Changed Files

- `webapp/sql/1-schema.sql`

## Evidence

```json
{
  "after": {
    "chair_locations_explain": "uses chair_locations_chair_id_created_at_idx; Backward index scan",
    "error_counts": "map[]",
    "report": "reports/baseline-isucon14-20260921-024509.json"
  },
  "before": {
    "chair_locations_explain": "type=ALL; Extra=Using where; Using filesort",
    "report": "reports/baseline-isucon14-20260921-024119.json"
  },
  "indexes": [
    "chair_locations_chair_id_created_at_idx (chair_id, created_at)"
  ],
  "iteration_report": "reports/iterations/iteration-20260921-024519.md",
  "next_candidates": [
    "SELECT * FROM ride_statuses WHERE ride_id = ? ORDER BY created_at",
    "/api/chair/notification"
  ]
}
```
