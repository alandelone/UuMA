# Scholar 五图导览

打开 index.html，从五个页签查看系统架构、科研流程、展示时序、数据流与代码关系。可单独打开每张 HTML；图自身包含交互查看器，无需运行 UuMA。

## 内容和范围

- UuMA 基线：0e273c8dce5f846dd1ffebd78e0d9e60ce8d3319。
- 已核对：Scholar SOUL、Hermes MCP 配置、可信审批转交、Worker 控制面、ScholarFieldKG 就绪检查、Observatory 适配/GET/SSE/缓存/卡片。
- 外部契约：RSTV4 研究内核、Catalog、Studio。当前工作区没有其源码；没有虚构内部类或实际运行地址。
- 本次未运行研究、模型、GPU、实验、采集或科学批准，未启动或验证现有产品 UI 服务。
- Observatory 默认 :8790；Phoenix 可选 :6006。总览页说明查看方法及 Catalog/Studio 的独立角色。

## 关键发现

1. Observatory 只读源库。科研卡片直接读取 catalog.db / uuma.db；活动流另经 Harvester 与 observatory.db。
2. ScholarAdapter 的默认 Catalog 路径指向另一台机器的旧路径，Registry 未覆盖；该路径本机不存在。
3. 研究树有演示回退；收起卡片、部分阶段数字、流水线定论和测试摘要为固定内容，不是实时科学验收。
4. SSE activity 只追加活动流；卡片数据由 GET 和 SSE init 重读。断线重连 5 秒，fallback 卡片轮询实际 10 秒。
5. 用户保留科学意图、方法、结论和发布权；Track 显式固定 Snapshot，不导入其他路线批准。

## 校验与保留意见

verification.json 记录最终五图的 validate / deliver / provenance check / real-browser check 回执及 SHA256 对照。所有四类自动关口通过后才打包。没有声明人工视觉审阅。自动路由报告架构图 1 处、数据流图 2 处交叉及少量绕线，具体见 layout_advice；未为减少交叉删除任何数据来源或关系。

任务开始时 active-session/HANDOFF.md 与 active-session/progress.md 已有改动，保留原内容并按会话规则追加交接；没有更改产品源码或 mission gate。

ZIP 内图稿与原产物逐字节一致，图内源码链接固定到上述提交。解压时保留五个子目录与 index.html 的相对位置。
