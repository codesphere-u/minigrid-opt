"""minigrid-opt — Hybrid Solar PV, Battery Cycle-Life & Diesel Dispatch Optimizer."""

from minigrid_opt.dispatch import (
    DIESEL_CO2_KG_PER_LITER,
    BatterySpec,
    DieselSpec,
    HourlyDispatch,
    HourlyStepInput,
    SimulationSummary,
    simulate_hybrid_dispatch,
)

__version__ = "0.1.0"

__all__ = [
    "DIESEL_CO2_KG_PER_LITER",
    "BatterySpec",
    "DieselSpec",
    "HourlyDispatch",
    "HourlyStepInput",
    "SimulationSummary",
    "__version__",
    "simulate_hybrid_dispatch",
]
