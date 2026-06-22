"""
飞书交叉表数据提取脚本
输入：lark-cli sheets +csv-get 的标注格式输出（[row=X]前缀的CSV）
输出：today.json / yesterday.json / week.json，格式与 prepare_data.py 兼容

用法：
  python extract_feishu_pivot.py --raw <csv文件或直接粘贴> --date "6月20日" [--prev-date "6月19日"] [--week-start "6月13日"] [--output-dir <目录>]

也支持直接传入标注CSV字符串（从lark-cli输出复制粘贴）。

字段名映射参照 config/input_spec.json，自动将飞书表指标名映射为 prepare_data.py 的标准字段名。

最后更新：2026-06-22
用途：直播复盘日报 Skill 的飞书数据预处理
"""
import csv
import io
import json
import re
import sys
import argparse
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "config"

# 飞书表指标名 → prepare_data.py 标准字段名 映射
FIELD_MAP = {
    "直播时长": "直播时长",
    "整体GMV（含券）": "整体GMV",
    "整体GMV(含券)": "整体GMV",
    "整体GMV": "整体GMV",
    "整体GMV（不含券）": "整体GMV_不含券",
    "退后GMV（含券）": "退后GMV",
    "退后GMV(含券)": "退后GMV",
    "千川整体智能优惠券": "优惠券金额",
    "优惠券金额占比": "优惠券占比",
    "广告消耗": "广告消耗",
    "退款金额（退款时间）": "退款金额",
    "退款金额(退款时间)": "退款金额",
    "退款金额": "退款金额",
    "综合ROI": "综合ROI",
    "退后ROI": "退后ROI",
    "退款率": "退款率",
    "千次曝光成交": "千次曝光成交",
    "千次曝光成本": "CPM",
    "GPM": "GPM",
    "小时产出": "小时产出",
    "成交人数": "成交人数",
    "直播间曝光次数": "曝光次数",
    "曝光次数": "曝光次数",
    "直播间场观次数（PV）": "直播间PV",
    "直播间场观次数(PV)": "直播间PV",
    "直播间PV": "直播间PV",
    "场观次数": "直播间PV",
    "直播间观看人数（UV）": "UV",
    "直播间观看人数(UV)": "UV",
    "商品点击次数": "商品点击次数",
    "成交订单数": "成交订单数",
    "曝光-观看率": "曝光观看率",
    "商品观看-点击率": "商品观看点击率",
    "商品点击-成交率": "点击成交率",
    "观看-成交率": "观看成交率",
    "增粉数": "增粉数",
    "互动率": "互动率",
    "停留时长": "停留时长",
    "平均在线人数": "平均在线人数",
}

# prepare_data.py 需要的必填字段
REQUIRED_FIELDS = ["直播时长", "整体GMV", "退款金额", "广告消耗",
                   "曝光次数", "直播间PV", "商品点击次数", "成交订单数", "成交人数"]


def parse_value(v):
    """解析单个单元格值，去除引号和千分位逗号"""
    v = v.strip()
    if v.startswith('"') and v.endswith('"'):
        v = v[1:-1]
    # 去千分位逗号
    if re.match(r'^[\d,]+\.\d+$', v):
        v = v.replace(',', '')
    elif re.match(r'^[\d,]+$', v):
        v = v.replace(',', '')
    # 空值/无效值
    if v == '' or v == '#DIV/0!' or v == '0' or v == '-' or v == '#N/A':
        return None
    # 百分比
    if '%' in v:
        try:
            return float(v.replace('%', '')) / 100
        except ValueError:
            return v
    # 数字
    try:
        return float(v) if '.' in v else int(v)
    except (ValueError, TypeError):
        return v


def parse_annotated_csv(raw_text):
    """
    解析lark-cli csv-get输出的标注格式。
    每行格式：[row=X] col1,col2,...
    返回 list[dict]，每个dict包含 row_num 和 values（list[str]）
    """
    rows = []
    for line in raw_text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        match = re.match(r'\[row=(\d+)\]\s*(.*)', line)
        if match:
            row_num = int(match.group(1))
            row_data = match.group(2)
            reader = csv.reader(io.StringIO(row_data))
            values = next(reader)
            rows.append({'row_num': row_num, 'values': values})
        else:
            # 无标注前缀的普通CSV行
            reader = csv.reader(io.StringIO(line))
            values = next(reader)
            rows.append({'row_num': len(rows) + 1, 'values': values})
    return rows


def find_date_columns(header_row, target_date, prev_date=None, week_start=None):
    """
    从表头行找到目标日期对应的列索引。
    
    飞书交叉表的列结构通常是：
    A=板块, B=指标, C=月TTL, D=6月1日, E=6月2日, ...
    
    返回 dict: {日期字符串: 列索引}
    """
    # 日期列从第3列开始（跳过板块和指标列）
    date_cols = {}
    for i, val in enumerate(header_row):
        if i < 2:  # 跳过板块、指标列
            continue
        v = val.strip()
        if v.startswith('6月') or v.startswith('7月') or re.match(r'\d+月\d+日', v):
            date_cols[v] = i
    
    result = {}
    if target_date in date_cols:
        result['target'] = date_cols[target_date]
    else:
        raise ValueError(f"找不到目标日期列: {target_date}, 可用日期列: {list(date_cols.keys())}")
    
    if prev_date and prev_date in date_cols:
        result['prev'] = date_cols[prev_date]
    
    if week_start:
        # 从week_start开始，取7天
        # 需要推断日期序列
        base_match = re.match(r'(\d+)月(\d+)日', week_start)
        if base_match:
            month = int(base_match.group(1))
            day = int(base_match.group(2))
            week_indices = []
            for d in range(day, day + 7):
                date_str = f"{month}月{d}日"
                if date_str in date_cols:
                    week_indices.append(date_cols[date_str])
            result['week'] = week_indices
    
    result['date_cols'] = date_cols
    return result


def extract_date_data(rows, col_idx, field_map):
    """
    从交叉表rows中，提取指定列索引的所有指标值。
    返回 dict: {标准字段名: 值}
    """
    result = {}
    for row in rows:
        values = row['values']
        # 指标名在第2列（index 1）
        if len(values) < 2:
            continue
        metric_name = values[1].strip()
        if not metric_name:
            continue
        
        # 映射为标准字段名
        std_name = field_map.get(metric_name)
        if std_name is None:
            # 未在映射表中的指标，保留原名
            std_name = metric_name
        
        # 取目标列的值
        if col_idx < len(values):
            val = parse_value(values[col_idx])
            if val is not None:
                result[std_name] = val
    
    return result


def extract_week_avg(rows, week_col_indices, field_map):
    """
    计算指定列索引列表（7天）的各指标均值。
    返回 dict: {标准字段名: 均值}
    """
    # 先提取每天的数据
    daily_data = []
    for col_idx in week_col_indices:
        day_data = extract_date_data(rows, col_idx, field_map)
        daily_data.append(day_data)
    
    # 计算均值
    avg_result = {}
    all_fields = set()
    for day_data in daily_data:
        all_fields.update(day_data.keys())
    
    for field in all_fields:
        vals = [d.get(field) for d in daily_data
                if d.get(field) is not None and isinstance(d.get(field), (int, float))]
        if vals:
            avg_result[field] = sum(vals) / len(vals)
    
    return avg_result


def check_required_fields(data, required):
    """检查必填字段是否存在且有效"""
    missing = []
    for field in required:
        if field not in data or data[field] is None:
            missing.append(field)
    return missing


def main():
    parser = argparse.ArgumentParser(description='飞书交叉表数据提取')
    parser.add_argument('--raw', required=True,
                        help='lark-cli csv-get输出的文件路径，或直接粘贴的标注CSV文本')
    parser.add_argument('--date', required=True,
                        help='目标日期，如 "6月20日"')
    parser.add_argument('--prev-date', default=None,
                        help='环比参考日期，如 "6月19日"')
    parser.add_argument('--week-start', default=None,
                        help='7日均值起始日期，如 "6月13日"（取7天）')
    parser.add_argument('--output-dir', default=None,
                        help='输出目录，默认为当前目录')
    
    args = parser.parse_args()
    
    # 读取原始数据
    raw_path = Path(args.raw)
    if raw_path.exists():
        raw_text = raw_path.read_text(encoding='utf-8')
    else:
        # 可能是直接粘贴的文本
        raw_text = args.raw
    
    # lark-cli csv-get 输出是JSON格式，需要提取 annotated_csv 字段
    annotated_csv = None
    try:
        json_data = json.loads(raw_text)
        if isinstance(json_data, dict) and 'data' in json_data:
            annotated_csv = json_data['data'].get('annotated_csv', '')
        elif isinstance(json_data, dict) and 'annotated_csv' in json_data:
            annotated_csv = json_data.get('annotated_csv', '')
    except (json.JSONDecodeError, TypeError):
        # 不是JSON，就是纯标注CSV文本
        annotated_csv = raw_text
    
    if not annotated_csv:
        print("错误：无法从输入数据中提取标注CSV", file=sys.stderr)
        sys.exit(1)
    
    # 解析标注CSV
    rows = parse_annotated_csv(annotated_csv)
    if not rows:
        print("错误：无法解析输入数据", file=sys.stderr)
        sys.exit(1)
    
    # 找表头行（第一行包含日期列）
    header_row = rows[0]['values']
    
    # 定位日期列
    try:
        col_info = find_date_columns(header_row, args.date, args.prev_date, args.week_start)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)
    
    # 提取目标日期数据
    today_data = extract_date_data(rows, col_info['target'], FIELD_MAP)
    
    # 检查必填字段
    missing = check_required_fields(today_data, REQUIRED_FIELDS)
    if missing:
        print(f"警告：以下必填字段缺失或无效: {missing}", file=sys.stderr)
    
    # 添加日期和直播间信息（从数据推断）
    # 日期从参数获取
    today_data['日期'] = args.date
    
    # 提取环比数据
    yesterday_data = None
    if 'prev' in col_info:
        yesterday_data = extract_date_data(rows, col_info['prev'], FIELD_MAP)
        yesterday_data['日期'] = args.prev_date
    
    # 提取7日均值
    week_avg_data = None
    if 'week' in col_info:
        week_avg_data = extract_week_avg(rows, col_info['week'], FIELD_MAP)
    
    # 输出目录
    output_dir = Path(args.output_dir) if args.output_dir else Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 写出JSON文件
    today_path = output_dir / "today.json"
    with open(today_path, 'w', encoding='utf-8') as f:
        json.dump(today_data, f, ensure_ascii=False, indent=2)
    print(f"今日数据: {today_path}")
    
    if yesterday_data:
        yesterday_path = output_dir / "yesterday.json"
        with open(yesterday_path, 'w', encoding='utf-8') as f:
            json.dump(yesterday_data, f, ensure_ascii=False, indent=2)
        print(f"昨日数据: {yesterday_path}")
    
    if week_avg_data:
        week_path = output_dir / "week_avg.json"
        with open(week_path, 'w', encoding='utf-8') as f:
            json.dump(week_avg_data, f, ensure_ascii=False, indent=2)
        print(f"7日均值: {week_path}")
    
    # 同时输出综合facts摘要（供LLM直接使用，减少后续计算）
    facts_summary = {
        "日期": args.date,
        "直播间": today_data.get("直播间", "未知"),
        "直播时长": today_data.get("直播时长"),
        "今日数据": today_data,
        "昨日数据": yesterday_data,
        "7日均值": week_avg_data,
    }
    
    # 计算环比和vs均值
    if yesterday_data:
        changes = {}
        for field in REQUIRED_FIELDS + ["综合ROI", "退后ROI", "退款率", "GPM", "CPM",
                                         "千次曝光成交", "小时产出", "曝光观看率",
                                         "商品观看点击率", "点击成交率", "观看成交率"]:
            t = today_data.get(field)
            p = yesterday_data.get(field)
            if t is not None and p is not None and isinstance(t, (int, float)) and isinstance(p, (int, float)) and p != 0:
                changes[field] = {
                    "today": t,
                    "yesterday": p,
                    "change_pct": round((t - p) / p, 4),
                }
        facts_summary["环比变化"] = changes
    
    if week_avg_data:
        vs_avg = {}
        for field in REQUIRED_FIELDS + ["综合ROI", "退后ROI", "退款率", "GPM", "CPM",
                                         "千次曝光成交", "小时产出", "曝光观看率",
                                         "商品观看点击率", "点击成交率", "观看成交率"]:
            t = today_data.get(field)
            a = week_avg_data.get(field)
            if t is not None and a is not None and isinstance(t, (int, float)) and isinstance(a, (int, float)) and a != 0:
                vs_avg[field] = {
                    "today": t,
                    "avg_7d": round(a, 2),
                    "vs_avg_pct": round((t - a) / a, 4),
                }
        facts_summary["vs_7日均值"] = vs_avg
    
    # 加载阈值配置，计算预警状态
    thresholds_path = CONFIG_DIR / "thresholds.json"
    if thresholds_path.exists():
        thresholds = json.loads(thresholds_path.read_text(encoding='utf-8'))
        alerts = {}
        for field, th in thresholds.items():
            if not isinstance(th, dict) or th.get("type") != "range":
                continue
            val = today_data.get(field)
            if val is None or not isinstance(val, (int, float)):
                continue
            if "red_below" in th and val < th["red_below"]:
                alerts[field] = {"value": val, "alert": "红色预警"}
            elif "red_above" in th and val > th["red_above"]:
                alerts[field] = {"value": val, "alert": "红色预警"}
            elif "yellow_below" in th and val < th["yellow_below"]:
                alerts[field] = {"value": val, "alert": "黄色预警"}
            elif "yellow_above" in th and val > th["yellow_above"]:
                alerts[field] = {"value": val, "alert": "黄色预警"}
            else:
                normal = th.get("normal", [])
                if len(normal) == 2 and normal[0] <= val <= normal[1]:
                    alerts[field] = {"value": val, "alert": "正常"}
        facts_summary["预警状态"] = alerts

    facts_path = output_dir / "facts_summary.json"
    with open(facts_path, 'w', encoding='utf-8') as f:
        json.dump(facts_summary, f, ensure_ascii=False, indent=2)
    print(f"综合摘要: {facts_path}")

    # 打印预警摘要供快速参考
    if "预警状态" in facts_summary:
        red = [f for f, v in facts_summary["预警状态"].items() if v["alert"] == "红色预警"]
        yellow = [f for f, v in facts_summary["预警状态"].items() if v["alert"] == "黄色预警"]
        if red:
            print(f"红色预警: {', '.join(red)}")
        if yellow:
            print(f"黄色预警: {', '.join(yellow)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
