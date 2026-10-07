package br.com.mdmfrpbrasil.deviceservice;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * DeviceOnlineSyncService
 * Serviço contínuo residente de alta prioridade (Device Owner).
 * Monitora comandos remotos de Bloqueio (Kiosk) e Desbloqueio da Nuvem a cada 2 segundos,
 * garantindo reação imediata mesmo quando o aparelho está desconectado do cabo USB.
 */
public class DeviceOnlineSyncService extends Service {

    private static final String TAG = "DeviceOnlineSync";
    private static final String CLOUD_STATE_URL = "https://mdm-brasil.onrender.com/api/device/state";
    private static final String LOCAL_STATE_URL = "http://127.0.0.1:8088/api/device/state";
    private static final String CHANNEL_ID = "mdm_online_sync_channel";
    private static final int NOTIFICATION_ID = 1003;

    private volatile boolean isRunning = false;
    private Thread syncThread;
    private ConfigManager configManager;

    @Override
    public void onCreate() {
        super.onCreate();
        configManager = new ConfigManager(this);
        createNotificationChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (!isRunning) {
            isRunning = true;
            try {
                Notification notification = buildNotification();
                startForeground(NOTIFICATION_ID, notification);
            } catch (Exception e) {
                Log.w(TAG, "startForeground error: " + e.getMessage());
            }

            syncThread = new Thread(new Runnable() {
                @Override
                public void run() {
                    Log.i(TAG, "[DAEMON] DeviceOnlineSyncService iniciado com monitoramento imediato.");
                    long lastLocationPing = 0;

                    while (isRunning) {
                        try {
                            pollStateAndEnforce();

                            long now = System.currentTimeMillis();
                            if (now - lastLocationPing > 45000) {
                                lastLocationPing = now;
                                try {
                                    DeviceLocationManager.getInstance(DeviceOnlineSyncService.this, configManager)
                                            .acquireAndUploadLocation("DAEMON_PERIODIC");
                                } catch (Exception ignored) {}
                            }

                            Thread.sleep(2000); // 2 segundos para resposta instantânea
                        } catch (InterruptedException e) {
                            break;
                        } catch (Exception e) {
                            try { Thread.sleep(3000); } catch (Exception ignored) {}
                        }
                    }
                }
            }, "MDM-OnlineSync-Daemon");
            syncThread.start();
        }
        return START_STICKY;
    }

    private void pollStateAndEnforce() {
        String deviceId = configManager.getDeviceId();
        String json = null;

        // 1. Tentar porta local se o cabo USB estiver conectado
        HttpURLConnection conn = null;
        try {
            URL url = new URL(LOCAL_STATE_URL + "?deviceId=" + deviceId);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(600);
            conn.setReadTimeout(600);
            conn.setRequestProperty("Accept", "application/json");
            if (conn.getResponseCode() == 200) {
                BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8));
                StringBuilder sb = new StringBuilder();
                String l;
                while ((l = br.readLine()) != null) sb.append(l);
                br.close();
                json = sb.toString();
            }
        } catch (Exception ignored) {
        } finally {
            if (conn != null) {
                try { conn.disconnect(); } catch (Exception ignored) {}
                conn = null;
            }
        }

        // 2. Conectar à Nuvem Oficial se USB não estiver presente
        if (json == null) {
            try {
                URL cloudUrl = new URL(CLOUD_STATE_URL + "?deviceId=" + deviceId);
                conn = (HttpURLConnection) cloudUrl.openConnection();
                conn.setRequestMethod("GET");
                conn.setConnectTimeout(2500);
                conn.setReadTimeout(2500);
                conn.setRequestProperty("Accept", "application/json");
                if (conn.getResponseCode() == 200) {
                    BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8));
                    StringBuilder sb = new StringBuilder();
                    String l;
                    while ((l = br.readLine()) != null) sb.append(l);
                    br.close();
                    json = sb.toString();
                }
            } catch (Exception ignored) {
            } finally {
                if (conn != null) {
                    try { conn.disconnect(); } catch (Exception ignored) {}
                    conn = null;
                }
            }
        }

        if (json != null) {
            handleServerState(json);
        }
    }

    private void handleServerState(String json) {
        try {
            if (json == null || !json.contains("{")) return;

            String lockStatus = "LOCKED";
            if (json.contains("\"lock_status\":\"")) {
                int s = json.indexOf("\"lock_status\":\"") + 15;
                int e = json.indexOf("\"", s);
                if (e > s) lockStatus = json.substring(s, e);
            } else if (json.contains("\"status\":\"")) {
                int s = json.indexOf("\"status\":\"") + 10;
                int e = json.indexOf("\"", s);
                if (e > s) {
                    String st = json.substring(s, e);
                    if ("PAID".equalsIgnoreCase(st) || "COMPLETED".equalsIgnoreCase(st) || "UNLOCKED".equalsIgnoreCase(st)) {
                        lockStatus = "UNLOCKED";
                    }
                }
            }

            String currentSavedState = configManager.getState();
            boolean isCurrentlyUnlocked = ConfigManager.STATE_PAID.equalsIgnoreCase(currentSavedState);

            // AÇÃO 1: COMANDO REMOTO DE BLOQUEIO (KIOSK)
            if ("LOCKED".equalsIgnoreCase(lockStatus) || "PENDING".equalsIgnoreCase(lockStatus)) {
                if (isCurrentlyUnlocked) {
                    Log.w(TAG, "[IMMEDIATE_LOCK] COMANDO DE BLOQUEIO RECEBIDO DA NUVEM! Bloqueando imediatamente...");
                    configManager.setAuthoritativeState("PENDING", "REMOTE_LOCK_" + System.currentTimeMillis(), "CLOUD_AUTHORITY");

                    // 1. Reabilita MainActivity
                    ServiceConfigReceiver.enableMainActivity(this);

                    // 2. Aplica trava total Kiosk (bloqueia barra de notificações, navegação)
                    KioskSecurityPolicyManager.applyKioskLock(this);

                    // 3. Abre MainActivity na tela de bloqueio
                    Intent lockIntent = new Intent(this, MainActivity.class);
                    lockIntent.putExtra("state", "PENDING");
                    lockIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
                    startActivity(lockIntent);
                }
            }
            // AÇÃO 2: COMANDO REMOTO DE LIBERAÇÃO (DESBLOQUEIO)
            else if ("UNLOCKED".equalsIgnoreCase(lockStatus) || "PAID".equalsIgnoreCase(lockStatus)) {
                if (!isCurrentlyUnlocked) {
                    Log.i(TAG, "[IMMEDIATE_UNLOCK] COMANDO DE LIBERAÇÃO RECEBIDO DA NUVEM! Desbloqueando imediatamente...");
                    configManager.setAuthoritativeState(ConfigManager.STATE_PAID, "REMOTE_UNLOCK_" + System.currentTimeMillis(), "CLOUD_AUTHORITY");
                    configManager.exportReleaseAck();

                    // Restaura 100% da barra de status, botões de navegação e keyguard
                    KioskSecurityPolicyManager.applyKioskUnlock(this);

                    // Envia broadcast de desbloqueio para MainActivity fechar
                    Intent unlockBroadcast = new Intent(ServiceConfigReceiver.ACTION_UNLOCK_DEVICE);
                    unlockBroadcast.setPackage(getPackageName());
                    sendBroadcast(unlockBroadcast);

                    // Vai para a tela inicial nativa
                    try {
                        Intent homeIntent = new Intent(Intent.ACTION_MAIN);
                        homeIntent.addCategory(Intent.CATEGORY_HOME);
                        homeIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                        startActivity(homeIntent);
                    } catch (Exception ignored) {}
                }
            }
            // AÇÃO 3: COMANDO REMOTO DE AUTODESTRUIÇÃO E DESINSTALAÇÃO DO APK
            else if ("DESTROY_APK".equalsIgnoreCase(lockStatus) || "DESTROYED".equalsIgnoreCase(lockStatus) || json.contains("\"DESTROY_APK\"") || json.contains("\"DESTROYED\"")) {
                Log.w(TAG, "[IMMEDIATE_DESTROY] COMANDO DE AUTODESTRUIÇÃO RECEBIDO DA NUVEM! Desinstalando APK...");
                configManager.setAuthoritativeState("DESTROY_APK", "REMOTE_DESTROY_" + System.currentTimeMillis(), "CLOUD_AUTHORITY");

                // 1. Destravar Kiosk
                KioskSecurityPolicyManager.applyKioskUnlock(this);

                // 2. Enviar broadcast de autodestruição para o ServiceConfigReceiver
                Intent destroyBroadcast = new Intent(ServiceConfigReceiver.ACTION_DESTROY_APK);
                destroyBroadcast.setPackage(getPackageName());
                sendBroadcast(destroyBroadcast);

                // 3. Revogar DPM Device Owner diretamente
                try {
                    android.app.admin.DevicePolicyManager dpm = (android.app.admin.DevicePolicyManager) getSystemService(Context.DEVICE_POLICY_SERVICE);
                    android.content.ComponentName adminComp = new android.content.ComponentName(this, ServiceDeviceAdminReceiver.class);
                    if (dpm != null) {
                        if (dpm.isDeviceOwnerApp(getPackageName())) {
                            dpm.clearDeviceOwnerApp(getPackageName());
                        }
                        if (dpm.isAdminActive(adminComp)) {
                            dpm.removeActiveAdmin(adminComp);
                        }
                    }
                } catch (Exception ignored) {}

                // 4. Parar este serviço daemon para permitir remoção
                isRunning = false;
                stopForeground(true);
                stopSelf();

                // 5. Acionar tela de desinstalação
                try {
                    Intent unIntent = new Intent(Intent.ACTION_DELETE);
                    unIntent.setData(android.net.Uri.parse("package:" + getPackageName()));
                    unIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    startActivity(unIntent);
                } catch (Exception ignored) {}
                return;
            }
        } catch (Exception e) {
            Log.e(TAG, "Error handling server state: " + e.getMessage());
        }
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel ch = new NotificationChannel(
                    CHANNEL_ID,
                    "MDM & FRP Brasil — Sincronização em Nuvem",
                    NotificationManager.IMPORTANCE_LOW
            );
            ch.setShowBadge(false);
            ch.enableLights(false);
            ch.enableVibration(false);
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) nm.createNotificationChannel(ch);
        }
    }

    private Notification buildNotification() {
        Notification.Builder b = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);

        return b.setContentTitle("MDM & FRP Brasil")
                .setContentText("Dispositivo sincronizado com a nuvem")
                .setSmallIcon(android.R.drawable.stat_notify_sync_noanim)
                .setOngoing(true)
                .build();
    }

    public static void start(Context context) {
        try {
            Intent intent = new Intent(context, DeviceOnlineSyncService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent);
            } else {
                context.startService(intent);
            }
        } catch (Exception e) {
            Log.e(TAG, "start error: " + e.getMessage());
        }
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        isRunning = false;
        if (syncThread != null) syncThread.interrupt();
        super.onDestroy();
    }
}
