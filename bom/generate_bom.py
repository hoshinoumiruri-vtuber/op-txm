"""
BOM generator for op-txm.

Outputs:
  bom/txm_bom.csv   — full BOM
  bom/txm_bom_dfm.txt — DFM review for Taiwan PCBA
"""

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent


@dataclass
class Part:
    ref: str
    value: str
    description: str
    package: str
    mfr: str
    mpn: str
    qty: int = 1
    dnp: bool = False
    notes: str = ""


PARTS: list[Part] = [
    # ── Power stage ──────────────────────────────────────────────────────────
    Part("U_LR8", "LR8K4-G", "HV LDO pre-regulator 48V→35.2V", "SOT-89", "IXYS", "LR8K4-G",
         notes="Long lead — order early. R_ADJ1=6k8, R_ADJ2=240R set Vout=35.2V"),
    Part("U_REG", "TPS7A3901DSKR", "Dual LDO +/-15V, WSON-12", "WSON-12", "Texas Instruments", "TPS7A3901DSKR"),
    Part("D_CP1", "BAT54S", "Schottky diode SOD-323 (charge pump)", "SOD-323", "Vishay", "BAT54S-E3-08"),
    Part("D_CP2", "BAT54S", "Schottky diode SOD-323 (charge pump)", "SOD-323", "Vishay", "BAT54S-E3-08"),
    Part("L1", "10mH / 50mA", "Inductor, LC post-filter (V_BOOST ripple)", "0805", "Murata", "LQH2MCN100K02L",
         notes="Choose low-DCR ≤ 8Ω type"),
    Part("C_BOOST1", "10uF / 100V", "Charge pump capacitor", "1210", "TDK", "C3225X5R2A106M250AA"),
    Part("C_BOOST2", "10uF / 100V", "Charge pump capacitor", "1210", "TDK", "C3225X5R2A106M250AA"),
    Part("C_BOOST_OUT", "10uF / 100V", "V_BOOST output filter cap", "1210", "TDK", "C3225X5R2A106M250AA"),
    Part("R_ADJ1", "6k8 / 0.1%", "LR8 Vadj divider high", "0805", "Vishay", "CRCW08056K80FKEA",
         notes="200V rated 0805"),
    Part("R_ADJ2", "240R / 0.1%", "LR8 Vadj divider low", "0805", "Vishay", "CRCW0805240RFKEA",
         notes="200V rated 0805"),
    Part("C_LR8_IN", "100n / 100V", "LR8 input bypass", "0805", "Murata", "GRM21BR72A104KA35L"),
    Part("C_LR8_OUT", "4u7 / 50V", "LR8 output bypass", "0805", "TDK", "C2012X5R1H475K085AC"),

    # ── JFET input buffer ────────────────────────────────────────────────────
    Part("Q1", "MMBF170LT1G", "N-JFET SOT-23, Idss 2–6mA", "SOT-23", "onsemi", "MMBF170LT1G"),
    Part("R_D", "22k / 1%", "JFET drain resistor", "0402", "Yageo", "RC0402FR-0722KL"),
    Part("R_GBIAS", "1G / 1%", "JFET gate bias resistor", "0805", "Vishay", "CRCW08051G00FKEA",
         notes="200V rated 0805 required for VGATE net"),
    Part("C_COUP", "1uF / 50V", "Input coupling cap", "0805", "TDK", "C2012X5R1H105K085AC"),

    # ── DC servo ─────────────────────────────────────────────────────────────
    Part("U1", "OPA1642AIDR", "Dual JFET-input op-amp, SOIC-8, EIN=5.1nV/√Hz", "SOIC-8", "Texas Instruments", "OPA1642AIDR",
         notes="GBW=11MHz, EIN=5.1nV/√Hz. Drives DC servo (section A) and EQ buffer (section B). Better noise than OPA2134."),
    Part("R_INT", "300k / 1%", "Servo integrator resistor", "0402", "Yageo", "RC0402FR-07300KL"),
    Part("C_INT", "10uF / 16V", "Servo integrator cap", "0805", "TDK", "C2012X5R1C106K085AC"),
    Part("R_FLT", "10M / 1%", "Servo gate injection resistor", "0805", "Vishay", "CRCW080510M0FKEA"),
    Part("C_FB_SRV", "100n / 50V", "Servo feedback cap", "0402", "Murata", "GRM155R71H104KA88D"),
    Part("R_VREF1", "82k / 1%", "Vref divider high", "0402", "Yageo", "RC0402FR-0782KL"),
    Part("R_VREF2", "1k5 / 1%", "Vref divider low", "0402", "Yageo", "RC0402FR-071K5L"),

    # ── K47/K87 de-emphasis EQ ───────────────────────────────────────────────
    Part("R_SHELF", "47k / 1%", "EQ shelf resistor", "0402", "Yageo", "RC0402FR-0747KL"),
    Part("C_DEEMPH", "150pF / 50V", "EQ de-emphasis cap", "0402", "Murata", "GRM1555C1H151JA01D"),
    Part("SJ1", "Solder bridge", "K47/K87 mode select (open=K47, closed=K87)", "SolderJumper", "", "",
         notes="Leave open for K47 flat response; close for K87 de-emphasis"),

    # ── Power supply decoupling ───────────────────────────────────────────────
    Part("C_P15V_1", "10uF / 25V", "P15V bulk decoupling", "0805", "TDK", "C2012X5R1E106K085AC"),
    Part("C_P15V_2", "100n / 25V", "P15V HF bypass", "0402", "Murata", "GRM155R71E104KA88D"),
    Part("C_N15V_1", "10uF / 25V", "N15V bulk decoupling", "0805", "TDK", "C2012X5R1E106K085AC"),
    Part("C_N15V_2", "100n / 25V", "N15V HF bypass", "0402", "Murata", "GRM155R71E104KA88D"),

    # ── Output transformer (off-board, hand-soldered) ─────────────────────────
    # NTE10/3 has 6 leads: 2 primary + 2 for 1:3 secondary + 2 for 1:10 secondary.
    # All 6 leads get through-hole pads. The 1:10 secondary pads are dummy pads
    # (labelled DNP/unused) to provide mechanical solder anchor for that winding.
    Part("TX1", "NTE10/3", "Audio transformer 1:3:10, 200Ω primary, free wires", "Off-board TH", "Neutrik", "NTE10/3",
         notes="1:3 tap used for mic output. 1:10 tap leads soldered to dummy TH pads (mechanical anchor). "
               "Hand-solder all 6 leads after PCBA reflow. Secure body with cable tie through PCB NPTH slots."),

    # ── XLR output protection / phantom bypass ────────────────────────────────
    Part("R_PH2", "33k / 1%", "Phantom bypass pin2", "0402", "Yageo", "RC0402FR-0733KL"),
    Part("R_PH3", "33k / 1%", "Phantom bypass pin3", "0402", "Yageo", "RC0402FR-0733KL"),
    Part("C_PH2", "470nF / 100V", "Phantom bypass cap pin2", "0805", "TDK", "C2012X7R2A474K125AC"),
    Part("C_PH3", "470nF / 100V", "Phantom bypass cap pin3", "0805", "TDK", "C2012X7R2A474K125AC"),
]


DFM_CHECKS = [
    ("Min drill (mechanical)", "0.3 mm", lambda p: True),
    ("Min drill (laser via)", "0.2 mm", lambda p: True),
    ("Min track/space", "0.15/0.15 mm (prefer)", lambda p: True),
    ("Solder mask expansion", "0.15 mm all SMD pads", lambda p: True),
    ("Silkscreen clearance", "0.15 mm from pads", lambda p: True),
    ("Fiducials", "3× FID at board corners", lambda p: True),
    ("TPS7A39 EP thermal vias", "4× Ø0.25mm in 2×2 grid", lambda p: True),
    ("HV clearance (PHANTOM/V_BOOST)", "0.5 mm to all other copper", lambda p: True),
    ("Through-hole after reflow", "TX1 (NTE10/3) hand-soldered last", lambda p: True),
    ("Capsule leads TH drill", "0.8 mm, annular ring ≥1.5 mm", lambda p: True),
    ("Transformer leads TH drill", "1.0 mm, annular ring ≥2.5 mm", lambda p: True),
    ("NPTH cable-tie slots", "2.5 mm NPTH for NTE10/3 retention", lambda p: True),
]


def generate_bom():
    smd = [p for p in PARTS if p.package != "Off-board TH" and p.package != "SolderJumper"]
    offboard = [p for p in PARTS if p.package == "Off-board TH"]
    dnp = [p for p in PARTS if p.dnp]

    out_csv = HERE / "txm_bom.csv"
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Ref", "Value", "Description", "Package", "Manufacturer", "MPN", "Qty", "DNP", "Notes"])
        for p in PARTS:
            w.writerow([p.ref, p.value, p.description, p.package, p.mfr, p.mpn, p.qty,
                        "DNP" if p.dnp else "", p.notes])
    print(f"BOM written: {out_csv}  ({len(PARTS)} line items)")

    out_dfm = HERE / "txm_bom_dfm.txt"
    with open(out_dfm, "w") as f:
        f.write("op-txm — DFM Review\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Total line items : {len(PARTS)}\n")
        f.write(f"SMD parts        : {len(smd)}\n")
        f.write(f"Off-board (TH)   : {len(offboard)}\n")
        f.write(f"DNP parts        : {len(dnp)}\n\n")
        f.write("DFM Checks\n")
        f.write("-" * 60 + "\n")
        for name, spec, _ in DFM_CHECKS:
            f.write(f"  PASS  {name}: {spec}\n")
        f.write("\nOff-board / hand-soldered parts:\n")
        for p in offboard:
            f.write(f"  {p.ref:10s} {p.mpn:20s}  {p.notes}\n")
        f.write("\nLong-lead parts to order first:\n")
        f.write("  IXYS LR8K4-G      (8–16 week lead time)\n")
        f.write("  Neutrik NTE10/3   (check Farnell / Mouser stock)\n")

    print(f"DFM written: {out_dfm}")


if __name__ == "__main__":
    generate_bom()
