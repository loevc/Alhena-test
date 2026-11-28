import java.awt.*;
import java.awt.image.BufferedImage;
import java.io.*;
import java.lang.instrument.Instrumentation;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.lang.reflect.*;
import java.nio.file.*;
import javax.imageio.ImageIO;
import javax.swing.*;

/** External smoke probe; never bundled with the product. All UI work runs on EDT. */
public final class UiProbe {
  public static void agentmain(String args, Instrumentation instrumentation) throws Exception {
    String[] parts = args.split("\\|", 2);
    Path directory = Path.of(parts[0]);
    Files.createDirectories(directory);
    String action = parts.length > 1 ? parts[1] : "inspect";
    if(action.equals("close")) {
      Class<?> manager=Class.forName("com.intellij.openapi.application.ApplicationManager");
      Object applicationObject=manager.getMethod("getApplication").invoke(null);
      Class<?> modality=Class.forName("com.intellij.openapi.application.ModalityState");
      Object nonModal=modality.getMethod("nonModal").invoke(null);
      Files.writeString(directory.resolve("close.txt"),"platformExitRequested=true\n");
      Runnable close=() -> {
        try { applicationObject.getClass().getMethod("exit",boolean.class,boolean.class,boolean.class).invoke(applicationObject,true,true,false); }
        catch(Exception error) { error.printStackTrace(); }
      };
      applicationObject.getClass().getMethod("invokeLater",Runnable.class,modality).invoke(applicationObject,close,nonModal);
      return;
    }
    try (PrintWriter out = new PrintWriter(Files.newBufferedWriter(directory.resolve(action + ".txt")))) {
      SwingUtilities.invokeAndWait(() -> {
        try {
          Class<?> application = Class.forName("com.intellij.openapi.application.ApplicationManager");
          if (application.getMethod("getApplication").invoke(null) == null) {
            out.println("openProjects=0 applicationNotReady=true");
            return;
          }
          Class<?> pm = Class.forName("com.intellij.openapi.project.ProjectManager");
          Object manager = pm.getMethod("getInstance").invoke(null);
          Object[] projects = (Object[]) pm.getMethod("getOpenProjects").invoke(manager);
          out.println("openProjects=" + projects.length);
          MemoryUsage heap = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
          out.println("metric.uptimeMs=" + ManagementFactory.getRuntimeMXBean().getUptime());
          out.println("metric.heapUsedBytes=" + heap.getUsed());
          out.println("metric.heapCommittedBytes=" + heap.getCommitted());
          out.println("metric.heapMaxBytes=" + heap.getMax());
          out.println("metric.loadedClasses=" + instrumentation.getAllLoadedClasses().length);
          Class<?> progress = Class.forName("com.intellij.openapi.progress.impl.CoreProgressManager");
          Class<?> indicator = Class.forName("com.intellij.openapi.progress.ProgressIndicator");
          int runningIndicators=0;
          for(Object item:(java.util.List<?>)progress.getMethod("getCurrentIndicators").invoke(null)) {
            if((Boolean)indicator.getMethod("isRunning").invoke(item)) runningIndicators++;
          }
          out.println("metric.runningProgressIndicators="+runningIndicators);
          Class<?> dumb = Class.forName("com.intellij.openapi.project.DumbService");
          Class<?> projectClass = Class.forName("com.intellij.openapi.project.Project");
          for (Object project : projects) {
            Object service = dumb.getMethod("getInstance",projectClass).invoke(null,project);
            out.println("metric.projectDumb=" + dumb.getMethod("isDumb").invoke(service));
            Class<?> scanning=Class.forName("com.intellij.openapi.project.UnindexedFilesScannerExecutor");
            Object executor=scanning.getMethod("getInstance",projectClass).invoke(null,project);
            Object running=scanning.getMethod("isRunning").invoke(executor);
            Object value=Class.forName("kotlinx.coroutines.flow.StateFlow").getMethod("getValue").invoke(running);
            out.println("metric.projectScanning="+value);
            out.println("metric.scanningQueued="+scanning.getMethod("getHasQueuedTasks").invoke(executor));
            Object scanEvents=scanning.getMethod("getStartedOrStoppedEvent").invoke(executor);
            out.println("metric.scanningActivity="+Class.forName("kotlinx.coroutines.flow.StateFlow").getMethod("getValue").invoke(scanEvents));
          }
          if (action.equals("activate")) {
            Class<?> projectType = Class.forName("com.intellij.openapi.project.Project");
            Class<?> twm = Class.forName("com.intellij.openapi.wm.ToolWindowManager");
            Class<?> tw = Class.forName("com.intellij.openapi.wm.ToolWindow");
            for (Object project : projects) {
              Class<?> editorManager=Class.forName("com.intellij.openapi.fileEditor.FileEditorManager");
              Class<?> virtualFile=Class.forName("com.intellij.openapi.vfs.VirtualFile");
              Class<?> fileSystem=Class.forName("com.intellij.openapi.vfs.VirtualFileSystem");
              Object editors=editorManager.getMethod("getInstance",projectType).invoke(null,project);
              boolean central=false;
              for(Object file:(Object[])editorManager.getMethod("getOpenFiles").invoke(editors)) {
                Object fs=virtualFile.getMethod("getFileSystem").invoke(file);
                if("vcs-log".equals(fileSystem.getMethod("getProtocol").invoke(fs))) {
                  editorManager.getMethod("openFile",virtualFile,boolean.class,boolean.class).invoke(editors,file,true,true);
                  central=true;
                  out.println("centralGitLog=true");
                  Object selected=editorManager.getMethod("getSelectedEditor",virtualFile).invoke(editors,file);
                  if(selected!=null) {
                    Component component=(Component)Class.forName("com.intellij.openapi.fileEditor.FileEditor").getMethod("getComponent").invoke(selected);
                    out.println("metric.centralLogRows="+centralLogRows(component));
                  }
                  break;
                }
              }
              Object windows = twm.getMethod("getInstance", projectType).invoke(null, project);
              for (String id : (String[]) twm.getMethod("getToolWindowIds").invoke(windows)) {
                out.println("toolWindow=" + id);
                if (!central && (id.equals("Version Control") || id.equals("Git"))) {
                  Object window = twm.getMethod("getToolWindow", String.class).invoke(windows, id);
                  tw.getMethod("show", Runnable.class).invoke(window, (Runnable)null);
                }
                if (id.equals("Meet New UI")) {
                  Object window = twm.getMethod("getToolWindow", String.class).invoke(windows, id);
                  tw.getMethod("hide", Runnable.class).invoke(window, (Runnable)null);
                }
              }
            }
          }
          int index = 0;
          for (Window window : Window.getWindows()) {
            if (action.equals("activate") && window instanceof Frame) window.setSize(1400,1000);
            window.validate();
            out.println("window=" + window.getClass().getName() + " visible=" + window.isVisible() + " size=" + window.getSize()
                        + (window instanceof Frame ? " title=" + ((Frame)window).getTitle() : ""));
            inspect(window, out, action);
            if (window instanceof Frame && window.getWidth() > 200 && window.getHeight() > 200) {
              window.validate();
              BufferedImage image = new BufferedImage(window.getWidth(), window.getHeight(), BufferedImage.TYPE_INT_RGB);
              Graphics2D graphics = image.createGraphics();
              window.paint(graphics);
              graphics.dispose();
              ImageIO.write(image, "png", directory.resolve(action + "-" + index++ + ".png").toFile());
            }
          }
        } catch (Throwable error) { error.printStackTrace(out); }
      });
    }
  }

  private static int centralLogRows(Component component) {
    if(component instanceof JTable && component.isShowing() && component.getClass().getName().endsWith("VcsLogMainGraphTable")) {
      return ((JTable)component).getRowCount();
    }
    int rows=-1;
    if(component instanceof Container) for(Component child:((Container)component).getComponents()) rows=Math.max(rows,centralLogRows(child));
    return rows;
  }

  private static void inspect(Component component, PrintWriter out, String action) {
    String name = component.getClass().getName();
    if(action.equals("expand") && component.isShowing() && name.equals("git4idea.ui.branch.dashboard.ExpandStripeButton")) {
      ((JButton)component).doClick();
    }
    if(component.isShowing() && component instanceof JLabel) {
      String text=((JLabel)component).getText();
      if(text!=null && (text.contains("Repository") || text.contains("New Project"))) out.println("label="+text);
    }
    if(component.isShowing() && component instanceof AbstractButton) {
      String text=((AbstractButton)component).getText();
      if(text!=null && !text.isBlank()) out.println("button="+text);
    }
    if (action.equals("diff") && component.isShowing() && name.equals("com.intellij.vcs.log.ui.frame.VcsLogChangesBrowser")) {
      try {
        Class<?> browser = component.getClass();
        boolean available = (Boolean) browser.getMethod("canShowDiff").invoke(component);
        out.println("canShowDiff=" + available);
        if (available) browser.getMethod("showDiff").invoke(component);
      } catch (Exception error) { error.printStackTrace(out); }
    }
    if (component instanceof JTable) {
      JTable table = (JTable)component;
      out.println("table=" + name + " showing=" + table.isShowing() + " rows=" + table.getRowCount() + " columns=" + table.getColumnCount());
      for (int row = 0; row < Math.min(table.getRowCount(), 10); row++) {
        out.print("row[" + row + "]=");
        for (int col = 0; col < table.getColumnCount(); col++) out.print(table.getValueAt(row,col) + " | ");
        out.println();
      }
      if (action.equals("select") && table.isShowing() && name.endsWith("VcsLogMainGraphTable") && table.getRowCount() > 2) table.setRowSelectionInterval(2,2);
    }
    if (component instanceof JTree && component.isShowing()) {
      JTree tree = (JTree)component;
      if (action.equals("expand") && name.equals("git4idea.ui.branch.dashboard.BranchesTreeComponent")) {
        for (int row = 0; row < Math.min(tree.getRowCount(),100); row++) tree.expandRow(row);
      }
      out.println("tree=" + name + " rows=" + tree.getRowCount());
      if(name.equals("git4idea.ui.branch.dashboard.BranchesTreeComponent")) out.println("branchesVisibleWidth="+tree.getVisibleRect().width);
      for (int row = 0; row < Math.min(tree.getRowCount(), 25); row++) out.println("node=" + tree.getPathForRow(row));
    }
    if (name.contains("Diff") && component.isShowing()) out.println("diffComponent=" + name);
    if (component instanceof Container) for (Component child : ((Container)component).getComponents()) inspect(child,out,action);
  }
}
