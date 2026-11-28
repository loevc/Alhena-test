package alhena;

import com.intellij.ide.AppLifecycleListener;
import com.intellij.ide.ui.customization.CustomActionsSchema;
import com.intellij.ide.util.PropertiesComponent;
import com.intellij.openapi.actionSystem.*;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.options.advanced.AdvancedSettings;
import com.intellij.openapi.updateSettings.impl.UpdateSettings;
import com.intellij.openapi.util.registry.Registry;
import java.util.List;

/** Product shell only. Original Git actions retain their own UI and behavior. */
public final class AlhenaApplication implements AppLifecycleListener {
  @Override public void appFrameCreated(List<String> arguments) {
    UpdateSettings settings=UpdateSettings.getInstance();
    settings.setCheckNeeded(false);
    settings.setPluginsCheckNeeded(false);
    settings.setPluginsAutoUpdateEnabled(false);
    Registry.get("ide.experimental.ui.meetNewUi").setValue(false);
    Registry.get("ide.show.plugin.suggestions.on.open").setValue(false);
    // The Git workspace is the landing view, including existing IDEA projects.
    // The platform's later README opener otherwise takes focus and hides Log.
    AdvancedSettings.setBoolean("ide.open.readme.md.on.startup",false);
    PropertiesComponent.getInstance().setValue("ide.try.ultimate.disabled",true);
    ApplicationManager.getApplication().invokeLater(AlhenaApplication::configureActions);
  }

  private static void configureActions() {
    ActionManager manager=ActionManager.getInstance();
    PropertiesComponent preferences=PropertiesComponent.getInstance();
    if(!preferences.getBoolean("alhena.staging.initialized")) {
      AnAction enable=manager.getAction("Git.Stage.Enable");
      if(enable instanceof ToggleAction) {
        AnActionEvent event=AnActionEvent.createFromAnAction(enable,null,"Alhena",DataContext.EMPTY_CONTEXT);
        if(!((ToggleAction)enable).isSelected(event)) enable.actionPerformed(event);
        preferences.setValue("alhena.staging.initialized",true);
      }
    }
    remove(manager,"MainMenu",List.of("CodeMenu","AnalyzeMenu","RefactoringMenu","BuildMenu","RunMenu"));
    remove(manager,"MainToolbarRight",List.of("NewUiRunWidget","StopWithDropDown","ExecutionTargetsToolbarGroup"));
    remove(manager,"WelcomeScreen.QuickStart",List.of("WelcomeScreen.DefaultNewProjectActionGroup"));
    remove(manager,"NewProjectOrModuleGroup",List.of("WelcomeScreen.DefaultNewProjectAction"));
    AnAction open=manager.getAction("WelcomeScreen.OpenProject");
    if(open!=null) open.getTemplatePresentation().setText("Open Repository");
    AnAction clone=manager.getAction("Vcs.VcsClone");
    if(clone!=null) clone.getTemplatePresentation().setText("Clone Repository");
    AnAction toolbar=manager.getAction("Alhena.GitToolbar");
    if(toolbar instanceof DefaultActionGroup) {
      DefaultActionGroup group=(DefaultActionGroup)toolbar;
      group.removeAll();
      for(String id:List.of("OpenFile","Alhena.History","Git.Commit.Stage","Git.Fetch","Vcs.UpdateProject","Vcs.Push","Alhena.GitSettings")) {
        AnAction action=manager.getAction(id);
        if(action!=null) group.add(action);
      }
    }
    CustomActionsSchema schema=CustomActionsSchema.getInstance();
    for(String id:List.of("MainMenu","MainToolbarRight","MainToolbarCenter")) schema.invalidateCustomizedActionGroup(id);
  }

  private static void remove(ActionManager manager,String parent,List<String> ids) {
    AnAction action=manager.getAction(parent);
    if(!(action instanceof DefaultActionGroup)) return;
    DefaultActionGroup group=(DefaultActionGroup)action;
    for(String id:ids) {
      AnAction child=manager.getAction(id);
      if(child!=null) group.remove(child);
    }
  }
}
