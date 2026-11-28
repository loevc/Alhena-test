package alhena;

import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.module.Module;
import com.intellij.openapi.module.ModuleManager;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.project.ProjectStorePathManager;
import com.intellij.openapi.roots.ModifiableRootModel;
import com.intellij.openapi.roots.ModuleRootManager;
import com.intellij.openapi.util.Ref;
import com.intellij.openapi.vfs.VirtualFile;
import com.intellij.platform.DirectoryProjectConfigurator;

/** One plain repository content root, without importing SDKs, facets or build modules. */
public final class AlhenaDirectoryConfigurator implements DirectoryProjectConfigurator {
  @Override public boolean isEdtRequired() { return true; }

  @Override public void configureProject(Project project,VirtualFile baseDir,Ref<Module> moduleRef,boolean createdWithWizard) {
    ModuleManager modules=ModuleManager.getInstance(project);
    Module[] existing=modules.getModules();
    if(existing.length!=0) { moduleRef.set(existing[0]); return; }
    ApplicationManager.getApplication().runWriteAction(() -> {
      String file=ProjectStorePathManager.getInstance().getStoreDirectoryPath(baseDir.toNioPath()).resolve("repository.iml").toString();
      Module module=modules.newModule(file,"EMPTY_MODULE");
      ModifiableRootModel model=ModuleRootManager.getInstance(module).getModifiableModel();
      try {
        model.addContentEntry(baseDir);
        model.commit();
      } finally {
        if(!model.isDisposed()) model.dispose();
      }
      moduleRef.set(module);
    });
  }
}
