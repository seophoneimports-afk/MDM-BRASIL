package br.com.mdmfrpbrasil.deviceservice;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public class BackendSyncManager {

    private static final String TAG = "BackendSyncManager";

    // Primary endpoint: forwarded by ADB reverse to the Windows controller
    private static final String DEFAULT_BACKEND_URL = "http://127.0.0.1:8088/api/device/state";
    private static final String DEFAULT_COMPLETE_URL = "http://127.0.0.1:8088/api/device/complete";

    // Official Cloud Authority endpoint: online sync via Wi-Fi/4G without USB
    private static final String CLOUD_BACKEND_URL = "https://mdm-brasil.onrender.com/api/device/state";
    private static final String CLOUD_COMPLETE_URL = "https://mdm-brasil.onrender.com/api/device/complete";

    public interface StateChangeListener {
        void onStateChanged(String newState, String operationId, String authorizedBy);
        void onConnectivityChanged(boolean isOnline, String message);
    }

    private final Context context;
    private final ConfigManager configManager;
    private final Handler mainHandler;
    private StateChangeListener listener;
    private volatile boolean isRunning = false;
    private Thread syncThread;

    public BackendSyncManager(Context context, ConfigManager configManager) {
        this.context = context.getApplicationContext();
        this.configManager = configManager;
        this.mainHandler = new Handler(Looper.getMainLooper());
    }

    public void setListener(StateChangeListener listener) {
        this.listener = listener;
    }

    public synchronized void startSync() {
        if (isRunning) return;
        isRunning = true;

        syncThread = new Thread(new Runnable() {
            @Override
            public void run() {
                while (isRunning) {
                    performSyncCycle();
                    try {
                        Thread.sleep(2500); // 2.5s sync cycle
                    } catch (InterruptedException e) {
                        break;
                    }
                }
            }
        }, "MDM-Backend-Sync");
        syncThread.start();
    }

    public synchronized void stopSync() {
        isRunning = false;
        if (syncThread != null) {
            syncThread.interrupt();
            syncThread = null;
        }
    }

    private void performSyncCycle() {
        String deviceId = configManager.getDeviceId();
        String jsonResult = null;
        boolean fromCloud = false;

        // 1. Tentar primeiro o controlador local via USB (porta 8088 reversa) com timeout rápido
        HttpURLConnection conn = null;
        try {
            URL url = new URL(DEFAULT_BACKEND_URL + "?deviceId=" + deviceId);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(1200);
            conn.setReadTimeout(1200);
            conn.setRequestProperty("Accept", "application/json");

            int code = conn.getResponseCode();
            if (code == 200) {
                BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8));
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) {
                    sb.append(line);
                }
                reader.close();
                jsonResult = sb.toString();
            }
        } catch (Exception ignored) {
            // Local offline (cabo USB desconectado)
        } finally {
            if (conn != null) {
                try { conn.disconnect(); } catch (Exception ignored) {}
                conn = null;
            }
        }

        // 2. Se local não respondeu (dispositivo sem USB), conectar à Nuvem Oficial via Wi-Fi/4G
        if (jsonResult == null) {
            try {
                URL cloudUrl = new URL(CLOUD_BACKEND_URL + "?deviceId=" + deviceId);
                conn = (HttpURLConnection) cloudUrl.openConnection();
                conn.setRequestMethod("GET");
                conn.setConnectTimeout(3500);
                conn.setReadTimeout(3500);
                conn.setRequestProperty("Accept", "application/json");

                int code = conn.getResponseCode();
                if (code == 200) {
                    BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8));
                    StringBuilder sb = new StringBuilder();
                    String line;
                    while ((line = reader.readLine()) != null) {
                        sb.append(line);
                    }
                    reader.close();
                    jsonResult = sb.toString();
                    fromCloud = true;
                } else {
                    notifyConnectivity(false, "Nuvem retornou HTTP " + code);
                }
            } catch (Exception e) {
                notifyConnectivity(false, "Sincronização Cloud em espera (Modo Seguro Ativo)");
            } finally {
                if (conn != null) {
                    try { conn.disconnect(); } catch (Exception ignored) {}
                    conn = null;
                }
            }
        }

        if (jsonResult != null) {
            parseAndApplyBackendResponse(jsonResult, true);
        }
    }

    public void reportCompletedToBackend(final String operationId) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                String payload = "{\"deviceId\":\"" + configManager.getDeviceId() + "\"," +
                        "\"operationId\":\"" + operationId + "\"," +
                        "\"status\":\"COMPLETED\"," +
                        "\"timestamp\":" + System.currentTimeMillis() + "}";

                // Reportar tanto localmente quanto na nuvem
                String[] endpoints = new String[]{DEFAULT_COMPLETE_URL, CLOUD_COMPLETE_URL};
                for (String endpoint : endpoints) {
                    HttpURLConnection conn = null;
                    try {
                        URL url = new URL(endpoint);
                        conn = (HttpURLConnection) url.openConnection();
                        conn.setRequestMethod("POST");
                        conn.setDoOutput(true);
                        conn.setConnectTimeout(3000);
                        conn.setReadTimeout(3000);
                        conn.setRequestProperty("Content-Type", "application/json");

                        OutputStream os = conn.getOutputStream();
                        os.write(payload.getBytes(StandardCharsets.UTF_8));
                        os.flush();
                        os.close();

                        int resCode = conn.getResponseCode();
                        Log.i(TAG, "Completed report to " + endpoint + " result: " + resCode);
                    } catch (Exception ignored) {
                    } finally {
                        if (conn != null) conn.disconnect();
                    }
                }
            }
        }).start();
    }

    public void parseAndApplyBackendResponse(String jsonStr, boolean fromHttp) {
        try {
            if (jsonStr == null || !jsonStr.trim().startsWith("{")) return;

            // Simple lightweight JSON parse without external dependency
            String remoteStatus = extractJsonField(jsonStr, "status");
            String operationId = extractJsonField(jsonStr, "operationId");
            String authorizedBy = extractJsonField(jsonStr, "authorizedBy");

            if (remoteStatus != null && !remoteStatus.isEmpty()) {
                String normalized = configManager.normalizeState(remoteStatus);
                String current = configManager.getState();

                if (!normalized.equals(current)) {
                    Log.i(TAG, "Backend authoritative state change: " + current + " -> " + normalized);
                    configManager.setAuthoritativeState(normalized, operationId, authorizedBy);

                    notifyStateChange(normalized, operationId, authorizedBy);
                }
            }

            if (fromHttp) {
                notifyConnectivity(true, "🟢 CONECTADO AO SERVIDOR • AUTORIDADE BACKEND ATIVA");
            }
        } catch (Exception e) {
            Log.e(TAG, "Error applying backend response: " + e.getMessage());
        }
    }

    private void notifyStateChange(final String newState, final String opId, final String authBy) {
        if (listener == null) return;
        mainHandler.post(new Runnable() {
            @Override
            public void run() {
                if (listener != null) {
                    listener.onStateChanged(newState, opId, authBy);
                }
            }
        });
    }

    private void notifyConnectivity(final boolean online, final String message) {
        if (listener == null) return;
        mainHandler.post(new Runnable() {
            @Override
            public void run() {
                if (listener != null) {
                    listener.onConnectivityChanged(online, message);
                }
            }
        });
    }

    private String extractJsonField(String json, String field) {
        String pattern = "\"" + field + "\"";
        int idx = json.indexOf(pattern);
        if (idx == -1) return null;
        int colon = json.indexOf(":", idx + pattern.length());
        if (colon == -1) return null;
        int startQuote = json.indexOf("\"", colon + 1);
        if (startQuote == -1) return null;
        int endQuote = json.indexOf("\"", startQuote + 1);
        if (endQuote == -1) return null;
        return json.substring(startQuote + 1, endQuote);
    }
}
