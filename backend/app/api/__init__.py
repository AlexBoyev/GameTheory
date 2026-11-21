"""Transport layer: routers, DTOs and the WebSocket hub.

Calls `services/` only - it never touches `sim/`, `ai/` or `persistence/`
directly (enforced by import-linter).
"""
