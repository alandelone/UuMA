# Daily project tree and title-tail note control

The user requested a fixed expanded tree in By project: each shared L2 title once, its L3 titles indented beneath it, then their L4 Actions further indented. L2/L3 headings have no collapse controls. L2 is slightly larger than the existing L3 label; the current blue palette and L4 typography remain. By type retains the earlier per-card parent labels.

The permanent Step / note footer is removed. A small inline plus is anchored immediately after the title text. Only hovering that title-tail area reveals it; hovering the rest of the Action does not. Keyboard focus reveals the same control, and Enter on the task title still opens a note. The title focus target is an inline accessible button role with Enter and Space handling, avoiding nested native buttons. Clicking the plus requests an outline row without changing the active Focus. Touch devices retain a small visible affordance.

The candidate overlays only DailyView.tsx, dailyHierarchy.ts and daily.css on the exact published daily-live-20261111-6519f4204e86 snapshot, plus rebuilt assets. The helper groups sibling Actions under their actual nearest L3, emits that L3 heading once, and preserves By type order. All backend/Python files, schedule filtering, actual activity intervals, ten-minute live follow and autosave contracts are unchanged.

113 frontend tests and TypeScript/Vite build passed. Tests verify shared L3 grouping, all sibling Actions retained, and unchanged type grouping. Archive SHA256 e8f1804279bef2d71d0c7f11c4d50c8244eb1ece975e9034cd54db9ed64f8af4. Browser UI verification is unavailable because local browser use is disabled in Work settings; it was not enabled or bypassed, and no new screenshot or hover verification is claimed.

Task receipts: .uuma-local/yonc-daily-tree-20261111/. The current live-update iteration authorizes the scoped Graph publication. Server staging and guarded publication preserve every business table and the same persisted active manual Daily interval, with no migration or timer reset. No Notion/research/model work, unrelated source deployment, shared-service restart or mission gate approval.

Published November 11, 2026 at 16:57 UTC+08, source `/home/alandelone/.local/share/uuma/production/yonc/releases/daily-tree-20261111-e8f1804279be/source`. Only YONC Graph restarted (PID561489→563366); active manual Focus/Activity IDs and original start times remained unchanged. All 28 tables match the consistent backup; graph version remains 518 with 953 nodes, 899 edges and 50 eligible L4s at publication. User's newer notes (graph518) were retained, not replaced by the older fixture.

Independent live health, Daily and HTML/asset HTTP checks passed. Browser visual/hover verification remains unavailable due to Work settings; no screenshot claim. Refresh the browser to load the new bundle. Task-owned local preview was stopped with exact PID/command guard; fixture and source evidence retained.

Backup `/home/alandelone/.local/share/uuma/production/yonc/releases/daily-tree-20261111-e8f1804279be/backup-20261111T085702Z/project_graph.sqlite3`, SHA256 `868073ad0b69a757481a2e5f10a9a4f170ef90d9e32240e32aaa68fdac0d5125`. Roll back code/configuration only after checking later writes; never overwrite current records with the old backup.
