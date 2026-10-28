package com.axx.mobile;

import android.content.Context;
import android.content.Intent;
import android.appwidget.AppWidgetManager;
import android.content.ComponentName;
import android.graphics.BitmapFactory;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;
import com.getcapacitor.PermissionState;
import android.Manifest;
import androidx.activity.result.ActivityResult;
import com.journeyapps.barcodescanner.ScanOptions;
import com.journeyapps.barcodescanner.ScanIntentResult;
import org.json.JSONObject;
import java.net.URI;
import java.io.ByteArrayOutputStream;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.security.cert.CertificateException;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.HostnameVerifier;

/** Credentials never cross the Capacitor bridge; TLS identity comes from the PC QR. */
@CapacitorPlugin(name = "AxxTransport", permissions = {@Permission(alias="camera", strings={Manifest.permission.CAMERA})})
public class AxxTransportPlugin extends Plugin {
    private static final String ALIAS = "axx.mobile.credentials.v1";
    private final ThreadPoolExecutor network = new ThreadPoolExecutor(2, 2, 0L, TimeUnit.MILLISECONDS, new ArrayBlockingQueue<>(8));
    private final ThreadPoolExecutor inputNetwork = new ThreadPoolExecutor(2, 2, 0L, TimeUnit.MILLISECONDS, new ArrayBlockingQueue<>(8));
    private JSONObject cachedProfile;
    private String tlsIdentity = "";
    private SSLSocketFactory socketFactory;
    private HostnameVerifier hostnameVerifier;

    private synchronized SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (!store.containsAlias(ALIAS)) {
            KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
            generator.generateKey();
        }
        return (SecretKey) store.getKey(ALIAS, null);
    }

    private synchronized void save(JSONObject profile) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key());
        String encrypted = Base64.encodeToString(cipher.doFinal(profile.toString().getBytes(StandardCharsets.UTF_8)), Base64.NO_WRAP);
        boolean saved = getContext().getSharedPreferences("axx_trust", Context.MODE_PRIVATE).edit()
            .putString("data", encrypted).putString("iv", Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP)).commit();
        if (!saved) throw new IllegalStateException("Could not save pairing");
        cachedProfile = new JSONObject(profile.toString());
    }

    private synchronized JSONObject loadProfile() throws Exception {
        if (cachedProfile != null) return cachedProfile;
        var prefs = getContext().getSharedPreferences("axx_trust", Context.MODE_PRIVATE);
        String data = prefs.getString("data", null);
        if (data == null) return null;
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(prefs.getString("iv", ""), Base64.NO_WRAP)));
        cachedProfile = new JSONObject(new String(cipher.doFinal(Base64.decode(data, Base64.NO_WRAP)), StandardCharsets.UTF_8));
        return cachedProfile;
    }

    static URI validateEndpoint(String value) throws Exception {
        URI uri = new URI(value);
        String host = uri.getHost();
        if (!"https".equals(uri.getScheme()) || host == null || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null
            || !(uri.getPath().isEmpty() || uri.getPath().equals("/")) || uri.getPort() < 1 || uri.getPort() > 65535)
            throw new IllegalArgumentException("Invalid PC HTTPS address");
        if (!host.matches("[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+")) throw new IllegalArgumentException("A local IP address is required");
        String[] parts = host.split("\\.");
        int[] octets = new int[4];
        for (int i=0;i<4;i++) {
            octets[i] = Integer.parseInt(parts[i]);
            if (octets[i] > 255 || !Integer.toString(octets[i]).equals(parts[i])) throw new IllegalArgumentException("Invalid IP address");
        }
        if (!(octets[0] == 10 || octets[0] == 192 && octets[1] == 168 || octets[0] == 172 && octets[1] >= 16 && octets[1] <= 31))
            throw new IllegalArgumentException("Only private LAN networks are supported");
        return uri;
    }

    static void checkPin(X509Certificate certificate, String fingerprint) throws Exception {
        certificate.checkValidity();
        if (!fingerprint.matches("[a-f0-9]{64}")) throw new CertificateException("Invalid fingerprint");
        byte[] expected = new byte[32];
        for (int i=0;i<32;i++) expected[i] = (byte) Integer.parseInt(fingerprint.substring(i*2, i*2+2), 16);
        byte[] actual = MessageDigest.getInstance("SHA-256").digest(certificate.getEncoded());
        if (expected.length != 32 || !MessageDigest.isEqual(expected, actual)) throw new CertificateException("PC identity changed. Generate a new pairing QR on your PC.");
    }

    private synchronized void configureTls(String pin, String host, HttpsURLConnection connection) throws Exception {
        if (!pin.matches("[a-f0-9]{64}")) throw new IllegalArgumentException("Invalid PC fingerprint");
        String identity=pin+"@"+host;
        if (!identity.equals(tlsIdentity)) {
        SSLContext tls = SSLContext.getInstance("TLS");
        tls.init(null, new TrustManager[]{new X509TrustManager() {
            public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
            public void checkClientTrusted(X509Certificate[] chain, String type) throws CertificateException { throw new CertificateException("No client certificate"); }
            public void checkServerTrusted(X509Certificate[] chain, String type) throws CertificateException {
                try {
                    if (chain.length == 0) throw new CertificateException("Empty certificate chain");
                    checkPin(chain[0], pin);
                } catch (Exception e) { throw new CertificateException("PC identity could not be verified", e); }
            }
        }}, null);
        socketFactory=tls.getSocketFactory();
        hostnameVerifier=(name,session)->name.equals(host);
        tlsIdentity=identity;
        }
        connection.setSSLSocketFactory(socketFactory);
        connection.setHostnameVerifier(hostnameVerifier);
    }

    private JSONObject exchange(JSONObject profile, String path, String method, JSONObject body) throws Exception {
        URI endpoint = validateEndpoint(profile.getString("endpoint"));
        if (!path.matches("/v1/[a-z/-]+(\\?[a-z_]+=[a-zA-Z0-9_-]+)?") || !(method.equals("GET") || method.equals("POST")))
            throw new IllegalArgumentException("Invalid mobile operation");
        var connection = (HttpsURLConnection) new URI(endpoint.getScheme(), null, endpoint.getHost(), endpoint.getPort(), null, null, null).resolve(path).toURL().openConnection();
        boolean reusable=false;
        try {
            // The QR certificate pin is the authority, independent of DHCP address changes.
            configureTls(profile.getString("fingerprint"),endpoint.getHost(),connection);
            connection.setInstanceFollowRedirects(false);
            boolean control=path.startsWith("/v1/control/") || path.startsWith("/v1/avatar/");
            connection.setConnectTimeout(control?1500:6000);
            connection.setReadTimeout(control?1500:method.equals("GET")?8000:75000);
            connection.setRequestMethod(method);
            connection.setRequestProperty("Accept", "application/json");
            if (profile.has("credential")) connection.setRequestProperty("Authorization", "Bearer " + profile.getString("credential"));
            if (body != null) {
                byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
                if (bytes.length > 2*1024*1024) throw new IllegalArgumentException("Request is too large");
                connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type", "application/json");
                connection.setFixedLengthStreamingMode(bytes.length);
                try (var output = connection.getOutputStream()) { output.write(bytes); }
            }
            int status = connection.getResponseCode();
            if (status >= 300 && status < 400) throw new IllegalStateException("The PC tried to redirect the connection");
            var input = status < 400 ? connection.getInputStream() : connection.getErrorStream();
            if (input == null) throw new IllegalStateException("The PC did not return a valid response");
            try (input) {
                ByteArrayOutputStream buffer = new ByteArrayOutputStream();
                byte[] chunk = new byte[8192];
                int count;
                while ((count = input.read(chunk)) != -1) {
                    if (buffer.size() + count > 8*1024*1024) throw new IllegalStateException("Response is too large");
                    buffer.write(chunk, 0, count);
                }
                byte[] bytes = buffer.toByteArray();
                JSONObject response = new JSONObject(new String(bytes, StandardCharsets.UTF_8));
                if (status >= 400 || !response.optBoolean("ok", true)) {
                    JSONObject error = response.optJSONObject("error");
                    throw new IllegalStateException(error == null ? "PC error ("+status+")" : error.optString("message", error.optString("code", "PC error")));
                }
                reusable=path.equals("/v1/control/events")||path.equals("/v1/control/status");
                return response;
            }
        } finally { if (!reusable) connection.disconnect(); }
    }

    private JSObject publicProfile(JSONObject profile) throws Exception {
        JSObject result = new JSObject();
        result.put("paired", profile != null);
        if (profile != null) for (String field : new String[]{"endpoint", "fingerprint", "device_id", "scopes"}) result.put(field, profile.get(field));
        return result;
    }

    private void submit(PluginCall call, CheckedAction action) {
        ThreadPoolExecutor executor=call.getString("path", "").startsWith("/v1/control/")?inputNetwork:network;
        try { executor.execute(() -> { try { action.run(); } catch (Exception e) { call.reject(e instanceof javax.net.ssl.SSLException ? "PC identity could not be verified. Generate a new QR on the PC; never bypass certificate checks." : e instanceof java.io.IOException ? "Cannot reach your PC. Keep Axx open, use the same Wi-Fi, and select Show new QR on the PC. Check that Windows Firewall allows Axx on your private network." : e.getMessage() == null ? "Could not connect to the PC" : e.getMessage()); } }); }
        catch (java.util.concurrent.RejectedExecutionException e) { call.reject("Axx is busy; try again"); }
    }
    private interface CheckedAction { void run() throws Exception; }

    @PluginMethod public void profile(PluginCall call) { submit(call, () -> call.resolve(publicProfile(loadProfile()))); }

    static byte[] shortcutPng(String value) {
        String prefix = "data:image/png;base64,";
        if (value == null || !value.startsWith(prefix) || value.length() > 2*1024*1024)
            throw new IllegalArgumentException("Invalid Axx image");
        byte[] bytes = java.util.Base64.getDecoder().decode(value.substring(prefix.length()));
        byte[] signature = {(byte)137,80,78,71,13,10,26,10};
        if (bytes.length < 24 || !java.util.Arrays.equals(java.util.Arrays.copyOf(bytes,8),signature))
            throw new IllegalArgumentException("A PNG image is required");
        var header = java.nio.ByteBuffer.wrap(bytes);
        int width=header.getInt(16), height=header.getInt(20);
        if (width < 16 || height < 16 || width > 1024 || height > 1024)
            throw new IllegalArgumentException("Invalid icon size");
        return bytes;
    }

    private int updateHomeIconBytes(byte[] bytes) throws Exception {
        var iconFile=new android.util.AtomicFile(new java.io.File(getContext().getFilesDir(),"home-character.png"));
        java.io.FileOutputStream output=null;
        try{output=iconFile.startWrite();output.write(bytes);iconFile.finishWrite(output);}
        catch(Exception error){if(output!=null)iconFile.failWrite(output);throw error;}
        AppWidgetManager manager=getContext().getSystemService(AppWidgetManager.class);
        int[] ids=manager.getAppWidgetIds(new ComponentName(getContext(),AxxHomeWidget.class));
        if(ids.length>0)manager.updateAppWidget(ids,AxxHomeWidget.views(getContext()));
        return ids.length;
    }

    @PluginMethod public void updateHomeIcon(PluginCall call) {
        getActivity().runOnUiThread(()->{
            try{updateHomeIconBytes(shortcutPng(call.getString("png")));call.resolve();}
            catch(Exception error){call.reject(error.getMessage());}
        });
    }

    @PluginMethod public void shortcut(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            try {
                AppWidgetManager manager=getContext().getSystemService(AppWidgetManager.class);
                if (manager == null || !manager.isRequestPinAppWidgetSupported())
                    throw new IllegalStateException("Your home screen does not support adding shortcuts from Axx.");
                byte[] bytes=shortcutPng(call.getString("png"));
                var bitmap=BitmapFactory.decodeByteArray(bytes,0,bytes.length);
                if(bitmap == null)throw new IllegalArgumentException("Could not read the Axx icon");
                var component=new ComponentName(getContext(),AxxHomeWidget.class);
                int count=updateHomeIconBytes(bytes);
                if(count==0 && !manager.requestPinAppWidget(component,null,null))throw new IllegalStateException("Could not request the home shortcut.");
                JSObject result=new JSObject();result.put("requested",count==0);call.resolve(result);
            }catch(Exception e){call.reject(e.getMessage());}
        });
    }

    @PluginMethod public void scan(PluginCall call) {
        if (getPermissionState("camera") != PermissionState.GRANTED) {
            requestPermissionForAlias("camera", call, "cameraPermission");
            return;
        }
        launchScanner(call);
    }

    @PermissionCallback private void cameraPermission(PluginCall call) {
        if (getPermissionState("camera") != PermissionState.GRANTED) {
            call.reject("Camera access is required to scan. Allow it in Android Settings → Apps → Axx Mobile → Permissions, or paste the pairing link from your PC.");
            return;
        }
        launchScanner(call);
    }

    private void launchScanner(PluginCall call) {
        ScanOptions options = new ScanOptions().setDesiredBarcodeFormats(ScanOptions.QR_CODE)
            .setPrompt("Scan the Axx QR on your PC").setBeepEnabled(false)
            .setOrientationLocked(false).setBarcodeImageEnabled(false);
        startActivityForResult(call, options.createScanIntent(getContext()), "scanned");
    }

    @PluginMethod public void pairingLink(PluginCall call) {
        Intent intent=getActivity().getIntent();
        String link=intent.getDataString();
        JSObject result=new JSObject();
        if (link!=null && link.startsWith("axx://pair?") && link.length()<=2048) {
            result.put("uri",link);
            intent.setData(null);
        }
        call.resolve(result);
    }

    @ActivityCallback private void scanned(PluginCall call, ActivityResult result) {
        if (call == null) return;
        String content = ScanIntentResult.parseActivityResult(result.getResultCode(), result.getData()).getContents();
        if (content == null) { call.reject("Scan cancelled or camera unavailable. You can paste the link from your PC."); return; }
        if (!content.startsWith("axx://pair?") || content.length() > 2048) { call.reject("This QR is not an Axx pairing link."); return; }
        JSObject response = new JSObject(); response.put("uri", content); call.resolve(response);
    }

    @PluginMethod public void pair(PluginCall call) {
        submit(call, () -> {
            Map<String,String> fields = pairingFields(call.getString("uri", ""));
            JSONObject profile = new JSONObject().put("endpoint", fields.get("endpoint")).put("fingerprint", fields.get("fingerprint"));
            JSONObject previous = loadProfile();
            if (previous != null && previous.getString("fingerprint").equals(fields.get("fingerprint")))
                profile.put("credential", previous.getString("credential"));
            JSONObject body = new JSONObject().put("code", fields.get("code")).put("device_name", android.os.Build.MODEL);
            JSONObject claimed = exchange(profile, "/v1/pair/claim", "POST", body);
            for (String field : new String[]{"device_id", "credential", "scopes"}) profile.put(field, claimed.get(field));
            save(profile);
            call.resolve(publicProfile(profile));
        });
    }

    static Map<String,String> pairingFields(String value) throws Exception {
        if (value.length()>2048) throw new IllegalArgumentException("Pairing link is too long");
        URI uri=new URI(value);
        if (!"axx".equals(uri.getScheme()) || !"pair".equals(uri.getHost()) || uri.getRawQuery()==null
                || uri.getUserInfo()!=null || uri.getPort()!=-1 || !uri.getPath().isEmpty() || uri.getFragment()!=null)
            throw new IllegalArgumentException("Scan the QR generated by Axx on your PC");
        Map<String,String> fields=new HashMap<>();
        for (String pair:uri.getRawQuery().split("&",-1)) {
            String[] parts=pair.split("=",2);
            if (parts.length!=2 || fields.put(parts[0],URLDecoder.decode(parts[1],"UTF-8"))!=null)
                throw new IllegalArgumentException("Invalid pairing QR");
        }
        if (fields.size()!=3 || !fields.containsKey("endpoint") || !fields.containsKey("fingerprint") || !fields.containsKey("code"))
            throw new IllegalArgumentException("Incomplete pairing QR");
        validateEndpoint(fields.get("endpoint"));
        if (!fields.get("fingerprint").matches("[a-f0-9]{64}") || !fields.get("code").matches("[A-Za-z0-9_-]{20,128}"))
            throw new IllegalArgumentException("Invalid pairing identity or code");
        return fields;
    }

    @PluginMethod public void request(PluginCall call) {
        submit(call, () -> {
            JSONObject profile = loadProfile();
            if (profile == null) throw new IllegalStateException("Pair a PC first");
            String path = call.getString("path", "");
            if (path.startsWith("/v1/pair")) throw new IllegalArgumentException("Use the pairing flow");
            call.resolve(JSObject.fromJSONObject(exchange(profile, path, call.getString("method", "GET"), call.getObject("body"))));
        });
    }

    @PluginMethod public void forget(PluginCall call) {
        submit(call, () -> {
            if (!getContext().getSharedPreferences("axx_trust", Context.MODE_PRIVATE).edit().clear().commit()) throw new IllegalStateException("Could not forget the PC");
            synchronized(this){cachedProfile=null;}
            call.resolve();
        });
    }

    @Override protected void handleOnDestroy() { network.shutdownNow(); inputNetwork.shutdownNow(); }
}
