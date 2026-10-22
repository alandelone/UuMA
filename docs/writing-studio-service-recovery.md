# Writing Studio 启动与恢复

2026-10-21 修复：3000 前端与 8874 Studio API 均已恢复，8875 文献主界面保持运行。

## 原因与修复

原 Scholar 登录任务只启动 Catalog 8875，Writing Studio 的两项服务未纳入常驻启动。
同时 Studio API 的默认根目录指向工作区上层，而 Catalog 使用 RSTV4；现改为依次采用
显式参数、`RSTV4_ROOT`、RSTV4 包所在仓库，与 Catalog 保持一致。旧库保留，没有迁移或合并。

新增两个独立 Windows 登录任务 `UuMA Writing Studio Api`、`UuMA Writing Studio Web`。
登录后延迟 45 秒启动，以隐藏控制台运行；前端使用正式构建，分别仅监听本机 8874、3000。
子进程退出后由各自监督程序等待 5 秒再启动，监督程序异常退出也有任务级失败重试。
命名互斥锁和已存在服务检查防止重复启动；未知端口占用拒绝接管。没有重启 Catalog 或科研 worker。

## 使用

打开 [Writing Studio](http://127.0.0.1:3000/)，或从
[Scholar](http://127.0.0.1:8875/) 的“论文工作台”进入。
当前正式库没有 Track／Manuscript，工作台显示真实空态；没有为验证而创建研究或稿件。

安装／更新启动任务：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/install-writing-studio-services.ps1
Start-ScheduledTask -TaskName 'UuMA Writing Studio Api'
Start-ScheduledTask -TaskName 'UuMA Writing Studio Web'
```

前端源码变动后在 `writing-studio` 执行 `npm run build`，再安排仅 Web 服务的维护更新。
当前运行中的正式构建不应被不相关任务覆盖。安装会备份已有任务定义并保留明确禁用状态。
日志在 `.uuma-local/windows-service-logs/WritingStudio-*`，每次启动有独立 stdout/stderr 日志。

## 验证与边界

- 正式前端五阶段构建通过；Studio 根目录三项回归及既有写作服务测试共 12 项通过。
- API 健康、首页、同源 `/api/studio/tracks` 均 HTTP 200；7 个页面 JS/CSS 资源均 HTTP 200。
- 分别按精确进程身份结束本次启动的 API 与 Web 子进程，均由各自监督程序自动恢复并重新通过接口检查。
- 在数据库副本上先验证启动，再核对正式库 106 表与旧库 83 表全部行摘要／数量保持一致。
  主库总论文 3177，排除隔离记录后界面显示 1197；已核实与运行中 8875 的库路径身份一致。
- 没有运行模型、生成稿件、科研审批或实际投稿。当前工具未提供 Browser 技能需要的浏览器执行接口，
  因此本次验证为实际 HTTP、正式静态资源和服务恢复验证，未声称浏览器渲染／编辑交互验收。
- 已安装登录触发配置，没有通过真实 Windows 重启／重新登录验证。

原始库备份、旧构建、源文件备份和验证回执保存在
`.uuma-local/writing-studio-repair-20261021/`。原 118 项功能验收和 mission gate 不由本次运行修复推进。
