"""pcb/layout.py — op-txm PCB Layout (KiCad 10, code-driven via kiutils)
=========================================================================
Generates pcb/op-txm.kicad_pcb from the parametric outline.

Board: 35 mm (W) × 85 mm (L)  — compact mic form factor
Canvas centre: (100, 100) mm    — board spans X=[82.5,117.5], Y=[57.5,142.5]

Signal flow (Y-axis, top → bottom):
  Input zone  Y=[60,72]   Capsule TH pads + JFET input (quiet end)
  GAP         Y=[72,74]   Noise isolation buffer
  Audio zone  Y=[74,93]   OPA1642 EQ + DC servo + decoupling
  GAP         Y=[93,100]  HV isolation buffer
  Power zone  Y=[100,122] Power (LR8, TPS7A3901, charge pump)
  TX area     Y=[122,135] Transformer TH pads + XLR pads + bobbin cutout

Usage
-----
    .venv/bin/python pcb/layout.py

Outputs
-------
    pcb/op-txm.kicad_pcb   — KiCad 10 PCB file
    pcb/op_txm_layout.png  — matplotlib preview
"""

import math
import uuid as _uuid
from pathlib import Path

from kiutils.board import Board
from kiutils.footprint import (
    Footprint, Pad, DrillDefinition,
    FpText, FpRect, FpLine, Net, Position,
)
from kiutils.items.brditems import Via, Segment
from kiutils.items.zones import Zone, ZonePolygon, FillSettings, Hatch
from kiutils.items.common import Effects, Font, Justify

# ---------------------------------------------------------------------------
# Board geometry
# ---------------------------------------------------------------------------
CX, CY   = 100.0, 100.0
BOARD_W  = 35.0
BOARD_H  = 85.0

BOUNDS_MIN_X = CX - BOARD_W / 2   # 82.5
BOUNDS_MAX_X = CX + BOARD_W / 2   # 117.5
BOUNDS_MIN_Y = CY - BOARD_H / 2   # 57.5
BOUNDS_MAX_Y = CY + BOARD_H / 2   # 142.5

SAFE_MARGIN = 3.5
SAFE_MIN_X  = BOUNDS_MIN_X + SAFE_MARGIN   # 86.0
SAFE_MAX_X  = BOUNDS_MAX_X - SAFE_MARGIN   # 114.0
SAFE_MIN_Y  = BOUNDS_MIN_Y + 2.0           # 59.5
SAFE_MAX_Y  = BOUNDS_MAX_Y - 2.0           # 140.5

ZONE_INPUT  = (86.0,  60.0, 114.0,  72.0)
ZONE_AUDIO  = (86.0,  74.0, 114.0,  93.0)
ZONE_POWER  = (86.0, 100.0, 114.0, 122.0)

FIDUCIAL_POS = [(87.0, 62.0), (113.0, 62.0), (113.0, 103.0)]

MHOLE_POS = [
    ( 85.0,  60.0),   # top-left
    (115.0,  60.0),   # top-right
    ( 85.0, 140.0),   # bottom-left
    (115.0, 140.0),   # bottom-right
]
MHOLE_R = 5.0   # keepout radius mm

# ---------------------------------------------------------------------------
# Net table
# ---------------------------------------------------------------------------
NETS = {
    "GND":        1,
    "PHANTOM":    2,
    "V_BOOST":    3,
    "P15V":       4,
    "N15V":       5,
    "VGATE":      6,
    "VSOURCE":    7,
    "VDRAIN":     8,
    "SIG_EQ":     9,     # EQ op-amp output → transformer driven winding
    "SRV_OUT":    10,    # DC servo output → gate injection
    "SRV_INT":    11,    # servo integrator node
    "P48V_LDO":   12,    # LR8 output (35.2V)
    "LR8_ADJ":    13,
    "TPS_FB_POS": 14,
    "TPS_FB_NEG": 15,
    "TX_DRV_HOT": 16,    # 3× secondary hot (op-amp side)
    "TX_DRV_RTN": 17,    # 3× secondary return
    "XLR_HOT":    18,    # XLR pin 2 — from 1× primary
    "XLR_COLD":   19,    # XLR pin 3 — from 1× primary
    "BP_CAPSULE": 20,    # back-plate bias (V_BOOST via R_GBIAS)
    "FP_CAPSULE": 21,    # front-plate signal (→ VGATE)
}

# ---------------------------------------------------------------------------
# Routing constants
# ---------------------------------------------------------------------------
W_HV     = 0.40   # HV traces (PHANTOM, V_BOOST, BP_CAPSULE) mm
W_POWER  = 0.30   # Power rails (P48V_LDO, P15V, N15V, GND) mm
W_SIGNAL = 0.20   # Audio signal mm
W_HIMP   = 0.15   # High-Z (VGATE, FP_CAPSULE) mm
VIA_SIZE  = 0.60
VIA_DRILL = 0.30
HV_CLEAR  = 1.20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clamp(x, y):
    return (max(SAFE_MIN_X, min(SAFE_MAX_X, x)),
            max(SAFE_MIN_Y, min(SAFE_MAX_Y, y)))


def _pos(x, y):   return Position(X=x, Y=y)
def _net(name):
    if not name:
        return None
    return Net(number=NETS[name], name=name)

_SILK_FONT    = Font(height=0.6, width=0.6, thickness=0.12)
_SILK_EFFECTS = Effects(font=_SILK_FONT)


def _ref(text, dx=0, dy=-1.2, layer="F.SilkS"):
    t = FpText(); t.type = "reference"; t.text = text
    t.position = _pos(dx, dy); t.layer = layer
    j = Justify()
    if dx > 1.0:   j.horizontally = "left"
    elif dx < -1.0: j.horizontally = "right"
    t.effects = Effects(font=Font(height=0.6, width=0.6, thickness=0.12), justify=j)
    return t


def _val(text, dx=0, dy=1.0, layer="F.Fab"):
    t = FpText(); t.type = "value"; t.text = text
    t.position = _pos(dx, dy); t.layer = layer
    t.hide = True
    t.effects = Effects(font=Font(height=0.6, width=0.6, thickness=0.12))
    return t


def _crtyd(x0, y0, x1, y1):
    r = FpRect(); r.start = _pos(x0, y0); r.end = _pos(x1, y1)
    r.layer = "F.CrtYd"; r.width = 0.05; return r


def _fab_rect(x0, y0, x1, y1):
    r = FpRect(); r.start = _pos(x0, y0); r.end = _pos(x1, y1)
    r.layer = "F.Fab"; r.width = 0.1; return r


def _smd(num, x, y, w, h, net="", shape="roundrect"):
    p = Pad()
    p.number = str(num); p.type = "smd"; p.shape = shape
    p.position = _pos(x, y); p.size = _pos(w, h)
    p.layers = ["F.Cu", "F.Paste", "F.Mask"]
    if shape == "roundrect":
        p.roundrectRatio = 0.25
    p.net = _net(net)
    return p


def _thru(num, x, y, diameter, drill, net=""):
    p = Pad()
    p.number = str(num); p.type = "thru_hole"; p.shape = "circle"
    p.position = _pos(x, y); p.size = _pos(diameter, diameter)
    p.drill = DrillDefinition(oval=False, diameter=drill)
    p.layers = ["*.Cu", "*.Mask"]
    p.net = _net(net)
    return p


def _npth(x, y, drill):
    p = Pad()
    p.number = ""; p.type = "np_thru_hole"; p.shape = "circle"
    p.position = _pos(x, y); p.size = _pos(drill, drill)
    p.drill = DrillDefinition(oval=False, diameter=drill)
    p.layers = ["*.Cu", "*.Mask"]
    return p


def _fp(ref, value, x, y, angle=None, graphics=None, pads=None):
    x, y = clamp(x, y)
    fp = Footprint()
    fp.libraryNickname = "op-txm"
    fp.entryName = value
    fp.layer = "F.Cu"
    fp.position = Position(X=x, Y=y, angle=angle, unlocked=False)
    fp.description = value
    fp.graphicItems = list(graphics or [])
    fp.pads = list(pads or [])
    return fp


def _gnd_via(x, y):
    return Via(
        position=Position(X=x, Y=y),
        size=VIA_SIZE, drill=VIA_DRILL,
        layers=["F.Cu", "B.Cu"],
        net=NETS["GND"],
        tstamp=str(_uuid.uuid4()),
    )


def _net_via(x, y, net_name):
    return Via(
        position=Position(X=x, Y=y),
        size=VIA_SIZE, drill=VIA_DRILL,
        layers=["F.Cu", "B.Cu"],
        net=NETS[net_name],
        tstamp=str(_uuid.uuid4()),
    )


def _seg(x0, y0, x1, y1, net_name, width=W_SIGNAL, layer="F.Cu"):
    s = Segment()
    s.start = Position(X=x0, Y=y0)
    s.end   = Position(X=x1, Y=y1)
    s.width = width
    s.layer = layer
    s.net   = NETS[net_name]
    s.tstamp = str(_uuid.uuid4())
    return s


# ---------------------------------------------------------------------------
# Component footprint builders
# ---------------------------------------------------------------------------

def fiducial(ref, x, y):
    return _fp(ref, "Fiducial", x, y,
        graphics=[_crtyd(-1.5, -1.5, 1.5, 1.5)],
        pads=[
            _smd(1, 0, 0, 1.0, 1.0, "", "circle"),
        ])


def capsule_pad(ref, net, x, y):
    """0.8 mm drill TH pad for capsule wire (front plate or back plate)."""
    return _fp(ref, "CapsulePad", x, y,
        graphics=[_crtyd(-1.0, -1.0, 1.0, 1.0),
                  _ref(ref, dx=1.2)],
        pads=[_thru(1, 0, 0, 1.5, 0.8, net)])


def th_pad(ref, net, x, y, drill=1.0, ring=2.5):
    """Generic through-hole pad — transformer leads, XLR wires."""
    return _fp(ref, "THPad", x, y,
        graphics=[_crtyd(-ring/2-0.3, -ring/2-0.3, ring/2+0.3, ring/2+0.3),
                  _ref(ref, dx=ring/2+0.4)],
        pads=[_thru(1, 0, 0, ring, drill, net)])


def npth_slot(ref, x, y, drill=2.5):
    """NPTH zip-tie slot for transformer body retention."""
    return _fp(ref, "NPTH_Slot", x, y,
        graphics=[_crtyd(-2.0, -2.0, 2.0, 2.0),
                  _ref(ref, dx=2.2)],
        pads=[_npth(0, 0, drill)])


def sot23(ref, value, p1_net, p2_net, p3_net, x, y):
    """SOT-23-3: pin1=left-bottom, pin2=right-bottom, pin3=top.
    MMBF170LT1G: pin1=Gate, pin2=Source, pin3=Drain.
    Pad dimensions match KiCad standard SOT-23 footprint (1.0×1.4 mm at ±1.30 mm).
    """
    return _fp(ref, value, x, y,
        graphics=[
            _crtyd(-1.5, -1.9, 1.5, 2.0),
            _fab_rect(-0.65, -0.9, 0.65, 0.55),
            _ref(ref, dx=0, dy=-2.8),
        ],
        pads=[
            _smd(1, -0.95,  1.30, 1.0, 1.4, p1_net),  # pin1: Gate  (MMBF170)
            _smd(2,  0.95,  1.30, 1.0, 1.4, p2_net),  # pin2: Source (MMBF170)
            _smd(3,  0.00, -1.30, 1.0, 1.4, p3_net),  # pin3: Drain  (MMBF170)
        ])


def r0402(ref, value, net1, net2, x, y):
    """0402 resistor or capacitor."""
    return _fp(ref, value, x, y,
        graphics=[
            _crtyd(-1.3, -0.7, 1.3, 0.7),
            _fab_rect(-0.5, -0.25, 0.5, 0.25),
            _ref(ref, dx=0, dy=-0.9),
        ],
        pads=[
            _smd(1, -0.575, 0, 0.6, 0.55, net1),
            _smd(2,  0.575, 0, 0.6, 0.55, net2),
        ])


def r0603(ref, value, net1, net2, x, y):
    """0603 capacitor (for larger values: 10µF, 4.7µF)."""
    return _fp(ref, value, x, y,
        graphics=[
            _crtyd(-1.8, -1.0, 1.8, 1.0),
            _fab_rect(-0.75, -0.4, 0.75, 0.4),
            _ref(ref, dx=0, dy=-1.2),
        ],
        pads=[
            _smd(1, -1.05, 0, 0.8, 0.8, net1),
            _smd(2,  1.05, 0, 0.8, 0.8, net2),
        ])


def r0805(ref, value, net1, net2, x, y):
    """0805 (used for R_GBIAS 10MΩ — larger body for high-voltage handling)."""
    return _fp(ref, value, x, y,
        graphics=[
            _crtyd(-2.2, -1.2, 2.2, 1.2),
            _fab_rect(-1.0, -0.6, 1.0, 0.6),
            _ref(ref, dx=0, dy=-1.5),
        ],
        pads=[
            _smd(1, -1.1, 0, 1.0, 1.1, net1),
            _smd(2,  1.1, 0, 1.0, 1.1, net2),
        ])


def soic8(ref, value, nets8, x, y):
    """SOIC-8: pins 1-4 left side (top to bottom), 5-8 right side (bottom to top).
    nets8: list of 8 net names, index 0=pin1 ... index 7=pin8.
    """
    PITCH = 1.27
    PAD_W, PAD_H = 1.55, 0.6
    pads = []
    for i in range(4):
        py = -PITCH * 1.5 + i * PITCH
        pads.append(_smd(i + 1, -2.7, py, PAD_W, PAD_H, nets8[i]))
    for i in range(4):
        py = PITCH * 1.5 - i * PITCH
        pads.append(_smd(i + 5, 2.7, py, PAD_W, PAD_H, nets8[i + 4]))
    return _fp(ref, value, x, y,
        graphics=[
            _crtyd(-4.0, -2.8, 4.0, 2.8),
            _fab_rect(-2.05, -2.7, 2.05, 2.7),
            _ref(ref, dx=-4.2, dy=0),
        ],
        pads=pads)


def sot89(ref, value, p1_net, p2_net, p3_net, tab_net, x, y):
    """SOT-89-3: pin1=ADJ, pin2=OUT, pin3=IN; tab=IN (large).
    Pin row at Y=+2.0, tab at Y=-2.0.
    """
    return _fp(ref, value, x, y,
        graphics=[
            _crtyd(-2.5, -3.0, 2.5, 3.0),
            _fab_rect(-2.0, -2.5, 2.0, 2.5),
            _ref(ref, dx=-2.8, dy=0),
        ],
        pads=[
            _smd(1, -1.5,  2.0, 1.0, 1.8, p1_net),   # ADJ
            _smd(2,  0.0,  2.0, 1.0, 1.8, p2_net),   # OUT
            _smd(3,  1.5,  2.0, 1.0, 1.8, p3_net),   # IN
            _smd(4,  0.0, -2.0, 3.6, 2.0, tab_net),  # tab (IN)
        ])


def wson12(ref, value, nets12, x, y):
    """WSON-12 3×3 mm: 6 pads left, 6 pads right + exposed pad (EP) centre.
    nets12: 12 net names (index 0=pin1 .. 11=pin12); index 12 = EP net.
    Pitch 0.5 mm.
    """
    PITCH = 0.5
    PAD_W, PAD_H = 0.4, 0.25
    pads = []
    for i in range(6):
        py = -PITCH * 2.5 + i * PITCH
        pads.append(_smd(i + 1,    -1.65, py, PAD_H, PAD_W, nets12[i]))
    for i in range(6):
        py = PITCH * 2.5 - i * PITCH
        pads.append(_smd(i + 7,     1.65, py, PAD_H, PAD_W, nets12[i + 6]))
    ep_net = nets12[12] if len(nets12) > 12 else ""
    pads.append(_smd("EP", 0, 0, 1.7, 1.7, ep_net, shape="rect"))
    return _fp(ref, value, x, y,
        graphics=[
            _crtyd(-2.0, -2.0, 2.0, 2.0),
            _fab_rect(-1.5, -1.5, 1.5, 1.5),
            _ref(ref, dx=-2.2, dy=0),
        ],
        pads=pads)


def gnd_zone(board):
    """Add a B.Cu GND fill zone covering the full board."""
    EDGE_CLEARANCE = 1.0   # pour pullback from board edge (burr-short prevention)
    z = Zone(
        net=NETS["GND"],
        netName="GND",
        layers=["B.Cu"],
        tstamp=str(_uuid.uuid4()),
        name="GND_Plane_BCu",
        hatch=Hatch(style="edge", pitch=0.508),
        clearance=0.254,
        minThickness=0.25,
        fillSettings=FillSettings(
            yes=True,
            thermalGap=0.5,
            thermalBridgeWidth=0.5,
            islandRemovalMode=1,
        ),
    )
    corners = [
        Position(X=BOUNDS_MIN_X + EDGE_CLEARANCE, Y=BOUNDS_MIN_Y + EDGE_CLEARANCE),
        Position(X=BOUNDS_MAX_X - EDGE_CLEARANCE, Y=BOUNDS_MIN_Y + EDGE_CLEARANCE),
        Position(X=BOUNDS_MAX_X - EDGE_CLEARANCE, Y=BOUNDS_MAX_Y - EDGE_CLEARANCE),
        Position(X=BOUNDS_MIN_X + EDGE_CLEARANCE, Y=BOUNDS_MAX_Y - EDGE_CLEARANCE),
    ]
    z.polygons.append(ZonePolygon(coordinates=corners))
    board.zones.append(z)


# ---------------------------------------------------------------------------
# build_layout
# ---------------------------------------------------------------------------

def build_layout():
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent))
    from outline import generate_board as _gen_outline

    pcb_path = Path(__file__).parent / "op-txm.kicad_pcb"
    pcb_path.write_text(_gen_outline())

    b = Board.from_file(str(pcb_path))
    b.version = 20260206

    for fp in b.footprints:
        for pad in fp.pads:
            if pad.type == "type":
                pad.type  = "np_thru_hole"
                pad.shape = "circle"

    for name, number in sorted(NETS.items(), key=lambda kv: kv[1]):
        b.nets.append(Net(number=number, name=name))

    components = []
    segments   = []
    vias       = []

    # ── Fiducials ──────────────────────────────────────────────────────────
    for i, (fx, fy) in enumerate(FIDUCIAL_POS, 1):
        components.append(fiducial(f"FID{i}", fx, fy))

    # ══════════════════════════════════════════════════════════════════════
    # INPUT ZONE  Y=[60,72]  — Capsule interface + JFET
    # ══════════════════════════════════════════════════════════════════════

    # Capsule pads (Y≈62, PCB head — same Y as top mounting holes, different X)
    # FP: front-plate signal → VGATE via C_IN
    # BP: back-plate bias (V_BOOST via R_GBIAS — sets capsule polarisation)
    components.append(capsule_pad("FP",         "FP_CAPSULE",  93.0, 62.0))
    components.append(capsule_pad("BP",         "BP_CAPSULE", 100.0, 62.0))
    components.append(capsule_pad("GND_SHIELD", "GND",        107.0, 62.0))

    # Q1: MMBF170LT1G SOT-23 (pin1=S, pin2=G, pin3=D in SOT-23 pinout)
    # MMBF170 SOT-23 pinout: 1=Gate, 2=Source, 3=Drain (check datasheet!)
    # Placed Y=66 — below capsule pads
    components.append(sot23("Q1", "MMBF170LT1G",
                             "VGATE", "VSOURCE", "VDRAIN",
                             100.0, 66.0))

    # R_GBIAS: 10 MΩ 0805 — BP_CAPSULE → VGATE (sets capsule polarisation bias)
    # Large body for high-voltage handling; isolate from signal traces
    components.append(r0805("R_GBIAS", "10M",
                             "BP_CAPSULE", "VGATE", 93.0, 65.0))

    # C_IN: 10 nF 0402 — FP_CAPSULE → VGATE coupling cap (AC, blocks capsule DC)
    components.append(r0402("C_IN", "10n",
                             "FP_CAPSULE", "VGATE", 93.0, 69.0))

    # R_D: 22 kΩ 0402 — VDRAIN → V_BOOST (drain load resistor)
    components.append(r0402("R_D", "22k",
                             "VDRAIN", "V_BOOST", 107.0, 65.0))

    # R_S: 1 kΩ 0402 — VSOURCE → GND (source degeneration for servo lock)
    components.append(r0402("R_S", "1k",
                             "VSOURCE", "GND", 107.0, 69.0))

    # D_RS: HSMS-2820 SOT-23 Schottky — anode=GND, cathode=VSOURCE
    # Clamps across R_S to protect JFET gate-source during power transients
    components.append(sot23("D_RS", "HSMS-2820",
                             "GND", "GND", "VSOURCE",
                             111.0, 67.0))

    # ══════════════════════════════════════════════════════════════════════
    # AUDIO ZONE  Y=[74,93]  — OPA1642 EQ + DC Servo
    # ══════════════════════════════════════════════════════════════════════

    # U1: OPA1642AIDR SOIC-8
    # OPA1642 pinout (dual op-amp):
    #   Pin 1: OUT_A   Pin 2: IN-_A  Pin 3: IN+_A  Pin 4: V-
    #   Pin 5: IN+_B   Pin 6: IN-_B  Pin 7: OUT_B  Pin 8: V+
    # Section A = EQ (inverting), Section B = DC servo
    opa_nets = [
        "SIG_EQ",    # pin1: OUT_A (EQ output → transformer)
        "SIG_EQ",    # pin2: IN-_A (inverting; EQ feedback)
        "GND",       # pin3: IN+_A (non-inverting = AC GND via cap)
        "N15V",      # pin4: V-
        "GND",       # pin5: IN+_B (servo non-inverting = VREF)
        "SRV_INT",   # pin6: IN-_B (servo inverting = integrator node)
        "SRV_OUT",   # pin7: OUT_B (servo output → gate injection)
        "P15V",      # pin8: V+
    ]
    components.append(soic8("U1", "OPA1642AIDR", opa_nets, 100.0, 81.0))

    # EQ components (Section A) — cluster around U1 left side
    # R_IN: 10 kΩ — VSOURCE → IN-_A  (input summing resistor)
    components.append(r0402("R_IN", "10k",
                             "VSOURCE", "SIG_EQ", 91.0, 77.5))

    # R_F: 47 kΩ — OUT_A → IN-_A  (feedback; K47 mode)
    components.append(r0402("R_F", "47k",
                             "SIG_EQ", "SIG_EQ", 91.0, 80.0))

    # R_SHELF: 47 kΩ — in series with C_DEEMPH across R_F (K87 de-emphasis)
    components.append(r0402("R_SHELF", "47k",
                             "SIG_EQ", "SIG_EQ", 91.0, 82.5))

    # C_DEEMPH: 150 pF — de-emphasis shelf cap
    components.append(r0402("C_DEEMPH", "150p",
                             "SIG_EQ", "SIG_EQ", 91.0, 85.0))

    # SJ1: solder bridge — K47 (open) / K87 (closed) mode select
    # Bridges C_DEEMPH to R_SHELF junction — just a 0402 0Ω position
    components.append(r0402("SJ1", "SJ_K87",
                             "SIG_EQ", "SIG_EQ", 91.0, 87.5))

    # DC Servo components (Section B) — cluster around U1 right side
    # R_INJ: 1 MΩ — SRV_OUT → VGATE (low-pass injection into gate)
    components.append(r0402("R_INJ", "1M",
                             "SRV_OUT", "VGATE", 109.0, 77.5))

    # R_INT: 300 kΩ — VSOURCE → IN-_B (servo integrator input)
    components.append(r0402("R_INT", "300k",
                             "VSOURCE", "SRV_INT", 109.0, 80.0))

    # C_INT: 10 µF 0603 — IN-_B → OUT_B (integrator cap, sets f_c ≈ 0.05 Hz)
    components.append(r0603("C_INT", "10u",
                             "SRV_INT", "SRV_OUT", 109.0, 83.0))

    # Decoupling caps for ±15V supply (near U1) — 4 mm spacing so courtyards clear
    components.append(r0402("C_P15_100n", "100n", "P15V", "GND",  96.0, 73.0))
    components.append(r0603("C_P15_1u",   "1u",   "P15V", "GND", 100.0, 73.0))
    components.append(r0402("C_N15_100n", "100n", "N15V", "GND", 104.0, 73.0))
    components.append(r0603("C_N15_1u",   "1u",   "N15V", "GND", 108.0, 73.0))

    # ══════════════════════════════════════════════════════════════════════
    # POWER ZONE  Y=[100,122]  — LR8 pre-reg + TPS7A3901 ±15V + charge pump
    # ══════════════════════════════════════════════════════════════════════

    # U2: LR8 SOT-89  — 48V PHANTOM → 35.2V (P48V_LDO)
    components.append(sot89("U2", "LR8",
                             "LR8_ADJ", "P48V_LDO", "PHANTOM", "PHANTOM",
                             91.0, 110.5))

    # LR8 programming resistors — left of U2
    components.append(r0402("R_LR8_1", "270k", "P48V_LDO", "LR8_ADJ", 87.0, 107.5))
    components.append(r0402("R_LR8_2", "10k",  "LR8_ADJ",  "GND",     87.0, 110.5))

    # LR8 decoupling
    components.append(r0603("C_LR8_IN",  "10u/100V", "PHANTOM",  "GND", 91.0, 106.5))
    components.append(r0603("C_LR8_OUT", "4u7",      "P48V_LDO", "GND", 96.0, 110.5))

    # U3: TPS7A3901 WSON-12 3×3 mm — ±15V dual LDO from 35.2V
    tps_nets = [
        "P48V_LDO",  # 1: IN
        "P48V_LDO",  # 2: IN
        "TPS_FB_NEG",# 3: FB-
        "N15V",      # 4: OUT-
        "TPS_FB_NEG",# 5: FB-
        "P48V_LDO",  # 6: IN
        "P48V_LDO",  # 7: IN
        "TPS_FB_POS",# 8: FB+
        "P15V",      # 9: OUT+
        "TPS_FB_POS",# 10: FB+
        "P48V_LDO",  # 11: IN
        "P48V_LDO",  # 12: IN
        "GND",       # EP
    ]
    components.append(wson12("U3", "TPS7A3901", tps_nets, 100.0, 110.0))

    # TPS7A3901 programming resistors — right of U3
    components.append(r0402("R_TPS_P1", "127k", "P15V",       "TPS_FB_POS", 104.0, 107.0))
    components.append(r0402("R_TPS_P2", "10k",  "TPS_FB_POS", "GND",        107.0, 107.0))
    components.append(r0402("R_TPS_N1", "127k", "N15V",       "TPS_FB_NEG", 104.0, 110.0))
    components.append(r0402("R_TPS_N2", "10k",  "TPS_FB_NEG", "GND",        107.0, 110.0))

    # TPS7A3901 output decoupling
    components.append(r0603("C_P15_OUT", "10u", "P15V", "GND", 104.0, 114.0))
    components.append(r0603("C_N15_OUT", "10u", "N15V", "GND", 108.0, 114.0))

    # Charge pump — 1-stage Cockcroft-Walton 48V → 72V (V_BOOST)
    components.append(sot23("D1", "BAT54S",
                             "PHANTOM", "V_BOOST", "GND",
                             91.0, 117.0))
    components.append(r0402("C_PUMP", "100n/100V", "PHANTOM", "V_BOOST", 91.0, 120.0))
    components.append(r0603("C_RSVR", "4u7/100V",  "V_BOOST", "GND",     95.0, 117.0))
    components.append(r0805("L1",     "10mH",       "V_BOOST", "V_BOOST", 100.0, 117.0))
    components.append(r0603("C_LPF",  "10u",        "V_BOOST", "GND",     105.0, 117.0))

    # ══════════════════════════════════════════════════════════════════════
    # TRANSFORMER AREA  Y=[122,135]
    # Cutout X=[95,105] Y=[123,131] (10×8 mm, centre (100,127))
    # Secondary column LEFT (X=88, 3 mm pitch): TX_S3H / TX_S3R / TX_S3C
    # Primary + XLR columns RIGHT (X=109/112, 3 mm pitch)
    # NPTH cable-tie slots at X=92 and X=109, Y=133
    # ══════════════════════════════════════════════════════════════════════

    # 3× secondary winding (op-amp drives these):
    # X=88 is ≥11 mm from bottom mounting hole at (85,140) — well clear of DRC
    components.append(th_pad("TX_S3H", "TX_DRV_HOT", 88.0, 123.0))  # Blue
    components.append(th_pad("TX_S3R", "TX_DRV_RTN", 88.0, 126.0))  # White
    components.append(th_pad("TX_S3C", "GND",         88.0, 129.0))  # Yellow CT → GND

    # 1× primary winding (XLR output):
    components.append(th_pad("TX_P1",  "XLR_HOT",  109.0, 123.0))   # Red
    components.append(th_pad("TX_P2",  "XLR_COLD", 109.0, 126.0))   # Black

    # XLR cable pads — X=112 is ≥11 mm from bottom mounting hole at (115,140)
    components.append(th_pad("XLR1", "GND",      112.0, 123.0))  # pin 1 — shield
    components.append(th_pad("XLR2", "XLR_HOT",  112.0, 126.0))  # pin 2 — hot
    components.append(th_pad("XLR3", "XLR_COLD", 112.0, 129.0))  # pin 3 — cold

    # Cable-tie NPTH slots — Y=133 clears all TH pad rings and mounting holes
    # SLOT1(92,133): ≥5.66 mm from TX_S3C(88,129), ≥9.9 mm from MH(85,140)
    # SLOT2(109,133): ≥5.00 mm from XLR3(112,129), ≥9.2 mm from MH(115,140)
    components.append(npth_slot("SLOT1",  92.0, 133.0))
    components.append(npth_slot("SLOT2", 109.0, 133.0))

    # ── GND stitching vias ───────────────────────────────────────────────
    # Y=71 row: avoid X=100 (lands on N15V bus at Y=71); use X=95 instead
    for vx in [88.0, 95.0, 112.0]:
        vias.append(_gnd_via(vx, 71.0))
    for vy in [93.0, 121.0]:
        for vx in [88.0, 100.0, 112.0]:
            vias.append(_gnd_via(vx, vy))

    # ══════════════════════════════════════════════════════════════════════
    # INPUT ZONE ROUTING — local connections in the JFET cluster
    # Pad absolute positions (footprint-centre + local pad offset):
    #   Q1(100,66) SOT-23: gate=(99.05,67.30) src=(100.95,67.30) drn=(100.00,64.70)
    #   R_GBIAS(93,65) 0805: p1-BP=(91.90,65.0) p2-VGATE=(94.10,65.0)
    #   C_IN(93,69) 0402:   p1-FP=(92.425,69.0) p2-VGATE=(93.575,69.0)
    #   R_D(107,65) 0402:   p1-VDRAIN=(106.425,65.0)
    #   R_S(107,69) 0402:   p1-VSOURCE=(106.425,69.0) p2-GND=(107.575,69.0)
    #   D_RS(111,67) SOT-23: p1-GND=(110.05,68.30) p3-VSOURCE=(111.00,65.70)
    # ══════════════════════════════════════════════════════════════════════

    # VDRAIN (HV net, W_HV=0.40mm): Q1 drain → R_D pad1
    segments.extend([
        _seg(100.00, 64.70, 106.425, 64.70, "VDRAIN", W_HV),
        _seg(106.425, 64.70, 106.425, 65.00, "VDRAIN", W_HV),
    ])

    # VSOURCE: Q1 source → R_S pad1 and D_RS cathode (T-node at X=106.425 Y=67.30)
    segments.extend([
        _seg(100.95, 67.30, 106.425, 67.30, "VSOURCE"),
        _seg(106.425, 67.30, 106.425, 69.00, "VSOURCE"),  # → R_S pad1
        _seg(106.425, 67.30, 111.00,  67.30, "VSOURCE"),  # continue right
        _seg(111.00,  67.30, 111.00,  65.70, "VSOURCE"),  # → D_RS cathode
    ])

    # VGATE (high-Z, W_HIMP=0.15mm): R_GBIAS pad2 and C_IN pad2 → Q1 gate
    # Route at Y=66.0 (not 67.30) east of Q1 gate to avoid Q1 VSOURCE pad at (100.95,67.30)
    segments.extend([
        _seg(94.10,  65.00, 94.10,  66.00, "VGATE", W_HIMP),  # R_GBIAS pad2 down to Y=66
        _seg(94.10,  66.00, 99.05,  66.00, "VGATE", W_HIMP),  # east at Y=66
        _seg(99.05,  66.00, 99.05,  67.30, "VGATE", W_HIMP),  # down to Q1 gate
        _seg(93.575, 69.00, 93.575, 67.30, "VGATE", W_HIMP),  # C_IN pad2 up
        _seg(93.575, 67.30, 94.10,  67.30, "VGATE", W_HIMP),  # → join node
        _seg(94.10,  67.30, 94.10,  66.00, "VGATE", W_HIMP),  # up to Y=66 bus
    ])

    # GND bus at X=112 (W_POWER): GND_SHIELD pad, D_RS anode, R_S pad2 → GND via(112,71)
    segments.extend([
        _seg(112.00,  62.00, 112.00, 71.00, "GND", W_POWER),  # vertical bus
        _seg(107.00,  62.00, 112.00, 62.00, "GND", W_POWER),  # GND_SHIELD tap
        _seg(110.05,  68.30, 112.00, 68.30, "GND", W_POWER),  # D_RS anode tap
        _seg(107.575, 69.00, 112.00, 69.00, "GND", W_POWER),  # R_S pad2 tap
    ])

    # ── Task A: Input zone — HV feeds ────────────────────────────────────

    # BP_CAPSULE (HV 0.40 mm): BP capsule pad (100,62) → R_GBIAS pad1 (91.9,65)
    # Jog right to X=96 so horizontal at Y=66.5 stays >0.5 mm below VGATE pad2 (94.1,65).
    segments.extend([
        _seg(100.0, 62.0,  96.0, 62.0,  "BP_CAPSULE", W_HV),
        _seg( 96.0, 62.0,  96.0, 66.5,  "BP_CAPSULE", W_HV),
        _seg( 96.0, 66.5,  91.9, 66.5,  "BP_CAPSULE", W_HV),
        _seg( 91.9, 66.5,  91.9, 65.0,  "BP_CAPSULE", W_HV),  # up → R_GBIAS pad1
    ])

    # FP_CAPSULE (hi-Z 0.15 mm): FP capsule pad (93,62) → C_IN pad1 (92.425,69)
    # Step left to X=90.5 before going south so trace stays >0.5 mm from BP_CAPSULE
    # copper at R_GBIAS pad1 (91.9,65); Y=63.5 clears R_GBIAS courtyard top (63.8).
    segments.extend([
        _seg( 93.0, 62.0,  93.0,   63.5,  "FP_CAPSULE", W_HIMP),
        _seg( 93.0, 63.5,  90.5,   63.5,  "FP_CAPSULE", W_HIMP),
        _seg( 90.5, 63.5,  90.5,   69.0,  "FP_CAPSULE", W_HIMP),
        _seg( 90.5, 69.0,  92.425, 69.0,  "FP_CAPSULE", W_HIMP),  # → C_IN pad1
    ])

    # V_BOOST (HV 0.40 mm): R_D pad2 (107.575,65) short east jog on F.Cu, then north to Y=63.7
    # (clears GND_SHIELD right edge 107.75 by 0.55 mm; stays above VSOURCE vertical at Y≥67.3).
    # Via at (108.5,63.7) drops to B.Cu, east to X=113.1, south to Y=71.
    # X=113.1 on B.Cu: fiducials are F.Cu SMD-only (no B.Cu pad); mounting hole at (115,60)
    # left edge 113.9 → gap 0.6 mm; GND vias at X=112 right-pad-edge 112.3 → gap 0.6 mm.
    segments.extend([
        _seg(107.575, 65.0, 108.5,  65.0, "V_BOOST", W_HV),          # east on F.Cu
        _seg(108.5,   65.0, 108.5,  63.7, "V_BOOST", W_HV),          # north on F.Cu
        _seg(108.5,   63.7, 113.1,  63.7, "V_BOOST", W_HV, "B.Cu"),  # east on B.Cu
        _seg(113.1,   63.7, 113.1,  71.0, "V_BOOST", W_HV, "B.Cu"),  # south on B.Cu
    ])
    vias.append(_net_via(108.5, 63.7, "V_BOOST"))  # F.Cu ↔ B.Cu layer transition

    # ── Task F: Power zone — PHANTOM + LR8 ──────────────────────────────
    # Pad positions:
    #   C_LR8_IN(91,106.5) 0603: p1-PHANTOM=(89.95,106.5) p2-GND=(92.05,106.5)
    #   U2-LR8(91,110.5) SOT-89: pin1-LR8_ADJ=(89.5,112.5) pin2-P48V_LDO=(91,112.5)
    #                             pin3-PHANTOM=(92.5,112.5) tab-PHANTOM=(91,108.5)
    #   R_LR8_1(87,107.5) 0402:  p1-P48V_LDO=(86.425,107.5) p2-LR8_ADJ=(87.575,107.5)
    #   R_LR8_2(87,110.5) 0402:  p1-LR8_ADJ=(86.425,110.5) p2-GND=(87.575,110.5)
    #   C_LR8_OUT(96,110.5) 0603: p1-P48V_LDO=(94.95,110.5) p2-GND=(97.05,110.5)

    # Local GND via for C_LR8_IN pad2 — X=93.6 keeps >0.5 mm from PHANTOM tab edge (92.8)
    vias.append(_gnd_via(93.6, 108.5))

    # PHANTOM (HV 0.40 mm): C_LR8_IN pad1 <-> U2 tab <-> U2 pin3 + north stub for Task I
    segments.extend([
        _seg(89.95, 106.5, 89.95, 100.0, "PHANTOM", W_HV),   # north stub -> Task I trunk
        _seg(89.95, 106.5, 89.95, 108.5, "PHANTOM", W_HV),   # down to U2 tab level
        _seg(89.95, 108.5, 91.0,  108.5, "PHANTOM", W_HV),   # right to U2 tab centre
        _seg(91.0,  108.5, 92.5,  108.5, "PHANTOM", W_HV),   # right toward pin3
        _seg(92.5,  108.5, 92.5,  112.5, "PHANTOM", W_HV),   # down -> U2 pin3
    ])

    # P48V_LDO (0.30 mm): U2 pin2 -> C_LR8_OUT pad1 -> R_LR8_1 pad1
    # Approach R_LR8_1 pad1 from above at Y=105 to avoid crossing pad2 (LR8_ADJ, same Y row).
    # Y=105 stays >0.5 mm HV clearance above PHANTOM pads on C_LR8_IN (pad top 106.1).
    segments.extend([
        _seg( 91.0,  112.5,  91.0,   110.5, "P48V_LDO", W_POWER),
        _seg( 91.0,  110.5,  94.95,  110.5, "P48V_LDO", W_POWER),  # -> C_LR8_OUT pad1
        _seg( 94.95, 110.5,  94.95,  105.0, "P48V_LDO", W_POWER),  # up above C_LR8_IN
        _seg( 94.95, 105.0,  86.425, 105.0, "P48V_LDO", W_POWER),  # left
        _seg( 86.425, 105.0, 86.425, 107.5, "P48V_LDO", W_POWER),  # down -> R_LR8_1 pad1
    ])

    # LR8_ADJ (0.20 mm): R_LR8_1 pad2 -> R_LR8_2 pad1 -> U2 pin1
    # Down-then-left avoids routing at Y=107.5 where both pads share the same row.
    segments.extend([
        _seg(87.575, 107.5, 87.575, 109.0, "LR8_ADJ"),
        _seg(87.575, 109.0, 86.425, 109.0, "LR8_ADJ"),
        _seg(86.425, 109.0, 86.425, 112.5, "LR8_ADJ"),  # passes through R_LR8_2 pad1
        _seg(86.425, 112.5,  89.5,  112.5, "LR8_ADJ"),  # -> U2 pin1
    ])

    # GND (0.30 mm): LR8 cluster decoupling -> stitching vias
    segments.extend([
        # R_LR8_2 pad2 -> GND via at (88,121)
        _seg(87.575, 110.5, 88.0,  110.5, "GND", W_POWER),
        _seg( 88.0,  110.5, 88.0,  121.0, "GND", W_POWER),
        # C_LR8_IN pad2 -> local GND via at (93.6,108.5)
        _seg(92.05,  106.5, 93.6,  106.5, "GND", W_POWER),
        _seg(93.6,   106.5, 93.6,  108.5, "GND", W_POWER),
        # C_LR8_OUT pad2 -> GND via at (100,121)
        _seg(97.05,  110.5, 97.0,  110.5, "GND", W_POWER),
        _seg( 97.0,  110.5, 97.0,  121.0, "GND", W_POWER),
        _seg( 97.0,  121.0, 100.0, 121.0, "GND", W_POWER),
    ])

    # ── Task G1: TPS7A3901 — P48V_LDO to IN pins ─────────────────────────
    # Left IN: p1(98.35,108.75), p2(98.35,109.25), p6(98.35,111.25)
    # Right IN: p12(101.65,108.75), p11(101.65,109.25), p7(101.65,111.25)
    # p6 and p7 approach from below: p3-p5 and p8-p10 (non-P48V_LDO) are in between
    segments.extend([
        # Trunk east from existing T at (94.95,105)
        _seg( 94.95, 105.0, 102.0, 105.0, "P48V_LDO", W_POWER),
        # Left p1 + p2 — drop from trunk
        _seg( 98.35, 105.0,  98.35, 108.75, "P48V_LDO", W_POWER),
        _seg( 98.35, 108.75, 98.35, 109.25, "P48V_LDO", W_POWER),
        # Right p12 + p11 — drop from trunk
        _seg(101.65, 105.0,  101.65, 108.75, "P48V_LDO", W_POWER),
        _seg(101.65, 108.75, 101.65, 109.25, "P48V_LDO", W_POWER),
        # East drop then west trunk: p6 and p7 from below (shifted to X=102.5)
        _seg(102.5,  105.0,  102.5,  112.0,  "P48V_LDO", W_POWER),
        _seg(102.5,  112.0,   98.35, 112.0,  "P48V_LDO", W_POWER),
        _seg( 98.35, 112.0,   98.35, 111.25, "P48V_LDO", W_POWER),
        _seg(101.65, 112.0,  101.65, 111.25, "P48V_LDO", W_POWER),
    ])

    # ── Task G2: TPS7A3901 — P15V and N15V outputs ───────────────────────
    # p9(101.65,110.25)=P15V → R_TPS_P1 pad1(103.425,107)
    # p4(98.35,110.25)=N15V  → R_TPS_N1 pad1(103.425,110)
    segments.extend([
        # P15V: west clear of EP (right edge X=100.85), south below P48V_LDO bottom trunk,
        #       east past G1 vertical, north to R_TPS_P1
        _seg(101.65, 110.25, 101.1,  110.25, "P15V", W_POWER),
        _seg(101.1,  110.25, 101.1,  113.0,  "P15V", W_POWER),
        _seg(101.1,  113.0,  103.5,  113.0,  "P15V", W_POWER),
        _seg(103.5,  113.0,  103.5,  107.0,  "P15V", W_POWER),
        _seg(103.5,  107.0,  103.425, 107.0, "P15V", W_POWER),
        # N15V: west to X=96.5 (clears C_LR8_OUT GND pad at X=97.05), north, east to R_TPS_N1
        # Route east at Y=108.5 to avoid P48V_LDO horizontal at Y=107
        _seg( 98.35, 110.25,  96.5,  110.25, "N15V", W_POWER),
        _seg( 96.5,  110.25,  96.5,  108.5,  "N15V", W_POWER),
        _seg( 96.5,  108.5,  103.425, 108.5, "N15V", W_POWER),
        _seg(103.425, 108.5, 103.425, 110.0, "N15V", W_POWER),
    ])

    # ── Task G3: TPS7A3901 — FB loops, output decoupling, EP vias ───────
    # TPS_FB_POS: R_TPS_P1 pad2(104.575,107) → R_TPS_P2 pad1(106.425,107)
    # TPS_FB_NEG: R_TPS_N1 pad2(104.575,110) → R_TPS_N2 pad1(106.425,110)
    # C_P15_OUT pad1(102.95,114) from P15V trunk at X=103.5
    # C_N15_OUT pad1(106.95,114) from N15V at Y=107 corridor east then south
    # EP GND: 4× thermal vias in 2×2 grid under U3 EP at (100,110)
    segments.extend([
        _seg(104.575, 107.0, 106.425, 107.0, "TPS_FB_POS", W_SIGNAL),
        _seg(104.575, 110.0, 106.425, 110.0, "TPS_FB_NEG", W_SIGNAL),
        # P15V → C_P15_OUT: branch south from trunk at X=103.5, Y=113 → Y=114
        _seg(103.5, 113.0, 102.95, 113.0, "P15V", W_POWER),
        _seg(102.95, 113.0, 102.95, 114.0, "P15V", W_POWER),
        # N15V → C_N15_OUT: east from Y=107 corridor to X=106.95, south to Y=114
        _seg(103.425, 107.0, 106.95, 107.0, "N15V", W_POWER),
        _seg(106.95, 107.0, 106.95, 114.0, "N15V", W_POWER),
    ])
    # EP GND thermal vias: 2×2 grid at ±0.35mm from EP centre (100,110)
    for vx, vy in [(99.65, 109.65), (100.35, 109.65),
                   (99.65, 110.35), (100.35, 110.35)]:
        vias.append(_gnd_via(vx, vy))

    # ── Task C: DC servo (U1 section B) ──────────────────────────────────
    # U1 right pads X=102.7: pin7=SRV_OUT(80.365) pin6=SRV_INT(81.635)
    # R_INJ(109,77.5) 0402: p1=SRV_OUT(108.425,77.5) p2=VGATE(109.575,77.5)
    # R_INT(109,80.0) 0402: p1=VSOURCE(108.425,80.0) p2=SRV_INT(109.575,80.0)
    # C_INT(109,83.0) 0603: p1=SRV_INT(107.95,83.0) p2=SRV_OUT(110.05,83.0)
    segments.extend([
        # SRV_OUT trunk at X=107.5 (shifted from 108.5 to clear V_BOOST at X=108.8)
        _seg(102.7,  80.365, 107.5,  80.365, "SRV_OUT", W_SIGNAL),
        _seg(107.5,  80.365, 107.5,  77.5,   "SRV_OUT", W_SIGNAL),
        _seg(107.5,  77.5,   108.425, 77.5,  "SRV_OUT", W_SIGNAL),  # → R_INJ p1
        _seg(107.5,  80.365, 107.5,  83.0,   "SRV_OUT", W_SIGNAL),
        _seg(107.5,  83.0,   110.05,  83.0,  "SRV_OUT", W_SIGNAL),  # → C_INT p2
        # SRV_INT trunk at X=106.5
        _seg(102.7,  81.635, 106.5, 81.635, "SRV_INT", W_SIGNAL),
        _seg(106.5,  81.635, 106.5, 83.0,   "SRV_INT", W_SIGNAL),  # → C_INT p1
        _seg(106.5,  83.0,   107.95, 83.0,  "SRV_INT", W_SIGNAL),
        _seg(109.575, 80.0,  106.5,  80.0,  "SRV_INT", W_SIGNAL),
        _seg(106.5,   80.0,  106.5,  81.635,"SRV_INT", W_SIGNAL),   # → R_INT p2
        # VSOURCE to R_INT p1 (108.425,80.0) — branch east from VSOURCE at Y=67.3
        _seg(106.425, 67.3,  108.425, 67.3,  "VSOURCE", W_SIGNAL),
        _seg(108.425, 67.3,  108.425, 80.0,  "VSOURCE", W_SIGNAL),
        # VGATE to R_INJ p2 (109.575,77.5) — extend east at Y=66 (avoids VSOURCE at Y=67.3)
        _seg(99.05,  66.0,   105.5,  66.0,   "VGATE",   W_HIMP),
        _seg(105.5,  66.0,   105.5,  75.5,   "VGATE",   W_HIMP),
        _seg(105.5,  75.5,   109.575, 75.5,  "VGATE",   W_HIMP),
        _seg(109.575, 75.5,  109.575, 77.5,  "VGATE",   W_HIMP),
    ])

    # ── Task E: U1 decoupling caps ───────────────────────────────────────
    # C_P15_100n(96,73) 0402: p1=P15V(95.425,73)  C_P15_1u(100,73) 0603: p1=P15V(98.95,73)
    # C_N15_100n(104,73) 0402: p1=N15V(103.425,73) C_N15_1u(108,73) 0603: p1=N15V(106.95,73)
    # P15V bus at Y=73; N15V bus at Y=71 with stubs north to cap pads
    segments.extend([
        # P15V: extend trunk north to Y=73, bus west to C_P15_100n
        _seg(103.5,  79.095, 103.5,  73.0,  "P15V", W_POWER),
        _seg(103.5,  73.0,   95.425, 73.0,  "P15V", W_POWER),
        # N15V: extend trunk north to Y=71 at X=96.5, bus east, stubs to cap pads
        _seg(96.5,   82.905, 96.5,   71.0,  "N15V", W_POWER),
        _seg(96.5,   71.0,   106.95, 71.0,  "N15V", W_POWER),
        _seg(103.425, 71.0,  103.425, 73.0, "N15V", W_POWER),
        _seg(106.95,  71.0,  106.95,  73.0, "N15V", W_POWER),
    ])

    # ── Task D: U1 power pins ────────────────────────────────────────────
    # pin8=P15V (102.7,79.095): extend P15V trunk (X=103.5) north then west
    # pin4=N15V (97.3,82.905):  extend N15V trunk (X=97.0) north then east
    segments.extend([
        _seg(103.5, 107.0, 103.5,  79.095, "P15V", W_POWER),
        _seg(103.5,  79.095, 102.7, 79.095, "P15V", W_POWER),
        _seg(96.5,  108.5,  96.5,  82.905, "N15V", W_POWER),
        _seg(96.5,  82.905, 97.3,  82.905, "N15V", W_POWER),
    ])

    # ── Task B: Audio zone EQ (U1 section A) ─────────────────────────────
    # U1 SOIC-8 at (100,81), PITCH=1.27, left pads X=97.3, right pads X=102.7
    # pin1=OUT_A/SIG_EQ  (97.3, 79.095)
    # pin2=IN-_A/SIG_EQ  (97.3, 80.365)
    # EQ components at X=91: R_IN(77.5) R_F(80) R_SHELF(82.5) C_DEEMPH(85) SJ1(87.5)
    # SIG_EQ trunk at X=93.5, Y=[77.5..87.5]; VSOURCE from Q1 src to R_IN p1
    segments.extend([
        # SIG_EQ vertical trunk
        _seg(93.5, 77.5, 93.5, 87.5, "SIG_EQ", W_SIGNAL),
        # U1 pin1 and pin2 → trunk
        _seg(97.3, 79.095, 93.5, 79.095, "SIG_EQ", W_SIGNAL),
        _seg(97.3, 80.365, 93.5, 80.365, "SIG_EQ", W_SIGNAL),
        # R_IN p2 (91.575,77.5) → trunk
        _seg(91.575, 77.5, 93.5, 77.5, "SIG_EQ", W_SIGNAL),
        # R_F, R_SHELF, C_DEEMPH, SJ1 — right pad → trunk
        _seg(91.575, 80.0, 93.5, 80.0, "SIG_EQ", W_SIGNAL),
        _seg(91.575, 82.5, 93.5, 82.5, "SIG_EQ", W_SIGNAL),
        _seg(91.575, 85.0, 93.5, 85.0, "SIG_EQ", W_SIGNAL),
        _seg(91.575, 87.5, 93.5, 87.5, "SIG_EQ", W_SIGNAL),
        # R_F, R_SHELF, C_DEEMPH, SJ1 — left pad also SIG_EQ → trunk
        _seg(90.425, 80.0, 91.575, 80.0, "SIG_EQ", W_SIGNAL),
        _seg(90.425, 82.5, 91.575, 82.5, "SIG_EQ", W_SIGNAL),
        _seg(90.425, 85.0, 91.575, 85.0, "SIG_EQ", W_SIGNAL),
        _seg(90.425, 87.5, 91.575, 87.5, "SIG_EQ", W_SIGNAL),
        # VSOURCE: Q1 source (100.95,67.3) west then south to R_IN p1 (90.425,77.5)
        _seg(100.95, 67.3, 90.0,  67.3, "VSOURCE", W_SIGNAL),
        _seg(90.0,   67.3, 90.0,  77.5, "VSOURCE", W_SIGNAL),
        _seg(90.0,   77.5, 90.425, 77.5, "VSOURCE", W_SIGNAL),
    ])

    # ── Task J: Transformer + XLR routing ────────────────────────────────
    # TX_S3H(88,123)=TX_DRV_HOT  TX_S3R(88,126)=TX_DRV_RTN  TX_S3C(88,129)=GND
    # TX_P1(109,123)=XLR_HOT     TX_P2(109,126)=XLR_COLD
    # XLR1(112,123)=GND  XLR2(112,126)=XLR_HOT  XLR3(112,129)=XLR_COLD
    segments.extend([
        # SIG_EQ trunk south to TX_S3H (op-amp drives transformer secondary)
        _seg(93.5, 87.5,  93.5, 121.0, "SIG_EQ", W_SIGNAL),
        _seg(93.5, 121.0, 88.0, 121.0, "SIG_EQ", W_SIGNAL),
        _seg(88.0, 121.0, 88.0, 123.0, "SIG_EQ", W_SIGNAL),
        # TX_S3R (secondary return) → SIG_EQ feedback node
        _seg(88.0, 126.0, 88.0, 124.5, "TX_DRV_RTN", W_SIGNAL),
        # XLR_HOT: TX_P1(109,123) → XLR2(112,126) — jog at X=110 to avoid XLR1 GND pad
        _seg(109.0, 123.0, 110.0, 123.0, "XLR_HOT", W_SIGNAL),
        _seg(110.0, 123.0, 110.0, 126.0, "XLR_HOT", W_SIGNAL),
        _seg(110.0, 126.0, 112.0, 126.0, "XLR_HOT", W_SIGNAL),
        # XLR_COLD: TX_P2(109,126) → XLR3(112,129) — jog at X=110.7 (clears HOT at X=110)
        _seg(109.0, 126.0, 110.7, 126.0, "XLR_COLD", W_SIGNAL),
        _seg(110.7, 126.0, 110.7, 129.0, "XLR_COLD", W_SIGNAL),
        _seg(110.7, 129.0, 112.0, 129.0, "XLR_COLD", W_SIGNAL),
    ])
    vias.append(_gnd_via(88.0, 130.5))   # TX_S3C GND stitch
    vias.append(_gnd_via(112.0, 122.0))  # XLR1 GND stitch

    # ── Task I: HV rail trunks ────────────────────────────────────────────
    # V_BOOST: B.Cu trunk continues from (113.1,71) south to (113.1,116); via back to F.Cu;
    # F.Cu west to C_LPF p1 at (103.95,116).
    segments.extend([
        _seg(113.1,  71.0,  113.1, 116.0, "V_BOOST", W_HV, "B.Cu"),  # B.Cu trunk
        _seg(113.1, 116.0, 103.95, 116.0, "V_BOOST", W_HV),          # F.Cu west to caps
    ])
    vias.append(_net_via(113.1, 116.0, "V_BOOST"))  # B.Cu ↔ F.Cu layer transition

    # ── Task H: Charge pump ───────────────────────────────────────────────
    # D1 SOT-23 (91,117): p1=PHANTOM(90.05,118.30) p2=V_BOOST(91.95,118.30) p3=GND(91,115.70)
    # C_PUMP 0402 (91,120): p1=PHANTOM(90.425,120) p2=V_BOOST(91.575,120)
    # C_RSVR 0603 (95,117): p1=V_BOOST(93.95,117) p2=GND(96.05,117)
    # L1 0805 (100,117): p1=V_BOOST(98.9,117) p2=V_BOOST(101.1,117)
    # C_LPF 0603 (105,117): p1=V_BOOST(103.95,117) p2=GND(106.05,117)
    segments.extend([
        # PHANTOM: extend south trunk from X=89.95 down to D1 p1 and C_PUMP p1
        _seg(89.95, 106.5, 89.95, 120.0,  "PHANTOM", W_HV),
        _seg(89.95, 118.3, 90.05, 118.3,  "PHANTOM", W_HV),
        _seg(89.95, 120.0, 90.425, 120.0, "PHANTOM", W_HV),
        # V_BOOST: D1 p2 → C_PUMP p2 → C_RSVR p1 → L1 p1 → L1 p2 → C_LPF p1
        # Route at Y=116 (not 117) to avoid passing through GND pads at Y=117
        _seg(91.95, 118.3, 91.95, 116.0,  "V_BOOST", W_HV),
        _seg(91.575, 120.0, 91.95, 120.0, "V_BOOST", W_HV),
        _seg(91.95, 120.0, 91.95, 118.3,  "V_BOOST", W_HV),
        # stubs north to each component pad at Y=117
        _seg(91.95, 116.0, 93.95, 116.0,  "V_BOOST", W_HV),  # trunk east
        _seg(93.95, 117.0, 93.95, 116.0,  "V_BOOST", W_HV),  # C_RSVR p1 stub
        _seg(93.95, 116.0, 98.9,  116.0,  "V_BOOST", W_HV),  # trunk to L1
        _seg(98.9,  117.0, 98.9,  116.0,  "V_BOOST", W_HV),  # L1 p1 stub
        _seg(98.9,  116.0, 101.1, 116.0,  "V_BOOST", W_HV),  # L1 bridge
        _seg(101.1, 117.0, 101.1, 116.0,  "V_BOOST", W_HV),  # L1 p2 stub
        _seg(101.1, 116.0, 103.95, 116.0, "V_BOOST", W_HV),  # trunk to C_LPF
        _seg(103.95, 117.0, 103.95, 116.0,"V_BOOST", W_HV),  # C_LPF p1 stub
    ])
    vias.append(_gnd_via(91.0, 114.5))   # D1 p3 GND
    vias.append(_gnd_via(96.05, 118.0))  # C_RSVR p2 GND
    vias.append(_gnd_via(106.05, 118.0)) # C_LPF p2 GND

    # ── Commit to board ──────────────────────────────────────────────────
    b.footprints.extend(components)
    b.traceItems.extend(segments)
    b.traceItems.extend(vias)

    gnd_zone(b)

    b.to_file(str(pcb_path))
    print(f"PCB written → {pcb_path}")
    return pcb_path


# ---------------------------------------------------------------------------
# Preview renderer (matplotlib — no KiCad required)
# ---------------------------------------------------------------------------
def render_preview(out_png: Path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("matplotlib not available — skipping preview")
        return

    fig, ax = plt.subplots(figsize=(5, 12))
    ax.set_aspect("equal")
    ax.set_xlim(BOUNDS_MIN_X - 2, BOUNDS_MAX_X + 2)
    ax.set_ylim(BOUNDS_MIN_Y - 3, BOUNDS_MAX_Y + 3)
    ax.invert_yaxis()
    ax.set_title("op-txm PCB — component placement preview", fontsize=9)
    ax.set_xlabel("X (mm)"); ax.set_ylabel("Y (mm)")

    # Board outline
    ax.add_patch(mpatches.Rectangle(
        (BOUNDS_MIN_X, BOUNDS_MIN_Y), BOARD_W, BOARD_H,
        fill=False, edgecolor="black", linewidth=2))

    # Zones
    colors = {"Input": "lightcyan", "Audio": "lightyellow", "Power": "mistyrose"}
    for (label, (x0, y0, x1, y1), col) in [
        ("Input zone", ZONE_INPUT, "lightcyan"),
        ("Audio zone", ZONE_AUDIO, "lightyellow"),
        ("Power zone", ZONE_POWER, "mistyrose"),
    ]:
        ax.add_patch(mpatches.Rectangle(
            (x0, y0), x1 - x0, y1 - y0,
            facecolor=col, edgecolor="gray", linewidth=0.5, alpha=0.5))
        ax.text((x0 + x1) / 2, (y0 + y1) / 2, label,
                ha="center", va="center", fontsize=7, color="gray")

    # Mounting holes
    for mx, my in MHOLE_POS:
        ax.add_patch(plt.Circle((mx, my), 1.1,
                                fill=False, edgecolor="gray",
                                linewidth=1.5, linestyle="--", zorder=6))

    # Transformer bobbin cutout (10 × 8 mm, centre at X=100 Y=127)
    _tx_w, _tx_h = 10.0, 8.0
    ax.add_patch(mpatches.Rectangle(
        (CX - _tx_w / 2, 127.0 - _tx_h / 2), _tx_w, _tx_h,
        facecolor="white", edgecolor="red", linewidth=1.5,
        linestyle="--", zorder=7))
    ax.text(CX, 127.0, "TX\ncutout", ha="center", va="center",
            fontsize=6, color="red")

    ax.text(CX, BOUNDS_MIN_Y - 1.5, "▲ CAPSULE", ha="center",
            fontsize=8, color="teal", fontweight="bold")
    ax.text(CX, BOUNDS_MAX_Y + 1.5, "▼ XLR OUTPUT", ha="center",
            fontsize=8, color="#880000", fontweight="bold")

    plt.tight_layout()
    fig.savefig(str(out_png), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Preview → {out_png}")


if __name__ == "__main__":
    out_pcb = build_layout()
    render_preview(out_pcb.parent / "op_txm_layout.png")
    print()
    print("Open in KiCad 10:")
    print(f"  kicad {out_pcb}")
    print()
    print("Required before Gerber export:")
    print("  1. Fill All Zones (B key) — floods B.Cu GND plane")
    print("  2. DRC — verify zero clearance violations, zero unrouted nets")
    print("  3. Route remaining nets interactively in KiCad")
