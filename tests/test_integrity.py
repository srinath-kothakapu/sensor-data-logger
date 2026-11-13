"""Tests for frame integrity (CRC), input validation, range checks and the watchdog."""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from sources import (  # noqa: E402
    MAX_LINE_CHARS,
    FrameError,
    FrameStats,
    SensorTimeout,
    crc8,
    make_frame,
    parse_frame,
    parse_line,
    readings_from_lines,
)


def reason_of(line, **kwargs):
    with pytest.raises(FrameError) as info:
        parse_frame(line, **kwargs)
    return info.value.reason


# --- CRC -------------------------------------------------------------------


def test_crc8_standard_check_value():
    # published check value for CRC-8 (poly 0x07, init 0) over "123456789"
    assert crc8(b"123456789") == 0xF4


def test_valid_frame_round_trip():
    assert parse_frame(make_frame(23.45, 41.2)) == (23.45, 41.2)
    assert parse_frame(make_frame(-12.5, 0.0) + "\r\n") == (-12.5, 0.0)


def test_corrupted_payload_is_rejected():
    frame = make_frame(23.45, 41.2)
    assert reason_of(frame.replace("23.45", "23.46")) == "crc_mismatch"
    assert reason_of(frame.replace("41.2", "91.2")) == "crc_mismatch"


def test_wrong_or_damaged_crc_is_rejected():
    frame = make_frame(23.45, 41.2)
    good_crc = frame[-2:]
    other = "00" if good_crc != "00" else "01"
    assert reason_of(frame[:-2] + other) == "crc_mismatch"
    assert reason_of(frame[:-2] + "ZZ") == "malformed"
    assert reason_of(frame[:-1]) == "malformed"  # CRC cut to one digit


def test_every_single_character_change_is_detected():
    frame = make_frame(23.45, 41.2)
    body_start, body_end = 1, frame.index("*")
    for i in range(body_start, body_end):
        for ch in "0123456789,.-":
            if ch == frame[i]:
                continue
            damaged = frame[:i] + ch + frame[i + 1:]
            assert parse_line(damaged, require_crc=True) is None, damaged


def test_missing_crc_rejected_in_strict_mode_only():
    assert reason_of("23.45,41.2") == "no_crc"
    assert parse_frame("23.45,41.2", require_crc=False) == (23.45, 41.2)
    # a framed line is always checked, even in legacy mode
    assert reason_of("$23.45,41.2*00", require_crc=False) == "crc_mismatch"


# --- input validation --------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        "",  # empty
        "23.4",  # one field
        "1,2,3",  # three fields
        "nan,40",  # float() would accept these
        "40,inf",
        "-inf,40",
        "1e2,40",  # exponent
        "0x10,40",  # hex
        "23.4.5,40",
        "23,40,",
        " 23,40",  # stray whitespace
        "23 ,40",
        "abc,def",
        "٢٣,40",  # non-ASCII digits that float() would accept
        "23.4567,40",  # more decimals than the format allows
        "12345,40",  # too many digits
        "+23,40",
        ",",
    ],
)
def test_malformed_payloads_rejected(payload):
    frame = f"${payload}*{crc8(payload.encode('utf-8', 'replace')):02X}"
    assert parse_line(frame, require_crc=True) is None
    assert parse_line(payload, require_crc=False) is None


@pytest.mark.parametrize(
    "line",
    [
        "$",
        "$*",
        "$*00",
        "*00",
        "$23.45,41.2",  # no '*CRC'
        "$23.45,41.2*",
        "$$23.45,41.2*00",
        "$23.45*41.2*00",
        "$23.45,41.2*00*00",
        "$23.45,41.2*0",
        "$23.45,41.2*000",
        "23.45,41.2*BE",
        "$23.45,41.2\x00*BE",  # control character
        "$23.45,41.2*BE\x07",
        "$23.45,41.2*BÉ",
        "\x00\x01\x02",
        "\n",
    ],
)
def test_malformed_frames_rejected(line):
    assert parse_line(line, require_crc=True) is None


def test_overlong_line_rejected_before_parsing():
    assert reason_of("9" * 10_000) == "too_long"
    assert reason_of("$" + "1" * MAX_LINE_CHARS + "*00") == "too_long"


def test_parse_line_never_raises_on_garbage():
    for junk in ["", "\xff\xfe", "�" * 5, "{}", "DROP TABLE", "%s%s%s", "../../etc/passwd", "𝟏𝟐,𝟑𝟒"]:
        assert parse_line(junk) is None
        assert parse_line(junk, require_crc=True) is None


# --- range checks -------------------------------------------------------------


@pytest.mark.parametrize(
    "temp,hum",
    [(200.0, 40.0), (-90.0, 40.0), (85.5, 40.0), (23.0, 101.0), (23.0, -1.0), (999.0, 999.0)],
)
def test_out_of_range_values_rejected_even_with_valid_crc(temp, hum):
    payload = f"{temp:.2f},{hum:.1f}"
    frame = f"${payload}*{crc8(payload.encode()):02X}"
    assert reason_of(frame) == "out_of_range"


@pytest.mark.parametrize("temp,hum", [(-40.0, 0.0), (85.0, 100.0), (0.0, 50.0)])
def test_range_limits_are_inclusive(temp, hum):
    assert parse_frame(make_frame(temp, hum)) == (temp, hum)


def test_custom_range():
    frame = make_frame(60.0, 40.0)
    assert reason_of(frame, temp_range=(0.0, 50.0)) == "out_of_range"
    assert parse_frame(frame, temp_range=(0.0, 70.0)) == (60.0, 40.0)


# --- timeout / watchdog --------------------------------------------------------


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def feed(clock, items, step=1.0):
    """Yield ``items`` as read results, advancing the fake clock ``step`` s per read."""
    for item in items:
        clock.now += step
        yield item


def test_silent_device_triggers_watchdog():
    clock = FakeClock()
    lines = feed(clock, [make_frame(21.0, 40.0)] + [""] * 20)
    stream = readings_from_lines(lines, watchdog_s=5.0, clock=clock)
    assert next(stream) == (21.0, 40.0)
    with pytest.raises(SensorTimeout):
        next(stream)
    assert clock.now == 7.0  # 1 s (good frame) + 6 s of silence: first time > 5 s


def test_garbage_only_stream_also_triggers_watchdog():
    clock = FakeClock()
    stats = FrameStats()
    lines = feed(clock, ["abc", "$1,2*00", "23.4,41"] * 10)
    with pytest.raises(SensorTimeout):
        list(readings_from_lines(lines, watchdog_s=5.0, stats=stats, clock=clock))
    assert stats.accepted == 0
    assert stats.rejected_total >= 5


def test_valid_frames_keep_the_watchdog_quiet():
    clock = FakeClock()
    frames = [make_frame(20.0 + i * 0.1, 40.0) for i in range(30)]
    got = list(readings_from_lines(feed(clock, frames, step=2.0), watchdog_s=5.0, clock=clock))
    assert len(got) == 30


def test_bad_frames_between_good_ones_are_dropped_and_counted():
    clock = FakeClock()
    stats = FrameStats()
    lines = [
        make_frame(21.0, 40.0),
        "garbage",  # not a frame at all
        make_frame(21.0, 40.0).replace("21.00", "22.00"),  # corrupted -> crc_mismatch
        make_frame(150.0, 40.0),  # valid CRC, out of range
        "23.4,41",  # legacy line in strict mode
        make_frame(22.0, 41.0),
    ]
    got = list(readings_from_lines(feed(clock, lines, step=0.5), watchdog_s=5.0, stats=stats, clock=clock))
    assert got == [(21.0, 40.0), (22.0, 41.0)]
    assert stats.accepted == 2
    assert dict(stats.rejected) == {"no_crc": 2, "crc_mismatch": 1, "out_of_range": 1}
    assert "2 frames accepted, 4 rejected" in stats.summary()


# --- firmware stays in sync with the Python CRC ------------------------------


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not available")
def test_firmware_crc8_matches_python(tmp_path):
    ino = (ROOT / "firmware" / "arduino_sensor_uart" / "arduino_sensor_uart.ino").read_text()
    func = re.search(r"uint8_t crc8\(const char \*data\) \{.*?\n\}\n", ino, re.S)
    assert func, "crc8 function not found in firmware"

    vectors = ["123456789", "23.45,41.2", "-12.50,0.0", "85.00,100.0", ""]
    main = "#include <stdio.h>\n#include <stdint.h>\n" + func.group(0) + (
        "int main(void) {\n"
        "  const char *v[] = {" + ", ".join(f'"{x}"' for x in vectors) + "};\n"
        f"  for (int i = 0; i < {len(vectors)}; i++) printf(\"%02X\\n\", crc8(v[i]));\n"
        "  return 0;\n}\n"
    )
    src = tmp_path / "crc.c"
    src.write_text(main)
    exe = tmp_path / "crc"
    subprocess.run(["gcc", "-Wall", "-Werror", "-o", str(exe), str(src)], check=True)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.split()
    assert out == [f"{crc8(v.encode()):02X}" for v in vectors]
