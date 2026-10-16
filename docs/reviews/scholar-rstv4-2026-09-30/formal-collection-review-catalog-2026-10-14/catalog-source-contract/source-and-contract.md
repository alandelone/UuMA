# CA07 已有真实资料来源（只读）

原句：多条 Sort 支持不同方向与优先级；默认更新倒序，相同值按 paper_id 稳定排序；每页 50 篇。未新增纸、seed、模型或任何DB写入。

找到本任务原始验收已经明确引用的DB：**C:/Users/Alandelone/CodeSpace_Local/RSTV4/data/catalog.db**，原证据 .tmp/scholar_acceptance_probe.py 的 PRODUCTION 常量、.tmp/scholar-acceptance-results.json、docs/reviews/scholar-rstv4-2026-09-30/acceptance-evidence.json。这里是已有真实Catalog生产资料，不能称为新合成软件seed资料；父代理只一致复制到新owned测试根运行UI。

原catalog schema_version=5（applied_at=2026-09-27 06:56:16），PRAGMA user_version=0；父代理副本明确迁移到105表/version13，新增表空，旧字段投影保持。当前只读核对：83表、3177个不同paper、1980隔离、**1197正式可见paper**，足够50分页。非空year80：2025×4、2024×8、2023×9、2022×18、2021×19、2020×19、2019×3；另1117条year=null、authors=[]，是真实完全同值大组，可验证paper_id稳定排序。updated_at无重复，故仅默认排序不能单独证明tie-break；用year/authors共同同值组。

源DB14,106,624B，SHA256 **24ade014972da14c8b2b03c7a506a89934c9e0e310048824806f97fdc5b9dff3**；只读查询前后原DB字节一致。采用node:sqlite DatabaseSync readOnly:true，仅已知任务文件对应的这一DB，未扫描其他DB或用户目录。原83表无逻辑写。

先前软件Catalog-selection/scoped-literature来源分别是1paper，当前Catalog列/筛选原生场景也只1paper，不足证明CA07分页。没有通过复制同一paper行或新seed制造足够条目。

## 父代理最小copied-fixture合同

- 新mkdtemp owned目录，源DB只读SQLite consistent backup；复制前后保留原83schema/rows和源raw摘要，副本当前服务constructor若迁移，只副本迁移、明确记录原行保持及新增空schema/版本时间变化。绝不把当前服务直接指向生产根。
- 网关deny全部任务；无worker/parser/extractor/实验/model；只读GET和正式只读POST /api/catalog/papers/query。CA07不打开PDF/不改源路径，不需拷贝任何权重或私人配置。启动完成后捕获稳定基线，UI后全部表/文件逻辑精确。
- 新空闲端口/自有tab；保留卡住IAB tab2与Writing Studio。不要为加速启用CPU减速/emulation。
- 默认updated desc验Page1/2各50、回Page1相同ID；独立排序全1197元数据核对。
- 混合Year desc＋Last Updated asc，观察同年时间升序；通过移除/重加调整为Last Updated asc＋Year desc，优先级应改变结果；原句没要求sort-row拖动，正式UI只有按添加顺序的优先级。
- 真正完全同值场景：正式Filter用Year is_empty AND Authors is_empty，得到1117；Sort=Year desc＋Authors asc，全部值相同，返回应严格paper_id asc。Page1前50、Page2后50、Previous回原前50；筛选/排序在翻页保持，无重复/漏项。source-audit.json保留全tie-ID与1197条排序元数据，父代理可独立计算期望，不用浏览器隐藏state/fetch。实际Filter树键需按正式控件构造，JSON合同中的filter是说明性结构，不能猜APIschema直接提交。

该子任务没有复制DB或启动UI/服务，CA07原生验收仍由父代理执行。未变更产品src/tests/scripts、共享session、HANDOFF、gate；未触碰原身份成功副本或保留卡页。
