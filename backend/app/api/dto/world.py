"""Terrain transfer DTO (SPEC section 3)."""

from pydantic import BaseModel, ConfigDict, Field


class TerrainDTO(BaseModel):
    """`GET /api/world/terrain`.

    The heightmap is a base64-encoded little-endian Float32 array of
    `resolution * resolution` values in row-major `[z][x]` order; `biomes` is
    the same shape as uint8 ordinals indexed into `biome_names`.
    """

    model_config = ConfigDict(extra="forbid")

    size: float = Field(description="World extent in world units.")
    resolution: int = Field(description="Grid cells per axis.")
    water_level: float
    max_height: float
    heights_b64: str = Field(description="base64 Float32, row-major.")
    biomes_b64: str = Field(description="base64 uint8 biome ordinals.")
    biome_names: list[str] = Field(description="Index -> biome name.")
