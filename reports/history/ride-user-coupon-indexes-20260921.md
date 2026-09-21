# ride-user-coupon-indexes-20260921

- Recorded at: `2026-09-21T02:38:43.930243+00:00`
- Before score: `1972`
- After score: `2076`
- Delta: `104`
- Rollback status: `not_needed`
- Commit: `21411ab`
- Before report: `reports/baseline-isucon14-20260921-022931.json`
- After report: `reports/baseline-isucon14-20260921-023808.json`

## Hypothesis

The next iteration report pointed at rides by user ordered by created_at and coupon lookup by used_by. Add indexes for rides(user_id, created_at) and coupons(used_by).

## Changed Files

- `webapp/sql/1-schema.sql`

## Evidence

```json
{
  "after": {
    "coupons_used_by_explain": "uses coupons_used_by_idx",
    "error_counts": "map[]",
    "report": "reports/baseline-isucon14-20260921-023808.json",
    "rides_user_created_explain": "uses rides_user_id_created_at_idx; Backward index scan for DESC lookup"
  },
  "before": {
    "coupons_used_by_explain": "type=ALL; Extra=Using where",
    "error_counts": "map[26:1]",
    "report": "reports/baseline-isucon14-20260921-022931.json",
    "rides_user_created_explain": "type=ALL; Extra=Using where; Using filesort"
  },
  "discarded_noisy_report": "reports/baseline-isucon14-20260921-023623.json scored 1750, so the change was remeasured before adoption.",
  "indexes": [
    "rides_user_id_created_at_idx (user_id, created_at)",
    "coupons_used_by_idx (used_by)"
  ],
  "iteration_report": "reports/iterations/iteration-20260921-023816.md",
  "next_candidates": [
    "SELECT * FROM chairs INNER JOIN (SELECT id FROM chairs WHERE is_active = TRUE ORDER BY RAND() LIMIT 1)",
    "/api/chair/notification"
  ]
}
```
