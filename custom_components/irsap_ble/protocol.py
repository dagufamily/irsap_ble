"""IRSAP BLE protocol: building command packets and decoding the radiator state (no I/O).

Reverse engineered from Bluetooth traces of the IRSAP NOW app (Ares electric towel warmer).
All temperatures are sent and received in tenths of a degree Celsius, little-endian.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import struct
import time
import zlib

UUID_ANNOUNCE = "8b146310-44bd-4821-9030-100f0b89693d"       # handle 0x3c: announces length / requests state
UUID_CONFIG = "58ff39ce-05d6-42bd-9385-ca5066eabadf"         # handle 0x3e: configuration table
UUID_STATUS_HEADER = "61d4260b-a6a5-4682-b9ae-1f2984ce4a0d"  # handle 0x3a: status header (declared length)
UUID_STATUS_DATA = "aa5032db-5d67-49a0-9598-0aa1c60bd7a4"    # handle 0x40: status data, returned in chunks

CMD_OFF = 1        # off: the radiator goes to antifreeze (5 C)
CMD_PROGRAM = 2    # on, back to the normal program; also rewrites the Comfort preset
CMD_TEMPORARY = 3  # temporary setpoint until a given hour, then back to the program
CMD_MANUAL = 4     # manual setpoint without expiry ("until next modification" in the app)

MODE_MANUAL = "manual"
MODE_PROGRAM = "program"

TEMPLATES: dict[int, str] = {
    1: "0ffce06a0200000003000000000000000000000000000000000000000000000000000000000004000018010011011002081104100ffce06a1b1101100019110110001a110110001811011000071101203c27110940050000120000180000281105400000000000002101100201210110001221012002172101100119210210080709218c40010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff05210220f00008210220c80006210220f0000721011000132101200001410110000241044000000000004101100005410040efddca3b",
    2: "3ffce06a0200000003000000000000000000000000000000000000000000000000000000000004000018010011011002081104103dfce06a1b1101100019110110001a110110001811011000071101203c27110940050000120000180000281105400000000000002101100201210110011221012002172101100119210210080709218c40010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff05210220f00008210220c80006210220f00007210110001321012000014101100002410440000000000041011000054100402499dd8b",
    3: "9bfce06a020000000300000000000000000000000000000000000000000000000000000000000400001b010011011002081104109afce06a1b1101100019110110001a110110001811011000071101203c27110940050000120000180000281105400000000000002101100201210110011221012002172101100119210210080709218c40010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff05210220f00008210220c80006210220e60007210410d010e16a13210120000141011000024104400000000000410110000541004030314e0d",
    4: "5741e46a0200000003000000000000000000000000000000000000000000000000000000000004000018010011011002081104105741e46a1b1101100019110110001a110110001811011000071101203c27110940050000110000170000281105400000000000002101100101210110011221012002172101100119210210080709218c40010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff010600020900010c00020e0001120002160001ff05210220dc0008210220c80006210220f00007210110001321012000014101100002410440000000000041011000054100404f8fb304",
}


@dataclass(frozen=True)
class RadiatorState:
    """Decoded radiator state."""

    mode: str | None            # "manual" or "program"
    is_on: bool
    current_temp: float | None  # measured temperature, C
    target_temp: float | None   # effective setpoint, C
    expiry: datetime | None     # program: next program change; manual with timer: end of the timer
    presets: dict[str, float | None]


def _set_record(blob: bytearray, record_id: int, tenths: int) -> None:
    """Set a 2-byte temperature record (id, 0x21, 0x02, 0x20, value) in a configuration table."""
    k = blob.find(bytes([record_id, 0x21, 0x02, 0x20]))
    if k < 0:
        raise ValueError(f"record {record_id:#x} not found in template")
    blob[k + 4 : k + 6] = struct.pack("<H", tenths)


def build_command(
    command: int,
    *,
    temp: float | None = None,
    hours: float | None = None,
    comfort: float | None = None,
    now: int | None = None,
) -> tuple[bytes, bytes]:
    """Return (announce, blob) to write on UUID_ANNOUNCE then UUID_CONFIG.

    command 3: temp (C) and hours (rounded to the full hour) are used.
    command 4: temp (C) is the manual setpoint.
    command 2: comfort (C) is the Comfort preset written back (the template value is 24.0).
    """
    now = int(now or time.time())
    blob = bytearray(bytes.fromhex(TEMPLATES[command]))
    if command == CMD_TEMPORARY:
        if temp is not None:
            _set_record(blob, 0x06, round(temp * 10))
        if hours is not None:
            k = blob.find(bytes([0x07, 0x21, 0x04, 0x10]))
            if k < 0:
                raise ValueError("expiry record not found in template")
            blob[k + 4 : k + 8] = struct.pack("<I", (now + int(hours * 3600)) // 3600 * 3600)
    elif command == CMD_MANUAL:
        if temp is None:
            raise ValueError("command 4 needs a temperature")
        _set_record(blob, 0x05, round(temp * 10))
    elif command == CMD_PROGRAM and comfort is not None:
        _set_record(blob, 0x05, round(comfort * 10))
    blob[0:4] = struct.pack("<I", now)    # leading timestamp
    blob[52:56] = struct.pack("<I", now)  # second timestamp
    blob[-4:] = struct.pack("<I", zlib.crc32(bytes(blob[:-4])) & 0xFFFFFFFF)  # CRC32 of everything before it
    announce = bytearray(44)
    announce[0:4] = bytes([1, 0, 0, 1])
    announce[4:6] = struct.pack("<H", len(blob))
    announce[-4:] = struct.pack("<I", now)
    return bytes(announce), bytes(blob)


def build_status_requests(now: int | None = None) -> list[bytes]:
    """Two small writes on UUID_ANNOUNCE make the radiator prepare its state for reading."""
    ts = struct.pack("<I", int(now or time.time()))
    return [bytes([op, 0, 0, 1]) + bytes(36) + ts for op in (0, 2)]


def declared_length(header: bytes) -> int:
    """Length of the state data, as declared in the status header."""
    return struct.unpack("<H", header[4:6])[0]


def parse_state(raw: bytes) -> RadiatorState | None:
    """Decode the state data (concatenated chunks read from UUID_STATUS_DATA)."""
    start = raw.find(bytes([0x01, 0x21, 0x01, 0x10]))
    if start < 0:
        return None
    area = raw[start:]

    def rec(record_id: int) -> int | None:
        # record layout: id, group (0x21), length, type, value (little-endian)
        k = area.find(bytes([record_id, 0x21]))
        while k >= 0:
            length = area[k + 2] if k + 2 < len(area) else 0
            if length in (1, 2, 4) and k + 4 + length <= len(area):
                return int.from_bytes(area[k + 4 : k + 4 + length], "little")
            k = area.find(bytes([record_id, 0x21]), k + 1)
        return None

    mode = None
    if start >= 5 and raw[start - 5 : start - 1] == bytes([0x00, 0x21, 0x01, 0x10]):
        mode = {1: MODE_MANUAL, 2: MODE_PROGRAM}.get(raw[start - 1])
    on = rec(0x01)
    measured, setpoint, expiry = rec(0x0A), rec(0x0B), rec(0x0C)
    if on is None or setpoint is None:
        return None

    def tenth(value: int | None) -> float | None:
        return None if value is None else value / 10

    return RadiatorState(
        mode=mode,
        is_on=bool(on),
        current_temp=tenth(measured),
        target_temp=tenth(setpoint),
        expiry=None if expiry in (None, 0, 0xFFFFFFFF) else datetime.fromtimestamp(expiry, tz=UTC),
        presets={"antifreeze": tenth(rec(0x02)), "eco": tenth(rec(0x03)), "comfort": tenth(rec(0x05))},
    )
