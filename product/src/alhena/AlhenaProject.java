package alhena;

import com.intellij.ide.util.PropertiesComponent;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.startup.ProjectActivity;
import com.intellij.openapi.util.Disposer;
import com.intellij.openapi.wm.ToolWindow;
import com.intellij.openapi.wm.ToolWindowManager;
import com.intellij.openapi.wm.ex.ToolWindowManagerListener;
import com.intellij.ui.content.Content;
import com.intellij.ui.content.ContentManager;
import com.intellij.ui.content.ContentManagerEvent;
import com.intellij.ui.content.ContentManagerListener;
import java.util.List;
import kotlin.Unit;
import kotlin.coroutines.Continuation;

/** Initial Git workspace layout; subsequent window placement stays user-controlled. */
public final class AlhenaProject implements ProjectActivity {
  @Override public Object execute(Project project, Continuation<? super Unit> continuation) {
    ToolWindowManager manager=ToolWindowManager.getInstance(project);
    manager.invokeLater(() -> {
      if(project.isDisposed()) return;
      for(String id:List.of("TODO","Services","Bookmarks","Problems View","Structure","Meet New UI")) {
        ToolWindow window=manager.getToolWindow(id);
        if(window!=null) { window.hide(null); window.setAvailable(false); }
      }
      ToolWindow history=manager.getToolWindow("Version Control");
      if(history==null) return;
      ContentManager contents=history.getContentManager();
      ContentManagerListener listener=new ContentManagerListener() {
        @Override public void contentAdded(ContentManagerEvent event) {
          manager.invokeLater(() -> applyInitialLayout(project,manager,history));
        }
      };
      contents.addContentManagerListener(listener);
      Disposer.register(project,() -> contents.removeContentManagerListener(listener));
      project.getMessageBus().connect(project).subscribe(ToolWindowManagerListener.TOPIC,new ToolWindowManagerListener() {
        @Override public void stateChanged(ToolWindowManager toolWindowManager) {
          if(!PropertiesComponent.getInstance(project).getBoolean("alhena.workspace.initialized")) {
            manager.invokeLater(() -> applyInitialLayout(project,manager,history));
          }
        }
      });
      applyInitialLayout(project,manager,history);
    });
    return Unit.INSTANCE;
  }

  private static void applyInitialLayout(Project project,ToolWindowManager manager,ToolWindow history) {
    if(project.isDisposed() || !history.isAvailable()) return;
    PropertiesComponent local=PropertiesComponent.getInstance(project);
    if(local.getBoolean("alhena.workspace.initialized")) return;
    // VCS content arrives after the platform tool window is registered. Showing
    // an empty window earlier makes the platform hide it again automatically.
    for(Content content:history.getContentManager().getContents()) {
      if(!"Log".equals(content.getTabName())) continue;
      ToolWindow files=manager.getToolWindow("Project");
      if(files!=null) files.hide(null);
      HistoryAction.show(project,() -> local.setValue("alhena.workspace.initialized",true));
      return;
    }
  }
}
