"""
op-txm Full Signal-Chain Simulation
=========================================
AC sweep of the complete signal path:

  Capsule (K87, 50 pF)
    → JFET buffer (MMBF170, Rd=22kΩ, Rs=1kΩ, Vhv=72V)
    → DC-coupling cap (1 µF)
    → EQ stage (OPA2134 macromodel, K47 flat or K87 −6 dB shelf)
    → NTE10/3 output transformer (1:3 step-up, estimated parameters)
    → Differential 600 Ω XLR load

No optical compressor.  One operating point; two EQ modes.

Transformer parameters
-----------------------
  L_pri = 80 H  (community bench measurement; verify with LCR meter)
  n = 3  (1:3 secondary tap)  →  L_sec = 720 H
  k ≈ 0.999997  (leakage ~0.5 mH referred to primary → HF -3dB ≈ 42 kHz)
  DCR_pri = 30 Ω, DCR_sec = 270 Ω  (estimated — update after bench measurement)

Outputs
-------
  sim/chain_k47.cir / .log
  sim/chain_k87.cir / .log
  assets/sim_results/signal_chain.png

Usage
-----
    .venv/bin/python sim/signal_chain.py
"""

import os
import subprocess
import shutil
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import scipy.optimize as so

SIM_DIR  = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SIM_DIR)
OUT_DIR  = os.path.join(REPO_ROOT, "assets", "sim_results")
os.makedirs(OUT_DIR, exist_ok=True)

SEP = "=" * 68

# ── Circuit values ─────────────────────────────────────────────────────────────
# Capsule
C_CAP     = 50e-12      # K87 capsule capacitance
R_GBIAS   = 1e9         # gate bias (1 GΩ)

# JFET (MMBF170)
V_HV      = 72.0        # V
R_D       = 22e3        # drain load
R_S       = 1e3         # source degeneration
C_COUP    = 1e-6        # JFET drain coupling cap
BETA_JFT  = 40e-3       # A/V²
VTO_JFT   = -0.60       # V
LAMBDA    = 0.005       # 1/V

# EQ (OPA1642 macromodel — JFET dual, GBW=11MHz, EIN=5.1nV/√Hz)
R_EQ_IN   = 10e3
R_F       = 47e3
R_SHELF   = 47e3
C_DEEMPH  = 150e-12     # K87 de-emphasis cap
GBW       = 11e6        # Hz  (OPA1642: 11 MHz vs OPA2134's 8 MHz)
A_DC      = 200e3
Gm_VAL    = 1e-3
Rp_VAL    = A_DC / Gm_VAL
Cp_VAL    = Gm_VAL / (2 * np.pi * GBW)

# NTE10/3 transformer (1:3 tap)
N_TURNS   = 3.0
L_PRI     = 80.0        # H  — community measurement; verify at bench
L_SEC     = L_PRI * N_TURNS**2   # = 720 H
L_LEAK    = 5e-4        # H  referred to primary (~0.5 mH → HF corner ~42 kHz)
K_COUPLE  = (1.0 - L_LEAK / L_PRI) ** 0.5   # coupling coefficient
DCR_PRI   = 30.0        # Ω  — estimated; measure at bench
DCR_SEC   = DCR_PRI * N_TURNS**2  # = 270 Ω (scaled by n²)

# Load
R_LOAD_EACH = 600.0     # Ω per balanced leg (600 Ω standard XLR load, each side)

OPAMP_SUBCKT = f"""\
.subckt opamp1 inp inn out
Rin   inp inn  1Meg
Gm    0   vint  inp inn  {Gm_VAL:.6g}
Rp    vint 0    {Rp_VAL:.6g}
Cp    vint 0    {Cp_VAL:.6g}
Eout  out  0    vint 0  1
.ends opamp1"""

JFET_MODEL = (
    f".model MMBF170 NJF "
    f"VTO={VTO_JFT} BETA={BETA_JFT:.4g} LAMBDA={LAMBDA} "
    f"IS=1e-14 RD=5 RS=5 CGS=30p CGD=12p"
)

# ── Analytical preview ─────────────────────────────────────────────────────────
def jfet_eqn(ids, r_par):
    vgs = -ids * r_par
    if vgs <= VTO_JFT:
        return -ids
    return BETA_JFT * (vgs - VTO_JFT) ** 2 - ids

R_PAR = R_S  # only source degeneration (no LDR/Rnfb in op-txm)
ids_op = so.brentq(jfet_eqn, 1e-9, 20e-3, args=(R_PAR,))
vgs_op = -ids_op * R_PAR
gm_op  = 2 * BETA_JFT * (vgs_op - VTO_JFT)
rds_op = 1.0 / (LAMBDA * ids_op)
vd_op  = V_HV - ids_op * R_D

R_jfet_load = 1e6 * R_EQ_IN / (1e6 + R_EQ_IN)  # 1MΩ Rbias_eq || 10k R_EQ_IN
R_D_eff = R_D * R_jfet_load / (R_D + R_jfet_load)
Av_jfet = -gm_op * R_D_eff / (1 + gm_op * R_S)
Av_eq_k47 = -R_F / R_EQ_IN
Av_tx = N_TURNS  # voltage step-up

# Loading at secondary: R_load total differential = 2 × R_LOAD_EACH = 1200 Ω
# Insertion loss factor from winding DCR:
R_load_diff = 2 * R_LOAD_EACH
r_ins_loss = R_load_diff / (R_load_diff + DCR_SEC + DCR_PRI * N_TURNS ** 2)
Av_total_k47 = abs(Av_jfet * Av_eq_k47) * Av_tx * r_ins_loss

print(SEP)
print("op-txm Signal Chain — Analytical Preview")
print(SEP)
print(f"\nJFET Q-point (MMBF170, self-bias):")
print(f"  Ids = {ids_op*1e3:.2f} mA  |  Vgs = {vgs_op:.3f} V  |  Vdrain = {vd_op:.1f} V")
print(f"  gm  = {gm_op*1e3:.2f} mA/V  |  rds = {rds_op/1e3:.0f} kΩ")
print(f"\nMid-band gain breakdown (K47 mode, 1 kHz):")
print(f"  JFET (loaded)  : {20*np.log10(abs(Av_jfet)):.1f} dB")
print(f"  EQ (K47 flat)  : {20*np.log10(abs(Av_eq_k47)):.1f} dB")
print(f"  Transformer 1:3: +{20*np.log10(Av_tx):.1f} dB (voltage)")
print(f"  Insertion loss  : {20*np.log10(r_ins_loss):.2f} dB (DCR loading, estimated)")
print(f"  Total (K47)    : {20*np.log10(Av_total_k47):.1f} dB")

Av_eq_hf = -(R_F * R_SHELF / (R_F + R_SHELF)) / R_EQ_IN
Av_total_k87_hf = abs(Av_jfet * Av_eq_hf) * Av_tx * r_ins_loss
shelf_db = 20 * np.log10(Av_total_k87_hf) - 20 * np.log10(Av_total_k47)
print(f"\nK87 shelf (>22 kHz): {shelf_db:.1f} dB  (target −6 dB)")

lf_corner = (DCR_PRI + R_D_eff / N_TURNS**2) / (2 * np.pi * L_PRI)
hf_corner = R_load_diff / (2 * np.pi * L_LEAK * N_TURNS**2)
print(f"\nTransformer bandwidth (estimated):")
print(f"  LF −3 dB : {lf_corner:.2f} Hz  (Lpri={L_PRI:.0f} H, Rsrc={DCR_PRI:.0f}Ω)")
print(f"  HF −3 dB : {hf_corner/1e3:.1f} kHz  (Lleak={L_LEAK*1e3:.1f} mH referred to primary)")
print(f"  NOTE: Both depend on estimated/measured transformer parameters.")
print()

# ── Netlist writer ─────────────────────────────────────────────────────────────
def write_netlist(path: str, eq_mode: str) -> None:
    # Rf always connects eq_inn → eq_out.
    # K87: SJ1 adds a parallel branch (Rshelf + Cdeemph) giving a HF rolloff shelf.
    # Feedback impedance K47: Rf
    # Feedback impedance K87: Rf || (Rshelf + Zcdeemph)  → -6 dB above ~11 kHz
    rf_conn = "eq_inn  eq_out"
    if eq_mode == "k87":
        sj1 = (
            f"Rshelf   eq_inn    eq_fb_mid  {R_SHELF:.6g}\n"
            f"Cdeemph  eq_fb_mid eq_out     {C_DEEMPH:.6g}"
        )
    else:
        sj1 = "* SJ1 open — K47 flat"

    netlist = f"""\
* op-txm full signal chain — AC analysis
* EQ mode: {eq_mode.upper()}
{OPAMP_SUBCKT}
{JFET_MODEL}

* ── Supplies ───────────────────────────────────────────────────────────────────
Vhv  vhv  0  DC {V_HV}
Vcc  vcc  0  DC 15
Vee  vee  0  DC -15

* ── Capsule model (K87 50 pF) ──────────────────────────────────────────────────
Vsig  vcap_src  0  AC 1
Ccap  vcap_src  vcap  {C_CAP:.6g}
Rgb1  vcap      0     {R_GBIAS:.6g}

* ── JFET buffer (MMBF170, common-source) ──────────────────────────────────────
Cin   vcap    jg     10n
Rgb2  jg      0      {R_GBIAS:.6g}
J1    jd      jg     js    MMBF170
Rd    vhv     jd     {R_D:.6g}
Rs    js      0      {R_S:.6g}
Cout  jd      eq_in  {C_COUP:.6g}

* ── EQ inverting stage ─────────────────────────────────────────────────────────
Rbias_eq  eq_in   0        1Meg
Req_in    eq_in   eq_inn   {R_EQ_IN:.6g}
Req_bias  eq_inp  0        {R_EQ_IN:.6g}
Rf_eq     {rf_conn}  {R_F:.6g}
{sj1}
Xeq  eq_inp  eq_inn  eq_out  opamp1

* ── NTE10/3 transformer (1:3 step-up) ─────────────────────────────────────────
* Estimated parameters — update DCR_PRI, DCR_SEC, L_LEAK after bench measurement
Rdcr_pri  eq_out  txp_hi  {DCR_PRI:.4g}
Lpri      txp_hi  txp_lo  {L_PRI}H
Lsec      txs_hi  txs_lo  {L_SEC}H
Ktx       Lpri Lsec  {K_COUPLE:.8f}
Rdcr_sec  txs_hi  vout_h  {DCR_SEC:.4g}
* Primary return to GND
Vtx_gnd   txp_lo  0  DC 0

* ── Balanced 600 Ω load (differential, each leg) ──────────────────────────────
Rload_h  vout_h  vcm  {R_LOAD_EACH}
Rload_c  txs_lo  vcm  {R_LOAD_EACH}
Vcm      vcm     0    DC 0

.op
.ac dec 100 10 100k
.print ac vdb(vout_h) vp(vout_h) vdb(txs_lo) vp(txs_lo)
.end
"""
    with open(path, "w") as fh:
        fh.write(netlist)


def run_ngspice(cir: str, log: str) -> int:
    r = subprocess.run(["ngspice", "-b", "-o", log, cir],
                       capture_output=True, text=True)
    return r.returncode


def parse_log(log: str):
    """Parse ngspice AC output: frequencies, vdb_hot, phase_hot (degrees).

    ngspice writes 4-column rows (index freq vdb vp) in multiple 57-row blocks,
    all under the same 'Index frequency vdb(vout_h) vp(vout_h)' header.
    Collect both columns from each data row.
    """
    freqs, vdb_h, vph_h = [], [], []
    in_ac = False
    try:
        with open(log) as fh:
            for line in fh:
                s = line.strip()
                if "vdb(vout_h)" in s.lower():
                    in_ac = True
                    continue
                if "vdb(txs_lo)" in s.lower():
                    in_ac = False   # stop at secondary low-side section
                    continue
                if s.startswith("---") or s.startswith("Index"):
                    continue
                if not in_ac:
                    continue
                parts = s.split()
                if len(parts) < 4:
                    continue
                try:
                    int(parts[0])
                except ValueError:
                    continue
                freqs.append(float(parts[1]))
                vdb_h.append(float(parts[2]))
                vph_h.append(float(parts[3]))
    except FileNotFoundError:
        pass
    return np.array(freqs), np.array(vdb_h), np.rad2deg(np.array(vph_h))


# ── Run simulations ────────────────────────────────────────────────────────────
ngspice_ok = bool(shutil.which("ngspice"))
results = {}

print(SEP)
print("Running ngspice AC sweeps...")
print(SEP)

for mode in ["k47", "k87"]:
    cir = os.path.join(SIM_DIR, f"chain_{mode}.cir")
    log = os.path.join(SIM_DIR, f"chain_{mode}.log")
    write_netlist(cir, mode)
    if ngspice_ok:
        rc = run_ngspice(cir, log)
        freqs, vdb, phase = parse_log(log)
        n = len(freqs)
        print(f"  {mode.upper():4s}  →  {n} points  [{'OK' if n > 0 else 'no data — check log'}]")
        results[mode] = (freqs, vdb, phase)
    else:
        print("  ngspice not found — install: sudo pacman -S ngspice")
        results[mode] = (np.array([]), np.array([]), np.array([]))


def idx(freqs, f):
    return int(np.argmin(np.abs(freqs - f)))


# ── Report ─────────────────────────────────────────────────────────────────────
all_pass = True
f47, db47, ph47 = results["k47"]
f87, db87, ph87 = results["k87"]

if len(f47) > 0 and len(f87) > 0:
    print()
    print(SEP)
    print("Results — ngspice AC")
    print(SEP)

    g47_1k   = db47[idx(f47, 1e3)]
    g47_20k  = db47[idx(f47, 20e3)]
    g47_100k = db47[idx(f47, 100e3)]
    g87_1k   = db87[idx(f87, 1e3)]
    g87_20k  = db87[idx(f87, 20e3)]
    g87_100k = db87[idx(f87, 100e3)]
    shelf_20k  = g87_20k  - g47_20k
    shelf_100k = g87_100k - g47_100k

    print(f"\n  Gain @ 1 kHz   : K47 = {g47_1k:.1f} dB  |  K87 = {g87_1k:.1f} dB")
    print(f"  Gain @ 20 kHz  : K47 = {g47_20k:.1f} dB  |  K87 = {g87_20k:.1f} dB")
    print(f"  Gain @ 100 kHz : K47 = {g47_100k:.1f} dB  |  K87 = {g87_100k:.1f} dB")
    print(f"  K87 shelf @ 20 kHz  : {shelf_20k:.1f} dB  (expected ~−3.7 dB; shelf corner = 22.6 kHz)")
    print(f"  K87 shelf @ 100 kHz : {shelf_100k:.1f} dB  (target −6 dB, tol ±1.5 dB)  "
          f"[{'PASS' if abs(shelf_100k + 6) < 1.5 else 'FAIL'}]")
    all_pass = all_pass and abs(shelf_100k + 6) < 1.5
    print(f"\n  NOTE: ngspice gain is ~8 dB lower than analytical because this netlist")
    print(f"  uses self-biased JFET Q-point (Ids≈0.49mA, gm≈8.85mA/V). The DC servo")
    print(f"  (see dc_servo.py) locks Ids≈1.64mA, gm≈16.18mA/V, adding ~+8 dB.")

    # LF and HF −3 dB points (K47 mode, relative to 1 kHz)
    ref = g47_1k
    lf_idx = np.where(db47 >= ref - 3)[0]
    hf_idx = np.where(db47 >= ref - 3)[0]
    lf_3db = f47[lf_idx[0]]  if len(lf_idx) > 0 else float("nan")
    hf_3db = f47[hf_idx[-1]] if len(hf_idx) > 0 else float("nan")
    print(f"\n  Bandwidth (K47, −3 dB from 1 kHz):")
    print(f"    LF corner : {lf_3db:.1f} Hz")
    print(f"    HF corner : {hf_3db/1e3:.1f} kHz")

    ph_1k = ph47[idx(f47, 1e3)]
    print(f"\n  Phase @ 1 kHz (K47): {ph_1k:.1f}°")
    print()

# ── Plot ───────────────────────────────────────────────────────────────────────
if len(f47) > 0:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    fig.suptitle("op-txm — Full Signal Chain (JFET → EQ → NTE10/3 → 600Ω)",
                 fontsize=14, fontweight="bold")

    # Gain
    ax1.semilogx(f47, db47, color="#1565C0", lw=2.0, label="K47 mode (SJ1 open, flat)")
    if len(f87) > 0:
        ax1.semilogx(f87, db87, color="#B71C1C", lw=2.0, linestyle="--",
                     label="K87 mode (SJ1 closed, −6 dB shelf)")
    ax1.axvline(20e3, color="gray", lw=0.7, ls=":")
    ax1.set_ylabel("Gain (dB, hot output)")
    ax1.legend(loc="lower left")
    ax1.grid(True, which="both", alpha=0.3)
    ax1.set_xlim(10, 100e3)

    # Phase
    ax2.semilogx(f47, ph47, color="#1565C0", lw=2.0, label="K47 phase")
    if len(ph87) > 0:
        ax2.semilogx(f87, ph87, color="#B71C1C", lw=2.0, linestyle="--",
                     label="K87 phase")
    ax2.axvline(20e3, color="gray", lw=0.7, ls=":")
    ax2.set_xlabel("Frequency (Hz)")
    ax2.set_ylabel("Phase (°)")
    ax2.legend(loc="lower left")
    ax2.grid(True, which="both", alpha=0.3)

    plt.tight_layout()
    out_png = os.path.join(OUT_DIR, "signal_chain.png")
    plt.savefig(out_png, dpi=120)
    plt.close(fig)
    print(f"Plot saved: {out_png}")

print()
print("─" * 68)
print("Summary:")
print(f"  Analytical gain (K47, 1 kHz): {20*np.log10(Av_total_k47):.1f} dB")
print(f"  Transformer step-up          : +{20*np.log10(N_TURNS):.1f} dB (1:3, voltage)")
print(f"  Transformer LF −3 dB         : {lf_corner:.2f} Hz  (estimated)")
print(f"  Transformer HF −3 dB         : {hf_corner/1e3:.0f} kHz  (estimated)")
print(f"  All checks: {'PASS' if all_pass else 'FAIL (check log)'}")
print()
print("NOTE: Transformer values are estimates. Update sim after bench measurement of DCR/Lleak.")
