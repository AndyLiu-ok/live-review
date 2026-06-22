# live-review — 直播复盘日报 Skill

WorkBuddy Skill：从飞书电子表格一键生成直播复盘日报（五段式）。

## 功能

- 读取飞书电子表格中的直播数据（交叉表/宽表格式）
- 自动计算环比变化、7日均值偏差
- 根据预警阈值标记红色/黄色预警
- 时长差异自动归一化（单位小时指标对比）
- 生成五段式日报：核心数据 → 亮点 → 问题诊断 → 优化建议 → 异常备注
- 输出 Markdown + HTML 双格式

## 安装

### 前提条件

- 已安装 [WorkBuddy](https://workbuddy.app)

### 安装步骤

**方式一：Git Clone（推荐，方便后续更新）**

```bash
git clone https://github.com/<你的用户名>/live-review.git "%USERPROFILE%\.workbuddy\skills\live-review"
```

**方式二：手动下载**

1. 点击页面上方绿色的 **Code** 按钮 → **Download ZIP**
2. 解压后，将 `live-review` 文件夹放到：
   ```
   C:\Users\<你的用户名>\.workbuddy\skills\live-review
   ```

### 首次使用

打开 WorkBuddy，新建对话，发送类似以下消息：

> 根据这个飞书表格 https://xxx.feishu.cn/wiki/xxx 帮我生成昨天的直播复盘日报

Skill 会自动检测环境并引导你完成以下配置（仅首次需要）：

1. **Python 3** — 如未安装，访问 https://www.python.org/downloads/ 下载安装（勾选 "Add to PATH"）
2. **Node.js** — 如未安装，访问 https://nodejs.org/ 下载 LTS 版本安装
3. **lark-cli** — Skill 会自动安装：`npm install -g @anthropic-ai/lark-cli`（如已安装此步跳过）
4. **飞书认证** — 首次使用需登录飞书账号授权 lark-cli

## 使用说明

### 输入

给 WorkBuddy 发一条消息，包含：
- 飞书表格链接（wiki 链接或直接表格链接均可）
- 要生成哪天的日报（如"昨天"、"6月20日"）

### 输出

- `{店铺名}_{日期}_复盘日报.md` — Markdown 格式日报
- `{店铺名}_{日期}_复盘日报.html` — 带样式的 HTML 格式日报（可直接在浏览器打开）

### 预警阈值

预警阈值配置在 `config/thresholds.json`，可根据自己店铺的实际情况调整。

## 文件结构

```
live-review/
├── SKILL.md                          # Skill 定义（WorkBuddy 读取）
├── README.md                         # 本文件
├── config/
│   ├── input_spec.json               # 输入字段规格
│   └── thresholds.json               # 预警阈值（可调）
├── examples/
│   └── sample_daily_report.md        # 日报样本（few-shot）
└── scripts/
    ├── extract_feishu_pivot.py       # 飞书交叉表数据提取 + 计算
    ├── md_to_html.py                 # Markdown → HTML 转换
    └── prepare_data.py               # 窄格式数据处理（备用）
```

## 常见问题

**Q: 提示"lark-cli 未安装"**
A: 运行 `npm install -g @anthropic-ai/lark-cli`

**Q: 提示"飞书认证失败"**
A: 运行 `lark-cli auth login`，按提示登录飞书账号

**Q: 提示"没有权限访问该表格"**
A: 在飞书中申请对应表格的查看权限

**Q: 日报数据不对**
A: 检查飞书表格中对应日期的列是否有数据，确认日期格式正确

## 更新

如果使用 Git Clone 安装，拉取最新版本：

```bash
cd "%USERPROFILE%\.workbuddy\skills\live-review"
git pull
```
