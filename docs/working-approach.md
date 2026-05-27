# Working Approach — op-txm PCB Development

## Core rule

**Write code → run → fix errors → commit. No pre-solving geometry in prose.**  
If the geometry is unclear, write the attempt, see what DRC says, iterate.

---

## Iteration loop

```
edit layout.py
→ uv run python pcb/layout.py
→ open in KiCad → Inspect → Design Rules Checker → save report to pcb/DRC.rpt
→ read DRC.rpt, pick next root-cause short
→ repeat
```

DRC.rpt is gitignored (generated artefact). The .kicad_pcb is also gitignored — it is always regenerated from layout.py.

---

## Batching

Fix **one root-cause short per commit**. A root-cause short typically clears 5–20 downstream
solder_mask_bridge / tracks_crossing entries. Do not attempt multiple root causes in one pass —
the interactions are hard to predict and error output becomes unreadable.

After each fix commit, re-run DRC and update `docs/drc-fix-plan.md` with new violation count.

---

## DRC priority order

1. **shorting_items** — hard shorts between different nets (circuit-breaking)
2. **tracks_crossing / clearance** — routing overlaps, HV clearance violations
3. **unconnected_items** — floating pads
4. **Warnings** (text_height, silk_overlap, lib_footprint, via_dangling) — fix last or waive

**Always waive**: WSON-12 (U3 TPS7A3901) adjacent-pad clearances — structural, 0.5mm pitch.

---

## Routing conventions

| Net type | Width | Layer |
|----------|-------|-------|
| PHANTOM, V_BOOST, BP_CAPSULE | 0.40 mm | F.Cu |
| P15V, N15V, P48V_LDO, GND | 0.30 mm | F.Cu |
| SIG_EQ, SRV_OUT, SRV_INT, VSOURCE | 0.20 mm | F.Cu |
| VGATE, FP_CAPSULE | 0.15 mm | F.Cu |
| Via | Ø0.60 mm / drill 0.30 mm | F.Cu–B.Cu |

HV net (PHANTOM, V_BOOST, BP_CAPSULE) clearance: **0.5 mm** to any other net (enforced via op-txm.kicad_dru).

---

## Pad position reference (absolute canvas coords)

All components are placed relative to board centre (100, 100).

### U1 OPA1642 SOIC-8 at (100, 81), pitch 1.27 mm
Left pads X=97.3: pin1=SIG_EQ(79.095), pin2=SIG_EQ(80.365), pin3=GND(81.635), pin4=N15V(82.905)  
Right pads X=102.7: pin5=GND(82.905), pin6=SRV_INT(81.635), pin7=SRV_OUT(80.365), pin8=P15V(79.095)  
Pad half-width = 0.775 mm → right-pad right edge = **103.475 mm** (safe-zone boundary for P15V trunk)

### U3 TPS7A3901 WSON-12 at (100, 110), pitch 0.5 mm
Left pads X=98.35: p1=P48V_LDO(108.75), p2=P48V_LDO(109.25), p3=TPS_FB_NEG(109.75), p4=N15V(110.25), p5=TPS_FB_NEG(110.75), p6=P48V_LDO(111.25)  
Right pads X=101.65: p7=P48V_LDO(111.25), p8=TPS_FB_POS(110.75), p9=P15V(110.25), p10=TPS_FB_POS(109.75), p11=P48V_LDO(109.25), p12=P48V_LDO(108.75)  
EP (GND) centre (100, 110), 1.7×1.7 mm

### U2 LR8 SOT-89 at (91, 110.5)
pin1=LR8_ADJ(89.5, 112.5), pin2=P48V_LDO(91.0, 112.5), pin3=PHANTOM(92.5, 112.5), tab=PHANTOM(91.0, 108.5)

---

## DRC fix batches (see drc-fix-plan.md for detail)

| Batch | Root cause | Status |
|-------|-----------|--------|
| B1 | Move V_BOOST trunk X=108.8 → X=111.5 (clears audio zone right side) | TODO |
| B2 | Move P15V trunk X=103.5 → X=104.5 (clears U1 right pads + N15V) | TODO |
| B3 | Reroute N15V around P48V_LDO stubs (not through Y=108.5) | TODO |
| B4 | Jog PHANTOM trunk west of LR8_ADJ pad at (89.5, 112.5) | TODO |
| B5 | Reroute P48V_LDO from U2 around SIG_EQ trunk at X=93.5 | TODO |
| B6 | Fix XLR_COLD jog X=110.7 → X=110.3 (clears XLR2 HOT pad) | TODO |
| B7 | Move GND via (88,121) — SIG_EQ trunk endpoint; fix SIG_EQ→TX_DRV_HOT net | TODO |
| B8 | Connect TPS_FB_POS/NEG to U3 pins 8,10 and 3,5 | TODO |
| B9 | Connect GND islands (decoupling cap GND pads → stitching vias) | TODO |

---

## File map

```
pcb/
  layout.py          — all component placement + routing (edit this)
  outline.py         — board outline, mounting holes, TX cutout (rarely edit)
  op-txm.kicad_dru   — custom HV clearance rules
  op-txm.kicad_pcb   — generated (gitignored, regenerate with layout.py)
  DRC.rpt            — generated (gitignored, save from KiCad DRC dialog)

docs/
  drc-fix-plan.md    — root-cause analysis + batch fix plan
  working-approach.md — this file
  pcb_routing_knowhow.md — general routing rules (ported from OCM)
```

---

## Git commit hygiene

- One commit per completed batch
- Commit message format: `pcb: fix <short description> (DRC Bn)`
- Never commit .kicad_pcb or DRC.rpt (gitignored)
- After all DRC errors resolved → final commit: `pcb: DRC clean, ready for Gerber export`
