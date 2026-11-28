package alhena.build

import org.jetbrains.intellij.build.BuildContext
import org.jetbrains.intellij.build.impl.buildDistributions
import org.jetbrains.intellij.build.impl.collectIncludedPluginModules
import org.jetbrains.intellij.build.impl.createDistributionBuilderState

/**
 * Compiled inside the upstream build-scripts module to use its internal layout API.
 * Derive the production compile set from the real platform/plugin layout, rather
 * than treating a handwritten JPS dependency list as the distribution contents.
 * Reference: upstream dev/IdeBuilder.kt, collectModulesToCompileForDistribution.
 */
suspend fun buildAlhenaDistribution(context: BuildContext) {
  val state = createDistributionBuilderState(context)
  val modules = state.platformModules.toMutableSet()
  collectIncludedPluginModules(context.getBundledPluginModules(), modules, context)
  modules.addAll(context.productProperties.productLayout.productApiModules)
  modules.addAll(context.productProperties.productLayout.productImplementationModules)
  modules.addAll(listOf(
    context.productProperties.applicationInfoModule,
    "intellij.idea.community.build.tasks",
    "intellij.platform.images.build",
    "intellij.tools.launcherGenerator",
  ))
  context.compileModules(modules)
  // The distribution entry otherwise calls compileModules(null), compiling the
  // entire upstream project. Reuse this context's freshly compiled product set.
  context.options.useCompiledClassesFromProjectOutput = true
  buildDistributions(context)
}
