import pytest

from pvvr.engine.snapshot import (SnapshotSpec, pv_available, spec_at_hour,
                                  spec_manual)
from pvvr.engine.simulation import run_day, run_hour
from pvvr.model import curves_io
from pvvr.model import schema as sch
from pvvr.model.presets import PRESETS


def _single():
    return sch.project_from_dict(PRESETS["single_phase"]())


def _ieee33():
    return sch.project_from_dict(PRESETS["ieee33"]())


# ---------------- 断面生成 ----------------

def test_spec_at_hour_from_curves():
    p = _single()
    noon = spec_at_hour(p, 12)
    night = spec_at_hour(p, 0)
    assert noon.pv_factor == 1.0          # 光伏曲线峰值=1 在正午
    assert night.pv_factor == 0.0         # 夜间光伏为 0
    assert 0 < night.load_scale < noon.load_scale


def test_spec_at_hour_bounds():
    p = _single()
    with pytest.raises(ValueError):
        spec_at_hour(p, 24)


def test_spec_manual_negative_rejected():
    with pytest.raises(ValueError):
        spec_manual(load_scale=-0.1)


def test_pv_available_night_zero():
    """夜间断面光伏可用出力为 0（FR-2 可用出力语义）。"""
    p = _single()
    av = pv_available(p, spec_at_hour(p, 0))
    assert av == {"PV1": 0.0, "PV2": 0.0}
    noon = pv_available(p, spec_at_hour(p, 12))
    assert noon == {"PV1": 250.0, "PV2": 200.0}


def test_no_curves_defaults_rated():
    p = _ieee33()
    p.curves = None
    spec = spec_at_hour(p, 5)
    assert spec.load_scale == 1.0 and spec.pv_factor == 1.0


# ---------------- 24h 仿真 ----------------

def test_run_day_24_records_and_pv_shape():
    day = run_day(_single())
    assert day.hour_series() == list(range(24))
    noon_v = day.max_v_series()[12]
    night_v = day.max_v_series()[0]
    assert noon_v > night_v > 0          # 正午光伏抬压 > 夜间
    assert day.max_v_series()[0] < 1.001  # 夜间无光伏不越上限


def test_run_hour_explicit_pv_kw():
    p = _single()
    full = run_hour(p, hour=12)
    zero = run_hour(p, hour=12, pv_kw={"PV1": 0.0, "PV2": 0.0})
    assert full.result.max_v()[0] > zero.result.max_v()[0]
    assert full.pv_kw == {"PV1": 250.0, "PV2": 200.0}


def test_run_hour_manual_snapshot():
    p = _ieee33()
    rec = run_hour(p, load_scale=0.5)
    assert rec.hour is None and rec.spec.load_scale == 0.5


# ---------------- 曲线 CSV ----------------

def test_curve_csv_roundtrip(tmp_path):
    vals = [h / 23.0 for h in range(24)]
    f = tmp_path / "c.csv"
    curves_io.write_curve_csv(vals, f)
    got = curves_io.read_curve_csv(f)
    assert got == pytest.approx(vals, abs=1e-6)   # 文件按 %.6f 落盘


def test_curve_csv_errors(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("hour,value\n0,0.1\n1,0.2\n", encoding="utf-8")
    with pytest.raises(curves_io.CurveCsvError) as ei:
        curves_io.read_curve_csv(f)
    assert "缺少小时" in str(ei.value)
    f2 = tmp_path / "bad2.csv"
    f2.write_text("hour,value\n0,0.1\n0,0.2\n" +
                  "\n".join("%d,0.5" % h for h in range(1, 24)) + "\n",
                  encoding="utf-8")
    with pytest.raises(curves_io.CurveCsvError) as ei2:
        curves_io.read_curve_csv(f2)
    assert "重复" in str(ei2.value)


def test_curve_csv_unordered_rows_accepted(tmp_path):
    vals = [h / 23.0 for h in range(24)]
    lines = ["hour,value"] + ["%d,%.6f" % (23 - h, vals[23 - h]) for h in range(24)]
    f = tmp_path / "shuffle.csv"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert curves_io.read_curve_csv(f) == pytest.approx(vals, abs=1e-6)


# ---------------- 绘图 ----------------

def test_voltage_trajectory_png(tmp_path):
    from pvvr.engine.plot import plot_voltage_trajectory
    day = run_day(_single())
    out = plot_voltage_trajectory(day, tmp_path / "traj.png", 0.95, 1.05)
    assert out.exists() and out.stat().st_size > 10_000   # 300 DPI 非空图
