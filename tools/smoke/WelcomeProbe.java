import java.awt.*;
import java.awt.image.BufferedImage;
import java.io.PrintWriter;
import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;
import java.nio.file.*;
import java.util.List;
import javax.imageio.ImageIO;
import javax.swing.*;

/** Drives only the dedicated acceptance process, through its real welcome buttons. */
public final class WelcomeProbe {
  private static Object call(Object target, String name, Object... args) throws Exception {
    Class<?> owner=target instanceof Class<?> ? (Class<?>)target : target.getClass();
    for(Method method:owner.getMethods()) {
      if(!method.getName().equals(name) || method.getParameterCount()!=args.length) continue;
      boolean match=true;
      for(int i=0;i<args.length;i++) {
        Class<?> parameter=method.getParameterTypes()[i];
        if(parameter==boolean.class) parameter=Boolean.class;
        if(args[i]!=null && !parameter.isInstance(args[i])) match=false;
      }
      if(match) { method.setAccessible(true); return method.invoke(target instanceof Class<?> ? null:target,args); }
    }
    throw new NoSuchMethodException(owner.getName()+"."+name);
  }
  private static Object application() throws Exception {
    return call(Class.forName("com.intellij.openapi.application.ApplicationManager"),"getApplication");
  }
  public static void agentmain(String args, Instrumentation instrumentation) throws Exception {
    if(args.startsWith("base64:")) args=new String(java.util.Base64.getDecoder().decode(args.substring(7)),java.nio.charset.StandardCharsets.UTF_8);
    String[] parts=args.split("\\|",3);
    Path evidence=Path.of(parts[0]);
    String operation=parts[1], payload=parts.length>2 ? parts[2]:"";
    Files.createDirectories(evidence);
    if(operation.equals("inspect")) {
      SwingUtilities.invokeAndWait(() -> snapshot(evidence));
      return;
    }
    Object[] modality=new Object[1];
    SwingUtilities.invokeAndWait(() -> {
      try { modality[0]=call(Class.forName("com.intellij.openapi.application.ModalityState"),"current"); }
      catch(Exception error) { throw new RuntimeException(error); }
    });
    Files.writeString(evidence.resolve(operation+".scheduled"),"scheduled");
    call(application(),"invokeLater",(Runnable)() -> {
      try {
        switch(operation) {
          case "open": button("Open Repository").doClick(); break;
          case "main-open":
            Object projects=call(Class.forName("com.intellij.openapi.project.ProjectManager"),"getInstance");
            Object[] opened=(Object[])call(projects,"getOpenProjects");
            if(opened.length!=1) throw new IllegalStateException("Expected one fixture project before switching");
            Path base=Path.of((String)call(opened[0],"getBasePath")).toAbsolutePath().normalize();
            Path switchRoot=evidence.getParent().getParent().resolve("fixtures").toAbsolutePath().normalize();
            if(!base.startsWith(switchRoot)) throw new IllegalArgumentException("Refuse non-fixture project switching");
            Component openButton=findActionButton("OpenFile");
            if(openButton==null) throw new IllegalStateException("Original main-toolbar Open button is not visible");
            call(openButton,"click");
            break;
          case "this-window": button("This Window").doClick(); break;
          case "clone": button("Clone Repository").doClick(); break;
          case "clone-fields":
            String[] clone=payload.split("\\n",2);
            if(clone.length!=2 || !List.of("https://github.com/loevc/Alhena-test.git","git@github.com:loevc/Alhena-test.git").contains(clone[0])) throw new IllegalArgumentException("Unauthorized clone remote");
            Path target=Path.of(clone[1]).toAbsolutePath().normalize();
            Path allowed=evidence.getParent().getParent().resolve("fixtures").toAbsolutePath().normalize();
            if(!target.startsWith(allowed) || Files.exists(target)) throw new IllegalArgumentException("Clone target must be a new fixture");
            java.util.ArrayList<JTextField> fields=new java.util.ArrayList<>();
            for(Window window:Window.getWindows()) if(window.isShowing() && window instanceof Dialog && ((Dialog)window).getTitle().equals("Clone Repository")) fields(window,fields);
            if(fields.size()<2) throw new IllegalStateException("No original clone fields");
            fields.get(0).setText(clone[0]);
            fields.get(1).setText(target.toString());
            break;
          case "clone-go": button("Clone").doClick(); break;
          case "cancel":
            for(Window window:Window.getWindows()) {
              if(window instanceof FileDialog && window.isVisible()) { window.dispose(); return; }
            }
            button("Cancel").doClick(); break;
          case "ide-chooser":
            call(Class.forName("com.intellij.openapi.options.advanced.AdvancedSettings"),"setBoolean","ide.ui.native.file.chooser",false);
            Object setting=call(Class.forName("com.intellij.openapi.util.registry.Registry"),"get","ide.ui.new.file.chooser");
            call(setting,"setValue",true);
            break;
          case "path":
            Path fixture=Path.of(payload).toAbsolutePath().normalize();
            Path fixtureRoot=evidence.getParent().getParent().resolve("fixtures").toAbsolutePath().normalize();
            if(!fixture.startsWith(fixtureRoot) || !Files.exists(fixture.resolve(".git"))) throw new IllegalArgumentException("Non-fixture path");
            Object panel=find("com.intellij.openapi.fileChooser.impl.FileChooserPanelImpl");
            if(panel==null) throw new IllegalStateException("No original chooser panel");
            call(panel,"load",fixture);
            break;
          case "initial-path":
            Path initial=Path.of(payload).toAbsolutePath().normalize();
            Path initialRoot=evidence.getParent().getParent().resolve("fixtures").toAbsolutePath().normalize();
            if(!initial.startsWith(initialRoot) || !Files.exists(initial.resolve(".git"))) throw new IllegalArgumentException("Non-fixture initial path");
            Object general=call(Class.forName("com.intellij.ide.GeneralLocalSettings"),"getInstance");
            call(general,"setDefaultProjectDirectory",initial.toString());
            break;
          case "choose":
            Component chooser=find("com.intellij.openapi.fileChooser.impl.FileChooserPanelImpl");
            if(chooser==null) throw new IllegalStateException("No original chooser panel");
            clearSelection(chooser);
            button("OK").doClick(); break;
          case "trust":
            AbstractButton trust=findButton(null,"Trust");
            if(trust==null) throw new IllegalStateException("No trust confirmation");
            trust.doClick(); break;
          case "close": call(application(),"exit",true,true,false); break;
          default: throw new IllegalArgumentException(operation);
        }
        Files.writeString(evidence.resolve(operation+".completed"),"completed");
      } catch(Throwable error) {
        try(PrintWriter writer=new PrintWriter(Files.newBufferedWriter(evidence.resolve("errors.txt"),StandardOpenOption.CREATE,StandardOpenOption.APPEND))) {
          error.printStackTrace(writer);
        } catch(Exception ignored) { }
      }
    },modality[0]);
  }
  private static AbstractButton button(String exact) {
    AbstractButton button=findButton(exact,null);
    if(button==null || !button.isEnabled()) throw new IllegalStateException("No enabled button: "+exact);
    return button;
  }
  private static Component findActionButton(String id) throws Exception {
    for(Window window:Window.getWindows()) if(window.isShowing()) {
      Component found=findActionButton(window,id); if(found!=null) return found;
    }
    return null;
  }
  private static Component findActionButton(Component component,String id) throws Exception {
    if(!component.isShowing()) return null;
    if(Class.forName("com.intellij.openapi.actionSystem.impl.ActionButton").isInstance(component)) {
      Object action=call(component,"getAction");
      Object manager=call(Class.forName("com.intellij.openapi.actionSystem.ActionManager"),"getInstance");
      if(id.equals(call(manager,"getId",action))) return component;
    }
    if(component instanceof Container) for(Component child:((Container)component).getComponents()) {
      Component found=findActionButton(child,id); if(found!=null) return found;
    }
    return null;
  }
  private static AbstractButton findButton(String exact,String prefix) {
    for(Window window:Window.getWindows()) if(window.isShowing()) {
      AbstractButton result=findButton(window,exact,prefix);
      if(result!=null) return result;
    }
    return null;
  }
  private static AbstractButton findButton(Component component,String exact,String prefix) {
    if(component instanceof AbstractButton && component.isShowing()) {
      AbstractButton button=(AbstractButton)component;
      String text=button.getText();
      if(text!=null && (exact!=null ? text.equals(exact):button instanceof JButton && text.startsWith(prefix))) return button;
    }
    if(component instanceof Container) for(Component child:((Container)component).getComponents()) {
      AbstractButton button=findButton(child,exact,prefix); if(button!=null) return button;
    }
    return null;
  }
  private static Component find(String name) {
    for(Window window:Window.getWindows()) if(window.isShowing()) {
      Component found=find(window,name); if(found!=null) return found;
    }
    return null;
  }
  private static Component find(Component component,String name) {
    if(component.getClass().getName().equals(name)) return component;
    if(component instanceof Container) for(Component child:((Container)component).getComponents()) {
      Component found=find(child,name); if(found!=null) return found;
    }
    return null;
  }
  private static void clearSelection(Component component) {
    if(component instanceof JTable) ((JTable)component).clearSelection();
    if(component instanceof Container) for(Component child:((Container)component).getComponents()) clearSelection(child);
  }
  private static void fields(Component component, java.util.List<JTextField> fields) {
    if(component instanceof JTextField && !(component instanceof JPasswordField) && component.isShowing()) fields.add((JTextField)component);
    if(component instanceof Container) for(Component child:((Container)component).getComponents()) fields(child,fields);
  }
  private static void snapshot(Path directory) {
    try(PrintWriter out=new PrintWriter(Files.newBufferedWriter(directory.resolve("inspect.txt")))) {
      if(application()==null) {
        out.println("openProjects=0 applicationNotReady=true");
        return;
      }
      Object manager=call(Class.forName("com.intellij.openapi.project.ProjectManager"),"getInstance");
      Object[] projects=(Object[])call(manager,"getOpenProjects");
      out.println("openProjects="+projects.length);
      for(Object project:projects) out.println("project="+call(project,"getBasePath"));
      int index=0;
      for(Window window:Window.getWindows()) if(window.isVisible()) {
        out.println("window="+window.getClass().getName()+(window instanceof Dialog ? " title="+((Dialog)window).getTitle():""));
        inspect(window,out);
        if(!(window instanceof FileDialog) && window.getWidth()>50 && window.getHeight()>50) {
          BufferedImage image=new BufferedImage(window.getWidth(),window.getHeight(),BufferedImage.TYPE_INT_RGB);
          Graphics2D graphics=image.createGraphics(); window.paint(graphics); graphics.dispose();
          ImageIO.write(image,"png",directory.resolve("window-"+index+++".png").toFile());
        }
      }
    } catch(Throwable error) {
      try(PrintWriter writer=new PrintWriter(Files.newBufferedWriter(directory.resolve("errors.txt"),StandardOpenOption.CREATE,StandardOpenOption.APPEND))) { error.printStackTrace(writer); }
      catch(Exception ignored) { }
    }
  }
  private static void inspect(Component component,PrintWriter out) throws Exception {
    if(!component.isShowing()) return;
    if(component instanceof AbstractButton) out.println("button="+((AbstractButton)component).getText()+" enabled="+component.isEnabled());
    if(component instanceof JPasswordField) out.println("passwordFieldPresent=true");
    else if(component instanceof JTextField) out.println("field="+((JTextField)component).getText());
    if(component instanceof JTable) out.println("table="+component.getClass().getName()+" rows="+((JTable)component).getRowCount());
    if(component.getClass().getName().equals("com.intellij.openapi.fileChooser.impl.FileChooserPanelImpl")) {
      java.lang.reflect.Field field=component.getClass().getDeclaredField("myCurrentDirectory"); field.setAccessible(true);
      out.println("chooserDirectory="+field.get(component));
    }
    if(component instanceof Container) for(Component child:((Container)component).getComponents()) inspect(child,out);
  }
}
