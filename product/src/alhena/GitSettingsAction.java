package alhena;

import com.intellij.openapi.actionSystem.AnActionEvent;
import com.intellij.openapi.options.ShowSettingsUtil;
import com.intellij.openapi.options.SearchableConfigurable;
import com.intellij.openapi.project.DumbAwareAction;

/** Open the original Git settings directly, without duplicating its options. */
public final class GitSettingsAction extends DumbAwareAction {
  @Override public void actionPerformed(AnActionEvent event) {
    if(event.getProject()!=null) ShowSettingsUtil.getInstance().showSettingsDialog(event.getProject(),
      configurable -> configurable instanceof SearchableConfigurable &&
        "vcs.Git".equals(((SearchableConfigurable)configurable).getId()),null);
  }
  @Override public void update(AnActionEvent event) {
    event.getPresentation().setEnabled(event.getProject()!=null);
  }
}
