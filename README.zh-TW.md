# luma-event-scanner

[English](README.md) | [简体中文](README.zh-CN.md)

**免費的 Luma 日曆掃描器。** 它會讀你指定日曆裡每一場未來活動的完整說明，用你的關鍵字比對，依你的重要性排序，並記住你已經看過哪些，所以隔天的清單只會出現新的活動。

不需要付費 API。Luma 官方 API 需要 Luma Plus，[年繳每月 $59](https://luma.com/pricing)。這個工具讀的是公開活動頁，完全免費。

## 用 AI 程式助手安裝

把這段貼給 Claude Code、Codex CLI 或任何程式助手：

> 請 clone https://github.com/yyu0310/luma-event-scanner，先讀 AGENTS.md，再幫我設定。請問我要監控哪些 Luma 日曆、我在意什麼。日曆的 slug 是它 luma.com 網址的最後一段。然後依 examples/criteria.example.json 幫我寫一份 criteria.json，再執行一次。

這個專案不需要任何密碼、token 或 API key，所以每個步驟都可以交給助手代勞。

## 為什麼做這個

大型會議週的 Luma 會冒出數百場周邊活動。Luma 沒有跨活動說明的搜尋，能幫上忙的官方 API 又鎖在付費方案裡。而你在意的內容常常只出現在說明內文，不在標題。

| 你想做的事 | 這個工具怎麼做 |
| --- | --- |
| 找出說明裡提到某件事的活動 | `--keywords` 比對標題、主辦、嘉賓與說明 |
| 先看最相關的活動 | `criteria.json` 依你定的優先順序排序 |
| 每天查，不重看舊活動 | 列給你看過的活動，隔天自動進汰除名單 |
| 略過已經決定的活動 | `--exclude` 與 `--restore` |
| 幫活動做筆記 | `--note` |

## 快速開始

需求：Python 3.9 以上。只用標準庫，不必安裝任何東西。

```bash
git clone https://github.com/yyu0310/luma-event-scanner.git
cd luma-event-scanner

# 第一次執行：指定要監控的日曆（luma.com/<slug>），關鍵字 regex 可選
python3 luma_scan.py --calendars my-calendar,another-calendar --keywords "grant|hackathon" --timezone Asia/Taipei

# 選用：依自己的優先順序排序
mkdir -p ~/.luma-event-scanner
cp examples/criteria.example.json ~/.luma-event-scanner/criteria.json   # 再自行修改

# 之後每次執行（日曆與關鍵字都會被記住）
python3 luma_scan.py
```

然後打開 `~/.luma-event-scanner/candidates.md`。第一次會把每場活動下載一次，每秒約兩次請求，300 場的日曆要幾分鐘。之後只會下載新活動。

## 指令

| 指令 | 作用 |
| --- | --- |
| `python3 luma_scan.py` | 列出日曆、掃描新活動、寫出報表 |
| `--data-dir DIR` | 帳本與報表放哪裡（預設 `~/.luma-event-scanner`） |
| `--full` | 全部重掃，不只掃新活動 |
| `--note KEY "文字"` | 幫活動加備註，重跑不會消失 |
| `--exclude KEY [原因]` | 手動把活動放進汰除名單 |
| `--restore KEY` | 把活動從汰除名單還原 |
| `--peek` | 產生今日候選，但不標記為已看過 |
| `--timezone NAME` | 顯示時區，例如 `Asia/Singapore`（預設：系統時區） |
| `--rescan-days N` | 已掃過的活動隔 N 天重掃（預設 3） |

`KEY` 是活動的 `api_id`，或活動網址 `luma.com/<KEY>` 的最後一段。

## 排序怎麼運作

`criteria.json` 是一個由重要到次要排列的清單。每個條件有一個 regex，和兩份要去比對的欄位清單：

```json
{"tag": "V", "name": "Venture investors", "regex": "\\bVCs?\\b|venture|investors?",
 "strong": ["title", "host_names"], "weak": ["hosts"]}
```

- 可用欄位：`title`、`hosts`、`host_names`、`guests`、`categories`、`calendar`、`description`。`hosts` 比對主辦名稱與簡介，`host_names` 只比對名稱。
- 命中 `strong` 欄位是強匹配，命中 `weak` 欄位是弱匹配。
- 每場活動歸在它命中的最重要的那個條件底下。同一區內強匹配在前，再依開始時間排。
- 像 "investor" 或 "AI" 這種幾乎每場說明都會出現的常見字，通常不要把 `description` 放進強匹配。

沒有 `criteria.json` 時，工具只做關鍵字掃描。

## 汰除名單

列在 `candidates.md` 的每場活動，隔天會移進 `excluded.md`，所以每天跑只會看到新的。同一天跑兩次不會有任何改變。只想預覽就加 `--peek`，誤汰除的用 `--restore` 還原。沒有命中任何條件的活動不會被汰除，所以主辦之後改了說明、開始符合條件時，它會出現。

