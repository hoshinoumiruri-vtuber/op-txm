"""
Transformer Output Stage Simulation
=====================================
Models the Neutrik NTE10/3 output transformer driven by the JFET buffer +
de-emphasis EQ stage.

Advantages of transformer-balanced output:
  - True galvanic isolation between capsule/preamp and balanced output
  - Passive common-mode rejection (no op-amp required in output path)
  - Inherent ESD and RFI robustness on the XLR connector

Connection — reversed 3:1 (standard Neumann/AKG practice)
----------------------------------------------------------
    EQ op-amp → DCR_sec (270Ω) → 3× winding (720H) ─┐
                                                      │ coupled
                              XLR balanced ← 1× winding (80H) ← DCR_pri (30Ω)

  Op-amp drives the HIGH-turn (3×) winding.
  XLR output comes from the LOW-turn (1×) winding.
  Benefits:
    · Op-amp load : 1200 Ω × 9 = 10.8 kΩ (very easy, full headroom)
    · Zout at XLR : ≈ 61 Ω  (DCR_pri dominated — excellent cable drive)
    · Voltage      : V_xlr = V_eq / 3  (−9.5 dB)
    · HF corner    : ~390 kHz (leakage at 1× output winding is 9× smaller)

Neutrik NTE10/3 parameters
---------------------------
  Physical turns ratio  : 1:3:10
  Selected tap          : 1:3  →  driven winding = 3× (secondary), output = 1× (primary)
  Primary (1×) inductance: ~80 H (community measurement; verify at bench)
  Secondary (3×) inductance: 720 H  (= 80 × 3²)
  Leakage inductance    : ~0.5 mH referred to 1× winding  (TBD; measure at bench)
  DCR primary (1×)      : ~30 Ω  (TBD)
  DCR secondary (3×)    : ~270 Ω  (= 30 × 9, TBD)

Analytical model
----------------
  T-model: source → (R_src + DCR_in + jω×L_leak_in) → node A
           At A: magnetising L_in (720H) in shunt, and reflected load n²×(DCR_out+R_load)
           Output = V_A / n × R_load / (R_load + DCR_out)

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
# Physical turns ratio 1:3 (selected tap). Connection is REVERSED:
#   driven winding = 3× (secondary), output winding = 1× (primary).
N_TURNS = 3.0          # voltage ratio of driven:output winding (3:1 step-down)
L_PRI_H = 80.0         # 1× winding inductance [H] — community measurement; verify at bench
L_SEC_H = L_PRI_H * N_TURNS ** 2   # = 720 H  (3× driven winding)
L_LEAK_H = 0.0005      # leakage inductance referred to 1× (output) winding [H] — TBD
DCR_PRI_OHM = 30.0     # 1× winding DCR [Ω] — output side; TBD at bench
DCR_SEC_OHM = 270.0    # 3× winding DCR [Ω] — input side; = 30 × n² = 270 Ω estimated

# ── Circuit parameters ────────────────────────────────────────────────────────
R_SRC_OHM = 100.0      # op-amp output impedance after EQ [Ω] (approximate)
R_LOAD_OHM = 1200.0    # balanced XLR load (600 Ω per leg × 2) [Ω]
V_SIG = 0.1            # AC signal amplitude for sweep [V]


def lf_corner_hz(r_src, dcr_in, l_in):
    """LF −3 dB corner: driven by magnetising inductance of the 3× input winding."""
    return (r_src + dcr_in) / (2 * np.pi * l_in)


def hf_corner_hz(r_load, dcr_out, l_leak_out):
    """HF −3 dB corner: leakage at 1× output winding forms LPF with load."""
    return (r_load + dcr_out) / (2 * np.pi * l_leak_out)


def analytical_response(freqs, r_src, r_load, l_in, l_leak_out, dcr_in, dcr_out, n):
    """
    Reversed 3:1 T-model. Source drives n× winding (l_in); output from 1× winding.
      n = 3, l_in = L_SEC_H = 720 H, l_leak_out = L_LEAK_H = 0.5 mH
    """
    omega = 2 * np.pi * freqs
    jw = 1j * omega

    l_leak_in = l_leak_out * n ** 2         # leakage referred to input (n×) winding
    z_series = r_src + dcr_in + jw * l_leak_in

    z_mag = jw * l_in
    z_load_ref = (dcr_out + r_load) * n ** 2   # load reflected to input winding
    z_shunt = z_mag * z_load_ref / (z_mag + z_load_ref)

    v_a = V_SIG * z_shunt / (z_series + z_shunt)   # voltage at node A
    v_out = v_a / n * r_load / (r_load + dcr_out)   # step down, then DCR_out divider

    gain_db = 20 * np.log10(np.abs(v_out) / V_SIG + 1e-12)
    phase_deg = np.angle(v_out / V_SIG, deg=True)
    return gain_db, phase_deg


def run():
    freqs = np.logspace(np.log10(10), np.log10(100_000), 500)

    lf = lf_corner_hz(R_SRC_OHM, DCR_SEC_OHM, L_SEC_H)
    hf = hf_corner_hz(R_LOAD_OHM, DCR_PRI_OHM, L_LEAK_H)
    # Mid-band gain: (1/n) × R_load / (R_load + DCR_out + reflected R_src/DCR_in)
    r_src_ref = (R_SRC_OHM + DCR_SEC_OHM) / N_TURNS ** 2
    passband_gain_db = 20 * np.log10(
        (1 / N_TURNS) * R_LOAD_OHM / (R_LOAD_OHM + DCR_PRI_OHM + r_src_ref) + 1e-12
    )
    zout_xlr = (R_SRC_OHM + DCR_SEC_OHM) / N_TURNS ** 2 + DCR_PRI_OHM

    print("Neutrik NTE10/3 — Analytical Response (reversed 3:1, estimated values)")
    print(f"  Connection        : reversed 3:1 — op-amp drives 3× winding, XLR from 1× winding")
    print(f"  LF −3 dB corner   : {lf:.3f} Hz  (Ldriven = {L_SEC_H:.0f} H)")
    print(f"  HF −3 dB corner   : {hf/1e3:.1f} kHz  (Lleak = {L_LEAK_H*1e3:.2f} mH at 1× output)")
    print(f"  Passband gain     : {passband_gain_db:.2f} dB  (= −9.5 dB step-down + DCR losses)")
    print(f"  Zout at XLR       : {zout_xlr:.0f} Ω  (excellent cable drive)")
    print()
    print("NOTE: L_LEAK_H, DCR_PRI_OHM, DCR_SEC_OHM are estimates — measure at bench.")

    gain_db, phase_deg = analytical_response(
        freqs, R_SRC_OHM, R_LOAD_OHM, L_SEC_H, L_LEAK_H,
        DCR_SEC_OHM, DCR_PRI_OHM, N_TURNS,
    )

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    ax1.semilogx(freqs, gain_db, color="steelblue", linewidth=1.5)
    ax1.axvline(lf, color="red", linestyle="--", linewidth=0.8, label=f"LF corner {lf:.1f} Hz")
    ax1.axvline(hf, color="orange", linestyle="--", linewidth=0.8, label=f"HF corner {hf:.0f} Hz")
    ax1.set_ylabel("Gain (dB)")
    ax1.set_title("NTE10/3 Transformer — Reversed 3:1 Connection (estimated parameters)")
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
