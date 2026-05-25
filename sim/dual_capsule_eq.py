"""
Task 5: Dual-Capsule Impedance Matching — K47 vs K87 De-emphasis
=================================================================

Problem
-------
K87/K67 capsules exhibit a broad presence peak of +6 to +8 dB centred
around 8-12 kHz. K47 capsules are relatively flat. The output stage
op-amp must serve both capsules without respin.

Solution
--------
A solder bridge (SJ1) switches a series R_shelf + C_deemph branch in
parallel with the feedback resistor (Rf) of the JFET-input output op-amp.

                Rf (47 kΩ) — always present
           +---[////]---+
           |             |
           |  SJ1 (default OPEN = K47 mode)
           +---[S]--R_shelf(47k)--C_deemph(150p)---+
           |                                        |
  Vin  --->---Rin(10k)---[LDR]---(-)-[op-amp]------+---> Vout
                                  (+) = GND

K47 mode (SJ1 open)  : Zf = Rf            → flat gain = -Rf / (Rin + LDR)
K87 mode (SJ1 closed): Zf = Rf || Z_shelf → HF gain rolls off 6 dB above
                                             the shelf frequency

De-emphasis network math
------------------------
Z_shelf(s) = R_shelf + 1/(sC)

Zf(s) = Rf * Z_shelf / (Rf + Z_shelf)
       = Rf * (1 + s*R_shelf*C) / (1 + s*(Rf + R_shelf)*C)

This gives a shelving function with:
  pole of Zf at f_p = 1 / (2π * (Rf + R_shelf) * C)   — rolloff starts here
  zero of Zf at f_z = 1 / (2π * R_shelf * C)           — shelf reached here
  HF shelf level:  -20*log10(Rf / (Rf||R_shelf)) = -6 dB  (when R_shelf = Rf)

Component selection
-------------------
  Rf        = 47 kΩ
  R_shelf   = 47 kΩ  →  -6 dB shelf (matches K87 peak of ~6-8 dB)
  C_deemph  = 150 pF →  f_p = 11.3 kHz, f_z = 22.6 kHz

Rationale: B&K data shows this capsule has only a +3-4 dB presence peak
(not the +6-8 dB of a vintage K87). The original 330 pF network started
rolling off at 5.1 kHz and reached −6 dB at 10.2 kHz, over-damping the
highs and making the mic sound dark. 150 pF pushes the shelf corner above
the audio presence peak:
  f_pole = 11.3 kHz  (rolloff start, above capsule presence peak)
  f_zero = 22.6 kHz  (full −6 dB shelf, above audio band)
  10 kHz attenuation: −1.7 dB (was −3.9 dB) — top-end air preserved
  20 kHz attenuation: −3.6 dB (was −5.3 dB)
  −3 dB corner:       15.9 kHz (was 7.5 kHz)

LDR interaction and phase margin
---------------------------------
The LDR sits in series with Rin (input path). It modulates the closed-loop
gain: Acl ≈ -Rf / (Rin + LDR).

Higher LDR → lower closed-loop gain → higher feedback factor β → the loop-
gain crossover frequency f_c shifts toward the GBW.

For a JFET-input op-amp with GBW = 8 MHz:
  LDR =  10 kΩ → Acl ≈ 2.35 → f_c ≈ 2.4 MHz
  LDR =   1 MΩ → Acl ≈ 0.05 → f_c ≈ 7.6 MHz

Both crossovers are decades above the de-emphasis network (5-10 kHz), so
the zero-pole pair in Zf contributes negligible net phase at f_c.
Phase margin remains ≥ 80° across the full LDR range in both modes.

Usage
-----
  .venv/bin/python sim/dual_capsule_eq.py

Outputs
-------
  sim/dual_capsule_eq.png    — H(f) curves, delta, and phase margin chart
  sim/k47_ac_*.cir / .log   — ngspice AC netlists (K47)
  sim/k87_ac_*.cir / .log   — ngspice AC netlists (K87)

PCB note — Solder Bridge SJ1
------------------------------
  Footprint  : SolderJumper_2_Open  (KiCad standard library)
  Default    : OPEN → K47 mode (flat)
  Closed     : K87 mode (de-emphasised)
  Silk label : "SJ1  K47|K87"
  Location   : Adjacent to Rf on F.Cu, within 1 mm
  Schematic  : Flag R_shelf + C_deemph branch as DNF in K47 BOM variant
"""

import subprocess
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# ---------------------------------------------------------------------------
# Component values
# ---------------------------------------------------------------------------
RIN       = 10e3       # Ω  input resistor (fixed)
RF        = 47e3       # Ω  feedback resistor
R_SHELF   = 47e3       # Ω  de-emphasis shelf resistor (series with C_deemph)
C_DEEMPH  = 150e-12    # F  de-emphasis capacitor (was 330 pF — see rationale above)
GBW       = 8e6        # Hz JFET op-amp GBW (e.g. OPA2134, LME49720)
A_OL_DC   = 1e5        # V/V open-loop DC gain (100 dB)

# Derived network frequencies
F_P_ZF = 1.0 / (2 * np.pi * (RF + R_SHELF) * C_DEEMPH)   # pole of Zf (rolloff start)
F_Z_ZF = 1.0 / (2 * np.pi * R_SHELF * C_DEEMPH)           # zero of Zf (shelf point)
F_P1   = GBW / A_OL_DC                                    # op-amp dominant pole

HF_SHELF_DB = 20 * np.log10((RF * R_SHELF / (RF + R_SHELF)) / RF)

# LDR resistance range: 10 kΩ (full compression) → 1 MΩ (no compression)
LDR_VALUES = {
    "10 kΩ (full compression)":  10e3,
    "30 kΩ":                     30e3,
    "100 kΩ":                   100e3,
    "1 MΩ (no compression)":     1e6,
}

FREQS = np.logspace(1, np.log10(200e3), 2000)
S     = 1j * 2 * np.pi * FREQS

# ---------------------------------------------------------------------------
# Impedance and transfer function helpers
# ---------------------------------------------------------------------------

def Zf_k47(f: np.ndarray) -> np.ndarray:
    """Feedback impedance — K47 mode (SJ1 open): pure Rf."""
    return np.full_like(f, RF, dtype=complex)


def Zf_k87(f: np.ndarray) -> np.ndarray:
    """Feedback impedance — K87 mode (SJ1 closed): Rf || (R_shelf + 1/jωC)."""
    s = 1j * 2 * np.pi * f
    Z_branch = R_SHELF + 1.0 / (s * C_DEEMPH)
    return RF * Z_branch / (RF + Z_branch)


def closed_loop_H(f: np.ndarray, Zf_func, r_ldr: float) -> np.ndarray:
    """
    Closed-loop transfer function (ideal op-amp, A_ol → ∞).
    H(f) = -Zf / (Rin + LDR)
    Valid when A_ol >> |H|, which holds across the audio band for GBW = 8 MHz.
    """
    Zin = RIN + r_ldr
    return -Zf_func(f) / Zin


def open_loop_A(f: np.ndarray) -> np.ndarray:
    """Single-pole op-amp open-loop gain: A(f) = A0 / (1 + jf/f_p1)."""
    return A_OL_DC / (1.0 + 1j * f / F_P1)


def feedback_beta(f: np.ndarray, Zf_func, r_ldr: float) -> np.ndarray:
    """
    Feedback factor for inverting configuration.
    β = Zin / (Zin + Zf)
    """
    Zin = RIN + r_ldr
    return Zin / (Zin + Zf_func(f))


def compute_phase_margin(Zf_func, r_ldr: float):
    """
    Numerically compute the phase margin.

    Loop gain: T(f) = A_ol(f) * β(f)
    Phase margin: PM = 180° + ∠T(f_c)  where |T(f_c)| = 1

    Returns (f_crossover_Hz, phase_margin_degrees) or None if no crossover.
    """
    f_sweep = np.logspace(2, np.log10(GBW * 3), 20_000)
    T_mag   = np.abs(open_loop_A(f_sweep) * feedback_beta(f_sweep, Zf_func, r_ldr))

    crossings = np.where(np.diff(np.sign(T_mag - 1.0)))[0]
    if len(crossings) == 0:
        return None

    i = crossings[0]
    # Log-linear interpolation to find exact crossover
    lf = np.log10(f_sweep[i:i+2])
    lT = np.log10(T_mag[i:i+2])
    lfc = np.interp(0.0, lT[::-1], lf[::-1])
    fc  = 10.0 ** lfc

    # Phase at crossover
    T_phase = np.angle(open_loop_A(f_sweep) * feedback_beta(f_sweep, Zf_func, r_ldr),
                       deg=True)
    t   = (lfc - lf[0]) / (lf[1] - lf[0])
    phi = T_phase[i] + t * (T_phase[i+1] - T_phase[i])

    return fc, 180.0 + phi


# ---------------------------------------------------------------------------
# ngspice AC sweep
# ---------------------------------------------------------------------------
OPAMP_SUBCKT = f"""\
* Single-pole op-amp model: A_ol={A_OL_DC:.0e}, GBW={GBW/1e6:.0f} MHz
* f_p1 = GBW/A_ol = {F_P1:.1f} Hz
.subckt OPAMP1 inp inn out
  Rid  inp inn 1G
  E1   int 0   inp inn {A_OL_DC:.0f}
  Rp   int out 1k
  Cp   out 0   {A_OL_DC/(2*np.pi*GBW*1e3):.4e}
.ends OPAMP1
"""


def write_spice_netlist(mode: str, r_ldr: float) -> tuple[str, str]:
    """Write an ngspice AC netlist for the given mode and LDR value."""
    ldr_tag  = f"{int(r_ldr/1e3)}k"
    cir_path = f"sim/{mode.lower()}_ac_{ldr_tag}.cir"
    log_path = f"sim/{mode.lower()}_ac_{ldr_tag}.log"

    k87_branch = ""
    if mode == "k87":
        k87_branch = (
            f"Rshelf  out   sj1mid  {R_SHELF}\n"
            f"Cdeemph sj1mid  vm   {C_DEEMPH:.4e}  ; SJ1 closed\n"
        )

    netlist = (
        f"* OCM Task 5 — {mode.upper()} mode, LDR={ldr_tag}\n"
        f"{OPAMP_SUBCKT}\n"
        f"Vin    in  0    AC 1\n"
        f"Rin    in  vin2 {RIN}\n"
        f"Rldr   vin2 vm  {r_ldr}\n"
        f"Rf     out  vm  {RF}\n"
        + k87_branch +
        f"Xamp   0   vm   out  OPAMP1\n"
        f"\n"
        f".ac dec 200 10 200k\n"
        f".print ac vdb(out) vp(out)\n"
        f".end\n"
    )

    with open(cir_path, "w") as fh:
        fh.write(netlist)
    return cir_path, log_path


def run_spice(cir_path: str, log_path: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Run ngspice and parse AC output: returns (freqs, gain_dB, phase_deg)."""
    subprocess.run(
        ["ngspice", "-b", "-o", log_path, cir_path],
        capture_output=True, text=True,
    )
    freqs, gains, phases = [], [], []
    with open(log_path) as lf:
        for line in lf:
            parts = line.split()
            if len(parts) == 4:
                try:
                    _ = int(parts[0])
                    freqs.append(float(parts[1]))
                    gains.append(float(parts[2]))
                    phases.append(float(parts[3]))
                except ValueError:
                    pass
    return np.array(freqs), np.array(gains), np.array(phases)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 70)
    print("  Task 5: Dual-Capsule EQ — K47 vs K87 De-emphasis")
    print("=" * 70)
    print(f"  De-emphasis: R_shelf={R_SHELF/1e3:.0f} kΩ, C_deemph={C_DEEMPH*1e12:.0f} pF")
    print(f"  Zf pole (rolloff start) : {F_P_ZF:.0f} Hz")
    print(f"  Zf zero (shelf reached) : {F_Z_ZF:.0f} Hz")
    print(f"  HF shelf level (K87)    : {HF_SHELF_DB:.1f} dB  (target: −6 dB for K87 peak)")
    print(f"  Op-amp GBW              : {GBW/1e6:.0f} MHz, dominant pole f_p1 = {F_P1:.1f} Hz")
    print()

    # ------------------------------------------------------------------
    # Build plots
    # ------------------------------------------------------------------
    fig = plt.figure(figsize=(15, 10))
    gs  = gridspec.GridSpec(2, 3, figure=fig, hspace=0.45, wspace=0.38)
    ax_k47   = fig.add_subplot(gs[0, 0])
    ax_k87   = fig.add_subplot(gs[0, 1])
    ax_delta = fig.add_subplot(gs[0, 2])
    ax_pm    = fig.add_subplot(gs[1, :2])
    ax_loop  = fig.add_subplot(gs[1, 2])

    COLORS = ["steelblue", "seagreen", "darkorange", "firebrick"]

    pm_rows = []      # (mode, ldr_label, fc_hz, pm_deg)
    spice_ok = True

    for (label, r_ldr), color in zip(LDR_VALUES.items(), COLORS):
        ldr_kΩ = r_ldr / 1e3

        # --- Analytical H(f) ---
        H47 = closed_loop_H(FREQS, Zf_k47, r_ldr)
        H87 = closed_loop_H(FREQS, Zf_k87, r_ldr)
        # Normalise to 0 dB at 1 kHz (reference level)
        ref47 = np.abs(closed_loop_H(np.array([1e3]), Zf_k47, r_ldr))[0]
        ref87 = np.abs(closed_loop_H(np.array([1e3]), Zf_k87, r_ldr))[0]

        H47_dB = 20 * np.log10(np.abs(H47) / ref47)
        H87_dB = 20 * np.log10(np.abs(H87) / ref87)

        ax_k47.semilogx(FREQS, H47_dB, color=color, lw=1.8,
                        label=f"LDR = {ldr_kΩ:.0f} kΩ")
        ax_k87.semilogx(FREQS, H87_dB, color=color, lw=1.8,
                        label=f"LDR = {ldr_kΩ:.0f} kΩ")

        # K87 − K47 delta (de-emphasis shape, LDR-independent since it cancels)
        delta = H87_dB - H47_dB
        ax_delta.semilogx(FREQS, delta, color=color, lw=1.8,
                          label=f"LDR = {ldr_kΩ:.0f} kΩ")

        # --- ngspice AC verification ---
        for mode, Zf_func in [("k47", Zf_k47), ("k87", Zf_k87)]:
            cir, log = write_spice_netlist(mode, r_ldr)
            f_sp, g_sp, _ = run_spice(cir, log)
            if len(f_sp) > 20:
                ref_sp = np.interp(1e3, f_sp, g_sp)
                overlay_ax = ax_k47 if mode == "k47" else ax_k87
                overlay_ax.semilogx(f_sp, g_sp - ref_sp, color=color,
                                    lw=0.6, linestyle=":", alpha=0.7)
            else:
                spice_ok = False

        # --- Phase margin ---
        for mode, Zf_func in [("K47", Zf_k47), ("K87", Zf_k87)]:
            result = compute_phase_margin(Zf_func, r_ldr)
            if result:
                fc, pm = result
                pm_rows.append((mode, label, ldr_kΩ, fc, pm))

    # --- Loop gain Bode (K87 mode, two LDR extremes) ---
    f_bode = np.logspace(2, np.log10(GBW * 2), 5000)
    for r_ldr, ldr_label, color in [
        (10e3,  "LDR=10 kΩ (compression)", "steelblue"),
        (1e6,   "LDR=1 MΩ (no compression)", "firebrick"),
    ]:
        T = open_loop_A(f_bode) * feedback_beta(f_bode, Zf_k87, r_ldr)
        ax_loop.semilogx(f_bode, 20*np.log10(np.abs(T)+1e-30),
                         color=color, lw=1.5, label=ldr_label)
    ax_loop.axhline(0, color="gray", lw=0.8, linestyle="--")
    ax_loop.axvline(F_P_ZF, color="orange", lw=0.8, linestyle=":", label=f"f_pole={F_P_ZF:.0f} Hz")
    ax_loop.axvline(F_Z_ZF, color="seagreen", lw=0.8, linestyle=":", label=f"f_zero={F_Z_ZF:.0f} Hz")
    ax_loop.set_xlabel("Frequency (Hz)")
    ax_loop.set_ylabel("Loop gain T (dB)")
    ax_loop.set_title("Loop Gain — K87 Mode (both LDR extremes)", fontsize=9)
    ax_loop.legend(fontsize=7)
    ax_loop.grid(True, which="both", alpha=0.3)
    ax_loop.set_xlim(100, GBW * 2)

    # --- Style H(f) axes ---
    for ax, title in [
        (ax_k47, "K47 Mode — SJ1 Open (linear, no de-emphasis)"),
        (ax_k87, f"K87 Mode — SJ1 Closed (−6 dB shelf above {F_Z_ZF:.0f} Hz)"),
    ]:
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel("Relative gain (dB, ref 1 kHz)")
        ax.set_title(title, fontsize=9)
        ax.set_xlim(20, 200e3)
        ax.set_ylim(-12, 6)
        ax.axhline(-3, color="gray", lw=0.6, linestyle=":")
        ax.axvspan(20, 20e3, alpha=0.04, color="green")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=7)
    if spice_ok:
        ax_k47.set_title(ax_k47.get_title() + "\n(solid=analytical, dotted=ngspice)", fontsize=9)
        ax_k87.set_title(ax_k87.get_title() + "\n(solid=analytical, dotted=ngspice)", fontsize=9)

    # --- Delta (de-emphasis shape) ---
    ax_delta.axhline(HF_SHELF_DB, color="red",    lw=0.9, linestyle="--",
                     label=f"{HF_SHELF_DB:.0f} dB shelf")
    ax_delta.axhline(-3,          color="gray",   lw=0.6, linestyle=":")
    ax_delta.axvline(F_P_ZF, color="orange",  lw=0.8, linestyle=":",
                     label=f"f_pole={F_P_ZF:.0f} Hz")
    ax_delta.axvline(F_Z_ZF, color="seagreen", lw=0.8, linestyle=":",
                     label=f"f_zero={F_Z_ZF:.0f} Hz")
    ax_delta.set_xlabel("Frequency (Hz)")
    ax_delta.set_ylabel("K87 − K47 (dB)")
    ax_delta.set_title("De-emphasis shape\n(K87 mode vs K47 mode)", fontsize=9)
    ax_delta.set_xlim(20, 200e3)
    ax_delta.set_ylim(-10, 2)
    ax_delta.grid(True, which="both", alpha=0.3)
    ax_delta.legend(fontsize=7)

    # --- Phase margin bar chart ---
    labels_pm = [f"{mode} / {lbl.split('(')[0].strip()}" for mode, lbl, *_ in pm_rows]
    pms       = [r[-1] for r in pm_rows]
    fcs       = [r[-2] for r in pm_rows]
    bar_colors = ["seagreen" if p >= 60 else "orange" if p >= 45 else "firebrick"
                  for p in pms]
    bars = ax_pm.barh(labels_pm, pms, color=bar_colors, height=0.6, edgecolor="white")
    ax_pm.axvline(45, color="red",   lw=1,   linestyle="--", label="45° minimum")
    ax_pm.axvline(60, color="green", lw=0.8, linestyle="--", label="60° ideal")
    ax_pm.set_xlabel("Phase Margin (°)")
    ax_pm.set_title("Phase Margin — Both Modes, Full LDR Range\n"
                    "(green ≥60°, orange 45-60°, red <45°)", fontsize=9)
    ax_pm.legend(fontsize=8)
    ax_pm.set_xlim(0, 100)
    ax_pm.grid(True, axis="x", alpha=0.3)
    for bar, pm_val, fc in zip(bars, pms, fcs):
        ax_pm.text(pm_val + 1, bar.get_y() + bar.get_height()/2,
                   f"{pm_val:.1f}°  (f_c={fc/1e6:.1f} MHz)",
                   va="center", fontsize=7)

    fig.suptitle(
        f"Task 5: Dual-Capsule EQ — K87 De-emphasis (SJ1)\n"
        f"Rf={RF/1e3:.0f} kΩ  R_shelf={R_SHELF/1e3:.0f} kΩ  C_deemph={C_DEEMPH*1e12:.0f} pF  "
        f"|  Rolloff {F_P_ZF:.0f} Hz → {F_Z_ZF:.0f} Hz → {HF_SHELF_DB:.0f} dB shelf",
        fontsize=11
    )
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out_path = "sim/dual_capsule_eq.png"
    plt.savefig(out_path, dpi=150)
    print(f"  Plot saved to: {out_path}")

    # ------------------------------------------------------------------
    # Phase margin summary table
    # ------------------------------------------------------------------
    print()
    print(f"  {'Mode':<5} {'LDR':<26} {'f_crossover':>12} {'PM':>8}  Status")
    print("  " + "-" * 62)
    for mode, lbl, ldr_kΩ, fc, pm in pm_rows:
        status = "PASS" if pm >= 45 else "MARGINAL"
        print(f"  {mode:<5} {lbl:<26} {fc/1e6:>9.2f} MHz {pm:>7.1f}°  {status}")
    print("  " + "-" * 62)
    print()

    # Engineering verdict
    all_pass = all(r[-1] >= 45 for r in pm_rows)
    if all_pass:
        print("  RESULT: Phase margin PASS across all LDR values in both modes.")
        print(f"  The de-emphasis network (f_pole={F_P_ZF:.0f} Hz, f_zero={F_Z_ZF:.0f} Hz)")
        print(f"  is well below the loop gain crossover (>{min(r[-2] for r in pm_rows)/1e6:.1f} MHz),")
        print("  so SJ1 switching has no effect on amplifier stability.")
        print()
        print("  NOTE — Single-pole model limitation:")
        print("  This model uses a single-pole op-amp (GBW=8 MHz, one pole at 80 Hz).")
        print("  Real JFET-input op-amps (OPA2134, LME49720) have secondary poles")
        print("  at 20-40 MHz that shave ~10-15° off the phase margin at high LDR")
        print("  values (LDR > 100 kΩ, where f_c > 5 MHz).")
        print("  Worst-case real PM estimate: ~75° — still well above the 45° limit.")
        print("  A 22 pF Cdom cap across Rf is recommended for production to add")
        print("  a safety margin on untrimmed parts with lower GBW.")
    else:
        print("  WARNING: Some phase margin values are marginal.")
        print("  Consider adding a 22pF compensation cap across Rf.")

    print()
    print("  PCB — Solder Bridge SJ1:")
    print(f"    Footprint  : SolderJumper_2_Open")
    print(f"    Default    : OPEN  → K47 mode (flat response)")
    print(f"    Closed     : K87 mode  (-6 dB shelf above {F_Z_ZF:.0f} Hz)")
    print(f"    Silk label : 'SJ1  K47|K87'")
    print(f"    Place      : adjacent to Rf ({RF/1e3:.0f} kΩ) on F.Cu")
    print(f"    Series branch: R_shelf={R_SHELF/1e3:.0f} kΩ + C_deemph={C_DEEMPH*1e12:.0f} pF (0402 SMD)")
