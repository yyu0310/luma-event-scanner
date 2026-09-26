# luma-event-scanner

[English](README.md) | [繁體中文](README.zh-TW.md)

**免费的 Luma 日历扫描器。** 它会读取你指定日历里每一场未来活动的完整说明，用你的关键词匹配，按你的重要性排序，并记住你已经看过哪些，所以第二天的清单只会出现新的活动。

不需要付费 API。Luma 官方 API 需要 Luma Plus，[年付每月 $59](https://luma.com/pricing)。这个工具读取的是公开活动页，完全免费。

## 用 AI 编程助手安装

把这段粘贴给 Claude Code、Codex CLI 或任何编程助手：

> 请 clone https://github.com/yyu0310/luma-event-scanner，先读 AGENTS.md，再帮我设置。请问我要监控哪些 Luma 日历、我在意什么。日历的 slug 是它 luma.com 网址的最后一段。然后按 examples/criteria.example.json 帮我写一份 criteria.json，再运行一次。

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

