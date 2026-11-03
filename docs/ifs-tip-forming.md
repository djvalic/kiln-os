# IFS Filament Unload: Mechanical Cutting vs. Thermal Tip Forming

This document compares the stock/legacy Flashforge AD5X mechanical blade cut routine with the Happy Hare thermal tip-forming unload routine.

---

## 1. Overview

| Feature | Legacy Method (`ifs.py` / Stock) | Happy Hare Method (`_MMU_FORM_TIP`) |
|---|---|---|
| **Mechanism** | Physical blade sliced against frame lever | Extruder motor thermal pull & cool |
| **Toolhead Movement** | Dashes to front-left corner (`X -1.7, Y -6.0`) | None (stays in place or at purge box) |
| **Frame Impact** | Slams against frame post to depress cutter lever | Zero contact with frame |
| **Risk of Lost Steps** | High if cutter post overshoots or binds | Zero (no toolhead travel) |
| **Hotend Remnant** | Leaves ~55 mm severed strand in hotend | None (entire strand extracted cleanly) |
| **Purge Requirement** | Requires ~90 mm purge to flush leftover piece | Standard color-change purge only |
| **Wear & Maintenance** | Blade wear, cutter arm spring fatigue | None (software-driven motor moves) |

---

## 2. Legacy Method: Mechanical Blade Cut

### How it works
1. **Target Position**: The toolhead moves to `X = CutXOffset - 2.5`, `Y = CutYOffset - 7.5` (with user offsets `CutXOffset: 0.8`, `CutYOffset: 1.5`, this targets `X -1.7, Y -6.0`).
2. **Cutting Action**: The toolhead hits the physical frame post on the front-left, pushing the spring-loaded blade lever into the filament channel ~55 mm above the nozzle.
3. **Extruder Back-off**: The extruder backs off 5 mm (`G1 E-5 F600`).
4. **Purge Box Move**: The toolhead moves to the purge box (`X 52.5, Y 229`).
5. **Retract**: The extruder retracts 60 mm (`G1 E-60 F600`) while the IFS feeder pulls the cut strand back to the IFS unit.

### Known Limitations
- **Step Loss / Coordinate Shift**: If the physical stop or frame corner resists slightly or if the travel speed is too aggressive (`F18000` / 300 mm/s), the X/Y stepper motors can skip steps on impact. This offsets the entire machine coordinate system, causing the subsequent poop-chute move and all future print moves to be misaligned.
- **Leftover Hotend Strand**: Slicing the filament ~55 mm above the melt zone leaves the lower piece inside the hotend. When the next color loads, the printer must extrude and purge ~90 mm of material at the purge box solely to push the severed segment out of the nozzle before the new color can begin printing.

---

## 3. Happy Hare Method: Thermal Tip Forming

### How it works
1. **No Toolhead Motion**: The toolhead does not travel to the frame post or cutter lever.
2. **Fast Initial Necking**:
   ```gcode
   G1 E-15 F3000
   ```
   A rapid 15 mm retraction at 50 mm/s pulls the molten plastic quickly upward into the transition/heatbreak zone, stretching the molten strand so it necks down and breaks thinly rather than forming a wide bulb.
3. **Cooling Dwell**:
   ```gcode
   G4 P1000
   ```
   A 1-second pause lets the thin tip solidify in the cooling zone so it does not deform or leave hairs in the Bowden tube.
4. **Cold-Zone Extraction**:
   ```gcode
   G1 E-45 F600
   ```
   A controlled 45 mm retraction pulls the solidified tip completely out of the extruder drive gears and into the Bowden tube.
5. **Bowden Traverse**: Happy Hare's IFS gear stepper takes over and pulls the strand back through the 680 mm Bowden tube to the IFS parking position behind the selector carriage.

### Advantages
- **No Step Loss**: Zero collision with the frame eliminates any possibility of coordinate shifts during unloads.
- **No Severed Plug**: The full strand is removed intact, eliminating the need to flush an entire 55 mm piece on subsequent loads.
- **Universal Reliability**: Consistent tip shape across tool changes without relying on blade sharpness.

---

## 4. Re-enabling the Mechanical Blade Cutter in Happy Hare

If mechanical cutting is explicitly preferred, Happy Hare can be configured to use a blade-cutting macro instead of tip forming by setting:

```ini
[mmu_parameters]
form_tip_macro: _MMU_CUT_TIP
```

And defining `_MMU_CUT_TIP` with carefully tuned, gentle approach coordinates to prevent hard frame impacts:

```jinja2
[gcode_macro _MMU_CUT_TIP]
description: Mechanical blade cutter move with gentle deceleration
gcode:
  {% set unit = printer['gcode_macro _AD5X_UNIT'] %}
  SAVE_GCODE_STATE NAME=MMU_CUT_TIP_state
  G90
  # Approach slowly to avoid hard mechanical frame impact
  G1 Y{unit.cut_y_offset - 7.5} F6000
  G1 X20 F6000
  G1 X{unit.cut_x_offset - 2.5} F300
  M400
  M83
  G1 E-5 F600
  M400
  # Back off from frame before moving to purge box
  G1 X20 F6000
  RESTORE_GCODE_STATE NAME=MMU_CUT_TIP_state
```
