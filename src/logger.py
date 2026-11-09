"""Log sensor readings from a serial port (or the simulator) to a CSV file.

Examples:
    python src/logger.py --simulate --duration 30 --out data/demo.csv
    python src/logger.py --port COM3 --baud 115200 --out data/run1.csv
"""

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

from sources import serial_source, simulated_source

HEADER = ["time_iso", "elapsed_s", "temperature_c", "humidity_pct"]


def log(source, out_path: Path, duration_s: float) -> int:
    """Write readings from ``source`` to ``out_path`` for ``duration_s`` seconds.

    Returns the number of samples written.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    count = 0
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        for temperature, humidity in source:
            elapsed = time.time() - start
            if elapsed > duration_s:
                break
            writer.writerow([datetime.now().isoformat(timespec="milliseconds"),
                             round(elapsed, 3), temperature, humidity])
            f.flush()
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Sensor data logger")
    parser.add_argument("--port", help="serial port, for example COM3 or /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--simulate", action="store_true", help="use simulated data instead of hardware")
    parser.add_argument("--rate", type=float, default=5.0, help="simulator samples per second")
    parser.add_argument("--duration", type=float, default=60.0, help="logging time in seconds")
    parser.add_argument("--out", default="data/log.csv")
    args = parser.parse_args()

    if args.simulate:
        source = simulated_source(args.rate)
    elif args.port:
        source = serial_source(args.port, args.baud)
    else:
        parser.error("give --port <port> or use --simulate")

    n = log(source, Path(args.out), args.duration)
    print(f"Wrote {n} samples to {args.out}")


if __name__ == "__main__":
    main()
