# chair-ride-lookup-indexes-20260921

- Recorded at: `2026-09-21T02:30:24.213892+00:00`
- Before score: `1297`
- After score: `1972`
- Delta: `675`
- Rollback status: `not_needed`
- Commit: `85d665d`
- Before report: `reports/baseline-isucon14-20260921-015831.json`
- After report: `reports/baseline-isucon14-20260921-022931.json`

## Hypothesis

After the ride_statuses index improvement, slow logs pointed at chair authentication and latest rides by chair. Add indexes for chairs.access_token and rides(chair_id, updated_at).

## Changed Files

- `webapp/sql/1-schema.sql`

## Evidence

```json
{
  "after": {
    "chairs_access_token_explain": "unique index, const lookup",
    "error_counts": "map[26:1]",
    "report": "reports/baseline-isucon14-20260921-022931.json",
    "rides_chair_updated_explain": "uses rides_chair_id_updated_at_idx; Backward index scan"
  },
  "before": {
    "chairs_access_token_explain": "type=ALL; Extra=Using where",
    "error_counts": "map[]",
    "report": "reports/baseline-isucon14-20260921-015831.json",
    "rides_chair_updated_explain": "type=ALL; Extra=Using where; Using filesort"
  },
  "indexes": [
    "chairs_access_token_idx (access_token)",
    "rides_chair_id_updated_at_idx (chair_id, updated_at)"
  ],
  "iteration_report": "reports/iterations/iteration-20260921-022940.md",
  "next_candidates": [
    "Investigate CODE=26 recurrence",
    "SELECT * FROM rides WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
    "/api/chair/notification"
  ]
}
```
