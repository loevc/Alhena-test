package alhena.build

import kotlinx.collections.immutable.persistentListOf
import kotlinx.collections.immutable.toPersistentList
import kotlinx.collections.immutable.toPersistentSet
import org.jetbrains.intellij.build.*
import java.nio.file.Files
import java.nio.file.Path

/** Product composition. Pinned source compatibility fixes live in patches/upstream.json. */
class AlhenaProperties(private val home: Path) : ProductProperties() {
  override val baseFileName = "alhena"

  init {
    platformPrefix = "Alhena"
    applicationInfoModule = "alhena.product"
    useSplash = false
    buildCrossPlatformDistribution = false
    buildSourcesArchive = false
    runtimeDistribution = JetBrainsRuntimeDistribution.LIGHTWEIGHT
    productLayout.productImplementationModules = listOf("intellij.platform.starter", "alhena.product")
    productLayout.bundledPluginModules = persistentListOf("intellij.vcs.git")
    // Layout validation visits every configured plugin layout, including those
    // not bundled. Retain Git's upstream layout instead of the entire IDE list.
    productLayout.pluginLayouts = CommunityRepositoryModules.COMMUNITY_REPOSITORY_PLUGINS
      .filter { it.mainModule == "intellij.vcs.git" }
      .toPersistentList()
    productLayout.buildAllCompatiblePlugins = false
    productLayout.prepareCustomPluginRepositoryForPublishedPlugins = false
    // Match the public Community product: omit optional modules absent from this
    // repository. Required/embedded modules still fail upstream validation.
    productLayout.skipUnresolvedContentModules = true
    productLayout.excludedModuleNames = Files.readAllLines(home.resolve("alhena/resources/alhena-excluded-modules.txt"))
      .map { it.trim() }.filter { it.isNotEmpty() && !it.startsWith("#") }.toPersistentSet()
    additionalVmOptions = persistentListOf(
      "-Didea.initially.ask.config=false",
      // This independent product has no JetBrains usage-statistics consent.
      "-Didea.disable.collect.statistics=true",
      "-Didea.suppress.statistics.report=true",
      "-Dide.experimental.ui.meetNewUi=false",
      "-Dide.show.plugin.suggestions.on.open=false",
      "-Dide.check.windows.defender.rules=false",
      // The platform default writes a module file into repository/.idea.
      "-Dide.create.fake.module.on.project.import=false",
    )
  }

  override fun createWindowsCustomizer(projectHome: String) = WindowsDistributionCustomizer().apply {
    icoPath = home.resolve("alhena/resources/alhena.ico").toString()
    associateIpr = false
    publishUninstaller = false
    fileAssociations = emptyList()
  }
  override fun createLinuxCustomizer(projectHome: String): LinuxDistributionCustomizer? = null
  override fun createMacCustomizer(projectHome: String): MacDistributionCustomizer? = null
  override fun getSystemSelector(appInfo: ApplicationInfoProperties, buildNumber: String) = "AlhenaSandbox0.1"
  override fun getBaseArtifactName(appInfo: ApplicationInfoProperties, buildNumber: String) = "alhena-${appInfo.fullVersion}-$buildNumber"
  override fun getOutputDirectoryName(appInfo: ApplicationInfoProperties) = "alhena"

  override suspend fun copyAdditionalFiles(context: BuildContext, targetDir: Path) {
    Files.copy(home.resolve("alhena/resources/alhena-version.json"), targetDir.resolve("alhena-version.json"), java.nio.file.StandardCopyOption.REPLACE_EXISTING)
    for (name in listOf("LICENSE.txt", "NOTICE.txt")) {
      Files.copy(home.resolve(name), targetDir.resolve(name), java.nio.file.StandardCopyOption.REPLACE_EXISTING)
    }
  }
}
