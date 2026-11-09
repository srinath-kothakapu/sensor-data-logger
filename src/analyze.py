"""Basic statistics for a logged sensor run: mean, noise, range and drift.

Example:
    python src/analyze.py data/demo.csv
"""

import argparse
import csv

import numpy as np


def analyze_channel(t, values):
    """Return summary statistics for one measurement channel.

    t      : time in seconds
    values : measured values
    Noise is the standard deviation of the residuals after removing a straight
    line (so slow drift is not counted as noise).
    """
    t = np.asarray(t, dtype=float)
    v = np.asarray(values, dtype=float)
    slope, intercept = np.polyfit(t, v, 1)
    residuals = v - (slope * t + intercept)
    return {
        "samples": int(len(v)),
        "mean": float(np.mean(v)),
        "min": float(np.min(v)),
        "max": float(np.max(v)),
        "peak_to_peak": float(np.ptp(v)),
        "noise_std": float(np.std(residuals)),
        "drift_per_min": float(slope * 60.0),
    }


def sample_rate_hz(t):
    """Average sampling rate in samples per second."""
    t = np.asarray(t, dtype=float)
    return float((len(t) - 1) / (t[-1] - t[0]))


def load(path):
    t, temp, hum = [], [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            t.append(float(row["elapsed_s"]))
            temp.append(float(row["temperature_c"]))
            hum.append(float(row["humidity_pct"]))
    return t, temp, hum


def main():
    parser = argparse.ArgumentParser(description="Analyze a sensor log")
    parser.add_argument("csv_file")
    args = parser.parse_args()

    t, temp, hum = load(args.csv_file)
    print(f"Samples: {len(t)}   Duration: {t[-1] - t[0]:.1f} s   Rate: {sample_rate_hz(t):.2f} Hz")
    for name, unit, values in (("Temperature", "°C", temp), ("Humidity", "%", hum)):
        r = analyze_channel(t, values)
        print(f"\n{name}")
        print(f"  mean          {r['mean']:.3f} {unit}")
        print(f"  min / max     {r['min']:.3f} / {r['max']:.3f} {unit}")
        print(f"  peak-to-peak  {r['peak_to_peak']:.3f} {unit}")
        print(f"  noise (std)   {r['noise_std']:.4f} {unit}")
        print(f"  drift         {r['drift_per_min']:+.4f} {unit}/min")


if __name__ == "__main__":
    main()
