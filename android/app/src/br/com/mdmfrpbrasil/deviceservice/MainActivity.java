package br.com.mdmfrpbrasil.deviceservice;

import android.Manifest;
import android.app.Activity;
import android.app.admin.DevicePolicyManager;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.io.File;

public class MainActivity extends Activity implements BackendSyncManager.StateChangeListener {

    private static final String TAG = "MainActivity";

    private ConfigManager configManager;
    private BackendSyncManager syncManager;
    private DeviceLocationManager locationManager;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    // Header views
    private ImageView imgLogo;
    private TextView tvAppName;
    private TextView tvAppSubtitle;
    private LinearLayout layoutStatusBadge;
    private TextView tvStatusBadge;
    private TextView tvStatusSub;

    // Content views
    private LinearLayout cardPending;
    private TextView tvDeviceModel;
    private TextView tvDeviceSub;
    private TextView tvDeviceId;
    private TextView tvClientService;
    private TextView tvPendingValue;
    private ImageView imgQrCode;
    private TextView tvPixCode;
    private TextView tvBackendNotice;

    private LinearLayout cardProcessing;

    private LinearLayout cardCompleted;
    private TextView tvCompletedDetails;
    private TextView tvCompletedOpId;

    // Footer views
    private TextView tvSupport;
    private TextView tvConnectivity;
    private TextView tvOperationId;

    private boolean isExecutingDeprovisioning = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        configManager = new ConfigManager(this);
        DeviceOnlineSyncService.start(this);

        // If payment is already confirmed / device unlocked, do NOT enter lock mode
        if (configManager.isPaidOrUnlocked()) {
            Log.i(TAG, "Device is in PAID / UNLOCKED state. Suppressing lock screen.");
            locationManager = DeviceLocationManager.getInstance(this, configManager);
            locationManager.startPeriodicTracking();
            finishAndRemoveTask();
            return;
        }

        syncManager = new BackendSyncManager(this, configManager);
        syncManager.setListener(this);

        initViews();
        processIntentExtras(getIntent());
        renderUi();

        applyImmersiveMode();
        applyDevicePolicyRestrictions();
        checkAndGrantLocationPermissions();

        // Start real-time sync with Windows Backend
        syncManager.startSync();

        // Start official Device Location Tracking
        locationManager = DeviceLocationManager.getInstance(this, configManager);
        locationManager.startPeriodicTracking();

        registerUnlockReceiver();
    }

    private BroadcastReceiver unlockReceiver;

    private void registerUnlockReceiver() {
        unlockReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                Log.i(TAG, "MainActivity received unlock broadcast! Dismissing lock screen immediately...");
                mainHandler.post(new Runnable() {
                    @Override
                    public void run() {
                        try {
                            Intent homeIntent = new Intent(Intent.ACTION_MAIN);
                            homeIntent.addCategory(Intent.CATEGORY_HOME);
                            homeIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                            startActivity(homeIntent);
                        } catch (Exception ignored) {}
                        finishAndRemoveTask();
                    }
                });
            }
        };
        IntentFilter filter = new IntentFilter();
        filter.addAction(ServiceConfigReceiver.ACTION_UNLOCK_DEVICE);
        filter.addAction(ServiceConfigReceiver.ACTION_RESTORE_STATUS_BAR);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(unlockReceiver, filter, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(unlockReceiver, filter);
        }
    }

    private void checkAndGrantLocationPermissions() {
        try {
            DevicePolicyManager dpm = (DevicePolicyManager) getSystemService(Context.DEVICE_POLICY_SERVICE);
            ComponentName admin = new ComponentName(this, ServiceDeviceAdminReceiver.class);

            if (dpm != null && dpm.isDeviceOwnerApp(getPackageName())) {
                dpm.setPermissionGrantState(admin, getPackageName(), Manifest.permission.ACCESS_FINE_LOCATION, DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED);
                dpm.setPermissionGrantState(admin, getPackageName(), Manifest.permission.ACCESS_COARSE_LOCATION, DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED);
                Log.i(TAG, "[LOG] LOCATION_PERMISSION_GRANTED via DevicePolicyManager");
            }
        } catch (Exception e) {
            Log.w(TAG, "DPM permission grant note: " + e.getMessage());
        }

        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION
            }, 101);
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == 101) {
            boolean granted = grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED;
            if (granted) {
                Log.i(TAG, "[LOG] LOCATION_PERMISSION_GRANTED pelo usuário");
                if (locationManager != null) {
                    locationManager.acquireAndUploadLocation("PERMISSION_CALLBACK");
                }
            } else {
                Log.w(TAG, "[LOG] LOCATION_PERMISSION_DENIED pelo usuário");
            }
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        processIntentExtras(intent);
        if (configManager != null && configManager.isPaidOrUnlocked()) {
            finishAndRemoveTask();
            return;
        }
        renderUi();
        applyImmersiveMode();
        applyDevicePolicyRestrictions();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (configManager != null && configManager.isPaidOrUnlocked()) {
            finishAndRemoveTask();
            return;
        }
        renderUi();
        applyImmersiveMode();
        applyDevicePolicyRestrictions();
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            if (configManager != null && configManager.isPaidOrUnlocked()) {
                finishAndRemoveTask();
                return;
            }
            applyImmersiveMode();
            applyDevicePolicyRestrictions();
        }
    }

    @Override
    public void onBackPressed() {
        String state = configManager.getState();
        if (!configManager.isPaidOrUnlocked()) {
            Log.i(TAG, "Back button consumed in managed state: " + state);
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (unlockReceiver != null) {
            try {
                unregisterReceiver(unlockReceiver);
            } catch (Exception ignored) {}
            unlockReceiver = null;
        }
        if (syncManager != null) {
            syncManager.stopSync();
        }
        if (locationManager != null) {
            locationManager.stopPeriodicTracking();
        }
    }

    private void initViews() {
        imgLogo = findViewById(R.id.imgLogo);
        tvAppSubtitle = findViewById(R.id.tvAppSubtitle);
        layoutStatusBadge = findViewById(R.id.layoutStatusBadge);
        tvStatusBadge = findViewById(R.id.tvStatusBadge);
        tvStatusSub = findViewById(R.id.tvStatusSub);

        cardPending = findViewById(R.id.cardPending);
        tvDeviceModel = findViewById(R.id.tvDeviceModel);
        tvDeviceSub = findViewById(R.id.tvDeviceSub);
        tvDeviceId = findViewById(R.id.tvDeviceId);
        tvClientService = findViewById(R.id.tvClientService);
        tvPendingValue = findViewById(R.id.tvPendingValue);
        imgQrCode = findViewById(R.id.imgQrCode);
        tvPixCode = findViewById(R.id.tvPixCode);
        tvBackendNotice = findViewById(R.id.tvBackendNotice);

        tvSupport = findViewById(R.id.tvSupport);
        tvConnectivity = findViewById(R.id.tvConnectivity);
        tvOperationId = findViewById(R.id.tvOperationId);
    }

    private void applyImmersiveMode() {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                WindowInsetsController controller = getWindow().getInsetsController();
                if (controller != null) {
                    controller.hide(WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars());
                    controller.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
                }
            } else {
                getWindow().getDecorView().setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    | View.SYSTEM_UI_FLAG_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                );
            }
        } catch (Exception ignored) {}
    }

    private void applyDevicePolicyRestrictions() {
        try {
            DevicePolicyManager dpm = (DevicePolicyManager) getSystemService(Context.DEVICE_POLICY_SERVICE);
            ComponentName admin = new ComponentName(this, ServiceDeviceAdminReceiver.class);

            if (dpm != null && dpm.isDeviceOwnerApp(getPackageName())) {
                boolean isLocked = !configManager.isPaidOrUnlocked();

                if (isLocked) {
                    KioskSecurityPolicyManager.applyKioskLock(this);
                    try {
                        startLockTask();
                    } catch (Exception e) {
                        Log.w(TAG, "startLockTask: " + e.getMessage());
                    }
                } else {
                    try {
                        stopLockTask();
                    } catch (Exception ignored) {}
                    KioskSecurityPolicyManager.applyKioskUnlock(this);
                }
            }
        } catch (Exception e) {
            Log.e(TAG, "Error applying DPM policies: " + e.getMessage());
        }
    }

    private void processIntentExtras(Intent intent) {
        if (intent == null) return;

        String state = intent.getStringExtra("state");
        String opId = intent.getStringExtra("operation_id");
        String authBy = intent.getStringExtra("authorized_by");

        if ("RELEASE".equalsIgnoreCase(state) || ConfigManager.STATE_AUTHORIZED.equalsIgnoreCase(state) || ConfigManager.STATE_PAID.equalsIgnoreCase(state) || "PAID".equalsIgnoreCase(state)) {
            triggerDeprovisioningProcedure(opId != null ? opId : configManager.getOperationId(), authBy);
            return;
        }

        String client = intent.getStringExtra("client");
        String service = intent.getStringExtra("service");
        String value = intent.getStringExtra("value");
        String pix = intent.getStringExtra("pix");
        String logoPath = intent.getStringExtra("logo_path");
        String qrPath = intent.getStringExtra("qr_path");

        if (state != null || client != null || service != null || value != null || pix != null || logoPath != null || qrPath != null || opId != null) {
            configManager.saveConfiguration(state, client, service, value, pix, logoPath, qrPath, opId);
        }
    }

    @Override
    public void onStateChanged(String newState, String operationId, String authorizedBy) {
        Log.i(TAG, "onStateChanged received from backend authority: " + newState);
        if (ConfigManager.STATE_AUTHORIZED.equalsIgnoreCase(newState) || ConfigManager.STATE_PAID.equalsIgnoreCase(newState) || "PAID".equalsIgnoreCase(newState)) {
            triggerDeprovisioningProcedure(operationId, authorizedBy);
        } else {
            renderUi();
        }
    }

    @Override
    public void onConnectivityChanged(boolean isOnline, String message) {
        if (tvConnectivity != null) {
            tvConnectivity.setText(isOnline ? "🟢 ONLINE" : "🔴 OFFLINE");
            tvConnectivity.setTextColor(isOnline ? 0xFF00E676 : 0xFFEF4444);
        }
    }

    public synchronized void triggerDeprovisioningProcedure(final String opId, final String authBy) {
        if (isExecutingDeprovisioning) return;
        isExecutingDeprovisioning = true;

        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    // 1. Encerrar Lock Task (Modo Kiosk)
                    mainHandler.post(new Runnable() {
                        @Override
                        public void run() {
                            try {
                                stopLockTask();
                            } catch (Exception ignored) {}
                        }
                    });

                    // 2. Restaurar controles nativos do Android via DevicePolicyManager SEM remover o Device Owner
                    KioskSecurityPolicyManager.applyKioskUnlock(MainActivity.this);

                    // 3. Salvar estado oficial como PAID (persistido permanentemente)
                    configManager.setAuthoritativeState(ConfigManager.STATE_PAID, opId, authBy);
                    configManager.exportReleaseAck();

                    // 4. Reportar confirmação de pagamento ao Backend
                    syncManager.reportCompletedToBackend(opId);

                    // 5. Retornar usuário diretamente à tela inicial do Android
                    mainHandler.post(new Runnable() {
                        @Override
                        public void run() {
                            try {
                                Intent homeIntent = new Intent(Intent.ACTION_MAIN);
                                homeIntent.addCategory(Intent.CATEGORY_HOME);
                                homeIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                                startActivity(homeIntent);
                            } catch (Exception ignored) {}
                            finishAndRemoveTask();
                        }
                    });

                } catch (Exception e) {
                    Log.e(TAG, "Erro no fluxo de liberação do pagamento: " + e.getMessage());
                } finally {
                    isExecutingDeprovisioning = false;
                }
            }
        }, "Payment-Release-Worker").start();
    }

    private void renderUi() {
        if (configManager != null && configManager.isPaidOrUnlocked()) {
            finishAndRemoveTask();
            return;
        }

        String state = configManager.getState();
        String opId = configManager.getOperationId();
        String client = configManager.getClient();
        String service = configManager.getService();
        String value = configManager.getValue();
        String pix = configManager.getPix();
        String logoPath = configManager.getLogoPath();
        String qrPath = configManager.getQrPath();

        // 1. Carregar Logo
        loadLogo(logoPath);

        // 2. Telemetria e Hardware
        String model = configManager.getDeviceModel().toUpperCase();
        if (tvDeviceModel != null) tvDeviceModel.setText(model);
        if (tvDeviceSub != null) tvDeviceSub.setText("Galaxy S21 FE 5G");
        if (tvDeviceId != null) tvDeviceId.setText(configManager.getDeviceId());
        if (tvClientService != null) tvClientService.setText(client.isEmpty() ? "Atendimento Técnico Autorizado" : client);

        if (tvOperationId != null) tvOperationId.setText("#" + opId);
        if (tvSupport != null) tvSupport.setText("(19) 99482-7743");

        // 3. Renderizar campos de pagamento na cor verde
        if (tvStatusBadge != null) {
            tvStatusBadge.setText("PAGAMENTO PENDENTE");
            tvStatusBadge.setTextColor(0xFF00E676);
        }
        if (tvStatusSub != null) tvStatusSub.setText("Aguardando confirmação do cliente");

        if (tvPendingValue != null) {
            tvPendingValue.setText(value.isEmpty() ? "R$ 250,00" : value);
            tvPendingValue.setTextColor(0xFF00E676);
        }

        if (tvPixCode != null) {
            if (pix == null || pix.isEmpty()) {
                tvPixCode.setText("Chave Pix: 19994827743");
            } else {
                tvPixCode.setText("Chave Pix: " + pix);
            }
            tvPixCode.setTextColor(0xFF00E676);
        }

        loadQrCode(qrPath);

        if (cardPending != null) cardPending.setVisibility(View.VISIBLE);

        configManager.exportStatusJson();
    }

    private void loadLogo(String path) {
        String[] candidates = new String[] {
            path,
            new File(configManager.getAppFilesDir(), "service_logo.png").getAbsolutePath(),
            "/sdcard/Android/data/br.com.mdmfrpbrasil.deviceservice/files/service_logo.png",
            "/data/local/tmp/service_logo.png"
        };

        for (String c : candidates) {
            if (c != null && !c.isEmpty()) {
                File f = new File(c);
                if (f.exists() && f.canRead() && f.length() > 0) {
                    try {
                        Bitmap bmp = BitmapFactory.decodeFile(c);
                        if (bmp != null) {
                            imgLogo.setImageBitmap(bmp);
                            return;
                        }
                    } catch (Exception ignored) {}
                }
            }
        }
        imgLogo.setImageResource(R.drawable.logo_official);
    }

    private void loadQrCode(String path) {
        String[] candidates = new String[] {
            path,
            new File(configManager.getAppFilesDir(), "service_qr.png").getAbsolutePath(),
            "/sdcard/Android/data/br.com.mdmfrpbrasil.deviceservice/files/service_qr.png",
            "/data/local/tmp/service_qr.png"
        };

        for (String c : candidates) {
            if (c != null && !c.isEmpty()) {
                File f = new File(c);
                if (f.exists() && f.canRead() && f.length() > 0) {
                    try {
                        Bitmap bmp = BitmapFactory.decodeFile(c);
                        if (bmp != null) {
                            imgQrCode.setImageBitmap(bmp);
                            imgQrCode.setVisibility(View.VISIBLE);
                            return;
                        }
                    } catch (Exception ignored) {}
                }
            }
        }
        imgQrCode.setImageDrawable(null);
    }
}
