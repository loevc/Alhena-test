import java.awt.*;
import java.io.PrintWriter;
import java.lang.reflect.Proxy;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import javax.swing.*;

/** Fixture-only original action/controls driver. Never part of the product. */
public final class AdvancedProbe {
  private static Object project, repository;
  private static PrintWriter out;
  private static Object call(Object target,String name,Object... args) throws Exception { return WorkflowProbe.call(target,name,args); }
  private static Class<?> type(String name) throws Exception { return Class.forName(name); }
  private static Object service(String name) throws Exception { return call(project,"getService",type(name)); }
  public static void runInProgress(String operation,String payload,Object project,Object repository,PrintWriter out,Path evidence) throws Exception {
    Object progress=call(type("com.intellij.openapi.progress.ProgressManager"),"getInstance");
    Object indicator=type("com.intellij.openapi.progress.EmptyProgressIndicator").getConstructor().newInstance();
    call(progress,"runProcess",(Runnable)() -> {
      try { run(operation,payload,project,repository,out,evidence); }
      catch(Exception error) { throw new RuntimeException(error); }
    },indicator);
  }
  private static Object file(String name) throws Exception {
    if(!List.of("hunks.txt","history.txt").contains(name)) throw new IllegalArgumentException("Unexpected fixture file");
    Object root=call(repository,"getRoot");
    Object file=call(root,"findChild",name);
    if(file==null) throw new IllegalStateException("Fixture file is not in VFS");
    return file;
  }
  private static Object editors() throws Exception { return call(type("com.intellij.openapi.fileEditor.FileEditorManager"),"getInstance",project); }
  private static Object tracker() throws Exception {
    Object manager=call(type("com.intellij.openapi.vcs.impl.LineStatusTrackerManager"),"getInstance",project);
    return call(manager,"getLineStatusTracker",file("hunks.txt"));
  }
  private static Object event(Object action,Map<String,Object> data) throws Exception {
    Class<?> contextClass=type("com.intellij.openapi.actionSystem.DataContext");
    Object context=Proxy.newProxyInstance(contextClass.getClassLoader(),new Class[]{contextClass},(proxy,method,args) -> {
      if(!method.getName().equals("getData")) return null;
      Object key=args[0];
      String name=key instanceof String ? (String)key:(String)call(key,"getName");
      if(name.equals("project")) return project;
      return data.get(name);
    });
    return call(type("com.intellij.openapi.actionSystem.AnActionEvent"),"createFromAnAction",action,null,"AlhenaAcceptance",context);
  }
  private static void branchAction(String id,String branchName) throws Exception {
    if(!List.of("acceptance/created","acceptance/renamed").contains(branchName)) throw new IllegalArgumentException("Unexpected fixture branch");
    Object branch=call(call(repository,"getBranches"),"findLocalBranch",branchName);
    if(branch==null) throw new IllegalStateException("Fixture branch missing from original repository model");
    Object action=id.equals("delete") ? type("git4idea.actions.ref.GitDeleteRefAction").getConstructor().newInstance():
      call(call(type("com.intellij.openapi.actionSystem.ActionManager"),"getInstance"),"getAction",id);
    Object event=event(action,Map.of("Git.Selected.Ref",branch,"Git.Repositories",List.of(repository)));
    call(action,"update",event);
    if(!(Boolean)call(call(event,"getPresentation"),"isEnabled")) throw new IllegalStateException("Original branch action is disabled");
    call(action,"actionPerformed",event);
    out.println("originalBranchAction="+action.getClass().getName());
  }
  private static Dialog branchDialog() {
    for(Window window:Window.getWindows()) if(window.isShowing() && window instanceof Dialog && ((Dialog)window).getTitle().toLowerCase().contains("branch")) return (Dialog)window;
    throw new IllegalStateException("No original branch dialog");
  }
  private static Component find(Component component,String name) {
    if(!component.isShowing()) return null;
    if(component.getClass().getName().equals(name)) return component;
    if(component instanceof Container) for(Component child:((Container)component).getComponents()) { Component found=find(child,name); if(found!=null) return found; }
    return null;
  }
  private static boolean button(Component component,String text) {
    if(!component.isShowing()) return false;
    if(component instanceof AbstractButton && text.equals(((AbstractButton)component).getText()) && component.isEnabled()) { ((AbstractButton)component).doClick(); return true; }
    if(component instanceof Container) for(Component child:((Container)component).getComponents()) if(button(child,text)) return true;
    return false;
  }
  private static void componentAction(String id,Component component) throws Exception {
    // Programmatic Swing selection does not pass through the platform's input
    // event cache invalidation. Re-snapshot real UI providers for this action.
    call(type("com.intellij.openapi.actionSystem.impl.PreCachedDataContext"),"clearAllCaches");
    Object action=call(call(type("com.intellij.openapi.actionSystem.ActionManager"),"getInstance"),"getAction",id);
    Object context=call(call(type("com.intellij.ide.DataManager"),"getInstance"),"getDataContext",component);
    Object event=call(type("com.intellij.openapi.actionSystem.AnActionEvent"),"createFromAnAction",action,null,"AlhenaAcceptance",context);
    out.println("contextProject="+(call(event,"getProject")!=null));
    if(id.equals("Vcs.CherryPick")) {
      out.println("selectedLogRowsAtAction="+((JTable)component).getSelectedRowCount());
      Object selection=call(context,"getData","Vcs.Log.Commit.Selection");
      out.println("contextCommitSelection="+(selection!=null));
      if(selection!=null) out.println("contextSelectedCommits="+call(selection,"getCommits"));
    }
    // Let the platform honor the action's BGT update / EDT execution contract.
    Object manager=call(type("com.intellij.openapi.actionSystem.ActionManager"),"getInstance");
    call(manager,"tryToExecute",action,null,component,"AlhenaAcceptance",false);
    out.println("originalContextActionDispatched="+id);
  }
  private static JTable graph() {
    for(Window window:Window.getWindows()) {
      Component found=find(window,"com.intellij.vcs.log.ui.frame.VcsLogMainGraphTable");
      if(found!=null) return (JTable)found;
    }
    throw new IllegalStateException("No visible original central Git log table");
  }
  private static Dialog dialog(String title) {
    for(Window window:Window.getWindows()) if(window.isShowing() && window instanceof Dialog && ((Dialog)window).getTitle().contains(title)) return (Dialog)window;
    throw new IllegalStateException("No original dialog: "+title);
  }
  private static void printTables(Component component) {
    if(!component.isShowing()) return;
    if(component instanceof JTable) {
      JTable table=(JTable)component;
      out.println("advancedTable="+component.getClass().getName()+" rows="+table.getRowCount());
      for(int row=0;row<Math.min(10,table.getRowCount());row++) {
        StringBuilder cells=new StringBuilder();
        for(int column=0;column<table.getColumnCount();column++) cells.append(table.getValueAt(row,column)).append(" / ");
        out.println("advancedRow="+cells);
      }
    }
    if(component instanceof Container) for(Component child:((Container)component).getComponents()) printTables(child);
  }
  private static boolean link(Component component,String text,boolean click) throws Exception {
    if(!component.isShowing()) return false;
    if(component.getClass().getName().equals("com.intellij.ui.components.labels.LinkLabel") && text.equals(((JLabel)component).getText())) {
      out.println("originalHunkLink="+text);
      if(click) call(component,"doClick");
      return true;
    }
    boolean found=false;
    if(component instanceof Container) for(Component child:((Container)component).getComponents()) {
      if(link(child,text,click)) { if(click) return true; found=true; }
    }
    return found;
  }
  public static void run(String operation,String payload,Object projectValue,Object repoValue,PrintWriter writer,Path evidence) throws Exception {
    project=projectValue; repository=repoValue; out=writer;
    switch(operation) {
      case "ui-advanced-state":
        out.println("currentBranch="+call(repository,"getCurrentBranchName"));
        for(Object branch:(java.util.Collection<?>)call(call(repository,"getBranches"),"getLocalBranches")) out.println("localBranch="+call(branch,"getName"));
        Object tracker=tracker();
        if(tracker!=null) {
          out.println("lineTracker="+tracker.getClass().getName());
          List<?> ranges=(List<?>)call(tracker,"getRanges");
          if(ranges!=null) for(Object range:ranges) out.println("hunk="+call(range,"getLine1")+","+call(range,"getLine2")+" staged="+call(range,"getHasStaged")+" unstaged="+call(range,"getHasUnstaged"));
        }
        for(Window window:Window.getWindows()) if(window.isShowing()) { link(window,"Stage",false); link(window,"Unstage",false); }
        Object selected=call(editors(),"getSelectedTextEditor");
        if(selected!=null) {
          List<?> annotations=(List<?>)call(call(selected,"getGutter"),"getTextAnnotations");
          out.println("gutterAnnotations="+annotations.size());
          for(int line=0;line<3;line++) {
            StringBuilder text=new StringBuilder();
            for(Object annotation:annotations) text.append(call(annotation,"getLineText",line,selected)).append(" / ");
            out.println("blameLine="+line+" text="+text);
          }
        }
        for(Window window:Window.getWindows()) printTables(window);
        try {
          JTable visibleGraph=graph();
          out.println("selectedLogRows="+visibleGraph.getSelectedRowCount());
        } catch(IllegalStateException ignored) { }
        break;
      case "ui-advanced-open-hunks": call(editors(),"openFile",file("hunks.txt"),true); break;
      case "ui-advanced-hunk-popup":
        Object hunkTracker=tracker();
        if(hunkTracker==null || !hunkTracker.getClass().getName().equals("git4idea.index.GitStageLineStatusTracker")) throw new IllegalStateException("No original staging line tracker");
        List<?> ranges=(List<?>)call(hunkTracker,"getRanges");
        Object textEditor=call(editors(),"getSelectedTextEditor");
        if(ranges==null || ranges.size()!=2 || textEditor==null) throw new IllegalStateException("Expected two separate fixture hunks");
        call(hunkTracker,"scrollAndShowHint",ranges.get(0),textEditor);
        break;
      case "ui-advanced-hunk-stage":
      case "ui-advanced-hunk-unstage":
        String text=operation.endsWith("-unstage") ? "Unstage":"Stage";
        boolean found=false;
        for(Window window:Window.getWindows()) if(window.isShowing() && link(window,text,true)) { found=true; break; }
        if(!found) throw new IllegalStateException("No original hunk link: "+text);
        break;
      case "ui-advanced-popup-close":
        Object app=call(type("com.intellij.openapi.application.ApplicationManager"),"getApplication");
        call(call(app,"getService",type("com.intellij.openapi.vcs.ex.LineStatusMarkerPopupService")),"closeActivePopup");
        break;
      case "ui-advanced-branch-create": WorkflowProbe.later(() -> WorkflowProbe.action("Git.CreateNewBranch")); break;
      case "ui-advanced-branch-rename": WorkflowProbe.later(() -> branchAction("Git.Rename.Local.Branch","acceptance/created")); break;
      case "ui-advanced-branch-delete": WorkflowProbe.later(() -> branchAction("delete","acceptance/renamed")); break;
      case "ui-advanced-branch-name":
        if(!List.of("acceptance/created","acceptance/renamed").contains(payload)) throw new IllegalArgumentException("Unexpected fixture name");
        Component field=find(branchDialog(),"com.intellij.util.textCompletion.TextFieldWithCompletion");
        if(field==null) throw new IllegalStateException("No original branch name field");
        call(field,"setText",payload);
        break;
      case "ui-advanced-branch-submit":
        if(!List.of("Create","Rename").contains(payload) || !button(branchDialog(),payload)) throw new IllegalStateException("No original branch submit button");
        break;
      case "ui-advanced-log-select-cherry":
        JTable table=graph();
        boolean foundCommit=false;
        for(int row=0;row<table.getRowCount();row++) for(int col=0;col<table.getColumnCount();col++) {
          if("Accept cherry-pick source".equals(String.valueOf(table.getValueAt(row,col)))) {
            table.setRowSelectionInterval(row,row);
            table.scrollRectToVisible(table.getCellRect(row,col,true));
            foundCommit=true; break;
          }
        }
        if(!foundCommit) throw new IllegalStateException("Cherry source not loaded in visible log");
        break;
      case "ui-advanced-cherry-pick": componentAction("Vcs.CherryPick",graph()); break;
      case "ui-advanced-checkout-feature":
        Object brancher=call(type("git4idea.branch.GitBrancher"),"getInstance",project);
        call(brancher,"checkout","rebase-feature",false,List.of(repository),null);
        break;
      case "ui-advanced-rebase-open": WorkflowProbe.later(() -> WorkflowProbe.action("Git.Rebase")); break;
      case "ui-advanced-rebase-target":
        Component combo=find(dialog("Rebase"),"git4idea.ui.ComboBoxWithAutoCompletion");
        if(combo==null) throw new IllegalStateException("No original rebase target combo");
        call(combo,"setSelectedItem","upstream-target");
        break;
      case "ui-advanced-rebase": if(!button(dialog("Rebase"),"Rebase")) throw new IllegalStateException("No original Rebase button"); break;
      case "ui-advanced-open-history": call(editors(),"openFile",file("history.txt"),true); break;
      case "ui-advanced-blame":
        Object editor=call(editors(),"getSelectedTextEditor");
        if(editor==null) throw new IllegalStateException("No original text editor");
        componentAction("Annotate",(Component)call(editor,"getContentComponent"));
        break;
      case "ui-advanced-file-history":
        Object historyEditor=call(editors(),"getSelectedTextEditor");
        if(historyEditor==null) throw new IllegalStateException("No original history text editor");
        componentAction("Vcs.ShowTabbedFileHistory",(Component)call(historyEditor,"getContentComponent"));
        break;
      case "api-advanced-blame":
        Object provider=type("git4idea.annotate.GitAnnotationProvider").getConstructor(type("com.intellij.openapi.project.Project")).newInstance(project);
        Object annotation=call(provider,"annotate",file("history.txt"));
        try {
          for(int line=0;line<3;line++) {
            out.println("blameRevision."+line+"="+call(call(annotation,"getLineRevisionNumber",line),"asString"));
            for(Object aspect:(Object[])call(annotation,"getAspects")) out.println("blameAspect."+line+"="+call(aspect,"getId")+":"+call(aspect,"getValue",line));
          }
        } finally { call(annotation,"dispose"); }
        break;
      case "api-advanced-file-history":
        Object path=call(type("com.intellij.vcsUtil.VcsUtil"),"getFilePath",file("history.txt"));
        List<?> revisions=(List<?>)call(type("git4idea.history.GitFileHistory"),"collectHistory",project,path,new String[0]);
        for(Object revision:revisions) out.println("fileRevision="+call(call(revision,"getRevisionNumber"),"asString")+" message="+call(revision,"getCommitMessage"));
        break;
      default: throw new IllegalArgumentException(operation);
    }
  }
}
