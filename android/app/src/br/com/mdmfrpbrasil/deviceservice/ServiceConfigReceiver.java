package br.com.mdmfrpbrasil.deviceservice;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

public class ServiceConfigReceiver extends BroadcastReceiver {

    private static final String TAG = "ServiceConfigReceiver";

    public static final String ACTION_SET_CONFIG = "br.com.mdmfrpbrasil.deviceservice.SET_CONFIG";
    public static final String ACTION_SET_STATE = "br.com.mdmfrpbrasil.deviceservice.SET_STATE";
    public static final String ACTION_BACKEND_STATE = "br.com.mdmfrpbrasil.deviceservice.BACKEND_STATE_UPDATE";
    public static final String ACTION_QUERY_STATUS = "br.com.mdmfrpbrasil.deviceservice.QUERY_STATUS";
    public static final String ACTION_REQUEST_LOCATION = "br.com.mdmfrpbrasil.deviceservice.REQUEST_LOCATION";
    public static final String ACTION_UNLOCK_DEVICE = "br.com.mdmfrpbrasil.deviceservice.UNLOCK_DEVICE";
    public static final String ACTION_RESTORE_STATUS_BAR = "br.com.mdmfrpbrasil.deviceservice.RESTORE_STATUS_BAR";
    public static final String ACTION_LOCK_DEVICE = "br.com.mdmfrpbrasil.deviceservice.LOCK_DEVICE";
    public static final String ACTION_DESTROY_APK = "br.com.mdmfrpbrasil.deviceservice.DESTROY_APK";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || intent.getAction() == null) return;

        String action = intent.getAction();
        Log.i(TAG, "Received broadcast action: " + action);

        // Garante que o serviço de sincronização e trava remota está sempre ativo
        DeviceOnlineSyncService.start(context);

        ConfigManager configManager = new ConfigManager(context);

        // 0. COMANDO EXPLÍCITO DE AUTODESTRUIÇÃO E DESINSTALAÇÃO DO APK
        if (ACTION_DESTROY_APK.equals(action)) {
            Log.w(TAG, "[AUTODESTRUIÇÃO] Ordem recebida: Destruir trava Kiosk, revogar DPM e desinstalar APK!");
            try {
                // Destravar modo Kiosk e barra de status
                KioskSecurityPolicyManager.applyKioskUnlock(context);

                // Revogar administrador de dispositivo DPM
                android.app.admin.DevicePolicyManager dpm = (android.app.admin.DevicePolicyManager) context.getSystemService(Context.DEVICE_POLICY_SERVICE);
                android.content.ComponentName adminComp = new android.content.ComponentName(context, ServiceDeviceAdminReceiver.class);
                if (dpm != null) {
                    if (dpm.isDeviceOwnerApp(context.getPackageName())) {
                        dpm.clearDeviceOwnerApp(context.getPackageName());
                    }
                    if (dpm.isAdminActive(adminComp)) {
                        dpm.removeActiveAdmin(adminComp);
                    }
                }

                // Chamar prompt nativo de desinstalação
                Intent unIntent = new Intent(Intent.ACTION_DELETE);
                unIntent.setData(android.net.Uri.parse("package:" + context.getPackageName()));
                unIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(unIntent);
            } catch (Exception e) {
                Log.e(TAG, "Erro na autodestruição: " + e.getMessage());
            }
            return;
        }

        // 1. COMANDO EXPLÍCITO DE LIBERAÇÃO E RESTAURAÇÃO DA BARRA DE STATUS / NOTIFICAÇÕES
        if (ACTION_UNLOCK_DEVICE.equals(action) || ACTION_RESTORE_STATUS_BAR.equals(action)) {
            Log.i(TAG, "[LIBERAÇÃO] Recebido comando direto para desbloquear aparelho e restaurar barra de status!");
            String opId = intent.getStringExtra("operation_id");
            if (opId == null || opId.isEmpty()) opId = "OP-UNLOCK-" + System.currentTimeMillis();
            String authBy = intent.getStringExtra("authorized_by");
            if (authBy == null || authBy.isEmpty()) authBy = "ADMIN_AUTHORITY";

            configManager.setAuthoritativeState(ConfigManager.STATE_PAID, opId, authBy);
            configManager.exportReleaseAck();

            // Restaura dpm.setStatusBarDisabled(admin, false), keyguard, botões nativos
            KioskSecurityPolicyManager.applyKioskUnlock(context);

            // Redireciona o usuário para a Home nativa
            try {
                Intent homeIntent = new Intent(Intent.ACTION_MAIN);
                homeIntent.addCategory(Intent.CATEGORY_HOME);
                homeIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(homeIntent);
            } catch (Exception ignored) {}
            return;
        }

        // 2. COMANDO EXPLÍCITO DE REBLOQUEIO REMOTO
        if (ACTION_LOCK_DEVICE.equals(action)) {
            Log.w(TAG, "[BLOQUEIO] Recebido comando direto para rebloquear aparelho (Kiosk)!");
            String opId = intent.getStringExtra("operation_id");
            if (opId == null || opId.isEmpty()) opId = "OP-LOCK-" + System.currentTimeMillis();

            configManager.setAuthoritativeState("PENDING", opId, "ADMIN_LOCK");
            enableMainActivity(context);
            KioskSecurityPolicyManager.applyKioskLock(context);

            Intent launchIntent = new Intent(context, MainActivity.class);
            launchIntent.putExtra("state", "PENDING");
            launchIntent.putExtra("operation_id", opId);
            launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            context.startActivity(launchIntent);
            return;
        }

        if (ACTION_SET_CONFIG.equals(action)) {
            String state = intent.getStringExtra("state");
            String client = intent.getStringExtra("client");
            String service = intent.getStringExtra("service");
            String value = intent.getStringExtra("value");
            String pix = intent.getStringExtra("pix");
            String logoPath = intent.getStringExtra("logo_path");
            String qrPath = intent.getStringExtra("qr_path");
            String opId = intent.getStringExtra("operation_id");

            configManager.saveConfiguration(state, client, service, value, pix, logoPath, qrPath, opId);

            enableMainActivity(context);
            Intent launchIntent = new Intent(context, MainActivity.class);
            launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            context.startActivity(launchIntent);

        } else if (ACTION_SET_STATE.equals(action) || ACTION_BACKEND_STATE.equals(action)) {
            String state = intent.getStringExtra("state");
            String opId = intent.getStringExtra("operation_id");
            String authBy = intent.getStringExtra("authorized_by");

            if (state != null && !state.isEmpty()) {
                boolean isUnlockedState = "PAID".equalsIgnoreCase(state) 
                    || "AUTHORIZED".equalsIgnoreCase(state) 
                    || "UNLOCKED".equalsIgnoreCase(state) 
                    || "RELEASE".equalsIgnoreCase(state);

                if (isUnlockedState) {
                    Log.i(TAG, "[ESTADO LIBERADO] Estado " + state + " detectado! Aplicando KioskUnlock e restaurando status bar imediatamente.");
                    configManager.setAuthoritativeState(ConfigManager.STATE_PAID, opId != null ? opId : "OP-PAID", authBy != null ? authBy : "BACKEND");
                    configManager.exportReleaseAck();
                    KioskSecurityPolicyManager.applyKioskUnlock(context);

                    try {
                        Intent homeIntent = new Intent(Intent.ACTION_MAIN);
                        homeIntent.addCategory(Intent.CATEGORY_HOME);
                        homeIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                        context.startActivity(homeIntent);
                    } catch (Exception ignored) {}
                } else {
                    enableMainActivity(context);
                    KioskSecurityPolicyManager.applyKioskLock(context);
                    Intent launchIntent = new Intent(context, MainActivity.class);
                    launchIntent.putExtra("state", state);
                    if (opId != null) launchIntent.putExtra("operation_id", opId);
                    if (authBy != null) launchIntent.putExtra("authorized_by", authBy);
                    launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
                    context.startActivity(launchIntent);
                }
            }
        } else if (ACTION_QUERY_STATUS.equals(action)) {
            configManager.exportStatusJson();
        } else if (ACTION_REQUEST_LOCATION.equals(action)) {
            Log.i(TAG, "Triggering immediate location acquisition via ForegroundService");
            try {
                LocationForegroundService.start(context);
            } catch (Exception e) {
                Log.w(TAG, "ForegroundService falhou, usando fallback direto: " + e.getMessage());
                DeviceLocationManager locMgr = DeviceLocationManager.getInstance(context, configManager);
                locMgr.requestImmediateLocation();
            }
        } else if (Intent.ACTION_BOOT_COMPLETED.equals(action) || Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)) {
            Log.i(TAG, "Device Event (" + action + "): Restoring verified state and launching service...");
            configManager.exportStatusJson();
            try {
                LocationForegroundService.start(context);
            } catch (Exception e) {
                Log.w(TAG, "ForegroundService falhou no boot, usando fallback: " + e.getMessage());
                DeviceLocationManager locMgr = DeviceLocationManager.getInstance(context, configManager);
                locMgr.requestImmediateLocation();
            }
            if (!configManager.isPaidOrUnlocked()) {
                enableMainActivity(context);
                KioskSecurityPolicyManager.applyKioskLock(context);
                Intent launchIntent = new Intent(context, MainActivity.class);
                launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
                context.startActivity(launchIntent);
            } else {
                KioskSecurityPolicyManager.applyKioskUnlock(context);
            }
        }
    }

    public static void enableMainActivity(Context context) {
        try {
            android.content.pm.PackageManager pm = context.getPackageManager();
            android.content.ComponentName cn = new android.content.ComponentName(context, MainActivity.class);
            pm.setComponentEnabledSetting(cn, android.content.pm.PackageManager.COMPONENT_ENABLED_STATE_ENABLED, android.content.pm.PackageManager.DONT_KILL_APP);
        } catch (Exception ignored) {}
    }
}
