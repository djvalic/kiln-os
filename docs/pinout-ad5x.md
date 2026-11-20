# AD5X main board connector pinout

All measurements were taken on the **FFP0303_Main_Board_V3.0.1** main board,
dated 2025-05-16. Other board revisions may differ.

> **Warning:** before connecting an expansion board, make sure its signal lines
> are rated for **3.3 V or less**. Ignoring this can destroy the printer.

Two different chips are involved, and both use `PA`/`PB`/`PC` style port names.
Each section below says which chip its pin names belong to: **X2600** (the SoC
that runs Linux) or **N32G455** (the microcontroller).

## 1. J28 USB

Not fitted at the factory. Wired to the **X2600** as USB0, with OTG support.
Used to recover the boot loader or the eMMC with Ingenic's USBCloner. It can
also be used to attach expansion boards.

Example: connecting a BTT EBB42:

```
serial: /dev/serial/by-id/usb-Klipper_stm32g0b1xx_2A0050000151343530323632-if00
```

## 2. J6 USB

Not fitted at the factory. Wired to the **X2600** as USB1 through a hub
controller (GL852G). Can be used to attach expansion boards.

## 3. J8 Debug

Fitted at the factory. Wired to the **X2600**, used as USART0 (console).

| Pin | Signal       |
|----:|--------------|
| VCC | +3.3 V       |
| TX  | TX (PE9)     |
| RX  | RX (PE10)    |
| GND | GND          |

## 4. J22 SWD

Fitted at the factory. Wired to the **N32G455** (N32G455 port names).

| Pin   | Signal |
|------:|--------|
| VCC   | +3.3 V |
| SWCLK | PA14   |
| SWDIO | PA13   |
| GND   | GND    |

## 5. J19 JTAG

Not fitted at the factory. Wired to the **X2600**.

| Pin | Signal |
|----:|--------|
| VCC | +3.3 V |
| TMS | PB0    |
| TDI | PB1    |
| TDO | PB2    |
| TCK | PB3    |
| GND | GND    |

## 6. J24 TVOC

Not fitted at the factory. Wired to the **X2600**.

| Pin | Signal |
|----:|--------|
| 5V  | NC     |
| RX  | PB22   |
| TX  | PB23   |
| GND | GND    |

## 7. J26 Servo motor

Not fitted at the factory. Wired to the **N32G455** (N32G455 port names).

| Pin | Signal |
|----:|--------|
| 5V  | NC     |
| SIG | PC11   |
| GND | GND    |

## 8. J18 Filter fan in

Not fitted at the factory. Wired to the **N32G455** (N32G455 port names),
pin PA4. Using it requires soldering the additional support components.

## 9. J17 Filter fan out

Not fitted at the factory. Wired to the **N32G455** (N32G455 port names),
pin PC15. Using it requires soldering the additional support components.

## 10. J5 LCD

Wired to the **X2600**.

| Pin | Signal      | Pin | Signal      |
|----:|-------------|----:|-------------|
| 1   | GND         | 2   | USB2_LCD    |
| 3   | USB2_LCD    | 4   | GND         |
| 5   | K1          | 6   | USB1_LCD    |
| 7   | USB1_LCD    | 8   | +5 V        |
| 9   | +5 V        | 10  | +5 V        |
| 11  | GND         | 12  | PC14        |
| 13  | PC10        | 14  | GND         |
| 15  | PC0         | 16  | PC1         |
| 17  | GND         | 18  | PC7         |
| 19  | unknown     | 20  | GND         |
| 21  | DSI_TX(U5)  | 22  | DSI_TX(T6)  |
| 23  | GND         | 24  | DSI_TX(R5)  |
| 25  | DSI_TX(T5)  | 26  | GND         |
| 27  | DSI_TX(T3)  | 28  | DSI_TX(U3)  |
| 29  | GND         | 30  | DSI_TX(R4)  |
| 31  | DSI_TX(T4)  | 32  | GND         |
| 33  | DSI_TX(T2)  | 34  | DSI_TX(U2)  |
| 35  | GND         | 36  | GND         |
| 37  | GND         | 38  | +3.3 V      |
| 39  | +3.3 V      | 40  | +3.3 V      |

## 11. Test points

X2600 test points, by BGA ball number.

| TP | Ball | TP | Ball | TP | Ball |
|---:|------|---:|------|---:|------|
| 12 | E17  | 24 | F15  | 48 | C13  |
| 14 | C6   | 25 | G17  | 49 | B15  |
| 15 | A3   | 26 | R13  | 50 | A16  |
| 16 | A1   | 27 | T15  | 51 | C15  |
| 17 | B3   | 28 | R14  | 52 | A17  |
| 18 | C3   | 29 | T14  | 53 | C16  |
| 19 | A2   | 30 | U16  | 55 | D15  |
| 20 | C4   | 31 | U15  | 56 | E15  |
| 21 | K2   | 44 | U11  | 57 | L1   |
| 22 | J3   | 46 | A5   | 58 | L3   |
| 23 | H3   | 47 | B13  |    |      |

