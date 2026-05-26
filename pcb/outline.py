"""pcb/outline.py — op-txm PCB Outline Generator
=================================================
Generates a blank KiCad 10 board file:

  - Board outline: 35 mm (W) × 85 mm (L)
  - 4× M2.2 NPTH mounting holes, 30×80 mm rectangular pattern
  - HV keepout zone: bottom ~41 mm (power + transformer zone)

Usage
-----
    .venv/bin/python pcb/outline.py

Output
------
    pcb/op-txm.kicad_pcb
"""

import uuid
from pathlib import Path

BOARD_CENTER_X  = 100.0
BOARD_CENTER_Y  = 100.0
BOARD_W         = 35.0
BOARD_H         = 85.0
EDGE_WIDTH      = 0.05
COPPER_CLEARANCE = 0.25
HV_CLEARANCE    = 1.2

MOUNT_HOLE_DIAM = 2.2
MOUNT_HOLES = [
    (BOARD_CENTER_X - 15.0, BOARD_CENTER_Y - 40.0),  # top-left
    (BOARD_CENTER_X + 15.0, BOARD_CENTER_Y - 40.0),  # top-right
    (BOARD_CENTER_X - 15.0, BOARD_CENTER_Y + 40.0),  # bottom-left
    (BOARD_CENTER_X + 15.0, BOARD_CENTER_Y + 40.0),  # bottom-right
]

HV_KEEPOUTS = [
    (0.0, 21.0, 32.0, 41.0),   # bottom zone: power + XLR + transformer pads
]

# Transformer bobbin cutout — bobbin passes through; metal core sits as flange on PCB
# Measure the physical NTE10/3 bobbin before finalising these values.
# Full body: 11.5 × 12.9 × 11.5 mm; bobbin is the wound plastic section (smaller).
TX_BOBBIN_W = 10.0   # cutout width  (X) mm — adjust after measuring
TX_BOBBIN_H = 8.0    # cutout height (Y) mm — adjust after measuring
TX_CUTOUT_X = 100.0  # cutout centre X (canvas absolute mm)
TX_CUTOUT_Y = 127.0  # cutout centre Y (canvas absolute mm)


def uid() -> str:
    return str(uuid.uuid4())


def xy(x: float, y: float) -> str:
    return f"{x:.4f} {y:.4f}"


def keepout_zone_sexpr(cx, cy, w, h, board_cx, board_cy):
    x0 = board_cx + cx - w / 2
    y0 = board_cy + cy - h / 2
    x1 = board_cx + cx + w / 2
    y1 = board_cy + cy + h / 2
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    pts = "\n          ".join(f"(xy {xy(*c)})" for c in corners)
    return f"""\
  (zone
    (net 0)
    (net_name "HV_Keepout")
    (layer "F.Cu")
    (uuid "{uid()}")
    (name "HV_Keepout")
    (hatch edge 0.508)
    (connect_pads (clearance {COPPER_CLEARANCE}))
    (min_thickness 0.25)
    (keepout
      (tracks not_allowed)
      (vias not_allowed)
      (pads not_allowed)
      (copperpour not_allowed)
      (footprints allowed))
    (fill (thermal_gap 0.5) (thermal_bridge_width 0.5))
    (polygon (pts {pts}))
  )"""


def rect_outline_sexpr(cx, cy, w, h):
    x0, y0 = cx - w / 2, cy - h / 2
    x1, y1 = cx + w / 2, cy + h / 2
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    lines = []
    for i in range(4):
        ax, ay = corners[i]
        bx, by = corners[(i + 1) % 4]
        lines.append(f"""\
  (gr_line
    (start {xy(ax, ay)})
    (end {xy(bx, by)})
    (layer "Edge.Cuts")
    (width {EDGE_WIDTH})
    (uuid "{uid()}")
  )""")
    return "\n".join(lines)


def mount_hole_sexpr(x, y, diam):
    return f"""\
  (footprint "MountingHole:MountingHole_2.2mm_M2.2_Pad"
    (layer "F.Cu")
    (uuid "{uid()}")
    (at {xy(x, y)})
    (descr "M2.2 Mounting Hole")
    (pad "" np_thru_hole circle
      (at 0 0)
      (size {diam:.4f} {diam:.4f})
      (drill {diam:.4f})
      (layers "*.Cu" "*.Mask")
      (uuid "{uid()}")
    )
  )"""


def tx_cutout_sexpr() -> str:
    """Interior rectangular Edge.Cuts cutout for the NTE10/3 bobbin.
    The metal core (larger than the bobbin) acts as a retaining flange on the PCB surface.
    """
    x0 = TX_CUTOUT_X - TX_BOBBIN_W / 2
    x1 = TX_CUTOUT_X + TX_BOBBIN_W / 2
    y0 = TX_CUTOUT_Y - TX_BOBBIN_H / 2
    y1 = TX_CUTOUT_Y + TX_BOBBIN_H / 2
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    lines = []
    for i in range(4):
        ax, ay = corners[i]
        bx, by = corners[(i + 1) % 4]
        lines.append(f"""\
  (gr_line
    (start {xy(ax, ay)})
    (end {xy(bx, by)})
    (layer "Edge.Cuts")
    (width {EDGE_WIDTH})
    (uuid "{uid()}")
  )""")
    return "\n".join(lines)


def generate_board() -> str:
    cx, cy = BOARD_CENTER_X, BOARD_CENTER_Y
    outline  = rect_outline_sexpr(cx, cy, BOARD_W, BOARD_H)
    holes    = "\n".join(mount_hole_sexpr(x, y, MOUNT_HOLE_DIAM) for x, y in MOUNT_HOLES)
    keepouts = "\n".join(keepout_zone_sexpr(kx, ky, kw, kh, cx, cy)
                         for kx, ky, kw, kh in HV_KEEPOUTS)
    cutout   = tx_cutout_sexpr()

    return f"""\
(kicad_pcb
  (version 20241229)
  (generator "op-txm-parametric-outline")
  (generator_version "10.0")

  (general
    (thickness 1.6)
  )

  (paper "A4")

  (layers
    (0 "F.Cu" signal)
    (2 "B.Cu" signal)
    (1 "F.Mask" user)
    (3 "B.Mask" user)
    (5 "F.SilkS" user "F.Silkscreen")
    (7 "B.SilkS" user "B.Silkscreen")
    (13 "F.Paste" user)
    (15 "B.Paste" user)
    (17 "Dwgs.User" user "User.Drawings")
    (25 "Edge.Cuts" user)
    (31 "F.CrtYd" user "F.Courtyard")
    (35 "F.Fab" user "F.Fab")
  )

  (setup
    (pad_to_mask_clearance 0)
    (pcbplotparams
      (layerselection 0x00010fc_ffffffff)
      (usegerberattributes true)
      (usegerberadvancedattributes true)
      (creategerberjobfile true)
      (svgprecision 4)
      (plotframeref false)
      (viasonmask false)
      (mode 1)
      (useauxorigin false)
      (psnegative false)
      (epsplot false)
      (pdf_front_fp_property_popups true)
      (pdf_back_fp_property_popups true)
      (dxfunits 1)
      (dxfpolygonmode true)
      (dxfimperialunits false)
      (dxfusepcbnewfont true)
      (pdfprecision 4)
      (svguseinch false)
      (outputdirectory "gerbers/")
    )
  )

{outline}

{holes}

{cutout}

{keepouts}

)
"""


if __name__ == "__main__":
    out = Path(__file__).parent / "op-txm.kicad_pcb"
    out.write_text(generate_board())
    print(f"Board outline written → {out}")
