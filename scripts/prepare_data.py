"""
直播复盘日报 — 数据准备脚本
输入：原始运营数据（dict 或 CSV/Excel）
输出：facts JSON（原始值 + 派生指标 + 环比 + 预警状态）

这个脚本只做确定性计算，不生成报告文案。报告由 LLM 基于 facts 生成。
"""
import json
import sys
import os
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_thresholds():
    with open(CONFIG_DIR / "thresholds.json", "r", encoding="utf-8") as f:
        return json.load(f)


FIELD_ALIASES = {
    "直播时长_小时": "直播时长",
    "整体GMV_含券": "整体GMV",
    "退后GMV_含券": "退后GMV",
    "整体GMV(含券)": "整体GMV",
    "整体GMV（含券）": "整体GMV",
    "退后GMV(含券)": "退后GMV",
    "退后GMV（含券）": "退后GMV",
    "直播时长（小时）": "直播时长",
    "直播时长(小时)": "直播时长",
}


def normalize_fields(raw):
    """将飞书表/各种格式的列名统一为标准字段名"""
    normalized = {}
    for k, v in raw.items():
        key = FIELD_ALIASES.get(k.strip(), k.strip())
        if isinstance(v, str):
            v = v.strip().replace(",", "").replace("，", "")
            if v.endswith("%"):
                try:
                    v = float(v[:-1]) / 100
                except ValueError:
                    pass
            else:
                try:
                    v = float(v) if "." in v else int(v)
                except (ValueError, TypeError):
                    pass
        normalized[key] = v
    return normalized


def safe_div(a, b, default=None):
    if b is None or b == 0:
        return default
    return a / b


def compute_derived(raw):
    """从运营输入的原始字段计算派生指标"""
    gmv = raw.get("整体GMV", 0)
    refund = raw.get("退款金额", 0)
    ad_cost = raw.get("广告消耗", 0)
    exposure = raw.get("曝光次数", 0)
    pv = raw.get("直播间PV", 0)
    clicks = raw.get("商品点击次数", 0)
    orders = raw.get("成交订单数", 0)
    hours = raw.get("直播时长", 0)

    退后GMV = gmv - refund

    return {
        "退后GMV": 退后GMV,
        "综合ROI": safe_div(gmv, ad_cost),
        "退后ROI": safe_div(退后GMV, ad_cost),
        "退款率": safe_div(refund, gmv),
        "CPM": safe_div(ad_cost, exposure, 0) * 1000 if exposure else None,
        "千次曝光成交": safe_div(gmv, exposure, 0) * 1000 if exposure else None,
        "曝光观看率": safe_div(pv, exposure),
        "商品观看点击率": safe_div(clicks, pv),
        "点击成交率": safe_div(orders, clicks),
        "观看成交率": safe_div(orders, pv),
        "GPM": safe_div(gmv, pv, 0) * 1000 if pv else None,
        "小时产出": safe_div(退后GMV, hours),
    }


def compute_change(today_val, yesterday_val):
    """计算环比变化"""
    if today_val is None or yesterday_val is None or yesterday_val == 0:
        return None
    return (today_val - yesterday_val) / yesterday_val


def compute_avg(history_values):
    """计算历史均值"""
    valid = [v for v in history_values if v is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)


def check_alert(name, value, thresholds):
    """判断预警状态：正常/黄色预警/红色预警"""
    if value is None:
        return {"status": "无法计算", "reason": "数据缺失"}

    cfg = thresholds.get(name)
    if not cfg:
        return {"status": "正常", "reason": "无阈值配置"}

    lo, hi = cfg.get("normal", [None, None])

    if cfg.get("red_below") is not None and value < cfg["red_below"]:
        return {"status": "红色预警", "reason": f"{value} < 红线 {cfg['red_below']}"}
    if cfg.get("red_above") is not None and value > cfg["red_above"]:
        return {"status": "红色预警", "reason": f"{value} > 红线 {cfg['red_above']}"}
    if cfg.get("yellow_below") is not None and value < cfg["yellow_below"]:
        return {"status": "黄色预警", "reason": f"{value} < 黄线 {cfg['yellow_below']}"}
    if cfg.get("yellow_above") is not None and value > cfg["yellow_above"]:
        return {"status": "黄色预警", "reason": f"{value} > 黄线 {cfg['yellow_above']}"}

    if lo is not None and hi is not None and lo <= value <= hi:
        return {"status": "正常", "reason": f"在正常区间 [{lo}, {hi}]"}

    return {"status": "正常", "reason": ""}


def prepare_facts(today_raw, yesterday_raw=None, history_raws=None):
    """
    主入口：接收原始数据，输出完整 facts JSON。

    参数：
        today_raw: dict, 今日原始数据
        yesterday_raw: dict, 昨日原始数据（可选）
        history_raws: list[dict], 近7日原始数据（可选）

    返回：
        dict, 结构化的 facts JSON
    """
    thresholds = load_thresholds()

    today_raw = normalize_fields(today_raw)
    if yesterday_raw:
        yesterday_raw = normalize_fields(yesterday_raw)
    if history_raws:
        history_raws = [normalize_fields(r) for r in history_raws]

    today_derived = compute_derived(today_raw)

    yesterday_derived = compute_derived(yesterday_raw) if yesterday_raw else {}

    history_derived_list = [compute_derived(r) for r in history_raws] if history_raws else []

    all_metrics = list(today_derived.keys())
    metrics_report = {}

    for metric in all_metrics:
        today_val = today_derived[metric]

        yesterday_val = yesterday_derived.get(metric)
        change = compute_change(today_val, yesterday_val)

        history_vals = [d.get(metric) for d in history_derived_list]
        avg_7d = compute_avg(history_vals)
        change_vs_avg = compute_change(today_val, avg_7d)

        alert = check_alert(metric, today_val, thresholds)

        metrics_report[metric] = {
            "value": today_val,
            "yesterday": yesterday_val,
            "change_vs_yesterday": change,
            "avg_7d": avg_7d,
            "change_vs_avg_7d": change_vs_avg,
            "history_sample_count": len([v for v in history_vals if v is not None]),
            "alert": alert,
        }

    facts = {
        "日期": today_raw.get("日期"),
        "直播间": today_raw.get("直播间"),
        "直播时长": today_raw.get("直播时长"),
        "主推商品": today_raw.get("主推商品", ""),
        "异常备注": today_raw.get("异常备注", ""),
        "原始数据": {
            "整体GMV": today_raw.get("整体GMV"),
            "退款金额": today_raw.get("退款金额"),
            "广告消耗": today_raw.get("广告消耗"),
            "曝光次数": today_raw.get("曝光次数"),
            "直播间PV": today_raw.get("直播间PV"),
            "商品点击次数": today_raw.get("商品点击次数"),
            "成交订单数": today_raw.get("成交订单数"),
            "成交人数": today_raw.get("成交人数"),
        },
        "指标分析": metrics_report,
        "数据完整度": {
            "有昨日数据": yesterday_raw is not None,
            "历史天数": len(history_raws) if history_raws else 0,
            "历史样本充足": len(history_raws) >= 7 if history_raws else False,
        },
    }

    return facts


def read_csv(filepath):
    """读取 CSV 文件，返回 list[dict]"""
    import csv
    rows = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            parsed = {}
            for k, v in row.items():
                k = k.strip()
                try:
                    parsed[k] = float(v) if "." in v else int(v)
                except (ValueError, TypeError):
                    parsed[k] = v
            rows.append(parsed)
    return rows


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    if len(sys.argv) < 2:
        print("用法: python prepare_data.py <today.csv> [yesterday.csv] [history.csv]")
        print("输出: facts JSON 到 stdout")
        sys.exit(1)

    today_data = read_csv(sys.argv[1])[0]

    yesterday_data = None
    if len(sys.argv) >= 3:
        rows = read_csv(sys.argv[2])
        if rows:
            yesterday_data = rows[0]

    history_data = None
    if len(sys.argv) >= 4:
        history_data = read_csv(sys.argv[3])

    facts = prepare_facts(today_data, yesterday_data, history_data)
    print(json.dumps(facts, ensure_ascii=False, indent=2))
