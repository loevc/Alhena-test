# Alhena

独立的 Windows Git 桌面客户端，研究并逐步复现 IntelliJ IDEA 的 Git 工作流与可视化体验。

当前是 **0.1 历史浏览器原型**：使用真实本地 Git 数据，支持打开仓库、分支筛选、拓扑提交图、提交搜索、变更文件和双栏文本 Diff。界面为 WPF，无需启动 IDEA、浏览器服务或 Node。

## 运行

要求 Windows 10/11、.NET Framework 4.8，以及已加入 PATH 的 Git。当前采用系统 Framework 编译器，不需要安装 .NET SDK 或下载 NuGet 包。

```powershell
.\build.ps1 -Run
```

也可以在编译后双击 `build\Alhena.exe`，或指定仓库：

```powershell
.\build\Alhena.exe D:\path\to\repository
```

点击「打开仓库」，或在顶部输入目录并按 Enter。左侧点击分支会筛选历史，不会切换工作区分支；选择「所有分支」恢复全仓库历史。F5 刷新引用与提交。「加载更多」每次增加 300 条。搜索只覆盖已加载提交的标题、作者、哈希和引用。

## 当前边界

- 所有功能均为只读，没有暂存、提交、checkout、fetch/pull/push。
- 合并提交的文件和 Diff 与第一父提交比较；初始提交与空树比较。
- 图轨道代表父子关系，不代表固定分支；当前批次底部的连线可能延伸到尚未加载的父提交。
- 搜索隐藏不匹配行，图仍沿用完整批次的轨道；隐藏区间尚未绘制折叠连线。
- 双栏显示带上下文的 patch，支持新增、删除、修改、重命名；二进制仅显示 Git 说明。超长行用省略号显示，悬停查看全文；没有语法高亮、三方合并或行内单词差异。
- Diff 预览约限 20,000 行；Git 输出仍先完整读取，超大 diff 的内存优化尚待实现。
- 每次加载重新读取当前上限范围，尚未实现持久缓存和增量分页。后台查询设有 30 秒超时；新选择会丢弃旧结果，旧进程在完成或超时前仍会运行。
- 尚未测试 bare 仓库（使用 `--show-toplevel`，目前只支持有工作区的仓库）、子模块工作流或打包安装器。
- 深色布局已完成运行截图验证；尚未测量启动耗时和内存，暂不作性能承诺。

如果 Git 报 `dubious ownership`，应用会原样显示错误，不会自动修改全局 Git 信任配置。请在确认目录归属后自行配置 Git，或使用当前用户拥有的仓库。

## 验证

```powershell
.\build.ps1 -Test
```

测试创建独立临时仓库，验证空仓库、存在其他引用的 unborn HEAD、中文和特殊路径、拓扑顺序、合并第一父提交差异、重命名、游离 HEAD、图轨道回收、octopus 合并和错误传播。随后启动真实 WPF 窗口，验证提交/文件/Diff 联动、搜索清理旧详情及分支筛选，并生成 `build\preview.png`。界面测试需要交互式 Windows 桌面。临时仓库路径记录在 `build\fixture-path.txt`，供手工复查；测试不会修改开发仓库历史。

## 结构

| 文件 | 职责 |
| --- | --- |
| `src/Git.cs` | 无 shell 的 Git 进程调用、NUL 分隔解析、提交/引用/文件/patch 查询 |
| `src/Graph.cs` | 与 WPF 解耦的拓扑轨道计算 |
| `src/App.cs` | WPF 界面、虚拟化提交列表、图绘制、异步选择联动、双栏 Diff |
| `tests/Tests.cs` | 真实 Git 仓库集成检查及图算法检查 |
| `tests/UiTests.cs` | 真实 WPF 窗口集成检查及截图 |

源码研究和后续路线见 [docs/idea-git-research.md](docs/idea-git-research.md)。
