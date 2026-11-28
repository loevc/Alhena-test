package alhena;

import com.intellij.openapi.actionSystem.*;
import com.intellij.ide.DataManager;
import com.intellij.openapi.fileEditor.FileEditorManager;
import com.intellij.openapi.project.DumbAwareAction;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.vcs.ProjectLevelVcsManager;
import com.intellij.openapi.util.Key;
import com.intellij.openapi.util.Disposer;
import com.intellij.openapi.vfs.VirtualFile;
import com.intellij.openapi.wm.ToolWindow;
import com.intellij.openapi.wm.ToolWindowManager;
import com.intellij.ui.content.Content;
import java.awt.Component;
import java.awt.Container;
import java.beans.PropertyChangeListener;
import javax.swing.JTable;

public final class HistoryAction extends DumbAwareAction {
  private static final Key<Boolean> OPENING=Key.create("alhena.history.opening");

  @Override public void actionPerformed(AnActionEvent event) {
    Project project=event.getProject();
    if(project!=null) show(project,() -> {});
  }

  static void show(Project project,Runnable opened) {
    if(project.isDisposed()) return;
    FileEditorManager editors=FileEditorManager.getInstance(project);
    if(selectExisting(editors)) { opened.run(); return; }
    if(Boolean.TRUE.equals(project.getUserData(OPENING))) return;
    ToolWindowManager windows=ToolWindowManager.getInstance(project);
    ToolWindow history=windows.getToolWindow("Version Control");
    if(history==null || !history.isAvailable()) return;
    Content log=null;
    for(Content content:history.getContentManager().getContents()) {
      if("Log".equals(content.getTabName())) { log=content; break; }
    }
    if(log==null) return;
    Content logContent=log;
    project.putUserData(OPENING,true);
    PropertyChangeListener[] listener=new PropertyChangeListener[1];
    boolean[] running={false},finished={false};
    Runnable attempt=() -> {
      if(project.isDisposed() || finished[0] || running[0] || !hasGraph(logContent.getComponent())) return;
      running[0]=true;
      try {
        if(!selectExisting(editors)) {
          AnAction action=ActionManager.getInstance().getAction("Vcs.Log.OpenAnotherTabInEditor");
          if(action==null) throw new IllegalStateException("Original Git log editor action is missing");
          DataContext original=DataManager.getInstance().getDataContext(logContent.getComponent());
          DataContext context=id -> CommonDataKeys.PROJECT.is(id) ? project:original.getData(id);
          action.actionPerformed(AnActionEvent.createFromAnAction(action,null,"AlhenaHistory",context));
        }
        if(selectExisting(editors)) {
          finished[0]=true;
          history.hide(null);
          opened.run();
        }
      } catch(RuntimeException | Error error) {
        finished[0]=true;
        throw error;
      } finally {
        running[0]=false;
        if(finished[0]) {
          logContent.removePropertyChangeListener(listener[0]);
          project.putUserData(OPENING,null);
        }
      }
    };
    // Wait for VCS mappings, use the real Log context, and coalesce reentrant
    // callbacks. Git's dumb-aware editor must not wait for code indexing.
    Runnable schedule=() -> ProjectLevelVcsManager.getInstance(project).runAfterInitialization(
      () -> windows.invokeLater(attempt));
    // The main Log is lazy. Content replacement is the platform's readiness
    // event, so no polling or dependency on its module's private class loader.
    listener[0]=event -> {
      if(Content.PROP_COMPONENT.equals(event.getPropertyName())) schedule.run();
    };
    logContent.addPropertyChangeListener(listener[0]);
    Disposer.register(project,() -> logContent.removePropertyChangeListener(listener[0]));
    history.getContentManager().setSelectedContent(logContent);
    history.show(schedule);
  }

  private static boolean hasGraph(Component component) {
    if(component instanceof JTable && component.getClass().getSimpleName().contains("VcsLog") && component.getClass().getSimpleName().endsWith("GraphTable")) return true;
    if(component instanceof Container) for(Component child:((Container)component).getComponents()) if(hasGraph(child)) return true;
    return false;
  }

  private static boolean selectExisting(FileEditorManager editors) {
    for(VirtualFile file:editors.getOpenFiles()) {
      if("vcs-log".equals(file.getFileSystem().getProtocol())) {
        editors.openFile(file,true,true);
        return true;
      }
    }
    return false;
  }
  @Override public void update(AnActionEvent event) {
    event.getPresentation().setEnabled(event.getProject()!=null);
  }
}
