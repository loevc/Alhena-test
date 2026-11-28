package alhena;

import com.intellij.ide.ConsentOptionsProvider;
import com.intellij.openapi.application.ApplicationInfo;

/** No usage telemetry is collected by this product. No JetBrains consent is fabricated. */
public final class AlhenaConsent implements ConsentOptionsProvider {
  @Override public boolean isEAP() { return ApplicationInfo.getInstance().isEAP(); }
  @Override public boolean isActivatedWithFreeLicense() { return false; }
  @Override public boolean isSendingUsageStatsAllowed() { return false; }
  @Override public void setSendingUsageStatsAllowed(boolean allowed) { }
}
