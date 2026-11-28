import java.lang.instrument.Instrumentation;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

/** Reload the probe on each invocation, using the real Git plugin class loader. */
public final class WorkflowLoader {
  public static void agentmain(String args, Instrumentation instrumentation) throws Exception {
    String[] parts = args.split("\\|",4);
    ClassLoader gitLoader = null;
    for (Class<?> type : instrumentation.getAllLoadedClasses()) {
      if (type.getName().equals("git4idea.GitVcs")) { gitLoader = type.getClassLoader(); break; }
    }
    if (gitLoader == null) {
      if(parts[1].equals("ui-inspect")) {
        Path directory=Path.of(parts[0]);
        java.nio.file.Files.createDirectories(directory);
        java.nio.file.Files.writeString(directory.resolve("ui-inspect.txt"),"fixtureNotReady=true\n");
        return;
      }
      throw new IllegalStateException("Git4Idea not loaded yet");
    }
    URL location = Path.of(parts[3]).toUri().toURL();
    try (URLClassLoader loader = new URLClassLoader(new URL[]{location}, gitLoader) {
      @Override protected Class<?> loadClass(String name, boolean resolve) throws ClassNotFoundException {
        if (name.equals("WorkflowProbe") || name.startsWith("WorkflowProbe$") || name.equals("AdvancedProbe") || name.startsWith("AdvancedProbe$")) {
          Class<?> found = findLoadedClass(name);
          if (found == null) found = findClass(name);
          if (resolve) resolveClass(found);
          return found;
        }
        return super.loadClass(name,resolve);
      }
    }) {
      loader.loadClass("WorkflowProbe").getMethod("run", String.class).invoke(null,parts[0]+"|"+parts[1]+"|"+parts[2]);
    }
  }
}
