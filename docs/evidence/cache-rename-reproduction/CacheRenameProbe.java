import java.nio.file.*;
import java.nio.channels.FileChannel;
import java.nio.MappedByteBuffer;
import java.util.*;
public final class CacheRenameProbe {
  private static Path root;
  private static void attempt(String label,Path source,Path target) throws Exception {
    if(!source.toAbsolutePath().normalize().startsWith(root)||!target.toAbsolutePath().normalize().startsWith(root)) throw new IllegalArgumentException("Outside owned fixture");
    try { Files.move(source,target,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING); System.out.println(label+"|success"); }
    catch(java.io.IOException e) { System.out.println(label+"|"+e.getClass().getName()+"|"+e.getMessage()); }
  }
  public static void main(String[] args) throws Exception {
    Path fixtures=Path.of(args[0]).toAbsolutePath().normalize();
    if(!fixtures.endsWith("out/fixtures".replace('/',java.io.File.separatorChar))) throw new IllegalArgumentException("Expected fixture root");
    root=Files.createTempDirectory(fixtures,"workflow-cache-rename-");
    System.out.println("java="+System.getProperty("java.runtime.version")); System.out.println("fixture="+root);
    for(String mode:List.of("unheld","channel-open","mapped-channel-closed","mapped-and-channel-open")) {
      Path source=root.resolve(mode+".tmp"),target=root.resolve(mode+".data");Files.writeString(source,"new cache");Files.writeString(target,"old cache");
      if(mode.equals("unheld")) attempt(mode,source,target);
      else if(mode.equals("channel-open")) {try(FileChannel ch=FileChannel.open(target,StandardOpenOption.READ)){attempt(mode,source,target);}}
      else {
        MappedByteBuffer mapping;
        if(mode.equals("mapped-channel-closed")) {try(FileChannel ch=FileChannel.open(target,StandardOpenOption.READ)){mapping=ch.map(FileChannel.MapMode.READ_ONLY,0,ch.size());}attempt(mode,source,target);}
        else {try(FileChannel ch=FileChannel.open(target,StandardOpenOption.READ)){mapping=ch.map(FileChannel.MapMode.READ_ONLY,0,ch.size());attempt(mode,source,target);}}
        System.out.println(mode+"|mappingStillReadable="+(mapping.get(0)=='o'));
      }
    }
  }
}

