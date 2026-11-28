import com.sun.tools.attach.VirtualMachine;

/** Attaches only to the PID explicitly supplied by the smoke runner. */
public final class Attach {
  public static void main(String[] args) throws Exception {
    VirtualMachine vm = VirtualMachine.attach(args[0]);
    try { vm.loadAgent(args[1], args[2]); }
    finally { vm.detach(); }
  }
}
