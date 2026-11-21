"""Terrain transfer (SPEC section 3)."""

from fastapi import APIRouter

from app.api.deps import SimulationDep
from app.api.dto.world import TerrainDTO

router = APIRouter(prefix="/world", tags=["world"])


@router.get("/terrain", response_model=TerrainDTO, summary="Heightmap and biome map")
def terrain(simulation: SimulationDep) -> TerrainDTO:
    """Return the island heightmap and biome map as base64 arrays.

    Sent once per world: the terrain only changes on reset, so the frontend
    caches the mesh and the socket carries nothing but the moving parts.
    """
    return TerrainDTO(**simulation.queries.terrain_payload())
