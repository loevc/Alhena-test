# IDEA Git 研究与 Alhena 实现路线

> 历史记录：本文描述早期 master 调查与 WPF 实验。2026-11-26 用户已选择保留平台、裁剪产品；当前路线、固定版本与验收见 [platform-product-plan.md](platform-product-plan.md)。本文中的 WPF 实现状态不代表当前 IntelliJ 平台版状态。

研究日期：2026-11-26。以下链接使用 JetBrains 官方仓库的 master 路径，内容会随上游变更。当前没有复制 JetBrains 源代码；Alhena 的命令适配、图布局和 WPF 视图独立实现。后续如引入源码，需逐文件记录版本、来源及适用许可证。

## 上游入口

| 入口 | 研究问题 | Alhena 对应部分 |
| --- | --- | --- |
| [plugins/git4idea](https://github.com/JetBrains/intellij-community/tree/master/plugins/git4idea) | Git 专属命令与平台适配如何组织 | `Git.cs` |
| [platform/vcs-log](https://github.com/JetBrains/intellij-community/tree/master/platform/vcs-log) | 通用日志数据、图和视图如何拆分 | `Graph.cs` + 历史视图 |
| [GitImpl.java](https://github.com/JetBrains/intellij-community/blob/master/plugins/git4idea/backend/src/commands/GitImpl.java) | 下一步阅读：命令封装和执行错误如何处理 | Git 进程层扩展 |
| [VcsLogGraphTable.java](https://github.com/JetBrains/intellij-community/blob/master/platform/vcs-log/impl/src/com/intellij/vcs/log/ui/table/VcsLogGraphTable.java) | 下一步阅读：表格选择、图绘制和操作如何结合 | 提交表格与 GraphCell |
| [vcs-log/graph](https://github.com/JetBrains/intellij-community/tree/master/platform/vcs-log/graph) | 下一步阅读：压缩、筛选和复杂 DAG 的处理 | 图布局下一阶段 |

本轮核对了 Git4Idea 和 vcs-log 官方目录，以及 Git log/diff 文档。上述具体 Java 类作为后续精读入口，本轮未完成逐方法研究，不能把目前实现描述为 IDEA 算法移植。

## 当前技术决策

先做 Windows 原生桌面版。使用 WPF 的窗口、虚拟化 DataGrid 和 DrawingContext 绘图，不加载编辑器、索引、语言服务等 IDE 子系统。本机无 .NET SDK，初版使用系统自带 .NET Framework 4.x 编译器及 WPF 引用；语言特性保持 C# 5 兼容。后续迁移到现代 .NET SDK 项目后，再补发布、性能测量及更完善的取消机制。

Git 是独立子进程：直接传参，不经过 shell；stdout/stderr 并发读取，非零退出码作为错误。全局使用 literal pathspec，文件名在 `--` 后传入；patch 禁用 external diff 和 textconv。查询不会修改全局 Git 配置。

日志来自 `git log --all [HEAD] --topo-order -z`，每条记录包含完整哈希、父提交、作者、时间、引用和标题，字段用 NUL 分隔。分支筛选使用完整 refname，避免显示名称歧义。详见 [git-log 文档](https://git-scm.com/docs/git-log)。

文件变更以 NUL 分隔的 name-status 读取，重命名保留两个路径。合并提交明确使用第一父提交进行比较，初始提交使用 root diff。详见 [git-diff 文档](https://git-scm.com/docs/git-diff)。

## 提交图基础算法

1. 输入为子提交先于父提交的拓扑序。
2. active lanes 记录各轨道等待出现的提交哈希及颜色。
3. 当前哈希已存在时使用对应轨道；否则添加新轨道。
4. 移除当前节点，以第一父提交续接当前轨道，额外父提交创建轨道；父提交已有轨道时复用。
5. 将每行顶部的旧轨道映射到行底部的新轨道，绘制穿过该行的线、入节点线和出节点线。
6. 图行附着在提交模型上，由虚拟化单元格按需绘制。

轨道不是分支。分支只是某个提交上的引用，不能给每个分支固定一列。当前算法是用于验证真实历史的基础布局，还没有实现 IDEA 的图压缩、隐藏节点桥接、跨页稳定布局和复杂历史下的交叉优化。

## 分阶段交付

| 阶段 | 范围 | 当前状态 |
| --- | --- | --- |
| 0.1 | 本地仓库、分支树、提交图、搜索、变更、双栏 Diff | 原型已实现，真实仓库和 WPF 集成检查通过 |
| 0.2 | 可用性：现代 SDK 工程、可取消查询、增量加载、缓存、完整提交信息、Diff 可读性及图布局优化 | 待做 |
| 0.3 | 工作区、暂存/取消暂存、提交、切换分支 | 待做；需仓库写操作串行化、失败恢复和刷新策略 |
| 0.4 | fetch/pull/push、认证、进度和取消 | 待做 |
| 0.5 | stash、cherry-pick、rebase、冲突解决、局部暂存 | 待做 |

下一轮优先测量大仓库首屏加载和快速选择行为，再改进 Diff 与提交图；日常 Git 写操作建立在这一基础上。
