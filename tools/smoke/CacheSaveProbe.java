import java.io.*;
import java.lang.instrument.Instrumentation;
import java.lang.reflect.*;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.atomic.*;

/** Fixture-only diagnostic agent exercising the actual platform cache serializer. Never shipped. */
public final class CacheSaveProbe {
  private static Instrumentation instrumentation;
  private static ClassLoader loader;
  private static Class<?> type(String name) throws Exception {
    for(Class<?> c:instrumentation.getAllLoadedClasses()) if(c.getName().equals(name)) return c;
    return Class.forName(name,true,loader);
  }
  private static Object call(Object target,String name,Object...args) throws Exception {
    Class<?> owner=target instanceof Class<?>?(Class<?>)target:target.getClass();
    for(Method m:owner.getMethods()) {
      if(!m.getName().equals(name)||m.getParameterCount()!=args.length) continue;
      boolean matches=true;
      for(int i=0;i<args.length;i++) if(args[i]!=null&&!m.getParameterTypes()[i].isInstance(args[i])) matches=false;
      if(matches) { m.setAccessible(true); return m.invoke(target instanceof Class<?>?null:target,args); }
    }
    throw new NoSuchMethodException(name);
  }
  private static Throwable unwrap(Throwable e) {
    while(e instanceof InvocationTargetException) e=((InvocationTargetException)e).getCause();
    return e;
  }
  private static Throwable save(Object cache) {
    try { call(cache,"saveCacheNow"); return null; } catch(Throwable e) { return unwrap(e); }
  }
  private static void require(boolean value,String message) { if(!value) throw new IllegalStateException(message); }
  private static Set<String> temporaryFiles(Path directory) throws IOException {
    Set<String> result=new TreeSet<>();
    try(var files=Files.list(directory)) { files.filter(p->p.getFileName().toString().matches("cache.*\\.tmp")).forEach(p->result.add(p.getFileName().toString())); }
    return result;
  }
  public static void agentmain(String args,Instrumentation inst) throws Exception {
    instrumentation=inst;String[] parts=args.split("\\|",4);
    Path root=Path.of(parts[0]).toAbsolutePath().normalize(),repository=Path.of(parts[1]).toAbsolutePath().normalize(),system=Path.of(parts[2]).toAbsolutePath().normalize(),evidence=Path.of(parts[3]).toAbsolutePath().normalize();
    require(repository.startsWith(root.resolve("out/fixtures"))&&Files.isDirectory(repository.resolve(".git")),"Not an isolated repository");
    require(system.startsWith(root.resolve("out/cache-contention"))&&evidence.startsWith(root.resolve("out/cache-contention")),"Not an owned cache-test sandbox");
    Files.createDirectories(evidence);
    try(PrintWriter out=new PrintWriter(Files.newBufferedWriter(evidence.resolve("cache-probe.txt")))) {
      try {
        for(Class<?> c:inst.getAllLoadedClasses()) if(c.getName().equals("git4idea.GitVcs")) loader=c.getClassLoader();
        Object[] projects=(Object[])call(call(type("com.intellij.openapi.project.ProjectManager"),"getInstance"),"getOpenProjects");
        require(projects.length==1&&repository.equals(Path.of((String)call(projects[0],"getBasePath")).toAbsolutePath().normalize()),"Wrong project");
        Object cache=call(projects[0],"getService",type("com.intellij.platform.backend.workspace.WorkspaceModelCache"));
        Path file=(Path)call(cache,"getCacheFile");require(file.toAbsolutePath().normalize().startsWith(system),"Cache escaped owned sandbox");
        require(cache.getClass().getName().equals("com.intellij.workspaceModel.ide.impl.WorkspaceModelCacheImpl"),"Not the original cache service");
        out.println("cacheService="+cache.getClass().getName());out.println("cacheFile="+file);
        for(int i=0;i<10;i++) require(save(cache)==null,"Unheld initial save failed");
        Set<String> before=temporaryFiles(file.getParent());
        for(int hold:new int[]{20,40,60}) {
          FileChannel reader=FileChannel.open(file,StandardOpenOption.READ);
          AtomicReference<Throwable> closeError=new AtomicReference<>();
          Thread closer=new Thread(()->{try {Thread.sleep(hold);reader.close();} catch(Throwable e){closeError.set(e);}},"cache-test-reader-release");
          Throwable failure;
          long start=System.nanoTime();closer.start();
          try {failure=save(cache);} finally {reader.close();closer.join(3000);}
          require(!closer.isAlive()&&closeError.get()==null,"Reader release failed");
          out.println("transientHold"+hold+"Ms="+(System.nanoTime()-start)/1_000_000);
          require(failure==null,"Short reader contention was not recovered: "+failure);
          require(call(cache,"loadCache")!=null,"Recovered cache cannot be deserialized");
          require(temporaryFiles(file.getParent()).equals(before),"Temporary cache leaked after recovery");
        }
        out.println("transientReaderRecovery=true");
        byte[] old=Files.readAllBytes(file);Throwable permanent;long start=System.nanoTime();
        try(FileChannel reader=FileChannel.open(file,StandardOpenOption.READ)){permanent=save(cache);}
        long deniedMs=(System.nanoTime()-start)/1_000_000;
        require(permanent instanceof AccessDeniedException,"Persistent denial was swallowed: "+permanent);
        require(deniedMs>=100&&deniedMs<3000,"Persistent retry budget is not bounded: "+deniedMs);
        require(Arrays.equals(old,Files.readAllBytes(file)),"Persistent denial changed the old cache");
        require(temporaryFiles(file.getParent()).equals(before),"Temporary cache leaked after exhausted retries");
        out.println("persistentDenialMs="+deniedMs);out.println("persistentDenialVisible=true");out.println("oldCachePreserved=true");
        AtomicReference<Throwable> interruption=new AtomicReference<>();AtomicBoolean flagPreserved=new AtomicBoolean();
        Thread writer=new Thread(()->{try{interruption.set(save(cache));flagPreserved.set(Thread.currentThread().isInterrupted());}finally{Thread.interrupted();}},"cache-test-interrupted-writer");
        boolean observedWait=false;
        try(FileChannel reader=FileChannel.open(file,StandardOpenOption.READ)) {
          writer.start();long deadline=System.nanoTime()+2_000_000_000L;
          while(writer.isAlive()&&System.nanoTime()<deadline) {
            if(writer.getState()==Thread.State.TIMED_WAITING&&Arrays.stream(writer.getStackTrace()).anyMatch(f->f.getClassName().equals("com.intellij.workspaceModel.ide.impl.WorkspaceModelCacheSerializer"))) {observedWait=true;writer.interrupt();break;}
            Thread.sleep(1);
          }
          writer.join(2000);
        } finally {if(writer.isAlive()){writer.interrupt();writer.join(2000);}}
        require(observedWait&&!writer.isAlive(),"Could not verify interruption during retry");
        require(interruption.get() instanceof InterruptedIOException&&flagPreserved.get(),"Interrupt was lost: "+interruption.get());
        require(Arrays.equals(old,Files.readAllBytes(file)),"Interruption changed old cache");
        require(temporaryFiles(file.getParent()).equals(before),"Temporary cache leaked after interruption");
        out.println("interruptionPreserved=true");
        for(int i=0;i<100;i++) require(save(cache)==null,"Unheld post-recovery save failed at "+i);
        require(call(cache,"loadCache")!=null,"Final cache cannot be deserialized");
        require(temporaryFiles(file.getParent()).equals(before),"Unexpected temporary cache after stress");
        out.println("unheldStressSuccess=100");out.println("temporaryFilesCleaned=true");out.println("cacheProbePassed=true");
      } catch(Throwable e) { e.printStackTrace(out);out.println("cacheProbePassed=false"); }
    }
  }
}
