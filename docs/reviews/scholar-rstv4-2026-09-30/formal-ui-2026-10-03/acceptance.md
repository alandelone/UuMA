# Scholar 正式 Studio 本批修复与实跑

日期：2026-10-03，Asia/Kuala_Lumpur。全部 **118 个唯一需求 ID** 保留；11 组整体验收未完成。

## 本批范围与证据边界

使用正式 RSTV4 Studio HTTP 接口、正式 Writing Studio、独立临时数据库与真实编译器。
初始成文只在制作验收数据时用固定作者文字替代模型；待处理检查项是明确标记的测试数据。
这能验证界面操作、保存、版本与阶段约束，不能证明模型表达质量或科研正确性。
没有修改生产数据库、批准科研决定、采用 Snapshot、发布产品或推进 mission gate。

## 实际结果

| 需求／组 | 实跑结果 | 尚需继续 |
|---|---|---|
| ST-27／G-04 | Stage 3 进入原结构后有 Done；保存输入修订，返回原成文并关闭两侧面板。原生成版本、任务、OPEN 问题、阶段与阶段历史均不变 | 最终完整真实稿件流程复验 |
| RE-06／07／10／G-06 | A01 单条修改、A01＋A02 同时关联、单条解除、结束上下文、归档后普通修改、同 ID／同编号恢复均实跑。A02 始终保持 A02。归档 A01 后的新编辑没有挂回 A01 | 断线／跨标签归档／本地草稿恢复；完整返修生成与输出 |
| RE-03／04／05／G-07 | 单条内有空行仍为一条；重复可由作者保留或取消。101 条预览完整保留且导入被禁用；取消第 1 条、编辑第 101 条后，实际 HTTP 导入 100 条。第 101 条原文、编辑文本、原序号 100、全批原文均保存 | 浏览器完整文件上传、各格式错误与最大文件场景 |
| ST-02／04／G-03 | 刷新恢复 structure 模式、thought_reading、左右栏关闭与 Chat 收起；URL 同步这些状态。长列表滚动从 21313 恢复到 21304，差异 9 像素，页面总高度变化 8 像素 | 未同步内容的立即持久化、完整冲突副本恢复、选区／批注、折叠及 Catalog／总览位置 |
| ST-20／G-08 | 修复前空思想输入按 Delete，思想输入数变成 0；修复后仍为 1，原稳定 ID 与引用决定保留。拖动句柄的非 Delete 按键交给原键盘拖动处理 | 键盘拖动完整实跑、空容器、多选、分组、模板 |

界面实跑还发现两处遗漏并修复：修改已入库但意见计数没有刷新；实际 HTTP 请求模型按全部
预览条数限制 100，导致“101 条中选 100 条”仍被拒绝。接口测试已从直接调用服务改为真实
preview → import HTTP 路径，修复前失败、修复后通过。

## 测试与构建

- 新 Revision 契约与原 Studio、Scholar 阶段约束合计 **28 passed**，一个既有依赖警告。
- 现有完整 RSTV4 优化环境回归 **316 passed**，21 项既有依赖／API 警告；未运行真实模型优化。
- 当前前端类型检查、修改范围 Oxlint 与后台修改范围 Ruff 均通过。
- 生产构建首次在 client 阶段报 `memory allocation of 113088 bytes failed`；有限并行／1024 MB
  Node 尝试仍未完成。记录当时内存并关闭已完成的自建标签页、停止自己的预览进程后，保持
  相同源代码、`RAYON_NUM_THREADS=1` 与 `NODE_OPTIONS=--max-old-space-size=1024`，五个构建阶段
  全部完成，原始退出码 **0**。没有关闭其他应用、共享服务、研究任务或修改系统内存设置。
- 随后在显式 `127.0.0.1:3000` 启动自建的构建后页面，重新验证意见关联开始／结束和单条空行预览。
  该服务仅连接隔离 Studio 数据；它不是生产部署。

## 当前未通过的浏览器检查

文件选择入口已增加名称、键盘操作与焦点反馈，键盘 Enter 能打开文件选择器。
实际上传被 Chrome 扩展本地文件权限拦住。用户已同意临时开启并在验收后恢复；但浏览器
安全策略禁止助手进入扩展设置页，已请求用户手动开启，仍等待确认。助手未改动这项设置。
权限恢复关闭也必须由用户确认，不能假定已经恢复。

390×844 视口设置请求未改变实际渲染宽度（仍为 1920）；已 reset。
**窄屏验收没有通过，不把宽屏截图当成窄屏证据。**

## 实景

![Stage 3 Done 返回原成文，问题保持待处理](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/formal-ui-2026-10-03/stage3-done.jpg)

![原编辑布局中的 A01、A02 关联与结束控制](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/formal-ui-2026-10-03/revision-context.jpg)

原始隔离接口响应见同目录 `runtime-evidence.json`；重现测试见
[Revision 契约](C:/Users/Alandelone/CodeSpace_Local/RSTV4/tests/test_studio_revision_contracts.py)。
自建服务／验收数据位置在 UuMA 忽略目录 `.tmp/scholar-ui-fixes-services.json`，原文件备份在
`.tmp/scholar-studio-ui-baseline-2026-10-02`。构建完整日志在 `.tmp/scholar-ui-production-build.log`。

本批按[Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md)
补充表单名称、键盘文件入口、焦点、异步状态和长列表渲染；保留已精修的正式编辑布局与竖排标签。
