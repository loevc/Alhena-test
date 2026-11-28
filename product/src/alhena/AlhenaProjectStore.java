package alhena;

import com.intellij.openapi.application.PathManager;
import com.intellij.openapi.project.ProjectStorePathManager;
import com.intellij.openapi.vfs.LocalFileSystem;
import com.intellij.openapi.vfs.VirtualFile;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Locale;

/** Product workspace state belongs to Alhena's config, not the repository's IDE project. */
public final class AlhenaProjectStore implements ProjectStorePathManager {
  @Override public Path getStoreDirectoryPath(Path projectRoot) {
    String identity=projectRoot.toAbsolutePath().normalize().toString().replace('\\','/');
    if(System.getProperty("os.name","").startsWith("Windows")) identity=identity.toLowerCase(Locale.ROOT);
    try {
      String key=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(identity.getBytes(StandardCharsets.UTF_8)));
      // JPS serializers require the store folder itself to retain the .idea name.
      return PathManager.getConfigDir().resolve("repositories").resolve(key).resolve(".idea");
    } catch(NoSuchAlgorithmException error) {
      throw new IllegalStateException("SHA-256 is required by the runtime",error);
    }
  }

  @Override public boolean testStoreDirectoryExistsForProjectRoot(Path projectRoot) {
    return Files.isDirectory(getStoreDirectoryPath(projectRoot));
  }

  @Override public VirtualFile getStoreDirectory(VirtualFile projectRoot) {
    if(!projectRoot.isDirectory() || !projectRoot.isInLocalFileSystem()) return null;
    return LocalFileSystem.getInstance().findFileByNioFile(getStoreDirectoryPath(projectRoot.toNioPath()));
  }

  @Override public boolean testStoreDirectoryExistsForProjectRoot(VirtualFile projectRoot) {
    return projectRoot.isDirectory() && projectRoot.isInLocalFileSystem()
      && Files.isDirectory(getStoreDirectoryPath(projectRoot.toNioPath()));
  }
}
