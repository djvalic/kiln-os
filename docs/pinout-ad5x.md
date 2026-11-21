# AD5X main board connector pinout

All measurements were taken on the **FFP0303_Main_Board_V3.0.1** main board,
dated 2025-05-16. Other board revisions may differ.

> **Warning:** the board mixes two logic levels. Ports **B** and **C** of the
> X2600 run at **3.3 V**. Port **D** is 3.3 V except PD0–PD5, which are on
> VDDIO_SD and are **1.8 V** on this board — the eMMC runs HS200, 8-bit, at a
> 1.80 V signal voltage. None of PD0–PD5 reach a connector or a test point. The
> **E port** sits in the 1.8 V bank (VDDIO18), and its `AUX` pins are 1.8 V ADC
> inputs; the **A port** is also 1.8 V on this board. Before connecting an
> expansion board, make sure its signal lines match the level of the pin.
> Ignoring this can destroy the printer.

Two different chips are involved, and both use `PA`/`PB`/`PC` style port names.
Each section below says which chip its pin names belong to:

* **X2600** (the SoC that runs Linux): J5, J6, J8, J19, J24, J28, test points.
* **N32G455** (the microcontroller): J16, J17, J18, J22, J26.

At reset every X2600 GPIO comes up as an input, except PC0–PC3, which start as
the main core's JTAG pins (TDO, TDI, TCK, TMS).

## 1. J28 USB

Wired to the **X2600** as USB0, with OTG support. Used to recover the boot
loader or the eMMC with Ingenic's USBCloner. It can also be used to attach
expansion boards.

The two main board generations differ here: J28 is **fitted** on
first-generation boards and **not fitted** on second-generation ones. On the
FFP0303_Main_Board_V3.0.1 used for these measurements it is not fitted.

Example: connecting a BTT EBB42:

```
serial: /dev/serial/by-id/usb-Klipper_stm32g0b1xx_2A0050000151343530323632-if00
```

## 2. J6 USB

Not fitted at the factory. Wired to the **X2600** as USB1 through a hub
controller (GL852G), port 3 of that hub. Can be used to attach expansion
boards.

## 3. USB hub (GL852G)

The **X2600** has two USB 2.0 ports. USB0 (OTG) goes to J28; USB1 feeds the
**GL852G** hub on the main board, which fans it out to four ports:

| Port | Where it goes                          |
|-----:|----------------------------------------|
| 1    | USB socket on the display board        |
| 2    | USB camera socket on the display board |
| 3    | J6 on the main board                   |
| 4    | Wi-Fi module                           |

USB1 has no OTG. The datasheet says it can act as a device, but on this board
it is wired straight to the hub, so in practice it is host only. USB0 works as
a host too, as the EBB42 example above shows.

## 4. J8 Debug

Fitted at the factory. Wired to the **X2600**, used as USART0 (console). The
E port is in the 1.8 V bank, so there is a **level shifter** between J8 and the
SoC: the 3.3 V levels on the header are safe, PE9 and PE10 themselves are 1.8 V.

| Pin | Signal       |
|----:|--------------|
| VCC | +3.3 V       |
| TX  | TX (PE9)     |
| RX  | RX (PE10)    |
| GND | GND          |

## 5. J22 SWD

Fitted at the factory. Wired to the **N32G455** (N32G455 port names).

| Pin   | Signal |
|------:|--------|
| VCC   | +3.3 V |
| SWCLK | PA14   |
| SWDIO | PA13   |
| GND   | GND    |

## 6. J19 JTAG

Not fitted at the factory. Wired to the **X2600**. This is the **RISC-V core's
JTAG**, not the main core's: PB0–PB3 are in function 2 (JTAG) of the second
core. The main core's JTAG is spread over J5 and the test points (see below).

| Pin | Signal |
|----:|--------|
| VCC | +3.3 V |
| TMS | PB0    |
| TDI | PB1    |
| TDO | PB2    |
| TCK | PB3    |
| GND | GND    |

R80–R83 are 0 Ω links in these four lines. Kiln keeps UART1, I2C1, I2C2 and
SPI0 disabled, so the pins are free. In the stock firmware `IAPCommand` and
`IFSCommand` contain code that pulses PB2 and sets PB3, but nothing calls it.
PB2 and PB3 go nowhere else on the board: only to J19.

## 7. J24 TVOC

Not fitted at the factory. Wired to the **X2600** as UART3 (`/dev/ttyS3`). Both
Kiln and the stock firmware enable the port, but nothing opens it.

| Pin | Signal |
|----:|--------|
| 5V  | NC     |
| RX  | PB22   |
| TX  | PB23   |
| GND | GND    |

## 8. J26 Servo motor

Not fitted at the factory. Wired to the **N32G455** (N32G455 port names), pin
PC11. This pin appears in none of the configs.

| Pin | Signal |
|----:|--------|
| 5V  | NC     |
| SIG | PC11   |
| GND | GND    |

## 9. J18 Filter fan in

Not fitted at the factory. Wired to the **N32G455** (N32G455 port names), pin
PA4. In the stock `printer.base.cfg` the `external_fan` on PA4 is commented
out. Using it requires soldering the additional support components.

## 10. J17 Filter fan out

Not fitted at the factory. Wired to the **N32G455** (N32G455 port names), pin
PC15. In the stock `printer.base.cfg` the `internal_fan` on PC15 is commented
out. Using it requires soldering the additional support components.

## 11. J16 PLA fan

Fitted at the factory. Wired to the **N32G455** (N32G455 port names), pin PB7.
In the stock `printer.base.cfg` the `chamber_fan` on PB7 is commented out.

| Pin | Signal |
|----:|--------|
| +   | +24 V  |
| PWM | PB7    |
| FG  | +3.3 V |
| −   | GND    |

## 12. J5 LCD

Wired to the **X2600**. The panel is 800x480 and Kiln drives it as **LVDS**
(`ad5x-display.dtsi`); the datasheet only calls these pins DSI.

| Pin | Signal      | Pin | Signal      |
|----:|-------------|----:|-------------|
| 1   | GND         | 2   | USB2_LCD D+ |
| 3   | USB2_LCD D− | 4   | GND         |
| 5   | K1          | 6   | USB1_LCD D+ |
| 7   | USB1_LCD D− | 8   | +5 V        |
| 9   | +5 V        | 10  | +5 V        |
| 11  | GND         | 12  | PC14        |
| 13  | PC10        | 14  | GND         |
| 15  | PC0         | 16  | PC1         |
| 17  | GND         | 18  | PC7         |
| 19  | unknown     | 20  | GND         |
| 21  | lane 0 −    | 22  | lane 0 +    |
| 23  | GND         | 24  | lane 1 −    |
| 25  | lane 1 +    | 26  | GND         |
| 27  | lane 2 −    | 28  | lane 2 +    |
| 29  | GND         | 30  | clock −     |
| 31  | clock +     | 32  | GND         |
| 33  | lane 3 −    | 34  | lane 3 +    |
| 35  | GND         | 36  | GND         |
| 37  | GND         | 38  | +3.3 V      |
| 39  | +3.3 V      | 40  | +3.3 V      |

Ten DSI balls: four data lanes plus one clock.

| Pins  | Balls | Signal    |
|-------|-------|-----------|
| 21/22 | U5/T6 | lane 0 −/+ |
| 24/25 | R5/T5 | lane 1 −/+ |
| 27/28 | T3/U3 | lane 2 −/+ |
| 30/31 | R4/T4 | clock −/+  |
| 33/34 | T2/U2 | lane 3 −/+ |

USB: pin 2/3 is `USB2_LCD`, pin 6/7 is `USB1_LCD`. `USB1` is hub port 1 (the
USB socket on the display board), `USB2` is hub port 2 (the camera socket on
the display board). Pin 19 is still unknown.

Other X2600 pins on J5:

* PC14 (pin 12, ball T13) — backlight on/off, also PWM15. Pulled down at reset,
  so the backlight stays off until Linux drives it.
* PC10 (pin 13, ball T11) — PWM11 / TCU5_IN1 / CAN1_RX. Neither Kiln nor the
  stock firmware uses it: it is not in `firmwareExe`, the module scripts or the
  start-up scripts. Its purpose is unknown.
* PC0/PC1 (pins 15/16, balls B4/C5) — touch I2C0 clock/data, TSC2007 at 0x48,
  400 kHz. At reset these are the main core's JTAG TDO/TDI.
* PC7 (pin 18, ball T10) — touch interrupt, low while the panel is touched.

I2C0 and the interrupt both go over this cable, so the TSC2007 sits on the
display board, not on the main board.

PC10 is CAN1_RX and TP44 (PC9) is CAN1_TX, so both CAN1 pins are reachable: one
on J5, one on a test point.

Pin 5 is K1, the AD5M Pro power button — see section 16.

## 13. Test points

X2600 test points, by BGA ball number.

| TP | Ball | Pin | Functions                       | V   |
|---:|------|-----|---------------------------------|-----|
| 12 | E17  | PB4 | LCD_D0, SLCD_D0                 | 3.3 |
| 14 | C6   | TRST_ | main core JTAG reset          | 3.3 |
| 15 | A3   | PD6 | SFC0_CLK, MSC1_CLK              | 3.3 |
| 16 | A1   | PD11 | SFC0_CE_, MSC1_D3              | 3.3 |
| 17 | B3   | PD7 | SFC0_DQ0, MSC1_CMD              | 3.3 |
| 18 | C3   | PD8 | SFC0_DQ1, MSC1_D0               | 3.3 |
| 19 | A2   | PD10 | SFC0_DQ2, MSC1_D2              | 3.3 |
| 20 | C4   | PD9 | SFC0_DQ3, MSC1_D1               | 3.3 |
| 21 | K2   | PE8 | AUX3 (ADC)                      | 1.8 |
| 22 | J3   | PE11 | AUX6, UART0_RTS                | 1.8 |
| 23 | H3   | PE12 | AUX7, UART0_CTS                | 1.8 |
| 24 | F15  | PB30 | LCD_HSYNC                      | 3.3 |
| 25 | G17  | PB31 | LCD_DE                         | 3.3 |
| 26 | R13  | PC25 | MSC1_CLK, SSI1_CLK             | 3.3 |
| 27 | T15  | PC26 | MSC1_CMD, SSI1_DT              | 3.3 |
| 28 | R14  | PC27 | MSC1_D0, SSI1_DR               | 3.3 |
| 29 | T14  | PC28 | MSC1_D1                        | 3.3 |
| 30 | U16  | PC29 | MSC1_D2                        | 3.3 |
| 31 | U15  | PC30 | MSC1_D3, SSI1_CE0              | 3.3 |
| 44 | U11  | PC9 | PWM10, CAN1_TX                  | 3.3 |
| 46 | A5   | PC2 | main core JTAG TCK, I2C1_SCK, UART1_TXD | 3.3 |
| 47 | B13  | PB21 | LCD_D17                       | 3.3 |
| 48 | C13  | PB20 | LCD_D16                       | 3.3 |
| 49 | B15  | PB16 | LCD_D12, PWM4                  | 3.3 |
| 50 | A16  | PB15 | LCD_D11, PWM3                  | 3.3 |
| 51 | C15  | PB14 | LCD_D10, PWM2                  | 3.3 |
| 52 | A17  | PB13 | LCD_D9, PWM1                   | 3.3 |
| 53 | C16  | PB10 | LCD_D6                        | 3.3 |
| 55 | D15  | PB8 | LCD_D4                         | 3.3 |
| 56 | E15  | PB6 | LCD_D2                         | 3.3 |
| 57 | L1   | PE5 | AUX0 (ADC), I2C3_SCK            | 1.8 |
| 58 | L3   | PE13 | AUX8 (ADC)                     | 1.8 |

Notes:

* TP15–TP20 are all six SFC0 / 4-bit MSC1 pins, on port D.
* TP26–TP31 are the other six 4-bit MSC1 pins, on port C.
* Kiln uses none of them, apart from TP22/TP23, which are part of the UART0 pin
  group (J8).
* The panel is LVDS, so the parallel LCD pins of port B are free.
* The main core's JTAG is spread out: TDO/TDI on J5 pins 15/16, TCK on TP46,
  TRST_ on TP14. TMS is PC3, which is the RS-485 driver enable for the IFS
  port, so it is not brought out to a test point.

## 14. X2600 pins Kiln uses

As in Kiln's device tree (`ad5x.dts`), which follows stock.

| Pin         | Use                                              |
|-------------|--------------------------------------------------|
| PB7         | Wi-Fi power                                      |
| PB11        | power key                                        |
| PB17/PB18   | mainboard N32 NRST and BOOT0 (from stock tools)   |
| PB22/PB23   | UART3 (`ttyS3`), enabled but unused, J24          |
| PB24/PB25   | UART4 (`ttyS4`), IFS (RS-485)                     |
| PB26/PB27   | UART5 (`ttyS5`), toolhead board                   |
| PC0/PC1     | I2C0 touch, J5                                   |
| PC3         | RS-485 driver enable                              |
| PC4/PC5     | UART7 (`ttyS7`), weighing board                   |
| PC6         | console strap, read by SPL                        |
| PC7         | touch interrupt, J5                              |
| PC11        | heartbeat                                        |
| PC12        | speaker (PWM13)                                  |
| PC14        | backlight, J5                                    |
| PC15        | Ethernet PHY clock pin, held low                 |
| PC16–PC24   | Ethernet (RMII)                                  |
| PD0–PD5, PE1–PE4 | eMMC (MSC0, 8-bit)                          |
| PD12/PD13   | UART2 (`ttyS2`), mainboard N32                    |
| PE9–PE12    | UART0 (`ttyS0`), console, J8                     |


## 15. N32G455 pins Kiln uses

From `ad5x.cfg`. Six of these pins reach a connector:

| Pin | Use                    | Connector |
|-----|------------------------|-----------|
| PA0 | bed thermistor         | J35       |
| PA5 | PCB fan                | J20       |
| PA11| chamber light          | J21       |
| PB3 | probe (weighing board) | J23 (RES) |
| PC12| Y endstop              | J12       |
| PD2 | Z endstop              | J14       |

The rest are wired straight on the board and go to no connector at all:

| Pin           | Use                |
|---------------|--------------------|
| PA2/PA7/PC4   | Y enable/dir/step  |
| PB0           | Y TMC2209 UART     |
| PB1/PB12/PB13 | X enable/dir/step  |
| PB9           | bed heater         |
| PB11          | X TMC2209 UART     |
| PB14/PC8/PC7  | Z enable/dir/step  |
| PB15          | Z TMC2209 UART     |

These are wired to a connector, but their function is disabled in the stock
config:

| Pin | Use                          | Connector       |
|-----|------------------------------|-----------------|
| PA4 | external fan (commented out) | J18, not fitted |
| PB7 | chamber_fan (commented out)  | J16, fitted     |
| PC11| not in any config            | J26, not fitted |
| PC15| internal fan (commented out) | J17, not fitted |

## 16. Power path: K1 and PB12

Both belong to the AD5M Pro, and neither is used on the AD5X.

* **K1** is the power button of the AD5M Pro. The same button is also on the
  LCD board. On the AD5X it has no direct connection to the X2600 or the
  N32G455.
* **PB12 (GPIO 44)** works in the power circuit on the AD5M Pro, the same way
  as K1. There it goes to **U20**, presumably a small microcontroller such as
  the STC15W201 or an equivalent. **That part is not fitted on the AD5X**, so
  PB12 has nothing to talk to.


## 17. Still open

* J5 pin 19 — unknown.
* J5 pin 13 (PC10) — not used by Kiln or the stock firmware; its purpose is
  unknown.
