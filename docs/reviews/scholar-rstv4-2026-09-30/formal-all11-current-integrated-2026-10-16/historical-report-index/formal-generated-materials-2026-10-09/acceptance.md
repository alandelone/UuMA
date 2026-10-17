# 六种原素材进入固定成文、PDF 和投稿包：修复与实跑验收

已修复素材只停留在作者区／ID 记录、没有进入成文和编译稿的问题。PNG、JPEG、SVG 图片和 CSV、XLSX、Markdown 表格现在使用同一份固定素材快照进入成文页面、Markdown、LaTeX、PDF 和投稿包；完整表格不再取六行小预览。原文件按字节保留，素材缺失、损坏或不属于稿件时明确拒绝生成。

本轮还修复了 Windows 长路径导致图片无法编译、十行小表被拆开、表格标题挤在同行而使右侧内容越出纸面三个实际问题。保留原失败日志、旧 PDF／ZIP 和逐页截图，修复后重新实跑，没有覆盖旧成文版本。

## 最终验证

- 最终完整回归 **1051 passed / 20 warnings**；相关套件 **67 passed**，其中六格式／字节与所有单元格／腐败拒绝／独立编译／16 位 PNG 等新增素材契约为 9 项。前端 15 项检查和后台／目录 23 项检查全部通过。392 个源码文件在最终回归前后相同，封存时再次核对。
- Chrome 实际点击生成、定稿、投稿包和下载入口。稿件 `manuscript_3c63372cb2ae406d977def5953d53b59`，作者修订 r3（原目的编辑后撤销，最终完整作者文档与原始 r1 精确相同），当前固定成文 v3 `manuscript_version_02338a596162441587a28d1c0ee72dbf`。CSV、Markdown 各十行及表头、XLSX 十行与第二工作表逐格对应原文件；三幅图实际加载，刷新后的内容和固定链接相同。
- 新下载 PDF `manuscript (2).pdf`，SHA256 `9dd3f477ab1f5a30121ece889cd752d0855a002409babb7948437616cee89972`；**三页实际图像逐页检查通过**，三图和所有表格完整、标题在表上方、没有右侧裁切；独立 Poppler 位置检查同时通过。原 v1 的右侧越界证据继续保留。
- 新下载 ZIP `submission_package_35c16c352e1141cab6cdccf692821500.zip`，60906 字节，SHA256 `0543ab72fe33fe1bd57ad783910f6e374f1b57d242ed17b657c5d7320306f05e`；**25 个文件**全部 CRC、名称、大小及固定清单哈希一致。六个原文件、三份渲染图及全部编译依赖在包内；包内 PDF 与新下载 PDF 完全相同。解包到独立目录后，真实编译返回 0。
- 独立核对 109 表，所有旧记录和其他稿件不变；当前作者完整原文／ID／素材顺序不变，旧三个生成版本均通过当前严格读取，旧产物和下载文件保持。没有数据库迁移。上轮下载报告 20 个、作者对应报告 872 个密封文件再次完整核对。

## 实跑范围与继续项

| 原要求 | 本轮证明 | 尚不能由本轮证明 |
| --- | --- | --- |
| ST-19 | 六种正式格式保留；作者小预览与成文完整素材分别实看；编译、冻结和整包交付 | 浏览器上传权限仍按此前边界；所有复杂文件／公式和科学素材场景还须完整原范围验收 |
| ST-16 | 原素材文件名、SHA、版本、固定文件可查，旧版本不追随实时文件变化 | 全部 Evidence 原文、精确页段与上下文回查 |
| WF-03 | 当前完整作者输入、顺序、素材、模型调用输入与固定快照一致，刷新可回读 | 全部真实科学来源／模板／引用组合 |
| WF-06 | 声明的软件原文未重写；所有五个主产物成功登记，真实编译和拒绝路径通过 | 真实模型对科学命题、条件和强度的合格保持 |
| RE-14 | 新旧包共存、原文件和依赖完整、真实下载及独立编译通过 | 本例没有审稿意见和被审轮次，不能据此证明完整返修六件材料质量 |

原 **118 条要求／G-01 至 G-11** 全部保留，**11 组整体验收仍未完成**。本素材批次不关闭 G-05 数字引用、G-09 完整来源与返修，其他历史证据也不因本轮被重写。3 次段落实跑调用均明确标为 `TEST_FIXTURE_MATERIALS_NATIVE`，远程真实模型调用为 0；软件通路通过不代表科学内容获得批准。任务继续保持 active，mission 仍为 verification / pending_review，未推进 gate。

## 可核对产物

[新 PDF](downloads/manuscript-v3.pdf)、[新 ZIP](downloads/submission-package-v3.zip)、[独立核对回执](evidence/scholar-generated-assets-native-audit-v3/receipt.json)、[逐页视觉核对](pdf-visual-review.json)、[最终回归](evidence/scholar-generated-assets-full-v2.log)、[完整原要求](original-118-and-11-scope.md)。

![浏览器中新旧固定版本同时保留](evidence/scholar-generated-assets-native-proof-v2/package-v3-and-retained-v1.png)

![完整表格和 XLSX 第二工作表](evidence/scholar-generated-assets-native-proof-v2/generated-v3-full-tables.png)

![修复后的 PDF 第三页](evidence/scholar-generated-assets-native-audit-v3/render/page-3.png)

SVG 渲染使用声明依赖 resvg-py 0.5.0，PNG/JPEG 使用 Pillow；实现依据：[维护者 API 文档](https://resvg-py.readthedocs.io/en/latest/api.html)。冻结和哈希保护由本项目实际验证。
