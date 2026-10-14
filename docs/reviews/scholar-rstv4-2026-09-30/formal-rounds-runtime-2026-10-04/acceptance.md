# Scholar 多轮返修实跑与生成格式修复：未通过验收

日期：2026-10-04 · Asia/Kuala_Lumpur。**118 条原要求、11 组范围全部保留，整体验收未通过。**

## 实际完成

- 多轮代码原批次的合并检查：92 项相关后台通过；17 项结构移动和 8 项真实键盘坐标函数检查通过；Ruff、前端类型、相关 Oxlint、差异检查通过。原始输出见 prior-merged-checks.log。
- 未修改前端源文件的这一版正式构建五阶段通过。原隔离数据库保留；核实进程和端口归属后，只重启自有 Studio 及前端。前端当前是 production_build_rounds_preview。
- 新软件验收稿第一次真实生成成功，5 种实际产物经 HTTP 200 取回，字节与注册本地文件一致，PDF 有实际文件头。真实第 1 轮建立并导入本轮软件 fixture 意见。
- 修改作者稿为修订 2 后，第二次真实生成失败：AttributeError，`'str' object has no attribute 'get'`。停止后未重放已完成生成、建立轮次、导入意见或作者保存。未建立第二轮、第三版或两轮投稿包。

## 本次修复及当前检查

失败位于原生成器直接遍历未经检查的 sentence_mappings。新增 studio_realization.py，明确返回格式、对象数组、整数句号索引、原作者 thought ID 完整覆盖、实际句子文字和对应区间；拒绝未知来源与不完整／伪造映射。一个作者想法允许对应多个实际句子，禁止猜补作者内容和句子区间。旧无句子文字的返回保留原映射，明确 sentence_positions_verified=false。

格式拒绝允许最多三次有明确错误反馈的模型调用，每次失败／拒绝／成功均在新增 studio_model_calls 表独立保存：实际输入及其摘要、真实返回、原模型契约、作者修订、任务和 job／Chat 消息关联。不重写原记录，未知模型保持未知；VALIDATED 只表示结构校验通过，不表示科学内容得到接受。普通 Chat 同样保存模型记录，不依赖存在采纳建议。提供所属稿件／job 检查的读取接口。

新增 17 项针对性检查实际通过（终端观察；非重建原日志）。随后当前合并回归实际为 **107 passed、2 failed、1 项既有依赖警告，77.15 秒**：

1. test_studio_context.py::test_generated_and_structure_discussions_return_original_version_after_deletion：新 model_call_id／model_contract 被加入 quoted，改变原有作者和助手共享的精确引文契约。
2. test_studio_context.py::test_real_numeric_citations_freeze_sources_and_preserve_underscore_keys：新模型及句子信息被加入成文 blocks，导致原版 artifact 读取与原 blocks 的完整相等性失败。

**这两处未修复，未修改或放宽原断言。** 下一步必须把新增来源信息与原引文／成文区块的稳定返回契约兼容起来，并验证真实模型记录与历史记录未知的区别。

回归失败后，检查驱动读取原始混合 UTF-8／Windows 编码日志又报 UnicodeDecodeError。原始字节完整保留在 current-merged-checks-raw.log，另存可读转写；驱动退出 1，没有因此声称后续静态检查通过。后续驱动应为子进程明确设置 UTF-8，而不是覆盖失败日志。

## 运行与验收边界

新生成格式／模型记录代码**尚未载入隔离服务，也没有新的真实模型或多轮成功实跑**。运行的后台仍是修复前多轮代码，前端文件与已构建的版本一致。native-round-flow.json 原顶层为 STARTED；其逐次 job 记录确实显示第一版 SUCCEEDED、第二版 FAILED，此处没有改写原始证据。原 92 项成功覆盖修复前 source snapshot，不代表新合并代码通过。

这次目标先返回 active，后最新 get_goal 返回 **paused**；助手未调用暂停／完成／阻塞，也未批准阶段门。暂停后只等待已启动回归收尾、读取实际结果并保存证据，没有开始新的模型／构建／服务重启／修复。

后续继续同一稿件 manuscript_bd7568923be94a2c8510d176010e4cca：当前作者修订 2，实际原生成版本及第 1 轮记录见原生流水证据，失败 job studio_job_c9266905897d4884bd68fce760315b3e。修复兼容性并通过当前回归后，验证自有进程、载入修复，仅从失败生成处继续；不得重新建立原稿或重复导入。

G-09 的后补关联／解除历史、最终页行与修改位置、回复断言、完整来源／输出仍待验收。G-08 的完整模板、待安置区、Subsection／L2，以及其他原组全部保留。普通讨论与生成模型记录的后台修复尚不能视作 G-05 整组通过。

浏览器文件上传由用户暂缓；助手未更改扩展权限，手动开启与验收后恢复关闭均未确认。新界面、拖动、轮次选择与窄屏均无浏览器实跑证据。本次没有正式研究数据写入、共享／科研服务重启、科研冻结文件编辑、科学接受或新增依赖。
