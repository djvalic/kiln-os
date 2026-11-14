# Serial console

The mainboard has a 4-pin header labelled **DEBUG**: `3.3V`, `TX`, `RX`,
`GND`. It carries the SoC's UART0 (`ttyS0`, the kernel console) and gives a
root shell that works without any network, for example when Wi-Fi is down.

## Wiring

- **3.3 V logic.** A USB-to-serial adapter must be a 3.3 V one (or set to
  3.3 V). A 5 V adapter can damage the SoC.
- Cross TX and RX: header `TX` to the adapter's `RX`, header `RX` to the
  adapter's `TX`, `GND` to `GND`.
- Leave the header's `3.3V` pin unconnected when the adapter is powered
  from USB. Use it only to power a bridge that has no other supply (below).
- 115200 baud, 8N1, no flow control.

## What you see

Output comes from Kiln's own 6.6 kernel and the main OS's start-up
scripts, ending at the `ad5x login:` prompt. Log in as `root` with the
same password as for SSH.

Everything before our kernel is switched by one strap, GPIO 70 (PC6):

- The boot loader (SPL) sets the header's pins (PE9-PE12) to UART0 at
  115200, then reads PC6 with its internal pull-up off. Low means no
  output at all.
- The stock 5.10 kernel follows the same strap: with PC6 high its whole
  log comes out on the header, from `console=ttyS0,115200n8` to
  `Run /linuxrc as init process`; with PC6 low, nothing. With PC6 low it
  sets UART0 to PE11/PE12 and leaves the header's PE9/PE10 as GPIO (port
  E registers at 0x13605000, read 2026-11-14).

Production boards hold PC6 low on purpose (below). As shipped, these are
silent on the header. Nothing appeared at 115200, 57600, 9600 or 3000000
baud across a boot into the recovery OS and back (2026-11-14), while our
kernel's output came through each time, as garbage at the other rates.
3000000 baud would turn a sender at any slower rate into bytes, so the
line really is idle:

- the boot loader;
- the first seconds of every start, before `S00ad5x-kernel` starts our
  kernel;
- the **recovery OS**, which runs the stock kernel
  ([recovery-os.md](recovery-os.md));
- a main OS that fell back to the stock kernel after our kernel failed to
  start.

So, as shipped, the header rescues a main OS that boots but can't be
reached, such as a Wi-Fi that doesn't come up. With PC6 held high, it
shows every start from the boot loader on, the recovery OS included.

## Turning the rest on: PC6

The SPL is the small first-stage boot loader. The boot ROM loads it from
the eMMC (offset 0x4400); it sets up the clocks, the RAM and the eMMC,
reads the boot flag and loads the kernel from slot A or B. Flashforge's
SPL loads the kernel itself, so U-Boot proper, with its prompt and its
"Hit any key to stop autoboot", never runs ([boot-slots.md](boot-slots.md)).
The SPL reads no input (its serial input routine is never called), so its
console gives a log but no way to stop the boot.

On `FFP0302_Main_Board_V3.0.1 2025-5-16`, PC6 is the middle of a divider
(traced by alexshev86 on a board with the SoC removed, #66; measured in circuit, so
approximate; other board revisions may differ):

- **R233**, about 3.8 kΩ (3.9 kΩ?), to +3.3 V;
- **R232**, about 0.9 kΩ (910 Ω?), to GND.

That holds PC6 at about 0.63 V, a low, through about 730 Ω. From Linux it
reads 0 with the internal pull-up on or off.

**PC6 is in the 1.8 V bank.** Hold it at **1.8 V** at power-on, never at
3.3 V (above the bank's supply). The divider's source impedance is low,
so use a firm source: holding PC6 at 1.8 V turned the console on in a
test (2026-11-14). With it, the header shows:

```
serila pio:val high
ERROR EPC dceeb9ff
...
DDR: W634GU6QG-11 type is : DDR3
run start1 firmware finished, return to bootrom!
[    0.000000] Linux version 5.10.186+ ...
```

`serila pio:val high` (sic) is the SPL reading the strap. `run start1
firmware finished, return to bootrom!` is one of the SPL's own messages,
its normal last line before the kernel. It is not a failure: the stock
kernel starts right after, then our kernel through chainload (whose log
is short: chainload passes `loglevel=5`), then the main OS to the
`ad5x login:` prompt.

## A wireless cable: XIAO ESP32-C6

A Seeed Studio XIAO ESP32-C6 running a UART bridge firmware works as a
wireless serial cable. It stays in the printer and is reached over Wi-Fi.

| Header | XIAO ESP32-C6 |
|---|---|
| `3.3V` | `3V3` |
| `GND` | `GND` |
| `TX` | `D7` (RX, GPIO17) |
| `RX` | `D6` (TX, GPIO16) |

The header's 3.3 V supply is enough to run the ESP32-C6, Wi-Fi included,
so it needs no USB cable.

### The 3.3 V supply when the printer restarts

- **Reboot** (`reboot`, an update, `ad5x-boot-recovery`,
  `ad5x-boot-main`): the 3.3 V supply stays on. The ESP32 keeps running and
  stays on Wi-Fi, so a connected session sees the shutdown and the next
  start, without a break. Seen 2026-11-14: the bridge's uptime carried on
  through two reboots in a row.
- **Power off and on** (the printer's switch, a smart plug): the 3.3 V supply
  goes away, and the ESP32 starts again with the printer. Any open session
  is closed. The bridge has to start and join Wi-Fi again before you can
  reconnect, so the first part of the output is lost. To capture a start
  after a power cut, wait for the bridge, connect, then reboot the printer
  from the console: the reboot keeps the supply, and so the capture.
- While the printer is switched off, the bridge is off too.

## Capturing a start to a file

With the bridge reached over SSH (adjust for yours):

```sh
sleep 3600 | ssh -tt admin@<bridge> >> ad5x-serial.log
```

The `sleep` keeps the session open (without stdin it closes at once).
Then reboot the printer, for example `ssh root@<printer> reboot`.
