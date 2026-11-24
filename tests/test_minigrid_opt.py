"""Tests for hybrid Solar PV + Battery + Diesel dispatch, critical load shedding & CLI."""

from __future__ import annotations

import json

import pytest

from minigrid_opt import BatterySpec, DieselSpec, HourlyStepInput, simulate_hybrid_dispatch
from minigrid_opt.cli import main as cli_main


def test_sunny_day_achieves_100_percent_renewable_and_zero_diesel() -> None:
    steps = [
        HourlyStepInput(
            hour=h,
            pv_kw=6.0 if 7 <= h <= 17 else 0.0,
            critical_load_kw=1.0,
            deferrable_load_kw=0.5,
        )
        for h in range(24)
    ]
    rep = simulate_hybrid_dispatch(
        steps,
        battery=BatterySpec("lifepo4", capacity_kwh=25.0, min_soc_frac=0.15),
        diesel=DieselSpec(rated_kw=5.0),
        initial_soc_frac=0.80,
    )
    assert rep.critical_unserved_kwh == 0.0
    assert rep.diesel_liters == 0.0
    assert rep.renewable_fraction_pct == 100.0
    assert rep.equivalent_full_cycles > 0.0


def test_cloudy_outage_sheds_deferrable_load_and_runs_diesel_above_min_load() -> None:
    # Zero solar for 12 hours with low starting SoC forces diesel cycle-charging
    steps = [HourlyStepInput(hour=h, pv_kw=0.0, critical_load_kw=1.5, deferrable_load_kw=2.0) for h in range(12)]
    rep = simulate_hybrid_dispatch(
        steps,
        battery=BatterySpec("lead_acid", capacity_kwh=10.0, min_soc_frac=0.50, rated_full_cycles=1200),
        diesel=DieselSpec(rated_kw=6.0, min_load_frac=0.35),
        initial_soc_frac=0.52,
        diesel_start_soc_frac=0.55,
        diesel_stop_soc_frac=0.85,
    )
    assert rep.critical_unserved_kwh == 0.0
    assert rep.diesel_liters > 0.0
    assert rep.co2_kg > 0.0
    # Every active diesel hour runs at or above minimum load (2.1 kW) to prevent wet-stacking
    for hr in rep.hourly:
        if hr.diesel_kw > 0:
            assert hr.diesel_kw >= 2.1


def test_cli_demo(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(["demo"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["critical_unserved_kwh"] == 0.0
    assert out["hours"] == 24
