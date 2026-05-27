# DRC Fix Plan — op-txm

Generated: 2026-05-27. DRC round 2 had **273 violations** (pcb/DRC.rpt).

## Strategy (from research)

1. Fix **hard shorts** first — each short can cascade into 5–15 solder_mask_bridge + tracks_crossing entries
2. Fix **clearance violations** (V_BOOST/PHANTOM custom rules) next
3. Fix **unconnected pads** last (less board-breaking than shorts)
4. Ignore all **warnings** until errors are zero — text_height, lib_footprint, silk_overlap are cosmetic
5. WSON-12 (U3) adjacent-pad clearances are **structural** (0.5mm pitch vs 0.5mm clearance rule) — accept/waive

## Root-cause shorts (each one drives many errors)

### S1: P15V trunk (X=103.5) vs N15V trunk (X=103.425) — 0.075mm apart
- P15V: `_seg(103.5, 107.0, 103.5, 79.095, "P15V")` — runs Y=107 → 73
- N15V: `_seg(103.425, 108.5, 103.425, 110.0, "N15V")` — overlaps at X≈103.45
- Also: P15V at X=103.5 passes U1 right pads (pin5=GND at 102.7,82.905; pin6=SRV_INT at 102.7,81.635; pin7=SRV_OUT at 102.7,80.365) — pad half-width=0.775mm → pad right edge = 103.475mm → P15V at 103.5 is only 0.025mm clear → DRC short
- **Fix**: Move P15V trunk east to X=104.5 (safe margin from U1 pads and N15V)

### S2: N15V horizontal at Y=108.5 crosses P48V_LDO stubs at Y=108.75
- N15V runs X=96.5→103.425 at Y=108.5 (W=0.3mm → top edge at Y=108.35)
- P48V_LDO stubs: left at (98.35,108.75) pad half-h=0.125 → bottom edge 108.625 — gap only 0.275mm
- Also shorts: P48V_LDO east trunk at X=102.5 runs Y=105→112 — N15V at Y=108.5 crosses it
- **Fix**: Route N15V below Y=112 (south of P48V_LDO east trunk end at Y=112), then approach R_TPS_N1 from below

### S3: P48V_LDO horizontal at Y=105 crosses SIG_EQ trunk at X=93.5
- P48V_LDO: `_seg(94.95, 105.0, 102.5, 105.0)` — passes X=93.5 where SIG_EQ trunk runs Y=87.5→121
- Wait: seg starts at X=94.95, so it starts right of X=93.5 — crossing happens because SIG_EQ vertical passes at X=93.5 while P48V_LDO crosses at Y=105
- Actually P48V_LDO starts at X=94.95 — it does NOT cross X=93.5. But DRC says they cross…
- Re-check: SIG_EQ trunk is at X=93.5 going from Y=87.5 to Y=121. P48V_LDO horizontal is at Y=105 from X=94.95 to X=102.5. These do NOT intersect geometrically. This must be a clearance/netclass HV issue.
- The HV netclass clearance is 0.5mm. SIG_EQ at X=93.5 is 1.45mm from P48V_LDO start at X=94.95 — that's fine. But P48V_LDO also has the `_seg(86.425, 105.0, 86.425, 107.5)` segment. Neither crosses X=93.5.
- Actual error: "tracks_crossing Rule: netclass 'HV'" @ P48V_LDO (94.95,105) length 8.525 and SIG_EQ (93.5,87.5) length 33.5. These two don't cross geometrically — but HV clearance 0.5mm is violated between them (SIG_EQ at X=93.5 is 1.45mm from P48V_LDO at X=94.95, which is fine). Hmm, actually 1.45mm > 0.5mm so that's OK.
- Wait — the "tracks_crossing" entry for HV means they're within HV clearance, not that they literally cross. At Y=105, SIG_EQ is at X=93.5 and P48V_LDO starts at X=94.95. Gap = 94.95 - 93.5 - 0.5*0.3 - 0.5*0.3 = 1.45 - 0.3 = 1.15mm. That's fine.
- But DRC reports they cross at these coords. This may be because SIG_EQ long segment (Y=87.5 to 121) at X=93.5 and P48V_LDO horizontal at Y=105 DOES geometrically cross if the segment bounding box overlaps... actually they would cross if one is vertical at X=93.5 and the other is horizontal at Y=105. But P48V_LDO starts at X=94.95, not X=93.5.
- OH WAIT. There's also `_seg(91.0, 110.5, 94.95, 110.5, "P48V_LDO")` which runs from X=91 to X=94.95 at Y=110.5. That crosses SIG_EQ trunk at X=93.5. That's the actual crossing! P48V_LDO at Y=110.5 crossing SIG_EQ trunk X=93.5, Y=87.5→121.
- **Fix**: Route P48V_LDO from U2 pin2 at (91,112.5) → to C_LR8_OUT not via Y=110.5 (which cuts across SIG_EQ). Perhaps go south to Y=114 first, then east past X=93.5, then north.
- But that creates other issues... Let me check what the actual crossing track DRC says: "@(91.0000 mm, 110.5000 mm): Track [P48V_LDO] on F.Cu, length 3.9500 mm" → this is the U2→C_LR8_OUT segment. And "@(93.5000 mm, 87.5000 mm): Track [SIG_EQ] on F.Cu, length 33.5000 mm" → the long vertical trunk.

Actually, SIG_EQ trunk at X=93.5 runs from Y=87.5 to Y=121. P48V_LDO at Y=110.5 runs from X=91.0 to X=94.95. Geometrically: does X=93.5 fall in [91.0, 94.95]? Yes! Does Y=110.5 fall in [87.5, 121]? Yes! So they DO cross geometrically.

- **Fix**: Move SIG_EQ trunk left to X=91 (or further left), OR route P48V_LDO around SIG_EQ.

### S4: PHANTOM trunk X=89.95 crosses LR8_ADJ at (89.5,112.5)
- PHANTOM runs at X=89.95 from Y=100→120. U2 pin1 LR8_ADJ is at (89.5,112.5), pad half-width = 0.5mm → pad right edge = 90.0mm
- PHANTOM at X=89.95 has half-width 0.20mm → left edge 89.75. LR8_ADJ pad right edge 90.0. Gap = 90.0 - 89.75 = 0.25mm < 0.5mm HV clearance
- Wait actually it's a short: "shorting two nets (nets LR8_ADJ and PHANTOM)" — the track literally overlaps the pad.
- PHANTOM at X=89.95, W_HV=0.40mm → right edge = 90.15mm. LR8_ADJ pad centre X=89.5, pad half-width=0.5mm → right edge = 90.0mm, left edge = 89.0mm. PHANTOM right edge 90.15 > pad left edge 89.0 and PHANTOM left edge 89.75 < pad right edge 90.0 — yes they overlap.
- **Fix**: Move PHANTOM trunk to X=89.0 (right edge = 89.2mm, clear of LR8_ADJ left edge at 89.0mm — actually still touches). Or X=88.5 (right edge 88.7mm, clear of LR8_ADJ pad at X=89.0 left edge). 
- Actually LR8_ADJ pad is 1.0mm wide (SOT-89 pin1), so half-width = 0.5mm, pad = X=89.0..90.0. PHANTOM at X=88.5 has right edge at 88.7mm. Gap = 89.0 - 88.7 = 0.3mm. Still less than 0.5mm HV clearance.
- Better: PHANTOM at X=88.0, right edge 88.2mm. Gap to LR8_ADJ left edge (89.0) = 0.8mm > 0.5mm. But will X=88.0 conflict with anything else? C_LR8_IN at (91,106.5) has pad1-PHANTOM at (89.95,106.5). So we need PHANTOM to reach X=89.95 somehow. Could jog: X=88.0 south of U2 pin1, then east to X=89.95 above U2 pin1.
- U2 pin1 at Y=112.5. If PHANTOM trunk goes at X=88.0 from Y=100 to Y=111, then jogs east to X=89.95 at Y=111, then south to C_LR8_IN and U2 connections. That avoids LR8_ADJ at Y=112.5.

### S5: SIG_EQ trunk Y=87.5→121 at X=93.5 conflicts with multiple things
- Crosses P48V_LDO at Y=110.5 (see S3)
- Crosses GND via at (93.6,108.5) (only 0.1mm apart)
- Crosses GND track `_seg(92.05,106.5, 93.6,106.5)` at Y=106.5
- Too close to V_BOOST stubs at X=93.95 (Y=116,117)
- **Fix**: Move SIG_EQ trunk to X=90.0 or further left. BUT X=90.0 is where VSOURCE goes west... Need to coordinate.
- The SIG_EQ components are all at X=91 (R_IN, R_F, etc.). Their left pads are at X=90.425. So SIG_EQ trunk can't go further left than ~90.2. 
- Actually: the right pads feed into the trunk at X=93.5. If we move the trunk to X=90.0, we need to re-route the horizontal taps from right pads at X=91.575 → to trunk at X=90.0. But U1 left pads at X=97.3 would need longer horizontal runs.
- Alternative: Keep trunk at X=93.5 but fix individual conflicts: move GND via, reroute P48V_LDO, reroute V_BOOST.

### S6: SIG_EQ continues at Y=121 and hits GND via at (88,121)
- `_seg(93.5,121,88,121)` plus `_seg(88,121,88,123)` = SIG_EQ reaches TX_S3H at (88,123)
- But TX_S3H net is TX_DRV_HOT — SIG_EQ connecting to TX_DRV_HOT is intentional (op-amp drives transformer). The short is expected! These are the same electrical node.
- The GND via at (88,121) was placed as GND stitching — that's the real error. Move that stitching via somewhere else.

### S7: V_BOOST trunk at X=108.8 too close to right-side audio components
- V_BOOST at X=108.8 (W=0.40mm) right edge = 109.0mm
- C_INT pad1 SRV_INT at (107.95,83.0), pad half-width=0.40mm → right edge 108.35mm. Gap = 109.0 - 108.35 = 0.65mm. But custom clearance rule requires 0.5mm. Wait, 0.65 > 0.5 so should be OK.
- DRC says: "V_BOOST_clearance clearance 0.5000 mm; actual 0.2500 mm" for C_INT pad1 at (107.95,83.0) and V_BOOST track at (108.8,71) length 45mm. Hmm, actual=0.25mm.
- C_INT is 0603 at (109,83). Pad1 SRV_INT at (107.95,83.0), pad size 0.8×0.8. Pad half-width = 0.4mm → pad right edge = 108.35mm. V_BOOST at X=108.8, half-width = 0.2mm → V_BOOST left edge = 108.6mm. Gap = 108.6 - 108.35 = 0.25mm. YES matches!
- Also SRV_OUT, R_INJ, R_INT are at X=108-109 — V_BOOST at 108.8 runs right through them.
- **Fix**: Move V_BOOST trunk to X=111.0 or further right (right of all audio components).

### S8: XLR_COLD at Y=126 shorting XLR2 HOT pad at (112,126)
- XLR_COLD: `_seg(109.0,126, 110.7,126)` then east... but XLR2 HOT is at (112,126). The segment doesn't reach (112,126).
- Wait: `_seg(109.0,126.0, 110.7,126.0, "XLR_COLD")` — from TX_P2 pad to the jog at X=110.7. But TX_P2 at (109,126) pad half-size = 1.25mm (ring) → pad right edge = 110.25mm. XLR2 at (112,126) pad half-size = 1.25mm → pad left edge = 110.75mm. Gap between pads = 0.5mm. And the COLD track starts at the TX_P2 pad (109,126) and runs east. At X=110.7 it's still between the two pads. 
- DRC says `_seg(109.0,126, 110.7,126) "XLR_COLD"` shorts XLR2 HOT pad. TX_P2 pad right edge = 109+1.25=110.25. XLR2 pad left edge = 112-1.25=110.75. Track at X=109→110.7 at Y=126. Track end at X=110.7 is less than pad left edge at 110.75. So track is between the pads, not in them. Unless the pads are larger than 2.5mm diameter.
- th_pad uses `ring=2.5mm` so pad size=2.5mm, half=1.25mm. TX_P2 at X=109, right edge = 110.25mm. Track starts at pad centre (is connected), OK. XLR2 at X=112, left edge = 110.75mm. Track endpoint at X=110.7 < 110.75, so track does NOT enter XLR2 pad.
- But DRC says it shorts. Maybe the issue is that the track at Y=126, from X=110.7 going south to Y=129, has a length of 3.0mm and its Y-extent of Y=126 to 129 might enter XLR2 at (112,126)? No, that segment is at X=110.7, not X=112.
- Actually re-reading the DRC: `_seg(110.7,126, 110.7,129) "XLR_COLD" length 3.0mm` shorts `XLR2 HOT`. XLR2 is at (112,126). Pad size = 2.5mm diameter, so half = 1.25mm. Pad extends from X=110.75 to 113.25, Y=124.75 to 127.25. Track at X=110.7 — pad left edge at 110.75. Track right edge (W=0.2mm, half=0.1mm) at X=110.8. Pad left edge at 110.75. Gap = 110.75 - 110.8 = -0.05mm — overlap! The track RIGHT EDGE at 110.8 overlaps the pad LEFT EDGE at 110.75. That's the short.
- **Fix**: Move XLR_COLD vertical jog from X=110.7 to X=110.4 (right edge = 110.5mm, gap to XLR2 left edge at 110.75 = 0.25mm). Or use X=110.1 (right edge 110.2, gap 0.55mm > 0.5mm V_BOOST clearance... wait XLR is not HV). Default clearance is 0.2mm, so X=110.5 (right edge 110.6, gap to 110.75 = 0.15mm) — still too close. Use X=110.4 (right edge 110.5, gap 0.25mm > 0.2mm). Good.

## Unconnected pads to fix

### U1: P48V_LDO trunk gap at Y=105
- Segment from (86.425,105) to (94.95,105) and segment from (94.95,105) to (102.5,105) should join at X=94.95
- DRC says they're not connected — they SHOULD be at the same point but kiutils may not merge them
- **Fix**: These segments share endpoint (94.95,105) — they should connect. DRC might be confused. May need a bridging segment.

### U2: N15V gap
- Track at (96.5,108.5) not connected to track at (103.425,107)
- These are after S1/S2 fixes — rerouting will address this

### U3: TPS_FB_POS not connected to U3 pins 8 and 10
- U3 pin8 TPS_FB_POS at (101.65,110.75), pin10 at (101.65,109.75)
- R_TPS_P1 pad2 at (104.575,107.0) — the current FB_POS seg goes from pad1 to pad2 of R_TPS_P1
- Need: pad2 of R_TPS_P1 → U3 pins 8 and 10
- **Fix**: Add segments from (104.575,107.0) → (104.575,109.75) → (101.65,109.75) [connects pin10]; then (101.65,109.75)→(101.65,110.75) [connects pin8]. But these cross into P48V_LDO territory, need care.

### U4: TPS_FB_NEG not connected to U3 pins 3 and 5
- U3 pin3 at (98.35,109.75), pin5 at (98.35,110.75)
- R_TPS_N1 pad2 at (104.575,110.0) connects to R_TPS_N2 pad1 at (106.425,110.0)
- Need: pin3 and pin5 connected to the TPS_FB_NEG net
- **Fix**: R_TPS_N1 pad1 at (103.425,110.0) connects from N15V. R_TPS_N1 pad2 at (104.575,110.0) is TPS_FB_NEG. Add segs: (104.575,110.0) → east to avoid P48V_LDO → down/west to U3 pins.

### U5: GND islands
- Many decoupling cap GND pads floating (no F.Cu trace to stitching via)
- C_P15_100n p2 (96.575,73), C_P15_1u p2 (101.05,73), C_N15_100n p2 (104.575,73), C_N15_1u p2 (109.05,73)
- C_P15_OUT p2 (105.05,114), C_N15_OUT p2 (109.05,114)
- R_TPS_P2 p2 (107.575,107), R_TPS_N2 p2 (107.575,110)
- D1 p3 GND (91,115.7) → via at (91,114.5) gap 1.2mm
- C_RSVR p2 GND (96.05,117) → via at (96.05,118) gap 1mm
- C_LPF p2 GND (106.05,117) → via at (106.05,118) gap 1mm
- **Fix**: Add short GND trace segments connecting each pad to its nearby via or stitching bus

## Batch execution plan

| Batch | Fixes | Expected error reduction |
|-------|-------|--------------------------|
| B1 | Move V_BOOST trunk X=108.8 → X=111.5 (right of all audio); fix SRV_OUT/SRV_INT to not extend into V_BOOST zone | ~25 errors |
| B2 | Fix P15V trunk (move to X=104.5); fix N15V reroute around P48V_LDO | ~40 errors |
| B3 | Fix PHANTOM trunk jog west of LR8_ADJ; fix SIG_EQ trunk conflicts (move GND via, fix P48V_LDO path) | ~20 errors |
| B4 | Fix XLR_COLD short; fix SIG_EQ→TX_DRV_HOT (move GND via at 88,121) | ~10 errors |
| B5 | Connect TPS_FB_POS/NEG loops to U3 pins; connect GND islands | ~19 unconnected |

**WSON-12 (U3) adjacent-pad clearances**: Accept as structural — 0.5mm pitch, unavoidable.

## Key dimensions reference

- U1 SOIC-8 at (100,81): right pads X=102.7, pad half-width=0.775mm → pad right edge=103.475mm
- U3 WSON-12 at (100,110): left pads X=98.35, right pads X=101.65
- P48V_LDO east trunk: X=102.5, Y=105→112
- P48V_LDO horizontal trunks: Y=105 (X=86.425→102.5) and Y=112 (X=98.35→102.5)
- V_BOOST trunk to move: currently X=108.8 (Y=65→116)
- SIG_EQ trunk: X=93.5 (Y=77.5→121)
