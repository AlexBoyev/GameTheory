"""Application services: engine lifecycle, metrics, snapshots.

May import everything below it (`sim/`, `ai/`, `persistence/`). Must not import
`api/` - transport subscribes to services, never the other way round.
"""
