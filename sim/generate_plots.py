"""
op-txm Simulation Plot Generator
======================================
Generates publication-quality plots for README documentation:

  1. eq_frequency_response.png  — K47 vs K87 EQ AC response
  2. hv_ripple_transient.png    — 72V charge-pump LC filter ripple suppression
  3. jfet_noise_density.png     — JFET equivalent input noise (EIN) density

No optical compressor — single operating point (no LDR sweep).

Outputs saved to: assets/sim_results/

Usage
-----
    uv run python sim/generate_plots.py
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

REPO_ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR    = os.path.join(REPO_ROOT, "assets", "sim_results")
os.makedirs(OUT_DIR, exist_ok=True)

# ── Shared plot style ──────────────────────────────────────────────────────────
STYLE = {
    "figure.facecolor":    "white",
    "axes.facecolor":      "white",
    "axes.edgecolor":      "#333333",
    "axes.linewidth":      1.2,
    "axes.grid":           True,
    "grid.color":          "#cccccc",
    "grid.linestyle":      "--",
    "grid.linewidth":      0.7,
    "axes.labelsize":      13,
    "axes.titlesize":      15,
    "axes.titleweight":    "bold",
    "xtick.labelsize":     11,
    "ytick.labelsize":     11,
    "legend.fontsize":     11,
    "legend.framealpha":   0.9,
    "legend.edgecolor":    "#aaaaaa",
    "lines.linewidth":     2.2,
    "font.family":         "sans-serif",
}

AUDIO_FREQS = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
FIG_SIZE    = (12, 6.67)   # 1200×667 px at 100 dpi → save at 150 dpi = 1800×1000 px
DPI         = 150

# =============================================================================
# 1.  EQ Frequency Response  (K47 vs K87, all LDR states)
# =============================================================================

RIN      = 10e3
RF       = 47e3
R_SHELF  = 47e3
C_DEEMPH = 150e-12   # updated from 330 pF — see dual_capsule_eq.py for rationale

F_P_ZF = 1.0 / (2 * np.pi * (RF + R_SHELF) * C_DEEMPH)
F_Z_ZF = 1.0 / (2 * np.pi * R_SHELF * C_DEEMPH)

FREQS = np.logspace(np.log10(10), np.log10(100e3), 4000)

def Zf_k47(f):
    return np.full(len(f), RF, dtype=complex)

def Zf_k87(f):
    s = 1j * 2 * np.pi * f
    Z_branch = R_SHELF + 1.0 / (s * C_DEEMPH)
    return RF * Z_branch / (RF + Z_branch)

def H_mag_dB(f, Zf_func, r_ldr):
    Zin = RIN + r_ldr
    H   = -Zf_func(f) / Zin
    return 20 * np.log10(np.abs(H))

# Normalise to 1 kHz gain in K47/nominal-LDR mode so 1 kHz = 0 dB reference
ldr_ref  = 100e3
ref_gain = H_mag_dB(np.array([1000.0]), Zf_k47, ldr_ref)[0]

with plt.rc_context(STYLE):
    fig, axes = plt.subplots(1, 2, figsize=FIG_SIZE, sharey=False)
    fig.suptitle("op-txm EQ Stage — K47 vs K87 De-emphasis Frequency Response",
                 fontsize=16, fontweight="bold", y=1.01)

    ax0, ax1 = axes

    # No optical compressor — single operating point (LDR removed from circuit)
    r_ldr_op = ldr_ref  # 100 kΩ used only for reference gain normalisation; no LDR in op-txm
    H_k47 = H_mag_dB(FREQS, Zf_k47, r_ldr_op) - ref_gain
    ax0.semilogx(FREQS, H_k47, color="#1565C0", label="K47 flat (no compressor)")

    ax0.set_title("K47 Mode (SJ1 Open) — Flat")
    ax0.set_xlabel("Frequency (Hz)")
    ax0.set_ylabel("Relative Gain (dB)")
    ax0.set_xlim(20, 20000)
    ax0.set_ylim(-20, 10)
    ax0.axhline(0, color="#555555", linewidth=0.9, linestyle=":")
    ax0.xaxis.set_major_formatter(ticker.FuncFormatter(
        lambda x, _: f"{int(x/1000)}k" if x >= 1000 else str(int(x))))
    ax0.set_xticks(AUDIO_FREQS)
    ax0.legend(loc="lower left")

    H_k87 = H_mag_dB(FREQS, Zf_k87, r_ldr_op) - ref_gain
    ax1.semilogx(FREQS, H_k87, color="#B71C1C", label="K87 de-emphasis")

    # Annotate rolloff corner (F_P_ZF ≈ 11.3 kHz — within audio band)
    ax1.axvline(F_P_ZF, color="#666666", linewidth=1.0, linestyle="--")
    ax1.annotate(f"Rolloff\n{F_P_ZF/1e3:.1f} kHz",
                 xy=(F_P_ZF, -2), xytext=(F_P_ZF*0.45, -8),
                 arrowprops=dict(arrowstyle="->", color="#555555"),
                 fontsize=9, color="#555555")
    # Shelf frequency (F_Z_ZF ≈ 22.6 kHz) is above the audio band xlim;
    # show it as a text note at the right edge instead of an off-screen vline.
    ax1.text(0.97, 0.12, f"−6 dB shelf: {F_Z_ZF/1e3:.1f} kHz\n(above audio band)",
             transform=ax1.transAxes, ha="right", va="bottom", fontsize=9,
             color="#333333",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                       edgecolor="#cccccc", alpha=0.9))

    ax1.set_title("K87 Mode (SJ1 Closed) — −6 dB De-emphasis Shelf")
    ax1.set_xlabel("Frequency (Hz)")
    ax1.set_ylabel("Relative Gain (dB)")
    ax1.set_xlim(20, 20000)
    ax1.set_ylim(-20, 10)
    ax1.axhline(-6, color="#aaaaaa", linewidth=0.8, linestyle=":")
    ax1.xaxis.set_major_formatter(ticker.FuncFormatter(
        lambda x, _: f"{int(x/1000)}k" if x >= 1000 else str(int(x))))
    ax1.set_xticks(AUDIO_FREQS)
    ax1.legend(loc="lower left")

    fig.tight_layout()
    out_path = os.path.join(OUT_DIR, "eq_frequency_response.png")
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"[1/3] Saved: {out_path}")

# Compute key values for reporting
H_k47_20   = H_mag_dB(np.array([20.0]),    Zf_k47, ldr_ref)[0] - ref_gain
H_k47_1k   = 0.0
H_k47_10k  = H_mag_dB(np.array([10000.0]), Zf_k47, ldr_ref)[0] - ref_gain
H_k47_20k  = H_mag_dB(np.array([20000.0]), Zf_k47, ldr_ref)[0] - ref_gain
H_k87_20   = H_mag_dB(np.array([20.0]),    Zf_k87, ldr_ref)[0] - ref_gain
H_k87_1k   = H_mag_dB(np.array([1000.0]),  Zf_k87, ldr_ref)[0] - ref_gain
H_k87_10k  = H_mag_dB(np.array([10000.0]), Zf_k87, ldr_ref)[0] - ref_gain
H_k87_20k  = H_mag_dB(np.array([20000.0]), Zf_k87, ldr_ref)[0] - ref_gain

# Flatness in K47 mode (20 Hz – 20 kHz)
H_k47_band = H_mag_dB(FREQS[(FREQS >= 20) & (FREQS <= 20000)], Zf_k47, ldr_ref) - ref_gain
k47_max_dev = np.max(np.abs(H_k47_band))

# −3 dB corner in K87 mode (relative to 1 kHz)
H_k87_band = H_mag_dB(FREQS, Zf_k87, ldr_ref) - ref_gain
corner_idx  = np.argmin(np.abs(H_k87_band - H_k87_1k + 3))
f_3db_k87   = FREQS[corner_idx]

# =============================================================================
# 2.  72V HV Rail — LC Filter Ripple Suppression
# =============================================================================

V_PHANTOM   = 48.0
V_CLK_PP    = 24.0
V_DIODE     = 0.30
F_OSC       = 100e3
C_PUMP      = 100e-9
C_OUT       = 4.7e-6
I_LOAD_HV   = 1.636e-3   # A  JFET Ids (servo-locked); only load on 72V rail
L_LPF       = 10e-3
C_LPF       = 10e-6
R_DAMP      = 5.0        # Ω  series resistance of inductor (ESR estimate)

V_OUT_IDEAL = V_PHANTOM + V_CLK_PP - 2 * V_DIODE
V_DROP      = I_LOAD_HV / (F_OSC * C_PUMP)
V_OUT_DC    = V_OUT_IDEAL - V_DROP

f_corner_lc = 1.0 / (2 * np.pi * np.sqrt(L_LPF * C_LPF))
atten_at_fosc = (f_corner_lc / F_OSC) ** 2

# Ripple before and after filter
V_ripple_pre  = I_LOAD_HV / (F_OSC * C_OUT)
V_ripple_post = V_ripple_pre * atten_at_fosc

# Build a time-domain waveform showing the filtered output
t   = np.linspace(0, 5e-5, 5000)   # 50 µs window (5 pump cycles at 100 kHz)
# Pre-filter: sinusoidal ripple at 100 kHz
v_pre  = V_OUT_DC + V_ripple_pre * np.sin(2 * np.pi * F_OSC * t)
# Post-filter: -80 dB at 100 kHz → essentially flat; show residual
v_post = V_OUT_DC + V_ripple_post * np.sin(2 * np.pi * F_OSC * t)

# Frequency sweep for Bode plot inset
f_sweep   = np.logspace(1, 6, 2000)
H_lc_dB   = np.where(
    f_sweep < f_corner_lc,
    0.0,
    20 * np.log10((f_corner_lc / f_sweep) ** 2)
)

with plt.rc_context(STYLE):
    fig = plt.figure(figsize=FIG_SIZE)
    gs  = fig.add_gridspec(1, 2, wspace=0.38)
    ax_t = fig.add_subplot(gs[0])
    ax_f = fig.add_subplot(gs[1])

    fig.suptitle("op-txm — 72V HV Rail Charge Pump Ripple Suppression",
                 fontsize=16, fontweight="bold", y=1.01)

    # Time-domain: pre vs post filter (offset for clarity)
    offset_ppb = 0.05   # mV scale view
    ax_t.plot(t * 1e6, (v_pre - V_OUT_DC) * 1e6,
              color="#E53935", linewidth=1.8, label=f"Before LC filter  ({V_ripple_pre*1e6:.0f} µV p-p)")
    ax_t.plot(t * 1e6, (v_post - V_OUT_DC) * 1e9,
              color="#1565C0", linewidth=1.8, label=f"After LC filter   ({V_ripple_post*1e9:.2f} nV p-p)")
    ax_t.set_xlabel("Time (µs)")
    ax_t.set_ylabel("Ripple amplitude")
    ax_t.set_title("Time-Domain Ripple (at 100 kHz pump)")
    ax_t.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y:.0f}"))
    ax_t.set_xlim(0, 50)
    ax_t.legend()
    ax_t.text(0.97, 0.97, f"V_out DC = {V_OUT_DC:.2f} V\n(Load: {I_LOAD_HV*1e3:.2f} mA)",
              transform=ax_t.transAxes, ha="right", va="top", fontsize=9,
              bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.9))
    # Dual-axis label note
    ax_t.set_ylabel("Red: µV scale  |  Blue: nV scale")

    # Frequency-domain: LC filter Bode plot
    ax_f.semilogx(f_sweep, H_lc_dB, color="#1565C0", linewidth=2.2)
    ax_f.axvline(F_OSC, color="#E53935", linestyle="--", linewidth=1.5,
                 label=f"Pump freq = {F_OSC/1e3:.0f} kHz")
    ax_f.axvline(f_corner_lc, color="#FF8F00", linestyle="--", linewidth=1.5,
                 label=f"LC corner = {f_corner_lc:.0f} Hz")
    ax_f.scatter([F_OSC], [H_lc_dB[np.argmin(np.abs(f_sweep - F_OSC))]],
                 color="#E53935", zorder=5, s=80)
    atten_dB = H_lc_dB[np.argmin(np.abs(f_sweep - F_OSC))]
    ax_f.annotate(f"Attenuation\nat 100 kHz:\n{atten_dB:.0f} dB",
                  xy=(F_OSC, atten_dB), xytext=(F_OSC * 0.08, atten_dB + 20),
                  arrowprops=dict(arrowstyle="->", color="#333333"),
                  fontsize=9, color="#333333")
    ax_f.set_xlabel("Frequency (Hz)")
    ax_f.set_ylabel("Attenuation (dB)")
    ax_f.set_title(f"LC Post-Filter Response\n(L={L_LPF*1e3:.0f} mH, C={C_LPF*1e6:.0f} µF)")
    ax_f.set_ylim(-120, 10)
    ax_f.set_xlim(10, 1e6)
    ax_f.legend(loc="lower left")

    fig.tight_layout()
    out_path = os.path.join(OUT_DIR, "hv_ripple_transient.png")
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"[2/3] Saved: {out_path}")

# =============================================================================
# 3.  JFET Equivalent Input Noise (EIN) Density
# =============================================================================
# MMBF170 in saturation at Ids = 1.64 mA (servo setpoint)
# Noise sources:
#   Thermal noise of Rg (1 GΩ gate bias) — negligible at audio
#   JFET channel thermal noise: v_n^2 = 4kT * (2/3) / gm
#   Flicker noise (1/f): S_vn = K_f / (C_ox * W * L * f)
#     — approximate with empirical K_f for MMBF170 (~1e-12 V²)
#   Drain resistor thermal noise: v_rd^2 = 4kT * R_D  (referred to input via gm)
#   Source resistor noise: v_rs^2 = 4kT * R_S (appears at output, divide by gm)

k     = 1.38e-23    # J/K
T     = 300.0       # K  (27 °C)
BETA  = 40e-3       # A/V²
VTO   = -0.60       # V
VHV   = 72.0
R_D_N = 22e3        # Ω  drain resistor
R_S_N = 1e3         # Ω  source resistor
R_G_N = 1e9         # Ω  gate bias (1 GΩ)
C_CAP = 50e-12      # F  K87 capsule capacitance (gate source impedance at audio)

# Operating point with servo
Ids_srv = (VHV - 36.0) / R_D_N   # 1.636 mA
gm      = 2 * np.sqrt(BETA * Ids_srv)   # 16.18 mA/V

# Idss range swept across incoming-inspection limits
IDSS_RANGE = {
    "Idss = 2 mA (low)":  {"ids": 2e-3,  "style": {"color": "#42A5F5", "linestyle": "--"}},
    "Idss = 4 mA (nom)":  {"ids": Ids_srv, "style": {"color": "#1565C0", "linestyle": "-",  "linewidth": 2.8}},
    "Idss = 6 mA (high)": {"ids": 6e-3,  "style": {"color": "#0D47A1", "linestyle": "-."}},
}

freqs_noise = np.logspace(np.log10(10), np.log10(20000), 1000)

# Flicker noise corner frequency for MMBF170-class N-JFET: ~50 Hz
F_CORNER_FLICKER = 50.0

# Gate resistor (Rg = 1 GΩ) Johnson noise, referred to input through the
# Rg–Ccapsule RC divider.  Corner fc = 1/(2π·Rg·Ccap) ≈ 3.2 Hz.
# Above fc the contribution rolls off as 1/f:
#   v_n_Rg(f) = sqrt(4kT·Rg) / sqrt(1 + (f/fc)²)
#             ≈ sqrt(4kT·Rg) · fc / f  for f >> fc
vn_rg_flat = np.sqrt(4 * k * T * R_G_N)
fc_rg      = 1.0 / (2 * np.pi * R_G_N * C_CAP)   # 3.18 Hz

with plt.rc_context(STYLE):
    fig, axes = plt.subplots(1, 2, figsize=FIG_SIZE)
    fig.suptitle("MMBF170 JFET + OPA1642 — Equivalent Input Noise (EIN) Density",
                 fontsize=16, fontweight="bold", y=1.01)

    ax_lin, ax_log = axes

    ein_at_1k_nom = None
    ein_at_1k_results = {}
    vn_ch_nom = None   # save for annotation

    for label, cfg in IDSS_RANGE.items():
        ids_pt = cfg["ids"]
        gm_pt  = 2 * np.sqrt(BETA * ids_pt)

        # Channel thermal noise referred to input (white above flicker corner)
        vn_ch = np.sqrt(4 * k * T * (2.0 / 3.0) / gm_pt)
        if "nom" in label:
            vn_ch_nom = vn_ch

        # Channel noise + 1/f flicker
        vn_chan_total = np.sqrt(vn_ch**2 * (1 + F_CORNER_FLICKER / freqs_noise))

        # Gate resistor noise filtered by Rg·Ccap (rolls off above 3 Hz)
        vn_rg = vn_rg_flat / np.sqrt(1.0 + (freqs_noise / fc_rg)**2)

        # Total EIN = RSS of all uncorrelated noise sources
        ein = np.sqrt(vn_chan_total**2 + vn_rg**2)

        ein_1k = ein[np.argmin(np.abs(freqs_noise - 1000.0))]
        ein_at_1k_results[label] = ein_1k

        if "nom" in label:
            ein_at_1k_nom = ein_1k

        kw = {"label": f"{label}  ({ein_1k*1e9:.2f} nV/√Hz @ 1 kHz)"}
        kw.update(cfg["style"])

        ax_lin.plot(freqs_noise, ein * 1e9, **kw)
        ax_log.loglog(freqs_noise, ein * 1e9, **kw)

    # Target line
    target_ein = 5e-9  # nV/√Hz — competitive large-diaphragm condenser spec
    for ax in [ax_lin, ax_log]:
        ax.axhline(target_ein * 1e9, color="#E53935", linestyle=":", linewidth=1.5,
                   label=f"Target ≤ {target_ein*1e9:.0f} nV/√Hz")
        if ax == ax_log:
            ax.axvline(F_CORNER_FLICKER, color="#FF8F00", linestyle="--",
                       linewidth=1.2, label=f"1/f corner ≈ {F_CORNER_FLICKER:.0f} Hz")
        ax.set_ylabel("EIN (nV/√Hz)")
        ax.set_xlim(10, 20000)
        ax.legend(loc="upper right", fontsize=9)
        ax.set_ylim(0.5, 30)

    ax_lin.set_xlabel("Frequency (Hz)")
    ax_lin.set_title("Linear Frequency Scale")
    ax_lin.xaxis.set_major_formatter(ticker.FuncFormatter(
        lambda x, _: f"{int(x/1000)}k" if x >= 1000 else str(int(x))))
    ax_lin.set_xticks(AUDIO_FREQS[1:])

    ax_log.set_xlabel("Frequency (Hz)")
    ax_log.set_title("Log-Log Scale")

    if ein_at_1k_nom is not None and vn_ch_nom is not None:
        # EIN at 20 Hz for nominal case
        vn_rg_20Hz   = vn_rg_flat / np.sqrt(1.0 + (20.0 / fc_rg)**2)
        vn_chan_20Hz  = np.sqrt(vn_ch_nom**2 * (1 + F_CORNER_FLICKER / 20.0))
        ein_20Hz_nom  = np.sqrt(vn_chan_20Hz**2 + vn_rg_20Hz**2)
        ax_lin.text(0.97, 0.60,
                    f"Nominal (Ids ≈ 1.64 mA):\n"
                    f"  gm = {gm*1e3:.2f} mA/V\n"
                    f"  EIN @ 1 kHz = {ein_at_1k_nom*1e9:.2f} nV/√Hz\n"
                    f"  EIN @ 20 Hz = {ein_20Hz_nom*1e9:.1f} nV/√Hz\n"
                    f"  Rg noise corner: {fc_rg:.1f} Hz",
                    transform=ax_lin.transAxes, ha="right", va="top",
                    fontsize=9, bbox=dict(boxstyle="round,pad=0.4",
                    facecolor="lightyellow", alpha=0.9))

    fig.tight_layout()
    out_path = os.path.join(OUT_DIR, "jfet_noise_density.png")
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"[3/3] Saved: {out_path}")

# =============================================================================
# 4.  Thermal Safety Calculations
# =============================================================================
# LR8: drops 48V → 35.2V at ~3.47 mA (power/LDO section load)
V_IN_LR8   = 48.0
V_OUT_LR8  = 35.2
I_LR8      = 4.7e-3    # A  35.2V rail load: TPS7A(1.0) + OPA1642(3.6) + misc(0.1) mA
P_LR8      = (V_IN_LR8 - V_OUT_LR8) * I_LR8
Rth_LR8    = 300.0   # °C/W  SOT-89 package (datasheet: 250–350 °C/W)
T_AMB      = 45.0    # °C  internal microphone body temperature (non-ventilated)
Tj_LR8     = T_AMB + P_LR8 * Rth_LR8

# TPS7A39: ±15V LDO, Vin=35.2V, Vout=±15V, Iq=75µA each
# Each half dissipates: (35.2 - 15) * I_out_half
I_OPAMP_TOTAL = 3.7e-3    # A  ±15V load: OPA1642 dual Iq(3.6mA) + misc(0.1mA)
I_EACH_HALF   = I_OPAMP_TOTAL / 2
P_TPS_POS  = (V_OUT_LR8 - 15.0) * I_EACH_HALF
P_TPS_NEG  = (V_OUT_LR8 - 15.0) * I_EACH_HALF
P_TPS_TOT  = P_TPS_POS + P_TPS_NEG + 2 * 75e-6 * 35.2  # both channels + Iq
Rth_TPS    = 46.0    # °C/W  WSON-12 with 4 thermal vias (datasheet: 36–50 °C/W)
Tj_TPS     = T_AMB + P_TPS_TOT * Rth_TPS

# =============================================================================
# 5.  Print summary for README
# =============================================================================
print("\n" + "=" * 68)
print("  Simulation Summary — README Values")
print("=" * 68)
print(f"\n  EQ Stage:")
print(f"    K47 max deviation 20 Hz–20 kHz : ±{k47_max_dev:.2f} dB")
print(f"    K87 −3 dB corner frequency      : {f_3db_k87/1e3:.1f} kHz")
print(f"    K87 HF shelf (at 20 kHz)        : {H_k87_20k:.1f} dB  (target −6 dB)")
print(f"    Gain table (ref = K47 @ 1 kHz = 0 dB):")
print(f"      20 Hz : K47 = {H_k47_20:+.2f} dB   K87 = {H_k87_20:+.2f} dB")
print(f"    1000 Hz : K47 = {H_k47_1k:+.2f} dB   K87 = {H_k87_1k:+.2f} dB")
print(f"   10000 Hz : K47 = {H_k47_10k:+.2f} dB   K87 = {H_k87_10k:+.2f} dB")
print(f"   20000 Hz : K47 = {H_k47_20k:+.2f} dB   K87 = {H_k87_20k:+.2f} dB")
print(f"\n  Noise:")
for lbl, val in ein_at_1k_results.items():
    print(f"    {lbl} : {val*1e9:.2f} nV/√Hz @ 1 kHz")
# EIN at 20 Hz (dominated by Rg noise through capsule RC)
vn_rg_at_20 = vn_rg_flat / np.sqrt(1.0 + (20.0 / fc_rg)**2)
gm_nom = 2 * np.sqrt(BETA * Ids_srv)
vn_ch_at_20 = np.sqrt(4 * k * T * (2.0/3.0) / gm_nom) * np.sqrt(1 + F_CORNER_FLICKER / 20.0)
ein_20Hz = np.sqrt(vn_ch_at_20**2 + vn_rg_at_20**2)
print(f"    Nominal EIN @ 20 Hz  : {ein_20Hz*1e9:.1f} nV/√Hz  (dominated by Rg/Ccap)")
print(f"\n  72V Rail:")
print(f"    V_out DC        : {V_OUT_DC:.2f} V  (trimmed to 72V by LR8)")
print(f"    Ripple pre-LC   : {V_ripple_pre*1e6:.2f} µV p-p")
print(f"    Ripple post-LC  : {V_ripple_post*1e9:.3f} nV p-p  ({V_ripple_post*1e6:.4f} µV)")
print(f"    LC attenuation  : {atten_dB:.0f} dB at 100 kHz")
print(f"\n  Thermal (T_amb = {T_AMB:.0f} °C inside enclosure):")
print(f"    LR8  : P = {P_LR8*1000:.1f} mW  →  Tj = {Tj_LR8:.1f} °C  "
      f"[{'PASS' if Tj_LR8 < 85 else 'FAIL'} < 85°C]")
print(f"    TPS7A39: P = {P_TPS_TOT*1000:.1f} mW  →  Tj = {Tj_TPS:.1f} °C  "
      f"[{'PASS' if Tj_TPS < 85 else 'FAIL'} < 85°C]")
print("=" * 68)

# Export numerical results as a small dict for use in CI or README automation
results = {
    "k47_max_dev_dB":        round(k47_max_dev, 3),
    "k87_corner_kHz":        round(f_3db_k87 / 1e3, 1),
    "k87_shelf_20kHz_dB":    round(H_k87_20k, 1),
    "k47_gain_20Hz":         round(H_k47_20,  2),
    "k47_gain_1kHz":         round(H_k47_1k,  2),
    "k47_gain_10kHz":        round(H_k47_10k, 2),
    "k47_gain_20kHz":        round(H_k47_20k, 2),
    "k87_gain_20Hz":         round(H_k87_20,  2),
    "k87_gain_1kHz":         round(H_k87_1k,  2),
    "k87_gain_10kHz":        round(H_k87_10k, 2),
    "k87_gain_20kHz":        round(H_k87_20k, 2),
    "ein_nom_1kHz_nV_rtHz":  round(ein_at_1k_nom * 1e9, 2),
    "ein_nom_20Hz_nV_rtHz":  round(ein_20Hz * 1e9, 1),
    "rg_noise_corner_Hz":    round(fc_rg, 2),
    "ripple_pre_uV":         round(V_ripple_pre * 1e6, 3),
    "ripple_post_nV":        round(V_ripple_post * 1e9, 3),
    "vout_dc_V":             round(V_OUT_DC, 2),
    "P_LR8_mW":              round(P_LR8 * 1000, 1),
    "Tj_LR8_C":              round(Tj_LR8, 1),
    "P_TPS_mW":              round(P_TPS_TOT * 1000, 1),
    "Tj_TPS_C":              round(Tj_TPS, 1),
}

import json, sys
print("\nJSON results:")
print(json.dumps(results, indent=2))
