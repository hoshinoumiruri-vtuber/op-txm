# op-txm — Transformer-Output Condenser Microphone

Solid-state condenser microphone with transformer-balanced output. Derived from the OCM project: same power stage, JFET buffer, DC servo, and K47/K87 dual-capsule EQ. The optical compressor and code-driven PCB layout are dropped. PCB layout is done manually in KiCad.

---

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Technical Specifications](#2-technical-specifications)
3. [Output Transformer — Neutrik NTE10/3](#3-output-transformer--neutrik-nte103)
4. [Engineering Verification and Simulation Results](#4-engineering-verification-and-simulation-results)
5. [Toolchain](#5-toolchain)
6. [Getting Started](#6-getting-started)
7. [Project Phases](#7-project-phases)
8. [Repository Structure](#8-repository-structure)

---

## 1. System Architecture

```
[XLR Phantom 48V] --> [LR8 Pre-reg 35.2V + Charge Pump] --> [JFET Input Buffer + DC Servo]
                              |                                            |
                        [TPS7A3901 +/-15V]                   [K47/K87 De-emphasis EQ]
                                                                           |
                                                          [NTE10/3 Output Transformer 1:3]
                                                                           |
                                                                    [XLR Balanced Out]
```

| Stage | Description |
|---|---|
| Power | LR8 pre-regulator (48V phantom → 35.2V). Diode charge pump → V_BOOST for JFET drain. TPS7A3901 WSON-12 → ±15V op-amp supply. Total draw < 7 mA. |
| Input | High-Z JFET buffer (MMBF170LT1G SOT-23) with op-amp DC servo for bias stability. |
| EQ | Active de-emphasis network tuned for K67/K87. Flat (K47) or −6 dB shelf above ~22 kHz (K87) via SJ1 solder bridge. |
| Output | Neutrik NTE10/3 1:3 turns ratio: transformer-balanced, galvanic isolation, passive CMRR. |

---

## 2. Technical Specifications

| Parameter | Value |
|---|---|
| Supply | +48V phantom power (IEC 61938) |
| Internal rail | 35.2V (LR8 pre-reg) → ±15V (TPS7A3901); V_BOOST charge pump for JFET drain |
| Max current draw | < 7 mA (phantom power budget) |
| Capsule | Takstar K87, 34 mm rim-terminated |
| Capsule compatibility | K47 (flat) and K87/K67 (de-emphasised) via SJ1 solder bridge |
| PCB form factor | 40×100 mm |
| Mounting | 4× M2.2 NPTH, rectangular pattern (30×80 mm) — same as OCM body |
| Assembly | SMD for all active/passive components; through-hole for capsule leads and NTE10/3 transformer leads |
| De-emphasis network | R_shelf = 47 kΩ, C_deemph = 150 pF — −6 dB shelf above ~22 kHz |
| Output stage | Neutrik NTE10/3 transformer, 1:3 turns ratio (+9.5 dB voltage step-up) |
| EQ op-amp | OPA1642AIDR (dual JFET-input, GBW=11 MHz, EIN=5.1 nV/√Hz) |
| Output balance | Transformer CMRR (passive) — no active output op-amp required |
| Output impedance | ~540 Ω referred to secondary (JFET 60Ω × n²=9) |

---

## 3. Output Transformer — Neutrik NTE10/3

### Confirmed specifications

| Parameter | Value | Source |
|---|---|---|
| Turns ratio | 1:3:10 (two secondary taps) | Neutrik datasheet |
| Selected tap | 1:3 (secondary = 1.8 kΩ) | Design choice |
| Primary impedance | 200 Ω | Neutrik / Farnell |
| Secondary impedance (1:3 tap) | 1.8 kΩ | Neutrik / Farnell |
| Secondary impedance (1:10 tap) | 20 kΩ | Neutrik / Farnell |
| Frequency response | 40 Hz – 20 kHz ±0.5 dB | Distributor spec |
| Solderability | IEC 68-2-20 compliant | Neutrik datasheet |
| Primary inductance | ~80 H (community measurement) | GroupDIY forum |
| Primary DCR | **TBD — measure at bench** | — |
| Leakage inductance | **TBD — measure at bench** | — |

> Update `sim/tx_output.py` with measured DCR and leakage inductance values before running the frequency response simulation.

### Wiring / connection

```
NTE10/3 lead colour (typical):
  Primary:
    Red   → JFET buffer output (hot)
    Black → GND (primary return / signal GND)
  Secondary (1:3 tap):
    Blue  → XLR pin 2 (hot)
    White → XLR pin 3 (cold / secondary CT or full secondary)
    Yellow→ Secondary centre tap → phantom bypass (33 kΩ to pin 2, 33 kΩ to pin 3)
```

> **Verify lead colours against the physical unit** — Neutrik wire colours are not always consistent across production batches. Use an LCR meter to confirm winding connections before soldering.

### PCB mounting

The NTE10/3 is an encapsulated off-board transformer connected via its free wires. It is **not** mounted on the PCB directly.

- Solder the five leads to through-hole pads on the PCB (1.0 mm drill, 2.5 mm annular ring recommended)
- Secure the transformer body inside the mic capsule body with two cable ties through 2.5 mm NPTH slots at the PCB edge (or adhesive mount to the capsule basket)
- Allow enough wire slack for the transformer to not stress the PCB pads

---

## 4. Engineering Verification and Simulation Results

All simulations run analytically (Python) with ngspice batch mode for transient verification.

### 4.1 Power Stage (inherited from OCM — Task 2)

72V boost stage (Cockcroft-Walton charge pump), LR8 pre-regulator, TPS7A39 ±15V.

| Parameter | Value | Status |
|---|---|---|
| 72V rail ripple (after LC filter) | 0.177 µV p-p | PASS |
| LR8 junction temperature | 58.3 °C (45 °C ambient) | PASS |
| TPS7A39 junction temperature | 48.5 °C (45 °C ambient) | PASS |
| Phantom current draw | 6.75 mA | PASS (< 7 mA) |

### 4.2 JFET Buffer + DC Servo (inherited from OCM — Task 9)

MMBF170 JFET, OPA2134 servo, Vdrain locked to 36 V ±1 V across 0–50 °C.

| Parameter | Value | Status |
|---|---|---|
| gm at operating point | 16.18 mA/V | — |
| Gain drift over temperature | 0.0 dB | PASS |
| Servo phase margin | 90° | PASS |
| EIN @ 1 kHz | 13.01 nV/√Hz | — |

### 4.3 K47/K87 De-emphasis EQ (inherited from OCM — Task 5)

| Frequency | K47 gain | K87 gain |
|---|---|---|
| 20 Hz | 0.00 dB | 0.00 dB |
| 1 kHz | 0.00 dB | −0.03 dB |
| 10 kHz | 0.00 dB | −1.74 dB |
| 20 kHz | 0.00 dB | −3.65 dB |

Phase margin ≥ 90° across all EQ states.

### 4.4 Full Signal Chain (sim/signal_chain.py) — ngspice PASS

K47/K87 modes, JFET → OPA1642 EQ → NTE10/3 → 600 Ω balanced load.

| Parameter | Value | Notes |
|---|---|---|
| Gain @ 1 kHz (K47, self-biased) | +27.5 dB | Servo adds ~+8 dB → ~+35 dB (see dc_servo.py) |
| Gain @ 20 kHz (K47) | +27.1 dB | Flat within 0.4 dB |
| K87 shelf @ 20 kHz | −3.7 dB | Expected — shelf corner is 22.6 kHz |
| K87 shelf @ 100 kHz | −5.9 dB | PASS (target −6 dB ±1.5 dB) |
| Bandwidth LF −3 dB (K47) | 10 Hz (self-biased) | Sub-Hz with servo-locked Q-point |
| Bandwidth HF −3 dB (K47) | 60 kHz | Well above audio band |
| Phase @ 1 kHz (K47) | −0.3° | — |
| Transformer step-up | +9.5 dB | 1:3 turns ratio, voltage |
| Transformer LF −3 dB | ~1.6 Hz | Estimated (Lpri=80 H) |
| Transformer HF −3 dB | ~42 kHz | Estimated (Lleak=0.5 mH, TBD) |

> Transformer DCR and leakage inductance are estimated. Update `sim/tx_output.py` and `sim/signal_chain.py` after bench measurement.

---

## 5. Toolchain

| Tool | Purpose | Version |
|---|---|---|
| Python | Primary language | 3.12+ |
| uv | Package and environment management | 0.11.8+ |
| ngspice | SPICE simulation engine | 46 |
| PySpice | Python wrapper for ngspice | 1.5 |
| KiCad | PCB design (manual layout) | 10.0.3+ |
| numpy / scipy | Numerical analysis | 2.4 / 1.17 |
| matplotlib | Plotting | 3.10 |

> **PCB layout is done manually in KiCad** — no code-driven layout scripts. See `docs/pcb_routing_knowhow.md` for routing rules and lessons from the OCM project.

> **ngspice -b batch mode** — do not use PySpice's `NgSpiceShared` API (unreliable with ngspice 42+).

---

## 6. Getting Started

### Prerequisites

```bash
# Arch Linux
sudo pacman -S ngspice kicad

# Ubuntu / Debian
sudo apt install ngspice kicad
```

### Python Environment

```bash
uv sync
```

### Running Simulations

```bash
source .venv/bin/activate

# Power stage
python sim/boost_72v.py

# JFET buffer + DC servo
python sim/dc_servo.py

# K47/K87 de-emphasis EQ
python sim/dual_capsule_eq.py

# Transformer output stage (update DCR/Lleak values first)
python sim/tx_output.py

# Generate all plots
python sim/generate_plots.py
```

---

## 7. Project Phases

### Phase 1: Simulation — IN PROGRESS

- [x] Port power stage simulation from OCM (boost_72v.py)
- [x] Port JFET buffer + DC servo from OCM (dc_servo.py)
- [x] Port K47/K87 EQ from OCM (dual_capsule_eq.py)
- [ ] Measure NTE10/3 DCR and leakage inductance (bench LCR meter)
- [ ] Update tx_output.py with measured values
- [ ] Run full signal-chain AC sweep including transformer

### Phase 2: PCB Layout (manual KiCad)

- [ ] Start new KiCad project: 40×100 mm, 4× M2.2 NPTH (30×80 mm pattern)
- [ ] Draw schematic: power, JFET buffer, EQ, transformer output
- [ ] Place components, define HV keepout, B.Cu GND plane
- [ ] Route manually (refer to `docs/pcb_routing_knowhow.md`)
- [ ] Add through-hole pads for NTE10/3 leads + NPTH zip-tie slots
- [ ] DRC — zero clearance violations
- [ ] Fill All Zones (B key), export Gerbers

### Phase 3: BOM + Procurement

- [ ] Generate BOM (bom/generate_bom.py)
- [ ] DFM review for Taiwan PCBA
- [ ] Order NTE10/3 (check stock: Farnell, Mouser)
- [ ] Order long-lead parts: IXYS LR8, TPS7A3901

### Phase 4: Bench Validation (hardware)

- [ ] Power-on: verify 35.2V LR8 rail, ±15V, V_BOOST
- [ ] DC servo: check Vdrain = 36V ±1V across 0–50°C
- [ ] Noise floor A-weighted (target < 14 dB-A)
- [ ] Frequency response 20Hz–20kHz (±1 dB)
- [ ] Output CMRR via transformer (target > 60 dB at 1 kHz)
- [ ] Phantom current draw (target < 7 mA)
- [ ] Acoustic evaluation

---

## 8. Repository Structure

```
op-txm/
├── pyproject.toml
├── README.md
├── sim/
│   ├── boost_72v.py          # Power stage (ported from OCM)
│   ├── dc_servo.py           # JFET DC servo (ported from OCM)
│   ├── dual_capsule_eq.py    # K47/K87 EQ (ported from OCM)
│   ├── tx_output.py          # NTE10/3 transformer output stage
│   ├── generate_plots.py     # Batch plot generator
│   └── models/               # Ngspice device models
├── bom/
│   └── generate_bom.py       # BOM generator
├── pcb/                      # KiCad project files (manual layout)
│   └── notes.md              # PCB constraints and layout notes
├── docs/
│   └── pcb_routing_knowhow.md # Routing rules ported from OCM
└── assets/
    └── sim_results/           # Generated plots
```
