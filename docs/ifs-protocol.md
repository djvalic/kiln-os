# IFS protocol (stock IFS firmware 3.0.7)

Source: IFS controller firmware `ifs.hex` from stock update 3.1.0 (IFS firmware reports version 3.0.7).
Method: static analysis of the IFS firmware, then use. Kiln OS's `klipper/extras/ifs.py` drives the stock IFS firmware with part of this protocol on every printer; those parts are marked **used by Kiln OS** below. Everything not marked that way comes from the firmware alone and is **unconfirmed**: it has not been seen on the wire.

Clean-room note: this file describes behavior only. Decompiled output stays in scratch and never enters the repo.

## Transport

- Host side (used by Kiln OS): `/dev/ttyS4` on the printer, **RS-485 half-duplex**. The host drives the transceiver's driver enable on PC3 while it sends (`kernel-ingenic66/ad5x.dts`, `patches/0002-*`); without it the IFS gets nothing and does not answer.
- **115200 baud, 8N1, no flow control** (used by Kiln OS). On the IFS MCU this is USART1 (TX PA9, RX PA10), from the `USART_Init` call (BaudRate 0x1C200, word length/stop/parity 0, mode TX|RX). PA11 is driven high at the same time, probably the IFS side's RS-485 driver enable (unconfirmed).
- Receive uses DMA plus the idle-line interrupt into a 200-byte buffer, so **a command is one burst of bytes followed by a pause**. The firmware needs no line terminator; Kiln OS sends `\r\n` after each command.
- The other two USARTs run at **9600** (USART2 and the port at 0x40015400). They are almost certainly the single-wire UARTs to the two TMC drivers, not the host link (unconfirmed).
- ASCII, G-code style. The controller scans the received line for `F`, parses the integer after it as the command number, then looks for single-letter parameters (`C`, `L`, `S`, `T`, `I`, `D`), each followed by a number.
- Every reply starts with `F<n> ok` (used by Kiln OS). In practice a reply has no line ending at its end (F21 has `\r\n` only between its lines), so `ifs.py` takes a reply as complete when the line goes quiet. Unknown or unimplemented command numbers get **no reply** (from the firmware; unconfirmed).

## Controller state

A single state byte drives the motion state machine (`FFS_state` in the
F13 reply). Values seen so far; the meanings are inferred from the firmware
unless marked otherwise:

| Value | Meaning |
|---|---|
| 1 | Set by F18 and F24 (a channel was selected / switch requested) |
| 5 | Ready / idle. F10, F11 and F39 refuse unless the state is 5. Used by Kiln OS (`STATE_READY`); that every move ends back in 5 is not confirmed |
| 10 + 11·(ch−1) | Feeding channel `ch` (10, 21, 32, 43) — F10 |
| 12 + 11·(ch−1) | Releasing channel `ch` (12, 23, 34, 45) — F39 |
| 14 + 11·(ch−1) | Retracting / exiting channel `ch` (14, 25, 36, 47) — F11 |
| 0x7e | Homing; stuck here means the IFS can't home (stock error E0114). Used by Kiln OS |
| 0x7f | A move faulted (stall); F15 clears it. Used by Kiln OS |
| 0x80 | Set by F30 |

`ifs.py` also names 3, 7, 11 and 15 (polling, clamped, loading,
unloading), values another IFS module saw on the wire; they are not in this
analysis.

## Commands

Channels are 1–4. **Used by Kiln OS** with the stock firmware: F10, F11,
F13, F15, F19, F21, F23, F24, F39, F42 and F112 (`ifs.py`), and F37
(`tools/flash_iap.py`, to flash the IFS). The other commands are from the
firmware only and **unconfirmed**.

| Cmd | Params | Effect | Reply |
|---|---|---|---|
| F10 | `L<len>` `S<speed>` `C<ch>` | Feed (load) channel. L and S are floats, optional, stored for the move | `F10 ok. FFS channel <ch> feeding.` / `… FFS not ready.` / `… No channel selected.` / `… FFS channel not exist.` |
| F11 | `L<len>` `S<speed>` `C<ch>` | Retract (unload) channel. Stores L negated | `F11 ok. FFS channel <ch> exiting.` + same errors as F10 |
| F12 | — | Report 4 values (meaning TBD, per channel) | `F12 ok. %d %d %d %d` |
| F13 | — | Full status | `F13 ok. FFS_state: %d silk_state: %d chan: %d ffs_channels_insert: %d stall_state: %d jinsi_GCONF: %08x qiehuan_GCONF: %08x` |
| F14 | — | Per-channel stall flags | `F14 ok. stall: %d %d %d %d` |
| F15 | — | Toggles two GPIO pins, state → 5 (stop / reset to idle?) | `F15 ok.` |
| F18 | — | state → 1 | `F18 ok` |
| F19 | — | Identify | `F19 ok. four color. version: 3.0.7` |
| F20 | — | Ping | `F20 ok.` |
| F21 | — | Per-channel filament ("silk") sensor and stall counters (16-bit) | `F21 ok.\r\n silk: %d %d %d %d \r\n stall: %d %d %d %d` |
| F22 | — | Bitmask of channels with filament inserted (bit0 = ch1) | `F22 ok. ffs_channels_insert: %d` |
| F23 | `C<ch>` | Clear that channel's inserted bit. The stock app sends it to acknowledge a newly inserted spool and after each purge round (captured from the stock app) | `F23 ok. chan <ch>.` / `F23 ok. no chan.` |
| F24 | `C<ch>` | Select active channel, state → 1 | `F24 ok. chan <ch>.` / errors |
| F30 | `D<n>` | Stores n, state → 0x80 (meaning TBD) | `F30 ok.` |
| F37 | — | Writes a flag, then system reset via AIRCR. The updater's `ifsF37` tool sends this to enter the bootloader | none (resets) |
| F39 | `C<ch>` | Release channel (back off / free the filament path?) | `F39 ok. FFS channel <ch> release.` + errors |
| F40 | — | Stall counters | `F40 ok.stall count: C1: %d C2: %d C3: %d C4: %d` |
| F41 / F50 | — | Feed driver GCONF (reg 0x00) | `F41 ok.GCONF: %08x` |
| F42 | `T<motor>` `I<irun>` | Set run current. T1 = feed ("jinsi"), T2 = switch ("qiehuan"); I clamped to 0–31, written to IHOLD_IRUN (0x10) with IHOLDDELAY 10 | `F42 ok.stepper_motor: %d stepper_motor_irun: %d` |
| F43 | — | Re-initialise both drivers | `F43 ok.` |
| F44 / F53 | — | Feed driver DRV_STATUS (0x6F) | `… DRV_STATUS: %08x` |
| F45 / F51 | — | Feed driver GSTAT (0x01) | `… GSTAT: %08x` |
| F52 | — | Feed driver CHOPCONF (0x6C) | |
| F54 | — | Feed driver PWMCONF (0x70) | |
| F60–F64 | — | Same as F50–F54 for the switch driver | |
| F112 | — | Stop: halts the motors (the same routine the fault stop uses), state → 5, reply yes. Refused only while a fault is latched (works during a move) | `F112 ok. yes.` / `F112 ok. error.` |

Implemented but silent: F46–F49. Everything else in F10–F39 not listed above falls to a no-reply default.

## Hardware hints from the firmware

- Two Trinamic drivers on single-wire UART. The register set (PWMCONF 0x70, DRV_STATUS 0x6F) points to TMC2209/2208. One drives the shared feed motor, the other the channel-switch motor.
- MCU: a Nations N32G455 (Cortex-M4; `docs/mcu-flashing.md`), app at 0x08010000 (bootloader below that, not in the update), STM32F1-style RCC/GPIO addresses.

## Answered and open questions

Partly answered by running the stock app in a sandbox (captured from the stock app)
and by Kiln OS's own use:

1. ~~Line terminator and signalling~~: RS-485 half-duplex (see Transport); Kiln OS sends `\r\n`. What the stock app sends is not confirmed.
2. ~~Units of `L` and `S`~~: millimetres and mm/min. Stock sends `F10 C<n> L90 S300` together with `G1 E90 F300`.
3. ~~What the host polls~~: `F13`, about every 0.8 s in the sandbox (482 of 525 commands in a print with one swap). The stock app's rate on hardware is not measured.
4. ~~Order for a full colour swap~~: recorded (`F24`, `F11`, `F112`, `F11`, `F24`, `F10`, `F112`, then per purge round `F10`, `F112`, `F39`, `F23`). F112 is the stop. Stock didn't send F12, F15, F18 or F30 in any run; F12, F18 and F30 are still open.

## Seen on one printer

Read-only queries in USB test mode (stock app not running), 2026-10-15,
`tools/probe_boards.py`. Silent until asked.

```
F19 ok. four color. version: 3.0.7
F13 ok. FFS_state: 5 silk_state: 15 chan: 0 ffs_channels_insert: 0 stall_state: 0 jinsi_GCONF: 00000000 qiehuan_GCONF: 00000000
F21 ok. \r\n silk: 212 3850 609 3337 \r\n stall: 2408 3210 2117 813
F22 ok. ffs_channels_insert: 0
```

Matches the simulator (`tools/fake_ifs.py`) apart from the two GCONF
values (0 here, `000001c0` in the simulator, not used by `ifs.py`).
`silk_state: 15` = all four channels have filament; no new-spool flags,
so nothing for the pre-feed to do on this boot. The toolhead board on
`ttyS5` repeats `Ready.` (its bootloader, waiting for the `checkEboard`
handshake); the motion MCU on `ttyS2` is silent.
