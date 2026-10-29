package com.axx.mobile;

import android.app.Activity;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.provider.DocumentsContract;
import android.provider.OpenableColumns;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.AtomicFile;
import android.util.Base64;
import androidx.activity.result.ActivityResult;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import org.json.JSONArray;
import org.json.JSONObject;

/** Native document selection and bounded, encrypted transfer storage. */
@CapacitorPlugin(name = "AxxFiles")
public class AxxFilesPlugin extends Plugin {
    static final int CHUNK_SIZE = 262144;
    static final long MAX_SIZE = 5L * 1024 * 1024 * 1024;
    private static final String KEY_ALIAS = "axx.mobile.files.v1";
    private final ThreadPoolExecutor worker = new ThreadPoolExecutor(1, 1, 0L, TimeUnit.MILLISECONDS, new ArrayBlockingQueue<>(16));
    private boolean pickerOpen;

    @FunctionalInterface private interface Work { void run() throws Exception; }
    private void submit(PluginCall call, Work work) {
        try { worker.execute(() -> { try { work.run(); } catch (Exception error) { call.reject(error.getMessage() == null ? "No se pudo procesar el archivo" : error.getMessage()); } }); }
        catch (java.util.concurrent.RejectedExecutionException error) { call.reject("Hay una operación de archivos en curso. Vuelve a intentarlo."); }
    }
    static String checkedId(String id) {
        if (id == null || !id.matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")) throw new IllegalArgumentException("Identificador de archivo no válido");
        return UUID.fromString(id).toString();
    }
    static String checkedName(String name) {
        if (name == null || name.isBlank() || name.length() > 180 || name.endsWith(" ") || name.endsWith(".") || name.matches(".*[\\\\/<>:\"|?*\\p{Cntrl}].*")
                || name.matches("(?i)(CON|PRN|AUX|NUL|CONIN\\$|CONOUT\\$|COM[1-9¹²³]|LPT[1-9¹²³])(\\..*)?")) throw new IllegalArgumentException("Nombre de archivo no válido");
        return name;
    }
    static void checkedManifest(long size, String hash, int chunkSize) {
        if (size < 0 || size > MAX_SIZE || hash == null || !hash.matches("[0-9a-f]{64}") || chunkSize != CHUNK_SIZE) throw new IllegalArgumentException("Tamaño, huella o bloques no válidos");
    }
    static int expectedLength(long size, int index) {
        if (index < 0 || (long) index * CHUNK_SIZE >= size) throw new IllegalArgumentException("Bloque fuera del archivo");
        return (int) Math.min(CHUNK_SIZE, size - (long) index * CHUNK_SIZE);
    }
    private File root() throws Exception {
        File root = new File(getContext().getNoBackupFilesDir().getCanonicalFile(), "transfer-v1");
        if (Files.isSymbolicLink(root.toPath())) throw new IllegalStateException("La bandeja no puede ser un enlace");
        if (!root.isDirectory() && !root.mkdirs()) throw new IllegalStateException("No se puede abrir la bandeja de archivos");
        return root;
    }
    private File directory(String id) throws Exception {
        File dir = new File(root(), checkedId(id));
        if (Files.isSymbolicLink(dir.toPath())) throw new IllegalStateException("El archivo no puede ser un enlace");
        return dir;
    }
    private File storageFile(String id, String part) throws Exception {
        File file = new File(directory(id), part + ".enc");
        for (String suffix : new String[]{"", ".bak", ".new"}) if (Files.isSymbolicLink(new File(file.getPath() + suffix).toPath())) throw new IllegalStateException("El bloque no puede ser un enlace");
        return file;
    }
    private SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
        if (!store.containsAlias(KEY_ALIAS)) {
            KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setKeySize(256).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
            generator.generateKey();
        }
        return (SecretKey) store.getKey(KEY_ALIAS, null);
    }
    private byte[] aad(String id, String part) { return ("axx-files-v1:" + checkedId(id) + ":" + part).getBytes(StandardCharsets.UTF_8); }
    static byte[] seal(SecretKey key, byte[] aad, byte[] clear) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, key); cipher.updateAAD(aad);
        byte[] encrypted = cipher.doFinal(clear), result = new byte[12 + encrypted.length];
        System.arraycopy(cipher.getIV(), 0, result, 0, 12); System.arraycopy(encrypted, 0, result, 12, encrypted.length); return result;
    }
    static byte[] open(SecretKey key, byte[] aad, byte[] bytes) throws Exception {
        if (bytes.length < 28) throw new IllegalArgumentException("Archivo cifrado incompleto");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, Arrays.copyOf(bytes, 12))); cipher.updateAAD(aad);
        return cipher.doFinal(bytes, 12, bytes.length - 12);
    }
    private void write(String id, String part, byte[] clear) throws Exception {
        File dir = directory(id); if (!dir.isDirectory() && !dir.mkdirs()) throw new IllegalStateException("No se puede guardar el archivo");
        byte[] encrypted = seal(key(), aad(id, part), clear);
        AtomicFile file = new AtomicFile(storageFile(id, part)); FileOutputStream output = null;
        try { output = file.startWrite(); output.write(encrypted); file.finishWrite(output); }
        catch (Exception error) { if (output != null) file.failWrite(output); throw error; }
    }
    private byte[] read(String id, String part, int limit) throws Exception {
        byte[] bytes;
        try (FileInputStream input = new AtomicFile(storageFile(id, part)).openRead()) {
            long length = input.getChannel().size(); if (length < 28 || length > limit + 28) throw new IllegalStateException("Archivo cifrado no válido");
            bytes = new byte[(int) length]; int offset = 0;
            while (offset < bytes.length) { int count = input.read(bytes, offset, bytes.length - offset); if (count < 0) throw new IllegalStateException("Archivo cifrado incompleto"); offset += count; }
            if (input.read() != -1) throw new IllegalStateException("Archivo cifrado modificado durante la lectura");
        }
        return open(key(), aad(id, part), bytes);
    }
    private JSONObject metadata(String id) throws Exception { return new JSONObject(new String(read(id, "meta", 16384), StandardCharsets.UTF_8)); }
    private void save(JSONObject metadata) throws Exception { write(metadata.getString("file_id"), "meta", metadata.toString().getBytes(StandardCharsets.UTF_8)); }
    private void resolve(PluginCall call, JSONObject result) throws Exception { call.resolve(JSObject.fromJSONObject(result)); }
    private String id(PluginCall call) { return checkedId(call.getString("file_id", call.getString("transfer_id"))); }
    private static String hex(byte[] bytes) { StringBuilder result = new StringBuilder(); for (byte b : bytes) result.append(String.format("%02x", b & 255)); return result.toString(); }
    private JSONObject newRecord(String id, String name, long size, String hash, String direction, String state) throws Exception {
        return new JSONObject().put("file_id", id).put("transfer_id", id).put("name", checkedName(name)).put("size", size).put("sha256", hash)
            .put("chunk_size", CHUNK_SIZE).put("next_index", 0).put("confirmed_bytes", 0).put("direction", direction).put("state", state).put("created_at", System.currentTimeMillis());
    }

    @PluginMethod public void choose(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            if (pickerOpen) { call.reject("El selector de documentos ya está abierto"); return; }
            pickerOpen = true;
            Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*");
            try { startActivityForResult(call, intent, "chosen"); }
            catch (Exception error) { pickerOpen = false; call.reject("No se puede abrir el selector de documentos"); }
        });
    }
    @ActivityCallback private void chosen(PluginCall call, ActivityResult result) {
        pickerOpen = false; if (call == null) return;
        if (result.getResultCode() != Activity.RESULT_OK || result.getData() == null || result.getData().getData() == null) { call.reject("Selección cancelada"); return; }
        Uri uri = result.getData().getData();
        submit(call, () -> {
            String name = "Archivo";
            try (Cursor cursor = getContext().getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE}, null, null, null)) {
                if (cursor != null && cursor.moveToFirst()) {
                    int column = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME); if (column >= 0 && !cursor.isNull(column)) name = cursor.getString(column);
                    column = cursor.getColumnIndex(OpenableColumns.SIZE); if (column >= 0 && !cursor.isNull(column) && cursor.getLong(column) > MAX_SIZE) throw new IllegalArgumentException("El máximo por archivo es 5 GiB");
                }
            }
            String fileId = UUID.randomUUID().toString(); JSONObject record = newRecord(fileId, name, 0, "", "to_pc", "importing"); save(record);
            try (InputStream input = getContext().getContentResolver().openInputStream(uri)) {
                if (input == null) throw new IllegalStateException("No se puede leer el documento");
                MessageDigest digest = MessageDigest.getInstance("SHA-256"); byte[] buffer = new byte[CHUNK_SIZE]; long size = 0; int index = 0;
                while (true) {
                    if (Thread.currentThread().isInterrupted()) throw new InterruptedException("Importación interrumpida");
                    int length = 0;
                    while (length < buffer.length) { int count = input.read(buffer, length, buffer.length - length); if (count < 0) break; if (count == 0) { int one = input.read(); if (one < 0) break; buffer[length++] = (byte) one; } else length += count; }
                    if (length == 0) break; size += length;
                    if (size > MAX_SIZE) throw new IllegalArgumentException("El máximo por archivo es 5 GiB");
                    digest.update(buffer, 0, length); write(fileId, Integer.toString(index++), Arrays.copyOf(buffer, length));
                    record.put("size", size).put("confirmed_bytes", size).put("next_index", index); save(record);
                }
                record.put("size", size).put("sha256", hex(digest.digest())).put("state", "ready"); save(record); resolve(call, record);
            } catch (Exception error) { remove(fileId); throw error; }
        });
    }

    @PluginMethod public void readChunk(PluginCall call) { submit(call, () -> {
        String fileId = id(call); JSONObject record = metadata(fileId);
        if (!record.getString("state").equals("ready") && !record.getString("state").equals("received")) throw new IllegalStateException("El archivo aún no está completo");
        int index = call.getInt("index", -1); byte[] chunk = read(fileId, Integer.toString(index), CHUNK_SIZE);
        if (chunk.length != expectedLength(record.getLong("size"), index)) throw new IllegalStateException("Longitud de bloque no válida");
        resolve(call, new JSONObject().put("data", Base64.encodeToString(chunk, Base64.NO_WRAP)).put("index", index).put("bytes", chunk.length));
    }); }
    @PluginMethod public void beginReceive(PluginCall call) { submit(call, () -> {
        String fileId = id(call), name = checkedName(call.getString("name")), hash = call.getString("sha256");
        Object value = call.getData().opt("size");
        if (!(value instanceof Number) || ((Number) value).doubleValue() != ((Number) value).longValue()) throw new IllegalArgumentException("Tamaño de archivo no válido");
        long size = ((Number) value).longValue(); checkedManifest(size, hash, call.getInt("chunk_size", CHUNK_SIZE));
        File meta = new File(directory(fileId), "meta.enc"); JSONObject record;
        if (meta.exists() || new File(meta.getPath() + ".bak").exists()) {
            record = metadata(fileId);
            if (!record.getString("direction").equals("to_phone") || record.getLong("size") != size || !record.getString("sha256").equals(hash) || !record.getString("name").equals(name)) throw new IllegalArgumentException("El identificador ya pertenece a otro archivo");
        } else { record = newRecord(fileId, name, size, hash, "to_phone", "receiving"); save(record); }
        resolve(call, record);
    }); }
    @PluginMethod public void writeChunk(PluginCall call) { submit(call, () -> {
        String fileId = id(call); JSONObject record = metadata(fileId); int index = call.getInt("index", -1), next = record.getInt("next_index");
        if (!record.getString("direction").equals("to_phone") || !record.getString("state").equals("receiving")) throw new IllegalStateException("El archivo no está recibiendo datos");
        String encoded = call.getString("data"); if (encoded == null || encoded.length() > 4 * ((CHUNK_SIZE + 2) / 3) || !encoded.matches("[A-Za-z0-9+/]*={0,2}")) throw new IllegalArgumentException("Bloque no válido");
        byte[] bytes = Base64.decode(encoded, Base64.NO_WRAP);
        if (bytes.length != expectedLength(record.getLong("size"), index) || index > next) throw new IllegalArgumentException("Longitud u orden de bloque no válido");
        if (index < next) { if (!MessageDigest.isEqual(bytes, read(fileId, Integer.toString(index), CHUNK_SIZE))) throw new IllegalArgumentException("El bloque repetido tiene contenido diferente"); }
        else { write(fileId, Integer.toString(index), bytes); record.put("next_index", next + 1).put("confirmed_bytes", (long) index * CHUNK_SIZE + bytes.length); save(record); }
        resolve(call, record);
    }); }
    private void verify(JSONObject record, OutputStream output) throws Exception {
        long size = record.getLong("size"), count = 0; String fileId = record.getString("file_id"); MessageDigest digest = MessageDigest.getInstance("SHA-256");
        int chunks = (int) ((size + CHUNK_SIZE - 1) / CHUNK_SIZE);
        if (record.getInt("next_index") != chunks) throw new IllegalStateException("Faltan bloques del archivo");
        for (int index = 0; index < chunks; index++) {
            if (Thread.currentThread().isInterrupted()) throw new InterruptedException("Verificación interrumpida");
            byte[] bytes = read(fileId, Integer.toString(index), CHUNK_SIZE);
            if (bytes.length != expectedLength(size, index)) throw new IllegalStateException("Longitud de bloque no válida");
            digest.update(bytes); count += bytes.length; if (output != null) output.write(bytes);
        }
        if (count != size || !hex(digest.digest()).equals(record.getString("sha256"))) throw new IllegalStateException("La integridad del archivo no coincide");
    }
    @PluginMethod public void finishReceive(PluginCall call) { submit(call, () -> {
        JSONObject record = metadata(id(call));
        if (!record.getString("direction").equals("to_phone")) throw new IllegalArgumentException("No es una recepción");
        if (!record.getString("state").equals("received")) { verify(record, null); record.put("state", "received"); save(record); }
        resolve(call, record);
    }); }
    @PluginMethod public void list(PluginCall call) { submit(call, () -> {
        JSONArray files = new JSONArray(); File[] dirs = root().listFiles(); int unavailable = 0;
        if (dirs != null) for (File dir : dirs) if (dir.isDirectory()) {
            try { files.put(metadata(dir.getName())); }
            catch (Exception error) {
                unavailable++;
                try { files.put(new JSONObject().put("file_id", checkedId(dir.getName())).put("name", "Archivo no disponible").put("state", "unavailable")); }
                catch (IllegalArgumentException ignored) { /* Unknown directories are never traversed. */ }
            }
        }
        resolve(call, new JSONObject().put("files", files).put("unavailable", unavailable));
    }); }

    @PluginMethod public void export(PluginCall call) { submit(call, () -> {
        JSONObject record = metadata(id(call));
        if (!record.getString("state").equals("ready") && !record.getString("state").equals("received")) throw new IllegalStateException("El archivo aún no está completo");
        verify(record, null);
        getActivity().runOnUiThread(() -> {
            if (pickerOpen) { call.reject("El selector de documentos ya está abierto"); return; } pickerOpen = true;
            Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("application/octet-stream").putExtra(Intent.EXTRA_TITLE, record.optString("name"));
            try { startActivityForResult(call, intent, "exported"); }
            catch (Exception error) { pickerOpen = false; call.reject("No se puede abrir el selector de destino"); }
        });
    }); }
    @ActivityCallback private void exported(PluginCall call, ActivityResult result) {
        pickerOpen = false; if (call == null) return;
        if (result.getResultCode() != Activity.RESULT_OK || result.getData() == null || result.getData().getData() == null) { call.reject("Guardado cancelado"); return; }
        Uri uri = result.getData().getData();
        submit(call, () -> {
            String fileId = id(call);
            try (OutputStream output = getContext().getContentResolver().openOutputStream(uri, "w")) {
                if (output == null) throw new IllegalStateException("No se puede guardar en ese destino"); verify(metadata(fileId), output);
            } catch (Exception error) { try { DocumentsContract.deleteDocument(getContext().getContentResolver(), uri); } catch (Exception ignored) { /* Provider may keep a partial export; never confirm it. */ } throw error; }
            resolve(call, new JSONObject().put("file_id", fileId).put("exported", true));
        });
    }
    private void remove(String fileId) throws Exception {
        File dir = directory(fileId); File[] children = dir.listFiles();
        if (children != null) for (File file : children) if (!file.isFile() || !file.delete()) throw new IllegalStateException("No se pudo limpiar el archivo parcial");
        if (dir.exists() && !dir.delete()) throw new IllegalStateException("No se pudo limpiar la recepción parcial");
    }
    @PluginMethod public void cancel(PluginCall call) { submit(call, () -> {
        String fileId = id(call); File dir = directory(fileId);
        if (dir.exists()) { JSONObject record = metadata(fileId); if (record.getString("state").equals("ready") || record.getString("state").equals("received")) { resolve(call, new JSONObject().put("cancelled", false).put("preserved", true)); return; } remove(fileId); }
        resolve(call, new JSONObject().put("cancelled", true));
    }); }
    @PluginMethod public void deleteCopy(PluginCall call) { submit(call, () -> {
        String fileId = id(call); remove(fileId);
        resolve(call, new JSONObject().put("file_id", fileId).put("deleted", true));
    }); }
    @Override protected void handleOnDestroy() { worker.shutdownNow(); }
}
