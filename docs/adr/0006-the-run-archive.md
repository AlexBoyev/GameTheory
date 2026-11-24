# ADR 0006 - The run archive, or: persistence that was never plugged in

- **Status:** accepted
- **Date:** 2026-11-23
- **Context:** Closing the gap between SPEC sections 10/11 and what the code did

## Context

SPEC section 10 ends "Stored in SQLite, streamed via WS", and section 11 lists
four tables: runs, metrics, snapshots and a capped event log. Only the WS half
and the snapshots were ever true.

Everything else was *built and connected to nothing*. `Repository` had
`create_run`, `add_metrics`, `metrics_since`, `add_events` and
`recent_events`; the tables were created on every startup; `EventRecord` was
never once constructed anywhere in the codebase; `MetricsService.__init__`
accepted a `Repository`, stored it as `self._repository`, and never called a
method on it. Both routers carried a comment promising the SQLite path would
"arrive in Phase 4". It did not arrive in Phase 4, 5, 6 or 7.

The visible consequence: charts and the event feed lived in a ring buffer
(2,000 samples, 500 events) and died with the process. A long run silently
lost its own beginning, and nothing survived a restart.

This is the fourth instance in this project of the same failure - declared,
typed, tested in isolation, called by nobody. See `docs/REVIEW.md` for the
other three and for the test that now sweeps for them.

## Decisions

### 1. One collaborator owns the durable record of a run

`RunArchive` holds three things that genuinely belong together: which run we
are in, writing to it, and reading it back. Splitting them would have meant
passing a run id around between a writer and a reader, and the run id is
exactly the thing that changes underneath both when somebody resets the world.

A run begins wherever a world is born - startup, reset, restore - not once at
construction. Two worlds are two runs; averaging their metrics together would
be meaningless.

### 2. Writes happen on a third thread, and may be dropped

The engine thread must never touch SQL, and neither should the event loop: a
metrics sample lands every few seconds, but a batch of events lands twenty
times a second, and an `fsync` on the broadcast thread is a stutter in
everyone's frame rate. So callers only ever put a job on a bounded queue, and
one daemon thread does the I/O.

When that queue is full, jobs are dropped rather than blocking the producer.
This is the right way round: the simulation is the product and the archive is
a record of it, so a database having a bad day must not become back pressure
on the thing being recorded. Failed writes are logged and swallowed for the
same reason - a lost chart is not a lost simulation.

The one exception is `flush`, which blocks to enqueue its barrier: it runs
only in tests and at shutdown, where a dropped barrier would report failure
for a writer that was merely busy.

### 3. The writer coalesces neighbouring samples into one transaction

SQLite pays an `fsync` per transaction, not per row. Writing a backlog one row
at a time is dramatically slower than writing the same rows together, which
matters exactly when the writer is already behind. The consumer takes up to 64
jobs at a time and batches the samples among them, preserving order: samples
accumulate only until a job of another kind arrives, so a `begin` or an `end`
never overtakes the rows it bounds.

### 4. Memory and the archive are stitched, and the read is bounded

`MetricsService.series` returns the in-memory window and asks the archive only
for what the window no longer holds (`before_tick`), so the two concatenate
instead of overlapping. `GET /events` does the same, topping up from SQLite
only when the ring buffer cannot fill the request, and de-duplicating on the
boundary. The caller sees one series and one feed; where each row came from is
not its problem.

The archived half is capped at 2,000 rows, ordered and limited by SQL rather
than fetched whole and filtered in Python. Without that cap the stitch was a
slow leak: the charts panel re-requests the entire series every three
seconds, so each poll of a long run re-read and re-parsed the whole metrics
table, growing without limit behind a chart a few hundred pixels wide.

### 5. The event table is capped by pruning in jumps

SPEC says capped. Deleting a row per insert would mean a `DELETE` on every
batch at MAX speed, so the archive counts rows every 2,000 writes and, when
the table passes 20,000, cuts it back to 15,000 in a single statement. Pruning
is therefore occasional rather than constant, and `prune_events` rejects a
`keep` at or above its `cap` - which would never settle.

### 6. A run's progress is stamped as it goes, not when it ends

A soak run showed every row in `runs` reading `last_tick = 0` with
`ended_at` NULL - including runs that had plainly finished. The driver stops
the backend with `taskkill /F /T` on Windows, because uvicorn and vite both
spawn children, so the FastAPI lifespan shutdown never runs and neither does
`RunArchive.end`. A `last_tick` written only on a clean exit reads 0 for
every run anybody actually watched.

So `last_tick` rides along with each metrics write, and never moves
backwards. `ended_at` keeps its narrower meaning: the process stopped
cleanly. NULL means killed, or still going.

## Consequences

- Charts keep the whole run. The ring buffer is now a cache in front of the
  archive rather than the only copy.
- A restart leaves a readable record: runs with their seed, config and last
  tick, their metrics, and their recent events.
- Three more threads' worth of care: the archive is the only place that writes
  SQL outside `SnapshotService`, and it does so on exactly one thread.
- `tests/api/test_persistence.py` asserts against the *running app* that rows
  actually land, because that is the only kind of test that would have caught
  the original bug. The unit tests for `RunArchive` would all have passed on
  the day nothing called it.
- Soaked for 27,000 ticks at MAX speed before being believed. It kept up:
  roughly 1,800 events a minute, not one dropped job, the feed and the table
  agreeing exactly on the newest thirty rows, and the event log pruning from
  just past 20,000 back to 15,000 in one jump with the newest kept. The
  backend held at ~134 MB. That run is also what turned up the `last_tick`
  problem above - no test would have, because every test shuts down
  politely.

## Alternatives considered

**Write synchronously from the broadcast thread.** Simplest, and fine for
metrics alone. Rejected because of events: twenty batches a second through an
`fsync` on the thread that feeds every websocket is the one place this could
visibly hurt.

**`asyncio.to_thread` per write.** No queue to size and no thread to manage,
but it spawns a worker per call and gives up ordering between them, which the
`begin` → rows → `end` sequence depends on.

**Persist only important events.** Keeps the table small without pruning, but
makes `GET /events?type=gossip` answer differently depending on whether the
answer came from memory or disk. A cap with uniform contents is easier to
reason about than a filter.
