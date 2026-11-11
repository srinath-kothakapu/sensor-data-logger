# Sensor Data Logger and Plotter

This repository is a small Python toolkit for collecting, plotting, and inspecting temperature and relative-humidity readings from a microcontroller. It can read a text stream over a serial (UART) port or use a built-in simulator, write timestamped CSV logs, display live charts, plot a saved run, and calculate basic statistics for both channels.

The simulator follows the same input interface as a serial device, so the logger, plotter, and analysis commands work with either source. That makes it possible to explore the complete workflow without connecting a board, while keeping hardware-specific input isolated in one source module.

## What the tools do

| Tool | Purpose |
|---|---|
| `src/sources.py` | Produces a stream of temperature/humidity tuples from a serial port or the software simulator; ignores malformed serial lines |
| `src/logger.py` | Adds an ISO timestamp and elapsed seconds, then records each sample in a CSV file |
| `src/plot.py` | Displays a live plot or plots saved temperature and humidity channels; can save a static image |
| `src/analyze.py` | Reports sample rate, mean, minimum, maximum, peak-to-peak range, detrended noise, and linear drift |
| `firmware/arduino_sensor_uart/` | Example DHT11 Arduino sketch that sends the UART format expected by the Python tools |
| `tests/` | Tests for serial-line parsing, statistical calculations, and logging behavior |

## Data flow

```text
DHT11 + microcontroller ── UART text line ─┐
                                           ├──> sources.py ──> logger.py ──> CSV
Software simulator ────────────────────────┘                       │
                                                                   ├──> analyze.py statistics
                                                                   └──> plot.py visualization
```

A device sends one reading per line in the format:

```text
<temperature_c>,<humidity_pct>
```

For example:

```text
23.45,41.2
```

The serial source discards empty, partial, or non-numeric lines, which can occur while a serial connection is opening. The logger timestamps accepted readings on the computer and adds elapsed time from the beginning of that logging run.

## Requirements and installation

- Python 3.9 or newer
- pip
- A webcam is not required; this project uses either a serial device or simulator
- For physical hardware: a board that emits the expected UART text format and a USB-to-serial connection

Create a virtual environment and install the dependencies:

```bash
git clone https://github.com/srinath-kothakapu/sensor-data-logger.git
cd sensor-data-logger
python -m venv .venv
```

Activate it and install the requirements:

```bash
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

python -m pip install -r requirements.txt
```

The requirements cover plotting, numeric analysis, serial-port access, and tests. The simulator can be used without opening a serial port; the hardware source uses `pyserial` when you request it.

## Try the complete workflow without hardware

Generate a 30-second simulator log, analyze it, and save a plot:

```bash
python src/logger.py --simulate --duration 30 --out data/demo.csv
python src/analyze.py data/demo.csv
python src/plot.py --csv data/demo.csv --save docs/demo-plot.png
```

You can also visualize simulated values as they arrive:

```bash
python src/plot.py --live --simulate
```

Close the Matplotlib window to stop the live plot. The simulator is generated data, not a sensor measurement or a test of the hardware path.

## Collect data from a microcontroller

The included example firmware is in [`firmware/arduino_sensor_uart/arduino_sensor_uart.ino`](firmware/arduino_sensor_uart/arduino_sensor_uart.ino). It uses a DHT11 and emits temperature and humidity values once per second at 115200 baud. Install the Adafruit DHT sensor library, select your Arduino board and port, then upload the sketch.

Find the serial port shown by your operating system or Arduino IDE. Examples include `COM3` on Windows and `/dev/ttyUSB0` on Linux. Use the same baud rate as the firmware:

```bash
python src/logger.py --port COM3 --baud 115200 --duration 120 --out data/run1.csv
python src/plot.py --live --port COM3 --baud 115200
python src/analyze.py data/run1.csv
```

The logger writes a new output file for the run, creates its parent directory when necessary, and prints how many samples it wrote. Only one program can normally own a serial port at a time: close the Arduino serial monitor before starting the logger or live plot.

To use a different microcontroller, make it send the same two comma-separated numeric values followed by a line break. The tools do not require a particular microcontroller as long as its serial output and baud rate match.

## Recorded CSV format

The logger writes the following header and values:

| Column | Meaning |
|---|---|
| `time_iso` | Computer local date/time when the row was recorded, in ISO format with milliseconds |
| `elapsed_s` | Seconds since the logger began capturing this run |
| `temperature_c` | Temperature value received from the sensor or simulator, in C |
| `humidity_pct` | Relative-humidity value received from the source, in percent |

Example:

```csv
time_iso,elapsed_s,temperature_c,humidity_pct
2026-03-20T10:00:00.125,0.0,23.45,41.2
2026-03-20T10:00:01.126,1.001,23.51,41.4
```

The live plot uses a bounded recent sample window and labels its horizontal axis by sample number. The saved-file plot uses the recorded elapsed seconds on the horizontal axis.

## Understanding the analysis

For each channel, `src/analyze.py` reports:

- **Sample rate:** `(number of samples - 1) / elapsed time between first and last samples`, in Hz.
- **Mean:** arithmetic average of the recorded values.
- **Minimum and maximum:** lowest and highest values in the run.
- **Peak-to-peak:** the difference between the maximum and minimum.
- **Noise standard deviation:** the standard deviation of residuals after fitting and subtracting a straight-line trend. Slow linear drift is therefore reported separately rather than counted as noise.
- **Drift per minute:** the fitted line's slope converted to change per minute.

These are simple descriptive statistics, not a calibration procedure, uncertainty budget, or guarantee that a sensor is accurate. The tool assumes a usable CSV with numeric `elapsed_s`, `temperature_c`, and `humidity_pct` fields and enough samples to fit a line.

## Example output

The committed sample plot and these example numbers are from the existing software-simulator run; they are not readings from real hardware.

![Example temperature and humidity plot from the simulator](docs/example_plot.png)

```text
Samples: 398   Duration: 20.0 s   Rate: 19.87 Hz

Temperature
  mean          22.387 C
  peak-to-peak  0.774 C
  noise (std)   0.0765 C
  drift         +1.7145 C/min
```

A new simulator run can produce different values and sample counts. The example is included to show the kinds of output the tools produce, not to promise a fixed result.

## Tests

Run the test suite from the repository root:

```bash
python -m pytest
```

Tests cover the core parsing, logger, and analysis behavior. They do not replace testing the serial connection, the board firmware, sensor accuracy, or the end-to-end hardware setup.

## Repository structure

```text
src/
  sources.py                 Serial and simulated reading sources
  logger.py                  Timed capture to timestamped CSV
  plot.py                    Live plotting and saved-CSV plotting
  analyze.py                 Sampling and per-channel statistics
firmware/arduino_sensor_uart/
  arduino_sensor_uart.ino    DHT11 UART example for Arduino
data/
  .gitkeep                  Keeps the output directory in Git; local captures belong here
docs/
  example_plot.png           Example visualization from the simulator
tests/
  test_sensor_logger.py      Parsing, logging and analysis tests
requirements.txt             Python dependencies
```

Generated capture files should be kept separate from the committed example. Sensor data can contain information about an environment or test setup, so review a log before sharing it.

## Project status and limitations

- The simulator workflow and the included test suite provide a way to exercise the software without a board.
- Real-hardware test results are not documented in this repository yet. Add the board, sensor, serial adapter, port, baud rate, and observations after you perform a real capture.
- The example firmware uses a DHT11 and sends only temperature and humidity; support for additional sensors or channels is not implemented.
- Computer timestamps are added by the logger. The source protocol does not carry a sensor-side timestamp, so serial buffering and host scheduling can affect recorded time.
- Noise and drift are calculated with a straight-line model. Non-linear trends, dropped samples, sensor warm-up, and calibration errors need separate analysis.
- The live chart is for interactive inspection, not long-term storage. Use the logger to persist data.

## Possible extensions

- Add an optional device timestamp and document clock synchronization.
- Support additional measurements such as pressure, illumination, or an ADC channel.
- Add explicit missing-sample, parsing-error, and sensor-warm-up reports.
- Export plots and summaries with run metadata such as sensor model and calibration date.
- Add configurable framing, checksum, or a more robust serial protocol for noisy links.

## License

This project is distributed under the MIT License. See [`LICENSE`](LICENSE).