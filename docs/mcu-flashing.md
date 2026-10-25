# MCU flashing: stock mechanism, mainline plan, way back

Plan for putting mainline Klipper on the two motion MCUs (mainboard, eboard) and getting back to
stock. Both boards of the developer's printer were flashed this way and run mainline Klipper
(v0.13.0-803-g4cd711119, `klipper/mcu-dicts/FLASHED`). Evidence is from the stock 3.1.0 update
(`firmware/stock-3.1.0/unpacked/`, git-ignored), the stock rootfs mirror
(`firmware/ff-repo/stock5x`), the behaviour of the stock app and its four control-1.1.1 flashing tools,
and the AD5M mod / xblax Klipper sources.

Summary:

- Mainboard: no Flashforge bootloader. The N32G455's **ROM ISP bootloader**, entered by the SoC
  driving BOOT0 and NRST over sysfs GPIO. It sits in mask ROM, so a bad app flash can always be
  fixed over serial.
- Eboard: Flashforge's **64 KB serial bootloader** at 0x08000000, app at 0x08010000. The flasher
  never sends addresses, so it can't overwrite the bootloader. It waits after every reset.
- IFS: own bootloader below 0x08010000. It waits after power-on, and after `F37`, whose handler
  erases its flag page at 0x0800D000. Klipper on it is opt-in (`/data/ad5x/ifs-klipper.enable`).
- Stock reflashes the MCUs at boot **only when flag files exist** (`Update`, `UpdateM`). It does
  not read the firmware version on the MCUs, so mainline on the boards does not trigger a
  re-flash. Stock with mainline MCUs simply fails to talk to them (see "Stock against mainline MCUs").
- Our build offsets match stock: mainboard 0x08000000, eboard 0x08010000.
- One gap in plain mainline: no Flashforge eboard bootloader bypass. After `FIRMWARE_RESTART`
  the eboard stays in its bootloader (see "Mainline gaps").

## Automatic updates (`ad5x-mcu`)

Kiln OS keeps both boards on the Klipper firmware its image was tested
against (`klipper/mcu-firmware/<FLASHED>/`, installed as
`/usr/share/ad5x/mcu/`). Nobody flashes by hand: `ad5x-mcu boot` runs at
every start (`S60ad5x-eboard`), before Klipper:

1. **Mainboard**: asks the firmware for its version (Klipper `identify` on
   `ttyS2`, `ad5x-mcu-version`). Anything else (Flashforge's firmware, an
   older Klipper, no answer): `NationsCommand -c -d --pn /dev/ttyS2 --fn
   mainboard.bin --v -r` through the chip's ROM bootloader, then identify
   again. The ROM bootloader can't be overwritten, so a failed write is
   retried at the next start.
2. **Eboard**: its bootloader accepts firmware only while it waits after
   power-on ("Ready" on `ttyS5`). If it waits and the last eboard flash on
   record (`/data/ad5x/mcu/eboard`) isn't this version: `IAPCommand
   eboard.hex /dev/ttyS5`, then `A` to start it. If its application already
   runs with another version (the SoC restarted without a power-cycle, e.g.
   right after the install), the screen asks to switch the printer off and
   on; the next start flashes it. Before that screen, the start counts as
   complete (`S99ad5x-booted`): the try-once boot flag otherwise still
   points at the recovery OS, and a user who switches off at once lands
   there instead (found in the 2026-10-19 round trip below).
3. **IFS**, only with `/data/ad5x/ifs-klipper.enable`: Klipper `identify`
   on `ttyS4` at 115200. Anything else: `ifsF37` (Flashforge's firmware and
   ours with `CONFIG_FLASHFORGE_IFS` erase the bootloader's flag page and
   reset into it), then `IFSCommand ifs.hex /dev/ttyS4`. A failure is logged
   and doesn't hold Klipper back: `S61klipper` gives Klipper the IFS as an
   MCU (`generic-flashforge-ifs.cfg`, through `ifs.cfg`'s include of
   `/run/ad5x/ifs-mcu/*.cfg`) only while it answers as Klipper; otherwise
   `ifs.py` uses Flashforge's firmware. By hand: `ad5x-mcu
   flash-ifs` (this version), `flash-ifs HEX`, or `flash-ifs stock`
   (Flashforge's `ifs.hex` back). When no bootloader answers, it keeps trying
   for 2 minutes: unplug the IFS cable and plug it back in (the bootloader
   always waits briefly after power-on).
4. When the mainboard and eboard report the wanted version,
   `/data/ad5x/klipper.enable` is created once and Klipper starts.

The flashing tools are Flashforge's own, from this printer: stock keeps them
in its control directory on the usershare partition (`/usr/prog` under
stock, never touched by the installer). `ad5x-mcu` copies them to
`/data/ad5x/vendor/mcu/` the first time; our images don't contain them.

**The way back is armed first.** Before it writes a board, `ad5x-mcu`
creates `Update` and `UpdateM` in stock's control directory: stock's own
board update (section 1). Kiln OS never runs it; stock runs it at its first
start, whenever that happens (a first start of Kiln OS that fails and
falls back to stock, or `ad5x-restore-stock`, which arms it too), and
writes Flashforge's images back. Switch the printer off and on for that,
not a reboot (the eboard must be in its bootloader). With zMod's
`klipper13` setting on, stock's update writes zMod's Klipper images instead
(section 3).

Screens while it works: "Updating the boards", "Switch off and on", "Board
update failed". `ad5x-mcu status` shows both versions; the log is
`/data/ad5x/mcu/log`. `/data/ad5x/mcu.disable` turns flashing off (the
eboard is still started). A new image with newer board firmware (a new
`FLASHED`) updates the boards the same way at its first start.

Tested on the laptop with simulated boards and stubbed flashing tools
(`tools/test_mcu.sh`), and on the developer's printer (2026-10-19): installed
as an update with both boards current (nothing flashed), `ad5x-mcu
flash-mainboard` (tools copied from usershare, stock armed, verified, about
a minute), and an eboard re-flash at power-on (IAPCommand success, started,
Klipper ready). Not yet tested on hardware: the round trip through stock
(stock writing its own images back, then a fresh install).

## 1. How stock updates each MCU

### Trigger

| Step | Where | What |
|---|---|---|
| USB update | `/usr/prog/app_startup.sh` (from `software-3.1.0/app_startup.sh`), run by `S99factory_test_shell` | Finds `/mnt/AD5X-*.tgz`, decrypts it (`mytar`), runs `flashforge_init.sh AD5X 0026`, then sleeps forever: the user power-cycles. Also runs `/mnt/flashforge_init.sh` from a stick (the hook our USB test mode uses). |
| Install | `flashforge_init.sh` `update_control` | Unpacks `control-<ver>.tar.xz` to `/usr/prog/PROGRAM/control/<ver>/` after an md5 check. **Does not run** its `run.sh` (commented out). The tar includes two empty flag files, `Update` and `UpdateM`. |
| Flash | `app_startup.sh`, every boot, **after** the USB-stick loop and **before** `firmwareExe` | Takes the highest-numbered dir in `/usr/prog/PROGRAM/control/` (`sort -Vr`). If `Update` **or** `UpdateM` exists there: `cd` into it, run `./run.sh`, then `reboot -f`. |
| Flag clear | the flash tools | `IAPCommand` deletes `$PWD/Update` after a successful eboard flash; `NationsCommand` deletes `$PWD/UpdateM` after a successful mainboard flash. A failure leaves the flag, so the next boot tries again (and reboots again). |
| OTA (cloud) | `firmwareExe` `UpdateManager::startInstallUpdatePackets` / `upgradeFirewareToPrinter` | Unpacks and renames packages, runs `run.sh` for the kernel/software/library packages only. Control packages go through the same flag-file path at next boot. |

`firmwareExe` has no MCU version check. `MainWindow::mcuVersion` / `Home::mcuVersion` just report
the name of the directory in `/usr/prog/PROGRAM/control/`, and `checkFirmwareVersion` sends the
directory versions to the cloud update check. Neither touches the MCUs. `firmwareExe` never
calls `NationsCommand` or `IAPCommand` (not in its strings).

### `control-1.1.1/run.sh` (in order)

1. `cat mcu.img > /dev/fb0` (update splash).
2. Eboard: `IAPCommand ADM_App.hex /dev/ttyS5`.
3. Mainboard: `NationsCommand -c -d --fn AD5X.bin --v -r` (port is the built-in default `/dev/ttyS2`).
4. IFS: copy `IFSCommand` and `ifs.hex` to `/usr/prog/PROGRAM/control/`, `ifsF37 /dev/ttyS4`, `IFSCommand ifs.hex /dev/ttyS4`. Runs on every `run.sh` call; no flag of its own.
5. If more than one version dir exists, delete the lowest-numbered one.

### Per board

| | Mainboard | Eboard | IFS |
|---|---|---|---|
| Port | `/dev/ttyS2` (tool default) | `/dev/ttyS5` (argument; tool default too) | `/dev/ttyS4` |
| Tool | `NationsCommand` ("Nations command line v1.0.0") | `IAPCommand` (an "stm32isp" derivative) | `ifsF37` + `IFSCommand` (same code as `IAPCommand`) |
| Target | Nations ROM ISP bootloader (system memory) | Flashforge bootloader in flash 0x08000000–0x0800FFFF | IFS bootloader below 0x08010000 |
| Entry | SoC sysfs GPIO **50** = 1 (BOOT0), GPIO **49** pulsed 0 for 200 ms then 1 (NRST), 200 ms settle. Repeated before every connect attempt | None: the bootloader runs after every reset and waits; the tool must catch it before anyone sends `A` | `ifsF37` sends `F37\r\n` at 115200; the IFS app erases the bootloader's flag page (0x0800D000) and resets (AIRCR); the bootloader then waits. It also waits briefly after every power-on (`docs/ifs-protocol.md`) |
| Link | 8N1. Tries 9600, 19200, 38400, 115200 (twice each; the help text claims a 115200 default, the code starts at 9600) | 115200 **8E1** | 115200 8E1 |
| Protocol | Nations ISP: command bytes with `cr1/cr2` status replies (0xA0 ok, 0xB0 fail); reads BOOT version and UCID; erases by file size from 0x08000000; writes the raw `.bin` at 0x08000000 (hard-coded, `--a` not used by `-d`); `--v` CRC-verifies; `-r` sends the ISP system-reset command. BOOT0 goes low as soon as the connection is up, so the reset starts the app | Sync: send `C` (0x43); 0x06 = start, 0x07 = "Update :HD" (tool exits 0 **without flashing**, flag kept; meaning unknown). Frames of 1030 bytes: 0x01, frame number (u8), length (u16), 1024 data bytes (0xFF padded), CRC-16/XMODEM (poly 0x1021, init 0) over the data. 0x06 per frame; anything else → resend, **no retry limit**. End: 0x04, expect 0x06 | Same as eboard |
| Addresses | From the tool (0x08000000) | **Not sent.** The tool cuts the hex into 1 KB blocks from its first address and sends them in order; the bootloader decides where they go. Make the hex without gaps (`tools/build_mcu.sh` writes it from `klipper.bin`): how a gap is handled is unknown | Same |
| File | Raw binary (`AD5X.bin`) | Intel hex (`ADM_App.hex`); start-address record unused by the tool | Intel hex (`ifs.hex`) |
| Side effects | `rm -f $PWD/UpdateM` on success | `touch /root/N32` (nothing in `firmwareExe` reads it), `rm $PWD/Update` on success | None |

GPIO numbers are sysfs numbers on the Ingenic SoC; with 32 pins per port, 49 = **PB17** (NRST) and
50 = **PB18** (BOOT0). That mapping is an inference; confirm on the board. `IAPCommand` and
`IFSCommand` also contain `stm32Reboot` (GPIO 34 = PB02 pulse) and `stm32UpdateFLag` (GPIO 35 = PB03),
but nothing calls them. The eboard has no reset or BOOT0 line from the SoC, as far as the tools show.

`cmd_gpio` in stock scripts: `PC15` set to output 0 at the start of `app_startup.sh`, `PC11`
toggled once a second by `sys_start.sh` (heartbeat), `PB07` for Wi-Fi power (`app_startup.sh`,
`firmwareExe` `restartWifiDevice`). None of them drives an MCU.

### Eboard start at every boot

`firmwareExe` `main()` calls `bootSerialMainEboardMcu` before building the UI: `/dev/ttyS5` at
115200, up to 20 reads of 0.1 s looking for `Ready`, then up to 20 × `A` until 0x06. If it heard
**nothing**, it logs `bootserial error` and shows a **modal dialog** that blocks start-up until
dismissed. If it heard anything, it sends `A` and carries on, even without an ACK.
`bootSerialMainMcu` (the same on `/dev/ttyS2`, sending `A\r\n`) exists but nothing calls it.
`/usr/prog/klipper/checkEboard` is a standalone copy of the eboard routine; `firmwareExe` doesn't
call it; its caller (probably zMod) is unconfirmed. `firmwareExe` starts stock Klipper itself (`/usr/prog/klipper/start.sh &`).

### IFS update from the UI

`MachineInfo::doUpdateIfs`, reached only from `on_btnIfs_clicked` (Machine Info screen, when not
printing): sends `F37`, closes the port, runs
`/usr/prog/PROGRAM/control/IFSCommand /usr/prog/PROGRAM/control/ifs.hex /dev/ttyS4`, then asks `F19`
for the version. Never automatic.

## 2. Bootloaders and offsets

| | Survives an app flash | Recover a bad app over serial | App start | Our mainline config | Stock image |
|---|---|---|---|---|---|
| Mainboard | ROM ISP is mask ROM; can't be erased. Lost only through option bytes (read/write protection), which we never touch | Yes: `NationsCommand` with BOOT0/NRST, whatever is in flash | 0x08000000 | `CONFIG_STM32_FLASH_START_0000`, `FLASH_APPLICATION_ADDRESS=0x8000000` ✔ | `AD5X.bin`, SP 0x20020000, reset 0x08006DDD |
| Eboard | Yes, if the bootloader writes only from 0x08010000 (it picks the address; the tool sends none). Not proven: we have no dump of it | Yes: power-cycle, don't send `A`, run `IAPCommand` | 0x08010000 | `CONFIG_STM32_FLASH_START_10000`, `FLASH_APPLICATION_ADDRESS=0x8010000` ✔ | `ADM_App.hex` 0x08010000–0x08018CAC, reset 0x08016A7D |
| IFS | So far: written stock → Klipper → stock → Klipper (2026-10-25), the bootloader intact | Yes: power-cycle the IFS while `IFSCommand` retries, whatever is in flash | 0x08010000 | `CONFIG_STM32_FLASH_START_10000`, `CONFIG_FLASHFORGE_IFS` (stack within 32 KiB: the stock SP is 0x20007498, and a build with 0x20020000 most likely never started) ✔ | `ifs.hex` 0x08010000–0x0801A0D0 |

Images checked on the laptop: `firmware/builds/v0.13.0-800-g9cb99754c/mainboard.bin` has its vector
table at 0x08000000 (SP 0x20010000, reset 0x08006CE1). `eboard.hex` covers 0x08010000–0x0801A298
**without gaps**, so `IAPCommand`'s sequential 1 KB blocks land where they are linked. Stock
`ADM_App.hex` has one 8-byte gap inside its first block, which is harmless. Its start record is
the reset handler, as in stock.

The mainboard has no bootloader, so `NationsCommand` (and so the SoC GPIOs) is the only serial
way in. Mainline's bigger image (41.4 KB vs 37.5 KB) is fine: erase-by-file-size covers it, and
the tail left past stock's size when going back is never executed.

## 3. Community projects

All of them flash in-system with Flashforge's own tools. None ships its own flasher.

**zMod (ghzserg, AD5M and AD5X; installed on our printer).** This is the most important one for us.
- `UPDATE_MCU [FORCE=…]` switches the boards between stock firmware and zMod's
  "Klipper 13" MCU images. For the AD5X the images are
  [ghzserg/zmod_klipper `mcu/ad5x/{Mainboard.bin,Eboard.hex}`](https://github.com/ghzserg/zmod_klipper/tree/main/mcu/ad5x),
  same offsets as ours (0x08000000 / 0x08010000, SP 0x20020000). The wiki warns that the only way
  back is the factory image ([wiki: System#update_mcu](https://wiki.zmod.link/System/#update_mcu)).
- It uses **stock's flag mechanism**: [`z_ad5x/.shell/zmcu.sh`](https://github.com/ghzserg/z_ad5x/blob/main/.shell/zmcu.sh)
  touches `Update` and `UpdateM` in the newest control dir, sets `klipper13` and powers off.
- At boot [`app_startup_mcu.sh`](https://github.com/ghzserg/z_ad5x/blob/main/.shell/app_startup_mcu.sh)
  sees a flag. With `klipper13=1` it **bind-mounts its own [`update_mcu.sh`](https://github.com/ghzserg/z_ad5x/blob/main/.shell/update_mcu.sh)
  over the stock `run.sh`** (`NationsCommand -c -d --fn Mainboard.bin --v -r`,
  `IAPCommand Eboard.hex /dev/ttyS5`, IFS lines commented out), runs it and `reboot -f`s. Without
  `klipper13`, the stock `run.sh` flashes the stock images.
- [`prepare.sh`](https://github.com/ghzserg/z_ad5x/blob/main/.shell/prepare.sh) exits zMod while any `Update` flag exists.
- [`klipper13.sh`](https://github.com/ghzserg/z_ad5x/blob/main/.shell/klipper13.sh) resets the mainboard with `NationsCommand -r` before starting Klipper 13.
- `FIX_UPDATE_MCU` ([source](https://github.com/ghzserg/zmod/blob/main/Native_firmware/fix_update_mcu/flashforge_init.sh))
  deletes stray `Update` files to break the reflash loop described in section 5.
- Restoring stock: a ghzserg/FF "Factory" tgz ([releases "R"](https://github.com/ghzserg/FF/releases/tag/R),
  every AD5X version 1.0.2–3.1.0; [FAQ "MCU Protocol error"](https://wiki.zmod.link/FAQ/),
  [Native_FW](https://wiki.zmod.link/Native_FW/)).
- The only AD5X SWD recipe found is for the **IFS** board: SWCK/SWIO/3.3V/GND pads, J-Link,
  target "Nations N32G455RE" ([wiki AD5X §11](https://wiki.zmod.link/AD5X/)).
- This is prior art for running newer Klipper on AD5X MCUs (credited to @darksimpson).

**xblax/flashforge_ad5m_klipper_mod (AD5M only).**
- [`mcu_update.sh`](https://github.com/xblax/flashforge_ad5m_klipper_mod/blob/master/build_overlays/common/usr/libexec/mcu_update.sh)
  runs the stock tools from the stock rootfs through stock's `ld-linux`:
  - mainboard: `NationsCommand -c -d --pn /dev/ttyS5 --fn …`
  - eboard: `Request Serial Bootloader` at 230400, then `IAPCommand … /dev/ttyS1`
- It refuses to run while Klipper runs. It tracks the flashed version in
  `printer_data/database/.klipper_mcu_version` and re-flashes at boot on mismatch (`S54mcu_update`).
- It restores stock (`update_stock`, from the images on the printer) on dual-boot-to-stock and
  uninstall. One user cured "MCU Protocol error" by forcing that path
  ([#352](https://github.com/xblax/flashforge_ad5m_klipper_mod/issues/352)).
- `S55mcu_boot` boots the eboard and resets the mainboard (`NationsCommand -c --pn … -r`) at
  every boot.
- AD5M `NationsCommand` uses sysfs GPIO 205 (reset) and 206 (BOOT0): the same scheme as our 49/50.
- No AD5X port is planned ([#296](https://github.com/xblax/flashforge_ad5m_klipper_mod/issues/296)).
- Its Klipper fork carries the eboard bypass and bootloader-request patches (`c349aad8`, `245ec843`).

**DrA1ex/ff5m (AD5M).** It doesn't flash MCUs; it only boots the eboard
([`boot_mcu`](https://github.com/DrA1ex/ff5m/blob/main/.bin/src/boot_mcu/main.cpp)). Recovery
goes through its uninstall image, then the Factory image, then SoC UART/FEL
([RECOVERY.md](https://github.com/DrA1ex/ff5m/blob/main/docs/RECOVERY.md)).

**Others.**
- Mainline N32G45x support: [`23e82d37f`](https://github.com/Klipper3d/klipper/commit/23e82d37f14b79a164234361a01b893443b5a34d)
  (2023). The 2026 fixes by Lev Voronov, tested on an AD5M toolhead: 144 MHz
  ([PR #7347](https://github.com/Klipper3d/klipper/pull/7347)) and ADC
  ([PR #7362](https://github.com/Klipper3d/klipper/pull/7362)). Upstream has no Nations ISP tool
  and no Flashforge eboard bypass.
- The [loss-and-quick/katapult `n32g45x`](https://github.com/loss-and-quick/katapult/tree/n32g45x)
  branch adds the N32 flash driver (2 KiB pages). Not needed while the stock bootloaders stay.
- An AD5M mainboard N32 was killed by overvoltage on its SWD pins and replaced with an
  STM32F103RET6 ([xblax #372](https://github.com/xblax/flashforge_ad5m_klipper_mod/issues/372)).
  Others bricked N32s while J-Link flashing
  ([g992 #8](https://github.com/g992/flashforge-ad5m-5mpro-research/issues/8),
  [Discourse 13893](https://klipper.discourse.group/t/nations-mcu-support-flashing/13893)).
  SWD is the risky path, not serial.
- No public pad map for the AD5X mainboard or eboard SWD.

## 4. Getting back to stock

Stock images: `firmware/stock-3.1.0/unpacked/control-1.1.1/{AD5X.bin,ADM_App.hex}` (md5 in that
dir's `md5sum.list`: `522b4641…` / `e8c74…`). On the printer they should also be in
`/usr/prog/PROGRAM/control/<ver>/`; check that the md5s match before relying on them.

**A. Flashforge's own path (preferred).** From the stock system over SSH:

1. Check `/usr/prog/PROGRAM/control/` has exactly one version dir with the stock files and run.sh,
   md5s matching.
2. `touch Update UpdateM` in that dir. Remove any USB stick (our stick's `flashforge_init.sh`
   runs first and never returns, so the flags would never be processed).
3. **Power-cycle** (switch off, not `reboot`): the eboard must be fresh in its bootloader.
4. `app_startup.sh` runs `run.sh`: eboard, mainboard, then IFS (re-flashed with the same stock
   image), deletes the flags, `reboot -f`.
5. Expect the update splash (`mcu.img`), then a normal stock start.

If a flag stays (the tool couldn't connect), every boot runs `run.sh` and reboots again.
Power-cycling usually fixes it; if not, remove the flags over SSH (dropbear starts before
`app_startup.sh`).

**B. Stock tools by hand** (AD5M mod `update_stock` pattern). Stop `firmwareExe` and stock
Klipper first, since they hold the ports. Mainboard: `NationsCommand -c -d --pn /dev/ttyS2 --fn AD5X.bin --v -r`.
Eboard: get it into its bootloader (power-cycle so nobody sends `A`, or the Klipper `reset`
command on mainline, below), then `IAPCommand ADM_App.hex /dev/ttyS5`. Run from a directory
without flag files.

**C. Full stock update**: `AD5X-3.1.0-…tgz` on a FAT stick re-installs everything, including the
control flags. Remove the stick after the update finishes, or it installs again. It may undo
zMod (open question).

**Worst case: SWD.** Needed only if the eboard bootloader is damaged, the chip's option bytes get
set, or the BOOT0/NRST lines don't work. N32G455 SWD is on PA13 (SWDIO) / PA14 (SWCLK), as on the
STM32F103. Pads or headers on the AD5X mainboard and eboard: not known (section 3). Before
anything risky, a full SWD dump of the eboard (bootloader included) would be the real backup. No
serial tool can read flash back (`NationsCommand` has no read, `IAPCommand` writes only).

## 5. Stock against mainline MCUs

What stock does at boot (no USB stick) after the boards run mainline:

1. `app_startup.sh`: no `Update`/`UpdateM` flag → **no re-flash**. Stock never compares MCU
   firmware versions. A flag left behind by an interrupted stock update would re-flash stock
   (that is restore path A, not a risk).
2. `firmwareExe` `main()`: eboard handshake. The Flashforge bootloader is untouched, so it prints
   `Ready`, gets `A` and starts mainline Klipper. Same as stock.
3. `firmwareExe` starts stock Klipper (v0.12-era host). Its data dictionary doesn't match
   mainline's, so klippy stops with an MCU protocol/version error. No motion, no heaters: mainline
   firmware keeps every pin off until configured, and `!PB9` holds the bed heater off.
4. The UI shows a Klipper error. `firmwareExe` may send `FIRMWARE_RESTART`
   (`gcode/firmware_restart` is in its strings). On mainline that resets the eboard into its
   bootloader. Harmless, but the eboard then waits until the next power-cycle.
5. Nothing in this path writes to the MCUs. IFS update is manual only. zMod adds a re-flash path,
   but only through the same flag files (section 3).
6. SSH (dropbear, zMod) still works, so restore path A or B can be run from there.

Risks:

- **Warm reboot.** The SoC can reboot without the MCUs resetting. The eboard then keeps running
  its app and is silent at 115200, so stock's handshake hears nothing and shows the modal
  `bootserial` dialog. A flag-file re-flash fails (`IAPCommand` can't connect) and reboots again.
  Always power-cycle around flashing.
- **Interrupted eboard flash.** `IAPCommand` retries a frame forever. If killed mid-transfer the
  app area is partial, but the bootloader is still there: power-cycle and flash again.
- **Interrupted mainboard flash**: ROM ISP is always there; run `NationsCommand` again.
- `IAPCommand` exit 0 with "Update :HD" means nothing was written. Check the output, not just
  the exit code.
- Running a stock tool from inside `/usr/prog/PROGRAM/control/<ver>/` deletes that dir's flag.
- **zMod.** With zMod's `klipper13` setting on, restore path A (flags) flashes **zMod's Klipper 13
  images**, not stock: its `app_startup_mcu.sh` mounts its own script over `run.sh`. Check and clear
  that setting before relying on path A. zMod's `UPDATE_MCU` would also overwrite our images:
  don't run it while the boards carry mainline.

## Mainline gaps (fix before relying on it)

Both fixed in our build: `tools/build_mcu.sh` applies `klipper/mcu-patches/` (the two xblax
commits, unchanged, GPLv3) on top of mainline `9cb99754c`, giving `v0.13.0-802-gf5d198392`
(reproducible: fixed commit dates). They only change builds for an N32G455 with the app at
0x10000, i.e. the eboard; the mainboard image is the same code. Checked in the eboard image:
the reset path writes 0x1234 to the backup registers (`movw r1, #0x1234`, BKP base
0x40006C00 referenced); the unpatched image has neither.

- **Eboard restart.** Flashforge's bootloader skips its wait after a reset when backup register
  BKP_DR1 holds 0x1234. xblax/klipper `c349aad8` writes this in the `reset` command for
  `MACH_N32G455 && FLASH_START_10000`, and stock images reference the PWR/BKP registers too.
  Mainline doesn't, so `FIRMWARE_RESTART` (our `restart_method: command`) leaves the eboard in its
  bootloader and klippy can't reconnect. Fix: carry that patch, or re-run `boot_eboard` after a
  firmware restart.
- **Bootloader request.** Mainline's `Request Serial Bootloader` only resets when the bootloader
  carries Katapult's signature. Flashforge's doesn't, so the AD5M mod's reflash trick does nothing
  on plain mainline. xblax `245ec843` makes it a plain reset. Without it: power-cycle, or the
  `reset` command (a plain reset on mainline, which leaves the eboard waiting in its bootloader).
- Mainline `mainboard.bin` has no bootloader-request code at all (no bootloader); not needed,
  since ISP uses GPIOs.

## Proposed procedure

**Phase 0: laptop only, no printer**

1. Re-check images: `SHA256SUMS` in `firmware/builds/v0.13.0-800-g9cb99754c/`; mainboard vector
   table at 0x08000000, eboard hex 0x08010000 without gaps (done, section 2).
2. Dry-run `IAPCommand` under `tools/qemu_stock.sh` against a pty with a simulated eboard
   bootloader: `C` → 0x06, check each frame's CRC and ACK it, ACK EOT. **Done 2026-10-15** with a
   scratch simulator:
   - mainline `eboard.hex`: 41 frames, CRCs good, image rebuilt from the frames (frame length field
     u16 little-endian) is byte-identical to the hex's 0x08010000–0x0801A298;
   - stock `ADM_App.hex`: 36 frames, also identical.

   The tool printed "STM32Write: success." and tried `rm $PWD/Update`. Worth adding the simulator
   to `tools/` as a regression test.
3. Dry-run `NationsCommand -?` and a connect attempt under qemu (sysfs GPIO is absent there; just
   confirm the arguments and port handling).
4. Decide on the eboard restart fix (patch or host hook) and rebuild if patched.

**Phase 1: printer, read-only (allowed now)**

5. `ls -la /usr/prog/PROGRAM/control/*/` and `md5sum` → stock files present, no flags left.
6. `ls /sys/class/gpio` exists (do **not** export anything).
7. Note which zMod scripts touch `/dev/ttyS2`/`ttyS5` or run `checkEboard`, and zMod's `klipper13`
   setting (section 3).
8. Photograph the boards: N32 markings and any SWD pads (needs the case open, the user's call).

**Phase 2: printer, writes (ask first)**

9. Connectivity test without writing: stop stock Klipper/`firmwareExe`, then
   `NationsCommand -c --pn /dev/ttyS2 -r`. This prints BOOT version and UCID and resets the
   mainboard. If that fails, stop.
10. Mainboard: `NationsCommand -c -d --pn /dev/ttyS2 --fn mainboard.bin --v -r`; needs "verify OK"
    and exit 0.
11. Eboard: power-cycle with the stock app blocked from sending `A` (e.g. from a USB-stick hook,
    which runs before `firmwareExe`), `IAPCommand eboard.hex /dev/ttyS5` from a dir without flag
    files; needs the frame count, "STM32Write: success." and no "HD".
12. Boot the USB test system; check klippy connects to both MCUs and `FIRMWARE_RESTART` behaves.
13. Unplug the stick, power-cycle, and confirm stock behaves as section 5 predicts (Klipper error, no
    re-flash). Then restore with path A and confirm stock prints again: the round trip
    is the real test of the way back.

Flash one board at a time, mainboard first: its ROM ISP is the safest way back, and the tool
verifies its writes.

## Open questions (need the printer)

1. Which dir(s) are in `/usr/prog/PROGRAM/control/` and do their images match 1.1.1?
2. GPIO 49/50 are really the N32's NRST/BOOT0 (PB17/PB18)? Is sysfs GPIO usable alongside zMod?
3. Does the eboard bootloader wait forever for `A`, or time out and start the app?
4. What does the eboard bootloader do on `C` → 0x07 ("HD")?
5. Does the eboard bootloader ever write below 0x08010000, or check the app before jumping?
6. Do the MCUs reset when the SoC reboots (`reboot -f`), or only on power-cycle?
7. Is BKP_DR1 = 0x1234 really the bypass on the AD5X bootloader (from the AD5M; not checked on this board)?
8. SWD pads on the AD5X mainboard and eboard; option bytes (RDP) state.
9. zMod's `klipper13` setting on this printer, and whether a stock USB update removes zMod.
10. Whether the printer's control dir is 1.1.1 (the version zMod's Klipper 13 images were made for is
    not documented).

## Checked on the user's unit (2026-10-15, USB test mode)

- **Mainboard ROM bootloader reachable** (step 9): `NationsCommand -c --pn /dev/ttyS2 -r`
  (no `-d`: nothing erased or written) connected at 9600, read `BOOT Command Version V:22`,
  `SubVersion V24` and the chip's UCID/UID, reset the chip, exit 0. Klipper `identify`
  afterwards: the stock app (`?-20241125_172251-ubuntu`) was running again. So the SoC's
  BOOT0/reset lines work as the tool expects.
- **Eboard handshake**: `boot_eboard` got `Ready.`, sent `A`, got 0x06; the stock app then
  answered Klipper `identify` at 230400 (`?-20241122_134741-ubuntu`, stm32f103xe profile,
  144 MHz, serial PA10/PA9): same clock, baud and pins as our build.
- zMod `klipper13 = 0`; no `Update`/`UpdateM` flag in `/usr/prog/PROGRAM/control/`; every file in
  `control/1.1.1/` matches the 3.1.0 update byte for byte (restore images on the laptop are what
  is installed). `mcu.img` is only the "updating" splash screen `run.sh` shows.

## Flash log

| Date | Board | Image | Result |
|---|---|---|---|
| 2026-10-16 | Mainboard (motion MCU) | `v0.13.0-802-gf5d198392` `mainboard.bin` (sha256 `83449c04…`) | `NationsCommand -c -d --pn /dev/ttyS2 --fn /tmp/mainboard.bin --v -r` from USB test mode: BOOT V22/V24, erase, download, "Chip verification succeeded", exit 0. `identify` afterwards: `v0.13.0-802-gf5d198392`, 144 MHz, 230400. Stock on this board now fails to connect until restored (`AD5X.bin` with the same tool, or the `UpdateM` flag + power-cycle). |
| 2026-10-16 | Eboard (toolhead) | `v0.13.0-802-gf5d198392` `eboard.hex` | `IAPCommand /tmp/eboard.hex /dev/ttyS5` after `Ready.`: 41 frames acked, "STM32Write: success", exit 0. `boot_eboard` got `Ready.`/`A`/0x06, but the board stayed in its bootloader: Klipper `identify` got no answer at 230400; raw bytes at 115200 were answered with 0x06 (bootloader ACKs). Cause (most likely): mainline gives N32G45x 64 KiB RAM, so the image's initial stack pointer is 0x20010000; stock (both boards) and xblax use 0x20020000, and the bootloader appears to check it before jumping. Fixed by `klipper/mcu-patches/0003` (128 KiB for N32G455): `v0.13.0-803-g4cd711119`. Board is recoverable in this state (bootloader intact). |
| 2026-10-16 | Eboard (toolhead) | `v0.13.0-803-g4cd711119` `eboard.hex` (sha256 `4873e51b…`) | After a power-cycle (`Ready.`): `IAPCommand`, 41 frames, success, exit 0; `boot_eboard` then Klipper `identify`: `v0.13.0-803-g4cd711119`, 144 MHz, 230400. **Runs.** Confirms the stack-pointer cause. |
| 2026-10-16 | Mainboard (motion MCU) | `v0.13.0-803-g4cd711119` `mainboard.bin` (sha256 `ba8c1355…`) | Same `NationsCommand` line; `identify` afterwards: `v0.13.0-803-g4cd711119`. Both boards on the same build. |
| 2026-10-19 | Both, full round trip | Kiln OS v0.0.3 | `ad5x-restore-stock` + power-cycle: stock flashed `AD5X.bin`/`ADM_App.hex` itself (flags consumed), stock Klipper ready on `?-20241125`/`?-20241122`. SSH install of the v0.0.3 install zip; first start (warm) flashed the mainboard and asked for a power-cycle. Power cut seconds after that screen came back in the **recovery OS**: start-up hadn't reached `S99ad5x-booted`, so the try-once flag still pointed at slot A (fixed: ad5x-mcu marks the start complete before that screen). From recovery, `ad5x-boot-main`: eboard flashed at start, Klipper ready on `v0.13.0-803-g4cd711119`. Repeated as a cold power-on with the eboard record removed: flashed, start-up complete. |

## Nozzle heater under mainline

**Symptom (2026-10-16, both boards on `v0.13.0-803-g4cd711119`):** extruder heater commanded at
100 % for 35 s, thermistor stayed at 24.8 °C, no heat. Part fan (`eboard:PB5`) and bed heater
(mainboard `PB9`) work.

**Diagnosis: the eboard has a separate heater-enable output, `eboard:PB7`, which must be driven
high.** `heater_pin: eboard:PA8` only switches the PWM side; with PB7 low the hotend gets no power.
Our config never sets PB7, and mainline firmware leaves every unconfigured pin off.

Evidence:

- zMod's Klipper 13 mode (mainline-based, which AD5X users print with) adds this block in its
  klipper13 base config (`github.com/ghzserg/z_ad5x`, commit `04902daf`,
  `translate/en/base_klipper13.cfg` lines 3-6, the same in every language):
  ```
  [output_pin _extruder_heater]
  pin:        eboard: PB7
  value:      1
  shutdown_value: 0
  ```
- xblax's AD5M Klipper mod (mainline on the same N32G455 eboard, same `heater_pin: eboard:PA8`)
  has the same block as `[output_pin extruder_heater]` plus `EXTRUDER_ON`/`EXTRUDER_OFF` macros
  (`github.com/xblax/flashforge_ad5m_klipper_mod`, `printer_configs/printer.base.cfg` lines 74-85).
- The firmware isn't the problem: zMod's prebuilt AD5X eboard image
  (`github.com/ghzserg/zmod_klipper`, `mcu/ad5x/Eboard.hex`, `v0.13.0-761-g3487ad41`, stm32f103xe
  profile, 144 MHz, app at 0x08010000) has no `INITIAL_PINS` and the same command set as ours, so
  zMod enables the heater from the config. xblax's `ffad5m/eboard` Kconfig matches ours too
  (`CONFIG_INITIAL_PINS=""`).
- Stock `printer.base.cfg` has no PB7 line on the eboard (line 92 `#pin:PB7` is a commented-out
  chamber fan on the *mainboard*). Stock's Flashforge firmware must drive eboard PB7 itself. We
  inferred this and did not check it in the disassembly; the zMod and xblax configs settle the fix.

**Fix:** add this to `klipper/ad5x.cfg`, next to `[extruder]`. It is the zMod block, and the
leading underscore hides the pin from the UIs:

```
# Eboard hotend power enable (zMod klipper13 / xblax AD5M mod). PA8 is only the
# PWM side; with PB7 low the heater gets no power. shutdown_value 0 cuts it on any
# Klipper shutdown, a second hardware cutoff besides PA8.
[output_pin _extruder_heater]
pin: eboard:PB7
value: 1
shutdown_value: 0
```

This is a config change, not a firmware change. It is not a deviation from stock behaviour:
stock firmware enables the same output itself. Log it in `docs/deviations-from-stock.md` as
"heater enable moved from firmware to config".

**10-second test** (after `FIRMWARE_RESTART` with the block added, nozzle cold):

```
SET_PIN PIN=_extruder_heater VALUE=1
SET_HEATER_TEMPERATURE HEATER=extruder TARGET=80
G4 P10000
M105
SET_HEATER_TEMPERATURE HEATER=extruder TARGET=0
```

Pass: `M105` shows the extruder several °C above ambient after 10 s. A 60 W cartridge at full
power rises about 2-5 °C/s, so expect roughly 40-60 °C. Without PB7 it stays at ambient, as on
2026-10-16. If it still doesn't heat with PB7 high, check that `[output_pin _extruder_heater]` shows
`value: 1` in the status, then look at the eboard's fuse or the heater connector.
