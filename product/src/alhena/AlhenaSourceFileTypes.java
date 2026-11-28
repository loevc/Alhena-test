package alhena;

import com.intellij.openapi.fileTypes.FileType;
import com.intellij.openapi.fileTypes.FileTypeRegistry;
import com.intellij.openapi.fileTypes.UnknownFileType;
import com.intellij.openapi.fileTypes.PlainTextFileType;
import com.intellij.openapi.fileTypes.impl.FileTypeOverrider;
import com.intellij.openapi.vfs.VirtualFile;
import java.util.Locale;
import java.util.Set;

/** Source languages without an installed provider still have predictable text extensions. */
public final class AlhenaSourceFileTypes implements FileTypeOverrider {
  private static final Set<String> SOURCE_EXTENSIONS=Set.of(
    "java","kt","kts","groovy","gradle","scala","py","pyi","rs","go",
    "c","h","cc","cpp","hpp","cxx","hxx","cs","js","jsx","ts","tsx",
    "rb","php","swift","sh","bash","ps1"
  );

  @Override public FileType getOverriddenFileType(VirtualFile file) {
    if(file.isDirectory()) return null;
    String extension=file.getExtension();
    if(extension==null || !SOURCE_EXTENSIONS.contains(extension.toLowerCase(Locale.ROOT))) return null;
    // A name-only lookup does not recurse through this overrider or sniff file
    // contents. Existing language types and explicit filename mappings win.
    FileType named=FileTypeRegistry.getInstance().getFileTypeByFileName(file.getName());
    return named==UnknownFileType.INSTANCE ? PlainTextFileType.INSTANCE:null;
  }
}
