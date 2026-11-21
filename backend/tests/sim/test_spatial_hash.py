"""The spatial hash must agree with brute force, always."""

import math

from hypothesis import given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st

from app.sim.spatial_hash import SpatialHash

COORDINATE = st.floats(min_value=-200.0, max_value=200.0, allow_nan=False, allow_infinity=False)
POINTS = st.lists(st.tuples(COORDINATE, COORDINATE), min_size=0, max_size=60)


def brute_force(
    points: list[tuple[float, float]],
    x: float,
    z: float,
    radius: float,
) -> set[int]:
    """Return the ids within `radius`, computed the obvious way."""
    return {
        index
        for index, (point_x, point_z) in enumerate(points)
        if math.hypot(point_x - x, point_z - z) <= radius
    }


@given(points=POINTS, query=st.tuples(COORDINATE, COORDINATE), radius=st.floats(0.5, 50.0))
@hypothesis_settings(max_examples=200, deadline=None)
def test_query_radius_matches_brute_force(
    points: list[tuple[float, float]],
    query: tuple[float, float],
    radius: float,
) -> None:
    index = SpatialHash(cell_size=18.0)
    for item_id, (x, z) in enumerate(points):
        index.insert(item_id, x, z)

    found = set(index.query_radius(query[0], query[1], radius))

    assert found == brute_force(points, query[0], query[1], radius)


@given(points=POINTS, radius=st.floats(0.5, 40.0), cell_size=st.floats(2.0, 40.0))
@hypothesis_settings(max_examples=120, deadline=None)
def test_result_is_independent_of_cell_size(
    points: list[tuple[float, float]],
    radius: float,
    cell_size: float,
) -> None:
    """Cell size is a performance knob; it must never change the answer."""
    coarse = SpatialHash(cell_size=cell_size)
    fine = SpatialHash(cell_size=2.0)
    for item_id, (x, z) in enumerate(points):
        coarse.insert(item_id, x, z)
        fine.insert(item_id, x, z)

    assert set(coarse.query_radius(0.0, 0.0, radius)) == set(fine.query_radius(0.0, 0.0, radius))


def test_insert_moves_an_existing_item() -> None:
    index = SpatialHash(cell_size=10.0)
    index.insert(1, 0.0, 0.0)
    index.insert(1, 100.0, 100.0)

    assert len(index) == 1
    assert index.query_radius(0.0, 0.0, 5.0) == []
    assert index.query_radius(100.0, 100.0, 5.0) == [1]


def test_move_within_the_same_cell_updates_the_position() -> None:
    index = SpatialHash(cell_size=50.0)
    index.insert(1, 1.0, 1.0)
    index.insert(1, 40.0, 40.0)

    assert index.position_of(1) == (40.0, 40.0)
    assert index.query_radius(1.0, 1.0, 5.0) == []
    assert index.query_radius(40.0, 40.0, 1.0) == [1]


def test_remove_and_rebuild() -> None:
    index = SpatialHash(cell_size=8.0)
    index.rebuild(iter([(1, 0.0, 0.0), (2, 1.0, 1.0), (3, 50.0, 50.0)]))
    assert len(index) == 3

    index.remove(2)
    assert 2 not in index
    assert set(index.query_radius(0.0, 0.0, 5.0)) == {1}

    index.rebuild(iter([(9, 0.0, 0.0)]))
    assert len(index) == 1
    assert index.query_radius(0.0, 0.0, 1.0) == [9]


def test_neighbours_excludes_itself() -> None:
    index = SpatialHash(cell_size=18.0)
    index.insert(1, 0.0, 0.0)
    index.insert(2, 3.0, 0.0)

    assert index.neighbours(1, 10.0) == [2]
    assert index.neighbours(99, 10.0) == []


def test_zero_radius_finds_nothing() -> None:
    index = SpatialHash(cell_size=4.0)
    index.insert(1, 0.0, 0.0)

    assert index.query_radius(0.0, 0.0, 0.0) == []


def test_a_query_at_a_cell_edge_still_finds_the_far_neighbour() -> None:
    """The exact case a property test found (and a span-based scan missed).

    The query sits a hair below zero, which puts it in cell -1, while the
    point at z=18 is in cell +1. A span of `ceil(radius / cell_size)` = 1
    around the query's cell covers cells -2..0 and never looks at +1, so a
    neighbour at exactly the vision radius was invisible - but only when the
    querying agent happened to be standing within a whisker of a cell border.
    """
    index = SpatialHash(cell_size=18.0)
    index.insert(0, 0.0, 18.0)

    assert index.query_radius(0.0, -1e-92, 18.0) == [0]


def test_cell_boundaries_agree_with_brute_force_from_every_side() -> None:
    """Sweep a query across a cell border with the target at the radius.

    Asserting "found" outright would be wrong: a query nudged to -1e-9 is
    10.000000001 from a point at 10.0, so it is genuinely out of range. The
    invariant is agreement with the obvious calculation, at exactly the
    offsets where a cell-span scan and the truth diverge.
    """
    cell = 10.0

    for offset in (-1e-9, -1e-12, 0.0, 1e-12, 1e-9):
        for distance in (cell, cell * 2, cell * 2.5):
            index = SpatialHash(cell_size=cell)
            index.insert(0, distance, 0.0)
            points = [(distance, 0.0)]

            along_x = set(index.query_radius(offset, 0.0, distance))
            assert along_x == brute_force(points, offset, 0.0, distance), (
                f"disagreed for a point {distance} away from a query at x={offset}"
            )

            index_z = SpatialHash(cell_size=cell)
            index_z.insert(0, 0.0, distance)
            along_z = set(index_z.query_radius(0.0, offset, distance))
            assert along_z == brute_force([(0.0, distance)], 0.0, offset, distance)
