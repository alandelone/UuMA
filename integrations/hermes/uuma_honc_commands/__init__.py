"""Read-only user guide. Examples are text, never configuration or activity writes."""

from __future__ import annotations

from typing import Any

GUIDE = """honc 操作指南

直接点击下方编号指令，一键直达各板块手册（无需复制输入）：

• 1. 习惯与打卡提醒：/honc_habits [/honc_1]
• 2. 休息、暂停与恢复：/honc_rest [/honc_2]
• 3. 工作进度与专注：/honc_work [/honc_3]
• 4. 补记、查询与更正：/honc_history [/honc_4]
• 5. 了解 Project Graph 回写：/honc_graph [/honc_5]

💡 常用操作场景直达指令（免复制，点击直接看例句）：
• 1.1 新增习惯常用句：/honc_habits_1
• 1.2 修改习惯提醒句：/honc_habits_2
• 1.3 习惯打卡记录句：/honc_habits_3
• 1.4 查看已有习惯：/honc_habits_4
• 2.1 专注中暂停休息：/honc_rest_1
• 2.2 恢复当前专注：/honc_rest_2
• 3.1 开始关联任务专注：/honc_work_1
• 3.2 补充任务进度：/honc_work_2
• 4.1 补记昨天的习惯：/honc_history_1

👉 点击复制发送，直接开始：
`新增一个习惯：午休，按分钟记录，不设提醒。`
`新增一个习惯：伸展，每天15:00提醒一次，按分钟记录。`
`记录午休习惯：今天午休了20分钟。`
`暂停当前专注，我要休息一下。`

习惯先建立，再记录；计划不算已经完成。
时间按马来西亚时间。看到保存成功的回复才算已记录。
/model、/new、/stop 沿用 Hermes 原生命令。"""

HABITS = """习惯与提醒

👉 场景直达指令（免复制，点击直达）：
• 1.1 新增习惯常用句：/honc_habits_1
• 1.2 修改习惯提醒句：/honc_habits_2
• 1.3 习惯打卡记录句：/honc_habits_3
• 1.4 查看已有习惯方法：/honc_habits_4

新增：
`新增一个习惯：午休，按分钟记录，不设提醒。`
`新增一个习惯：伸展，每天15:00提醒一次，按分钟记录。`
`新增一个习惯：阅读，每周一到周五21:00提醒一次，按分钟记录。`

修改：
`修改伸展习惯的提醒，改为每天16:00一次。`
`暂停伸展习惯。`
`恢复伸展习惯。`
`停用伸展习惯的提醒，保留这个习惯。`

记录已有习惯：
`记录伸展习惯：今天做了10分钟伸展。`
`记录午休习惯：今天午休了20分钟。`
`今天的伸展没做，记录为跳过。`

提醒默认每次一次；只新增习惯不会自动安排提醒。
多个时段可说明是哪一次，如 `上午九点那次`。
缺少必要信息时会补问；同名习惯会先核对。
查看已有习惯：直接说 `我有哪些习惯和提醒？`
返回总览：/honc"""

REST = """休息、暂停与恢复

👉 场景直达指令（免复制，点击直达）：
• 2.1 专注中暂停休息：/honc_rest_1
• 2.2 恢复当前专注：/honc_rest_2
• 2.3 记录休息习惯：/honc_rest_3
• 2.4 起床与睡前打卡：/honc_rest_4

① 专注中休息
`暂停当前专注，我要休息一下。`
`恢复当前专注。`
暂停时间不计入专注工时；结束回合不等于任务完成。

② 把休息当作习惯记录
先说 `新增一个习惯：午休，按分钟记录，不设提醒。`
实际休息后说 `记录午休习惯：今天午休了20分钟。`
要定时提醒，可说 `修改午休习惯的提醒，每天13:00一次。`
固定休息日可设置提醒只在指定星期触发；未设提醒不会自动催促。

③ 暂停某个习惯
`暂停午休习惯。`
`恢复午休习惯。`
暂停保留历史，并停止该习惯未发送的提醒。

④ 起床／睡前
`我起床了。`
`我准备睡觉了。`
默认起床08:00、睡前21:30；要修改请明确说时间。
目前只支持起床／睡前情境和固定时间、时间窗口提醒。
「休息时自动触发所有习惯」尚不支持。
返回总览：/honc"""

WORK = """工作进度与专注

👉 场景直达指令（免复制，点击直达）：
• 3.1 开始关联任务专注：/honc_work_1
• 3.2 补充已有任务进度：/honc_work_2
• 3.3 结束专注与收尾成果：/honc_work_3
• 3.4 报告完成与 Graph 同步：/honc_work_4

开始前说明任务和本轮成果：
`准备专注25分钟，关联任务〈任务ID〉，目标是写完登录测试，先打开测试文件。`
`开始当前专注。`

补充已有任务的进度：
`记录任务〈任务ID〉进度：写完了两项测试，用了30分钟；还差异常处理，下一步补异常测试。`
`记录任务〈任务ID〉进度：卡在接口权限，尚未完成。`

收尾：
`结束当前专注，成果是写完了两项测试，下一步补异常测试。`
`任务〈任务ID〉已经完成，验收依据是……，请核对完成标准。`

honc 会保留执行事实；不清楚具体任务时先核对。
普通进度保存在 honc 账本；明确报告任务完成时，会自动同步勾选 Project Graph。
须唯一关联普通任务、已有完成标准，并确认实际回执；连接失败不能说已同步。
项目拆分、里程碑和优先级交给 Yonc：/yonc
返回总览：/honc"""

HISTORY = """补记、查看与更正

👉 场景直达指令（免复制，点击直达）：
• 4.1 补记昨天的习惯：/honc_history_1
• 4.2 查看近期记录：/honc_history_2
• 4.3 更正与撤销记录：/honc_history_3
• 4.4 日记与身体状态：/honc_history_4

👉 点击复制发送，直接开始：
`补记昨天的伸展习惯：昨天做了15分钟伸展。`
`查看昨天的习惯记录。`
`查看午休习惯最近七天的记录。`
`刚才午休记错了，把20分钟更正为10分钟。`
`撤销刚才那条伸展记录。`

日记：`写日记：今天……`
身体：`记录身体状态：今天有点累。`
工作：`查看今天的工作日报。`

补记会保留发生日期和登记时间；不知道具体时刻就保留未知。
更正、撤销保留原记录和历史；不清楚是哪条时会先核对。
生活记录不会修改任务状态，也不会结束当前专注。
返回总览：/honc"""

GRAPH = """honc 与 Project Graph

• 工作进度、成果、下一步、卡点：先存 honc 执行账本。
• 关联任务的专注开始／结束：有 Graph 同步调用；是否成功需要另查实际结果。
• 任务明确完成：自动读取最新任务和完成标准，提交完成决策，再读回确认勾选。
• 习惯、休息习惯、身体、日记：存生活记录，不自动加入 Project Graph。
• 项目结构、里程碑、优先级：由 Yonc 管理（/yonc）。

所以「已记录进展」和「已同步到 Graph」是两种结果。
明确说 `今天完成了〈任务名称〉` 即可触发完成同步；不必再手动勾选。
同名、部分完成、缺少标准或需要专门复核时，会先保留事实并说明原因。
这是同步你的完成报告，不代表系统独立检验了产物。普通未完成进度仍只记入账本。

👉 点击复制发送：
`查看这项任务的完成回执和待同步事项`

本页是操作说明；查看本页不会发起 Graph 写入或确认连接正常。
返回总览：/honc"""


HABITS_1 = """习惯与提醒 · 1.1 新增习惯常用句

👉 点击复制发送，直接开始：
`新增一个习惯：午休，按分钟记录，不设提醒。`
`新增一个习惯：伸展，每天15:00提醒一次，按分钟记录。`
`新增一个习惯：阅读，每周一到周五21:00提醒一次，按分钟记录。`

返回习惯全览：/honc_habits | 返回总览：/honc"""

HABITS_2 = """习惯与提醒 · 1.2 修改习惯提醒句

👉 点击复制发送，直接开始：
`修改伸展习惯的提醒，改为每天16:00一次。`
`暂停伸展习惯。`
`恢复伸展习惯。`
`停用伸展习惯的提醒，保留这个习惯。`

返回习惯全览：/honc_habits | 返回总览：/honc"""

HABITS_3 = """习惯与提醒 · 1.3 习惯打卡记录句

👉 点击复制发送，直接开始：
`记录伸展习惯：今天做了10分钟伸展。`
`记录午休习惯：今天午休了20分钟。`
`今天的伸展没做，记录为跳过。`

返回习惯全览：/honc_habits | 返回总览：/honc"""

HABITS_4 = """习惯与提醒 · 1.4 查看已有习惯与提醒

👉 点击复制发送，直接开始：
`我有哪些习惯和提醒？`

返回习惯全览：/honc_habits | 返回总览：/honc"""

REST_1 = """休息与恢复 · 2.1 专注中休息

👉 点击复制发送，直接开始：
`暂停当前专注，我要休息一下。`

返回休息全览：/honc_rest | 返回总览：/honc"""

REST_2 = """休息与恢复 · 2.2 恢复当前专注

👉 点击复制发送，直接开始：
`恢复当前专注。`

返回休息全览：/honc_rest | 返回总览：/honc"""

REST_3 = """休息与恢复 · 2.3 记录休息习惯与定时

👉 点击复制发送，直接开始：
`新增一个习惯：午休，按分钟记录，不设提醒。`
`记录午休习惯：今天午休了20分钟。`
`修改午休习惯的提醒，每天13:00一次。`
`暂停午休习惯。`
`恢复午休习惯。`

返回休息全览：/honc_rest | 返回总览：/honc"""

REST_4 = """休息与恢复 · 2.4 起床与睡前打卡

👉 点击复制发送，直接开始：
`我起床了。`
`我准备睡觉了。`

返回休息全览：/honc_rest | 返回总览：/honc"""

WORK_1 = """工作进度与专注 · 3.1 开始专注新任务

👉 点击复制发送，直接开始：
`准备专注25分钟，关联任务〈任务ID〉，目标是写完登录测试，先打开测试文件。`
`开始当前专注。`

返回工作全览：/honc_work | 拆解项目：/yonc_split | 返回总览：/honc"""

WORK_2 = """工作进度与专注 · 3.2 补充已有任务进度

👉 点击复制发送，直接开始：
`记录任务〈任务ID〉进度：写完了两项测试，用了30分钟；还差异常处理，下一步补异常测试。`
`记录任务〈任务ID〉进度：卡在接口权限，尚未完成。`

返回工作全览：/honc_work | 返回总览：/honc"""

WORK_3 = """工作进度与专注 · 3.3 结束专注与收尾成果

👉 点击复制发送，直接开始：
`结束当前专注，成果是写完了两项测试，下一步补异常测试。`

返回工作全览：/honc_work | 返回总览：/honc"""

WORK_4 = """工作进度与专注 · 3.4 报告完成与 Graph 同步

👉 点击复制发送，直接开始：
`任务〈任务ID〉已经完成，验收依据是……，请核对完成标准。`
`查看这项任务的完成回执和待同步事项`

返回工作全览：/honc_work | 全部项目库：/yonc_projects | 返回总览：/honc"""

HISTORY_1 = """补记与更正 · 4.1 补记习惯

👉 点击复制发送，直接开始：
`补记昨天的伸展习惯：昨天做了15分钟伸展。`

返回历史全览：/honc_history | 返回总览：/honc"""

HISTORY_2 = """补记与更正 · 4.2 查看近期记录

👉 点击复制发送，直接开始：
`查看昨天的习惯记录。`
`查看午休习惯最近七天的记录。`
`查看今天的工作日报。`

返回历史全览：/honc_history | 返回总览：/honc"""

HISTORY_3 = """补记与更正 · 4.3 更正与撤销

👉 点击复制发送，直接开始：
`刚才午休记错了，把20分钟更正为10分钟。`
`撤销刚才那条伸展记录。`

返回历史全览：/honc_history | 返回总览：/honc"""

HISTORY_4 = """补记与更正 · 4.4 日记与身体状态

👉 点击复制发送，直接开始：
`写日记：今天……`
`记录身体状态：今天有点累。`

返回历史全览：/honc_history | 返回总览：/honc"""

SUBCARDS = {
    "habits_1": HABITS_1, "habits_2": HABITS_2, "habits_3": HABITS_3, "habits_4": HABITS_4,
    "rest_1": REST_1, "rest_2": REST_2, "rest_3": REST_3, "rest_4": REST_4,
    "work_1": WORK_1, "work_2": WORK_2, "work_3": WORK_3, "work_4": WORK_4,
    "history_1": HISTORY_1, "history_2": HISTORY_2, "history_3": HISTORY_3, "history_4": HISTORY_4,
}
SECTIONS = {"habits": HABITS, "rest": REST, "work": WORK, "history": HISTORY, "graph": GRAPH, **SUBCARDS}
ALIASES = {
    "habit": "habits",
    "habits": "habits",
    "honc_habits": "habits",
    "honc-habits": "habits",
    "_habits": "habits",
    "-habits": "habits",
    "习惯": "habits",
    "rest": "rest",
    "honc_rest": "rest",
    "honc-rest": "rest",
    "_rest": "rest",
    "-rest": "rest",
    "休息": "rest",
    "work": "work",
    "honc_work": "work",
    "honc-work": "work",
    "_work": "work",
    "-work": "work",
    "工作": "work",
    "history": "history",
    "honc_history": "history",
    "honc-history": "history",
    "_history": "history",
    "-history": "history",
    "历史": "history",
    "graph": "graph",
    "honc_graph": "graph",
    "honc-graph": "graph",
    "_graph": "graph",
    "-graph": "graph",
    "图谱": "graph",
    "help": "",
    "honc_1": "habits", "honc-1": "habits", "1": "habits",
    "honc_2": "rest", "honc-2": "rest", "2": "rest",
    "honc_3": "work", "honc-3": "work", "3": "work",
    "honc_4": "history", "honc-4": "history", "4": "history",
    "honc_5": "graph", "honc-5": "graph", "5": "graph",
}


def guide(raw_args: str = "") -> str:
    """Return a fixed page; never interpret trailing example text as an instruction."""
    key = (raw_args or "").strip().casefold()
    key = ALIASES.get(key, key)
    if not key:
        return GUIDE
    if key in SECTIONS:
        return SECTIONS[key]
    return "没有这个手册章节。用 /honc 查看目录；要新增习惯或记录事实，请另发一条日常消息。"


def register(ctx: Any) -> None:
    if ctx.profile_name != "honc":
        return
    ctx.register_command(
        "honc",
        guide,
        description="习惯、休息、工作和记录操作指南",
        args_hint="[habits / rest / work / history / graph]",
    )
    for section_name in ("habits", "rest", "work", "history", "graph"):
        desc = f"honc {section_name} 操作指南与提问引导"
        handler = lambda raw_args="", key=section_name: guide(key)
        ctx.register_command(f"honc_{section_name}", handler, description=desc)
        ctx.register_command(f"honc-{section_name}", handler, description=desc)

    # 1-tap numbered chapter jumps (/honc_1 to /honc_5)
    for num, s_name in enumerate(("habits", "rest", "work", "history", "graph"), start=1):
        h_num = lambda raw_args="", key=s_name: guide(key)
        ctx.register_command(f"honc_{num}", h_num, description=f"查看第 {num} 章：{s_name}")
        ctx.register_command(f"honc-{num}", h_num, description=f"查看第 {num} 章：{s_name}")

    # 1-tap direct scenario cards (/honc_habits_1 to 4, /honc_rest_1 to 4, /honc_work_1 to 4, /honc_history_1 to 4)
    for mod in ("habits", "rest", "work", "history"):
        for sub_i in range(1, 5):
            sub_key = f"{mod}_{sub_i}"
            h_sub = lambda raw_args="", key=sub_key: guide(key)
            ctx.register_command(f"honc_{sub_key}", h_sub, description=f"honc {mod} 场景 {sub_i}")
            ctx.register_command(f"honc-{mod}-{sub_i}", h_sub, description=f"honc {mod} 场景 {sub_i}")
