"""Metrics time series for the charts panel (SPEC section 10).

`MetricsService.series` stitches the in-memory window together with whatever
the run archive holds from earlier in the run, so this stays a straight
mapping to DTOs.
"""

from fastapi import APIRouter, Query

from app.api.deps import MetricsDep
from app.api.dto.observability import MetricPointDTO, MetricsDTO

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_model=MetricsDTO, summary="Metrics time series")
def get_metrics(metrics: MetricsDep, from_tick: int = Query(default=0, ge=0)) -> MetricsDTO:
    """Return samples at or after `from_tick`."""
    return MetricsDTO(
        from_tick=from_tick,
        sample_every_ticks=metrics.sample_every_ticks,
        points=[
            MetricPointDTO(
                tick=point.tick,
                sim_seconds=point.sim_seconds,
                population=point.population,
                births=point.births,
                deaths=point.deaths,
                cooperation_rate=point.cooperation_rate,
                food_gini=point.food_gini,
                trust_density=point.trust_density,
                deaths_by_cause=point.deaths_by_cause,
                by_tribe=point.by_tribe,
                by_strategy=point.by_strategy,
                payoff_by_strategy=point.payoff_by_strategy,
                cooperation_by_game=point.cooperation_by_game,
                extra={key: float(value) for key, value in point.extra.items()},
            )
            for point in metrics.series(from_tick)
        ],
    )
