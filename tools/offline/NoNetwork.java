package alhena.offline;

import java.net.InetAddress;
import java.net.SocketPermission;
import java.security.Permission;

/** Build-only guard for the pinned JDK 17/21; local compiler IPC remains available. */
@SuppressWarnings("removal")
public final class NoNetwork extends SecurityManager {
  private static boolean local(String host) {
    if (host.startsWith("[") && host.endsWith("]")) host = host.substring(1, host.length() - 1);
    return host.equalsIgnoreCase("localhost") || host.equals("127.0.0.1") ||
           host.equals("::1") || host.equals("0:0:0:0:0:0:0:1");
  }

  @Override public void checkConnect(String host, int port) {
    if (!local(host)) throw new SecurityException("ALHENA_OFFLINE: denied network connection to " + host);
  }

  @Override public void checkConnect(String host, int port, Object context) { checkConnect(host, port); }
  @Override public void checkMulticast(InetAddress address) {
    throw new SecurityException("ALHENA_OFFLINE: denied multicast");
  }
  @Override public void checkPermission(Permission permission) {
    if (permission instanceof SocketPermission &&
        (permission.getActions().contains("connect") || permission.getActions().equals("resolve"))) {
      String endpoint = permission.getName();
      String host = endpoint.startsWith("[") ? endpoint.substring(0, endpoint.indexOf(']') + 1) : endpoint.split(":", 2)[0];
      checkConnect(host, -1);
    }
  }
  @Override public void checkPermission(Permission permission, Object context) { checkPermission(permission); }
}
