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

/**
 * LocationForegroundService — promove o processo a foreground para
 * garantir acesso ao GPS no Android 14 (background GPS restriction).
 * Inicia, obtém localização via DeviceLocationManager e encerra sozinho.
 */
public class LocationForegroundService extends Service {

    private static final String TAG = "LocationForegroundSvc";
    private static final String CHANNEL_ID = "mdm_location_channel";
    private static final int NOTIFICATION_ID = 1001;

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Log.i(TAG, "[FGS] LocationForegroundService iniciado — solicitando GPS em foreground");

        Notification notification = buildNotification();
        startForeground(NOTIFICATION_ID, notification);

        // Solicitar localização em thread separada (GPS pode demorar até 15s)
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    ConfigManager configManager = new ConfigManager(LocationForegroundService.this);
                    DeviceLocationManager locMgr = DeviceLocationManager.getInstance(LocationForegroundService.this, configManager);
                    locMgr.acquireAndUploadLocation("FOREGROUND_REQUEST");
                    // Aguardar até 20s para o GPS responder antes de parar o serviço
                    Thread.sleep(20000);
                } catch (InterruptedException ignored) {
                } catch (Exception e) {
                    Log.e(TAG, "Erro ao obter localização: " + e.getMessage());
                } finally {
                    Log.i(TAG, "[FGS] LocationForegroundService encerrando.");
                    stopSelf();
                }
            }
        }, "LocationFGS-Thread").start();

        return START_NOT_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    "MDM & FRP Brasil — Localização",
                    NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("Serviço de rastreamento do dispositivo gerenciado");
            channel.setShowBadge(false);
            channel.enableLights(false);
            channel.enableVibration(false);
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) nm.createNotificationChannel(channel);
        }
    }

    private Notification buildNotification() {
        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(this, CHANNEL_ID);
        } else {
            builder = new Notification.Builder(this);
        }

        return builder
                .setContentTitle("MDM & FRP Brasil")
                .setContentText("Obtendo localização do dispositivo...")
                .setSmallIcon(android.R.drawable.ic_menu_mylocation)
                .setOngoing(true)
                .build();
    }

    /**
     * Inicia o serviço de localização em foreground a partir de qualquer contexto.
     */
    public static void start(Context context) {
        Intent intent = new Intent(context, LocationForegroundService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(intent);
        } else {
            context.startService(intent);
        }
    }
}
