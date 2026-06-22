"""
Markdown → HTML 转换脚本
输入：Markdown 文件路径
输出：同目录下同名 .html 文件

使用 Python 标准库，无需 pip install。
针对直播复盘日报的五段式格式优化。
"""
import re
import sys
from pathlib import Path

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", sans-serif;
    line-height: 1.8; color: #1a1a1a; background: #f5f5f5;
    padding: 20px;
  }}
  .container {{
    max-width: 800px; margin: 0 auto; background: #fff;
    border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    padding: 40px; overflow-x: auto;
  }}
  h1 {{
    font-size: 22px; color: #1a1a1a; border-bottom: 3px solid #4f46e5;
    padding-bottom: 12px; margin-bottom: 24px;
  }}
  h2 {{
    font-size: 18px; color: #4f46e5; margin: 32px 0 14px;
    padding: 8px 14px; border-left: 4px solid #4f46e5;
    background: #f0f0ff; border-radius: 0 6px 6px 0;
  }}
  h3 {{ font-size: 15px; color: #374151; margin: 20px 0 8px; font-weight: 600; }}
  p {{ margin: 8px 0; font-size: 14px; }}
  ul, ol {{ margin: 8px 0 8px 24px; font-size: 14px; }}
  li {{ margin: 5px 0; }}
  li > ul, li > ol {{ margin: 4px 0 4px 20px; }}
  strong {{ color: #1a1a1a; }}
  code {{
    background: #f3f4f6; padding: 2px 6px; border-radius: 3px;
    font-size: 13px; color: #dc2626;
  }}
  table {{
    width: 100%; border-collapse: collapse; margin: 12px 0;
    font-size: 13px;
  }}
  th {{
    background: #4f46e5; color: #fff; padding: 8px 10px;
    text-align: left; font-weight: 600; white-space: nowrap;
  }}
  td {{
    padding: 7px 10px; border-bottom: 1px solid #e5e7eb;
  }}
  tr:nth-child(even) td {{ background: #f9fafb; }}
  tr:hover td {{ background: #eef2ff; }}
  hr {{ border: none; border-top: 1px solid #e5e7eb; margin: 24px 0; }}
  .alert-red {{ color: #dc2626; font-weight: 600; }}
  .alert-yellow {{ color: #d97706; font-weight: 600; }}
  .alert-green {{ color: #16a34a; font-weight: 600; }}
  .summary-box {{
    background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px;
    padding: 14px 18px; margin: 12px 0; font-size: 14px;
  }}
  .section-intro {{
    color: #374151; font-size: 14px; margin: 8px 0 12px;
    padding-left: 4px; border-left: 3px solid #e5e7eb;
    padding: 4px 12px;
  }}
  .footer {{
    margin-top: 32px; padding-top: 16px; border-top: 1px solid #e5e7eb;
    font-size: 12px; color: #9ca3af; text-align: center;
  }}
</style>
</head>
<body>
<div class="container">
{body}
<div class="footer">由 AI 直播复盘 Skill 自动生成</div>
</div>
</body>
</html>
"""

SECTION_RE = re.compile(r"^###\s+([一二三四五六七八九十]、.+)$")
NUMBERED_RE = re.compile(r"^(\d+)\.\s+(.+)$")
BULLET_RE = re.compile(r"^(\s*)[-*]\s+(.+)$")
TABLE_ROW_RE = re.compile(r"^\|.+\|$")


def md_to_html(md_text):
    lines = md_text.split("\n")
    html_parts = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()

        if TABLE_ROW_RE.match(stripped):
            table_rows = []
            while i < len(lines) and TABLE_ROW_RE.match(lines[i].rstrip()):
                table_rows.append(lines[i].rstrip())
                i += 1
            html_parts.append(_render_table(table_rows))
            continue

        section_m = SECTION_RE.match(stripped)
        if section_m:
            html_parts.append(f"<h2>{_inline(section_m.group(1))}</h2>")
            i += 1
            continue

        if stripped.startswith("# "):
            html_parts.append(f"<h1>{_inline(stripped[2:].strip())}</h1>")
            i += 1
            continue
        if stripped.startswith("## "):
            html_parts.append(f"<h2>{_inline(stripped[3:].strip())}</h2>")
            i += 1
            continue
        if stripped.startswith("### "):
            html_parts.append(f"<h3>{_inline(stripped[4:].strip())}</h3>")
            i += 1
            continue

        if stripped.startswith("---"):
            html_parts.append("<hr>")
            i += 1
            continue

        numbered_m = NUMBERED_RE.match(stripped)
        if numbered_m:
            items, i = _collect_numbered_list(lines, i)
            html_parts.append(_render_numbered_list(items))
            continue

        bullet_m = BULLET_RE.match(stripped)
        if bullet_m:
            items, i = _collect_bullet_list(lines, i, 0)
            html_parts.append(_render_bullet_list(items))
            continue

        if stripped:
            html_parts.append(f"<p>{_inline(stripped)}</p>")

        i += 1

    return "\n".join(html_parts)


def _collect_bullet_list(lines, start, base_indent):
    items = []
    i = start
    while i < len(lines):
        m = BULLET_RE.match(lines[i].rstrip())
        if not m:
            break
        indent = len(m.group(1))
        if indent < base_indent:
            break
        if indent > base_indent and items:
            sub_items, i = _collect_bullet_list(lines, i, indent)
            items[-1]["children"] = sub_items
            continue
        items.append({"text": m.group(2).strip(), "children": []})
        i += 1
    return items, i


def _collect_numbered_list(lines, start):
    items = []
    i = start
    while i < len(lines):
        stripped = lines[i].rstrip()
        numbered_m = NUMBERED_RE.match(stripped)
        if numbered_m:
            items.append({"text": numbered_m.group(2).strip(), "children": []})
            i += 1
            sub_lines = []
            while i < len(lines):
                sl = lines[i].rstrip()
                if not sl:
                    i += 1
                    continue
                if NUMBERED_RE.match(sl):
                    break
                if SECTION_RE.match(sl) or sl.startswith("### ") or sl.startswith("## "):
                    break
                bm = BULLET_RE.match(sl)
                if bm:
                    sub_items, i = _collect_bullet_list(lines, i, len(bm.group(1)))
                    items[-1]["children"] = sub_items
                    continue
                items[-1].setdefault("extra", [])
                items[-1]["extra"].append(sl)
                i += 1
        else:
            break
    return items, i


def _render_bullet_list(items):
    parts = ["<ul>"]
    for item in items:
        content = _inline(item["text"])
        if item["children"]:
            content += "\n" + _render_bullet_list(item["children"])
        parts.append(f"<li>{content}</li>")
    parts.append("</ul>")
    return "".join(parts)


def _render_numbered_list(items):
    parts = ["<ol>"]
    for item in items:
        content = _inline(item["text"])
        extras = item.get("extra", [])
        if extras:
            for ex in extras:
                content += f"<br>{_inline(ex.strip())}"
        if item["children"]:
            content += "\n" + _render_bullet_list(item["children"])
        parts.append(f"<li>{content}</li>")
    parts.append("</ol>")
    return "".join(parts)


def _render_table(rows):
    if len(rows) < 2:
        return ""
    header_cells = [c.strip() for c in rows[0].strip("|").split("|")]
    parts = ["<table><thead><tr>"]
    for h in header_cells:
        parts.append(f"<th>{_inline(h)}</th>")
    parts.append("</tr></thead><tbody>")
    for row in rows[1:]:
        stripped = row.strip()
        if stripped.replace("|", "").replace("-", "").replace(":", "").strip() == "":
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        parts.append("<tr>")
        for cell in cells:
            parts.append(f"<td>{_inline(cell)}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def _inline(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    text = _apply_alert_colors(text)
    return text


def _apply_alert_colors(text):
    text = re.sub(
        r"(红色预警)",
        r'<span class="alert-red">\1</span>',
        text,
    )
    text = re.sub(
        r"(黄色预警)",
        r'<span class="alert-yellow">\1</span>',
        text,
    )
    return text


def convert_file(md_path):
    md_path = Path(md_path)
    md_text = md_path.read_text(encoding="utf-8")

    title_match = re.search(r"^#\s+(.+)", md_text, re.MULTILINE)
    title = title_match.group(1) if title_match else md_path.stem

    body = md_to_html(md_text)
    html = HTML_TEMPLATE.format(title=title, body=body)

    html_path = md_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    return str(html_path)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print("用法: python md_to_html.py <report.md>")
        print("输出: 同目录下同名 .html 文件")
        sys.exit(1)
    out = convert_file(sys.argv[1])
    print(f"已生成: {out}")
