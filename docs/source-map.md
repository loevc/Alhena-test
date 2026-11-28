# 固定基线的 Git 能力与源码入口

Alhena 使用官方 `idea/252.28539.166` / `b0d717640ee577a15b73fa79194629ff2a1d3d72` 源码。以下路径均对应这个已检出的提交，不使用 master 路径代替。上游主仓库下载后位于 `upstream/intellij-community/`。

| 能力 | 上游源码入口 | 本轮证据 |
| --- | --- | --- |
| 插件服务、动作、扩展注册 | `plugins/git4idea/resources/intellij.vcs.git.xml` | 产品仅捆绑 Git4Idea；构建内置模块自检通过 |
| Git 进程、命令结果与错误处理 | `plugins/git4idea/src/git4idea/commands/Git.java`、`GitImpl.java` | 提交、切换、同步及受控冲突均经原版 Git4Idea 执行 |
| 暂存、未跟踪文件、提交面板 | `plugins/git4idea/src/git4idea/index/ui/GitStagePanel.kt`、`GitStageCommitPanel.kt` | 原版 Stage All 与 Commit 控件，索引和提交结果双重验证 |
| 提交工作流与写入 | `plugins/git4idea/src/git4idea/index/GitStageCommitWorkflowHandler.kt`、`GitStageCommitter.kt`；`checkin/GitRepositoryCommitter.kt` | 普通空提交被拒绝；无文件差异的已解决合并可完成双父提交 |
| 取消暂存、丢弃 | `plugins/git4idea/src/git4idea/index/actions/GitFileStatusNodeAction.kt`、`StagingAreaOperation.kt` | `0ab35f94` 原版树选择与动作，索引、工作文件和其他暂存文件验证通过，见 `evidence/workspace-git-acceptance.json` |
| 按块暂存 | `plugins/git4idea/src/git4idea/index/GitStageLineStatusTracker.kt` | `0ab35f94` 原版行变更弹窗 Stage/Unstage 链接；两处分离改动只暂存第一块，第二块保持未暂存，取消暂存保留两块工作内容 |
| 分支操作 | `plugins/git4idea/src/git4idea/branch/GitBrancher.java`、`GitBranchWorker.java`；`branch/GitNewBranchDialog.kt` | 原版创建、重命名对话框及删除上下文动作；校验引用、当前分支、起点提交和干净工作区 |
| 提交图与列表 | `platform/vcs-log/impl/src/com/intellij/vcs/log/ui/frame/VcsLogMainGraphTable.java`、`MainFrame.java` | 5 条提交、分支和合并图；提交选择加载变更文件 |
| 分支树与过滤入口 | `plugins/git4idea/src/git4idea/ui/branch/dashboard/BranchesTree.kt` | main、feature/history 可展开；兼容补丁见下文 |
| 双栏文本 Diff | `platform/diff-impl/src/com/intellij/diff/tools/util/side/TwosideTextDiffViewer.java` | 原版双栏展示旧版两行、新版增加第三行，新增内容高亮 |
| 冲突读取与三方合并 | `plugins/git4idea/src/git4idea/merge/GitMergeProvider.java`；`platform/vcs-impl/src/com/intellij/openapi/vcs/merge/MultipleFileMergeDialog.kt`；`platform/diff-impl/src/com/intellij/diff/merge/MergeThreesideViewer.java` | 当前/基础/传入内容验证，原版 Merge 与 Accept Left，清除未合并索引 |
| Push | `plugins/git4idea/src/git4idea/push/GitPushOperation.java`；`platform/dvcs-impl/src/com/intellij/dvcs/push/ui/VcsPushDialog.java` | 原版对话框及 Push 按钮，本地裸仓库引用与提交哈希一致 |
| Fetch / Update | `plugins/git4idea/src/git4idea/actions/GitFetch.java`；`update/GitUpdateEnvironment.java`、`GitUpdateProcess.java` | 第二份克隆发布更新，原版 Fetch 和 Update Project 同步后校验引用与文件 |
| Clone / 认证 | `platform/dvcs-impl/src/com/intellij/dvcs/ui/DvcsCloneDialogComponent.kt`；`plugins/git4idea/src/git4idea/commands/GitHttpLoginDialog.kt` | `c9b5d639` 已实测专用 GitHub 仓库 HTTPS/SSH 克隆与认证、推送、同步、拒绝及取消；当前工作区包最终发布前仍需统一重跑 |
| Stash | `plugins/git4idea/src/git4idea/actions/GitStash.java`、`GitUnstash.java`；`stash/ui/GitStashContentProvider.kt` | `0ab35f94` 原版 Create Stash、Saved Patches 浏览器与 Apply，实际文件保存恢复通过 |
| Rebase / Cherry-pick | `plugins/git4idea/src/git4idea/rebase/GitRebaseDialog.kt`、`GitRebaseProcess.java`、`cherrypick/GitCherryPicker.java`；`platform/dvcs-impl/src/com/intellij/dvcs/cherrypick/VcsCherryPickAction.java` | 原版 Log 选择提交并 Cherry-pick；原版 Rebase 对话框选择上游，验证新父节点、提交重写及文件内容 |
| Blame / 文件历史 | `plugins/git4idea/src/git4idea/annotate/GitAnnotationProvider.java`；`history/GitFileHistory.kt`；`platform/vcs-impl/src/com/intellij/openapi/vcs/actions/TabbedShowHistoryAction.java` | 原版 Annotate 编辑器作者标注及文件历史界面；逐行哈希和文件历史两条提交由原版 Provider 与夹具预期核对 |

完整的固定源码可从 [官方提交树](https://github.com/JetBrains/intellij-community/tree/b0d717640ee577a15b73fa79194629ff2a1d3d72) 浏览；在该树下使用上述相对路径即可定位。能力调查的历史记录见 `idea-git-research.md`，其中 master 调查与早期 WPF 实验不能替代这里的版本依据。

重点源码直达：[Git 插件注册](https://github.com/JetBrains/intellij-community/blob/b0d717640ee577a15b73fa79194629ff2a1d3d72/plugins/git4idea/resources/intellij.vcs.git.xml)、[暂存面板](https://github.com/JetBrains/intellij-community/blob/b0d717640ee577a15b73fa79194629ff2a1d3d72/plugins/git4idea/src/git4idea/index/ui/GitStagePanel.kt)、[提交图](https://github.com/JetBrains/intellij-community/blob/b0d717640ee577a15b73fa79194629ff2a1d3d72/platform/vcs-log/impl/src/com/intellij/vcs/log/ui/frame/VcsLogMainGraphTable.java)、[双栏 Diff](https://github.com/JetBrains/intellij-community/blob/b0d717640ee577a15b73fa79194629ff2a1d3d72/platform/diff-impl/src/com/intellij/diff/tools/util/side/TwosideTextDiffViewer.java)、[Git 冲突数据](https://github.com/JetBrains/intellij-community/blob/b0d717640ee577a15b73fa79194629ff2a1d3d72/plugins/git4idea/src/git4idea/merge/GitMergeProvider.java)、[三方合并界面](https://github.com/JetBrains/intellij-community/blob/b0d717640ee577a15b73fa79194629ff2a1d3d72/platform/diff-impl/src/com/intellij/diff/merge/MergeThreesideViewer.java)。

## Alhena 自身代码

- `product/build/AlhenaProperties.kt`：产品组合、仅捆绑 Git、轻量 JBR、排除模块和构建属性。
- `product/src/alhena/AlhenaApplication.java`：独立默认设置、保留原动作对象的 Git 工具栏和菜单裁剪。
- `product/src/alhena/AlhenaProject.java`：ProjectActivity 与真实 Log 内容事件驱动的首次布局；后续保留用户布局。
- `product/src/alhena/HistoryAction.java`：等待原版 Log 内容就绪，通过已注册动作打开中央 Log，复用已有标签；没有跨模块类加载器直接引用 Log 实现。
- `product/src/alhena/AlhenaProjectStore.java`：通过平台 ProjectStorePathManager 服务将工程元数据隔离到 Alhena 配置目录，真实仓库根路径不变。
- `product/src/alhena/AlhenaDirectoryConfigurator.java`：单一 EMPTY_MODULE 内容根，模块文件写入外部存储，避免导入仓库原有 IDEA 工程模型。
- `product/src/alhena/AlhenaSourceFileTypes.java`：对指定且未知的源码文件名类型提供纯文本回退，避免大量读文件头，保留已有语言与二进制关联。
- `product/src/alhena/GitSettingsAction.java`：按 `vcs.Git` 配置 ID 直接打开原版 Git 设置页。
- `product/src/alhena/AlhenaWelcome.java`：Git 欢迎页，打开/克隆按钮委托平台原动作。
- `product/resources/ProductivityFeaturesRegistry.xml`：声明产品不提供额外 IDE 使用提示，满足平台必需资源约定；公共功能描述仍由平台加载。
- `product/src/alhena/AlhenaConsent.java`、`AlhenaUpdates.java`：独立产品的无使用统计策略和更新策略。
- `product/resources/alhena-excluded-modules.txt`：模块注册与打包共用的排除清单；`tools/workspace.py` 从上游 essential 描述符生成 AlhenaModules.xml。

## 两处受校验保护的源码补丁

`patches/upstream.json` 记录原始文件 SHA-256、唯一替换片段和理由。准备脚本拒绝版本漂移或覆盖用户手动编辑。

1. `BranchesTree.kt`：首次树展开调用需要读锁，将该小段切至 Dispatchers.EDT，保留平台线程检查。
2. `GitStageCommitPanel.kt`：把用户已包含、没有未解决冲突的 MERGING 仓库列入提交根，支持 Accept Left 后没有索引差异的合并提交。普通空提交仍由原工作流拒绝。

3. `VcsLogTabsManager.kt`、`IdeVcsLogManager.kt`、`OpenAnotherLogTabAction.java`：原版编辑器动作使用不返回 MainVcsLogUi 的打开入口，保留标签登记、文件监听和加载面板，避免异步初始化期间的空指针。原有需要同步 UI 的 API 保留。当前新包正在完整回归。

4. `ChangeListManagerImpl.java`：在 `projectClosing` 内先停止更新队列，再取消刷新任务，避免关闭期间刷新回调被恢复但服务尚未 dispose 的窗口期。保留后续幂等停止与队列原有断言。修复验证中。

5. `ApplicationLoader.kt`：仅 Alhena 启动分支统一取得原版懒加载 NOOP 遥测管理器，避免早期后台服务与异步 SDK 安装竞争。其他产品保持原路径，TelemetryManager 的单次初始化约束不变。

6. `WorkspaceModelCacheSerializer.kt`：只对 Windows 的 AccessDeniedException 做最多 20 次原子替换尝试，失败间隔请求休眠 10ms；保持原有不支持原子移动时的回退、临时文件 finally 清理和持续失败传播，并检查取消及保留线程中断。原版保存接口已复现旧包短暂读占用失败，新包专项三轮通过，完整同包回归、HTTPS中断恢复和精确源码托管构建已通过。

上述八个文件的补丁均需在升级上游时重新评估。其余产品界面调整位于 Alhena 层；本轮没有重写提交图、Diff、Merge 或 Git 命令执行实现。

高级功能验收见 `docs/evidence/advanced-git-acceptance.json`，运行 `tools/advanced-git-smoke.ps1` 复现。覆盖普通、无冲突的单仓库流程；强制删除、冲突型 Rebase/Cherry-pick 的继续与中止、逐行选择暂存等边界没有据此宣称完成。
