#!/usr/bin/env python3
# Copyright (C) 2026 Hunter Laux <hunterlaux@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
tools/flash_n32.py - Open-source firmware flasher for Nations N32 MCUs.

Flashes microcontroller firmware using the Nations N32 ROM In-System Programming
(ISP) serial bootloader protocol. Used for the mainboard (N32G455 on /dev/ttyS2)
on the Flashforge Adventurer 5X. Replaces the closed-source vendor binary
NationsCommand.

Protocol:
  - Bootloader Entry (repeated per connect attempt):
    - Drive GPIO 50 HIGH (BOOT0 = 1).
    - Pulse GPIO 49 LOW (~200 ms) then HIGH (~200 ms) (NRST).
    - Connect at 8N1 (sweeping 9600, 19200, 38400, 115200 twice each, starting
      at 9600 like NationsCommand).
    - Once connected, immediately drive GPIO 50 LOW (BOOT0 = 0).
  - Frame Framing:
    - Request:
      [0xAA, 0x55, CMD_H, CMD_L, LEN_L, LEN_H, PAR0..PAR3, DATA..., XOR]
      XOR checksum is bitwise XOR of all bytes from index 0 to (9 + LEN).
    - Response:
      [0xAA, 0x55, CMD_H, CMD_L, LEN_L, LEN_H, DATA..., CR1, CR2, XOR]
      CR1 == 0xA0 and CR2 == 0x00 on success.
  - Commands:
    - CMD_GET_INF (0x10, 0x00): Query chip information (bootloader version, UID, flash size).
    - CMD_FLASH_ERASE (0x30, 0x00): Erase target flash pages (2 KB per page).
    - CMD_FLASH_DWNLD (0x31, 0x00): Download firmware in 128-byte chunks (padded to 16-byte
      multiple). Each chunk is prefixed by 16 zero bytes and suffixed by 4 bytes of
      STM32 hardware CRC-32.
    - CMD_DATA_CRC_CHECK (0x32, 0x00): Hardware CRC-32 verification over 16-byte-aligned
      programmed region.
    - CMD_SYS_RESET (0x50, 0x00): Trigger NVIC system reset to boot into application.
    - CMD_APP_GO (0x51, 0x00): Jump directly to application reset vector.
"""

import argparse
import os
import select
import struct
import sys
import termios
import time

FLASH_BASE_ADDR = 0x08000000
PAGE_SIZE = 2048
CHUNK_SIZE = 128

CMD_GET_INF = (0x10, 0x00)
CMD_FLASH_ERASE = (0x30, 0x00)
CMD_FLASH_DWNLD = (0x31, 0x00)
CMD_DATA_CRC_CHECK = (0x32, 0x00)
CMD_SYS_RESET = (0x50, 0x00)
CMD_APP_GO = (0x51, 0x00)

STATUS_SUCCESS = 0xA0

DEFAULT_BAUD_SWEEP = (9600, 9600, 19200, 19200, 38400, 38400, 115200, 115200)


def stm32_crc(data: bytes) -> int:
    """Calculates STM32 / N32 hardware CRC-32 (poly 0x04C11DB7, init 0xFFFFFFFF)."""
    remainder = len(data) % 4
    if remainder:
        data = data + (b"\x00" * (4 - remainder))

    crc = 0xFFFFFFFF
    poly = 0x04C11DB7
    num_words = len(data) // 4
    words = struct.unpack(f"<{num_words}I", data)

    for word in words:
        crc ^= word
        for _ in range(32):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ poly) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
    return crc


def prepare_crc_check(firmware_data: bytes, base_addr: int = FLASH_BASE_ADDR) -> tuple:
    """Prepares 16-byte-aligned CRC-32 and payload for CMD_DATA_CRC_CHECK.

    Because CMD_FLASH_DWNLD zero-pads the final chunk to a 16-byte boundary
    when writing flash, NationsCommand rounds the buffer size up to a multiple
    of 16 bytes (zero-padded) before computing the expected CRC-32 and sending
    CMD_DATA_CRC_CHECK.

    Returns:
        (expected_crc, crc_data_payload, aligned_size)
    """
    remainder = len(firmware_data) % 16
    if remainder:
        padded = firmware_data + (b"\x00" * (16 - remainder))
    else:
        padded = firmware_data
    aligned_size = len(padded)
    expected_crc = stm32_crc(padded)
    crc_data = (b"\x00" * 16) + struct.pack("<II", base_addr, aligned_size)
    return expected_crc, crc_data, aligned_size


def gpio_export(gpio: int):
    """Exports a sysfs GPIO pin if not already exported."""
    gpio_dir = f"/sys/class/gpio/gpio{gpio}"
    if not os.path.exists(gpio_dir):
        try:
            with open("/sys/class/gpio/export", "w") as f:
                f.write(str(gpio))
        except OSError:
            pass


def gpio_set_direction(gpio: int, direction: str):
    """Sets direction for a sysfs GPIO pin."""
    gpio_dir = f"/sys/class/gpio/gpio{gpio}"
    gpio_export(gpio)
    time.sleep(0.01)
    with open(f"{gpio_dir}/direction", "w") as f:
        f.write(direction)


def gpio_set_value(gpio: int, value: int):
    """Sets value (0 or 1) for a sysfs GPIO pin."""
    gpio_dir = f"/sys/class/gpio/gpio{gpio}"
    gpio_export(gpio)
    with open(f"{gpio_dir}/value", "w") as f:
        f.write("1" if value else "0")


def enter_isp_mode(boot0_pin: int = 50, nrst_pin: int = 49):
    """Configures GPIOs and resets MCU into ROM ISP bootloader."""
    gpio_set_direction(boot0_pin, "out")
    gpio_set_direction(nrst_pin, "out")

    # BOOT0 HIGH
    gpio_set_value(boot0_pin, 1)
    time.sleep(0.01)

    # Pulse NRST LOW then HIGH
    gpio_set_value(nrst_pin, 0)
    time.sleep(0.2)
    gpio_set_value(nrst_pin, 1)
    time.sleep(0.2)


def exit_isp_mode(boot0_pin: int = 50, nrst_pin: int = 49):
    """Drives BOOT0 LOW so subsequent reset runs application."""
    gpio_set_value(boot0_pin, 0)
    time.sleep(0.05)


class SerialPort:
    """Raw POSIX serial port wrapper using standard termios."""

    def __init__(self, port: str, baudrate: int = 9600):
        self.port = port
        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        self.configure(baudrate)

    def configure(self, baudrate: int):
        baud_map = {
            9600: termios.B9600,
            19200: termios.B19200,
            38400: termios.B38400,
            57600: termios.B57600,
            115200: termios.B115200,
            230400: termios.B230400,
        }
        b = baud_map.get(baudrate, termios.B9600)
        attr = termios.tcgetattr(self.fd)
        attr[0] = 0                      # iflag: raw
        attr[1] = 0                      # oflag: raw
        attr[2] = termios.CS8 | termios.CREAD | termios.CLOCAL  # cflag: 8N1
        attr[3] = 0                      # lflag: raw, no echo
        attr[4] = b                      # ispeed
        attr[5] = b                      # ospeed
        attr[6][termios.VMIN] = 0        # non-blocking
        attr[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, attr)
        termios.tcflush(self.fd, termios.TCIOFLUSH)

    def write(self, data: bytes):
        os.write(self.fd, data)

    def read_exact(self, count: int, timeout_s: float = 2.0) -> bytes:
        deadline = time.monotonic() + timeout_s
        buf = bytearray()
        while len(buf) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            r, _, _ = select.select([self.fd], [], [], max(0.01, remaining))
            if r:
                try:
                    chunk = os.read(self.fd, count - len(buf))
                except BlockingIOError:
                    continue
                if chunk:
                    buf.extend(chunk)
        return bytes(buf)

    def flush(self):
        termios.tcflush(self.fd, termios.TCIOFLUSH)

    def close(self):
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


def build_frame(cmd: tuple, param: int = 0, data: bytes = b"") -> bytes:
    """Builds a Nations ISP master instruction frame with XOR checksum."""
    cmd_h, cmd_l = cmd
    length = len(data)

    header = bytearray([0xAA, 0x55, cmd_h, cmd_l])
    header.extend(struct.pack("<H", length))
    header.extend(struct.pack("<I", param))

    payload = header + data
    xor_val = 0
    for b in payload:
        xor_val ^= b

    return bytes(payload) + bytes([xor_val])


def send_and_receive(ser: SerialPort, cmd: tuple, param: int = 0,
                     data: bytes = b"", timeout_s: float = 3.0) -> tuple:
    """Sends an instruction frame and reads/validates slave response.

    Returns:
        (status_code, data_payload) on success.
    Raises:
        RuntimeError on communication error, framing error, or CRC mismatch.
    """
    req = build_frame(cmd, param, data)
    ser.flush()
    ser.write(req)

    # Read 6-byte response header: [0xAA, 0x55, CMD_H, CMD_L, LEN_L, LEN_H]
    hdr = ser.read_exact(6, timeout_s=timeout_s)
    if len(hdr) < 6:
        raise RuntimeError(f"Timeout waiting for response header (got {len(hdr)} bytes)")

    if hdr[0] != 0xAA or hdr[1] != 0x55:
        raise RuntimeError(f"Invalid response header sync bytes: {hdr[:2].hex()}")

    data_len = struct.unpack("<H", hdr[4:6])[0]

    # Read remaining response: DATA(data_len) + CR1(1) + CR2(1) + XOR(1) = data_len + 3
    body = ser.read_exact(data_len + 3, timeout_s=timeout_s)
    if len(body) < data_len + 3:
        raise RuntimeError(f"Incomplete response body (expected {data_len + 3}, got {len(body)})")

    resp_data = body[:data_len]
    cr1 = body[data_len]
    cr2 = body[data_len + 1]
    rx_xor = body[data_len + 2]

    # Validate XOR checksum over header + resp_data + CR1 + CR2
    calc_xor = 0
    for b in hdr:
        calc_xor ^= b
    for b in body[:data_len + 2]:
        calc_xor ^= b

    if calc_xor != rx_xor:
        raise RuntimeError(f"Response XOR mismatch (calc 0x{calc_xor:02X} != rx 0x{rx_xor:02X})")

    return cr1, resp_data


def flash_n32(port_name: str, firmware_path: str = None, baudrate: int = None,
              boot0_pin: int = 50, nrst_pin: int = 49, use_gpio: bool = True,
              erase_all: bool = False, verify: bool = True,
              run_app: bool = True, use_app_go: bool = False) -> bool:
    """Flashes firmware into Nations N32 microcontroller via ROM ISP."""
    firmware_data = None
    file_size = 0
    if firmware_path is not None:
        with open(firmware_path, "rb") as f:
            firmware_data = f.read()
        file_size = len(firmware_data)
        if file_size == 0:
            print(f"Error: Firmware file {firmware_path} is empty.")
            return False
        print(f"Firmware: {firmware_path} ({file_size} bytes)")

    baud_sequence = (baudrate, baudrate) if baudrate else DEFAULT_BAUD_SWEEP
    ser = SerialPort(port_name, baud_sequence[0])

    try:
        # Step 1: Handshake / Query chip info (CMD_GET_INF 0x10)
        connected = False
        for baud in baud_sequence:
            if use_gpio:
                enter_isp_mode(boot0_pin, nrst_pin)
            ser.configure(baud)
            print(f"Connect the device at baudrate {baud} ...", end="", flush=True)
            try:
                cr1, chip_info = send_and_receive(ser, CMD_GET_INF, param=0, timeout_s=1.0)
                if cr1 == STATUS_SUCCESS:
                    connected = True
                    print(" Connected!")
                    if len(chip_info) >= 19:
                        bl_ver = chip_info[1] if len(chip_info) > 1 else 0
                        flash_kb = (chip_info[2] if len(chip_info) > 2 else 0) * 256
                        part = chip_info[3:19].decode("ascii", errors="replace").strip("\x00 ")
                        print(f"Target: {part} (Bootloader v{bl_ver >> 4}.{bl_ver & 0x0F}, Flash: {flash_kb} KB)")
                    break
            except RuntimeError:
                print(" timeout")
            time.sleep(0.1)

        if not connected:
            print("\nError: Failed to connect to N32 bootloader.")
            return False

        # Deassert BOOT0 immediately once in ROM ISP (matches NationsCommand)
        if use_gpio:
            exit_isp_mode(boot0_pin, nrst_pin)

        if firmware_data is not None:
            # Step 2: Erase Flash (CMD_FLASH_ERASE 0x30)
            start_page = 0
            if erase_all:
                num_pages = 256  # 512 KB
                print("Erasing all flash pages...")
            else:
                num_pages = (file_size + PAGE_SIZE - 1) // PAGE_SIZE
                print(f"Erasing {num_pages} pages ({num_pages * PAGE_SIZE // 1024} KB)...")

            erase_param = (num_pages << 16) | (start_page & 0xFFFF)
            cr1, _ = send_and_receive(ser, CMD_FLASH_ERASE, param=erase_param, timeout_s=10.0)
            if cr1 != STATUS_SUCCESS:
                print(f"Error: Flash erase failed with status 0x{cr1:02X}")
                return False

            # Step 3: Program Firmware (CMD_FLASH_DWNLD 0x31)
            print(f"Writing {file_size} bytes to flash at 0x{FLASH_BASE_ADDR:08X}...")
            offset = 0
            total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE

            while offset < file_size:
                chunk = firmware_data[offset : offset + CHUNK_SIZE]
                target_addr = FLASH_BASE_ADDR + offset

                # Pad chunk to 16-byte multiple if needed
                remainder = len(chunk) % 16
                if remainder:
                    chunk = chunk + (b"\x00" * (16 - remainder))

                # Calculate chunk CRC32
                chunk_crc = stm32_crc(chunk)

                # Frame payload: 16 zero bytes + chunk + 4 bytes CRC32
                payload = (b"\x00" * 16) + chunk + struct.pack("<I", chunk_crc)

                retries = 3
                success = False
                while retries > 0:
                    try:
                        cr1, _ = send_and_receive(ser, CMD_FLASH_DWNLD, param=target_addr,
                                                  data=payload, timeout_s=3.0)
                        if cr1 == STATUS_SUCCESS:
                            success = True
                            break
                        else:
                            print(f"\n[Offset 0x{offset:06X}] Flash download status 0x{cr1:02X}, retrying...")
                    except RuntimeError as e:
                        print(f"\n[Offset 0x{offset:06X}] Error: {e}, retrying...")
                    retries -= 1
                    time.sleep(0.05)

                if not success:
                    print(f"\nError: Failed to write chunk at offset 0x{offset:06X}.")
                    return False

                offset += len(firmware_data[offset : offset + CHUNK_SIZE])
                chunk_num = (offset + CHUNK_SIZE - 1) // CHUNK_SIZE
                pct = min(100, chunk_num * 100 // total_chunks)
                print(f"\rWriting: {pct}% ({offset}/{file_size} bytes)", end="", flush=True)

            print("\nFlash write complete.")

            # Step 4: Verify Flash via On-Chip CRC (CMD_DATA_CRC_CHECK 0x32)
            if verify:
                print("Verifying flash via on-chip CRC-32...", end="", flush=True)
                expected_crc, crc_data, _ = prepare_crc_check(firmware_data, FLASH_BASE_ADDR)
                try:
                    cr1, _ = send_and_receive(ser, CMD_DATA_CRC_CHECK, param=expected_crc,
                                              data=crc_data, timeout_s=5.0)
                    if cr1 == STATUS_SUCCESS:
                        print(" Chip verification succeeded")
                    else:
                        print(f"\nError: Verification failed (status 0x{cr1:02X})")
                        return False
                except RuntimeError as e:
                    print(f"\nError: CRC check error: {e}")
                    return False

        # Step 5: Reset chip / Launch Application (CMD_SYS_RESET 0x50 or CMD_APP_GO 0x51)
        if run_app:
            cmd = CMD_APP_GO if use_app_go else CMD_SYS_RESET
            label = "Starting application (CMD_APP_GO)" if use_app_go else "Reset chip (CMD_SYS_RESET)"
            print(f"{label}...")
            try:
                cr1, _ = send_and_receive(ser, cmd, param=0, timeout_s=2.0)
                if cr1 == STATUS_SUCCESS:
                    print("Application started.")
            except RuntimeError:
                pass

        return True

    finally:
        ser.close()
        if use_gpio:
            exit_isp_mode(boot0_pin, nrst_pin)


def main():
    parser = argparse.ArgumentParser(
        description="Nations N32 ROM ISP Firmware Flasher (Mainboard)"
    )
    # Support both standard options and NationsCommand legacy arguments
    parser.add_argument("firmware", nargs="?", default=None,
                        help="Path to firmware binary (.bin)")
    parser.add_argument("-p", "--port", dest="port", default=None,
                        help="Serial port (default: /dev/ttyS2)")
    parser.add_argument("-b", "--baud", dest="baud", type=int, default=None,
                        help="Baud rate (default: sweep 9600..115200 starting at 9600)")
    parser.add_argument("--boot0-gpio", type=int, default=50,
                        help="Sysfs GPIO for BOOT0 (default: 50)")
    parser.add_argument("--nrst-gpio", type=int, default=49,
                        help="Sysfs GPIO for NRST (default: 49)")
    parser.add_argument("--no-gpio", action="store_true",
                        help="Do not toggle sysfs GPIOs")
    parser.add_argument("--erase-all", action="store_true",
                        help="Mass erase entire flash instead of sector erase")
    parser.add_argument("--no-verify", action="store_true",
                        help="Skip CRC verification")
    parser.add_argument("--no-run", action="store_true",
                        help="Do not reset/start application after flashing")
    parser.add_argument("--app-go", action="store_true",
                        help="Use CMD_APP_GO (0x51) instead of CMD_SYS_RESET (0x50)")
    parser.add_argument("--check", action="store_true",
                        help="Only connect, print chip info, and reset without flashing")

    # NationsCommand legacy options
    parser.add_argument("-c", dest="leg_c", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-d", dest="leg_d", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--pn", dest="leg_pn", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--fn", dest="leg_fn", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--v", dest="leg_v", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-r", dest="leg_r", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-g", dest="leg_g", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()

    firmware = args.firmware or args.leg_fn
    port = args.port or args.leg_pn or "/dev/ttyS2"

    if not firmware and not (args.check or (args.leg_c and not args.leg_d)):
        parser.error("Firmware binary path required (or pass --check).")

    success = flash_n32(
        port_name=port,
        firmware_path=firmware,
        baudrate=args.baud,
        boot0_pin=args.boot0_gpio,
        nrst_pin=args.nrst_gpio,
        use_gpio=not args.no_gpio,
        erase_all=args.erase_all,
        verify=not args.no_verify,
        run_app=not args.no_run,
        use_app_go=args.app_go or args.leg_g
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
