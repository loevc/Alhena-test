import java.io.*;
import java.lang.instrument.Instrumentation;
import java.lang.reflect.*;
import java.nio.file.*;
import javax.swing.SwingUtilities;
public final class NetworkNotificationProbe {
 private static Instrumentation inst;private static ClassLoader loader;
 private static Class<?> type(String name)throws Exception{for(Class<?> c:inst.getAllLoadedClasses())if(c.getName().equals(name))return c;return Class.forName(name,true,loader);}
 private static Object call(Object target,String name,Object...args)throws Exception{Class<?> owner=target instanceof Class<?>?(Class<?>)target:target.getClass();for(Method m:owner.getMethods()){if(!m.getName().equals(name)||m.getParameterCount()!=args.length)continue;boolean ok=true;for(int i=0;i<args.length;i++)if(args[i]!=null&&!m.getParameterTypes()[i].isInstance(args[i]))ok=false;if(ok){m.setAccessible(true);return m.invoke(target instanceof Class<?>?null:target,args);}}throw new NoSuchMethodException(name);}
 public static void agentmain(String args,Instrumentation instrumentation)throws Exception{
  inst=instrumentation;String[] p=args.split("\\|",3);Path root=Path.of(p[0]).toAbsolutePath().normalize(),repo=Path.of(p[1]).toAbsolutePath().normalize(),evidence=Path.of(p[2]).toAbsolutePath().normalize();
  if(!repo.startsWith(root.resolve("out/fixtures"))||!Files.isDirectory(repo.resolve(".git"))||!evidence.startsWith(root.resolve("out/network-recovery")))throw new IllegalArgumentException("Fixture-only guard");
  for(Class<?> c:inst.getAllLoadedClasses())if(c.getName().equals("git4idea.GitVcs"))loader=c.getClassLoader();Files.createDirectories(evidence);
  try(PrintWriter out=new PrintWriter(Files.newBufferedWriter(evidence.resolve("notifications.txt")))){
   SwingUtilities.invokeAndWait(()->{try{
    Object[] projects=(Object[])call(call(type("com.intellij.openapi.project.ProjectManager"),"getInstance"),"getOpenProjects");
    if(projects.length!=1||!repo.equals(Path.of((String)call(projects[0],"getBasePath")).toAbsolutePath().normalize()))throw new IllegalStateException("Wrong fixture project");
    Object manager=call(type("com.intellij.notification.NotificationsManager"),"getNotificationsManager");Object[] notes=(Object[])call(manager,"getNotificationsOfType",type("com.intellij.notification.Notification"),projects[0]);
    for(Object n:notes)out.println("notification="+call(n,"getType")+"|"+type("com.intellij.notification.Notification").getField("id").get(n)+"|"+call(n,"getTitle")+"|"+call(n,"getContent"));out.println("snapshotPassed=true");
   }catch(Throwable e){e.printStackTrace(out);}});
  }
 }
}
