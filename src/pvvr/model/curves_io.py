"""统一曲线 CSV 读写（spec FR-2：两列 hour, value，UTF-8，24 行）。"""

import csv
from pathlib import Path
from typing import List


class CurveCsvError(Exception):
    """曲线 CSV 不合法；message 为中文定位报错。"""


def read_curve_csv(path: Path) -> List[float]:
    rows: dict = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            raise CurveCsvError("曲线 CSV 为空（应有表头 hour,value 与 24 行数据）")
        if len(header) != 2 or header[0].strip().lower() != "hour":
            raise CurveCsvError("表头应为两列 hour,value，实际 %r" % header)
        for lineno, row in enumerate(reader, start=2):
            if not row or all(not c.strip() for c in row):
                continue
            if len(row) != 2:
                raise CurveCsvError("第 %d 行应为两列，实际 %d 列" % (lineno, len(row)))
            try:
                hour = int(row[0].strip())
                value = float(row[1].strip())
            except ValueError:
                raise CurveCsvError("第 %d 行数值无法解析：%r" % (lineno, row))
            if not 0 <= hour <= 23:
                raise CurveCsvError("第 %d 行小时 %d 超出 0–23" % (lineno, hour))
            if hour in rows:
                raise CurveCsvError("小时 %d 重复（第 %d 行）" % (hour, lineno))
            if value < 0:
                raise CurveCsvError("第 %d 行曲线值 %g 为负" % (lineno, value))
            rows[hour] = value
    missing = sorted(set(range(24)) - set(rows))
    if missing:
        raise CurveCsvError("缺少小时 %s（须 24 个整点齐全）" %
                            "、".join(str(h) for h in missing))
    return [rows[h] for h in range(24)]


def write_curve_csv(values: List[float], path: Path) -> Path:
    if len(values) != 24:
        raise CurveCsvError("曲线须为 24 个值，实际 %d 个" % len(values))
    path = Path(path)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["hour", "value"])
        for h, v in enumerate(values):
            w.writerow([h, "%.6f" % v])
    return path
