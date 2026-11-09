#!/usr/bin/env python3
"""Build an offline UUID128 SPP test executable from one verified Binrui GOC build.

Usage: python goc_desay_uuid128.py ORIGINAL OUTPUT
Requires Python 3.8+ and the stock file with the SHA-256 below.
The tool writes a new local file. It does not connect to or modify a vehicle.
"""

import argparse
import hashlib
import struct
import uuid
from pathlib import Path


STOCK_SHA256 = "f3f074e32c60f69f54aa92c657cbf5925ba2709498f92c99780312900f580f7e"
BUILDER = 0x4ACF8
BUILDER_SIZE = 0x5C
ALLOC_ZEROED = 0x19D28
INIT_SEARCH_OPTIONS = 0x6EFBC
COPY_BYTES = 0x6EDFC
SERVICE_UUID = uuid.UUID("00000000-deca-fade-deca-deafdecacafe")


def thumb_bl(address, target):
    """Encode a Thumb-2 BL using addresses with the Thumb bit cleared."""
    offset = target - (address + 4)
    if offset % 2 or not -(1 << 24) <= offset < (1 << 24):
        raise ValueError("Thumb BL target out of range or misaligned")
    bits = offset & ((1 << 25) - 1)
    sign = bits >> 24
    j1 = ((bits >> 23) & 1) ^ sign ^ 1
    j2 = ((bits >> 22) & 1) ^ sign ^ 1
    first = 0xF000 | (sign << 10) | ((bits >> 12) & 0x3FF)
    second = 0xD000 | (j1 << 13) | (j2 << 11) | ((bits >> 1) & 0x7FF)
    return struct.pack("<HH", first, second)


def uuid128_builder():
    # Keep the stock stack frame to match the existing ARM unwind entry.
    code = bytearray.fromhex("2d e9 f0 41 82 b0")
    # r4 = queue id, r5/r6 = packed remote address, allocate 44 bytes.
    code += bytes.fromhex("04 46 0d 46 16 46 2c 20")
    code += thumb_bl(BUILDER + len(code), ALLOC_ZEROED)

    # Store queue id, primitive 0x000F, remote address and the fixed options word.
    # Pass the options substructure at message+16 to the stock initializer.
    code += bytes.fromhex(
        "44 80 04 46 0f 23 23 80 65 60 a6 60 02 23 e3 60 04 f1 10 00"
    )
    code += thumb_bl(BUILDER + len(code), INIT_SEARCH_OPTIONS)

    adr_offset = len(code)
    code += b"\0\0"  # ADR r1, uuid_literal
    # Copy 16 UUID bytes to message+26 and store search count 1 at message+42.
    code += bytes.fromhex("04 f1 1a 00 10 22")
    code += thumb_bl(BUILDER + len(code), COPY_BYTES)
    code += bytes.fromhex("01 23 63 85 20 46 02 b0 bd e8 f0 81")
    while len(code) % 4:
        code += bytes.fromhex("00 bf")
    literal_offset = len(code)
    code += SERVICE_UUID.bytes

    adr_pc = (BUILDER + adr_offset + 4) & ~3
    adr_imm = BUILDER + literal_offset - adr_pc
    if adr_imm % 4 or not 0 <= adr_imm <= 1020:
        raise ValueError("UUID literal is out of ADR range")
    struct.pack_into("<H", code, adr_offset, 0xA100 | (adr_imm // 4))
    if len(code) > BUILDER_SIZE:
        raise ValueError("Replacement function exceeds the original slot")
    code += bytes.fromhex("00 bf") * ((BUILDER_SIZE - len(code)) // 2)
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("original", type=Path, help="stock 2021 Binrui DESAY gocsdk")
    parser.add_argument("output", type=Path, help="new path for the offline test file")
    args = parser.parse_args()

    try:
        original = args.original.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        if digest != STOCK_SHA256:
            parser.error(f"Unsupported stock SHA-256: {digest}")
        replacement = uuid128_builder()
        patched = (
            original[:BUILDER] + replacement + original[BUILDER + BUILDER_SIZE:]
        )
        with args.output.open("xb") as output:
            output.write(patched)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    print(f"Output: {args.output}")
    print(f"Patched file range: 0x{BUILDER:x}–0x{BUILDER + BUILDER_SIZE - 1:x}")
    print(f"SHA-256: {hashlib.sha256(patched).hexdigest()}")


if __name__ == "__main__":
    main()
