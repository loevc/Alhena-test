package alhena;

import com.intellij.openapi.updateSettings.UpdateStrategyCustomization;

/** Alhena packages are updated as a product, never through IDEA's release channels. */
public final class AlhenaUpdates extends UpdateStrategyCustomization {
  @Override public boolean forceEapUpdateChannelForEapBuilds() { return false; }
}
