import java.awt.*;
import java.awt.image.BufferedImage;
import java.io.*;
import java.lang.reflect.*;
import java.nio.file.*;
import java.util.*;
import java.util.List;
import javax.imageio.ImageIO;
import javax.swing.*;

/** Fixture-only acceptance driver. Runs upstream actions and APIs, never bundled. */
public final class WorkflowProbe {
  private static PrintWriter out;
  private static Object project;
  private static Object repository;
  private static String payload;
  private static Path evidenceDirectory;

  private static Class<?> type(String name) throws Exception { return Class.forName(name); }
  static Object call(Object target, String name, Object... args) throws Exception {
    Class<?> owner = target instanceof Class<?> ? (Class<?>)target : target.getClass();
    for (Method method : owner.getMethods()) {
      if (!method.getName().equals(name) || method.getParameterCount() != args.length) continue;
      boolean matches = true;
      for (int i=0;i<args.length;i++) {
        Class<?> parameter = method.getParameterTypes()[i];
        if (parameter == boolean.class) parameter = Boolean.class;
        if (parameter == int.class) parameter = Integer.class;
        if (args[i] != null && !parameter.isInstance(args[i])) matches = false;
      }
      if (matches) {
        method.setAccessible(true);
        return method.invoke(target instanceof Class<?> ? null : target,args);
      }
    }
    throw new NoSuchMethodException(owner.getName()+"."+name+" args="+Arrays.toString(args));
  }
  private static Object instance(String name) throws Exception { return call(type(name),"getInstance"); }
  private static Object array(String name) throws Exception { return Array.newInstance(type(name),0); }
  static void action(String id) throws Exception {
    Object action = call(instance("com.intellij.openapi.actionSystem.ActionManager"),"getAction",id);
    if (action == null) throw new IllegalStateException("Missing original action "+id);
    Class<?> dc = type("com.intellij.openapi.actionSystem.DataContext");
    Object context = Proxy.newProxyInstance(dc.getClassLoader(),new Class[]{dc},(proxy,method,args) -> {
      if (method.getName().equals("getData")) {
        Object key=args[0];
        String name=key instanceof String ? (String)key : (String)call(key,"getName");
        if (name.equals("project")) return project;
      }
      return null;
    });
    Object event = call(type("com.intellij.openapi.actionSystem.AnActionEvent"),"createFromAnAction",action,null,"AlhenaAcceptance",context);
    call(action,"actionPerformed",event);
    out.println("originalAction="+id);
  }
  private static void selectedStageAction(String id) throws Exception {
    JTree tree=stageTree();
    if(tree.getSelectionCount()!=1) throw new IllegalStateException("Expected one selected staging file");
    Object context=call(instance("com.intellij.ide.DataManager"),"getDataContext",tree);
    Object original=call(instance("com.intellij.openapi.actionSystem.ActionManager"),"getAction",id);
    Object event=call(type("com.intellij.openapi.actionSystem.AnActionEvent"),"createFromAnAction",original,null,"AlhenaAcceptance",context);
    call(original,"actionPerformed",event);
    out.println("originalSelectedAction="+id);
  }
  private static JTree stageTree() {
    for(Window window:Window.getWindows()) {
      Component found=findComponent(window,"git4idea.index.ui.GitStagePanel$MyChangesTree");
      if(found!=null) return (JTree)found;
    }
    throw new IllegalStateException("No original staging tree");
  }
  private static Component findComponent(Component component,String name) {
    if(!component.isShowing()) return null;
    if(component.getClass().getName().equals(name)) return component;
    if(component instanceof Container) for(Component child:((Container)component).getComponents()) {
      Component found=findComponent(child,name); if(found!=null) return found;
    }
    return null;
  }
  public static void run(String args) throws Exception {
    String[] parts = args.split("\\|",3);
    Path evidence = Path.of(parts[0]);
    evidenceDirectory = evidence;
    String operation = parts[1];
    payload = parts.length > 2 ? parts[2] : "";
    Files.createDirectories(evidence);
    try (PrintWriter writer = new PrintWriter(Files.newBufferedWriter(evidence.resolve(operation+".txt")))) {
      out = writer;
      try {
        boolean[] fixtureReady={false};
        SwingUtilities.invokeAndWait(() -> {
          try {
            Object[] projects = (Object[])call(instance("com.intellij.openapi.project.ProjectManager"),"getOpenProjects");
            if (projects.length != 1) {
              if(operation.equals("ui-inspect") && projects.length==0) { out.println("fixtureNotReady=true"); return; }
              throw new IllegalStateException("Expected one fixture project");
            }
            project = projects[0];
            String path = (String)call(project,"getBasePath");
            Path workspace=evidence.toAbsolutePath().normalize();
            while(workspace!=null && !Files.isRegularFile(workspace.resolve("upstream.lock.json"))) workspace=workspace.getParent();
            if(workspace==null) throw new IllegalStateException("Evidence is not under the Alhena workspace");
            Path fixtures=workspace.resolve("out/fixtures").normalize();
            Path candidate=Path.of(path).toAbsolutePath().normalize();
            if(!candidate.startsWith(fixtures) || fixtures.relativize(candidate).getNameCount()==0 || !fixtures.relativize(candidate).getName(0).toString().startsWith("workflow-")) throw new IllegalStateException("Refuse non-fixture project: "+path);
            Object manager = call(type("git4idea.repo.GitRepositoryManager"),"getInstance",project);
            List<?> repositories=(List<?>)call(manager,"getRepositories");
            if(repositories.isEmpty() && operation.equals("ui-inspect")) { out.println("fixtureNotReady=true"); return; }
            repository = repositories.get(0);
            out.println("fixture="+path);
            fixtureReady[0]=true;
          } catch (Exception error) { throw new RuntimeException(error); }
        });
        if(!fixtureReady[0]) return;
        if(operation.equals("ui-exit")) {
          edt(() -> {
            try { later(() -> call(call(type("com.intellij.openapi.application.ApplicationManager"),"getApplication"),"exit",true,true,false)); }
            catch(Exception error) { throw new RuntimeException(error); }
          });
          out.println("platformExitRequested=true");
          return;
        }
        if (operation.startsWith("ui-")) {
          edt(() -> {
            try { ui(operation); } catch (Exception error) { throw new RuntimeException(error); }
          });
        } else api(operation);
        SwingUtilities.invokeAndWait(() -> {
          try {
            int index=0;
            for (Window window : Window.getWindows()) {
              if (!window.isVisible() || window.getWidth()<50 || window.getHeight()<50) continue;
              out.println("window="+window.getClass().getName()+" size="+window.getSize()+(window instanceof Dialog ? " title="+((Dialog)window).getTitle():""));
              inspect(window);
              BufferedImage image=new BufferedImage(window.getWidth(),window.getHeight(),BufferedImage.TYPE_INT_RGB);
              Graphics2D graphics=image.createGraphics(); window.paint(graphics); graphics.dispose();
              ImageIO.write(image,"png",evidence.resolve(operation+"-"+index+++".png").toFile());
            }
          } catch (Exception error) { error.printStackTrace(out); }
        });
      } catch (Throwable error) { error.printStackTrace(out); }
    }
  }
  private static void ui(String operation) throws Exception {
    switch (operation) {
      case "ui-stage-open":
        call(type("git4idea.index.GitStageManagerKt"),"enableStagingArea",true);
        action("Git.Commit.Stage"); break;
      case "ui-stage-all": action("Git.Stage.Add.All"); break;
      case "ui-stage-selected": selectedStageAction("Git.Stage.Add"); break;
      case "ui-history": action("Alhena.History"); break;
      case "ui-about": later(() -> action("About")); break;
      case "ui-git-settings": later(() -> action("Alhena.GitSettings")); break;
      case "ui-stage-select":
        String[] selection=payload.split("\\n",2);
        if(selection.length!=2 || !List.of("Staged","Unstaged").contains(selection[0]) || !List.of("README.md","new-file.txt","shared.txt").contains(selection[1])) throw new IllegalArgumentException("Unexpected fixture selection");
        JTree stage=stageTree();
        boolean selected=false;
        for(int row=0;row<stage.getRowCount();row++) {
          javax.swing.tree.TreePath path=stage.getPathForRow(row);
          if(path.toString().contains(", "+selection[0]+",") && path.toString().endsWith(selection[1]+"]")) {
            stage.setSelectionPath(path); stage.scrollPathToVisible(path); selected=true; break;
          }
        }
        if(!selected) throw new IllegalStateException("Fixture staging row not found");
        break;
      case "ui-unstage-selected": selectedStageAction("Git.Stage.Reset"); break;
      case "ui-discard-selected": later(() -> selectedStageAction("Git.Stage.Revert")); break;
      case "ui-stash-open": later(() -> action("Git.Stash")); break;
      case "ui-stash":
        String createStash=(String)call(type("git4idea.i18n.GitBundle"),"message","stash.button",new Object[0]);
        if(!click(createStash)) throw new IllegalStateException("No original Stash button");
        break;
      case "ui-unstash-open": later(() -> action("Git.Unstash")); break;
      case "ui-unstash":
        String applyStash=(String)call(type("git4idea.i18n.GitBundle"),"message","unstash.button.apply",new Object[0]);
        if(!click("Apply") && !click(applyStash)) throw new IllegalStateException("No original Apply Stash button");
        break;
      case "ui-message":
        for (Window window:Window.getWindows()) setMessage(window);
        break;
      case "ui-commit":
        if (!click("Commit")) throw new IllegalStateException("No enabled original Commit button");
        break;
      case "ui-checkout":
        if (!List.of("main","feature/workflow").contains(payload)) throw new IllegalArgumentException("Unexpected fixture branch");
        Object brancher=call(type("git4idea.branch.GitBrancher"),"getInstance",project);
        call(brancher,"checkout",payload,false,List.of(repository),null);
        out.println("checkoutRequested="+payload); break;
      case "ui-push-open": later(() -> action("Vcs.Push")); break;
      case "ui-push":
        if (!click("Push")) throw new IllegalStateException("No original Push button");
        break;
      case "ui-auth-helper":
        String helper=(String)call(type("git4idea.i18n.GitBundle"),"message","login.dialog.select.login.way.use.helper",new Object[0]);
        if(!click(helper)) throw new IllegalStateException("No credential helper radio button");
        String login=(String)call(type("git4idea.i18n.GitBundle"),"message","login.dialog.button.login",new Object[0]);
        if(!click(login)) throw new IllegalStateException("No original Log In button");
        break;
      case "ui-auth-cancel":
        boolean authDialog=false;
        for(Window window:Window.getWindows()) if(window.isShowing() && window instanceof Dialog && ((Dialog)window).getTitle().startsWith("Log In to")) authDialog=true;
        if(!authDialog || !click("Cancel")) throw new IllegalStateException("No original authentication cancellation");
        break;
      case "ui-fetch": action("Git.Fetch"); break;
      case "ui-update-open": later(() -> action("Vcs.UpdateProject")); break;
      case "ui-update":
        if (!click("OK")) throw new IllegalStateException("No original update confirmation button");
        break;
      case "ui-conflict-open":
        Object file=call(call(repository,"getRoot"),"findChild","shared.txt");
        Object provider=type("git4idea.merge.GitMergeProvider").getConstructor(type("com.intellij.openapi.project.Project"),boolean.class).newInstance(project,false);
        later(() -> call(call(type("com.intellij.openapi.vcs.AbstractVcsHelper"),"getInstance",project),"showMergeDialog",List.of(file),provider));
        break;
      case "ui-click":
        if (!List.of("Merge...","Merge…","Accept Yours","Accept Left","Apply","Continue","Close","OK","Revert","Pop Stash","Apply Stash","Cancel").contains(payload)) throw new IllegalArgumentException("Unexpected fixture button");
        String text=payload;
        later(() -> { if(!click(text)) throw new IllegalStateException("No enabled button "+text); });
        break;
      case "ui-inspect":
        out.println("projectBasePath="+call(project,"getBasePath"));
        Object projectStore=call(type("com.intellij.openapi.project.ProjectStorePathManager"),"getInstance");
        out.println("projectStoreClass="+projectStore.getClass().getName());
        out.println("projectStorePath="+call(projectStore,"getStoreDirectoryPath",java.nio.file.Path.of((String)call(project,"getBasePath"))));
        Object moduleManager=call(type("com.intellij.openapi.module.ModuleManager"),"getInstance",project);
        Object[] modules=(Object[])call(moduleManager,"getModules");
        out.println("moduleCount="+modules.length);
        for(Object module:modules) out.println("moduleFile="+call(module,"getModuleFilePath"));
        Object stashTracker=call(project,"getService",type("git4idea.stash.GitStashTracker"));
        out.println("stashCount="+((List<?>)call(stashTracker,"getStashes",call(repository,"getRoot"))).size());
        Object editors=call(type("com.intellij.openapi.fileEditor.FileEditorManager"),"getInstance",project);
        for(Object openFile:(Object[])call(editors,"getOpenFiles")) out.println("openFileProtocol="+call(call(openFile,"getFileSystem"),"getProtocol"));
        for(Object editor:(Object[])call(editors,"getSelectedEditors")) out.println("selectedEditor="+editor.getClass().getName());
        Object vcsManager=call(type("com.intellij.openapi.vcs.ProjectLevelVcsManager"),"getInstance",project);
        for(Object vcs:(Object[])call(vcsManager,"getAllActiveVcss")) {
          out.println("activeVcs="+vcs+" updateEnvironment="+call(vcs,"getUpdateEnvironment")+" roots="+Array.getLength(call(vcsManager,"getRootsUnderVcs",vcs)));
        }
        Object modes=call(type("com.intellij.vcs.commit.CommitModeManager"),"getInstance",project);
        out.println("commitMode="+call(modes,"getCurrentCommitMode"));
        Object twm=call(type("com.intellij.openapi.wm.ToolWindowManager"),"getInstance",project);
        for(String id:(String[])call(twm,"getToolWindowIds")) {
          Object tw=call(twm,"getToolWindow",id);
          out.println("toolWindow="+id+" visible="+call(tw,"isVisible")+" available="+call(tw,"isAvailable"));
          Object manager=call(tw,"getContentManager");
          for(Object content:(Object[])call(manager,"getContents")) out.println("tab="+call(content,"getTabName"));
        }
        Object actions=instance("com.intellij.openapi.actionSystem.ActionManager");
        for(String id:List.of("MainMenu","MainToolbarRight","Alhena.GitToolbar")) {
          Object group=call(actions,"getAction",id);
          if(group!=null) {
            Object[] children=(Object[])call(group,"getChildren",actions);
            for(Object child:children) out.println("actionChild."+id+"="+call(actions,"getId",child));
          }
        }
        Object updates=instance("com.intellij.openapi.updateSettings.impl.UpdateSettings");
        Object appInfo=call(type("com.intellij.openapi.application.ApplicationInfo"),"getInstance");
        out.println("applicationVersion="+call(appInfo,"getFullVersion"));
        out.println("applicationBuild="+call(appInfo,"getBuild"));
        out.println("updates.platform="+call(updates,"isCheckNeeded")+" plugins="+call(updates,"isPluginsCheckNeeded"));
        Object consent=call(type("com.intellij.openapi.application.ApplicationManager"),"getApplication");
        consent=call(consent,"getService",type("com.intellij.ide.ConsentOptionsProvider"));
        out.println("usageStatisticsAllowed="+call(consent,"isSendingUsageStatsAllowed")+" provider="+consent.getClass().getName());
        Object telemetry=call(type("com.intellij.platform.diagnostic.telemetry.TelemetryManager"),"getInstance");
        out.println("telemetryManager="+telemetry.getClass().getName()+" spanExporters="+call(telemetry,"hasSpanExporters"));
        break;
          default: AdvancedProbe.run(operation,payload,project,repository,out,evidenceDirectory);
    }
  }
  interface CheckedAction { void run() throws Exception; }
  private static void edt(Runnable action) throws Exception {
    Object[] modality=new Object[1];
    SwingUtilities.invokeAndWait(() -> {
      try { modality[0]=call(type("com.intellij.openapi.application.ModalityState"),"current"); }
      catch(Exception error) { throw new RuntimeException(error); }
    });
    Object application=call(type("com.intellij.openapi.application.ApplicationManager"),"getApplication");
    call(application,"invokeAndWait",action,modality[0]);
  }
  static void later(CheckedAction action) throws Exception {
    Path errors=evidenceDirectory.resolve("async-errors.txt");
    Object application=call(type("com.intellij.openapi.application.ApplicationManager"),"getApplication");
    Object modality=call(type("com.intellij.openapi.application.ModalityState"),"current");
    call(application,"invokeLater",(Runnable)() -> {
      try {
        Files.writeString(evidenceDirectory.resolve("async-state.txt"),"started");
        action.run();
        Files.writeString(evidenceDirectory.resolve("async-state.txt"),"returned");
      } catch(Throwable error) {
        try(PrintWriter log=new PrintWriter(Files.newBufferedWriter(errors,StandardOpenOption.CREATE,StandardOpenOption.APPEND))) { error.printStackTrace(log); }
        catch(IOException failure) { failure.printStackTrace(); }
      }
    },modality);
    out.println("scheduledOriginalDialog=true");
  }
  private static void api(String operation) throws Exception {
    Object git=instance("git4idea.commands.Git");
    Object listeners=array("git4idea.commands.GitLineHandlerListener");
    Object result;
    switch(operation) {
      case "api-merge-conflict":
        result=call(git,"merge",repository,"conflict-other",List.of(),listeners);
        out.println("expectedConflictExit="+call(result,"getExitCode"));
        call(repository,"update"); return;
      case "api-conflict-data":
        Object root=call(repository,"getRoot");
        call(root,"refresh",false,true);
        Object file=call(root,"findChild","shared.txt");
        Object provider=type("git4idea.merge.GitMergeProvider").getConstructor(type("com.intellij.openapi.project.Project"),boolean.class).newInstance(project,false);
        Object data=call(provider,"loadRevisions",file);
        for(String side:List.of("CURRENT","ORIGINAL","LAST")) {
          byte[] bytes=(byte[])data.getClass().getField(side).get(data);
          out.println("mergeData."+side+"="+new String(bytes,java.nio.charset.StandardCharsets.UTF_8).trim());
        }
        return;
      default: AdvancedProbe.runInProgress(operation,payload,project,repository,out,evidenceDirectory);
    }
  }
  private static void setMessage(Component component) throws Exception {
    if (component.isShowing() && component.getClass().getName().equals("com.intellij.openapi.vcs.ui.CommitMessage")) {
      call(component,"setCommitMessage",payload); out.println("commitMessage="+payload);
    }
    if(component instanceof Container) for(Component child:((Container)component).getComponents()) setMessage(child);
  }
  private static boolean click(String text) {
    Window[] windows=Window.getWindows();
    for(int i=windows.length-1;i>=0;i--) if(windows[i].isVisible() && click(windows[i],text)) return true;
    return false;
  }
  private static boolean click(Component component,String text) {
    if(component.isShowing() && component instanceof AbstractButton) {
      AbstractButton button=(AbstractButton)component;
      String label=button.getText();
      if(label!=null && text.replace("…","...").equals(label.replace("…","...")) && button.isEnabled()) { button.doClick(0); out.println("clicked="+text); return true; }
    }
    if(component instanceof Container) for(Component child:((Container)component).getComponents()) if(click(child,text)) return true;
    return false;
  }
  private static void inspect(Component component) {
    if (!component.isShowing()) return;
    String name=component.getClass().getName();
    if(component instanceof AbstractButton) out.println("button="+((AbstractButton)component).getText()+" enabled="+component.isEnabled());
    if(component instanceof JLabel) {
      String text=((JLabel)component).getText();
      if(text!=null && (text.toLowerCase().contains("commit") || text.toLowerCase().contains("conflict") || text.contains("Git executable") || text.contains("Alhena") || text.contains("Build #"))) out.println("label="+text);
    }
    if(component instanceof JTree) {
      JTree tree=(JTree)component; out.println("tree="+name+" rows="+tree.getRowCount());
      for(int row=0;row<Math.min(tree.getRowCount(),25);row++) out.println("node="+tree.getPathForRow(row));
    }
    if(component instanceof JTable) out.println("table="+name+" rows="+((JTable)component).getRowCount());
    if(name.contains("Merge") || name.contains("Diff")) out.println("component="+name);
    if(component instanceof Container) for(Component child:((Container)component).getComponents()) inspect(child);
  }
}
