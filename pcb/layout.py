"""pcb/layout.py — op-txm PCB Layout (KiCad 10, code-driven via kiutils)
=========================================================================
Generates pcb/op-txm.kicad_pcb from the parametric outline.

Board: 40 mm (W) × 100 mm (L)  — standard large-body mic form factor
Canvas centre: (100, 100) mm    — board spans X=[80,120], Y=[50,150]

Signal flow (Y-axis, top → bottom):
  Top zone    Y=[52,68]   Capsule TH pads + JFET input (quiet end)
  GAP         Y=[68,78]   10 mm noise isolation buffer
  Middle zone Y=[78,118]  OPA1642 EQ + DC servo + decoupling
  GAP         Y=[118,123]  5 mm HV isolation buffer
  Bottom zone Y=[123,148] Power (LR8, TPS7A3901, charge pump)
                           + transformer TH pads + XLR TH pads

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
BOARD_W  = 40.0
BOARD_H  = 100.0

BOUNDS_MIN_X = CX - BOARD_W / 2   # 80.0
BOUNDS_MAX_X = CX + BOARD_W / 2   # 120.0
BOUNDS_MIN_Y = CY - BOARD_H / 2   # 50.0
BOUNDS_MAX_Y = CY + BOARD_H / 2   # 150.0

SAFE_MARGIN = 6.0
SAFE_MIN_X  = BOUNDS_MIN_X + SAFE_MARGIN   # 86.0
SAFE_MAX_X  = BOUNDS_MAX_X - SAFE_MARGIN   # 114.0
SAFE_MIN_Y  = BOUNDS_MIN_Y + 2.0           # 52.0
SAFE_MAX_Y  = BOUNDS_MAX_Y - 2.0           # 148.0

ZONE_INPUT  = (86.0,  52.0, 114.0,  68.0)
ZONE_AUDIO  = (86.0,  78.0, 114.0, 118.0)
ZONE_POWER  = (86.0, 123.0, 114.0, 148.0)

FIDUCIAL_POS = [(85.0, 55.0), (115.0, 55.0), (115.0, 145.0)]

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
    # TOP ZONE  Y=[52,68]  — Capsule interface + JFET
    # ══════════════════════════════════════════════════════════════════════

    # Capsule pads (Y≈56, PCB head)
    # FP: front-plate signal → VGATE via C_IN
    # BP: back-plate bias (V_BOOST via R_GBIAS — sets capsule polarisation)
    components.append(capsule_pad("FP",         "FP_CAPSULE",  93.0, 56.0))
    components.append(capsule_pad("BP",         "BP_CAPSULE", 100.0, 56.0))
    components.append(capsule_pad("GND_SHIELD", "GND",        107.0, 56.0))

    # Q1: MMBF170LT1G SOT-23 (pin1=S, pin2=G, pin3=D in SOT-23 pinout)
    # MMBF170 SOT-23 pinout: 1=Gate, 2=Source, 3=Drain (check datasheet!)
    # Placed Y=63 — just below capsule pads
    components.append(sot23("Q1", "MMBF170LT1G",
                             "VGATE", "VSOURCE", "VDRAIN",
                             100.0, 63.0))

    # R_GBIAS: 10 MΩ 0805 — BP_CAPSULE → VGATE (sets capsule polarisation bias)
    # Large body for high-voltage handling; isolate from signal traces
    components.append(r0805("R_GBIAS", "10M",
                             "BP_CAPSULE", "VGATE", 93.0, 63.0))

    # C_IN: 10 nF 0402 — FP_CAPSULE → VGATE coupling cap (AC, blocks capsule DC)
    components.append(r0402("C_IN", "10n",
                             "FP_CAPSULE", "VGATE", 93.0, 67.0))

    # R_D: 22 kΩ 0402 — VDRAIN → V_BOOST (drain load resistor)
    components.append(r0402("R_D", "22k",
                             "VDRAIN", "V_BOOST", 107.0, 63.0))

    # R_S: 1 kΩ 0402 — VSOURCE → GND (source degeneration for servo lock)
    components.append(r0402("R_S", "1k",
                             "VSOURCE", "GND", 107.0, 67.0))

    # ══════════════════════════════════════════════════════════════════════
    # MIDDLE ZONE  Y=[78,118]  — OPA1642 EQ + DC Servo
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
    components.append(soic8("U1", "OPA1642AIDR", opa_nets, 100.0, 90.0))

    # EQ components (Section A) — cluster around U1 left side
    # R_IN: 10 kΩ — VSOURCE → IN-_A  (input summing resistor)
    components.append(r0402("R_IN", "10k",
                             "VSOURCE", "SIG_EQ", 91.0, 87.5))

    # R_F: 47 kΩ — OUT_A → IN-_A  (feedback; K47 mode)
    components.append(r0402("R_F", "47k",
                             "SIG_EQ", "SIG_EQ", 91.0, 90.0))

    # R_SHELF: 47 kΩ — in series with C_DEEMPH across R_F (K87 de-emphasis)
    components.append(r0402("R_SHELF", "47k",
                             "SIG_EQ", "SIG_EQ", 91.0, 92.5))

    # C_DEEMPH: 150 pF — de-emphasis shelf cap
    components.append(r0402("C_DEEMPH", "150p",
                             "SIG_EQ", "SIG_EQ", 91.0, 95.0))

    # SJ1: solder bridge — K47 (open) / K87 (closed) mode select
    # Bridges C_DEEMPH to R_SHELF junction — just a 0402 0Ω position
    components.append(r0402("SJ1", "SJ_K87",
                             "SIG_EQ", "SIG_EQ", 91.0, 97.5))

    # DC Servo components (Section B) — cluster around U1 right side
    # R_INJ: 1 MΩ — SRV_OUT → VGATE (low-pass injection into gate)
    components.append(r0402("R_INJ", "1M",
                             "SRV_OUT", "VGATE", 109.0, 87.5))

    # R_INT: 300 kΩ — VSOURCE → IN-_B (servo integrator input)
    components.append(r0402("R_INT", "300k",
                             "VSOURCE", "SRV_INT", 109.0, 90.0))

    # C_INT: 10 µF 0603 — IN-_B → OUT_B (integrator cap, sets f_c ≈ 0.05 Hz)
    components.append(r0603("C_INT", "10u",
                             "SRV_INT", "SRV_OUT", 109.0, 93.0))

    # Decoupling caps for ±15V supply (near U1)
    components.append(r0402("C_P15_100n", "100n", "P15V", "GND", 97.0, 83.0))
    components.append(r0603("C_P15_1u",   "1u",   "P15V", "GND", 100.0, 83.0))
    components.append(r0402("C_N15_100n", "100n", "N15V", "GND", 103.0, 83.0))
    components.append(r0603("C_N15_1u",   "1u",   "N15V", "GND", 106.0, 83.0))

    # ══════════════════════════════════════════════════════════════════════
    # BOTTOM ZONE  Y=[123,148]  — Power + Transformer + XLR
    # ══════════════════════════════════════════════════════════════════════

    # U2: LR8 SOT-89  — 48V PHANTOM → 35.2V (P48V_LDO)
    # LR8 pinout (SOT-89): 1=ADJ, 2=OUT, 3=IN, tab=IN
    components.append(sot89("U2", "LR8",
                             "LR8_ADJ", "P48V_LDO", "PHANTOM", "PHANTOM",
                             91.0, 130.0))

    # LR8 programming resistors (sets Vout = 35.2V)
    # Vout = 1.22 × (1 + R1/R2) → R1/R2 ≈ 27.8
    # R2 = 10kΩ, R1 = 270kΩ (use 270k + 8.2k series, or single 270k for ~34V)
    components.append(r0402("R_LR8_1", "270k",
                             "P48V_LDO", "LR8_ADJ", 87.5, 130.0))
    components.append(r0402("R_LR8_2", "10k",
                             "LR8_ADJ", "GND", 87.5, 133.0))

    # LR8 output decoupling
    components.append(r0603("C_LR8_IN",  "10u/100V", "PHANTOM",   "GND", 91.0, 125.0))
    components.append(r0603("C_LR8_OUT", "4u7",      "P48V_LDO",  "GND", 94.0, 130.0))

    # U3: TPS7A3901 WSON-12 3×3 mm — ±15V dual LDO from 35.2V
    # TPS7A3901 pinout (WSON-12, 12 pins + EP):
    #   Pins 1-6 (left):  IN, IN, FB-, OUT-, FB-, IN
    #   Pins 7-12 (right): IN, FB+, OUT+, FB+, IN, IN
    #   EP: GND
    # Simplified net assignment:
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
    components.append(wson12("U3", "TPS7A3901", tps_nets, 100.0, 130.0))

    # TPS7A3901 programming resistors (+15V / -15V setpoints)
    components.append(r0402("R_TPS_P1", "127k", "P15V",       "TPS_FB_POS", 104.0, 126.0))
    components.append(r0402("R_TPS_P2", "10k",  "TPS_FB_POS", "GND",        107.0, 126.0))
    components.append(r0402("R_TPS_N1", "127k", "N15V",       "TPS_FB_NEG", 104.0, 129.0))
    components.append(r0402("R_TPS_N2", "10k",  "TPS_FB_NEG", "GND",        107.0, 129.0))

    # TPS7A3901 output decoupling
    components.append(r0603("C_P15_OUT", "10u", "P15V", "GND", 104.0, 132.5))
    components.append(r0603("C_N15_OUT", "10u", "N15V", "GND", 107.0, 132.5))

    # Charge pump — 1-stage Cockcroft-Walton 48V → 72V (V_BOOST)
    # D1: BAT54S (SOT-23, series dual Schottky) — anode pair = pin3, cathode = pin1+pin2
    # We treat it as two diodes in series using the dual package
    components.append(sot23("D1", "BAT54S",
                             "PHANTOM", "V_BOOST", "GND",
                             91.0, 138.0))

    # C_PUMP: 100 nF 0402 — pump capacitor (PHANTOM → V_BOOST)
    components.append(r0402("C_PUMP", "100n/100V", "PHANTOM", "V_BOOST", 91.0, 141.5))

    # C_RSVR: 4.7 µF — output reservoir capacitor (100V rated)
    components.append(r0603("C_RSVR", "4u7/100V", "V_BOOST", "GND", 94.0, 138.0))

    # LC post-filter: 10 mH + 10 µF (between raw pump and clean V_BOOST rail)
    components.append(r0805("L1",    "10mH",  "V_BOOST", "V_BOOST", 97.0, 138.0))
    components.append(r0603("C_LPF", "10u",   "V_BOOST", "GND",     100.0, 138.0))

    # ── Transformer TH pads (op-txm reversed 3:1 connection) ────────────
    # 3× secondary (driven by op-amp EQ output):
    components.append(th_pad("TX_S3H", "TX_DRV_HOT", 87.0, 144.0))  # Blue
    components.append(th_pad("TX_S3R", "TX_DRV_RTN", 90.0, 144.0))  # White
    components.append(th_pad("TX_S3C", "GND",         93.0, 144.0))  # Yellow (CT → GND)
    # 1× primary (XLR balanced output):
    components.append(th_pad("TX_P1",  "XLR_HOT",    96.0, 144.0))  # Red → XLR pin2
    components.append(th_pad("TX_P2",  "XLR_COLD",   99.0, 144.0))  # Black → XLR pin3

    # ── NPTH zip-tie slots (transformer body retention) ──────────────────
    components.append(npth_slot("SLOT1",  86.0, 148.0))
    components.append(npth_slot("SLOT2", 114.0, 148.0))

    # ── XLR cable solder pads ────────────────────────────────────────────
    components.append(th_pad("XLR1", "GND",      106.0, 144.0))  # pin 1 — shield/GND
    components.append(th_pad("XLR2", "XLR_HOT",  110.0, 144.0))  # pin 2 — hot
    components.append(th_pad("XLR3", "XLR_COLD", 114.0, 144.0))  # pin 3 — cold

    # ── GND stitching vias ───────────────────────────────────────────────
    for vy in [72.0, 98.0, 121.0]:
        for vx in [88.0, 100.0, 112.0]:
            vias.append(_gnd_via(vx, vy))

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
