package alhena;

import com.intellij.openapi.Disposable;
import com.intellij.openapi.actionSystem.ActionManager;
import com.intellij.openapi.actionSystem.ActionPlaces;
import com.intellij.openapi.actionSystem.AnAction;
import com.intellij.openapi.wm.WelcomeScreenCustomization;
import com.intellij.util.ui.JBUI;
import java.awt.BorderLayout;
import java.awt.Font;
import javax.swing.*;

/** Git-specific empty state, delegating opening/cloning to original platform actions. */
public final class AlhenaWelcome implements WelcomeScreenCustomization {
  @Override public JComponent createMainEmptyState(Disposable disposable) {
    JPanel content=new JPanel();
    content.setOpaque(false);
    content.setLayout(new BoxLayout(content,BoxLayout.Y_AXIS));
    JLabel title=new JLabel("Alhena");
    title.setFont(title.getFont().deriveFont(Font.BOLD,title.getFont().getSize2D()*2));
    title.setAlignmentX(0.5f);
    content.add(title);
    content.add(Box.createVerticalStrut(JBUI.scale(12)));
    JLabel subtitle=new JLabel("History, changes, and branches in one Git workspace.");
    subtitle.setAlignmentX(0.5f);
    content.add(subtitle);
    content.add(Box.createVerticalStrut(JBUI.scale(28)));
    JPanel buttons=new JPanel();
    buttons.setOpaque(false);
    buttons.add(button("Open Repository","WelcomeScreen.OpenProject"));
    buttons.add(Box.createHorizontalStrut(JBUI.scale(8)));
    buttons.add(button("Clone Repository","Vcs.VcsClone"));
    buttons.setAlignmentX(0.5f);
    content.add(buttons);
    JPanel centered=new JPanel(new BorderLayout());
    centered.setOpaque(false);
    centered.setBorder(JBUI.Borders.empty(95,20,20,20));
    centered.add(content,BorderLayout.NORTH);
    return centered;
  }
  private static JButton button(String text,String actionId) {
    JButton button=new JButton(text);
    button.setPreferredSize(JBUI.size(165,38));
    button.addActionListener(event -> {
      ActionManager manager=ActionManager.getInstance();
      AnAction action=manager.getAction(actionId);
      if(action!=null) manager.tryToExecute(action,null,button,ActionPlaces.WELCOME_SCREEN,true);
    });
    return button;
  }
}
