"""Plot sensor data: live from a source, or from a saved CSV file.

Examples:
    python src/plot.py --csv data/demo.csv --save docs/example_plot.png
    python src/plot.py --live --simulate
    python src/plot.py --live --port COM3
"""

import argparse
import csv
from collections import deque

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

from sources import SensorTimeout, serial_source, simulated_source


def load_csv(path):
    """Return (elapsed_s, temperature_c, humidity_pct) lists from a log file."""
    t, temp, hum = [], [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            t.append(float(row["elapsed_s"]))
            temp.append(float(row["temperature_c"]))
            hum.append(float(row["humidity_pct"]))
    return t, temp, hum


def make_axes(title):
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(9, 5))
    ax1.set_ylabel("Temperature (°C)")
    ax2.set_ylabel("Humidity (%)")
    ax2.set_xlabel("Time (s)")
    ax1.set_title(title)
    ax1.grid(True)
    ax2.grid(True)
    return fig, ax1, ax2


def plot_csv(path, save=None, title="Sensor log"):
    t, temp, hum = load_csv(path)
    fig, ax1, ax2 = make_axes(title)
    ax1.plot(t, temp)
    ax2.plot(t, hum, color="tab:orange")
    fig.tight_layout()
    if save:
        fig.savefig(save, dpi=130)
        print(f"Saved {save}")
    else:
        plt.show()


def plot_live(source, window=200):
    t_buf, temp_buf, hum_buf = (deque(maxlen=window) for _ in range(3))
    fig, ax1, ax2 = make_axes("Live sensor data")
    (line1,) = ax1.plot([], [])
    (line2,) = ax2.plot([], [], color="tab:orange")
    state = {"n": 0}

    def update(_frame):
        try:
            temperature, humidity = next(source)
        except SensorTimeout as err:
            print(f"ERROR: {err}")
            plt.close(fig)
            return line1, line2
        state["n"] += 1
        t_buf.append(state["n"])
        temp_buf.append(temperature)
        hum_buf.append(humidity)
        line1.set_data(t_buf, temp_buf)
        line2.set_data(t_buf, hum_buf)
        for ax in (ax1, ax2):
            ax.relim()
            ax.autoscale_view()
        ax2.set_xlabel("Sample number")
        return line1, line2

    _anim = FuncAnimation(fig, update, interval=100, cache_frame_data=False)
    plt.show()


def main():
    parser = argparse.ArgumentParser(description="Sensor data plotter")
    parser.add_argument("--csv", help="plot a saved CSV log")
    parser.add_argument("--save", help="save the CSV plot to this image file")
    parser.add_argument("--title", default="Sensor log")
    parser.add_argument("--live", action="store_true", help="live plot")
    parser.add_argument("--port")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--allow-legacy", action="store_true",
                        help="also accept old unframed 'temp,hum' lines without a CRC")
    args = parser.parse_args()

    if args.csv:
        plot_csv(args.csv, args.save, args.title)
    elif args.live:
        if args.simulate:
            source = simulated_source()
        elif args.port:
            source = serial_source(args.port, args.baud, require_crc=not args.allow_legacy)
        else:
            parser.error("live plot needs --port <port> or --simulate")
        plot_live(source)
    else:
        parser.error("use --csv <file> or --live")


if __name__ == "__main__":
    main()
