"""Búsqueda del objetivo más cercano por costo (base del modo «alerta solar»).

Cuadrículas diminutas generadas aquí; el resultado se contrasta con un Dijkstra
multi-destino de referencia escrito en la prueba y con find_path hacia cada objetivo.
"""

import heapq
import math
import random

import pytest

from algorithms.astar import (
    SQRT2,
    BlockedCellError,
    CostModel,
    Grid,
    GridCell,
    InvalidCellError,
    NoRouteError,
    NoTargetReachableError,
    find_nearest_target,
    find_path,
)


def reference_nearest_cost(grid, start, targets, model, allow_diagonal):
    """Dijkstra completo independiente: costo mínimo desde start a cualquier objetivo."""
    moves = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0)]
    if allow_diagonal:
        moves += [(-1, -1, SQRT2), (-1, 1, SQRT2), (1, -1, SQRT2), (1, 1, SQRT2)]
    dist = {start: 0.0}
    heap = [(0.0, start)]
    while heap:
        d, cur = heapq.heappop(heap)
        if d > dist.get(cur, math.inf):
            continue
        for dr, dc, f in moves:
            r, c = cur[0] + dr, cur[1] + dc
            if not grid.in_bounds(r, c) or grid.cell(r, c).blocked:
                continue
            if dr and dc and (grid.cell(cur[0] + dr, cur[1]).blocked
                              or grid.cell(cur[0], cur[1] + dc).blocked):
                continue
            nd = d + f * model.cell_multiplier(grid.cell(r, c))
            if nd < dist.get((r, c), math.inf):
                dist[(r, c)] = nd
                heapq.heappush(heap, (nd, (r, c)))
    reachable = [dist[t] for t in targets if t in dist]
    return min(reachable) if reachable else None


def random_grid(seed, rows=8, cols=9):
    rng = random.Random(seed)
    cells = [[GridCell(0.0, rng.uniform(0, 20), rng.random(), rng.random() < 0.2,
                       radiation=rng.random(), sky_view_factor=rng.uniform(0.7, 1.0))
              for _ in range(cols)] for _ in range(rows)]
    cells[0][0] = GridCell(0.0, 3.0, 0.1, False, radiation=0.5, sky_view_factor=0.99)
    return Grid(cells, 100.0)


def path_cost(grid, path, model):
    total = 0.0
    for a, b in zip(path, path[1:]):
        factor = SQRT2 if a[0] != b[0] and a[1] != b[1] else 1.0
        total += factor * model.cell_multiplier(grid.cell(*b))
    return total


@pytest.mark.parametrize("seed", range(20))
@pytest.mark.parametrize("allow_diagonal", [True, False])
@pytest.mark.parametrize("model", [CostModel(), CostModel(0.2, 2.0, radiation_weight=3.0)],
                         ids=["default", "weighted"])
def test_nearest_target_matches_dijkstra(seed, allow_diagonal, model):
    grid = random_grid(seed)

    def is_target(pos, cell):
        return not cell.blocked and cell.slope_deg <= 8 and cell.sky_view_factor <= 0.85

    targets = [(r, c) for r in range(grid.rows) for c in range(grid.cols)
               if is_target((r, c), grid.cell(r, c))]
    expected = reference_nearest_cost(grid, (0, 0), targets, model, allow_diagonal)
    if expected is None:
        with pytest.raises(NoTargetReachableError):
            find_nearest_target(grid, (0, 0), is_target, model, allow_diagonal)
        return
    result = find_nearest_target(grid, (0, 0), is_target, model, allow_diagonal)
    goal = result.path[-1]
    assert goal in targets
    assert result.path[0] == (0, 0)
    assert result.total_cost == pytest.approx(expected)
    assert path_cost(grid, result.path, model) == pytest.approx(result.total_cost)
    # Mismo costo que find_path al objetivo elegido, y ningún otro objetivo es más barato.
    assert find_path(grid, (0, 0), goal, model, allow_diagonal).total_cost == pytest.approx(
        result.total_cost)
    for target in targets:
        try:
            other = find_path(grid, (0, 0), target, model, allow_diagonal).total_cost
        except NoRouteError:
            continue
        assert other >= result.total_cost - 1e-9


def flat(blocked=False, svf=1.0):
    return GridCell(0.0, 0.0, 0.0, blocked, sky_view_factor=svf)


def test_origin_that_is_a_target_gives_single_cell_route():
    grid = Grid([[flat(svf=0.5), flat()], [flat(), flat()]], 100.0)
    result = find_nearest_target(grid, (0, 0), lambda p, c: c.sky_view_factor < 0.9)
    assert result.path == [(0, 0)]
    assert result.total_cost == 0.0 and result.distance_m == 0.0


def test_nearest_is_by_cost_not_by_distance():
    # Objetivo A a 2 pasos tras una celda muy pendiente; objetivo B a 4 pasos en llano.
    steep = GridCell(0.0, 40.0, 1.0, False, sky_view_factor=1.0)
    row = [flat(svf=0.5), steep, flat(), flat(), flat(), flat(), flat(), flat(svf=0.5)]
    grid = Grid([row], 100.0)
    result = find_nearest_target(grid, (0, 2), lambda p, c: c.sky_view_factor < 0.9,
                                 allow_diagonal=False)
    assert result.path[-1] == (0, 7)
    assert result.total_cost == pytest.approx(5.0)


def test_unreachable_targets_raise():
    grid = Grid([[flat(), flat(blocked=True), flat(svf=0.5)]], 100.0)
    with pytest.raises(NoTargetReachableError) as info:
        find_nearest_target(grid, (0, 0), lambda p, c: c.sky_view_factor < 0.9)
    assert info.value.nodes_expanded == 1


def test_invalid_or_blocked_origin_raises():
    grid = Grid([[flat(blocked=True), flat()]], 100.0)
    with pytest.raises(BlockedCellError):
        find_nearest_target(grid, (0, 0), lambda p, c: True)
    with pytest.raises(InvalidCellError):
        find_nearest_target(grid, (5, 0), lambda p, c: True)


def test_sky_view_factor_does_not_change_cost():
    a = GridCell(0.0, 5.0, 0.2, False, radiation=0.3, sky_view_factor=0.1)
    b = GridCell(0.0, 5.0, 0.2, False, radiation=0.3, sky_view_factor=0.9)
    model = CostModel(0.1, 2.0, radiation_weight=1.0)
    assert model.cell_multiplier(a) == model.cell_multiplier(b)
