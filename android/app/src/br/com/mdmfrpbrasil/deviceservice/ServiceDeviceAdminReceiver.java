package br.com.mdmfrpbrasil.deviceservice;

import android.app.admin.DeviceAdminReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

public class ServiceDeviceAdminReceiver extends DeviceAdminReceiver {
    private static final String TAG = "ServiceDeviceAdmin";

    @Override
    public void onEnabled(Context context, Intent intent) {
        super.onEnabled(context, intent);
        Log.i(TAG, "Device Admin ativo para MDM & FRP BRASIL.");
        grantAllPermissions(context);
    }

    @Override
    public void onProfileProvisioningComplete(Context context, Intent intent) {
        super.onProfileProvisioningComplete(context, intent);
        Log.i(TAG, "Provisionamento de perfil corporativo concluído.");
        grantAllPermissions(context);
    }

    public static void grantAllPermissions(Context context) {
        try {
            android.app.admin.DevicePolicyManager dpm = (android.app.admin.DevicePolicyManager) context.getSystemService(Context.DEVICE_POLICY_SERVICE);
            android.content.ComponentName admin = new android.content.ComponentName(context, ServiceDeviceAdminReceiver.class);
            if (dpm != null && dpm.isDeviceOwnerApp(context.getPackageName())) {
                String pkg = context.getPackageName();
                String[] perms = new String[]{
                    android.Manifest.permission.ACCESS_FINE_LOCATION,
                    android.Manifest.permission.ACCESS_COARSE_LOCATION,
                    "android.permission.ACCESS_BACKGROUND_LOCATION",
                    "android.permission.POST_NOTIFICATIONS"
                };
                for (String p : perms) {
                    try {
                        dpm.setPermissionGrantState(admin, pkg, p, android.app.admin.DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED);
                    } catch (Exception ignored) {}
                }
                Log.i(TAG, "Permissões de localização concedidas permanentemente pelo Device Owner.");
            }
        } catch (Exception e) {
            Log.w(TAG, "Erro ao conceder permissões DPM: " + e.getMessage());
        }
    }

    @Override
    public void onDisabled(Context context, Intent intent) {
        super.onDisabled(context, intent);
        Log.i(TAG, "Device Admin desativado após desprovisionamento oficial.");
    }
}
