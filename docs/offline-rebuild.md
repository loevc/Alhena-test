# 离线重建与跨设备交接

保存两份配套材料：Git 保存 Alhena 源码、上游版本锁、补丁、构建及恢复工具；离线 ZIP 保存固定上游 Git 对象、bootstrap JDK、Maven 构件和上游下载缓存。离线包的 SHA-256、逐文件清单哈希和源码指纹写入 `build-support/offline.lock.json`，该小文件提交 Git。大 ZIP 放入制品存储或移动硬盘，至少保留一份独立副本；Git 仓库不能代替依赖备份。若发布平台有单文件大小限制，应先分卷。仅保存 Git LFS 指针也不能替代备份实际包文件。

## 提交清单

唯一清单是 `build-support/source-manifest.json`，运行 `python tools/offline-kit.py list` 查看实际文件。建议提交：

```powershell
git add .gitattributes .gitignore README.md upstream.lock.json build.ps1 run.ps1 build-support product patches tools tests docs experiments/wpf-history
git diff --cached --stat
git status --short
```

`product/build/`、`product/platform-build/` 是 Kotlin 构建源码，`product/alhena.product.iml` 是 JPS 输入，必须提交。根 `/build/` 才是输出目录。两处 Git4Idea 修改保存在 `patches/upstream.json`；其余产品覆盖文件与生成规则在 `product/` 和 `tools/workspace.py`。

根 `.idea/` 不参与构建，排除本机 IDE 配置；上游自己的 `.idea` 随固定源码恢复。`.gitattributes` 固定文本 LF，避免跨设备检出改变补丁和源码字节。旧 WPF 实验一并归档源码，其构建输出仍排除，不参与当前产品编译。

不要执行 `git add -f upstream out .cache`：这些目录含嵌套 Git 仓库、测试远程、IDE 配置、编译状态和日志，不能作为可迁移的依赖方案。也不使用全局 `*.zip`、`*.jar` 或 `*.iml` 忽略规则，避免误忽略未来有意维护的构建输入。

## 离线包内容

| 内容 | 保存与恢复方式 |
| --- | --- |
| Alhena 源码快照 | 根据提交清单收集，文本规范化 LF，带逐文件哈希；可恢复完整新工作区或核对已有 Git 检出后只恢复依赖 |
| 固定 IDEA 源码 | 保存 Git 对象与浅克隆边界，先检查缺失对象；恢复为无远程、无个人配置的独立 Git 仓库，再检出固定提交 |
| 上游修改与覆盖 | 保存补丁和 Alhena 原文件；Prepare 校验后重新应用 |
| bootstrap JDK 17.0.14 | 保存项目 `.cache/bootstrap/` 中的 JDK 和完成标记，恢复到新工作区相对位置 |
| Maven 依赖 | 保存指定 `.m2/repository`，排除失败/临时下载；恢复到 `.cache/offline-home/.m2/repository`，构建单独设置 `user.home` |
| 构建下载归档 | 保存上游 `build/download` 顶层完整 JAR/ZIP/tar；在新路径重新解压，不沿用含绝对路径哈希的旧提取缓存 |
| 编译输出、JPS 缓存、旧发行包 | 不进入重建依赖包，从源码重新编译 |

不复制个人 Maven `settings.xml`、SSH 密钥、Git config/hooks、用户目录或环境变量。指定 Maven 仓库中的构件会整体备份，可能包含其他项目构件，以保留 Ant POM 传递依赖和 JPS 全项目解析所需依赖。以后若要减小范围，应先用独立 Maven 仓库完成构建和离线回归，再从该仓库导出。

支持 **Windows x64 → Windows x64**，允许更换盘符、用户和工作目录。目标机仍需预装 Git、Python 3.9+ 和 PowerShell；ZIP 不包含这些安装器，可在交接介质中另存经过校验的离线安装包。不承诺 macOS、Linux 或 Windows ARM 构建主机。

## 导出与保存

先完成 Package，在没有其他构建或下载并发时导出：

```powershell
python tools/offline-kit.py export --archive out/offline/alhena-offline-windows-x64-252.28539.zip
python tools/offline-kit.py verify --archive out/offline/alhena-offline-windows-x64-252.28539.zip
```

默认读取当前用户 `.m2/repository`；可明确传入 `--maven-repository X:/dedicated/repository`。确认指定仓库确实用于成功构建。导出拒绝覆盖已有 ZIP，新版本使用新文件名；同时更新并提交 `build-support/offline.lock.json`。ZIP 旁生成同内容的 `.zip.json`，一起复制到离线介质。

导出会拒绝未归入 `product/` 或 `patches/` 的上游修改、额外文件、覆盖文件漂移，以及自定义上游模块注册，避免只备份 Git 基线而丢失实际参与编译的手工改动。

包内源码对应导出时快照；锁文件与后生成的 `offline-validation.json` 不进入源码指纹，避免哈希循环。改动源码、工具或文档后，应重新导出配套包；旧包仍能恢复原快照。在已恢复工作区修改源码但不引入新依赖时，可以继续离线开发和编译。

若还需要完整 Alhena Git 历史，提交后另外执行 `git bundle create X:/backup/Alhena.bundle --all`，或保存 Git 镜像。离线 ZIP 含源码快照，不含本项目 Git 历史。当前已验收的便携发行 ZIP 也应独立保存为 Release 附件。

## 在另一台设备恢复

使用本仓库恢复工具，将 ZIP 和配套 `.zip.json` 恢复到不存在的新目录：

```powershell
python tools/offline-kit.py restore --archive X:/backup/alhena-offline-windows-x64-252.28539.zip --lock X:/backup/alhena-offline-windows-x64-252.28539.zip.json --destination D:/Alhena-rebuilt
Set-Location D:/Alhena-rebuilt
.\build.ps1 -Action Prepare -Offline
.\build.ps1 -Action Package -Offline
```

也可以先通过 Git 或本地 bundle 检出配套提交，再在没有 `upstream/`、`.cache/` 的干净检出中只恢复依赖：

```powershell
python tools/offline-kit.py restore --archive X:/backup/alhena-offline-windows-x64-252.28539.zip --destination D:/Alhena-checkout --into-checkout
Set-Location D:/Alhena-checkout
.\build.ps1 -Action Package -Offline
```

`--into-checkout` 核对源码快照，不替换源码或已有缓存；不一致就失败，可改为恢复新目录。两种模式均在写入前验证 ZIP、清单和每个文件的 SHA-256。

`-Offline` 不执行 clone 或 curl 预取；JBR 归档缺失/损坏立即失败。Ant、JPS 和 Java 子进程统一使用工作区 Maven 缓存，并加载构建专用网络防护，拒绝外部 Java 连接，保留编译器本地 IPC。构建设置索引会创建 Plugins 页面并独立刷新市场元数据，故仅在构建 JVM 中通过上游 `idea.plugins.host` 参数使用本地不可用端点，避免触发外网刷新；产品资源和运行参数不写入该地址。防护依赖当前固定 JDK 17/21 的 SecurityManager，升级时需要调整。它不是操作系统防火墙，严格隔离环境仍可断网；系统 Git/Python/PowerShell 由目标机提供。

## 验证标准

跨路径验证必须在全新目录执行，不带 Alhena class 或 JPS 增量状态，开启网络防护并重新产出 Windows ZIP。单独检查防护拒绝外部连接、允许本地 IPC。记录离线包哈希、恢复位置、构建退出码、日志和产物哈希到 `build-support/offline-validation.json`；导出或 ZIP 校验成功不等于离线编译成功。

重建 ZIP 含时间戳，通常不与原包哈希相同。这里保障固定源码与依赖下的重新编译能力；需要逐字节相同的已验收发行物时，直接保存原 Release ZIP。
