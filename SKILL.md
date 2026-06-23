---
name: live-review
description: 直播复盘日报生成：运营提供当天数据（飞书表/CSV/粘贴）→ LLM按星月格式自动生成五段式复盘日报。退后GMV为核心口径。
agent_created: true
---

# 直播复盘日报 Skill

## 触发条件

当用户提到以下关键词时触发：直播复盘、复盘日报、日报生成、直播数据分析、生成复盘

## 文件结构

```
~/.workbuddy/skills/live-review/
├── SKILL.md                    # 本文件
├── examples/
│   └── sample_daily_report.md  # few-shot 样本（炫迈6/14日报）
├── config/
│   ├── input_spec.json         # 输入字段规格
│   └── thresholds.json         # 预警阈值配置（可调）
├── scripts/
│   ├── prepare_data.py         # 数据标准化 + 派生计算
│   ├── extract_feishu_pivot.py # 飞书交叉表数据提取（新增）
│   └── md_to_html.py           # Markdown → HTML 转换（带样式）
└── output/                     # 生成的日报存放目录（.md + .html）
```

## 环境检查（精简版）

**只在首次使用或环境异常时执行，已确认可用则跳过。**

飞书数据源才需要检查 lark-cli，粘贴/CSV源只需Python。

并行执行（1 turn）：

```bash
# 检查Python（必须）
python --version 2>&1

# 检查lark-cli（飞书源才需要）
lark-cli --version 2>&1

# 检查飞书认证（飞书源才需要）
lark-cli auth status 2>&1
```

- Python缺失 → 提示用户安装（winget或手动下载，必须勾选Add to PATH）
- lark-cli缺失 → `npm install -g @larksuite/cli`
- 飞书认证失败 → 按lark-shared skill流程引导配置
- 全部通过 → "环境检查通过，开始生成复盘日报"

---

## 快速路径：飞书wiki链接（最优路径，目标8-9 turns）

**当用户直接给飞书wiki链接时，走此快速路径，禁止试错。**

### Step 1（并行，1 turn）

- 确定目标日期（用户指定或推算"上周X"）
- 读取 few-shot 样本（examples/sample_daily_report.md）
- 如需环境检查，在此步并行执行

⚠️ **速度规则（必须遵守）**：
- 不要读取 scripts/ 目录下的 .py 文件内容，直接按命令调用即可
- config/thresholds.json 不需要读取，脚本内部自动加载
- config/input_spec.json 不需要读取
- 只需读取 examples/sample_daily_report.md（作为 few-shot 样本）
- 环境检查已通过的不要重复检查

### Step 2（1 turn）：解析wiki URL → 获取表格信息

从URL提取node_token（`/wiki/`后面的字符串），执行：

```bash
lark-cli wiki spaces get_node --params '{"token":"<node_token>"}' --as user --format json 2>&1
```

从返回JSON读取：
- `obj_token` → 用作 spreadsheet-token
- `obj_type` → 确认是sheet类型
- `title` → 直播间名称参考

⚠️ **关键规则（禁止违反）**：
1. 必须加 `--as user`（wiki操作需要用户身份）
2. **不要给node_token加 `--obj-type` 参数**（会报错）
3. **不要用 `--url` 参数**（不支持）
4. **不要用 `+node-get` 命令**（已废弃/行为不同）
5. **只用 `spaces get_node` 这一个命令**，不要尝试其他变体

然后获取表格结构：

```bash
lark-cli sheets +workbook-info --spreadsheet-token "<obj_token>" --as user 2>&1
```

从sheets列表找到日报数据所在sheet_id（通常是"直播日报-X月"格式）。

### Step 3（并行，1 turn）：读取日报数据

读取两个sheet（并行）：

```bash
# SOP模板（通常URL直接指向的sheet）
lark-cli sheets +csv-get --spreadsheet-token "<obj_token>" --sheet-id "<sop_sheet_id>" --range "A1:T20" --as user 2>&1

# 日报数据（交叉表格式，只读指标行范围，减少token消耗）
lark-cli sheets +csv-get --spreadsheet-token "<obj_token>" --sheet-id "<data_sheet_id>" --range "A1:Y35" --as user 2>&1
```

**注意range选择**：只读A1到目标日期+7天列范围的指标行（约35行×23列），不要读整月（减少80%+ token消耗）。

### Step 4（1 turn）：数据提取 + 派生计算

lark-cli返回的是JSON格式，包含`annotated_csv`字段。用 `extract_feishu_pivot.py` 一步完成提取+转换：

```bash
python ~/.workbuddy/skills/live-review/scripts/extract_feishu_pivot.py \
  --raw "<lark-cli输出的JSON文件路径>" \
  --date "6月20日" \
  --prev-date "6月19日" \
  --week-start "6月13日" \
  --output-dir "<临时目录>"
```

脚本自动处理：
- 从JSON中提取annotated_csv字段
- 解析[row=X]标注格式
- 按日期列提取指标值
- 映射飞书指标名到标准字段名
- 计算环比和7日均值偏差
- 输出 facts_summary.json（可直接用于日报生成）

**如果时长差异需要确认**（如8小时场vs12小时场），在此步暂停问用户。

### Step 5（1 turn）：LLM生成日报

将 facts_summary.json 注入prompt（见下方"日报生成prompt"章节），由LLM生成五段式日报。

### Step 6（1 turn）：输出

1. 保存MD文件到 `output/{直播间}_{日期}_复盘日报.md`
2. 用脚本转HTML：

```bash
python ~/.workbuddy/skills/live-review/scripts/md_to_html.py "~/.workbuddy/skills/live-review/output/{直播间}_{日期}_复盘日报.md"
```

3. 展示结果，告诉用户两个文件路径

---

## 其他数据来源路径

### CSV/Excel文件

1. 用户提供文件路径
2. 运行 prepare_data.py 处理
3. 生成日报（同Step 5-6）

### 直接粘贴

1. 用户在对话中粘贴数据
2. 解析为结构化dict
3. 运行 prepare_data.py 或手动计算派生指标
4. 生成日报（同Step 5-6）

---

## 日报生成 Prompt

**重要：先读取 `examples/sample_daily_report.md` 作为 few-shot 参考。**

---

**System Prompt：**

你是一位资深直播运营分析师，正在给直播团队做今日复盘。你的风格是：
- 直接、不废话，像团队内部开会一样说话
- 数据先行，每个判断都要有数据支撑
- 问题诊断要找到根因，不只是列数据
- 优化建议要可落地，有具体动作和目标数字
- 事实和推测必须分开，推测的地方要标注"待核实"
- 退后GMV是核心口径，所有ROI讨论基于退后口径
- 消耗分析规则（核心）：
  - "核心数据概览"必须包含消耗板块：当日千川消耗、平均小时消耗（当日消耗÷直播时长）、消耗环比
  - 消耗目标对比：如 facts 中有消耗目标值则对比，没有则标注"消耗目标待接入"
  - GPM/小时产出归因链：千川消耗下降 → GMV与观看次数下滑 → GPM/小时产出降低。不要把"时长缩短"作为GPM/小时产出偏低的主因
  - 推广方向判断：用"消耗带来的观看次数 / CPM"评估投放方向是否有问题
  - ⚠️ 禁止使用"花钱效率"一词，全部改为"转化效率"（包括亮点分析、问题诊断等所有段落）
- 时长差异处理规则（重要）：
  - 当今日直播时长 ≠ 昨日直播时长时，环比分析必须同时给出"单位小时指标"对比（小时GMV、小时订单数、小时PV、小时消耗），绝对值环比仍展示但标注"时长差异X小时，绝对值环比仅供参考"
  - 不分析时长变化原因，不猜测为什么缩短或增加。仅在"异常数据备注"中标注时长差异事实，如"今日8h场 vs 昨日12h场，时长差异4h"
  - 小时产出始终是核心对比指标，它天然归一化了时长差异

**输出格式要求（严格遵守）：**

按以下五段式结构输出，不要增加或减少段落：

### 一、今日核心数据概览
- 列出关键指标（GMV、退后GMV、ROI、退后ROI、流量、CPM、GPM）
- **消耗板块（必须）**：当日千川消耗、平均小时消耗（=当日消耗÷直播时长，须附 vs 7日均值偏差）、消耗环比变化、消耗目标对比（无目标时标注"消耗目标待接入"）
- 每个指标附环比变化百分比和预警状态
- 最后一句话总结今天数据的核心特征

### 二、今日亮点总结
- 找出表现好的指标（环比上涨、在正常区间、优于均值的）
- 分析亮点背后可能的原因
- 如果没有亮点，直接说"今天没有明显亮点"

### 三、核心问题诊断
- 聚焦红色和黄色预警指标
- 每个问题要有：数据 → 原因分析 → 影响判断
- 如果涉及转化漏斗，要按"曝光→观看→点击→成交"逐级拆解
- **GPM/小时产出归因规则**：主因链条 = 千川消耗变化 → GMV与观看次数变化 → GPM/小时产出变化。同时用 CPM（消耗÷曝光×1000）判断推广方向是否有问题。不要把"直播时长缩短"当作GPM/小时产出下降的主因
- 推测原因用"可能是""待核实"标注

### 四、明日可落地优化建议
- 每条建议对应一个具体问题
- 格式：动作 + 目标数字
- 建议数量 2-4 条，不要泛泛而谈

### 五、异常数据备注
- 列出数据完整度
- 标注需要人工确认的异常点
- 如果历史数据不足，标明"样本不足，环比结论仅供参考"

---

**Few-shot 样本：**

{读取 examples/sample_daily_report.md 的完整内容插入此处}

**当前数据（facts JSON）：**

{插入 facts_summary.json 的内容}

---

## 飞书数据读取（完整说明）

### URL类型判断

用户提供URL后，先判断类型：
- `/wiki/` 路径 → wiki链接，需解析获取obj_token（见快速路径Step 2）
- `/sheets/` 路径 → 直接电子表格，URL中的token即spreadsheet-token

### 交叉表格式说明

飞书运营数据表是**交叉表**格式：
- 行 = 指标（直播时长、GMV、ROI等）
- 列 = 日期（C列=月TTL, D列=6月1日, E列=6月2日, ...）
- lark-cli csv-get 输出是JSON，`data.annotated_csv` 字段包含 `[row=X]` 前缀的CSV

这种格式不能用 prepare_data.py 直接处理（它期望行格式：一行一天，列是指标）。必须用 `extract_feishu_pivot.py` 先提取转换。

### 数据范围选择原则

- **不要读整月数据**（A1:AH203之类），只读需要的范围
- 目标日期列 + 前7天列 + 指标行 ≈ A1:Y35
- 这样减少80%+的token消耗

### 字段映射

飞书表指标名与标准字段名对照（extract_feishu_pivot.py内置映射表）：

| 飞书表指标名 | 标准字段名 |
|-------------|-----------|
| 直播时长 | 直播时长 |
| 整体GMV（含券） | 整体GMV |
| 退后GMV（含券） | 退后GMV |
| 广告消耗 | 广告消耗 |
| 退款金额（退款时间） | 退款金额 |
| 综合ROI | 综合ROI |
| 退后ROI | 退后ROI |
| 直播间曝光次数 | 曝光次数 |
| 直播间场观次数（PV） | 直播间PV |
| 商品点击次数 | 商品点击次数 |
| 成交订单数 | 成交订单数 |
| 成交人数 | 成交人数 |

## 必填字段校验

**必填字段（9个）：**
- 直播时长、整体GMV、退款金额、广告消耗
- 曝光次数、直播间PV、商品点击次数、成交订单数、成交人数

**校验规则：**
- 缺字段 → 停止，告诉用户缺哪些
- 数值字段不能为负
- 0 是有效值，空才是缺失

## 派生指标计算公式

```
退后GMV = 整体GMV - 退款金额
综合ROI = 整体GMV / 广告消耗
退后ROI = 退后GMV / 广告消耗
退款率 = 退款金额 / 整体GMV
CPM = (广告消耗 / 曝光次数) × 1000
千次曝光成交 = (整体GMV / 曝光次数) × 1000
曝光观看率 = 直播间PV / 曝光次数
商品观看点击率 = 商品点击次数 / 直播间PV
点击成交率 = 成交订单数 / 商品点击次数
观看成交率 = 成交订单数 / 直播间PV
GPM = (整体GMV / 直播间PV) × 1000
小时产出 = 退后GMV / 直播时长
平均小时消耗 = 广告消耗 / 直播时长
```

extract_feishu_pivot.py 已内置这些计算和环比/均值偏差分析。

## 边界

- 不接 API 取数（后续单独项目）
- 不推飞书群消息
- 不上服务器
- 不修改飞书数据源
- 话题飘到以上范围时，提醒用户这是后续项目

## 配置文件

- `config/thresholds.json` — 预警阈值，可按账号调整
- `config/input_spec.json` — 输入字段规格参考
- `examples/sample_daily_report.md` — 输出格式参考（few-shot）
