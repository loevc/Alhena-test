# 云端编译与 Tag 自动发布

日常可以只在本机编辑源码、提交和推送。Windows ZIP 由 GitHub 托管的 Windows runner 构建，本机不需要下载 IntelliJ 上游、JBR SDK 或编译依赖。编辑源码可以使用其他操作系统；当前产品的构建与运行目标仍是 Windows x64。

## 日常开发

普通分支 push 和 Pull Request 会运行单元测试，以及 Windows PowerShell 5.1 / PowerShell 7 脚本语法检查，不会创建 Release。只改文档时可跳过这些检查。

需要云端试编译时，在 Actions → **Windows checks, package and release** → Run workflow 中选择分支，并勾选 `build_package`。成功后从该次运行的 `windows-candidate-<提交SHA>` artifact 下载 ZIP。这个手动入口只产出候选，不自动发布。

## 自动发布

1. 修改 `product/resources/idea/AlhenaApplicationInfo.xml` 中 `<version full="...">` 的产品版本。例如下一版使用 `full="0.1.1-dev" eap="true"`。`major`、`minor` 是平台兼容字段，不随产品小版本更改。
2. 提交并推送源码和本次工作流变更。
3. 为这个提交创建并推送新 Tag。例如产品版本 `0.1.1-dev`：

```powershell
git push origin main
git tag v0.1.1-dev.1
git push origin v0.1.1-dev.1
```

推送 `v*` Tag 后自动执行：

```text
单元测试 / PowerShell 语法检查
    → Windows 云端编译并打包
    → ZIP CRC / 产品布局 / 上游许可证 / 内置 Java 启动检查
    → 生成 SHA-256、源码身份记录和发布说明
    → 创建 Release 草稿并上传四个附件
    → 核对 GitHub 附件 SHA-256 和大小
    → 发布 Release
```

四个附件是完整 Windows ZIP、对应 `.sha256`、`ci-package.json` 和 `release-notes.md`。ZIP 内已有 EXE、JAR、运行时及依赖；用户下载完整 ZIP 解压运行，无需单独下载 EXE/JAR。

Tag 的三段数字版本必须与产品 `full` 的三段数字版本一致。版本带 `-dev`、Tag 带预发布后缀，或 `eap="true"` 时，自动标记为 **Pre-release**。现有 `v0.1.0` 不需要移动或重新发布；下一次发布应使用新版本 Tag。

不需要个人访问令牌。发布 job 使用 GitHub 自带的 `GITHUB_TOKEN` 和 job 级 `contents: write` 权限；编译、检查 job 保持只读。仓库必须启用 GitHub Actions，并允许官方 checkout、setup-python、upload/download-artifact Action 运行。GitHub 托管运行器使用量受账户配额和计费设置约束。

## 失败和重试

测试或打包失败时不会创建 Release；上传或哈希核验失败时只留下草稿。修复临时网络问题后，在原 Actions 运行中选择 **Re-run failed jobs**，继续使用成功的 package job 留下的同一组附件。候选 artifact 保留 7 天；过期后需要重新构建，并使用新 Tag 发布新候选。

若 GitHub 在失败草稿中保留未完成上传的附件，或附件摘要不一致，工作流会停止；检查并删除该失败草稿后再重试，或改用新 Tag。

已经发布的附件不会被覆盖、删除或替换。现有手工 Release 也不会由此工具接管。如果对同一 Tag 重新构建出了不同哈希的 ZIP，工作流会拒绝替换；请创建新版本 Tag。自动上传成功后的重复发布操作只有在同一源码、Tag、附件哈希均一致时才视为成功。

## 本地构建继续保留

Windows x64 上安装 Git、Python 3.11+、PowerShell 和 curl 后，仍可执行：

```powershell
.\build.ps1 -Action Prepare
.\build.ps1 -Action Compile
.\build.ps1 -Action Package
```

参数是 `-Action`，编译选项是 `Compile`。完整 Package 已包含准备与编译，不必每次逐条执行。离线构建继续使用原有 `-Offline` 流程，见 [离线重建](offline-rebuild.md)。云端工作流同样调用这个本地入口，不维护第二套构建实现。

## 验收范围

自动发布包含单元测试、脚本解析、包结构、ZIP 完整性和内置 Java 启动检查。它不代表已经完成八组交互式桌面或真实远程认证验收；`ci-package.json` 和自动发布说明会如实记录。需要完整桌面验收时，在具备现有探针所需 JDK SDK 的 Windows 验收机上，下载该次候选后运行 `tools/desktop-gate.py`；探针仍需编译，但不必在本机重新编译产品。原有远程测试仍只使用专用测试仓库。

历史 `source-association.json` 对应既有已验收源码，后续改动源码后直接用它校验当前工作树会预期失败；要复核旧版本应检出对应旧提交。新 CI 候选由自己的 Tag、源码 SHA、`ci-package.json` 和 Release 附件哈希建立关联，不会把旧桌面证据移用于新程序包。


实现依据：[GitHub Actions 工作流语法与权限](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)、[Release 与草稿接口](https://docs.github.com/en/rest/releases/releases)、[附件摘要接口](https://docs.github.com/en/rest/releases/assets)。


本次改造的 [验证记录](evidence/ci-release-acceptance.json) 包含专用测试仓库实际 Tag 构建、自动发布、附件字节校验及重复发布零写入结果；旧主仓库 Release 未改动。
