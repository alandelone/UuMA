# 工作站開發與手動發布

## 版本怎麼算

UuMA 使用一個主倉庫，各 Agent 定義放在各自 profile 目錄。Git commit 是整個倉庫的
來源位置；運行版本按組件的內容和依賴摘要判斷。沒有改動的 Agent 可以保留較早的來源
commit，狀態顯示「已符合目標」，不需要重啟。

Hermes、Yonc Graph、eSchematic、RSTV4 保留原倉庫。`deploy/components.json` 固定其來源
commit、源碼內容摘要和版本包摘要。工作區未提交的修改已另存為源碼快照；它們不能冒充
原 commit 的內容。這些快照不包含運行資料庫、瀏覽器登入態或 `.env`。

## 三個手動步驟

1. 在工作站修改，檢查並提交選定的檔案。不要全量加入其他未完成的修改。
2. 產生預覽，核對目標提交、變動組件、受影響 Agent、服務和共享 gateway。
3. 明確套用那份預覽，再查看發布回執。此流程沒有定時拉取或自動發布。

入口為 `python -m uuma.release`：

```text
preview --root <倉庫> --target <固定提交> --actual <實際版本.json>
        --deployment <節點部署.json> --output <發布預覽.json>
apply   --root <倉庫> --plan <發布預覽.json> --actual <實際版本.json>
        --deployment <相同節點部署.json>
receipt <發布回執.json>
```

應在目標節點執行 apply，或由工作站透過 SSH 呼叫目標節點的相同入口。兩台機器各有
自己的實際版本檔。程式不會因產生預覽就啟動更新。預覽同時固定部署設定摘要，修改
服務啟動參數後必須重新預覽。

## 實際套用的條件

`CommandReleaseBackend` 已接上 CLI apply，從 Git 的固定提交展開新版本目錄，不覆蓋
開發工作區或舊環境。部署設定由操作者管理，逐組件指定 Agent 與服務；每個服務必須
提供 pause、snapshot、activate、verify、resume 五個固定參數命令，不經 shell 解譯。

命令會收到 `UUMA_DEPLOYMENT_CONTEXT`，必須以 JSON 回傳相同 plan_id，並提供實際證據：

| 階段 | 必須回報 |
|---|---|
| pause | intake_paused=true，訊息入口也停止接新工作 |
| snapshot | intake_paused、active 清單、paused 清單；必須涵蓋 Hermes 和領域背景工作 |
| activate | 成功切換該服務的固定版本與環境 |
| verify | healthy=true、各受影響組件實際 revision 和 fingerprint |
| resume | intake_paused=false |

暫停工作還必須有 run_id、resume_ref、retained=true 和存在的絕對環境目錄。
有活動工作時返回 WAITING_FOR_TASKS，保持接單關閉，不終止工作；待工作結束後，操作者
再次套用同一份仍有效的預覽。開始切換後發生錯誤會留下 RECONCILIATION_REQUIRED，
不得直接再次切換或假設已回退。

這個通用 OS 介面已通過隔離測試；**五個 Agent 的真實 gateway 和領域背景工作維護命令
尚未全部接齊**。空回執、只更換源碼路徑或只檢查程序存活不能替代實際版本驗證。
目前不能把這套通用入口視為已驗收的五 Agent 生產一鍵更新。

## 資料與回退

代碼、模型環境和資料目錄分開。保留舊版本與暫停工作的環境。新端產生資料寫入後，
回退代碼不代表可以用舊資料庫覆蓋新資料。領域資料各自保存，不合併控制庫、知識庫和
Hermes 的 state.db。
