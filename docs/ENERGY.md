# Energy, cost, carbon and savings calculations

All formulas live in `app/services/energy.py` and are unit-tested in `tests/test_energy.py`
and `tests/test_telemetry.py`.

## Energy (measured)

Between consecutive readings of an appliance (trapezoidal rule):

```
E [kWh] = (P1 + P2) / 2 [W] × Δt [s] / 3 600 000
```

* Gaps longer than `MAX_INTEGRATION_GAP_SECONDS` (default 300 s) are **not** integrated — the
  system does not invent consumption for periods without data.
* Out-of-order/duplicate readings are skipped.
* Energy is distributed over **15-minute UTC buckets** (`energy_records`), split proportionally
  at bucket boundaries. 15 minutes aligns with every real timezone offset (e.g. IST +5:30), so
  "today" is computed exactly from local midnight.
* Verified: a constant 1000 W load sampled every 10 s for one hour integrates to exactly
  1.000 kWh and costs exactly 8.00 at the default tariff.

## Wasted energy (measured, under stated assumptions)

The part of an interval during which the room was **vacant** (per the occupancy sensor) and the
appliance was non-essential and above its standby threshold. It is only as good as the occupancy
sensor (PIR sensors can miss motionless occupants).

## Cost

`cost = Σ kWh_bucket × rate(bucket midpoint)`. Rates are configurable: flat rate, optionally
time-of-use periods (local time, windows may cross midnight). Default: ₹8.00/kWh (placeholder —
set your institution's tariff).

## Carbon

`CO₂ [kg] = kWh × grid emission factor`. Default 0.71 kg/kWh (approximate Indian grid average —
replace with the factor published for your grid/year).

## Estimated savings (counterfactual estimate — labelled as such everywhere)

A savings **episode** starts when an OFF command for an appliance in a **vacant** room is
**acknowledged** (simulated, emulated or hardware) and the appliance was drawing more than its
standby threshold. The episode ends when the appliance is switched on again (telemetry or ON
command) or the room becomes occupied, and is capped at `savings_cap_hours` (default 8 h).

```
avoided kWh = baseline power (last reading before shutdown) × off-duration (capped) / 1000
```

The counterfactual assumption — *the load would otherwise have kept running at its
pre-shutdown power* — is shown next to every savings figure. Savings from simulated shutdowns are
tagged `simulation`. Dry-run decisions never produce savings. The dashboard never presents
estimated savings as measured.
