# 首轮观察记录

首轮新增后端用例：14 通过、1 失败，92.41 秒／1 项既有警告。
打包确实失败，结构化错误为 RevisionConflictError／Replies, associations or author reviews changed during packaging；新测试错误地对整个 error 字典查找消息字符串。后续改成检查 error.message，保留失败和阻止写包的断言。首轮结果来自该轮工具输出，此文件是观察摘要，不是原始测试日志。

原 Ruff 导入排序、无障碍 label／output 和受控异步等待失败日志另行完整保留。UI 控制测试改为完整等待有界异步保存链，断言不放宽；正式产品修复标签关联和语义 output。没有用这些受控检查冒称浏览器验收。
