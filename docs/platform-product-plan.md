# IntelliJ 平台裁剪产品：执行计划与初始证据

决策日期：2026-11-26。用户选择保留 IntelliJ 平台并裁剪产品；WPF 独立实现路线停止扩展。当前 A–E 计划已完成并核对证据：准备、构建、原版基本 Git 工作流、首轮产品界面与模块裁剪，以及同机重复测量均通过。本文件保留初始调查与构建证据，最终状态以文末交付验收为准。

## 基线与理由

固定官方标签 `idea/252.28539.166`，提交 `b0d717640ee577a15b73fa79194629ff2a1d3d72`，其 `community-resources/resources/idea/IdeaApplicationInfo.xml` 声明版本 2025.2.6.5。标签和提交已通过官方 Git remote 核实。

先使用这个发布基线的 JPS 构建路径，避免将当前 master 的 Bazel 迁移作为首轮产品裁剪的额外变量。固定版本不是升级承诺，也不代表它具有 master 调查中提到的所有能力。后续安全更新需要重新评估、迁移覆盖文件和重跑验收。

官方来源：

- [固定提交](https://github.com/JetBrains/intellij-community/tree/b0d717640ee577a15b73fa79194629ff2a1d3d72)
- [ProductProperties](https://github.com/JetBrains/intellij-community/blob/b0d717640ee577a15b73fa79194629ff2a1d3d72/platform/build-scripts/src/org/jetbrains/intellij/build/ProductProperties.kt)
- [IdeaCommunityProperties](https://github.com/JetBrains/intellij-community/blob/b0d717640ee577a15b73fa79194629ff2a1d3d72/build/src/org/jetbrains/intellij/build/IdeaCommunityProperties.kt)
- [产品打包布局](https://github.com/JetBrains/intellij-community/blob/b0d717640ee577a15b73fa79194629ff2a1d3d72/platform/build-scripts/src/org/jetbrains/intellij/build/ProductModulesLayout.kt)

## 产品组合

`AlhenaProperties` 直接继承 `ProductProperties`，不继承 `IdeaCommunityProperties` 或 `BaseIdeaProperties`，避免直接带入 IDEA 默认的 Java、Kotlin、Maven、Gradle 等插件集合。第一轮 bundled plugin 列表只有 `intellij.vcs.git`，Git 内部的 content modules 和传递依赖仍由上游机制决定。

自定义 `alhena.product` 资源模块提供 `AlhenaApplicationInfo.xml` 和 `AlhenaPlugin.xml`。核心描述符首先保留：

- `PlatformLangPlugin.xml`：上游平台核心服务与动作注册。
- `essential-modules.xml`：上游基本运行模块集合。
- `vcs-modules.xml`：VCS 平台模块集合。
- 最小定制、Local History、协作工具模块，用于第一轮兼容性验证。

这仍然是较宽的平台外壳，包含部分分析、执行、调试等通用基础模块。没有语言插件不等于完全不加载 PSI、项目模型或索引基础设施。第一轮先建立可启动基线，之后按运行证据逐组缩减，不能预先声称已经没有索引或具备低内存优势。

产品名称、启动器前缀及配置选择器独立：Alhena / alhena / AlhenaSandbox0.1。上游 `computeAppInfoXml` 要求产品主次版本与 252 构建系列匹配，验证包的 ApplicationInfo 使用 2025.2，而不是自定义 0.1 主次版本。保留上游 LICENSE 和 NOTICE；本阶段不制作公开发布的安装包。

## 首次静态依赖结果

使用 `tools/workspace.py audit` 分析 `.idea/modules.xml` 和 `.iml`：

- 索引到 1,207 个模块。
- 从产品、starter、Git、Log、Diff 入口可达 187 个非测试 JPS 模块。
- 当前闭包内未解析依赖为 0。
- 模块注册表中仍有 288 个当前工作树不可用的模块文件，包含外部仓库或其他产品模块；闭包无缺失不代表整个上游项目都能编译。

统计包含 COMPILE、RUNTIME、PROVIDED，排除 TEST。它没有模拟完整 JPS 导出规则，因此这是构建依赖调查结果，不是最终最小模块清单。

另行扫描产品与 Git 描述符，遍历了 69 个 XML、发现 74 个 content module ID；两个未解析 include 分别为 compose.xml、GraphPlugin.xml，均有可选 fallback。扫描器在整个项目 source roots 中寻找 include，不模拟真实 classloader 搜索顺序、XPointer、loading mode、服务/扩展点或反射依赖，不能替代打包和运行验证。

## 里程碑与验收

| 阶段 | 工作 | 验收证据 |
| --- | --- | --- |
| A：准备与调查 | 固定源码、产品覆盖文件、构建入口、静态依赖报告 | 准备可重复执行，版本校验通过，报告可生成 |
| B：编译 | 上游 bootstrap、Alhena 构建目标、Git/Log/Diff 编译 | 编译退出码 0，保留日志，记录下载和环境问题 |
| C：产品启动 | Windows ZIP、独立配置目录、打开本地仓库 | 原版 Git Log、分支树、提交选择和 Diff 可用，启动日志无阻断错误 |
| D：原版工作流 | 暂存、提交、分支切换、冲突解决、远程同步 | 使用专门临时仓库验收；远程写操作仅使用测试远程 |
| E：裁剪与测量 | 分组裁剪无关平台模块与界面，重复回归 | 对比模块清单、发行包体积、启动和内存；无 Git 功能回退 |

第一轮不会通过修改 Git4Idea 实现来掩盖平台服务缺失。先从产品模块注册和发行布局修正；确需改上游时记录文件、理由及覆盖方式。

## 首次构建调查

- 已下载并使用上游 bootstrap 指定的 JBR SDK 17.0.14-b1376.4。
- Ant 的 JPS bootstrap 编译成功，首次耗时 9 分 47 秒；这不是 Alhena 产品编译成功。
- JPS 成功加载 1,207 个项目模块和 308 个项目库，随后进入项目依赖解析。
- `platform/jps-bootstrap/src/main/java/org/jetbrains/jpsBootstrap/JpsBootstrapMain.kt` 中的 `downloadOrBuildClasses` 明确调用全项目依赖解析。上游注释解释，部分 Kotlin 编译器插件依赖不能从模块结构完整推导，因此需要预先下载所有依赖，包括未使用的项目库。
- 本轮保留上述机制，不通过跳过解析或关闭依赖校验来缩短首次构建。构建准备的下载范围与最终产品运行范围需要分别统计。
- 核心 Compile 入口退出码为 0；指定入口及传递依赖的首次干净编译耗时 7 分 26 秒。上游 `intellij.vcs.git` 的 Java/Kotlin 源码已实际编译。这不等于运行时可用。
- 发行桥接也已编译通过。它从上游实际平台与插件布局收集生产模块，编译后复用当前输出，避免 `buildDistributions` 默认请求编译全部上游模块。
- 首次 Package 在布局收集阶段因 `intellij.platform.identifiers.highlighting.shared` 不在公开仓库模块表中而失败。该模块在 essential 描述符中是可选模块；按上游 `IdeaCommunityProperties` 使用 `skipUnresolvedContentModules=true`。上游仅对非 required/embedded 模块应用这个过滤，必需模块检查保留。
- 可选模块处理后，实际发行布局收集了 263 个生产模块入口并完成增量编译（36 秒）。这是传给 JPS 的入口数，不是最终装载数或传递闭包大小。
- 随后的布局检查发现 `ProductModulesLayout` 默认插件布局列表会校验没有捆绑的 Android 设计器，触及外部仓库模块。Alhena 现在只保留 `intellij.vcs.git` 对应的上游插件布局，和 bundled plugin 选择保持一致。
- 首次运行自检发现 VCS 因缺少 `intellij.libraries.microba` 而被禁用。补入该实际依赖后，`listBundledPlugins` 与设置 UI 遍历自检均已通过，生成了 `AL-builtinModules.json`；插件清单为 Git4Idea 和平台核心 com.intellij。自检不代表真实仓库交互已验收。
- Windows 原生启动器要求至少八张 ICO 图像；原创图标已补齐 16/20/24/32/40/48/64/256 尺寸，启动器生成通过。
- 固定基线的 `ProductProperties` 默认选 JCEF 运行时。Alhena 改用官方 `JetBrainsRuntimeDistribution.LIGHTWEIGHT`（无 JCEF/DCEVM），避免捆绑 Git Log 和文本 Diff 不需要的浏览器运行时；Git Log 与双栏 Diff 的实际 GUI 验收已通过。

## Windows ZIP 与 GUI 验收证据

2026-11-26，Package 退出码 0，产物为 `upstream/intellij-community/out/alhena/artifacts/alhena-252.28539.SNAPSHOT.win.zip`，250,456,345 字节（约 239 MiB）。本次已验收包 SHA-256：`467740179b77df22c996297cdfb4db2d1ab14f686bf4193a922c38a18763c026`。重新构建含时间戳，哈希可能变化。随包 JBR 为 21.0.9+1-b1038.91，仅捆绑 vcs-git 插件目录。

Java 下载器在当前网络下曾停留于零字节；`tools/prefetch-runtime.ps1` 改为使用 curl 从同一官方端点预取，严格检查锁文件中的大小和 SHA-256，再放入上游预期缓存位置，没有绕过内容校验。

真实启动额外修复了两个问题：

1. 独立厂商没有 JetBrains 默认统计同意资源，平台查询产生空指针。使用上游 `idea.disable.collect.statistics=true` 和 `idea.suppress.statistics.report=true` 禁用采集与上报，不伪造厂商或用户同意。
2. 固定源码中的 `FilteringBranchesTree` 在 `launchOnShow` 的严格 UI 调度器内首次展开树；`TreeUtil.expandAll` 内部需要 ReadAction，触发 `LockAccessDisallowed`。仅将首次 `updateTree()` 放入 `withContext(Dispatchers.EDT)`，遵循上游读写锁约束。补丁记录在 `patches/upstream.json`，验证官方文件 SHA-256、唯一匹配和本地编辑，准备脚本重复执行安全。没有全局关闭线程检查。此为已记录的 Git4Idea 源码兼容修复，后续升级需重新评估。

对应原始源码：

- `platform/statistics/src/com/intellij/internal/statistic/utils/StatisticsUploadAssistant.java`
- `platform/platform-impl/src/com/intellij/ide/gdpr/ConsentOptions.java`
- `plugins/git4idea/src/git4idea/ui/branch/dashboard/BranchesTree.kt`
- `platform/ide-core/src/com/intellij/util/ui/uiScope.kt`
- `platform/platform-api/src/com/intellij/util/ui/tree/TreeUtil.java`

`tools/smoke.ps1` 在专用仓库执行可重复 GUI 验收，记录：

- 从 ZIP 解压后通过原生 alhena64.exe 启动，使用独立配置与缓存。
- 分支树可展开 main、feature/history；原版提交表显示 5 条提交和合并图。
- 选中 Describe side-by-side diff，变更列表加载 history.txt。
- 调用原版 Show Diff，在双栏中显示旧版两行和新版新增第三行，高亮新增内容。
- 本轮启动和交互日志没有 SEVERE/ERROR 条目；探针仅操作测试进程，结束后关闭它。

首轮通过证据：`out/gui-smoke/20261126-143625/result.json`、`git-log.png`、`commit-diff.png`；启动日志：`out/smoke/20261126-143627/log/idea.log`。外部探针不打包进产品，截图只绘制应用自身 Swing 窗口。这是小型本地仓库验收，不是长时间稳定性或性能基准。

早期外壳仍带有 Add Configuration、Problems、Services、新 UI 引导和平台更新通知；本轮已完成对应产品边界调整。后续原生首次启动测试也验证了配置目录不存在的路径，未通过修改平台启动代码规避配置导入。

## 原版工作流验收（阶段 D）

2026-11-26，`tools/workflow-smoke.ps1` 完整通过。证据：`out/workflow-smoke/20261126-152437/result.json`，对应 ZIP SHA-256 `c4a86e5e2c6fa16fecf48cb5f48347914d452e94a55171e4c460b13dc1c21f4a`；该包另存于 `out/baseline/alhena-baseline.win.zip`，作为后续裁剪比较基线。

本轮通过原版动作或控件完成：Stage All、Commit 按钮、GitBrancher 分支往返切换、Push 对话框及按钮、Fetch、Update Project 选项与确认、冲突列表、三方 Merge 和 Accept Left，再通过原版提交面板完成合并提交。Git CLI 仅用于建测试数据、驱动独立 peer，以及读取索引、提交、分支、远程引用和工作区结果；被测操作在 Alhena 的 Git4Idea 内执行。

测试仓库、本地裸远程和 peer 均位于 `out/fixtures/workflow-20261126-152436/`。Fetch 后远程跟踪引用和 peer HEAD 一致，Update 后本地 HEAD 和 peer HEAD 一致。冲突提供器 CURRENT / ORIGINAL / LAST 分别为 current / base / incoming version；接受当前版本后未合并索引清空。最终提交 `64e68d9356b62d67f75129838c277b62e358b738` 有两个父提交，MERGE_HEAD 已清除，工作区干净。本次全新启动和交互日志没有 SEVERE/ERROR。

过程中发现并修复了固定基线暂存区的真实边界问题：接受当前版本后，索引没有文件差异，但仓库仍处于 MERGING，原版面板会误判为空提交。`patches/upstream.json` 中第二处补丁将“已包含且没有冲突的 MERGING 仓库”加入 rootsToCommit，继续交给原版 GitStageCommitWorkflow 和 GitRepositoryCommitter 执行，不允许普通仓库任意空提交，不包含用户排除的仓库。该条件仍需随上游升级回归。

早期探针使用 Swing 调度导致的读写锁和 TransactionGuard 报错属于验收工具问题。现已改用 Application.invokeAndWait/invokeLater，并传递实际模态上下文；最终证据来自修复后的探针和全新测试进程，不以早期探索日志作为通过依据。

## 测量约定

建立可运行基线后再报告性能。记录机器、Windows、JBR、源码 SHA、仓库规模和配置状态；区分首次配置、首次仓库扫描、已有缓存启动。每类重复多次，记录中位数和范围。

启动分别记录进程创建、主窗口可交互、Git Log 首屏可用；内存分别记录空窗口、仓库首屏稳定、后台任务结束后的进程工作集与 JVM heap。磁盘上的插件缺失、插件未启用和模块未实际加载是三个不同指标，不能互相替代。

## 产品裁剪与最终验收（阶段 E）

最终产物：`out/releases/alhena-252.28539-c2bc63bb.win.zip`，250,135,557 字节（238.55 MiB）。SHA-256：`c2bc63bb4f326057d7816107e17196e20d0d9908330c4cfbefed467257a84f99`。源码固定提交、官方轻量 JBR 与前述基线一致。

产品层现在提供 Git 工具栏、默认暂存和历史布局、打开/克隆仓库欢迎页；工具栏使用原动作对象，不重新实现 Git 操作。默认布局由 ProjectActivity 和 Log 内容加入事件驱动，只有首次打开仓库时应用，保留后续用户布局。主菜单的 Run / Build / Code / Analyze / Refactor 入口与运行配置工具栏已移除，TODO、Services、Bookmarks、Problems、Structure、新 UI 引导等工具窗口不再作为产品可用入口。Files/Project 浏览器仍可由用户打开。

自动 IDEA/插件更新、插件推荐和使用统计已关闭；独立 ConsentOptionsProvider 始终返回不允许发送统计，不假冒 JetBrains 同意或许可状态。源码、Diff 编辑器、VFS、项目模型、部分 PSI/索引与共享执行 API 继续保留。

`alhena-excluded-modules.txt` 同时驱动 AlhenaModules.xml 生成和发行布局，实际移除：

- intellij.platform.clouds
- intellij.platform.execution.serviceView、execution.serviceView.frontend
- intellij.platform.execution.dashboard、execution.dashboard.frontend、execution.dashboard.backend

最终 ZIP 的 6 个对应 JAR 均不存在；压缩包比裁剪前减少 321,230 字节（约 0.31 MiB）。模块注册清单从 74 个 content ID 减少到 68 个，静态非 TEST JPS 可达模块仍为 187；这不等于实际装载类或运行时模块数。上游 BundledPluginsLister 会枚举已启用插件的全部 contentModules，不能把其 layout 清单直接当成每个模块的运行时启用或类装载证据。

同机三类场景各有 3 个正式测量样本，缓存启动另做预热，全部通过平台退出流程保存配置和 VFS。早期强制结束进程的数据含 NOT_CLOSED_PROPERLY，已排除。最终样本没有 VFS 崩溃恢复、SEVERE 或 ERROR，末次内存采样要求索引结束且公开进度任务连续两次为空。统计为隐藏窗口 Swing/EDT 探针观测，包含 Attach/轮询开销，不清空 OS 文件缓存，不强制 GC。

结果：任务结束后工作集中位数分别从 486.0 / 721.6 / 689.6 MiB 变为 462.5 / 701.2 / 671.1 MiB（空窗口 / 新索引仓库 / 缓存仓库）。启动时间和 heap 范围有明显重叠，不能宣称显著提速或低内存架构。基线本身已经是早期 Alhena 外壳，并非完整 IDEA。详细范围与硬件信息见 [性能报告](performance.md)，原始样本已归档到 `docs/evidence/`。

| 阶段 | 最终证据 | 状态 |
| --- | --- | --- |
| A：准备与调查 | 锁文件、重复准备/本地编辑保护/版本漂移测试、187 个生产依赖闭包无缺失 | 通过 |
| B：编译 | Package 退出码 0，源码/描述符与 JPS 输出核对，ZIP 中 Alhena class 与当前编译输出逐字节一致 | 通过 |
| C：产品启动 | `out/gui-smoke/20261126-192545/result.json`：分支、5 提交合并图、变更选择、原版双栏 Diff | 通过 |
| D：原版工作流 | `out/workflow-smoke/20261126-192527/result.json`：暂存/提交/空提交拒绝/分支往返/Push/Fetch/Update/三方合并/无差异合并提交 | 通过 |
| E：裁剪与测量 | `out/product-smoke/20261126-192515/result.json`、6 JAR 移除、同机清洁退出测量、功能回归无严重错误 | 通过 |

以上三组运行验收和最终测量均对应同一个最终 ZIP 哈希。`tools/verify-delivery.py` 的 66 项交付核对通过，包括实际仓库双父提交、干净索引/工作区、版本和覆盖文件、打包 class、许可证、模块排除、正常缓存退出及同机测量；详见 [交付审计](evidence/delivery.json)。六项 Python 准备/依赖保护测试和 PowerShell 语法检查也通过。

## 验收边界与复现

本轮交付是 Windows x64 本地单体 Git 产品。网络同步使用专用本地裸仓库和独立 peer 验证；没有使用用户仓库或外部远程写入。SSH/HTTP 认证矩阵、超大仓库、长期稳定性和 Rebase/Stash/Blame 等扩展功能没有逐项回归；其原版源码继续保留，入口见 [源码地图](source-map.md)。这些未列入本轮 A–E 基本工作流验收，不作为本轮已验证能力宣传。

```powershell
.\build.ps1 -Action Prepare
.\build.ps1 -Action Audit
python -m unittest discover -s tests -v
.\build.ps1 -Action Compile
.\build.ps1 -Action Package
.\tools\product-smoke.ps1
.\tools\workflow-smoke.ps1
.\tools\smoke.ps1

# 使用准备好的裁剪前 ZIP 与新包，串行测量，避免构建/其他测试同时运行。
.\tools\measure.ps1 -Archive out/baseline/alhena-baseline.win.zip -Label baseline-clean
.\tools\measure.ps1 -Archive upstream/intellij-community/out/alhena/artifacts/alhena-252.28539.SNAPSHOT.win.zip -Label trimmed-clean
```

本轮原始测量路径为 `out/measurements/baseline-clean-20261126-193237/results.json` 和 `out/measurements/trimmed-clean-20261126-193414/results.json`。新测量使用新的时间目录，再用 `tools/summarize-measurements.py` 生成中位数/范围报告。`tools/distribution-report.py` 比较真实 ZIP；`tools/verify-delivery.py` 把对应的三个验收结果、两组测量和最终 ZIP 重新核对。重新构建会改变包哈希，不能沿用旧验收记录。
