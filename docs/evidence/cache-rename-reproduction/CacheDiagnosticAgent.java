import java.lang.instrument.Instrumentation;
import java.lang.reflect.*;
import java.nio.file.*;
import java.nio.channels.FileChannel;
import java.io.*;
public final class CacheDiagnosticAgent {
  private static Instrumentation inst;
  private static ClassLoader loader;
  private static Class<?> type(String name) throws Exception {
    for(Class<?> c:inst.getAllLoadedClasses()) if(c.getName().equals(name)) return c;
    return Class.forName(name,true,loader);
  }
  private static Object call(Object target,String name,Object...args) throws Exception {
    Class<?> owner=target instanceof Class<?>?(Class<?>)target:target.getClass();
    for(Method m:owner.getMethods()) {
      if(!m.getName().equals(name)||m.getParameterCount()!=args.length)continue;
      boolean ok=true;for(int i=0;i<args.length;i++)if(args[i]!=null&&!m.getParameterTypes()[i].isInstance(args[i]))ok=false;
      if(ok){m.setAccessible(true);return m.invoke(target instanceof Class<?>?null:target,args);}
    }
    throw new NoSuchMethodException(name);
  }
  private static Throwable unwrap(Throwable e){while(e instanceof InvocationTargetException)e=((InvocationTargetException)e).getCause();return e;}
  public static void agentmain(String args,Instrumentation instrumentation) throws Exception {
    inst=instrumentation;String[] p=args.split("\\|",4);Path root=Path.of(p[0]).toAbsolutePath().normalize(),repository=Path.of(p[1]).toAbsolutePath().normalize(),system=Path.of(p[2]).toAbsolutePath().normalize(),evidence=Path.of(p[3]).toAbsolutePath().normalize();
    if(!repository.startsWith(root.resolve("out/fixtures"))||!Files.isDirectory(repository.resolve(".git"))||!system.startsWith(root.resolve("out/diagnostics"))||!evidence.startsWith(root.resolve("out/diagnostics")))throw new IllegalArgumentException("Fixture-only guard rejected request");
    Files.createDirectories(evidence);
    try(PrintWriter out=new PrintWriter(Files.newBufferedWriter(evidence.resolve("original-cache-path.txt")))) {
      try {
        for(Class<?> c:inst.getAllLoadedClasses())if(c.getName().equals("git4idea.GitVcs"))loader=c.getClassLoader();
        Object[] projects=(Object[])call(call(type("com.intellij.openapi.project.ProjectManager"),"getInstance"),"getOpenProjects");
        if(projects.length!=1||!repository.equals(Path.of((String)call(projects[0],"getBasePath")).toAbsolutePath().normalize()))throw new IllegalStateException("Wrong project");
        Object cache=call(projects[0],"getService",type("com.intellij.platform.backend.workspace.WorkspaceModelCache"));Path file=(Path)call(cache,"getCacheFile");
        if(!file.toAbsolutePath().normalize().startsWith(system))throw new IllegalStateException("Cache outside owned sandbox");
        out.println("cacheService="+cache.getClass().getName());out.println("cacheFile="+file);
        call(cache,"saveCacheNow");out.println("unheldSaveBefore=true");
        Throwable caught=null;
        try(FileChannel reader=FileChannel.open(file,StandardOpenOption.READ)) {
          try{call(cache,"saveCacheNow");}catch(Throwable e){caught=unwrap(e);}
        }
        if(!(caught instanceof AccessDeniedException))throw new IllegalStateException("Expected exact AccessDeniedException, got "+caught);
        out.println("heldReaderException="+caught.getClass().getName());caught.printStackTrace(out);
        call(cache,"saveCacheNow");out.println("unheldSaveAfter=true");
        int success=0,unheldDenied=0;
        for(int i=0;i<100;i++){
          try{call(cache,"saveCacheNow");success++;}
          catch(Throwable e){Throwable c=unwrap(e);if(!(c instanceof AccessDeniedException))throw e;unheldDenied++;out.println("unexpectedUnheldDeniedAt="+i);}
        }
        out.println("unheldStressSuccess="+success);out.println("unheldStressAccessDenied="+unheldDenied);out.println("diagnosticPassed=true");
      } catch(Throwable e){e.printStackTrace(out);}
    }
  }
}
