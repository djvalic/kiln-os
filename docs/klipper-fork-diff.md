# Flashforge Klipper fork vs. upstream (AD5X)

What Flashforge changed in the Klipper host software on the AD5X, what each change is for, and what
replaces it on mainline Klipper. Source of the first-draft mainline config: `klipper/ad5x.cfg`.

Clean-room note: this describes behaviour in our own words. The stock files and the matching upstream
files were compared on a local copy; they are not in this repository.

## Sources

The paths are local copies of the stock firmware (`firmware/`, not in the repository).

| Source | What it gave |
|---|---|
| `firmware/ff-repo/stock5x/usr/prog/klipper/` | Full fork tree (zMod's ghzserg/FF mirror of an AD5X rootfs, firmware version unknown). Runs as `/usr/prog/klipper/klippy/klippy.py /usr/data/config/printer.cfg` under Python 3.8.2. |
| `firmware/stock-3.1.0/.../software-3.1.0/` | The 3.1.0 update overwrites `extruder.py`, `virtual_sdcard.py`, `exclude_object.py`, `query_adc.py` and `printer.base.cfg` (see its `run.sh`). Those copies win over the stock5x ones. |
| `firmware/zmod-repo/Native_firmware/config/ad5x/printer.cfg` | The stock `printer.cfg` (`[extruder]` and friends plus a SAVE_CONFIG block from one unit). `printer.base.cfg` there is byte-identical to the 3.1.0 one. |
| MCU data dictionaries of the stock board firmware | Cross-check of the base date, and which MCU commands exist. |

**The stock5x tree is not pure stock.** Its `virtual_sdcard.py` carries a zMod patch (a `# zmod 1.5`
comment and a call to zMod's `_A_CHANGE_FILAMENT` macro). The other three files the 3.1.0 update ships
are byte-identical to stock5x. No other zMod markers were found in `klippy/`, but files 3.1.0 doesn't
ship can't be proven unmodded.

## Upstream base: v0.12.0-256-g6d7005026 (2024-06-21)

**Confidence: high.** Method: hash every file in the fork tree (git blob hash) and compare against
`git ls-tree` of every upstream commit from Dec 2023 to Mar 2025.

- Best match: `6d70050261ec` "temperature_mcu: Enhance ADC out of range error reports" (2024-06-21).
  2115 of 2137 files match exactly, and every remaining difference is a Flashforge change (below).
- The next upstream commit (`4d21ffc1d`, 2024-06-27) only adds a Tronxy config the fork doesn't have,
  so the base sits between those two commits.
- `docs/Config_Changes.md` in the fork ends at 20240415, which fits.
- Cross-check: both MCU images were built from upstream source of June to September 2024,
  and zMod calls the AD5X native MCU firmware "Klipper 12".

Two oddities in the dating:
- `mcu.py` has the MCU clock check change that upstream merged on **2024-10-26** (`f0a779771`), so
  Flashforge backported at least one later commit. The MCU images are dated 2024-11-22 and 2024-11-25.
- `reactor.py` still has a typo upstream fixed on **2023-03-14** (`0d5b96a60`). Flashforge seems
  to carry whole patched files forward from an older fork (likely the Adventurer 5M one) instead of
  rebasing patches. The typo is in the epoll reactor, which Klipper doesn't use (it picks the poll
  reactor), so it does nothing.

## Changed and added files

Classification:
- **drop**: not needed on the open stack.
- **re-implement**: needed, but as a mainline extra, macro, config value or OS setting, not a fork patch.
- **rebuild**: a printer feature to rebuild on mainline (leveling, IFS, sensors and so on).

### klippy core

| File | What changed | Class |
|---|---|---|
| `klippy/mcu.py` | (1) Homing trigger-sync timeout doubled from 25 ms to 50 ms. Homing X uses steppers on the mainboard and an endstop on the eboard, so it's multi-MCU homing over two 230400-baud UARTs. (2) The "MCU running at the wrong MHz" error only fires on a drift above 1%. Upstream has had (2) since 2024-10-26. | (1) **re-implement only if needed**: mainline has no config option for it. If X homing fails with "Communication timeout during homing", carry a one-line patch. (2) **drop**, already upstream. |
| `klippy/reactor.py` | Main reactor thread renices itself to -10 and logs it. Carries the old epoll typo (above). | **re-implement** at OS level (systemd `Nice=` / `CPUSchedulingPolicy=` for klippy). The host is a slow Ingenic MIPS SoC, so priority probably matters. |
| `klippy/serialhdl.py` | Serial background thread renices itself to -20. | **re-implement** at OS level, as above. |
| `klippy/chelper/serialqueue.c` | Same nice(-20) for the C serial thread. | **re-implement** at OS level, as above. |
| `klippy/chelper/__init__.py` | Compiler changed from `gcc` to `mips-linux-gnu-gcc`, so `c_helper.so` can be built on the printer or cross-built. | **drop**: our Buildroot package cross-builds `c_helper.so`. |
| `klippy/configfile.py` | `SAVE_CONFIG` asks for a firmware restart (MCUs reset too) instead of a host restart. The first restart request wins, so it's always a firmware restart. | **drop**. Run `FIRMWARE_RESTART` by hand if a saved value needs it. |
| `klippy/gcode.py` | `respond_info` no longer writes to the log. | **drop**: log volume / flash-wear tweak. |
| `klippy/toolhead.py` | `SET_VELOCITY_LIMIT` no longer records the limits in the log rollover header. Side effect: `SET_VELOCITY_LIMIT` with no arguments would hit an undefined variable. | **drop**. |
| `klippy/kinematics/extruder.py` (3.1.0) | Same for pressure advance: no rollover log entry. | **drop**. |
| `klippy/extras/statistics.py` | Stats logged every 2 s instead of 1 s. | **drop**. |
| `klippy/extras/shaper_calibrate.py` | Adds an unused `import os`. No behaviour change. | **drop**. |

### klippy/extras

| File | What changed | Class |
|---|---|---|
| `extras/virtual_sdcard.py` (3.1.0) | **IFS colour-change hook.** While FFM ("four-in-one", the IFS) is on, a line that is exactly `T0` to `T15` doesn't go to the G-code parser. If the channel differs from the loaded one, the print loop does `M400`, sets a `refuelling` flag in its status, and **blocks reading the file** until something clears the flag or the print pauses or stops. `firmwareExe` polls the status, does the whole swap itself (cut, IFS, purge), then sends `SDCARD_CLEAR_REFUELLING`. Adds `SDCARD_SET_CHANNEL CHANNEL=` (sets the loaded channel), `SDCARD_ENABLE_FFM ENABLE=0/1`, status fields `channel` and `refuelling`, and the `.gx` extension (Flashforge G-code with a binary preview header). Files open as UTF-8 with bad bytes ignored, and the case-insensitive filename fallback is gone. | **rebuild** (IFS). Mainline runs `T0`–`T3` as normal macros, and `ifs.cfg` maps them to `IFS_SWAP CHANNEL=<tool_map[n]>` (slot n+1 unless `IFS_MAP_TOOL` changed it), which blocks the G-code queue by itself. No print-loop hook, polling client or `SDCARD_*` command is needed. `.gx`: **drop** (slicers export plain G-code for Klipper). Encoding: **drop** (mainline reads files as bytes now). |
| `extras/exclude_object.py` (3.1.0) | Inserts reactor sleeps: 10 ms on every `EXCLUDE_OBJECT_START`/`END`, and 5 ms every 10 moves once any object has been excluded. Adds a `clear_mem` status flag (set while the current object is excluded, presumably so `firmwareExe` can react). Silences the "no object active" and "name mismatch" messages. | **drop**. The sleeps look like a workaround for the slow host being starved when it skips through excluded moves. If mainline shows "Timer too close" or a stuttering UI while objects are excluded, revisit. |
| `extras/query_adc.py` (3.1.0) | Adds `GET_FILAMENT_VALUE` and `GET_CUT_VALUE` (print the raw ADC of the sensors declared as `[temperature_sensor filamentValue]` and `[temperature_sensor cutValue]`) and a status object `{value, cut}` with both raw values for `firmwareExe`. Hard-codes those two sensor names. | **rebuild** (filament sensors). `printer.cfg` keeps the same two pseudo-thermistor sensors and defines `GET_FILAMENT_VALUE` / `GET_CUT_VALUE` as macros over mainline `QUERY_ADC NAME="temperature_sensor …"`. Still to build: thresholds, and a real runout / presence sensor plus a cut check on top. |
| `extras/heaters.py` | PID "settled" test loosened from ±1 °C and 0.1 °C/s to ±3 °C and 0.9 °C/s, so `M109`/`M190` return much sooner. | **drop**. If faster waits are wanted, override `M109`/`M190` with `TEMPERATURE_WAIT` in a macro, which keeps it visible in config. |
| `extras/tmc.py` | **Disables Klipper's TMC error checking**: no `DRV_STATUS`/`GSTAT` read at enable, and no periodic once-a-second check. A driver overtemperature, short or reset goes unnoticed. | **drop** (keep mainline checks: a safety gain). Risk: if the stock hardware or UART links throw spurious errors, mainline will shut down where stock carried on. Watch for it on first runs. |
| `extras/homing.py` | Adds `ADJUST_ENDSTOP_POS STEPPER=<name> OFFSET=<mm>`: writes `position_endstop` for that stepper into the pending SAVE_CONFIG. `firmwareExe` uses it to apply its per-unit X/Y home offsets (`xOffset`/`yOffset` in its settings file; zMod's "fix home" USB tool sets them). | **re-implement** as plain config: measure the offsets once and put them in `position_endstop`. |
| `extras/bus.py` | Software I2C buses take an extra `interval` option, and gain `set_interval` / `set_pulse` methods that send the Flashforge-only MCU commands `set_radar_interval` and `set_radar_sync_pulse`. The I2C setup message gets an extra `radar_interval` field (a protocol change mainline can't talk to). | **drop**. Only `bl24c16f.py` uses them, and the AD5X config doesn't declare that device. |
| `extras/bl24c16f.py` (added) | Driver for a BL24C16F 2 KB I2C EEPROM over 8 I2C addresses. G-code: `EEPROM_READ`, `EEPROM_WRITE_BYTE/INT/FLOAT`, `EEPROM_DEBUG_*` variants, `EEPROM_POS`, `EEPROM_PRINTER_INFO` (reads a saved file position and E position: **power-loss recovery**), plus `SET_INTERVAL` / `SET_PULSE` (the "radar" commands). Address constants for camera calibration data (pixel/mm, image size, camera/tag offsets, matrix). | **drop** on the AD5X: there's no `[bl24c16f]` section, so the module never loads. It reads like shared code for other Flashforge models (camera, power-loss EEPROM). If power-loss recovery is wanted later, use a mainline-style approach (e.g. the AD5M mod's `power_loss_recovery.py`, which saves to disk). |

### Added outside klippy/

| File | What it is | Class |
|---|---|---|
| `checkEboard` | Small MIPS binary. Opens `/dev/ttyS5`, waits for the eboard bootloader's ready message, and sends the ACK that starts the eboard application. `firmwareExe` has the same routine (`bootSerialMainEboardMcu`). | **re-implement**, and it **blocks startup**: without it the eboard stays in its bootloader and `[mcu eboard]` never connects. Needs a tiny open boot helper run before klippy (the AD5M mod has `device_tools/mcu/boot_eboard_mcu.c`); done, `tools/boot_eboard.py` (item 6 below). |
| `klipperDaemon`, `moonrakerDaemon`, `start.sh` (3.1.0) | start-stop-daemon init scripts: Python 3.8.2 paths, config `/usr/data/config/printer.cfg`, log `/usr/data/logs/printer.log`, API socket `/tmp/uds`. | **drop**. Replaced by our own init/systemd units in the Buildroot image (Phase 6). |

### MCU side, for completeness

The stock MCU images add `set_radar_interval`, `set_radar_sync_pulse` and a
`Mainboard`/`Exboard close=… Close_num=… Temp_waketime=…` message. In the host fork, the radar
commands are only used through `bus.py` by `bl24c16f.py` (unused on the AD5X). **Nothing in the fork
handles the `close=` message**: no klippy module mentions it. It may be consumed outside Klipper or not
at all. All three are **drop**: mainline MCU firmware won't have them and nothing we keep needs them.

Checked: **mainline host + stock MCU firmware doesn't work.** A batch-mode run of mainline klippy with
the stock data dictionaries stops at configuration with "MCU Protocol error" (the stock firmware has
the old `config_lis2dw` format). Both boards must be reflashed with mainline MCU firmware. Mainline
already has N32G45x support (`MACH_N32G45x`, since 2023-04-07), with a 64 KiB bootloader option
(2025-08-21) and 144 MHz clocking (2026-09-30), so the MCU side may not need a fork at all. Check by
building.

## Kiln OS patches on mainline Klipper

The host Klipper is mainline at the pin in `buildroot/package/klipper/klipper.mk`. Buildroot applies
every `buildroot/package/klipper/NNNN-*.patch` in order, without fuzz, before the build. A patch that
no longer applies after a Klipper bump fails the build, so the builder holds that bump back.
`klipper/patches/` holds prepared patches that are **not** applied (apply them by hand if needed).

| Patch | What and why | Risk | Test |
|---|---|---|---|
| `0001-serialhdl-add-half-duplex-RS-485-TDD-support.patch` | Keep-alive poll for a half-duplex RS-485 MCU (the IFS on Klipper firmware, opt-in). GitHub pull request #16 by Hunter Laux. | Low: only an MCU that advertises `SERIAL_RS485_TDD` uses it. | `tools/test_serial_tdd.py` |
| `0002-motion_queuing-raise-homing-drip-buffer-to-300-ms.patch` | `DRIP_TIME` in `klippy/extras/motion_queuing.py` from 0.100 to 0.300 s (`DRIP_SEGMENT_TIME` stays 0.050). During homing and probing, steps go to the MCU in 50 ms segments with only `DRIP_TIME` queued ahead. On the AD5X the host can stall up to ~0.3 s (seen right after a large G-code upload), which emptied the step queue and stopped with "Timer too close" (issue #40). | Low: the MCU still stops at the trsync trigger and drops later steps, so there is no overshoot; about 0.2 s more wait after each homing or probe trigger (the restart waits for the queued steps); a few more queued step commands on the MCU. The trsync timeout is unchanged. | On the printer: `G28` several times, `BED_MESH_CALIBRATE`, a large upload then print. Klipper's test mode (`tools/test_image.sh`, `tools/test_wizard.sh`) does not pause, so it does not use `DRIP_TIME`. |
| `0003-led-output_pin-send-late-after-a-host-stall.patch` | `klippy/extras/led.py` (`update_leds`) and `klippy/extras/output_pin.py` (`GCodeRequestQueue._flush_notification`): an LED, output pin or fan change whose time is already less than the MCU's minimum schedule time (0.1 s) ahead when it is sent goes out for now + 0.1 s. An idle `SET_LED`, `SET_PIN`, `SET_FAN_SPEED` or `M106` is timed about 0.25 s ahead (the toolhead's idle start) but sent after the rest of its macro and the next reactor pass; a host stall of that size (Moonraker zipping timelapse frames) left it in the past and the MCU stopped with "Timer too close" (issue #40). Nothing changes while the host keeps up; file output (batch) mode and step timing are unchanged. | Low: after a stall the change lands late (by up to the stall) instead of shutting the MCU down. | Idle `SET_LED` followed by a 0.3 s busy macro: no shutdown; LEDs, `SET_PIN` and `M106` during a print as before. |
| `0004-toolhead-do-not-log-every-SET_VELOCITY_LIMIT.patch` | `klippy/toolhead.py` `cmd_SET_VELOCITY_LIMIT`: the `toolhead: max_velocity ...` block goes to the rollover header only (`log=False`), not into klippy.log on every call. Slicers send `SET_VELOCITY_LIMIT` per feature; one user's klippy.log reached 82 MB in a boot, most of it this block (issue #40). Stock Flashforge's fork had dropped this logging too. A plain `SET_VELOCITY_LIMIT` still answers on the console. | Low: the log no longer shows limit changes during a print; each new log still starts with the current limits. | A print with per-feature accel adds no `toolhead:` blocks. |
| `0005-serialhdl-rate-limit-the-log-of-unhandled-MCU-messages.patch` | `klippy/serialhdl.py` `handle_default`: a message without a handler (`got {...}`) is logged in full for the first 20 of each name, then as one count line every 60 s while they keep coming, and the count left at disconnect. After a failed connect (an MCU still in shutdown after `M112` and a host reboot) the boards kept sending `analog_in_state`: 14852 lines (2.5 MB) in 6.5 min on one printer. | Low: only the log; the first 20 of each still show the message. | `tools/test_ad5x_log.py` (`UnhandledTest`). |
| `0006-configfile-log-the-config-in-full-only-when-this-log-lacks-it.patch` | `klippy/configfile.py` `log_config`: when the same config (sha1) is already in full further up the same klippy.log (its inode, size and rollover time checked against `printer_data/comms/klippy-config.json`), a one-line note `===== Config file unchanged since ...` instead of the 45 KB config at every start and `RESTART`. The rollover header at the top of each day's file still has it in full; batch mode (`-o`) always logs it. | Low: a log cut by hand may lack the config; the next start with a changed config, a new file or a new day writes it again. | `tools/test_ad5x_log.py` (`ConfigOnceTest`). |
| `0007-reactor-drop-a-completion-s-waiter-when-pause-raises.patch` | `klippy/reactor.py` `ReactorCompletion.wait`: the waiting greenlet is removed in a `finally`, also when `pause()` raises. Before, a wait with pauses disabled (a `SAVE_VARIABLE` from a `klippy:ready` handler: `save_variables` waits on the threaded executor at the pin) left it in the list, and the executor's later `complete()` crashed the reactor with `AttributeError: 'NoneType' object has no attribute 'timer_is_running'`, using up klippy's one retry for unhandled exceptions. Seen once after an `M112` on 2026-11-09, triggered by the IFS save fixed in v0.0.51. Not fixed upstream (pin is upstream master). | Low: only the error path; the `ReactorError` still reaches the caller. | `tools/test_klipper_reactor.py` (real reactor; fails without the patch). |
| `0008-mcu-reset-an-MCU-still-in-shutdown-when-klippy-starts.patch` | `klippy/mcu.py`: at the first `get_config` of a fresh klippy (`start_reason` `startup`: a host reboot or a Klipper service restart), an MCU that answers `is_shutdown` and resets by command (`restart_method: command`, as all AD5X boards) gets the automated firmware restart upstream uses for a CRC mismatch (`_check_restart`, "Attempting automated MCU ... restart: MCU still in shutdown at startup"). Nothing at boot resets the boards on a warm reboot, so after an `M112` and a reboot klippy stayed at "Can not update MCU config as it is shutdown" until a FIRMWARE_RESTART by hand. A `RESTART` in a running session is unchanged; after the automated restart the error stands, so it can't loop. | Medium: a shutdown (an `M112` or a board fault) is cleared after a host reboot without anyone acknowledging it; the boards come up as after a power cycle. | `tools/test_klipper_mcu_restart.py`; on the printer: `M112` then reboot, a normal reboot, a cold start. |
| `0009-configfile-let-ad5x_plugins-write-the-plugin-list-before-a-config-read.patch` | `klippy/configfile.py` `read_main_config`: Kiln only. Before the config is read (every start, `RESTART`, `FIRMWARE_RESTART`) it calls `extras.ad5x_plugins.before_config_read()`, which writes `plugins-active.cfg` (included by `ad5x.cfg`) from the printer's `plugins.cfg`, with each enabled plugin that can't run (incompatible, broken, missing, a required plugin off, a conflict) left out, so its config isn't read (`docs/plugins.md`). Klipper has no step of its own before the config read; without it a hand edit of `plugins.cfg` would apply only after a reboot when the last start stopped before `[ad5x_plugins]`. Without that module (plain Klipper) nothing changes. | Low: an error there is logged and the config is read as it is. | `tools/test_ad5x_plugins.py` with the builder's klippy (Klipper's own config reader after a hand edit; skipped on an unpatched klippy); a batch-mode klippy run with a stale list. |

## Flashforge G-code commands, status fields and config sections

### Commands added by the fork

| Command | Used for | Mainline replacement |
|---|---|---|
| `SDCARD_CLEAR_REFUELLING` | `firmwareExe` says the colour swap is done, so the print continues | Not needed: `IFS_SWAP` (klipper/extras/ifs.py) blocks until the swap is done |
| `SDCARD_SET_CHANNEL CHANNEL=` | Tell the print loop which IFS channel is loaded | ifs.py tracks the loaded channel itself (`save_variables` `ifs_loaded`; `IFS_SET_CHANNEL`) |
| `SDCARD_ENABLE_FFM ENABLE=` | Turn the T-line hook on or off per print | Not needed. If single-colour prints with stray `Tn` must skip swaps, add a flag variable to the `T0`–`T3` macros |
| `GET_FILAMENT_VALUE`, `GET_CUT_VALUE` | Raw ADC of the head filament sensor and cutter sensor | Macros over `QUERY_ADC NAME="temperature_sensor filamentValue/cutValue"` (in `printer.cfg`) |
| `ADJUST_ENDSTOP_POS STEPPER= OFFSET=` | Store per-unit X/Y home offsets | Edit `position_endstop` directly |
| `EEPROM_*`, `SET_INTERVAL`, `SET_PULSE` | bl24c16f EEPROM and "radar" (not configured on the AD5X) | None needed |

### Status fields added by the fork (read by `firmwareExe` over the API socket)

| Field | Replacement |
|---|---|
| `virtual_sdcard.channel`, `virtual_sdcard.refuelling` | `printer.ifs` status from ifs.py |
| `query_adc.value`, `query_adc.cut` | `QUERY_ADC`, or a future sensor extra with a proper status |
| `exclude_object.clear_mem` | None (UI glue) |

### Macros and sections in the stock config

| Stock item | What it does | Mainline replacement |
|---|---|---|
| `[gcode_macro HOME]` → `MYG67` | `QUERY_ENDSTOPS`. If Y is already on its endstop, fake a position and back Y off 20 mm. Then home Z (to max, bed down), X, Y. | `[homing_override]` + `_HOME_ZXY` in `printer.cfg`, same logic on plain `G28`. Differences: the Y back-off runs on any Y home (stock runs it only on the full HOME), and it keeps the current Z height instead of setting Z to 0 |
| `[gcode_macro M106]` / `M107` | Route `P`/`T` indexes 101 and 2 to a chamber fan (commented out, the AD5X has none); everything else goes to `[fan_generic fanM106]` | Kept as macros on `[fan_generic fanM106]` (`klipper/ad5x.cfg`); indexes 2, 101 and 102 are ignored |
| `[gcode_macro M900]` | Marlin-style pressure advance | Kept as-is (mainline has no M900) |
| `[fan_generic fanM106]` | Part fan, a generic fan because `firmwareExe` drives it by name | Kept: `[fan_generic fanM106]` on `eboard:PB5` (HelixScreen's AD5X preset and stock's tools use the name) |
| `[fan_generic pcb_fan]` on PA5 | Board fan switched by `firmwareExe` | `[fan_generic pcb_fan]` kept on by `[pcb_fan_watch]` while a motor or heater is on or a print runs |
| `[temperature_sensor filamentValue/cutValue]` | Analog sensors abused as thermistors so their ADC gets sampled | Kept, see above |
| `[lis2dw]`, `[resonance_tester]`, `[input_shaper]` | Accelerometer on the eboard (software SPI) | Same sections, mainline syntax unchanged |
| `[printer] max_accel_to_decel` | Deprecated upstream 20240313, removed 20250811 | `minimum_cruise_ratio: 0.75` (same behaviour) |
| `[probe]` (pin `!PB3`) + `[bed_mesh]` | Nozzle-contact probe on bed strain gauges, 5×5 mesh | Same sections. Tare and Z-zero flow: see "Open questions" |
| `[bl24c16f]` | Not present in the AD5X config | — |

## Features to rebuild on mainline (from the fork and `firmwareExe`)

1. **IFS colour change**: replaces the `virtual_sdcard` hook plus the `firmwareExe` swap logic. Draft exists (`klipper/extras/ifs.py`, `klipper/ifs.cfg`).
2. **Head filament sensor and cutter sensor**: analog sensors. Head sensor (filament present at <= 0.30 or >= 0.72, stock settings): `klipper/extras/adc_filament_sensor.py` (runout; `[adc_filament_sensor toolhead]`, also published as `filament_switch_sensor toolhead`) and `head_sensor` in `ifs.py` (stops loads and unloads, gates the cut), both enabled. Cutter sensor: not used yet.
3. **Z zero and leveling**: stock homes Z to a max switch and keeps that zero; `firmwareExe` tares the bed strain gauges over `/dev/ttyS7` before each probe and offsets the mesh by the centre drift before each print (`docs/bed-weighing-board.md`). Rebuilt as `klipper/extras/ad5x_weight.py` and the `_CHECK_Z` macro.
4. ~~**Per-unit calibration from `firmwareExe`'s settings file**~~: done. `klipper/unit.cfg` (`[gcode_macro _AD5X_UNIT]`: `z_offset` from `zProbeOffset`, `cut_x_offset`/`cut_y_offset`, `x_offset`/`y_offset`), generated by `tools/ad5x_unit_cfg.py` from `Adventurer5M.json`; the image does this at first boot.
5. **Purge and wipe**: `firmwareExe` computes flush volume from the colour pair (1 or 2 purge rounds) with brush wipes. Rebuilt in `ifs.py` (`purge_rounds: 0`) and `ifs.cfg` `purge_gcode`.
6. ~~**Eboard boot handshake** (`checkEboard`)~~: done. `tools/boot_eboard.py` (installed as `boot_eboard`), run by `ad5x-mcu boot` from `S60ad5x-eboard` before Klipper starts. **Process priority**: `S61klipper` starts klippy at nice -10.

## AD5X vs AD5M (prior art: xblax/flashforge_ad5m_klipper_mod)

The AD5M mod runs mainline-based Klipper (fork xblax/klipper, v0.13) on the same N32G455 boards.
Its `printer_configs/printer.base.cfg` is a good syntax reference. Where the AD5X differs:

| | AD5M (mod) | AD5X |
|---|---|---|
| Host | ARM | Ingenic XBurst2 MIPS (`mips-linux-gnu`), Python 3.8.2 on stock |
| Mainboard / eboard tty | ttyS5 / ttyS1 | **ttyS2 / ttyS5** |
| Bed origin | Centre (±110) | Corner (0–220) |
| Y endstop | eboard PB11 | mainboard PC12 |
| Probe pin | `!PB4` | `!PB3` |
| Load cell | Bridged through extra MCU commands (`flashforge_loadcell`, H1/H7 to the weight board); stock 5M config also had `weightValue` and `level_h1..3` pins | Neither: no weight sensor or level pins in the stock config, no load-cell commands in the stock MCU firmware |
| Filament sensors | Digital `filament_switch_sensor` (PB14, PE1) | Analog `filamentValue`/`cutValue` on the eboard, plus the IFS's own sensors |
| Extra hardware | Chamber/internal/external fans, TVOC, servo, power button, extruder heater-enable pin (eboard PB7) | None of these in stock config. **No heater-enable pin is declared on the AD5X**, worth checking on the board |
| Accelerometer | ADXL345 | LIS2DW |
| Multi-material | — | IFS on ttyS4 (own firmware, not Klipper) |

## Open questions / couldn't determine

- ~~How the AD5X tares its strain gauges~~: answered, a separate weighing board on `/dev/ttyS7` (`docs/bed-weighing-board.md`). Still open: its real reply text and the `H2`/`H3` calibration commands.
- ~~The ADC thresholds for `filamentValue`~~: present at <= 0.30 or >= 0.72 (stock settings). `cutValue` still unknown.
- Whether X homing on mainline needs the longer trsync timeout.
- Whether the stock5x tree has more zMod edits in files 3.1.0 doesn't ship (none found).
- What `close=` / `Close_num` / `Temp_waketime` mean (MCU-side, not handled by the host fork).
- Why the bed is limited to 40% power (`max_power: 0.4`), kept as-is.
