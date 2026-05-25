"""
Transformer Output Stage Simulation
=====================================
Models the Neutrik NTE10/3 output transformer driven by the JFET buffer +
de-emphasis EQ stage.

The transformer replaces the TLM active balanced output used in the OCM
design.  Advantages:
  - True galvanic isolation between capsule/preamp and balanced output
  - Passive common-mode rejection (no op-amp required in output path)
  - Inherent ESD and RFI robustness on the XLR connector

Topology
---------
    JFET output --> [EQ] --> Rin --> Transformer primary --> secondary --> XLR out
                                          |
                                         GND

Neutrik NTE10/3 parameters (update from datasheet):
  Turns ratio n      : TBD (measure or from datasheet)
  Primary inductance : TBD H
  Leakage inductance : TBD H (referred to primary)
  DCR primary        : TBD Ω
  DCR secondary      : TBD Ω
  Max level          : TBD dBu

SPICE model approach
--------------------
  Ideal transformer core: coupled inductors L1 (primary) and L2 (secondary)
  with coupling coefficient k ≈ 1 - Lleak/Lprimary.

  L2 = L1 * n^2  (where n = Ns/Np, step-up ratio)

  The model captures:
    - LF roll-off from finite primary inductance (f_low = R_src / (2π Lpri))
    - HF roll-off from leakage inductance (f_high = R_load / (2π Lleak*n^2))
    - Winding resistance losses

Usage
-----
    .venv/bin/python sim/tx_output.py

Outputs
-------
  - Frequency response plot (gain and phase, 20 Hz – 20 kHz)
  - Printed LF and HF -3 dB corner estimates
  - assets/sim_results/tx_frequency_response.png
"""

import subprocess
import tempfile
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

# ── NTE10/3 transformer parameters ───────────────────────────────────────────
# Turns ratio and impedance: confirmed from Neutrik / Farnell datasheet.
# Primary inductance: ~80 H from GroupDIY community bench measurement.
# DCR and leakage: not published; measure at bench with LCR meter and update.
#
# Using 1:3 secondary tap:
#   Primary  200 Ω rated,  secondary 1.8 kΩ rated
#   Voltage step-up: 3×  (+9.5 dB)
#   Impedance ratio: n² = 9
#
# Frequency spec from distributor: 40 Hz – 20 kHz ±0.5 dB
N_TURNS = 3.0        # secondary/primary voltage ratio (1:3 tap)
L_PRI_H = 80.0       # primary inductance [H] — community measurement; verify at bench
L_LEAK_H = 0.0005    # leakage inductance referred to primary [H] — TBD; chosen to give ~20kHz HF corner
DCR_PRI_OHM = 30.0   # primary winding DCR [Ω] — TBD; measure at bench
DCR_SEC_OHM = 270.0  # secondary winding DCR [Ω] — TBD; scaled by n²=9 from primary estimate

# ── Circuit parameters ────────────────────────────────────────────────────────
R_SRC_OHM = 100.0    # source impedance (JFET output after EQ)
R_LOAD_OHM = 1200.0  # standard balanced load (600 Ω per leg = 1200 Ω differential)
V_SIG = 0.1          # AC signal level for AC sweep [V]


def lf_corner_hz(r_src, dcr_pri, l_pri):
    """LF -3 dB corner from finite primary inductance."""
    r_total = r_src + dcr_pri
    return r_total / (2 * np.pi * l_pri)


def hf_corner_hz(r_load, dcr_sec, l_leak, n):
    """HF -3 dB corner from leakage inductance (referred to secondary)."""
    l_leak_sec = l_leak * n ** 2
    r_total = r_load + dcr_sec
    return r_total / (2 * np.pi * l_leak_sec)


def analytical_response(freqs, r_src, r_load, l_pri, l_leak, dcr_pri, dcr_sec, n):
    """
    Compute voltage gain magnitude (dB) across frequency analytically.
    Two-pole bandpass: HPF from Lpri, LPF from Lleakage.
    """
    omega = 2 * np.pi * freqs
    jw = 1j * omega

    # Referred-to-primary load
    r_load_pri = r_load / n ** 2 + dcr_sec / n ** 2

    # Primary circuit: voltage divider between (R_src + DCR_pri + jw*Lleak) and (jw*Lpri || R_load_pri)
    z_leak = DCR_PRI_OHM + jw * l_leak
    z_mag = jw * l_pri * r_load_pri / (jw * l_pri + r_load_pri)
    z_total = z_leak + r_src + z_mag

    v_pri = V_SIG * z_mag / z_total
    v_sec = v_pri * n  # step up by turns ratio

    gain_db = 20 * np.log10(np.abs(v_sec) / V_SIG + 1e-12)
    phase_deg = np.angle(v_sec / V_SIG, deg=True)
    return gain_db, phase_deg


def run():
    freqs = np.logspace(np.log10(10), np.log10(100_000), 500)

    lf = lf_corner_hz(R_SRC_OHM, DCR_PRI_OHM, L_PRI_H)
    hf = hf_corner_hz(R_LOAD_OHM, DCR_SEC_OHM, L_LEAK_H, N_TURNS)
    passband_gain_db = 20 * np.log10(
        N_TURNS * R_LOAD_OHM / (R_LOAD_OHM + DCR_SEC_OHM + (R_SRC_OHM + DCR_PRI_OHM) / N_TURNS ** 2)
        + 1e-12
    )

    print("Neutrik NTE10/3 — Analytical Response (placeholder values)")
    print(f"  Turns ratio       : {N_TURNS}:1")
    print(f"  LF -3 dB corner   : {lf:.2f} Hz")
    print(f"  HF -3 dB corner   : {hf:.0f} Hz")
    print(f"  Passband gain     : {passband_gain_db:.2f} dB  (ref 1 Vpeak in)")
    print()
    print("NOTE: all transformer parameters are placeholders.")
    print("Update N_TURNS, L_PRI_H, L_LEAK_H, DCR_PRI_OHM, DCR_SEC_OHM")
    print("from the NTE10/3 datasheet before interpreting these results.")

    gain_db, phase_deg = analytical_response(
        freqs, R_SRC_OHM, R_LOAD_OHM, L_PRI_H, L_LEAK_H,
        DCR_PRI_OHM, DCR_SEC_OHM, N_TURNS,
    )

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    ax1.semilogx(freqs, gain_db, color="steelblue", linewidth=1.5)
    ax1.axvline(lf, color="red", linestyle="--", linewidth=0.8, label=f"LF corner {lf:.1f} Hz")
    ax1.axvline(hf, color="orange", linestyle="--", linewidth=0.8, label=f"HF corner {hf:.0f} Hz")
    ax1.set_ylabel("Gain (dB)")
    ax1.set_title("NTE10/3 Transformer Output — Frequency Response (placeholder values)")
    ax1.legend(fontsize=8)
    ax1.grid(True, which="both", alpha=0.3)
    ax1.set_ylim(-20, 5)

    ax2.semilogx(freqs, phase_deg, color="darkorange", linewidth=1.5)
    ax2.set_ylabel("Phase (°)")
    ax2.set_xlabel("Frequency (Hz)")
    ax2.grid(True, which="both", alpha=0.3)
    ax2.set_xlim(10, 100_000)

    out_path = Path(__file__).parent.parent / "assets" / "sim_results" / "tx_frequency_response.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    print(f"\nPlot saved → {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    run()
