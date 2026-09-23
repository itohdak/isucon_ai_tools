# ride-statuses-indexes-20260921

- Recorded at: `2026-09-21T02:13:01.248635+00:00`
- Before score: `673`
- After score: `1297`
- Delta: `624`
- Rollback status: `not_needed`
- Commit: `b1bfb60`
- Before report: `reports/baseline-isucon14-20260921-014901.json`
- After report: `reports/baseline-isucon14-20260921-015831.json`

## Hypothesis

ride_statuses notification/latest-status lookups were doing full scans and filesorts because the table only had PRIMARY KEY (id). Add composite indexes for ride_id plus created_at and sent-at columns.

## Changed Files

- `webapp/sql/1-schema.sql`

## Evidence

```json
{
  "after": {
    "error_counts": "map[]",
    "explain": "uses ride_statuses_ride_id_created_at_idx; Backward index scan for latest-status lookup",
    "report": "reports/baseline-isucon14-20260921-015831.json"
  },
  "before": {
    "error_counts": "map[26:1]",
    "explain": "type=ALL; Extra=Using where; Using filesort",
    "report": "reports/baseline-isucon14-20260921-014901.json"
  },
  "indexes": [
    "ride_statuses_ride_id_created_at_idx (ride_id, created_at)",
    "ride_statuses_ride_id_app_sent_at_created_at_idx (ride_id, app_sent_at, created_at)",
    "ride_statuses_ride_id_chair_sent_at_created_at_idx (ride_id, chair_sent_at, created_at)"
  ]
}
```
