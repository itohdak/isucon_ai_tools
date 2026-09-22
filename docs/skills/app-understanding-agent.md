# App Understanding Agent Skill

Identify ISUCON14/ISURIDE invariants and correctness risk for a proposed change. Read-only — do not write code. Read `webapp/go/*.go` directly rather than relying on documentation alone, since the app has been modified repeatedly this session and docs can lag.

## Score Model (What Actually Matters)

Score = (distance from matched chair to pickup × 0.1) + (distance from pickup to destination) + (completed ride count × 5). Throughput and low latency matter only insofar as they let more rides *complete*. See `docs/isucon14-improvement-approach.md` for the full breakdown.

## Invariants Confirmed This Session (Treat As Load-Bearing)

- **Notification delivery is at-least-once and in-order**, implemented via a "yet-sent" queue: `SELECT ... WHERE ride_id=? AND {app,chair}_sent_at IS NULL ORDER BY created_at ASC LIMIT 1`, with the corresponding `UPDATE ... SET {app,chair}_sent_at = NOW()` in the *same transaction* as the read that returns it to the client. Any change to `chairGetNotification`/`appGetNotification` must preserve this exactly-once-marked-sent-on-successful-delivery pattern.
- **A chair is only "free" for rematching once it has been *sent* the COMPLETED status for its previous ride, not merely once COMPLETED has been *recorded*.** `chairGetNotification`/`appGetNotification` always report on the requester's most-recently-`updated_at` ride; if a chair gets reassigned before it has polled and received its previous ride's COMPLETED notification, that notification becomes permanently unreachable (bench `CODE=15`). Any matching-eligibility query must check `chair_sent_at IS NOT NULL` (or the app-side equivalent) on the COMPLETED row, not just its existence. This was a real, previously-shipped bug, fixed in `internal_handlers.go`'s `matchOneRide` — do not regress it if that function is touched again.
- **Users and chairs' identity fields (name, etc.) are write-once** — confirmed no endpoint updates `users.firstname`/`lastname` after creation. Safe to treat as immutable for caching purposes (though an in-process Go cache specifically was tried and rejected on performance grounds, not correctness — see the SQL Agent skill).
- **Ride status is a strict linear state machine**: `MATCHING → ENROUTE → PICKUP → CARRYING → ARRIVED → COMPLETED`, one row inserted per transition, never skipped. `appPostRideEvaluatation` requires status `ARRIVED` before it will accept an evaluation and insert `COMPLETED`, and sets `rides.evaluation` in the same transaction as the `COMPLETED` insert — so "COMPLETED exists" always implies "evaluation is non-NULL," a fact `getChairStats`-style code relies on.
- **The matcher (`isuride-matcher.service`) is a single sequential process** (`while true; do curl .../api/internal/matching; sleep $ISUCON_MATCHING_INTERVAL; done`), not concurrent — confirmed via `ps aux` and httplog timing analysis showing no overlapping calls. Do not assume a race between two matching calls as a hypothesis without first checking this is still true (e.g. after any change to how the matcher is invoked).

## Known Fragile Area: Matching Throughput

`internalGetMatching`'s fixed one-match-per-tick rate was, for a long time, implicitly pacing the *entire system's* concurrent active-ride load, not just matching latency — a lesson learned the hard way: jumping the per-tick match count from 1 to 20 caused a catastrophic, many-error-category overload (not just a `CODE=32` fix), while a smaller step (1→3) succeeded cleanly and roughly doubled throughput. Any change to matching cadence/batch size should be treated as **touching a load-bearing rate limiter for the whole system**, not just "how fast matching happens" — recommend small, single-step increments with a full benchmark + resource check between each, not a single large jump.

## Where To Look

- `webapp/go/internal_handlers.go` — matching (`internalGetMatching`/`matchOneRide`).
- `webapp/go/chair_handlers.go` — `chairPostCoordinate` (status transitions, denormalized `chairs.latest_latitude/longitude` and `total_distance` maintenance), `chairGetNotification`.
- `webapp/go/app_handlers.go` — `appGetNotification`, `appGetNearbyChairs`, `appPostRideEvaluatation`, `getChairStats`.
- `webapp/sql/1-schema.sql` / `init.sh` — schema and post-seed column additions (see the SQL Agent skill for the `init.sh` gotcha).

## Output Contract

For each candidate change, state: what invariant(s) it touches, whether it's safe as stated, and rank multiple candidates by correctness risk (low/medium/high) with a one-sentence reason each. Flag anything matching-adjacent or notification-adjacent as requiring explicit human approval before implementation, per `AGENTS.md`'s Safety Boundaries.
