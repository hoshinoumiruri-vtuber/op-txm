# PCB Routing Know-How (ported from OCM)

Accumulated routing rules and lessons from the OCM code-driven layout sessions.
Apply these when laying out op-txm manually in KiCad.

---

## Trace widths

| Net type | Width |
|---|---|
| V_BOOST, PHANTOM, BP_CAPSULE (HV) | 0.40 mm |
| Power rails (P15V, N15V, P48V_LDO, etc.) | 0.30 mm |
| Signal | 0.15–0.20 mm |
| VGATE, FP_CAPSULE (hi-Z capsule gate) | 0.15 mm |

HV traces (PHANTOM, V_BOOST) need 0.5 mm clearance to any lower-voltage net.

---

## Component packages (pad geometry reference)

| Package | Pad offset from center |
|---|---|
| 0402 | ±0.575 mm along long axis |
| 0805 | ±1.1 mm along long axis |
| SOIC-8 | X = ±2.7 mm, Y = ±0.635 / ±1.905 mm (1.27 mm pitch, 4 per side) |
| SOD-323 | ±1.05 mm along long axis |
| WSON-12 (TPS7A39) | Very tight pin pitch — expect DRC clearance warnings from adjacent HV traces |

---

## High-voltage keepout

Define a KiCad keepout zone around all PHANTOM / V_BOOST copper.
Minimum 0.5 mm clearance to any other copper.
On the 40×100 mm form factor, power zone occupies the bottom ~30 mm of the board.

---

## Ground plane strategy

- Solid B.Cu GND fill, 0.3 mm clearance, 0.5 mm thermal relief spokes on SMD pads
- GND stitching vias: at least one via per major copper island, Ø0.3 mm drill / 0.6 mm Cu
- Place stitching vias near decoupling caps and near the JFET source/gate area
- TPS7A39 exposed pad: minimum 4 thermal vias (2×2 grid, Ø0.25 mm drill) under the EP

---

## Routing topology lessons

### Crossing avoidance
- Route power trunks first (PHANTOM → LR8 → V_BOOST → regulator); signal routes come last
- Use 45° bends everywhere; avoid 90° corners
- If a straight route would cross another net, try: (a) a B.Cu via pair, (b) a waypoint detour around the obstacle, (c) route on B.Cu if the signal is not HV

### Structural overlap situations to accept
The following overlap types are geometrically unavoidable on tightly packed 40×100 mm boards and can be accepted after DRC review:
- Two adjacent IC pins exiting the same column (SOIC-8 pins 6/7 or 1/2)
- Power routes along the Y=130 corridor near SOD-323 diodes + inductor
- TPS7A39 WSON-12 adjacent-pin routes (D-cluster)

### Key learned rules
1. **Don't move a component to fix one overlap if it creates a crossing** — crossings are harder to resolve than overlaps.
2. **Always check both layers** after any component move; B.Cu routes cascade unexpectedly.
3. **Same-net B.Cu routes can self-cross** — check same-net pairs in the crossing audit too.
4. **SOIC-8 pin-column constraint**: pins 1/2 and 6/7 share the same X column; routes from these pin pairs will always overlap at the IC body edge. Accept as structural after confirming no inter-net DRC violation exists.
5. **HV corridor at Y=130** (power zone bottom): if D2 (SOD-323) and L1 (inductor) share Y=130, both V_BOOST and P48V_LDO are forced into that channel. No fix without relocating both; accept and note in DRC report.

---

## Fiducials

Place 3 fiducials (FID1/2/3) at board corners for PCBA pick-and-place alignment.
Keep 3 mm exclusion zone around each fiducial.

---

## PCB form factor (inherited from OCM)

- Board: 40×100 mm
- Mounting: 4× M2.2 NPTH, rectangular pattern 30×80 mm
- Assembly: 100% SMD except the NTE10/3 transformer (through-hole leads, off-board)
- Transformer mounting: zip tie slots or holes at board edge; transformer body sits outside PCB or in a cut-out

---

## Transformer (NTE10/3) PCB footprint notes

- NTE10/3 is an encapsulated audio transformer — leads exit the bottom
- Drill lead holes to fit lead diameter (check datasheet); use 1.0 mm drill as starting point
- Add two 2.5 mm NPTH slots or holes ~15 mm apart for zip tie retention
- Copper pads for transformer leads should be through-hole, minimum 2.5 mm annular ring (hand-soldering clearance)
- No SMD alternative — this part must be wave-soldered or hand-soldered last, after reflow

---

## Through-hole rules (capsule and transformer)

**Rule: only use SMD copper pads for SMD components. Capsule leads and transformer leads use through-hole (TH) drill holes.**

| Connection | Drill | Annular ring | Why |
|---|---|---|---|
| Capsule leads (2 holes) | 0.8 mm | 1.5 mm | Fine wire; solder after reflow |
| NTE10/3 transformer leads (5 holes) | 1.0 mm | 2.5 mm | Thicker lead wire; hand-solder last |
| XLR cable wires (3 holes) | 1.0 mm | 2.0 mm | At PCB tail end |
| Cable-tie NPTH slots for TX1 | 2.5 mm NPTH | no copper | Mechanical retention only |

- Do **not** use SMD pads for capsule or transformer connections
- Through-hole pads can be wave-soldered or hand-soldered after PCBA reflow
- Keep capsule TH pads at the head end (Y≈0), transformer TH pads at the tail end (Y≈100 mm)
- Capsule VGATE hole: isolate from all copper by 0.5 mm minimum on both layers

## DFM checklist (Taiwan PCBA)

- [ ] All SMD pads: minimum 0.15 mm solder mask expansion
- [ ] All SMD pads: minimum 0.15 mm silkscreen clearance
- [ ] Fiducials: 3 minimum, 1 mm copper dot + 3 mm clearance
- [ ] Minimum drill: 0.2 mm (laser via) or 0.3 mm (mechanical)
- [ ] Minimum track/space: 0.1 mm / 0.1 mm (prefer 0.15 mm / 0.15 mm for yield)
- [ ] No silkscreen over pads
- [ ] Paste layer: avoid paste on large exposed pads without thermal relief
