"""
op-txm Full Signal-Chain Simulation
=========================================
AC sweep of the complete signal path:

  Capsule (K87, 50 pF)
    → JFET buffer (MMBF170, Rd=22kΩ, Rs=1kΩ, Vhv=72V)
    → DC-coupling cap (1 µF)
    → EQ stage (OPA1642 macromodel, K47 flat or K87 −6 dB shelf)
    → NTE10/3 output transformer (1:3 step-up, estimated parameters)
    → Differential 600 Ω XLR load

No optical compressor.  One operating point; two EQ modes.

JFET Q-point
-------------
The DC servo (see dc_servo.py) locks Vdrain=36V → Ids=1.636mA, gm=16.18mA/V.
For accurate AC analysis, VTO_SIM is chosen so the JFET self-biases at the
servo-locked operating point with Rs=1kΩ (real VTO=-0.60V, VTO_SIM=-1.8382V).
This gives the correct linearised gm without modelling the servo integrator.

Transformer connection
-----------------------
  Reversed 3:1 — op-amp drives 3× winding (secondary, 720 H), XLR output
  from 1× winding (primary, 80 H).  Standard Neumann/AKG practice:
    · Op-amp load : 600 Ω × 9 = 5.4 kΩ  (easy drive, full headroom)
    · Zout at XLR : ≈ 61 Ω  (DCR_pri + reflected, excellent for cable)
    · Voltage gain through TX: ×(1/3) = −9.5 dB

  L_pri = 80 H  (community bench measurement; verify with LCR meter)
  n = 3  (1:3 tap)  →  L_sec = 720 H  (3× winding, driven winding)
  k ≈ 0.999997  (leakage ~0.5 mH referred to primary → HF −3dB estimated)
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
BETA_JFT  = 40e-3       # A/V²  (real device parameter)
# VTO_SIM ≠ real VTO. Chosen so JFET self-biases at servo-locked point with Rs=1kΩ:
#   Ids_target = (72-36)/22k = 1.636mA, Vgs = -Ids×Rs = -1.636V
#   1.636e-3 = BETA × (-1.636 - VTO_SIM)² → VTO_SIM = -1.636 - √(0.0409) = -1.8382V
VTO_JFT   = -1.8382     # V  (adjusted for servo-locked Q-point; real VTO = -0.60V)
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
# Reversed 3:1: op-amp drives 3× winding, XLR from 1× winding → step-DOWN
Av_tx = 1.0 / N_TURNS  # voltage step-down (−9.5 dB)

# Loading on 1× output winding: R_load_diff = 2 × R_LOAD_EACH = 1200 Ω
# Insertion loss from winding DCRs (referred to output winding):
R_load_diff = 2 * R_LOAD_EACH
# DCR_SEC is on the input side; DCR_PRI is on the output side
r_ins_loss = R_load_diff / (R_load_diff + DCR_PRI + DCR_SEC / N_TURNS ** 2)
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

# Reversed 3:1: driven winding is 3× (L_SEC), output winding is 1× (L_PRI)
# LF corner: driven by L_SEC (720H) with DCR_SEC in series, 600Ω load reflected
R_load_refl = R_load_diff / N_TURNS**2   # 1200/9 = 133Ω reflected to driven (3×) winding
lf_corner = (DCR_SEC + R_load_refl) / (2 * np.pi * L_SEC)
# HF corner: leakage referred to driven (3×) winding = L_LEAK × N² (if L_LEAK given at 1× side)
L_LEAK_SEC = L_LEAK * N_TURNS**2
hf_corner = R_load_diff / (2 * np.pi * L_LEAK_SEC)
print(f"\nTransformer bandwidth (estimated, reversed 3:1):")
print(f"  LF −3 dB : {lf_corner:.2f} Hz  (Ldriven={L_SEC:.0f} H, driven winding = 3×)")
print(f"  HF −3 dB : {hf_corner/1e3:.1f} kHz  (Lleak_sec={L_LEAK_SEC*1e3:.1f} mH, referred to 3× winding)")
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

* ── NTE10/3 transformer — reversed 3:1 (op-amp drives 3× winding → XLR from 1× winding)
* This is the standard Neumann/AKG approach: the high-turn winding sees the buffer,
* the low-turn winding drives the XLR cable.
*   Op-amp load : 600Ω × (3/1)² = 5.4 kΩ  (easy, full headroom)
*   Zout at XLR : (Zop + DCR_sec)/9 + DCR_pri ≈ 61 Ω  (excellent for cable drive)
*   Voltage     : V_xlr = V_opamp / 3  (−9.5 dB, compensated by JFET+EQ gain)
* Estimated parameters — update DCR_PRI, DCR_SEC, L_LEAK after bench measurement
Rdcr_in   eq_out   txs_hi  {DCR_SEC:.4g}
Lsec      txs_hi   txs_lo  {L_SEC}H
Lpri      txp_hi   txp_lo  {L_PRI}H
Ktx       Lpri Lsec  {K_COUPLE:.8f}
Rdcr_out  txp_hi   vout_h  {DCR_PRI:.4g}
* Driven winding (3×) return to GND
Vtx_gnd   txs_lo   0  DC 0

* ── Balanced 600 Ω load on 1× output winding ──────────────────────────────────
Rload_h  vout_h  vcm  {R_LOAD_EACH}
Rload_c  txp_lo  vcm  {R_LOAD_EACH}
Vcm      vcm     0    DC 0

* Differential output probe: vdiff = vout_h − txp_lo
Ediff    vdiff   0    vout_h txp_lo  1

.op
.ac dec 100 10 100k
.print ac vdb(vout_h) vp(vout_h) vdb(txp_lo) vp(txp_lo)
.print ac vdb(vdiff) vp(vdiff)
.end
"""
    with open(path, "w") as fh:
        fh.write(netlist)


def run_ngspice(cir: str, log: str) -> int:
    r = subprocess.run(["ngspice", "-b", "-o", log, cir],
                       capture_output=True, text=True)
    return r.returncode


def parse_log(log: str):
    """Parse ngspice AC output.

    Returns (freqs, vdb_hot, phase_hot, freqs_d, vdb_diff, phase_diff).
    ngspice writes 4-column rows (index freq vdb vp) in multiple 57-row blocks.
    Two print sections are parsed: vdb(vout_h) for hot-leg gain and vdb(vdiff)
    for differential gain.
    """
    freqs, vdb_h, vph_h = [], [], []
    freqs_d, vdb_d, vph_d = [], [], []
    in_hot = False
    in_diff = False
    try:
        with open(log) as fh:
            for line in fh:
                s = line.strip()
                if "vdb(vout_h)" in s.lower():
                    in_hot = True
                    in_diff = False
                    continue
                if "vdb(txp_lo)" in s.lower():
                    in_hot = False
                    continue
                if "vdb(vdiff)" in s.lower():
                    in_diff = True
                    in_hot = False
                    continue
                if s.startswith("---") or s.startswith("Index"):
                    continue
                if not (in_hot or in_diff):
                    continue
                parts = s.split()
                if len(parts) < 4:
                    continue
                try:
                    int(parts[0])
                except ValueError:
                    continue
                if in_hot:
                    freqs.append(float(parts[1]))
                    vdb_h.append(float(parts[2]))
                    vph_h.append(float(parts[3]))
                else:
                    freqs_d.append(float(parts[1]))
                    vdb_d.append(float(parts[2]))
                    vph_d.append(float(parts[3]))
    except FileNotFoundError:
        pass
    return (np.array(freqs), np.array(vdb_h), np.rad2deg(np.array(vph_h)),
            np.array(freqs_d), np.array(vdb_d), np.rad2deg(np.array(vph_d)))


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
        freqs, vdb, phase, freqs_d, vdb_d, phase_d = parse_log(log)
        n = len(freqs)
        nd = len(freqs_d)
        print(f"  {mode.upper():4s}  →  {n} hot pts  {nd} diff pts  "
              f"[{'OK' if n > 0 and nd > 0 else 'no data — check log'}]")
        results[mode] = (freqs, vdb, phase, freqs_d, vdb_d, phase_d)
    else:
        print("  ngspice not found — install: sudo pacman -S ngspice")
        results[mode] = (np.array([]),) * 6


def idx(freqs, f):
    return int(np.argmin(np.abs(freqs - f)))


# ── Report ─────────────────────────────────────────────────────────────────────
all_pass = True
have_diff = False
f47, db47, ph47, fd47, dbd47, phd47 = results["k47"]
f87, db87, ph87, fd87, dbd87, phd87 = results["k87"]

if len(f47) > 0 and len(f87) > 0:
    print()
    print(SEP)
    print("Results — ngspice AC")
    print(SEP)

    # Differential gain (primary metric)
    have_diff = len(fd47) > 0 and len(fd87) > 0
    if have_diff:
        gd47_1k   = dbd47[idx(fd47, 1e3)]
        gd47_20k  = dbd47[idx(fd47, 20e3)]
        gd47_100k = dbd47[idx(fd47, 100e3)]
        gd87_1k   = dbd87[idx(fd87, 1e3)]
        gd87_20k  = dbd87[idx(fd87, 20e3)]
        gd87_100k = dbd87[idx(fd87, 100e3)]
        shelf_20k  = gd87_20k  - gd47_20k
        shelf_100k = gd87_100k - gd47_100k
        print(f"\n  Differential gain @ 1 kHz   : K47 = {gd47_1k:.1f} dB  |  K87 = {gd87_1k:.1f} dB")
        print(f"  Differential gain @ 20 kHz  : K47 = {gd47_20k:.1f} dB  |  K87 = {gd87_20k:.1f} dB")
        print(f"  Differential gain @ 100 kHz : K47 = {gd47_100k:.1f} dB  |  K87 = {gd87_100k:.1f} dB")
    else:
        # Fall back to single-ended hot leg
        gd47_1k = db47[idx(f47, 1e3)]
        gd47_20k = db47[idx(f47, 20e3)]
        gd47_100k = db47[idx(f47, 100e3)]
        gd87_1k = db87[idx(f87, 1e3)]
        gd87_20k = db87[idx(f87, 20e3)]
        gd87_100k = db87[idx(f87, 100e3)]
        shelf_20k  = gd87_20k  - gd47_20k
        shelf_100k = gd87_100k - gd47_100k
        print(f"\n  Hot-leg gain @ 1 kHz   : K47 = {gd47_1k:.1f} dB  |  K87 = {gd87_1k:.1f} dB")
        print(f"  Hot-leg gain @ 20 kHz  : K47 = {gd47_20k:.1f} dB  |  K87 = {gd87_20k:.1f} dB")
        print(f"  Hot-leg gain @ 100 kHz : K47 = {gd47_100k:.1f} dB  |  K87 = {gd87_100k:.1f} dB")

    print(f"  K87 shelf @ 20 kHz  : {shelf_20k:.1f} dB  (expected ~−3.7 dB; shelf corner = 22.6 kHz)")
    print(f"  K87 shelf @ 100 kHz : {shelf_100k:.1f} dB  (target −6 dB, tol ±1.5 dB)  "
          f"[{'PASS' if abs(shelf_100k + 6) < 1.5 else 'FAIL'}]")
    all_pass = all_pass and abs(shelf_100k + 6) < 1.5
    print(f"\n  Q-point: servo-locked (VTO_SIM=-1.8382V → Ids=1.636mA, gm=16.18mA/V).")

    # LF and HF −3 dB points (K47 mode, relative to 1 kHz)
    ref_d = gd47_1k
    plot_f  = fd47 if have_diff else f47
    plot_db = dbd47 if have_diff else db47
    lf_idx = np.where(plot_db >= ref_d - 3)[0]
    hf_idx = np.where(plot_db >= ref_d - 3)[0]
    lf_3db = plot_f[lf_idx[0]]  if len(lf_idx) > 0 else float("nan")
    hf_3db = plot_f[hf_idx[-1]] if len(hf_idx) > 0 else float("nan")
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

    # Gain — prefer differential output; fall back to hot leg
    pf47 = fd47 if have_diff else f47
    pd47 = dbd47 if have_diff else db47
    pf87 = fd87 if have_diff else f87
    pd87 = dbd87 if have_diff else db87
    gain_label = "differential" if have_diff else "hot output"

    ax1.semilogx(pf47, pd47, color="#1565C0", lw=2.0, label=f"K47 mode (SJ1 open, flat)")
    if len(pf87) > 0:
        ax1.semilogx(pf87, pd87, color="#B71C1C", lw=2.0, linestyle="--",
                     label=f"K87 mode (SJ1 closed, −6 dB shelf)")
    ax1.axvline(20e3, color="gray", lw=0.7, ls=":")
    ax1.set_ylabel(f"Gain (dB, {gain_label})")
    ax1.legend(loc="lower left")
    ax1.grid(True, which="both", alpha=0.3)
    ax1.set_xlim(10, 100e3)

    # Phase (hot-leg phase is accurate; differential phase is identical for balanced TX)
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
print(f"  Transformer step-down        : {20*np.log10(1/N_TURNS):.1f} dB (reversed 3:1, Zout≈61Ω)")
print(f"  Transformer LF −3 dB         : {lf_corner:.2f} Hz  (estimated)")
print(f"  Transformer HF −3 dB         : {hf_corner/1e3:.0f} kHz  (estimated)")
print(f"  All checks: {'PASS' if all_pass else 'FAIL (check log)'}")
print()
print("NOTE: Transformer values are estimates. Update sim after bench measurement of DCR/Lleak.")
