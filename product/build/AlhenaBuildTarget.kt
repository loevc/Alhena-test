import alhena.build.AlhenaProperties
import alhena.build.buildAlhenaDistribution
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import org.jetbrains.intellij.build.*
import org.jetbrains.intellij.build.impl.BuildContextImpl

/** Invoked by the pinned upstream JPS bootstrap, rather than the IDEA build target. */
object AlhenaBuildTarget {
  @JvmStatic
  fun main(args: Array<String>) = runBlocking(Dispatchers.Default) {
    val home = BuildPaths.COMMUNITY_ROOT.communityRoot
    val options = BuildOptions().apply {
      incrementalCompilation = true
      // Source errors should fail immediately; an automatic full clean rebuild
      // cannot repair a missing product dependency and obscures the first error.
      incrementalCompilationFallbackRebuild = false
      useCompiledClassesFromProjectOutput = false
      buildStepsToSkip += setOf(
        BuildOptions.WIN_SIGN_STEP,
        BuildOptions.MAC_SIGN_STEP,
        BuildOptions.WINDOWS_EXE_INSTALLER_STEP,
        BuildOptions.CROSS_PLATFORM_DISTRIBUTION_STEP,
        BuildOptions.MAVEN_ARTIFACTS_STEP,
        BuildOptions.SOURCES_ARCHIVE_STEP,
      )
    }
    val context = BuildContextImpl.createContext(home, AlhenaProperties(home), options = options)
    if (System.getProperty("alhena.build.action", "compile") == "package") {
      buildAlhenaDistribution(context)
    }
    else {
      context.compileModules(listOf(
        "alhena.product", "intellij.platform.starter", "intellij.vcs.git",
        "intellij.platform.vcs.log.impl", "intellij.platform.diff.impl",
      ))
    }
  }
}
