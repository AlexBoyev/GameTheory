"""The pure, deterministic simulation core.

Rules enforced by import-linter (CLAUDE.md "Architecture rules", SPEC 2.1):

* no FastAPI / httpx / SQLModel - this package knows nothing about transport
  or storage;
* no wall-clock time and no global RNG - a `SimClock` and a seeded
  `numpy.random.Generator` are injected instead;
* same seed + LLM off => identical world after N ticks.
"""
