# Alhena 平台维护与升级

本文件定义固定平台的维护和后续升级门槛。[当前补丁与构建输入验收](evidence/cache-contention-maintenance-acceptance.json)，以及 [版本验收](evidence/version-maintenance-acceptance.json) 已验证独立产品版本、包内元数据、原版 About 展示及补丁保护。验证范围是当前锁定的平台；未来升级仍必须完整执行下列流程。

## 产品版本与平台版本

Alhena 当前开发版本是 `0.1.0-dev`，单一来源为 `product/resources/idea/AlhenaApplicationInfo.xml` 的 version/full 属性。原版 About 显示 `Alhena 0.1.0-dev EAP`；构建通过 appInfo.fullVersion 命名 ZIP，例如 `alhena-0.1.0-dev-252.28539.SNAPSHOT.win.zip`。EAP 明确表示开发候选，未代表正式发布。

应用描述符的 major/minor `2025.2` 和 Build `AL-252.28539.SNAPSHOT` 保留平台兼容含义。平台精确来源由 `upstream.lock.json` 的 tag、commit、applicationVersion 和 runtime 哈希共同确定。`AlhenaSandbox0.1` 只是保持配置兼容的目录标识，也不能替代产品版本。

`tools/workspace.py` 从同一描述符生成 `alhena-version.json`，同时记录产品版本、平台完整版本/tag/commit 和 JBR；该文件进入 app.jar，并复制到 ZIP 根目录供外部读取。构建出的 product-info.json 也使用相同产品版本。准备脚本拒绝不安全的版本字符串和被手工修改的生成元数据。28 项测试、ZIP 内实际资源与编译类对照、原版 About 控件和八组桌面门槛已通过。

产品版本递增和平台升级分别处理。源码提交与 ZIP SHA-256 继续记录在候选验收元数据中；未提交工作树只能记录基础提交和工作树摘要，不能宣称 ZIP 对应某个干净提交。正式发布仍需要精确源码提交、CI、Tag、附件和哈希关联。

保持 major/minor 与上游 build 分支兼容，避免把它们直接改成 `0.1` 导致平台构建校验失败。原版完整版本展示依据：

- `platform/build-scripts/src/org/jetbrains/intellij/build/ApplicationInfoPropertiesImpl.kt` 的 `fullVersionFormat` 和 `MessageFormat.format`。
- `platform/core-impl/src/com/intellij/openapi/application/impl/ApplicationInfoImpl.java` 对 `full` 属性的读取。
- `platform/platform-resources/src/idea/ApplicationInfo.xsd` 的 version/full 定义。
- 本项目 `tools/workspace.py` 的 `validate_version`。

## 工程隔离与产品策略

Alhena 覆盖平台 `ProjectStorePathManager`，在应用配置目录中按规范化仓库路径的 SHA-256 存储 `repositories/<哈希>/.idea`。末级目录必须为 `.idea`，固定平台的 JPS ProjectStoreBridge 以此解释相对存储路径。仓库 base path 仍为真实根路径；移动仓库会得到新的独立配置。

产品目录配置器创建一个 EMPTY_MODULE、一个真实仓库内容根，模块文件为外置 `.idea/repository.iml`。必须保留 `-Dide.create.fake.module.on.project.import=false`；默认平台配置器硬编码写入仓库 `.idea`，仅覆盖存储服务并不足以保护原工程。运行时需要同时检查模块数量、存储路径、真实 Git Stage/Unstage、重开恢复，以及仓库原有 `.idea`/`.iml` 全部路径和字节哈希。

文件类型覆盖器仅对指定源码扩展名且文件名类型为 UNKNOWN 时提供纯文本回退。已注册语言、用户文件名关联及二进制类型由原平台处理。升级后必须重跑实际 VFS 文件、已注册语言和显式二进制关联测试，不能用递归调用文件自身类型进行判断。

Alhena 的 bootstrap 分支统一取得平台懒加载 NOOP 遥测管理器，避免早期后台服务与异步 SDK 安装竞争；其他产品路径和 TelemetryManager 的单次初始化约束保留。产品验收明确检查 NoopTelemetryManager 与无 Span 导出器；使用统计许可由独立 AlhenaConsent 服务处理。

## 升级步骤

1. 保留当前候选 ZIP、哈希、源码提交、测试证据和旧平台 checkout。新版本使用独立 checkout；不在现有受保护补丁文件上直接切换上游分支。
2. 核对上游精确 tag/commit、许可、构建 JDK、发行 JBR 与下载哈希，再更新锁文件；不依赖移动分支或 latest。需要新下载的资料须重新核验官方来源。
3. 对每项补丁重新比较上游原始文件。`tools/workspace.py` 要求原始 SHA-256 正确、旧片段恰好出现一次、现有文件只能是原始内容或已打补丁内容。失败时停止并人工比较，禁止为了通过构建直接更换哈希或删掉保护。
4. 更新覆盖层后，检查生成的 essential modules、Git 插件布局、JPS 依赖和发行内容。核心产品类不能直接引用由插件模块类加载器提供的实现类；需要原版动作时优先通过注册动作及平台服务入口。
5. 执行 Python 测试及 Windows PowerShell 5.1/7 解析检查，联网 Package，核对 ZIP 中的实际类和资源。升级依赖缓存与旧平台分开保留，先不清理可回退环境。
6. 对同一新 ZIP 执行 `tools/desktop-gate.py` 和授权测试仓库的 `tools/remote-matrix.py`，重新采集性能样本。日志出现 SEVERE/ERROR 或非正常 VFS 恢复时，不把该次结果计作通过。
7. 完成精确源码提交、CI 实际运行、Tag、Release 附件和哈希关联后再发布。托管构建成功不能替代交互式 Windows 桌面验收。

## 受保护补丁与回归关系

| 补丁 | 必须保留的行为 | 对应验证 |
| --- | --- | --- |
| `BranchesTree.kt` 初始树更新切换 EDT | 分支面板真实展开，保留平台线程检查 | `tools/smoke.ps1` 的真实展开按钮、分支可见宽度和严重日志检查 |
| `GitStageCommitPanel.kt` 纳入无索引差异的 MERGING 根 | Accept Left 后仍生成双父合并提交；普通空提交仍拒绝；排除冲突或未选中的根 | `tools/workflow-smoke.ps1` 的空提交拒绝、三方冲突和无差异合并提交 |
| `VcsLogTabsManager.kt` / `IdeVcsLogManager.kt` / `OpenAnotherLogTabAction.java` | 原版编辑器动作允许返回加载面板，保留标签状态和同步 API，避免提前解引用尚未创建的 MainVcsLogUi | 多次全新仓库启动、扫描中打开 Log、标签复用和重启恢复；已通过当前同包桌面、独立启动和中央编辑器专用规模测量 |
| `ChangeListManagerImpl.java` 关闭监听器 | 在取消刷新指示器前 stop 队列并释放回调；保留刷新队列原有不变量检查 | 大工作树重开后立即关闭、五次 fresh 启动/退出、完整桌面与远程回归已通过 |
| `ApplicationLoader.kt` Alhena 分支 | Alhena 统一取得平台懒加载 NOOP 遥测管理器；其他产品和单次初始化约束保留 | 产品检查必须证明 NoopTelemetryManager、无 Span 导出器；多次首启及全套同包回归 |
| `WorkspaceModelCacheSerializer.kt` Windows 替换重试 | 只处理短暂 AccessDenied；持续拒绝仍可见，旧缓存不变，取消/中断和临时清理保留 | `tools/cache-contention-smoke.ps1`：20/40/60ms 释放、持久占用、原字节、中断及100次保存；旧29包负对照失败，新2a包三轮通过；完整同包回归、真实HTTPS中断恢复及托管构建均通过 |

当前验证范围是普通单仓库流程。冲突型 Rebase/Cherry-pick 的继续与中止、多根仓库组合、强制分支删除、逐行选择暂存和物理断网恢复需要单独扩展，不能由现有成功用例推断通过。旧 Windows 项目模型缓存 AccessDeniedException 观察仍保留，成功重跑不能证明根因已消除。

## 回退

保留旧 ZIP 与对应配置副本。跨平台版本不要复用测量的 system/index 缓存；正常退出后再切换版本。新版本失败时恢复旧 ZIP、旧配置和锁文件，不覆盖用户仓库工作内容，不修改全局 Git 身份或信任配置。


## Windows 缓存占用机制与回归

[精确复现](evidence/cache-rename-reproduction.json) 在随包 JBR `21.0.9+1-b1038.91` 上验证：普通读取句柄或内存映射占用目标时，`Files.move(ATOMIC_MOVE, REPLACE_EXISTING)` 可抛出 AccessDeniedException。通过实际 WorkspaceModelCacheImpl 调用得到与历史相同的 Serializer:93 / WindowsFileCopy:328 调用栈；释放后恢复，100 次未占用保存成功。原始失败中具体持有进程未留证，不能追溯指认某个应用或安全软件。

修复只对 Windows 的该异常做最多 20 次尝试，19 次请求 10ms 的等待；这是次数上限，实际耗时包含系统调度和文件 I/O，不能保证等于 190ms。持续占用仍抛出原异常，其他 I/O 错误不吞掉。原子移动不支持时的原回退保留，文件替换成功前旧缓存不动，临时文件始终清理。线程中断转为 InterruptedIOException 并保留标志；每轮检查平台取消。

[专项回归](evidence/cache-contention-acceptance.json) 覆盖三个短占用时长、持续拒绝、旧内容、反序列化、线程中断、临时文件以及100次后续保存，且三个独立进程正常退出。相同测试在旧29f137bb上首先因短占用失败，证明门槛能够检出缺陷。生产包不包含测试探针。底层接口参考 [Microsoft MoveFileExW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw) 和 [CreateFile/共享访问](https://learn.microsoft.com/en-us/windows/win32/fileio/creating-and-opening-files)。


## 已提交候选的跨设备复核

当前已验收产品源码提交为 `515baddbd59a5b0cfb88e73e80a6729af136fd87`。候选中的 `sourceBaseCommit` 保留构建时基线，`sourceCommit` 记录实际归档提交。审计工具、测试及关联记录已提交为 `f40b0ea`；该提交及远程 main 已由 `v0.1.0` 预发布 Tag 关联。发布附件 SHA-256 和大小与本地验收 ZIP、校验文件一致，见 `docs/evidence/published-release.json`；不代表产品重新构建或再次运行桌面验收。

在仓库根目录运行（Python 3.10+）：

```powershell
python tools/verify-source-association.py
python tools/verify-source-association.py --archive out/releases/alhena-0.1.0-dev-252.28539-2a71563a.win.zip
```

第一条只复核源码和已归档证据，不需要 SDK、缓存或原机器的绝对路径；输出 `archiveVerified: false`。第二条额外校验实际验收 ZIP。`docs/evidence/source-association.json` 记录实际提交的 Git 文件 SHA-256、测试 CI 文件摘要及历史原始摘要；它是随 Git 保存的审计声明，不是签名或独立重建证明。文本仅允许 CRLF 转 LF，保留 BOM、空白和末尾换行；二进制按原始字节比较。原门槛报告中的原始哈希继续保留，`desktop-gate.py --verify` 用于同一次运行的原始文件，不应用于经过 Git 换行转换后的归档副本。后续修改已关联的源码或证据会校验失败，应建立新候选并重新验收，不能直接重算摘要绕过。


`verify-source-association.py` 仅验证历史源码、证据与可选 ZIP，输出中的 `releaseReady: false` 表示该工具不查询发布状态。实际 GitHub 发布核验另记在 `published-release.json`。新发布状态记录可以随下次文档更新归档，无需移动已有 Tag 或重新上传相同程序包。


后续版本默认采用 [Tag 云端编译和自动发布](ci-release.md)，本地构建入口继续保留。旧 `v0.1.0` 的源码、附件和桌面验收关联不随新流水线更改。自动发布的 `ci-package.json` 明确记录托管验收范围；新生成的包不能沿用旧 ZIP 的桌面验收结论。
