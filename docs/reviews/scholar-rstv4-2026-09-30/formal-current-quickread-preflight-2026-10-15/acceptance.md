# 当前新解析版 QuickRead 续验前置核查

本批只读定位并核对原任务，**没有运行 QuickRead，也不计新增验收通过**。原118及最终11组贯通继续。

GPU原任务仍SUCCEEDED / attempt6。其新parse_run_bb2661e7c11bb18dd684661073472d71对应原QuickRead任务job_fe4651959298eab54d88abd9edaf6760仍READY / attempt0 / fence0，未创建替代任务、未重跑旧模型。注册PDF1827字节、SHA85f4078a0ae99a5c0b13894ce4bbf511c7e9302958512e738b7180dae1110f99完整；身份VERIFIED，原成员关系存在，3个新解析正文块可读。

当前HTTP模型入口https://api.95963210.xyz/v1的非推理GET /models返回403。服务器明确给出Cloudflare 1010 / access_denied / browser_signature_banned，而不是可据此反复重试的任务等待。保留诊断，不更换客户端签名、不改凭据、不绕过封禁、不向其他地址自行提交。

独立预算核查还发现采集ACTIVE / revision3，但max_active_seconds为86400（24小时），观测累计125553.229113秒，dispatch_stop已返回预算耗尽。不能用run_once“试试看”：它会先持久暂停采集，而不会调用模型。本批没有这样改变状态。

创建请求未显式提供budget，首个预算事件与软件默认值一致；这不等于人类已批准无限运行。已准备有限恢复提案：仅原QuickRead、light档、同一个新parse；待授权入口恢复及用户同意后，按临执行累计时间加1800秒，保留500篇、10GiB和attempts=null三项原限额，保留所有旧计时与事件。完整limits传入现有语义预算接口，不只传一个字段后误套默认。累计时间持续增长，示例数值不能稍后原样提交。不执行深读或GPU；成功前不把旧AVAILABLE当新解析版证据。

所有105表和schema、原11份文件、注册源PDF及311份当前源码/测试均未改变；没有构造worker、schema迁移、预算修改、模型推理或浏览器操作。当前1130完整回归封存保持，不对未变源码重复全量测试。

浏览器上一轮URL判定停止问题仍待用户结束地址栏编辑；本批没有再次调用Computer Use，也不把自动目标续接当作用户已处理或预算授权。

见[当前核查](verification.json)、[原任务与源定位](evidence/preflight.json)、[403原诊断](evidence/gateway-diagnostic.json)、[独立预算审查](evidence/budget-audit.json)、[待审恢复提案](evidence/proposed-resume.json)。
