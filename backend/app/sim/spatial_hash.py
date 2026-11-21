"""Uniform-grid spatial hash for neighbour queries (SPEC section 3).

This is the hottest data structure in the simulation: perception alone runs a
few hundred radius queries per tick, so two things matter more than elegance.

1. **Scan the fewest cells.** With `cell_size >= radius` a query can only
   reach one cell in each direction, so nine cells is the correct answer -
   scanning a wider ring is pure waste.
2. **Keep coordinates in the bucket.** Storing `(id, x, z)` inline means a
   candidate costs one tuple unpack instead of a dictionary lookup, which at
   a few million candidates per second is most of the cost.
"""

from collections.abc import Iterator
from math import ceil, floor

type Cell = tuple[int, int]
type Entry = tuple[int, float, float]


class SpatialHash:
    """Maps 2D positions to integer cells and answers radius queries.

    Insertion order is preserved per cell and cells are visited in a fixed
    order, so results are deterministic for a given insertion sequence.
    """

    __slots__ = ("_cells", "_positions", "cell_size")

    def __init__(self, cell_size: float) -> None:
        if cell_size <= 0:
            msg = "cell_size must be positive"
            raise ValueError(msg)
        self.cell_size = cell_size
        self._cells: dict[Cell, list[Entry]] = {}
        self._positions: dict[int, tuple[float, float]] = {}

    def __len__(self) -> int:
        return len(self._positions)

    def __contains__(self, item_id: object) -> bool:
        return item_id in self._positions

    def clear(self) -> None:
        """Drop all entries, keeping the configured cell size."""
        self._cells.clear()
        self._positions.clear()

    def cell_of(self, x: float, z: float) -> Cell:
        """Return the cell coordinates containing `(x, z)`."""
        return floor(x / self.cell_size), floor(z / self.cell_size)

    def position_of(self, item_id: int) -> tuple[float, float] | None:
        """Return the stored position of `item_id`, or `None`."""
        return self._positions.get(item_id)

    def insert(self, item_id: int, x: float, z: float) -> None:
        """Insert or move `item_id` to `(x, z)`."""
        previous = self._positions.get(item_id)
        new_cell = self.cell_of(x, z)

        if previous is not None:
            old_cell = self.cell_of(*previous)
            if old_cell == new_cell:
                bucket = self._cells[old_cell]
                for index, entry in enumerate(bucket):
                    if entry[0] == item_id:
                        bucket[index] = (item_id, x, z)
                        break
                self._positions[item_id] = (x, z)
                return
            self._remove_from_cell(old_cell, item_id)

        self._positions[item_id] = (x, z)
        self._cells.setdefault(new_cell, []).append((item_id, x, z))

    def remove(self, item_id: int) -> None:
        """Remove `item_id` if present."""
        position = self._positions.pop(item_id, None)
        if position is not None:
            self._remove_from_cell(self.cell_of(*position), item_id)

    def rebuild(self, items: Iterator[tuple[int, float, float]]) -> None:
        """Clear and re-insert everything - cheaper than moving every agent."""
        cells: dict[Cell, list[Entry]] = {}
        positions: dict[int, tuple[float, float]] = {}
        cell_size = self.cell_size

        for item_id, x, z in items:
            positions[item_id] = (x, z)
            cell = (floor(x / cell_size), floor(z / cell_size))
            bucket = cells.get(cell)
            if bucket is None:
                cells[cell] = [(item_id, x, z)]
            else:
                bucket.append((item_id, x, z))

        self._cells = cells
        self._positions = positions

    def query_radius(self, x: float, z: float, radius: float) -> list[int]:
        """Return ids within `radius` of `(x, z)`, nearest-cell-first order."""
        if radius <= 0:
            return []
        cell_size = self.cell_size
        cell_x = floor(x / cell_size)
        cell_z = floor(z / cell_size)
        # A circle of radius r reaches at most ceil(r / cell) cells away.
        span = max(1, ceil(radius / cell_size))
        radius_squared = radius * radius
        cells = self._cells
        found: list[int] = []

        for dz in range(-span, span + 1):
            row = cell_z + dz
            for dx in range(-span, span + 1):
                bucket = cells.get((cell_x + dx, row))
                if bucket is None:
                    continue
                for item_id, item_x, item_z in bucket:
                    offset_x = item_x - x
                    offset_z = item_z - z
                    if offset_x * offset_x + offset_z * offset_z <= radius_squared:
                        found.append(item_id)
        return found

    def neighbours(self, item_id: int, radius: float) -> list[int]:
        """Return ids within `radius` of `item_id`, excluding itself."""
        position = self._positions.get(item_id)
        if position is None:
            return []
        return [other for other in self.query_radius(*position, radius) if other != item_id]

    def _remove_from_cell(self, cell: Cell, item_id: int) -> None:
        bucket = self._cells.get(cell)
        if bucket is None:
            return
        for index, entry in enumerate(bucket):
            if entry[0] == item_id:
                del bucket[index]
                break
        if not bucket:
            del self._cells[cell]
