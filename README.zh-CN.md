# luma-event-scanner

[English](README.md) | [繁體中文](README.zh-TW.md)

**免费的 Luma 日历扫描器。** 它会读取你指定日历里每一场未来活动的完整说明，用你的关键词匹配，按你的重要性排序，并记住你已经看过哪些，所以第二天的清单只会出现新的活动。

## 用 AI 编程助手安装

把这段粘贴给 Claude Code、Codex CLI 或任何编程助手：

> 请 clone https://github.com/yyu0310/luma-event-scanner ，先读 AGENTS.md，再帮我设置。请问我要监控哪些 Luma 日历、我在意什么。日历的 slug 是它 luma.com 网址的最后一段。然后按 examples/criteria.example.json 帮我写一份 criteria.json，再运行一次。

这个项目不需要任何密码、token 或 API key，所以每个步骤都可以交给助手代劳。

## 为什么做这个

大型会议周的 Luma 上会冒出数百场周边活动。Luma 没有跨活动说明的搜索，能帮上忙的官方 API 又锁在付费方案里。而你在意的内容常常只出现在说明正文，不在标题。

| 你想做的事 | 这个工具怎么做 |
| --- | --- |
| 找出说明里提到某件事的活动 | `--keywords` 匹配标题、主办、嘉宾与说明 |
| 先看最相关的活动 | `criteria.json` 按你定的优先顺序排序 |
| 每天查，不重看旧活动 | 列给你看过的活动，第二天自动进淘汰名单 |
| 跳过已经决定的活动 | `--exclude` 与 `--restore` |
| 给活动做笔记 | `--note` |

## 快速开始

要求：Python 3.9 以上。只用标准库，不用安装任何东西。

```bash
git clone https://github.com/yyu0310/luma-event-scanner.git
cd luma-event-scanner

# 第一次运行：指定要监控的日历（luma.com/<slug>），关键词 regex 可选
python3 luma_scan.py --calendars my-calendar,another-calendar --keywords "grant|hackathon" --timezone Asia/Shanghai

# 可选：按自己的优先顺序排序
mkdir -p ~/.luma-event-scanner
cp examples/criteria.example.json ~/.luma-event-scanner/criteria.json   # 再自行修改

# 之后每次运行（日历与关键词都会被记住）
python3 luma_scan.py
```

然后打开 `~/.luma-event-scanner/candidates.md`。第一次会把每场活动下载一次，每秒约两次请求，300 场的日历要几分钟。之后只会下载新活动。

## 命令

| 命令 | 作用 |
| --- | --- |
| `python3 luma_scan.py` | 列出日历、扫描新活动、写出报表 |
| `--data-dir DIR` | 账本与报表放哪里（默认 `~/.luma-event-scanner`） |
| `--full` | 全部重扫，不只扫新活动 |
| `--note KEY "文字"` | 给活动加备注，重跑不会消失 |
| `--exclude KEY [原因]` | 手动把活动放进淘汰名单 |
| `--restore KEY` | 把活动从淘汰名单还原 |
| `--peek` | 生成今日候选，但不标记为已看过 |
| `--timezone NAME` | 显示时区，例如 `Asia/Singapore`（默认：系统时区） |
| `--rescan-days N` | 已扫过的活动隔 N 天重扫（默认 3） |

`KEY` 是活动的 `api_id`，或活动网址 `luma.com/<KEY>` 的最后一段。

## 排序怎么工作

`criteria.json` 是一个由重要到次要排列的清单。每个条件有一个 regex，和两份要去匹配的字段清单：

```json
{"tag": "V", "name": "Venture investors", "regex": "\\bVCs?\\b|venture|investors?",
 "strong": ["title", "host_names"], "weak": ["hosts"]}
```

- 可用字段：`title`、`hosts`、`host_names`、`guests`、`categories`、`calendar`、`description`。`hosts` 匹配主办名称与简介，`host_names` 只匹配名称。
- 命中 `strong` 字段是强匹配，命中 `weak` 字段是弱匹配。
- 每场活动归在它命中的最重要的那个条件下面。同一区内强匹配在前，再按开始时间排。
- 像 "investor" 或 "AI" 这种几乎每场说明都会出现的常见词，通常不要把 `description` 放进强匹配。

没有 `criteria.json` 时，工具只做关键词扫描。

## 淘汰名单

列在 `candidates.md` 的每场活动，第二天会移进 `excluded.md`，所以每天运行只会看到新的。同一天运行两次不会有任何改变。只想预览就加 `--peek`，误淘汰的用 `--restore` 还原。没有命中任何条件的活动不会被淘汰，所以主办之后改了说明、开始符合条件时，它会出现。

## 你的数据放哪里

默认放在 `~/.luma-event-scanner/`，在任何 repository 之外：

| 文件 | 内容 |
| --- | --- |
| `ledger.json` | 状态：看过的每场活动、扫描时间、备注、淘汰 |
| `scanned.md` | 账本的可读版 |
| `candidates.md` | 符合条件、还没看过的活动，已排序 |
| `excluded.md` | 已看过或手动淘汰的活动 |
| `criteria.json` | 你的条件，这份由你自己写 |
| `cache/` | 活动详情原始数据，改条件不必重新下载 |

如果你追踪好几个不相关的主题，每个主题用一个 `--data-dir`。

## 工作原理

1. `GET api.lu.ma/url` 把日历 slug 换成日历 id。
2. `GET api.lu.ma/calendar/get-items` 一页一页列出未来活动。
3. `GET api.lu.ma/event/get` 下载每场活动的详情：说明、主办、嘉宾与分类，并缓存。
4. 条件用缓存的详情计分，所以改 `criteria.json` 不需要网络。
5. 你看过的活动会记上 `shown_date`，`shown_date` 早于今天的活动就是被淘汰。

所有请求都是只读、不需登录的 GET，每秒约两次。

## 限制

- **非官方。** 上面三个端点没有官方文档，可能不预警地改版。这个项目完全基于学术研究，没有商业用途。它只以低频率读取公开页面，与 Luma 无关。请遵守 Luma 的服务条款。
- **只读公开数据。** 不能创建活动或管理嘉宾，所以取代不了官方 API。
- **只做文字匹配。** 它不理解语义。只以 logo 图片出现的赞助商它看不到。
- **只扫你指定的日历。** 不在那些日历里的活动看不到。
- **在 macOS 上用 Python 3.9 与 3.13 测试过。** Linux 与 Windows 因为只用标准库应该可以运行，但没有测试。Windows 上的时区名称需要安装 `tzdata` 包。

## 开发

```bash
python3 -m unittest discover tests -v
```

测试完全离线，用一个小型的内存内 Luma 日历取代网络，并写入临时文件夹。

## 许可

[PolyForm Noncommercial 1.0.0](LICENSE)。学术研究等非商业用途可免费使用。
