import itertools
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from analyze import analyze_channel, sample_rate_hz  # noqa: E402
from logger import HEADER, log  # noqa: E402
from sources import parse_line  # noqa: E402


def test_parse_valid_line():
    assert parse_line("23.45,41.2\n") == (23.45, 41.2)


def test_parse_rejects_bad_lines():
    assert parse_line("") is None
    assert parse_line("abc,def") is None
    assert parse_line("23.4") is None
    assert parse_line("1,2,3") is None


def test_analyze_detects_drift_and_noise():
    t = np.arange(0, 600, 1.0)  # 10 minutes at 1 Hz
    values = 20.0 + 0.02 * t  # +0.02 per second = +1.2 per minute
    r = analyze_channel(t, values)
    assert abs(r["drift_per_min"] - 1.2) < 1e-6
    assert r["noise_std"] < 1e-6


def test_sample_rate():
    assert abs(sample_rate_hz([0, 0.5, 1.0, 1.5, 2.0]) - 2.0) < 1e-9


def test_logger_writes_csv(tmp_path):
    out = tmp_path / "log.csv"
    source = itertools.cycle([(21.0, 40.0)])
    n = log(source, out, duration_s=0.0)  # stops at the first sample
    assert n == 0
    assert out.read_text().splitlines()[0] == ",".join(HEADER)
