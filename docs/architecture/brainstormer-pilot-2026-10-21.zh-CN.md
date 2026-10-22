# Brainstormer 伺服器隔離試點

## 範圍

這是五個 Agent 遷移的第一個驗證階段，並非正式 Telegram 切換。
工作站的 Orchestrator、Scholar 與原有 Bot 接收方仍保留原位。
Scholar 的暫停科研隊列未恢復、重試或重建。

三個伺服器模型帳戶均已通過原生 CLI 授權檢查；先前批准的單次
`OK` 模型連線驗證已完成，不重設或重跑該驗證。

| 服務 | 伺服器入口 | 狀態 |
| --- | --- | --- |
| 控制 API | loopback 8765 | 獨立控制庫，所有 Agent 接單保持暫停 |
| Brainstormer A2A | loopback 8768 | 官方 SDK 1.2.3，認證 Agent Card 與持久派發回執 |
| Hermes 內部執行 API | loopback 8772 | 一個 gateway，獨立 Brainstormer profile |
| 帳戶管理入口 | loopback 8771 | 原有 SSH 轉接入口，三個帳戶已就緒 |

8772 為新增的節點內部執行入口，不對外監聽。五個 Telegram Bot 的憑證
不放入此試點，避免兩端同時接收。同一台主機的模型執行上限設為兩個。

## 隔離與版本

`scripts/prepare-hermes-pilot.py` 只接受無憑證的 profile 候選、內容快照和
已審查的 UuMA plugin overlay，拒絕覆蓋現有執行目錄。角色 SOUL 保持原始
位元組；不複製 Hermes 會話、排程、登入態或歷史資料庫。

試點只開放指派查詢、進度／結果回報及四個 Brainstormer 領域讀取工具。
所有原有寫入工具、Gemini worker、Notion、ChatGPT bridge 與 Telegram
仍保留在完整來源定義中，試點的暫時縮減不是正式遷移後的權限定義。
領域讀取使用獨立內容快照；控制操作仍使用權威 API，禁止產生另一個 `uuma.db`。

Linux 執行狀態放在 `~/.local/share/uuma/pilot/`，版本來源另外保存。
執行目錄不能使用完整內容摘要形成過長路徑，否則 Hermes 的 Unix socket
會超過作業系統長度限制。服務目前不設定開機自動啟動。

Hermes 來源 commit 仍為 `274bc7b8f613c299b4f59160bacf8a19010f7003`。
完整來源摘要更新為
`a74e08df016459c43d9f97cb36a87cbcee5afad13c1430ac0d71c8c16ec9bfd9`，
共 3132 個檔案，補齊原先漏包的 `providers` 與 `tui_gateway`。
來源打包器現在核對 `pyproject.toml` 宣告的執行套件，缺少即拒絕打包。
執行時關閉 Hermes 自動安裝依賴；實際來源以程序環境核對，不能僅看服務檔案。

## 待啟動 Run 契約修正

實際 A2A 驗證發現：舊 `register_run` 固定將新 Run 記成 `RUNNING`，
而派發器只允許新的 `PENDING` 指派執行。這個組合不能啟動真正的 Hermes。

`RunRegistration.initial_status` 現在支援明確的 `PENDING`，舊呼叫及舊事件
仍維持 `RUNNING` 的預設語義。只有 Orchestrator 能準備尚未啟動、來源為
Orchestrator／Kanban 且尚無外部執行標識的 Run。事件保存初始狀態；投影將
待啟動 Run 對應至 READY Task。直接執行不藉此取得新的派發權限。

驗證包含真正控制 API → 持久 Run → 派發器，重複派發只啟動一次測試適配器。
Windows 與 Linux 均通過 43 項相關測試及五個子測試；Ruff 通過。

實際試點保留同一 Task。首次拒絕發生在派發意圖建立之前，確認沒有執行回執後，
以新 epoch 取代尚未啟動的舊 Run；保留其失敗歷史。禁止不核對回執就重試。

## 尚待驗收

- 真正模型執行的主題版本／物件數量結果，及領域快照雜湊不變。
- A2A 產出的結果仍須經 UuMA 驗收，不能用傳輸完成代替業務通過。
- Gemini worker 的伺服器登入或工作站服務安排。
- 最終資料停寫備份、完整工具接線、單一 Telegram 接收方切換。
- 其餘四個 Agent 的逐項遷移，以及手動發布介面的實際部署掛鉤。

不得將本試點的 API／授權成功解讀為五個 Agent 已完成生產遷移。

## 本階段實際回執

實際派發鏈：Task `task_935a34d78ff243a097de3c02854be8d9` → epoch 3 Run
`run_ff03e0b745184bd68798a3745d315cf9` → A2A Task
`f7b71027-ae38-44bb-8b93-188e0421c55a` → Hermes Run
`run_dd0381e9b7af4db7a6e20895c4085bf0`。

Agent 已回報 `proj_live_arch_001` 的 revision 6 與 object_count 6。獨立讀取
原始 JSON 校驗相同，七個原始領域檔案的 SHA 全部不變。控制狀態保持 REVIEW，
A2A 回讀明確顯示 accepted=false。Hermes 在四輪預算用盡時記成 failed、
turn_exit_reason=unknown；保留此執行限制，不能據此聲稱穩定完成或自動重跑。

實際模型工具呼叫發現結果回報原本只提供不透明 JSON 字串。現在 Worker MCP
同時公開嚴格 ResultContract／RunProgress 物件 schema 並保留既有字串介面；
業務輸出放 partial_state，不放到不允許的頂層欄位。原有審批與驗收檢查保持。

工作站已透過另一條 SSH 隧道以 18765／18768／18769 分別接到伺服器控制、
A2A、只讀 MCP。真正 MCP client 完成初始化、列出恰好三個領域讀取工具，
並取得同一個 revision 6／六物件結果。未認證回應為 403；控制與 A2A 回執
可讀。正式 Orchestrator profile 尚未切換到此試點。

領域 MCP 新增 --token-registry 指定既有身份登記檔，使領域快照資料根與
節點認證來源分開。不存在的登記檔會阻止啟動，禁止默默建立新權威。
新服務與帳戶入口都只監聽 loopback；試點服務不自動開機啟動。

Linux 目前相關驗證為 59 項通過、五個子測試通過；另有既存 MCP 設定型別
與 HTTP client 棄用警告，未修改斷言規避。Wisdom CPU KAG 依賴仍在獨立安裝
階段；未載入生產智慧庫或執行知識模型推理。
