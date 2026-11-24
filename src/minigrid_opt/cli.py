"""CLI for minigrid-opt."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence

from minigrid_opt.dispatch import BatterySpec, DieselSpec, HourlyStepInput, simulate_hybrid_dispatch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minigrid-opt",
        description="Hybrid Solar PV + Battery Cycle-Life + Diesel Dispatch Optimizer.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Simulate a 24-hour rural health clinic hybrid solar/LiFePO4/diesel system")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "demo":
        # 24-hour equatorial solar curve (6am-6pm) + clinic vaccine fridge (1.2 kW critical) + pump/office
        steps = [
            HourlyStepInput(
                hour=h,
                pv_kw=round(8.0 * math.sin(math.pi * (h - 6) / 12.0), 2) if 6 <= h <= 18 else 0.0,
                critical_load_kw=1.2,
                deferrable_load_kw=2.0 if 9 <= h <= 16 else 0.5,
            )
            for h in range(24)
        ]
        summary = simulate_hybrid_dispatch(
            steps,
            battery=BatterySpec("lifepo4", capacity_kwh=20.0, min_soc_frac=0.15),
            diesel=DieselSpec(rated_kw=6.0),
        )
        print(
            json.dumps(
                {
                    "hours": summary.hours,
                    "total_load_kwh": summary.total_load_kwh,
                    "critical_unserved_kwh": summary.critical_unserved_kwh,
                    "renewable_fraction_pct": summary.renewable_fraction_pct,
                    "diesel_liters": summary.diesel_liters,
                    "co2_kg": summary.co2_kg,
                    "equivalent_full_cycles": summary.equivalent_full_cycles,
                    "total_operating_cost_usd": summary.total_operating_cost_usd,
                },
                indent=2,
            )
        )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
