import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;

/** Does not send external traffic: the guard must throw before socket connect. */
public final class NetworkProbe {
  public static void main(String[] args) throws Exception {
    if (System.getSecurityManager() == null) throw new AssertionError("Network guard is absent");
    try (Socket remote = new Socket()) {
      remote.connect(new InetSocketAddress("203.0.113.1", 443), 1000);
      throw new AssertionError("External connection was allowed");
    }
    catch (SecurityException expected) {
      if (!expected.getMessage().startsWith("ALHENA_OFFLINE:")) throw expected;
      System.out.println("External connection denied by offline guard");
    }
    try (ServerSocket server = new ServerSocket(0, 1, InetAddress.getByName("127.0.0.1"));
         Socket client = new Socket("127.0.0.1", server.getLocalPort());
         Socket accepted = server.accept()) {
      System.out.println("Loopback compiler IPC allowed");
    }
  }
}
