"""Data sources for the sensor logger.

A source is a generator that yields one reading at a time as a tuple
``(temperature_c, humidity_pct)``. The rest of the program does not care
whether the readings come from a real microcontroller or from the simulator,
so the same logger, plotter and analysis code works for both.
"""

import math
import random
import time
from typing import Iterator, Optional, Tuple

Reading = Tuple[float, float]


def parse_line(line: str) -> Optional[Reading]:
    """Parse one text line sent by the microcontroller.

    Expected format: ``<temperature_c>,<humidity_pct>`` for example ``23.45,41.2``.
    Returns ``None`` for lines that are empty, incomplete or not numbers
    (this happens when the serial connection starts in the middle of a line).
    """
    parts = line.strip().split(",")
    if len(parts) != 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


def serial_source(port: str, baud: int = 115200) -> Iterator[Reading]:
    """Yield readings from a microcontroller connected on a serial port."""
    import serial  # imported here so the simulator works without pyserial

    with serial.Serial(port, baud, timeout=2) as ser:
        ser.reset_input_buffer()
        while True:
            raw = ser.readline().decode("utf-8", errors="ignore")
            reading = parse_line(raw)
            if reading is not None:
                yield reading


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
