# minigrid-opt

**Deterministic hybrid Solar PV + LiFePO4/Lead-Acid battery cycle-life & diesel backup dispatch optimizer with tiered critical-load shedding for rural clinics, schools, and cold-rooms.**

Zero runtime dependencies. Pure Python 3.11+. Models battery depth-of-discharge (DoD) cycle wear, inverter round-trip efficiency, Willans-line diesel minimum-load fuel curves (preventing wet-stacking), CO₂ emissions, and critical-vs-deferrable load shedding.

## Quick Start

```bash
uv sync --extra dev
minigrid-opt demo
```

## License

MIT License — see [LICENSE](LICENSE).
