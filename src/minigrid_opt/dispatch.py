"""Hybrid Solar PV + Battery Cycle-Life + Diesel Dispatch Optimizer for Off-Grid Mini-Grids."""

from __future__ import annotations

from dataclasses import dataclass

# Diesel combustion emission factor: 2.68 kg CO2 per liter
DIESEL_CO2_KG_PER_LITER = 2.68


@dataclass(frozen=True)
class BatterySpec:
    chemistry: str  # "lifepo4" or "lead_acid"
    capacity_kwh: float
    min_soc_frac: float  # e.g. 0.15 for LiFePO4, 0.50 for Lead-Acid
    max_soc_frac: float = 0.98
    max_charge_kw: float = 5.0
    max_discharge_kw: float = 5.0
    roundtrip_efficiency: float = 0.92
    rated_full_cycles: int = 4000
    replacement_cost_usd: float = 4000.0


@dataclass(frozen=True)
class DieselSpec:
    rated_kw: float
    min_load_frac: float = 0.30  # Running below 30% causes wet-stacking & terrible efficiency
    no_load_l_per_hr_per_kw: float = 0.08  # Willans-line intercept coefficient a
    marginal_l_per_kwh: float = 0.25  # Willans-line slope coefficient b
    fuel_price_usd_per_l: float = 1.45


@dataclass(frozen=True)
class HourlyStepInput:
    hour: int
    pv_kw: float
    critical_load_kw: float  # e.g., vaccine fridge, clinic lighting
    deferrable_load_kw: float  # e.g., water pumping, maize milling, office AC


@dataclass(frozen=True)
class HourlyDispatch:
    hour: int
    pv_used_kw: float
    pv_curtailed_kw: float
    battery_charge_kw: float
    battery_discharge_kw: float
    diesel_kw: float
    diesel_liters: float
    critical_served_kw: float
    deferrable_served_kw: float
    unserved_load_kw: float
    soc_end_frac: float


@dataclass(frozen=True)
class SimulationSummary:
    hours: int
    total_load_kwh: float
    total_served_kwh: float
    critical_unserved_kwh: float
    deferrable_shed_kwh: float
    pv_generated_kwh: float
    pv_curtailed_kwh: float
    renewable_fraction_pct: float
    diesel_kwh: float
    diesel_liters: float
    fuel_cost_usd: float
    co2_kg: float
    equivalent_full_cycles: float
    estimated_battery_wear_usd: float
    total_operating_cost_usd: float
    hourly: tuple[HourlyDispatch, ...]


def simulate_hybrid_dispatch(
    profile: list[HourlyStepInput],
    *,
    battery: BatterySpec,
    diesel: DieselSpec | None = None,
    initial_soc_frac: float = 0.65,
    diesel_start_soc_frac: float = 0.25,
    diesel_stop_soc_frac: float = 0.70,
) -> SimulationSummary:
    """Run deterministic hourly load-following / cycle-charging hybrid dispatch with critical-load priority."""
    if not profile:
        raise ValueError("Hourly profile cannot be empty")
    if battery.capacity_kwh <= 0:
        raise ValueError("battery.capacity_kwh must be positive")

    soc = max(battery.min_soc_frac, min(battery.max_soc_frac, initial_soc_frac))
    eta_one_way = battery.roundtrip_efficiency**0.5
    diesel_running = False
    dispatches: list[HourlyDispatch] = []
    throughput_kwh = 0.0

    for step in profile:
        pv = max(0.0, step.pv_kw)
        crit = max(0.0, step.critical_load_kw)
        defer = max(0.0, step.deferrable_load_kw)
        total_req = crit + defer

        # 1. Serve load directly from PV first
        pv_to_load = min(pv, total_req)
        pv_surplus = pv - pv_to_load
        deficit = total_req - pv_to_load

        batt_charge = 0.0
        batt_discharge = 0.0
        diesel_kw = 0.0
        diesel_l = 0.0
        crit_served = min(pv_to_load, crit)
        defer_served = max(0.0, pv_to_load - crit)

        # 2. If PV surplus exists, charge battery up to max_soc and max_charge_kw
        if pv_surplus > 0.0:
            headroom_kwh = max(0.0, (battery.max_soc_frac - soc) * battery.capacity_kwh)
            max_grid_in = headroom_kwh / eta_one_way
            batt_charge = min(pv_surplus, battery.max_charge_kw, max_grid_in)
            soc += (batt_charge * eta_one_way) / battery.capacity_kwh
            throughput_kwh += batt_charge * 0.5
            pv_curtailed = pv_surplus - batt_charge
        else:
            pv_curtailed = 0.0

        # 3. If deficit exists, serve critical first from battery, then deferrable if SoC healthy
        if deficit > 0.0:
            avail_stored_kwh = max(0.0, (soc - battery.min_soc_frac) * battery.capacity_kwh)
            max_out_kw = min(battery.max_discharge_kw, avail_stored_kwh * eta_one_way)

            # Decide whether hysteresis triggers backup diesel generator
            if diesel is not None and (
                soc <= diesel_start_soc_frac
                or (diesel_running and soc < diesel_stop_soc_frac)
                or (crit - crit_served > max_out_kw)
            ):
                diesel_running = True
                # Cycle-charging: run generator at >= min_load_frac, charging battery with excess
                min_gen = diesel.rated_kw * diesel.min_load_frac
                headroom_kwh = max(0.0, (battery.max_soc_frac - soc) * battery.capacity_kwh)
                desired_charge = min(battery.max_charge_kw, headroom_kwh / eta_one_way)
                target_kw = min(diesel.rated_kw, max(min_gen, deficit + desired_charge))
                diesel_kw = target_kw
                diesel_l = (
                    diesel.no_load_l_per_hr_per_kw * diesel.rated_kw
                    + diesel.marginal_l_per_kwh * diesel_kw
                )
                gen_to_load = min(diesel_kw, deficit)
                rem_crit = max(0.0, crit - crit_served)
                c_add = min(gen_to_load, rem_crit)
                crit_served += c_add
                defer_served += min(max(0.0, defer - defer_served), gen_to_load - c_add)
                excess_gen = max(0.0, diesel_kw - gen_to_load)
                if excess_gen > 0.0:
                    c_bat = min(excess_gen, battery.max_charge_kw, headroom_kwh / eta_one_way)
                    batt_charge += c_bat
                    soc += (c_bat * eta_one_way) / battery.capacity_kwh
                    throughput_kwh += c_bat * 0.5
                if soc >= diesel_stop_soc_frac:
                    diesel_running = False
            else:
                diesel_running = False
                # Shed deferrable load if battery is below 30% SoC to protect critical loads
                rem_crit = max(0.0, crit - crit_served)
                rem_defer = max(0.0, defer - defer_served)
                allow_defer = rem_defer if soc > max(battery.min_soc_frac + 0.15, 0.30) else 0.0
                draw = min(max_out_kw, rem_crit + allow_defer)
                batt_discharge = draw
                soc -= (draw / eta_one_way) / battery.capacity_kwh
                throughput_kwh += draw * 0.5
                c_add = min(draw, rem_crit)
                crit_served += c_add
                defer_served += min(allow_defer, draw - c_add)

        unserved = max(0.0, total_req - (crit_served + defer_served))
        dispatches.append(
            HourlyDispatch(
                hour=step.hour,
                pv_used_kw=round(pv - pv_curtailed, 3),
                pv_curtailed_kw=round(pv_curtailed, 3),
                battery_charge_kw=round(batt_charge, 3),
                battery_discharge_kw=round(batt_discharge, 3),
                diesel_kw=round(diesel_kw, 3),
                diesel_liters=round(diesel_l, 3),
                critical_served_kw=round(crit_served, 3),
                deferrable_served_kw=round(defer_served, 3),
                unserved_load_kw=round(unserved, 3),
                soc_end_frac=round(soc, 4),
            )
        )

    total_load = sum(s.critical_load_kw + s.deferrable_load_kw for s in profile)
    total_served = sum(d.critical_served_kw + d.deferrable_served_kw for d in dispatches)
    crit_unserved = sum(
        max(0.0, s.critical_load_kw - d.critical_served_kw)
        for s, d in zip(profile, dispatches, strict=True)
    )
    defer_shed = sum(
        max(0.0, s.deferrable_load_kw - d.deferrable_served_kw)
        for s, d in zip(profile, dispatches, strict=True)
    )
    pv_gen = sum(max(0.0, s.pv_kw) for s in profile)
    pv_curt = sum(d.pv_curtailed_kw for d in dispatches)
    diesel_kwh = sum(d.diesel_kw for d in dispatches)
    diesel_liters = sum(d.diesel_liters for d in dispatches)
    fuel_price = diesel.fuel_price_usd_per_l if diesel else 0.0
    fuel_cost = diesel_liters * fuel_price
    eq_cycles = throughput_kwh / battery.capacity_kwh
    wear_cost = (eq_cycles / battery.rated_full_cycles) * battery.replacement_cost_usd
    ren_frac = (
        max(0.0, min(100.0, ((total_served - diesel_kwh) / total_served) * 100.0))
        if total_served > 0
        else 100.0
    )

    return SimulationSummary(
        hours=len(profile),
        total_load_kwh=round(total_load, 2),
        total_served_kwh=round(total_served, 2),
        critical_unserved_kwh=round(crit_unserved, 2),
        deferrable_shed_kwh=round(defer_shed, 2),
        pv_generated_kwh=round(pv_gen, 2),
        pv_curtailed_kwh=round(pv_curt, 2),
        renewable_fraction_pct=round(ren_frac, 1),
        diesel_kwh=round(diesel_kwh, 2),
        diesel_liters=round(diesel_liters, 2),
        fuel_cost_usd=round(fuel_cost, 2),
        co2_kg=round(diesel_liters * DIESEL_CO2_KG_PER_LITER, 2),
        equivalent_full_cycles=round(eq_cycles, 3),
        estimated_battery_wear_usd=round(wear_cost, 2),
        total_operating_cost_usd=round(fuel_cost + wear_cost, 2),
        hourly=tuple(dispatches),
    )
