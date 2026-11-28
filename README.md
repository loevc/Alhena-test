# Alhena

基于 IntelliJ Platform 的独立 Git 客户端，采用 **保留平台、裁剪产品** 路线，复用原版 Git4Idea、Git Log、Diff 与 Merge。当前目标是 Windows x64 便携 ZIP；历史 WPF 实验保存在 `experiments/wpf-history/`。

产品版本 **0.1.0-dev EAP**，固定平台 **2025.2.6.5 / Build 252.28539.SNAPSHOT**。中央工作区显示原版提交图，History 复用已有标签；提供暂存、提交、分支、Fetch、Update、Push 和 Git 设置入口，移除无关 IDE 主入口。

当前候选：`out/releases/alhena-0.1.0-dev-252.28539-2a71563a.win.zip`，250,141,729 字节。SHA-256：

```text
2a71563a782d2c7ef6e9d00e9b7c1cade03a316ff416184616c6d1558f278bdc
```

该候选已通过 [八组同包桌面回归](docs/evidence/cache-contention-desktop/result.json)、[七组真实远程回归](docs/evidence/cache-contention-remote/result-reconciled.json) 和 [两类规模性能测量](docs/performance.md#当前候选中央编辑器专用测量)。同一精确源码 `115279f` 的 CI 检查和完整托管 Windows 打包均成功。另通过原版缓存读占用专项，以及真实 HTTPS 数据传输中断/恢复补测；CI 附件与本地已验收 ZIP 的哈希分别记录。产品源码 `515badd` 的 70 个构建/测试输入与成功打包的 CI 提交 `115279f` 一致。审计补充已提交为 `f40b0ea` 并推送，[v0.1.0 开发预发布](https://github.com/loevc/Alhena/releases/tag/v0.1.0) 的 Tag 指向该提交，两个附件的大小和 SHA-256 均已核验。产品仍为 **0.1.0-dev EAP**；[发布关联记录](docs/evidence/published-release.json) 保留核验范围。[候选审计](docs/evidence/current-candidate.json) 与 [执行计划](build-support/iteration-plan.json) 记录进度。旧候选及失败观察保留在证据文档中。

## 运行

解压程序包后运行 `bin/alhena64.exe`，在欢迎页打开或克隆仓库。运行需要本机可用的 Git，可在工具栏 Git 设置中配置其路径。随包携带官方轻量 JBR 21.0.9，无需另装 Java。也可使用脚本：

```powershell
.\run.ps1
.\run.ps1 -Repository 'D:\path\to\repository'
.\run.ps1 -Archive 'out\releases\alhena-0.1.0-dev-252.28539-2a71563a.win.zip' -Repository 'D:\path\to\repository'
```

脚本自动解压指定或最新程序包，使用 `out/sandbox/` 下的独立配置、缓存与日志。正常运行保留项目信任询问；`-Smoke` 自动信任仅限 `out/fixtures/` 内的专用测试仓库。

Alhena 将工程元数据存储到自身配置目录的 `repositories/<路径哈希>/.idea`，模块文件也位于其中。真实仓库根路径与 Git 索引保留；已有 IDEA 项目不会作为 Alhena 的工程模型导入。独立配置、IDE 更新、统计和原版 NOOP 遥测策略见 [维护说明](docs/maintenance.md)。

## 云端开发与发布

日常本机只需编辑源码、提交和推送。普通分支运行自动检查；推送新的 `v*` Tag 后，GitHub Actions 自动在云端 Windows 上编译、测试、打包、创建 Release 并上传 ZIP、SHA-256 和构建记录。本机无需编译；本地 `build.ps1 -Action Package` 和离线构建能力继续保留。

参见 [云端编译与 Tag 自动发布](docs/ci-release.md)，包含版本与 Tag 对应规则、手动云端试编译、失败重试和自动验收范围。工作流变更提交并推送后生效，已有 Release 保持原有内容。

## 固定源码与重建

- 上游：`JetBrains/intellij-community`
- 标签：`idea/252.28539.166`
- 精确提交：`b0d717640ee577a15b73fa79194629ff2a1d3d72`
- 环境：Windows x64、PowerShell、Git、Python 3.11+、curl.exe。构建使用 JPS bootstrap 的 JBR，不依赖 PATH 中的旧 Java。

```powershell
.\build.ps1 -Action Prepare
.\build.ps1 -Action Audit
python -m unittest discover -s tests
.\build.ps1 -Action Package
```

程序包输出至 `upstream/intellij-community/out/alhena/artifacts/alhena-0.1.0-dev-252.28539.SNAPSHOT.win.zip`。重新构建包含不同时间戳，必须重新计算哈希和执行验收。

首次联网准备会下载固定上游和依赖。Git 保存源码、覆盖层、受保护补丁、脚本及锁文件；`upstream/`、`.cache/`、`out/` 排除。离线跨设备重建还需要另外保存并校验依赖包，参见 [离线重建与提交范围](docs/offline-rebuild.md)。依赖包不同于供用户运行的便携 ZIP。

覆盖工具先验证上游提交和补丁原始 SHA-256，拒绝覆盖本地手动修改。`out/reports/dependencies.json` 是静态 JPS 依赖可达性报告，不等于最终运行时模块清单。[固定版本源码地图](docs/source-map.md) 提供 Git 能力与对应源码；[平台维护](docs/maintenance.md) 说明版本、升级、补丁和回退流程。

## 验收与边界

```powershell
python tools/desktop-gate.py --archive '<明确的候选ZIP路径>'
```

完整桌面门槛串行执行原生选择/切换、PS5.1/PS7、产品、提交图/Diff、基本工作流、工作区及高级 Git 八组回归，检查同一个 ZIP 与源码摘要。探针通过 JDK Attach 操作自建进程中的原版动作和 Swing 控件，不打进发行包，不使用用户仓库作为变更夹具。

真实远程测试只在明确授权的 `loevc/Alhena-test` 中进行，临时仓库级 SSH 密钥在测试后撤销；Git 全局身份和信任配置保持不变。已验证认证取消、拒绝、代理失败，以及 HTTPS 传输中断后错误通知、引用/文件保护和恢复 Fetch/Update。补测仅设置专用仓库本地代理，不改全局网络；物理 NIC 拔断和 SSH 传输中断仍未覆盖。多根仓库组合、冲突型 Rebase/Cherry-pick 的继续和中止等边界尚未扩展。

已准备 249,211 文件的真实上游工作树，以及含 2,381 条真实提交的 ripgrep 单分支历史。它们分别验证工作树规模和历史深度。[性能报告](docs/performance.md) 保留中位数、范围、失败样本和方法限制，不能由小夹具外推大仓库表现。

Windows 工程缓存替换在目标被读取或映射占用时可触发 `AccessDeniedException`，已通过原版接口复现同栈并验证短占用重试修复。持续拒绝仍报错，旧缓存内容、临时清理及中断语义保留；原始持有进程未留证，不能指认具体应用。见 [复现](docs/evidence/cache-rename-reproduction.json) 和 [专项回归](docs/evidence/cache-contention-acceptance.json)。启动与关闭竞态的修复记录见 [启动记录](docs/startup-fix.md)。

## 项目结构

| 路径 | 内容 |
| --- | --- |
| `upstream.lock.json` | 上游版本、运行时哈希和构建入口 |
| `product/` | 独立产品、品牌、默认布局、配置隔离和平台构建桥接 |
| `patches/upstream.json` | 固定上游受保护补丁、基线 SHA-256 和修改理由 |
| `tools/`、`tests/` | 准备、构建、验收、测量和校验 |
| `build-support/` | 重建锁文件与当前迭代计划 |
| `.github/workflows/windows.yml` | Windows 检查、手动托管打包与 Tag 自动发布 |
| `docs/` | 源码地图、设计、维护和精简验收证据 |
| `upstream/`、`.cache/`、`out/` | 忽略的上游工作树、缓存、程序包与测试输出 |

运行 `tools/clean-generated.ps1` 预览约定范围内可清理的旧验收索引，加 `-Apply` 执行。清理保留源码、Git 仓库、发行包和编译依赖；原始日志与精简证据用于复核。
