# happy-hare

Happy Hare v4 MMU software integration for the Flashforge AD5X 4-channel IFS
(Intelligent Filament System).

Replaces the stock `[ifs]` driver with Happy Hare v4, providing:
- **Fast Toolhead Parking**: unloads ~142 mm above the 4-to-1 combiner instead
  of fully retracting 580 mm Bowden tubes on toolchanges.
- **Active Synchronized Extrusion**: slaves the IFS feeder stepper to Klipper's
  extruder stepper (`sync_to_extruder: 1`), feeding in lockstep during printing.
- **FlowGuard Protection**: continuous clog and tangle detection using the IFS
  analog spring buffers (`ifs:PC1`, `ifs:PC3`, `ifs:PB13`, `ifs:PB15`), including
  automatic current boosting to pull through spool resistance.
- **AD5X Purge Box Integration**: full trash box purge with part fan cooling
  dwell to solidify purge pellets, box edge scraping (`_PURGE_WIPE`), and silicone
  brush cleaning (`_NOZZLE_BRUSH`).
- **Compatibility Aliases**: maps `T0`–`T3`, `IFS_SWAP`, `IFS_LOAD`, `IFS_UNLOAD`,
  and `IFS_SELECT` to Happy Hare MMU commands.

## Usage

Enable the plugin:
```gcode
ENABLE_PLUGIN NAME=happy-hare
```

Disable the plugin (reverts to stock Kiln OS IFS driver):
```gcode
DISABLE_PLUGIN NAME=happy-hare
```

Or toggle the switch under **Settings > Plugins** on the touchscreen.
