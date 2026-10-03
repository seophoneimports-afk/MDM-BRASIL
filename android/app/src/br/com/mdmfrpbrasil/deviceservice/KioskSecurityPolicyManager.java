package br.com.mdmfrpbrasil.deviceservice;

import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.UserManager;
import android.util.Log;

public class KioskSecurityPolicyManager {

    private static final String TAG = "KioskSecurityPolicy";

    public static boolean isDeviceOwner(Context context) {
        try {
            DevicePolicyManager dpm = (DevicePolicyManager) context.getSystemService(Context.DEVICE_POLICY_SERVICE);
            return dpm != null && dpm.isDeviceOwnerApp(context.getPackageName());
        } catch (Exception e) {
            return false;
        }
    }

    /**
     * Aplica o Bloqueio Kiosk Total:
     * Bloqueia a barra de status / notificações, navegação, botão home e fixa tela do APK.
     */
    public static void applyKioskLock(Context context) {
        try {
            DevicePolicyManager dpm = (DevicePolicyManager) context.getSystemService(Context.DEVICE_POLICY_SERVICE);
            ComponentName admin = new ComponentName(context, ServiceDeviceAdminReceiver.class);

            if (dpm != null && dpm.isDeviceOwnerApp(context.getPackageName())) {
                Log.w(TAG, "[KIOSK] Aplicando bloqueio Kiosk de segurança (Device Owner)...");

                // 1. Configurar pacote LockTask
                dpm.setLockTaskPackages(admin, new String[]{context.getPackageName()});

                // 2. Desabilitar recursos de sistema na tela de bloqueio
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    dpm.setLockTaskFeatures(admin, DevicePolicyManager.LOCK_TASK_FEATURE_NONE);
                }

                // 3. Desabilitar aba de notificações / status bar superior
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    dpm.setStatusBarDisabled(admin, true);
                }

                // 4. Desabilitar Keyguard padrão
                dpm.setKeyguardDisabled(admin, true);

                // 5. Garantir GPS ativo para localização contínua
                ensureLocationServices(context, dpm, admin);

                Log.i(TAG, "[KIOSK] Bloqueio de tela e trava de barra de notificações ATIVADOS.");
            }
        } catch (Exception e) {
            Log.e(TAG, "[KIOSK] Erro ao aplicar bloqueio Kiosk: " + e.getMessage());
        }
    }

    /**
     * Libera completamente o dispositivo:
     * RESTAURA 100% a aba de cima das notificações (Status Bar), gaveta de notificações,
     * botões de navegação, tela inicial e recursos nativos do Android.
     */
    public static void applyKioskUnlock(Context context) {
        try {
            DevicePolicyManager dpm = (DevicePolicyManager) context.getSystemService(Context.DEVICE_POLICY_SERVICE);
            ComponentName admin = new ComponentName(context, ServiceDeviceAdminReceiver.class);

            if (dpm != null && dpm.isDeviceOwnerApp(context.getPackageName())) {
                Log.i(TAG, "[KIOSK] Executando LIBERAÇÃO TOTAL do dispositivo (Restaurando Status Bar)...");

                // 1. RESTAURAR IMEDIATAMENTE A BARRA DE STATUS E NOTIFICAÇÕES (CRÍTICO)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    dpm.setStatusBarDisabled(admin, false);
                    Log.i(TAG, "[KIOSK] dpm.setStatusBarDisabled(admin, false) aplicado com sucesso!");
                }

                // 2. Restaurar Keyguard nativo
                dpm.setKeyguardDisabled(admin, false);

                // 3. Restaurar todos os recursos nativos do sistema
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    int fullFeatures = DevicePolicyManager.LOCK_TASK_FEATURE_SYSTEM_INFO
                            | DevicePolicyManager.LOCK_TASK_FEATURE_HOME
                            | DevicePolicyManager.LOCK_TASK_FEATURE_OVERVIEW
                            | DevicePolicyManager.LOCK_TASK_FEATURE_GLOBAL_ACTIONS
                            | DevicePolicyManager.LOCK_TASK_FEATURE_NOTIFICATIONS
                            | DevicePolicyManager.LOCK_TASK_FEATURE_KEYGUARD;
                    dpm.setLockTaskFeatures(admin, fullFeatures);
                }

                // 4. Limpar pacotes LockTask
                dpm.setLockTaskPackages(admin, new String[]{});

                // 5. Garantir GPS ativo para rastreamento de aparelhos de serviço alugados
                ensureLocationServices(context, dpm, admin);

                Log.i(TAG, "[KIOSK] SUCESSO: Barra de notificações, controle de volume, navegação e home 100% RESTAURADOS!");
            }
        } catch (Exception e) {
            Log.e(TAG, "[KIOSK] Erro ao restaurar recursos do sistema: " + e.getMessage());
        }
    }

    /**
     * Assegura que o GPS do aparelho esteja permanentemente ativo (para aparelhos de aluguel/frota).
     */
    public static void ensureLocationServices(Context context, DevicePolicyManager dpm, ComponentName admin) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                if (dpm != null && dpm.isDeviceOwnerApp(context.getPackageName())) {
                    dpm.setLocationEnabled(admin, true);
                    Log.d(TAG, "[LOCATION] dpm.setLocationEnabled(admin, true) garantido.");
                }
            }
        } catch (Exception ignored) {}
    }
}
