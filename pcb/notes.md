# PCB Design Notes — op-txm

## Board outline (same as OCM body)

- Size: 40×100 mm
- Mounting: 4× M2.2 NPTH at corners of 30×80 mm rectangular pattern
- Form factor: cylindrical microphone body, same as OCM

## Pad rules

- **SMD pads only** for resistors, capacitors, ICs, diodes — standard reflow assembly
- **Through-hole** for:
  - Capsule backplate and diaphragm leads (2 holes)
  - NTE10/3 transformer leads (5 holes — primary ×2, secondary ×3 or per winding count)
  - XLR wire solder points (3 holes — pin 1/2/3)

## Through-hole specifications

| Connection | Drill | Annular ring | Notes |
|---|---|---|---|
| Capsule leads | 0.8 mm | 1.5 mm | Fine wire; keep away from HV copper |
| Transformer leads (NTE10/3) | 1.0 mm | 2.5 mm | Hand-solder after reflow |
| XLR cable wires | 1.0 mm | 2.0 mm | At PCB tail end |

## HV keepout zone

- PHANTOM (48V) and V_BOOST (72V) nets require 0.5 mm clearance to all other copper
- Define a KiCad keepout zone in the bottom ~30 mm of the board (power zone)
- Capsule bias net (BP_CAPSULE, ~48V) — keep isolated from signal traces; minimum 0.5 mm clearance

## NTE10/3 transformer lead pads

The NTE10/3 has **5 free-wire leads** in the 1:3 configuration (2 primary + 2 for 1:3 secondary tap + 1 centre tap).
All leads get through-hole pads. Connection is **reversed 3:1** — op-amp drives the 3× secondary, XLR from 1× primary.

| Pad label | Drill | Function |
|---|---|---|
| TX_S3_HOT, TX_S3_RTN | 1.0 mm | 3× secondary — **driven by op-amp EQ output** (Blue / White leads) |
| TX_S3_CT | 1.0 mm | 3× secondary centre tap → signal GND (Yellow lead, tie to GND) |
| TX_P1, TX_P2 | 1.0 mm | 1× primary — **XLR pin 2 (hot) and XLR pin 3 (cold)** (Red / Black leads) |

The 1:10 secondary dummy pads serve two purposes:
1. Mechanical anchor — the leads are still soldered for strain relief
2. Future option — can be used if a different gain structure is needed

Mark the dummy pads in silkscreen: "TX 1:10 — NC" (no connect).
Do NOT leave 1:10 secondary leads hanging in air — solder them to the dummy pads.

Add 2× NPTH slots (2.5 mm) at PCB edge for cable-tie retention of the transformer body.

## NTE10/3 mounting

- Transformer body sits **off the PCB** — inside the mic basket or body, secured with cable ties
- Two 2.5 mm NPTH slots at PCB edge (or holes at 15 mm spacing) for cable tie retention
- Lead wire length: allow 40–60 mm of free wire from transformer body to PCB solder pads
- Solder pads for transformer leads: through-hole, 1.0 mm drill, placed near the PCB tail (XLR end)

## Capsule connection

- Two through-holes for capsule leads (backplate and diaphragm)
- Place at the PCB head (capsule end, opposite XLR)
- Keep VGATE trace (hi-Z, 1 GΩ gate bias) away from all other copper — 0.5 mm isolation clearance
- VGATE trace width: 0.15 mm, no copper pour closer than 0.5 mm on either layer

## Signal chain reference (left to right on 100 mm axis)

```
[Capsule TH pads] -- [JFET + Servo zone] -- [EQ zone] -- [Power zone] -- [Transformer TH pads + XLR TH pads]
   Y=0 (head end)                                                              Y=100 mm (tail end)
```

## Ground plane

- Solid B.Cu GND fill, 0.3 mm clearance, 0.5 mm thermal relief on SMD pads
- GND stitching: ≥1 via per zone, Ø0.3 mm drill / 0.6 mm Cu
- TPS7A39 exposed pad: 4 thermal vias (2×2, Ø0.25 mm) under EP

## Trace widths

| Net | Width |
|---|---|
| PHANTOM, V_BOOST (HV) | 0.40 mm |
| Power rails (P15V, N15V, P48V_LDO) | 0.30 mm |
| Signal | 0.15–0.20 mm |
| VGATE, FP_CAPSULE (hi-Z) | 0.15 mm |

## Fiducials

3× fiducials (FID1/2/3) at board corners, 1 mm Cu dot, 3 mm exclusion zone.

## See also

- `docs/pcb_routing_knowhow.md` — detailed routing rules and lessons from OCM code-driven layout
