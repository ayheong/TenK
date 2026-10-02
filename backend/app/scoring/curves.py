"""Piecewise-linear mapping from a raw metric to a 0-100 risk score."""

from app.scoring.models import Signal, SignalKind


def interpolate(value: float, knots: list[tuple[float, float]]) -> float:
    """Linearly interpolate `value` over (metric, risk) knots sorted by
    ascending metric, clamping to the end scores outside the range."""
    if value <= knots[0][0]:
        return knots[0][1]
    for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
        if value <= x1:
            return y0 + (value - x0) / (x1 - x0) * (y1 - y0)
    return knots[-1][1]


def blend(
    scored: list[tuple[str, float | str, float, float, str]],
    kind: SignalKind = "quantitative",
) -> tuple[float, list[Signal]]:
    """Weight-average per-signal risk scores, renormalizing over the signals
    present. Each input is (key, raw_value, risk, weight, source); each
    returned Signal's contribution is its share of the blended score."""
    total_weight = sum(weight for _, _, _, weight, _ in scored)
    signals = [
        Signal(
            key=key,
            kind=kind,
            raw_value=raw,
            direction="raises" if risk > 0 else "lowers",
            contribution=risk * weight / total_weight,
            source=source,
        )
        for key, raw, risk, weight, source in scored
    ]
    return sum(s.contribution for s in signals), signals
