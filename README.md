# Alhena

基于 IntelliJ Platform 的独立 Git 客户端，采用 **保留平台、裁剪产品** 路线，复用原版 Git4Idea、Git Log、Diff 与 Merge。当前目标是 Windows x64 便携 ZIP；历史 WPF 实验保存在 `experiments/wpf-history/`。

产品版本 **0.1.0-dev EAP**，固定平台 **2025.2.6.5 / Build 252.28539.SNAPSHOT**。中央工作区显示原版提交图，History 复用已有标签；提供暂存、提交、分支、Fetch、Update、Push 和 Git 设置入口，移除无关 IDE 主入口。

当前候选：`out/releases/alhena-0.1.0-dev-252.28539-29f137bb.win.zip`，250,141,421 字节。SHA-256：

```text
29f137bb7bc42ed16e1f2cfcf505de9210e4a2097041336115d3764a08b9df22
```

该候选已通过 [八组同包桌面回归](docs/evidence/current-desktop/result.json)、[七组真实远程回归](docs/evidence/current-remote/result.json) 和 [两类规模性能测量](docs/performance.md#当前候选中央编辑器专用测量)。当前源码 CI 检查与相同产品构建输入的托管 Windows 打包均成功；打包后仅修正测量工具，并另行完成检查和同包回归。源码提交、Tag、Release 附件及哈希关联尚未完成，**当前不是正式发布**。[候选审计](docs/evidence/current-candidate.json) 与 [执行计划](build-support/iteration-plan.json) 记录进度。旧候选及失败观察保留在证据文档中。

## 运行

解压程序包后运行 `bin/alhena64.exe`，在欢迎页打开或克隆仓库。运行需要本机可用的 Git，可在工具栏 Git 设置中配置其路径。随包携带官方轻量 JBR 21.0.9，无需另装 Java。也可使用脚本：

```powershell
.\run.ps1
.\run.ps1 -Repository 'D:\path\to\repository'
.\run.ps1 -Archive 'out\releases\alhena-0.1.0-dev-252.28539-29f137bb.win.zip' -Repository 'D:\path\to\repository'
```

脚本自动解压指定或最新程序包，使用 `out/sandbox/` 下的独立配置、缓存与日志。正常运行保留项目信任询问；`-Smoke` 自动信任仅限 `out/fixtures/` 内的专用测试仓库。

Alhena 将工程元数据存储到自身配置目录的 `repositories/<路径哈希>/.idea`，模块文件也位于其中。真实仓库根路径与 Git 索引保留；已有 IDEA 项目不会作为 Alhena 的工程模型导入。独立配置、IDE 更新、统计和原版 NOOP 遥测策略见 [维护说明](docs/maintenance.md)。

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

真实远程测试只在明确授权的 `loevc/Alhena-test` 中进行，临时仓库级 SSH 密钥在测试后撤销；Git 全局身份和信任配置保持不变。认证取消、拒绝和代理失败与物理断网恢复不同，后者尚未覆盖。多根仓库组合、冲突型 Rebase/Cherry-pick 的继续和中止等边界尚未扩展。

已准备 249,211 文件的真实上游工作树，以及含 2,381 条真实提交的 ripgrep 单分支历史。它们分别验证工作树规模和历史深度。[性能报告](docs/performance.md) 保留中位数、范围、失败样本和方法限制，不能由小夹具外推大仓库表现。

旧候选曾出现 Windows 工程缓存原子重命名 `AccessDeniedException`，根因仍未确定；后续成功回归不能证明已消除。见 [原始观察](docs/evidence/windows-cache-write-observation.json)。启动与关闭竞态的修复记录见 [启动记录](docs/startup-fix.md)。

## 项目结构

| 路径 | 内容 |
| --- | --- |
| `upstream.lock.json` | 上游版本、运行时哈希和构建入口 |
| `product/` | 独立产品、品牌、默认布局、配置隔离和平台构建桥接 |
| `patches/upstream.json` | 固定上游受保护补丁、基线 SHA-256 和修改理由 |
| `tools/`、`tests/` | 准备、构建、验收、测量和校验 |
| `build-support/` | 重建锁文件与当前迭代计划 |
| `.github/workflows/windows.yml` | Windows 检查及可选托管打包 |
| `docs/` | 源码地图、设计、维护和精简验收证据 |
| `upstream/`、`.cache/`、`out/` | 忽略的上游工作树、缓存、程序包与测试输出 |

运行 `tools/clean-generated.ps1` 预览约定范围内可清理的旧验收索引，加 `-Apply` 执行。清理保留源码、Git 仓库、发行包和编译依赖；原始日志与精简证据用于复核。
