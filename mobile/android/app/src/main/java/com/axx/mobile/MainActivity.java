package com.axx.mobile;

import com.getcapacitor.BridgeActivity;
import android.os.Bundle;
import android.content.Intent;

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
    }
}
