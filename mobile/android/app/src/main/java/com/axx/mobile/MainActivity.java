package com.axx.mobile;

import com.getcapacitor.BridgeActivity;
import android.os.Bundle;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.drawable.ColorDrawable;
import androidx.core.view.WindowCompat;

public class MainActivity extends BridgeActivity {
    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (getBridge()!=null) getBridge().triggerWindowJSEvent("axxPairingLink");
    }
    @Override public void onCreate(Bundle savedInstanceState) {
        registerPlugin(AxxTransportPlugin.class);
        registerPlugin(AxxVoicePlugin.class);
        super.onCreate(savedInstanceState);
        // App sizing is independent of Android; the system text option remains available in PC settings.
        boolean systemText = getSharedPreferences("axx_display", MODE_PRIVATE).getBoolean("system_text", false);
        getBridge().getWebView().getSettings().setTextZoom(systemText ? Math.round(getResources().getConfiguration().fontScale * 100) : 100);
        applyAppearance(getSharedPreferences("axx_display", MODE_PRIVATE).getString("theme", "light"));
    }
    void applyAppearance(String theme) {
        boolean dark = "dark".equals(theme);
        setTheme(dark ? R.style.AppTheme_NoActionBar_Dark : R.style.AppTheme_NoActionBar);
        int color = Color.parseColor(dark ? "#090b10" : "#f6f7f9");
        getWindow().setBackgroundDrawable(new ColorDrawable(color));
        getWindow().getDecorView().setBackgroundColor(color);
        getWindow().setStatusBarColor(color);
        getWindow().setNavigationBarColor(color);
        var bars = WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView());
        bars.setAppearanceLightStatusBars(!dark);
        bars.setAppearanceLightNavigationBars(!dark);
    }
    @Override public void onConfigurationChanged(Configuration configuration) {
        super.onConfigurationChanged(configuration);
        applyAppearance(getSharedPreferences("axx_display", MODE_PRIVATE).getString("theme", "light"));
    }
}
