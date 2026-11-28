using System;
using System.IO;
using System.Windows.Automation;
using System.Runtime.InteropServices;

// Test-only UI Automation driver. Every lookup is scoped to the supplied app PID.
internal static class NativeChooser {
  [DllImport("user32.dll")] private static extern IntPtr SendMessage(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);
  [DllImport("user32.dll")] private static extern bool SetForegroundWindow(IntPtr window);
  [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint process);
  [DllImport("user32.dll")] private static extern IntPtr GetDlgItem(IntPtr window, int id);
  private static AutomationElement Dialog(int pid) {
    var windows = AutomationElement.RootElement.FindAll(TreeScope.Children,
      new PropertyCondition(AutomationElement.ProcessIdProperty, pid));
    foreach (AutomationElement window in windows) {
      if (window.Current.ClassName == "#32770" || window.Current.Name == "Open File or Project" || window.Current.Name == "Open Project") return window;
      var child = window.FindFirst(TreeScope.Descendants,
        new AndCondition(new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Window),
          new PropertyCondition(AutomationElement.ClassNameProperty, "#32770")));
      if (child != null && child.Current.ProcessId == pid) return child;
    }
    foreach (AutomationElement window in windows) Console.Error.WriteLine("Owned window: class=" + window.Current.ClassName + " title=" + window.Current.Name);
    throw new InvalidOperationException("No native file dialog in acceptance process " + pid);
  }

  private static void Dump(AutomationElement root, int depth) {
    if (depth > 8) return;
    var type = root.Current.ControlType;
    if (type == ControlType.Window || type == ControlType.Edit || type == ControlType.ComboBox || type == ControlType.Button || type == ControlType.ToolBar) {
      Console.WriteLine("id=" + root.Current.AutomationId + " type=" + type.ProgrammaticName +
        " class=" + root.Current.ClassName + " name=" + root.Current.Name);
    }
    foreach (AutomationElement child in root.FindAll(TreeScope.Children, Condition.TrueCondition)) Dump(child, depth + 1);
  }

  [STAThread]
  private static int Main(string[] args) {
    try {
      int pid = Int32.Parse(args[0]);
      var dialog = Dialog(pid);
      if (args[1] == "inspect") { Dump(dialog, 0); return 0; }
      if (args[1] == "cancel") {
        IntPtr handle = new IntPtr(dialog.Current.NativeWindowHandle);
        uint cancelOwner;
        GetWindowThreadProcessId(handle, out cancelOwner);
        if (handle == IntPtr.Zero || cancelOwner != pid) throw new InvalidOperationException("Native cancel dialog owner mismatch");
        SendMessage(handle, 0x0111, new IntPtr(2), IntPtr.Zero);
        Console.WriteLine("nativeCancellationInvoked=true");
        return 0;
      }
      if (args[1] != "select" || args.Length != 4) throw new ArgumentException("pid inspect|select path fixtureRoot");
      string path = Path.GetFullPath(args[2]);
      string fixtureRoot = Path.GetFullPath(args[3]).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
      if (!path.StartsWith(fixtureRoot, StringComparison.OrdinalIgnoreCase) ||
          (!Directory.Exists(Path.Combine(path, ".git")) && !File.Exists(Path.Combine(path, ".git")))) {
        throw new InvalidOperationException("Refuse non-fixture path");
      }
      var address = dialog.FindFirst(TreeScope.Descendants,
        new AndCondition(new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.ToolBar),
          new PropertyCondition(AutomationElement.AutomationIdProperty, "1001")));
      if (address == null || !address.Current.Name.EndsWith(path, StringComparison.OrdinalIgnoreCase)) {
        throw new InvalidOperationException("Native chooser is not displaying the intended fixture directory");
      }
      Console.WriteLine("nativeDirectoryMatchesFixture=true");
      var currentConfirm = dialog.FindFirst(TreeScope.Descendants, new PropertyCondition(AutomationElement.AutomationIdProperty, "1"));
      object currentPattern;
      if (currentConfirm == null || !currentConfirm.TryGetCurrentPattern(InvokePattern.Pattern, out currentPattern)) throw new InvalidOperationException("No native folder confirmation");
      IntPtr buttonHandle = new IntPtr(currentConfirm.Current.NativeWindowHandle);
      IntPtr dialogHandle = new IntPtr(dialog.Current.NativeWindowHandle);
      if (buttonHandle == IntPtr.Zero) buttonHandle = GetDlgItem(dialogHandle, 1);
      uint owner;
      GetWindowThreadProcessId(dialogHandle, out owner);
      Console.WriteLine("dialogHandle="+dialogHandle+" buttonHandle="+buttonHandle+" owner="+owner+" expected="+pid);
      if (dialogHandle == IntPtr.Zero || owner != pid) throw new InvalidOperationException("Native dialog owner mismatch");
      if (buttonHandle != IntPtr.Zero) {
        GetWindowThreadProcessId(buttonHandle, out owner);
        if (owner != pid) throw new InvalidOperationException("Native button owner mismatch");
        SetForegroundWindow(dialogHandle);
        SendMessage(buttonHandle, 0x00F5, IntPtr.Zero, IntPtr.Zero);
      } else {
        // DirectUI can expose a virtual button without HWND. Dispatch its IDOK
        // command to the verified native dialog; still no global input.
        SendMessage(dialogHandle, 0x0111, new IntPtr(1), IntPtr.Zero);
      }
      Console.WriteLine("nativeConfirmationInvoked=true");
      return 0;

    } catch (Exception error) { Console.Error.WriteLine(error); return 1; }
  }
}
