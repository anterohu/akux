"""CAN-signaalien bittitason purku ja koodaus (Intel / little endian, kuten DBC:n @1)."""


def get_bits(data: bytes, start: int, length: int, signed: bool = False) -> int:
    """Palauttaa signaalin raaka-arvon. start = DBC:n aloitusbitti (Intel)."""
    value = int.from_bytes(bytes(data).ljust(8, b"\x00"), "little")
    raw = (value >> start) & ((1 << length) - 1)
    if signed and raw & (1 << (length - 1)):
        raw -= 1 << length
    return raw


def put_bits(buf: bytearray, start: int, length: int, raw: int) -> None:
    """Kirjoittaa raaka-arvon puskuriin (simulaattoria ja testejä varten)."""
    raw &= (1 << length) - 1
    value = int.from_bytes(bytes(buf).ljust(8, b"\x00"), "little")
    mask = ((1 << length) - 1) << start
    value = (value & ~mask) | (raw << start)
    buf[:] = value.to_bytes(8, "little")[: len(buf)]


def signal(data: bytes, start: int, length: int, factor: float = 1.0,
           offset: float = 0.0, signed: bool = False) -> float:
    return get_bits(data, start, length, signed) * factor + offset


def encode(buf: bytearray, start: int, length: int, value: float,
           factor: float = 1.0, offset: float = 0.0) -> None:
    put_bits(buf, start, length, int(round((value - offset) / factor)))
