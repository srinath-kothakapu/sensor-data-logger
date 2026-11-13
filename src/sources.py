"""Data sources for the sensor logger.

A source is a generator that yields one reading at a time as a tuple
``(temperature_c, humidity_pct)``. The rest of the program does not care
whether the readings come from a real microcontroller or from the simulator,
so the same logger, plotter and analysis code works for both.
"""

import math
import random
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator, Optional, Tuple

Reading = Tuple[float, float]


# ---------------------------------------------------------------------------
# Frame format and integrity checks
#
# The microcontroller sends one frame per line:
#
#     $<temperature_c>,<humidity_pct>*<CRC>\n        e.g.  $23.45,41.2*5B
#
# <CRC> is a CRC-8 (polynomial 0x07, initial value 0) of the payload text
# between "$" and "*", written as two hex digits. Anything that does not match
# this format exactly is rejected and counted, never logged.
# ---------------------------------------------------------------------------

MAX_LINE_CHARS = 64          # a valid frame is well under 40 characters
TEMP_RANGE_C = (-40.0, 85.0)     # plausible range for common digital sensors
HUMIDITY_RANGE_PCT = (0.0, 100.0)
DEFAULT_WATCHDOG_S = 5.0     # give up if no valid frame arrives for this long

_NUMBER = r"-?\d{1,3}(?:\.\d{1,3})?"   # plain decimals only: no nan, inf, 1e9, hex
_PAYLOAD_RE = re.compile(rf"^({_NUMBER}),({_NUMBER})$")
_FRAME_RE = re.compile(r"^\$([^$*]*)\*([0-9A-Fa-f]{2})$")


class FrameError(ValueError):
    """A received line was rejected. ``reason`` says why."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


class SensorTimeout(RuntimeError):
    """No valid frame arrived within the watchdog time."""


@dataclass
class FrameStats:
    """Counts of accepted and rejected lines, for reporting after a run."""

    accepted: int = 0
    rejected: Counter = field(default_factory=Counter)

    @property
    def rejected_total(self) -> int:
        return sum(self.rejected.values())

    def summary(self) -> str:
        if not self.rejected:
            return f"{self.accepted} frames accepted, 0 rejected"
        detail = ", ".join(f"{k}={v}" for k, v in sorted(self.rejected.items()))
        return f"{self.accepted} frames accepted, {self.rejected_total} rejected ({detail})"


def crc8(data: bytes) -> int:
    """CRC-8, polynomial 0x07, initial value 0 (check value for b"123456789" is 0xF4)."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def make_frame(temperature_c: float, humidity_pct: float) -> str:
    """Build a frame the way the firmware does (used by tests and the simulator)."""
    payload = f"{temperature_c:.2f},{humidity_pct:.1f}"
    return f"${payload}*{crc8(payload.encode('ascii')):02X}"


def parse_frame(
    line: str,
    require_crc: bool = True,
    temp_range: Tuple[float, float] = TEMP_RANGE_C,
    humidity_range: Tuple[float, float] = HUMIDITY_RANGE_PCT,
) -> Reading:
    """Validate one received line and return ``(temperature_c, humidity_pct)``.

    Raises ``FrameError`` (with ``.reason``) if the line is not a valid frame:

    - ``too_long``     longer than ``MAX_LINE_CHARS``
    - ``malformed``    wrong structure, non-ASCII bytes, not plain decimal numbers
    - ``no_crc``       not a ``$...*CRC`` frame (e.g. a plain line) while ``require_crc`` is set
    - ``crc_mismatch`` checksum does not match the payload (corrupted in transit)
    - ``out_of_range`` value outside the allowed physical range

    With ``require_crc=False`` the old unframed ``temp,hum`` lines are accepted
    too (a frame that does carry a CRC is still checked).
    """
    if len(line) > MAX_LINE_CHARS:
        raise FrameError("too_long", f"{len(line)} characters")
    line = line.rstrip("\r\n")
    if not line.isascii() or not line.isprintable():
        raise FrameError("malformed", "non-printable or non-ASCII characters")

    if line.startswith("$"):
        m = _FRAME_RE.match(line)
        if m is None:
            raise FrameError("malformed", "bad frame structure")
        payload, crc_text = m.group(1), m.group(2)
        if crc8(payload.encode("ascii")) != int(crc_text, 16):
            raise FrameError("crc_mismatch")
    elif require_crc:
        raise FrameError("no_crc")
    else:
        payload = line

    m = _PAYLOAD_RE.match(payload)
    if m is None:
        raise FrameError("malformed", "payload is not '<temp>,<humidity>'")
    temperature, humidity = float(m.group(1)), float(m.group(2))

    if not temp_range[0] <= temperature <= temp_range[1]:
        raise FrameError("out_of_range", f"temperature {temperature}")
    if not humidity_range[0] <= humidity <= humidity_range[1]:
        raise FrameError("out_of_range", f"humidity {humidity}")
    return temperature, humidity


def parse_line(line: str, require_crc: bool = False) -> Optional[Reading]:
    """Like ``parse_frame`` but returns ``None`` instead of raising.

    Defaults to accepting legacy unframed lines (``23.45,41.2``) so existing
    callers keep working; the serial source uses the strict mode.
    """
    try:
        return parse_frame(line, require_crc=require_crc)
    except FrameError:
        return None


def readings_from_lines(
    lines: Iterable[str],
    require_crc: bool = True,
    watchdog_s: float = DEFAULT_WATCHDOG_S,
    stats: Optional[FrameStats] = None,
    clock: Callable[[], float] = time.monotonic,
) -> Iterator[Reading]:
    """Turn raw text lines into validated readings, with a watchdog.

    ``lines`` yields one string per read attempt; an empty string means the
    read timed out with no data (this is what ``pyserial`` returns). If no
    *valid* frame has been accepted for ``watchdog_s`` seconds, whether because
    the device is silent or only sending garbage, ``SensorTimeout`` is raised.
    """
    stats = stats if stats is not None else FrameStats()
    last_good = clock()
    for raw in lines:
        if raw:
            try:
                reading = parse_frame(raw, require_crc=require_crc)
            except FrameError as err:
                stats.rejected[err.reason] += 1
            else:
                stats.accepted += 1
                last_good = clock()
                yield reading
        if clock() - last_good > watchdog_s:
            raise SensorTimeout(f"no valid data for {watchdog_s:g} s ({stats.summary()})")


def serial_source(
    port: str,
    baud: int = 115200,
    require_crc: bool = True,
    watchdog_s: float = DEFAULT_WATCHDOG_S,
    stats: Optional[FrameStats] = None,
) -> Iterator[Reading]:
    """Yield validated readings from a microcontroller on a serial port.

    Raises ``SensorTimeout`` if the device stops sending valid frames.
    """
    import serial  # imported here so the simulator works without pyserial

    def lines() -> Iterator[str]:
        with serial.Serial(port, baud, timeout=1) as ser:
            ser.reset_input_buffer()
            while True:
                # size limit: a stream without line breaks cannot grow without bound
                raw = ser.read_until(b"\n", size=MAX_LINE_CHARS + 1)
                yield raw.decode("ascii", errors="replace")

    yield from readings_from_lines(lines(), require_crc, watchdog_s, stats)


def simulated_source(rate_hz: float = 5.0, seed: Optional[int] = None) -> Iterator[Reading]:
    """Yield simulated readings: a slow temperature drift plus noise.

    This is only for trying the tools without hardware. Data from this
    source is NOT a real measurement.
    """
    rng = random.Random(seed)
    start = time.time()
    period = 1.0 / rate_hz
    while True:
        t = time.time() - start
        temperature = 22.0 + 0.01 * t + 0.4 * math.sin(2 * math.pi * t / 60.0) + rng.gauss(0, 0.05)
        humidity = 45.0 - 0.005 * t + rng.gauss(0, 0.3)
        yield round(temperature, 3), round(humidity, 2)
        time.sleep(period)
