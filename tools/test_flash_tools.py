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
"""Unit and protocol simulation tests for flash_iap.py and flash_n32.py."""

import os
import pty
import struct
import tempfile
import threading
import unittest

from flash_iap import (
    CMD_ACK,
    CMD_EOT,
    CMD_HD,
    CMD_POLL_CRC,
    CMD_SOH,
    FRAME_DATA_SIZE,
    FRAME_TOTAL_SIZE,
    build_iap_frame,
    crc16_ccitt as iap_crc16,
    flash_iap,
    load_firmware,
    parse_intel_hex,
)
from flash_n32 import (
    CMD_APP_GO,
    CMD_DATA_CRC_CHECK,
    CMD_FLASH_DWNLD,
    CMD_FLASH_ERASE,
    CMD_GET_INF,
    CMD_SYS_RESET,
    STATUS_SUCCESS,
    build_frame,
    flash_n32,
    prepare_crc_check,
    stm32_crc,
)


def _build_n32_slave_resp(cmd: tuple, status: int = STATUS_SUCCESS, data: bytes = b"") -> bytes:
    hdr = bytearray([0xAA, 0x55, cmd[0], cmd[1]])
    hdr.extend(struct.pack("<H", len(data)))
    body = hdr + data + bytes([status, 0x00])
    xor_val = 0
    for b in body:
        xor_val ^= b
    return bytes(body) + bytes([xor_val])


class TestFlashIAP(unittest.TestCase):
    def test_crc16_ccitt(self):
        self.assertEqual(iap_crc16(b"123456789"), 0x31C3)
        self.assertEqual(iap_crc16(b"\x00" * 1024), 0x0000)
        self.assertEqual(iap_crc16(b"\xFF" * 1024), 0xC084)

    def test_parse_intel_hex_and_frame_valid_len(self):
        # Sample Intel HEX with extended linear address record (04),
        # two 16-byte data records (00) with an 8-byte gap between them, and EOF (01)
        hex_content = (
            ":020000040801F1\n"
            ":10000000000102030405060708090A0B0C0D0E0FE8\n"
            ":10001800101112131415161718191A1B1C1D1E1FD0\n"
            ":00000001FF\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".hex", delete=False) as f:
            f.write(hex_content)
            temp_path = f.name

        try:
            image = parse_intel_hex(temp_path)
            # Unpadded span from 0x08010000 to 0x08010027 inclusive = 40 bytes
            self.assertEqual(len(image), 40)
            self.assertEqual(image[:16], bytes(range(16)))
            self.assertEqual(image[16:24], b"\xFF" * 8)
            self.assertEqual(image[24:40], bytes(range(16, 32)))

            # Building IAP frame preserves unpadded valid_len (40) in bytes [2..3]
            frame = build_iap_frame(0, image)
            self.assertEqual(len(frame), FRAME_TOTAL_SIZE)
            self.assertEqual(frame[0:1], CMD_SOH)
            self.assertEqual(frame[1], 0)
            valid_len = struct.unpack("<H", frame[2:4])[0]
            self.assertEqual(valid_len, 40)
            # Rebuilt slice using valid_len matches unpadded image byte-for-byte
            self.assertEqual(frame[4 : 4 + valid_len], image)
            # Padding is 0xFF and CRC-16 covers all 1024 bytes
            self.assertEqual(frame[4 + valid_len : 1028], b"\xFF" * (1024 - 40))
            expected_crc = iap_crc16(frame[4:1028])
            self.assertEqual(struct.unpack("<H", frame[1028:1030])[0], expected_crc)
        finally:
            os.unlink(temp_path)

    def test_load_firmware_binary(self):
        with tempfile.NamedTemporaryFile("wb", suffix=".bin", delete=False) as f:
            f.write(b"ABCDEF" * 200)  # 1200 bytes (1 full frame + 176-byte partial frame)
            temp_path = f.name

        try:
            image = load_firmware(temp_path)
            self.assertEqual(len(image), 1200)
            f0 = build_iap_frame(0, image[:1024])
            f1 = build_iap_frame(1, image[1024:])
            self.assertEqual(struct.unpack("<H", f0[2:4])[0], 1024)
            self.assertEqual(struct.unpack("<H", f1[2:4])[0], 176)
            rebuilt = f0[4 : 4 + 1024] + f1[4 : 4 + 176]
            self.assertEqual(rebuilt, image)
        finally:
            os.unlink(temp_path)

    def test_dry_run_refuses_f37(self):
        # Must refuse immediately without opening the serial port or erasing 0x0800D000
        self.assertFalse(
            flash_iap("/dev/nonexistent_tty", "dummy.hex", trigger_f37=True, dry_run=True)
        )

    def test_pty_iap_simulation_and_hd_abort(self):
        payload = os.urandom(1500)  # 2 frames: 1024 + 476 bytes
        with tempfile.NamedTemporaryFile("wb", suffix=".bin", delete=False) as f:
            f.write(payload)
            fw_path = f.name

        try:
            # 1. Test 0x07 ("Update :HD") abort without writing frames
            master_fd, slave_fd = pty.openpty()
            slave_name = os.ttyname(slave_fd)

            def hd_bootloader():
                b = os.read(master_fd, 1)
                if b == CMD_POLL_CRC:
                    os.write(master_fd, CMD_HD)

            t = threading.Thread(target=hd_bootloader, daemon=True)
            t.start()
            try:
                ok = flash_iap(slave_name, fw_path, trigger_f37=False, wait_seconds=5)
                self.assertFalse(ok)
            finally:
                t.join(timeout=2)
                os.close(master_fd)
                os.close(slave_fd)

            # 2. Test full 2-frame transfer + EOT reconstruction
            master_fd, slave_fd = pty.openpty()
            slave_name = os.ttyname(slave_fd)
            reconstructed = bytearray()

            def full_bootloader():
                b = os.read(master_fd, 1)
                if b == CMD_POLL_CRC:
                    os.write(master_fd, CMD_ACK)
                for expected_seq in range(2):
                    buf = bytearray()
                    while len(buf) < FRAME_TOTAL_SIZE:
                        buf.extend(os.read(master_fd, FRAME_TOTAL_SIZE - len(buf)))
                    assert buf[0:1] == CMD_SOH
                    assert buf[1] == expected_seq
                    valid_len = struct.unpack("<H", buf[2:4])[0]
                    data = bytes(buf[4:1028])
                    rx_crc = struct.unpack("<H", buf[1028:1030])[0]
                    assert rx_crc == iap_crc16(data)
                    reconstructed.extend(data[:valid_len])
                    os.write(master_fd, CMD_ACK)
                eot = os.read(master_fd, 1)
                if eot == CMD_EOT:
                    os.write(master_fd, CMD_ACK)

            t = threading.Thread(target=full_bootloader, daemon=True)
            t.start()
            try:
                ok = flash_iap(slave_name, fw_path, trigger_f37=False, wait_seconds=5)
                self.assertTrue(ok)
                t.join(timeout=2)
                self.assertEqual(bytes(reconstructed), payload)
            finally:
                os.close(master_fd)
                os.close(slave_fd)
        finally:
            os.unlink(fw_path)


class TestFlashN32(unittest.TestCase):
    def test_stm32_crc(self):
        self.assertEqual(stm32_crc(b"Hello world 1234"), 0x13D27D1B)
        self.assertEqual(stm32_crc(b"\x00\x00\x00\x00"), 0xC704DD7B)
        self.assertEqual(stm32_crc(b"\x00\x00"), 0xC704DD7B)

    def test_prepare_crc_check_16byte_alignment(self):
        # 41432 bytes (like mainboard.bin: 41432 % 16 == 8) must be zero-padded to 41440 bytes
        raw = b"\xAA" * 24  # 24 % 16 == 8
        expected_crc, crc_data, aligned_size = prepare_crc_check(raw, 0x08000000)
        self.assertEqual(aligned_size, 32)
        self.assertEqual(expected_crc, stm32_crc(raw + (b"\x00" * 8)))
        self.assertEqual(crc_data[:16], b"\x00" * 16)
        base_addr, length = struct.unpack("<II", crc_data[16:24])
        self.assertEqual(base_addr, 0x08000000)
        self.assertEqual(length, 32)
        # Confirm it differs from unaligned 24-byte CRC
        self.assertNotEqual(expected_crc, stm32_crc(raw))

    def test_build_frame_get_inf(self):
        frame = build_frame(CMD_GET_INF, param=0, data=b"")
        self.assertEqual(frame, bytes.fromhex("AA551000000000000000EF"))

    def test_build_frame_erase(self):
        frame = build_frame(CMD_FLASH_ERASE, param=0x00200000, data=b"")
        self.assertEqual(len(frame), 11)
        self.assertEqual(frame[:10], bytes.fromhex("AA553000000000002000"))
        xor = 0
        for b in frame[:10]:
            xor ^= b
        self.assertEqual(frame[10], xor)

    def test_build_frame_dwnld(self):
        chunk_data = b"X" * 128
        chunk_crc = stm32_crc(chunk_data)
        payload = (b"\x00" * 16) + chunk_data + struct.pack("<I", chunk_crc)
        self.assertEqual(len(payload), 148)

        frame = build_frame(CMD_FLASH_DWNLD, param=0x08000000, data=payload)
        self.assertEqual(len(frame), 11 + 148)
        self.assertEqual(frame[:4], bytes.fromhex("AA553100"))
        self.assertEqual(struct.unpack("<H", frame[4:6])[0], 148)
        self.assertEqual(struct.unpack("<I", frame[6:10])[0], 0x08000000)
        xor = 0
        for b in frame[:-1]:
            xor ^= b
        self.assertEqual(frame[-1], xor)

    def test_pty_n32_simulation(self):
        # 136 bytes (not a multiple of 16: 136 % 16 == 8 -> padded to 144 in flash)
        fw_bytes = bytes(range(136))
        with tempfile.NamedTemporaryFile("wb", suffix=".bin", delete=False) as f:
            f.write(fw_bytes)
            fw_path = f.name

        master_fd, slave_fd = pty.openpty()
        slave_name = os.ttyname(slave_fd)
        flash_mem = bytearray()
        commands_seen = []

        def n32_rom_bootloader():
            while True:
                hdr = bytearray()
                while len(hdr) < 10:
                    chunk = os.read(master_fd, 10 - len(hdr))
                    if not chunk:
                        return
                    hdr.extend(chunk)
                cmd = (hdr[2], hdr[3])
                data_len = struct.unpack("<H", hdr[4:6])[0]
                param = struct.unpack("<I", hdr[6:10])[0]
                rest = bytearray()
                while len(rest) < data_len + 1:
                    rest.extend(os.read(master_fd, (data_len + 1) - len(rest)))
                data = bytes(rest[:data_len])
                commands_seen.append(cmd)

                if cmd == CMD_GET_INF:
                    chip_info = b"\x00\x22\x02" + b"N32G455REL7\x00\x00\x00\x00\x00" + (b"\x11" * 13)
                    os.write(master_fd, _build_n32_slave_resp(cmd, STATUS_SUCCESS, chip_info))
                elif cmd == CMD_FLASH_ERASE:
                    os.write(master_fd, _build_n32_slave_resp(cmd, STATUS_SUCCESS))
                elif cmd == CMD_FLASH_DWNLD:
                    chunk_payload = data[16:-4]
                    rx_crc = struct.unpack("<I", data[-4:])[0]
                    assert rx_crc == stm32_crc(chunk_payload)
                    flash_mem.extend(chunk_payload)
                    os.write(master_fd, _build_n32_slave_resp(cmd, STATUS_SUCCESS))
                elif cmd == CMD_DATA_CRC_CHECK:
                    start_addr, check_len = struct.unpack("<II", data[16:24])
                    assert start_addr == 0x08000000
                    assert check_len == len(flash_mem)  # 144 bytes (16-byte aligned)
                    calc_crc = stm32_crc(bytes(flash_mem[:check_len]))
                    status = STATUS_SUCCESS if calc_crc == param else 0xB0
                    os.write(master_fd, _build_n32_slave_resp(cmd, status))
                elif cmd in (CMD_SYS_RESET, CMD_APP_GO):
                    os.write(master_fd, _build_n32_slave_resp(cmd, STATUS_SUCCESS))
                    return

        t = threading.Thread(target=n32_rom_bootloader, daemon=True)
        t.start()
        try:
            ok = flash_n32(
                slave_name,
                fw_path,
                baudrate=9600,
                use_gpio=False,
                verify=True,
                run_app=True,
            )
            self.assertTrue(ok)
            t.join(timeout=2)
            self.assertEqual(bytes(flash_mem), fw_bytes + (b"\x00" * 8))
            self.assertEqual(commands_seen[-1], CMD_SYS_RESET)
        finally:
            os.close(master_fd)
            os.close(slave_fd)
            os.unlink(fw_path)


if __name__ == "__main__":
    unittest.main()
