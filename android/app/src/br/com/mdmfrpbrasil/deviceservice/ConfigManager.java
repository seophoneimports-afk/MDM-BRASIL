package br.com.mdmfrpbrasil.deviceservice;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.provider.Settings;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;

public class ConfigManager {

    private static final String PREF_NAME = "mdm_device_service_pref";

    // Official State Machine States
    public static final String STATE_PENDING = "PENDING";
    public static final String STATE_AUTHORIZED = "AUTHORIZED";
    public static final String STATE_PROCESSING = "PROCESSING";
    public static final String STATE_COMPLETED = "COMPLETED";
    public static final String STATE_PAID = "PAID";
    public static final String STATE_DESTROY_APK = "DESTROY_APK";

    // Legacy compatibility constants
    public static final String STATE_ACTIVE = "ACTIVE";
    public static final String STATE_SERVICE_PENDING = "SERVICE_PENDING";
    public static final String STATE_RELEASED = "RELEASED";

    private static final String KEY_STATE = "state";
    private static final String KEY_OPERATION_ID = "operation_id";
    private static final String KEY_CLIENT = "client";
    private static final String KEY_SERVICE = "service";
    private static final String KEY_VALUE = "value";
    private static final String KEY_PIX = "pix";
    private static final String KEY_LOGO_PATH = "logo_path";
    private static final String KEY_QR_PATH = "qr_path";
    private static final String KEY_SUPPORT_PHONE = "support_phone";
    private static final String KEY_AUTHORIZED_BY = "authorized_by";
    private static final String KEY_AUTHORIZED_AT = "authorized_at";

    private final SharedPreferences prefs;
    private final Context context;

    public ConfigManager(Context context) {
        this.context = context.getApplicationContext();
        this.prefs = this.context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
    }

    public boolean isPaidOrUnlocked() {
        String s = getState();
        return STATE_PAID.equalsIgnoreCase(s) || STATE_COMPLETED.equalsIgnoreCase(s) || STATE_RELEASED.equalsIgnoreCase(s) || STATE_ACTIVE.equalsIgnoreCase(s) || STATE_DESTROY_APK.equalsIgnoreCase(s);
    }

    public String normalizeState(String state) {
        if (state == null || state.isEmpty()) return STATE_PENDING;
        if ("DESTROY_APK".equalsIgnoreCase(state) || "DESTROYED".equalsIgnoreCase(state) || "UNINSTALL".equalsIgnoreCase(state)) {
            return STATE_DESTROY_APK;
        }
        if ("PAID".equalsIgnoreCase(state) || "RELEASE".equalsIgnoreCase(state) || "RELEASED".equalsIgnoreCase(state) || "COMPLETED".equalsIgnoreCase(state) || "ACTIVE".equalsIgnoreCase(state)) {
            return STATE_PAID;
        }
        if ("AUTHORIZED".equalsIgnoreCase(state)) {
            return STATE_AUTHORIZED;
        }
        if ("PROCESSING".equalsIgnoreCase(state)) {
            return STATE_PROCESSING;
        }
        return STATE_PENDING;
    }

    public String getState() {
        String saved = prefs.getString(KEY_STATE, STATE_PENDING);
        return normalizeState(saved);
    }

    public void setAuthoritativeState(String state, String operationId, String authorizedBy) {
        String normalized = normalizeState(state);
        SharedPreferences.Editor editor = prefs.edit();
        editor.putString(KEY_STATE, normalized);
        if (operationId != null && !operationId.isEmpty()) {
            editor.putString(KEY_OPERATION_ID, operationId);
        }
        if (authorizedBy != null && !authorizedBy.isEmpty()) {
            editor.putString(KEY_AUTHORIZED_BY, authorizedBy);
            editor.putLong(KEY_AUTHORIZED_AT, System.currentTimeMillis());
        }
        editor.apply();
        exportStatusJson();
    }

    public void setState(String state) {
        setAuthoritativeState(state, null, null);
    }

    public String getOperationId() {
        return prefs.getString(KEY_OPERATION_ID, "OP-2026-OFICIAL");
    }

    public String getClient() {
        return prefs.getString(KEY_CLIENT, "Cliente Autorizado");
    }

    public String getService() {
        return prefs.getString(KEY_SERVICE, "Serviço Técnico Autorizado");
    }

    public String getValue() {
        return prefs.getString(KEY_VALUE, "R$ 250,00");
    }

    public String getPix() {
        return prefs.getString(KEY_PIX, "19994827743");
    }

    public String getLogoPath() {
        return prefs.getString(KEY_LOGO_PATH, "");
    }

    public String getQrPath() {
        return prefs.getString(KEY_QR_PATH, "");
    }

    public String getSupportPhone() {
        return prefs.getString(KEY_SUPPORT_PHONE, "Suporte Técnico: (19) 99482-7743");
    }

    public String getDeviceId() {
        try {
            String androidId = Settings.Secure.getString(context.getContentResolver(), Settings.Secure.ANDROID_ID);
            if (androidId != null && !androidId.isEmpty()) return androidId;
        } catch (Exception ignored) {}
        return Build.SERIAL != null ? Build.SERIAL : "UNKNOWN_DEVICE";
    }

    public String getDeviceModel() {
        return Build.MANUFACTURER + " " + Build.MODEL;
    }

    public void saveConfiguration(String state, String client, String service, String value, String pix, String logoPath, String qrPath, String operationId) {
        SharedPreferences.Editor editor = prefs.edit();
        if (state != null && !state.isEmpty()) editor.putString(KEY_STATE, normalizeState(state));
        if (client != null && !client.isEmpty()) editor.putString(KEY_CLIENT, client);
        if (service != null && !service.isEmpty()) editor.putString(KEY_SERVICE, service);
        if (value != null && !value.isEmpty()) editor.putString(KEY_VALUE, value);
        if (pix != null && !pix.isEmpty()) editor.putString(KEY_PIX, pix);
        if (logoPath != null && !logoPath.isEmpty()) editor.putString(KEY_LOGO_PATH, logoPath);
        if (qrPath != null && !qrPath.isEmpty()) editor.putString(KEY_QR_PATH, qrPath);
        if (operationId != null && !operationId.isEmpty()) editor.putString(KEY_OPERATION_ID, operationId);
        editor.apply();
        exportStatusJson();
    }

    public File getAppFilesDir() {
        File dir = context.getExternalFilesDir(null);
        if (dir == null) dir = context.getFilesDir();
        return dir;
    }

    public void exportStatusJson() {
        try {
            String json = "{\n" +
                    "  \"status\": \"" + getState() + "\",\n" +
                    "  \"operationId\": \"" + escape(getOperationId()) + "\",\n" +
                    "  \"deviceId\": \"" + escape(getDeviceId()) + "\",\n" +
                    "  \"model\": \"" + escape(getDeviceModel()) + "\",\n" +
                    "  \"client\": \"" + escape(getClient()) + "\",\n" +
                    "  \"service\": \"" + escape(getService()) + "\",\n" +
                    "  \"value\": \"" + escape(getValue()) + "\",\n" +
                    "  \"package\": \"br.com.mdmfrpbrasil.deviceservice\",\n" +
                    "  \"timestamp\": " + System.currentTimeMillis() + "\n" +
                    "}";

            // 1. Primary write to app external files dir (SELinux compliant)
            File primaryFile = new File(getAppFilesDir(), "mdm_service_status.json");
            FileOutputStream fos1 = new FileOutputStream(primaryFile);
            fos1.write(json.getBytes(StandardCharsets.UTF_8));
            fos1.flush();
            fos1.close();
            primaryFile.setReadable(true, false);

            // 2. Best-effort write to /data/local/tmp
            try {
                File tmpFile = new File("/data/local/tmp/mdm_service_status.json");
                FileOutputStream fos2 = new FileOutputStream(tmpFile);
                fos2.write(json.getBytes(StandardCharsets.UTF_8));
                fos2.flush();
                fos2.close();
                tmpFile.setReadable(true, false);
            } catch (Exception ignored) {}
        } catch (Exception ignored) {}
    }

    public void exportReleaseAck() {
        try {
            String json = "{\n" +
                    "  \"status\": \"COMPLETED\",\n" +
                    "  \"ack\": \"RELEASE_ACK\",\n" +
                    "  \"operationId\": \"" + escape(getOperationId()) + "\",\n" +
                    "  \"deviceId\": \"" + escape(getDeviceId()) + "\",\n" +
                    "  \"client\": \"" + escape(getClient()) + "\",\n" +
                    "  \"service\": \"" + escape(getService()) + "\",\n" +
                    "  \"package\": \"br.com.mdmfrpbrasil.deviceservice\",\n" +
                    "  \"timestamp\": " + System.currentTimeMillis() + "\n" +
                    "}";

            File primaryFile = new File(getAppFilesDir(), "mdm_service_status.json");
            FileOutputStream fos1 = new FileOutputStream(primaryFile);
            fos1.write(json.getBytes(StandardCharsets.UTF_8));
            fos1.flush();
            fos1.close();
            primaryFile.setReadable(true, false);

            try {
                File tmpFile = new File("/data/local/tmp/mdm_service_status.json");
                FileOutputStream fos2 = new FileOutputStream(tmpFile);
                fos2.write(json.getBytes(StandardCharsets.UTF_8));
                fos2.flush();
                fos2.close();
                tmpFile.setReadable(true, false);
            } catch (Exception ignored) {}
        } catch (Exception ignored) {}
    }

    private String escape(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
