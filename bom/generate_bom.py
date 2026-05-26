"""
BOM generator for op-txm.

Reference designators match pcb/layout.py exactly.

Outputs:
  bom/txm_bom.csv       — full BOM (one row per unique MPN)
  bom/txm_bom_dfm.txt   — DFM review summary for Taiwan PCBA
"""

import csv
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent


@dataclass
class Part:
    refs: str          # comma-separated (e.g. "R_TPS_P1,R_TPS_P2")
    value: str
    description: str
    package: str
    mfr: str
    mpn: str
    notes: str = ""
    dnp: bool = False

    @property
    def qty(self) -> int:
        return len([r.strip() for r in self.refs.split(",") if r.strip()])


PARTS: list[Part] = [
    # ── JFET input buffer ───────────────────────────────────────────────────
    Part("Q1", "MMBF170LT1G",
         "N-JFET, Idss 2–6 mA, SOT-23, capsule buffer",
         "SOT-23", "onsemi", "MMBF170LT1G"),
    Part("R_D", "22k 1%",
         "JFET drain load (VDRAIN → V_BOOST)",
         "0402", "Yageo", "RC0402FR-0722KL"),
    Part("R_S", "1k 1%",
         "JFET source degeneration",
         "0402", "Yageo", "RC0402FR-071KL"),
    Part("R_GBIAS", "10M 1%",
         "Gate bias — 200 V rated 0805 required (VGATE = V_BOOST via R_GBIAS)",
         "0805", "Vishay", "CRCW080510M0FKEA",
         notes="HV net (VGATE ≈ 72 V). Must be 200 V rated."),
    Part("C_IN", "10n 50V X7R",
         "Input coupling cap FP_CAPSULE → VGATE",
         "0402", "Murata", "GRM155R71H103KA88D"),

    # ── OPA1642 EQ + DC servo ────────────────────────────────────────────────
    Part("U1", "OPA1642AIDR",
         "Dual JFET op-amp, SOIC-8, GBW=11 MHz, EIN=5.1 nV/√Hz",
         "SOIC-8", "Texas Instruments", "OPA1642AIDR",
         notes="Section A = EQ inverting amp. Section B = DC servo integrator."),
    Part("R_IN", "10k 1%",
         "EQ input summing resistor (VSOURCE → IN-_A)",
         "0402", "Yageo", "RC0402FR-0710KL"),
    Part("R_F", "47k 1%",
         "EQ feedback resistor (OUT_A → IN-_A, K47 mode)",
         "0402", "Yageo", "RC0402FR-0747KL"),
    Part("R_SHELF", "47k 1%",
         "EQ shelf network series R (K87 de-emphasis)",
         "0402", "Yageo", "RC0402FR-0747KL"),
    Part("C_DEEMPH", "150p C0G/NP0",
         "EQ de-emphasis shelf cap (−6 dB shelf above ~22 kHz for K87)",
         "0402", "Murata", "GRM1555C1H151JA01D"),
    Part("SJ1", "SolderBridge 0Ω",
         "K47/K87 mode select — open=K47 (flat), close=K87 (de-emphasis)",
         "0402", "", "",
         notes="Populate 0Ω for K87; leave open for K47."),
    Part("R_INJ", "1M 1%",
         "Servo gate injection R (SRV_OUT → VGATE low-pass)",
         "0402", "Yageo", "RC0402FR-071ML"),
    Part("R_INT", "300k 1%",
         "Servo integrator input R (VSOURCE → IN-_B)",
         "0402", "Yageo", "RC0402FR-07300KL"),
    Part("C_INT", "10u 16V X5R",
         "Servo integrator cap (sets servo f_c ≈ 0.05 Hz)",
         "0603", "TDK", "C1608X5R1C106K080AC"),

    # ── ±15V decoupling near U1 ──────────────────────────────────────────────
    Part("C_P15_100n, C_N15_100n", "100n 25V X7R",
         "±15V HF bypass",
         "0402", "Murata", "GRM155R71E104KA88D"),
    Part("C_P15_1u, C_N15_1u", "1u 25V X5R",
         "±15V bulk decoupling near U1",
         "0603", "TDK", "C1608X5R1E105K080AC"),

    # ── LR8 pre-regulator ───────────────────────────────────────────────────
    Part("U2", "LR8K4-G",
         "HV LDO, 48V PHANTOM → 34.3V (P48V_LDO), SOT-89",
         "SOT-89", "IXYS", "LR8K4-G",
         notes="Long-lead item — order early. Vout = 1.225×(1+270k/10k) = 34.3V."),
    Part("R_LR8_1", "270k 1%",
         "LR8 Vadj divider high (P48V_LDO → LR8_ADJ)",
         "0402", "Yageo", "RC0402FR-07270KL"),
    Part("R_LR8_2", "10k 1%",
         "LR8 Vadj divider low (LR8_ADJ → GND)",
         "0402", "Yageo", "RC0402FR-0710KL"),
    Part("C_LR8_IN", "10u 100V X5R",
         "LR8 input bypass (PHANTOM = 48V)",
         "0603", "TDK", "C1608X5R2A106K080AC",
         notes="100 V rating required — PHANTOM net."),
    Part("C_LR8_OUT", "4u7 50V X5R",
         "LR8 output bypass (P48V_LDO = 34.3V)",
         "0603", "TDK", "C1608X5R1H475K080AC"),

    # ── TPS7A3901 ±15V dual LDO ─────────────────────────────────────────────
    Part("U3", "TPS7A3901DSKR",
         "Dual LDO ±15V from 34.3V, WSON-12 3×3 mm",
         "WSON-12", "Texas Instruments", "TPS7A3901DSKR"),
    Part("R_TPS_P1, R_TPS_N1", "127k 1%",
         "TPS7A3901 output voltage set resistor (high side, +15V and −15V)",
         "0402", "Yageo", "RC0402FR-07127KL",
         notes="Vout+ = 1.188×(1+127k/10k) ≈ 16.3V — trim if exact ±15V required."),
    Part("R_TPS_P2, R_TPS_N2", "10k 1%",
         "TPS7A3901 output voltage set resistor (low side)",
         "0402", "Yageo", "RC0402FR-0710KL"),
    Part("C_P15_OUT, C_N15_OUT", "10u 25V X5R",
         "TPS7A3901 output decoupling",
         "0603", "TDK", "C1608X5R1E106K080AC"),

    # ── Charge pump 48V → V_BOOST (~72V) ────────────────────────────────────
    Part("D1", "BAT54S",
         "Dual Schottky SOT-23, 1-stage Cockcroft-Walton (PHANTOM → V_BOOST)",
         "SOT-23", "Vishay", "BAT54S-E3-08"),
    Part("C_PUMP", "100n 100V X7R",
         "Charge pump capacitor",
         "0402", "Murata", "GRM155R72A104KA88D",
         notes="100 V rating required — HV pump cap."),
    Part("C_RSVR", "4u7 100V X5R",
         "V_BOOST reservoir cap",
         "0603", "TDK", "C1608X5R2A475K080AC",
         notes="100 V rating required."),
    Part("L1", "10mH 50mA",
         "LC post-filter inductor (V_BOOST ripple suppression)",
         "0805", "Murata", "LQH2MCN100K02L",
         notes="Low-DCR ≤ 8Ω, Isat ≥ 50 mA."),
    Part("C_LPF", "10u 100V X5R",
         "LC post-filter output cap (V_BOOST → BP_CAPSULE)",
         "0603", "TDK", "C1608X5R2A106K080AC",
         notes="100 V rating required."),

    # ── Output transformer (off-board, hand-soldered after reflow) ───────────
    Part("TX1", "NTE10/3",
         "Audio output transformer 1:3:10, reversed 3:1 connection, free wires",
         "Off-board", "Neutrik", "NTE10/3",
         notes="Long-lead. Hand-solder 5 leads to TH pads "
               "TX_S3H/TX_S3R/TX_S3C (3× secondary) + TX_P1/TX_P2 (1× primary) after reflow. "
               "Secure body with cable tie through SLOT1/SLOT2 NPTH holes."),
]


DFM_NOTES = [
    ("Board size",               "35 × 85 mm, 2-layer FR4 1.6 mm"),
    ("Mounting holes",           "4× M2.2 NPTH, 30 × 80 mm pattern"),
    ("Min drill (mechanical)",   "0.8 mm (capsule pads), 1.0 mm (TX/XLR TH)"),
    ("Min track / space",        "0.15/0.15 mm signal; 0.40/0.50 mm HV"),
    ("Solder mask expansion",    "0.05 mm all SMD pads"),
    ("Silkscreen clearance",     "0.12 mm from pads"),
    ("Fiducials",                "3× FID (F.Cu copper dot, 1 mm dia, 3 mm CY)"),
    ("HV clearance",             "0.5 mm Cu-to-Cu on PHANTOM/V_BOOST/BP_CAPSULE nets"),
    ("HV copper-edge clearance", "0.5 mm (IPC-2221 for 48–72 V)"),
    ("TPS7A39 WSON-12 EP",       "Exposed pad to B.Cu GND plane via thermal vias"),
    ("B.Cu GND plane",           "Full-board pour, 1 mm pullback from Edge.Cuts"),
    ("Post-reflow TH",           "NTE10/3 leads hand-soldered (5 pads); XLR wires (3 pads)"),
    ("Capsule leads",            "3× TH pad, 0.8 mm drill, 1.5 mm ring"),
    ("NPTH cable-tie slots",     "2× 2.5 mm NPTH (SLOT1, SLOT2) for transformer retention"),
]


def generate_bom():
    smd      = [p for p in PARTS if p.package != "Off-board" and not p.dnp]
    offboard = [p for p in PARTS if p.package == "Off-board"]
    dnp      = [p for p in PARTS if p.dnp]
    total_smd_qty = sum(p.qty for p in smd)

    out_csv = HERE / "txm_bom.csv"
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Refs", "Qty", "Value", "Description", "Package",
                    "Manufacturer", "MPN", "DNP", "Notes"])
        for p in PARTS:
            w.writerow([p.refs, p.qty, p.value, p.description, p.package,
                        p.mfr, p.mpn, "DNP" if p.dnp else "", p.notes])
    print(f"BOM written:  {out_csv}  ({len(PARTS)} line items, {total_smd_qty} SMD placements)")

    out_dfm = HERE / "txm_bom_dfm.txt"
    with open(out_dfm, "w") as f:
        f.write("op-txm — DFM Review\n")
        f.write("=" * 64 + "\n\n")
        f.write(f"  Total BOM line items : {len(PARTS)}\n")
        f.write(f"  SMD placements       : {total_smd_qty}\n")
        f.write(f"  Off-board (hand TH)  : {len(offboard)}\n")
        f.write(f"  DNP                  : {len(dnp)}\n\n")
        f.write("PCB / DFM parameters\n")
        f.write("-" * 64 + "\n")
        for name, spec in DFM_NOTES:
            f.write(f"  {name:<32s} {spec}\n")
        f.write("\nOff-board / hand-soldered parts\n")
        f.write("-" * 64 + "\n")
        for p in offboard:
            f.write(f"  {p.refs:<10s} {p.mpn:<20s} {p.notes[:60]}\n")
        f.write("\nLong-lead parts — order first\n")
        f.write("-" * 64 + "\n")
        f.write("  IXYS LR8K4-G        8–16 week lead time; check Mouser/Digi-Key\n")
        f.write("  Neutrik NTE10/3     check Farnell / Mouser stock\n")
        f.write("  TPS7A3901DSKR       check stock; WSON-12 may need stencil\n")
    print(f"DFM written:  {out_dfm}")


if __name__ == "__main__":
    generate_bom()
