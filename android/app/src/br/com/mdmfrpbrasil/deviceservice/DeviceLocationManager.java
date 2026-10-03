package br.com.mdmfrpbrasil.deviceservice;

import android.Manifest;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.location.Address;
import android.location.Geocoder;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.net.ConnectivityManager;
import android.net.NetworkInfo;
import android.os.BatteryManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;

public class DeviceLocationManager {

    private static final String TAG = "DeviceLocationManager";
    private static final String DEFAULT_LOCATION_ENDPOINT = "http://127.0.0.1:8088/api/device/location";
    private static final String CLOUD_LOCATION_ENDPOINT = "https://mdm-brasil.onrender.com/api/device/location";
    private static final String CLOUD_STATE_ENDPOINT = "https://mdm-brasil.onrender.com/api/device/state";

    private static DeviceLocationManager instance;

    public static synchronized DeviceLocationManager getInstance(Context context, ConfigManager configManager) {
        if (instance == null) {
            instance = new DeviceLocationManager(context.getApplicationContext(), configManager);
        }
        return instance;
    }

    public static synchronized DeviceLocationManager getInstanceOrNull() {
        return instance;
    }

    private final Context context;
    private final ConfigManager configManager;
    private final LocationManager locationManager;
    private final Handler mainHandler;

    private boolean isTrackingEnabled = true;
    private long updateIntervalMs = 5 * 60 * 1000L; // 5 minutes default
    private Location lastValidLocation = null;
    private boolean isRequestingFreshLocation = false;

    private final Runnable periodicUpdateTask = new Runnable() {
        @Override
        public void run() {
            if (isTrackingEnabled) {
                acquireAndUploadLocation("PERIODIC");
                mainHandler.postDelayed(this, updateIntervalMs);
            }
        }
    };

    public DeviceLocationManager(Context context, ConfigManager configManager) {
        this.context = context.getApplicationContext();
        this.configManager = configManager;
        this.locationManager = (LocationManager) this.context.getSystemService(Context.LOCATION_SERVICE);
        this.mainHandler = new Handler(Looper.getMainLooper());
    }

    public void startPeriodicTracking() {
        mainHandler.removeCallbacks(periodicUpdateTask);
        // Initial acquisition after 3 seconds to let network/ADB initialize
        mainHandler.postDelayed(new Runnable() {
            @Override
            public void run() {
                acquireAndUploadLocation("INITIAL_BOOT");
            }
        }, 3000);
        mainHandler.postDelayed(periodicUpdateTask, updateIntervalMs);
    }

    public void stopPeriodicTracking() {
        mainHandler.removeCallbacks(periodicUpdateTask);
    }

    public void requestImmediateLocation() {
        Log.i(TAG, "[LOG] LOCATION_REQUEST_RECEIVED - Solicitação de localização sob demanda recebida");
        acquireAndUploadLocation("ON_DEMAND");
    }

    public boolean hasLocationPermission() {
        boolean fine = context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED;
        boolean coarse = context.checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
        return fine || coarse;
    }

    public void acquireAndUploadLocation(final String triggerReason) {
        if (!hasLocationPermission()) {
            Log.w(TAG, "[LOG] LOCATION_PERMISSION_DENIED - Permissão de localização não concedida");
            uploadUnavailablePayload("PERMISSION_DENIED");
            return;
        }

        Log.i(TAG, "[LOG] LOCATION_PERMISSION_GRANTED - Iniciando obtenção de coordenadas (" + triggerReason + ")");

        if (locationManager == null) {
            uploadUnavailablePayload("LOCATION_MANAGER_NULL");
            return;
        }

        Location bestLocation = null;

        try {
            String[] providers = new String[]{
                LocationManager.GPS_PROVIDER,
                LocationManager.NETWORK_PROVIDER,
                LocationManager.PASSIVE_PROVIDER,
                "fused"
            };

            for (String prov : providers) {
                try {
                    if (locationManager.isProviderEnabled(prov)) {
                        Location loc = locationManager.getLastKnownLocation(prov);
                        if (isBetterLocation(loc, bestLocation)) {
                            bestLocation = loc;
                        }
                    }
                } catch (Exception ignored) {}
            }
        } catch (SecurityException se) {
            Log.e(TAG, "[LOG] SecurityException accessing last known location: " + se.getMessage());
        }

        if (bestLocation != null) {
            this.lastValidLocation = bestLocation;
            Log.i(TAG, "[LOG] LOCATION_ACQUIRED (BestKnown): " + bestLocation.getLatitude() + ", " + bestLocation.getLongitude() + " Prec: " + bestLocation.getAccuracy() + "m");
            sendLocationToBackend(bestLocation, "BEST_KNOWN");
        }

        // Also request a single fresh update from GPS or Network if not already running
        if (!isRequestingFreshLocation) {
            requestFreshFix();
        } else if (bestLocation == null) {
            uploadUnavailablePayload("LOCATION_UNAVAILABLE");
        }
    }

    private void requestFreshFix() {
        if (!hasLocationPermission() || locationManager == null) return;

        try {
            isRequestingFreshLocation = true;
            final LocationListener freshListener = new LocationListener() {
                @Override
                public void onLocationChanged(Location location) {
                    isRequestingFreshLocation = false;
                    try {
                        locationManager.removeUpdates(this);
                    } catch (Exception ignored) {}

                    if (location != null) {
                        lastValidLocation = location;
                        Log.i(TAG, "[LOG] LOCATION_ACQUIRED (Fresh): " + location.getLatitude() + ", " + location.getLongitude() + " Prec: " + location.getAccuracy() + "m");
                        sendLocationToBackend(location, "FRESH_FIX");
                    }
                }

                @Override
                public void onStatusChanged(String provider, int status, Bundle extras) {}

                @Override
                public void onProviderEnabled(String provider) {}

                @Override
                public void onProviderDisabled(String provider) {}
            };

            boolean requested = false;
            if (locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
                locationManager.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000, 1.0f, freshListener, Looper.getMainLooper());
                requested = true;
            }
            if (locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
                locationManager.requestLocationUpdates(LocationManager.NETWORK_PROVIDER, 1000, 1.0f, freshListener, Looper.getMainLooper());
                requested = true;
            }

            if (!requested) {
                isRequestingFreshLocation = false;
                Log.w(TAG, "[LOG] LOCATION_UNAVAILABLE - Provedores GPS e Rede desativados no aparelho");
                if (lastValidLocation == null) {
                    uploadUnavailablePayload("GPS_DISABLED");
                }
            } else {
                // Safety timeout: remove updates after 15 seconds to prevent battery drain
                mainHandler.postDelayed(new Runnable() {
                    @Override
                    public void run() {
                        if (isRequestingFreshLocation) {
                            isRequestingFreshLocation = false;
                            try {
                                locationManager.removeUpdates(freshListener);
                            } catch (Exception ignored) {}
                            Log.d(TAG, "[LOG] Fresh fix listener timed out, retaining last known");
                            // Se tiver última localização válida, envia ela (Android 14 bloqueia GPS em background)
                            if (lastValidLocation != null) {
                                Log.i(TAG, "[LOG] LOCATION_ACQUIRED (LastValid fallback): " + lastValidLocation.getLatitude() + ", " + lastValidLocation.getLongitude());
                                sendLocationToBackend(lastValidLocation, "LAST_KNOWN");
                            } else {
                                // Tentar getLastKnownLocation como último recurso
                                Location fallback = null;
                                try {
                                    for (String prov : new String[]{LocationManager.NETWORK_PROVIDER, LocationManager.GPS_PROVIDER, LocationManager.PASSIVE_PROVIDER}) {
                                        try {
                                            Location l = locationManager.getLastKnownLocation(prov);
                                            if (isBetterLocation(l, fallback)) fallback = l;
                                        } catch (Exception ignored) {}
                                    }
                                } catch (Exception ignored) {}
                                if (fallback != null) {
                                    lastValidLocation = fallback;
                                    Log.i(TAG, "[LOG] LOCATION_ACQUIRED (SystemFallback): " + fallback.getLatitude() + ", " + fallback.getLongitude());
                                    sendLocationToBackend(fallback, "SYSTEM_FALLBACK");
                                } else {
                                    Log.i(TAG, "[LOG] GPS indisponível em ambiente interno. Acionando Fallback de Geolocalização por Rede/IP...");
                                    attemptIpGeolocationFallback();
                                }
                            }
                        }
                    }
                }, 15000);
            }

        } catch (SecurityException se) {
            isRequestingFreshLocation = false;
            Log.e(TAG, "SecurityException requesting updates: " + se.getMessage());
        }
    }

    private boolean isBetterLocation(Location location, Location currentBestLocation) {
        if (location == null) return false;
        if (currentBestLocation == null) return true;

        long timeDelta = location.getTime() - currentBestLocation.getTime();
        boolean isSignificantlyNewer = timeDelta > 60000; // 1 min newer
        boolean isSignificantlyOlder = timeDelta < -60000;
        boolean isNewer = timeDelta > 0;

        if (isSignificantlyNewer) return true;
        if (isSignificantlyOlder) return false;

        int accuracyDelta = (int) (location.getAccuracy() - currentBestLocation.getAccuracy());
        boolean isLessAccurate = accuracyDelta > 0;
        boolean isMoreAccurate = accuracyDelta < 0;

        if (isMoreAccurate) return true;
        if (isNewer && !isLessAccurate) return true;
        return false;
    }

    private int getBatteryLevel() {
        try {
            Intent batteryIntent = context.registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
            if (batteryIntent != null) {
                int level = batteryIntent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
                int scale = batteryIntent.getIntExtra(BatteryManager.EXTRA_SCALE, -1);
                if (level >= 0 && scale > 0) {
                    return (int) ((level / (float) scale) * 100);
                }
            }
        } catch (Exception ignored) {}
        return 100;
    }

    private String getNetworkStatus() {
        try {
            ConnectivityManager cm = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
            if (cm != null) {
                NetworkInfo activeNetwork = cm.getActiveNetworkInfo();
                if (activeNetwork != null && activeNetwork.isConnectedOrConnecting()) {
                    return "online";
                }
            }
        } catch (Exception ignored) {}
        return "offline";
    }

    private String escapeJson(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r");
    }

    private void sendLocationToBackend(final Location location, final String type) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                HttpURLConnection conn = null;
                try {
                    String street = "";
                    String number = "";
                    String neighborhood = "";
                    String city = "";
                    String state = "";
                    String cep = "";
                    String fullAddress = "";

                    try {
                        if (Geocoder.isPresent()) {
                            Geocoder geocoder = new Geocoder(context, Locale.getDefault());
                            List<Address> addresses = geocoder.getFromLocation(location.getLatitude(), location.getLongitude(), 1);
                            if (addresses != null && !addresses.isEmpty()) {
                                Address addr = addresses.get(0);
                                if (addr.getThoroughfare() != null) street = addr.getThoroughfare();
                                if (addr.getSubThoroughfare() != null) number = addr.getSubThoroughfare();
                                if (addr.getSubLocality() != null) neighborhood = addr.getSubLocality();
                                if (addr.getLocality() != null) city = addr.getLocality();
                                if (addr.getAdminArea() != null) state = addr.getAdminArea();
                                if (addr.getPostalCode() != null) cep = addr.getPostalCode();
                                if (addr.getAddressLine(0) != null) fullAddress = addr.getAddressLine(0);
                            }
                        }
                    } catch (Exception ge) {
                        Log.d(TAG, "Android Geocoder lookup note: " + ge.getMessage());
                    }

                    String payload = "{" +
                            "\"deviceId\":\"" + configManager.getDeviceId() + "\"," +
                            "\"latitude\":" + location.getLatitude() + "," +
                            "\"longitude\":" + location.getLongitude() + "," +
                            "\"accuracy\":" + location.getAccuracy() + "," +
                            "\"timestamp\":" + location.getTime() + "," +
                            "\"provider\":\"" + (location.getProvider() != null ? location.getProvider() : "fused") + "\"," +
                            "\"batteryLevel\":" + getBatteryLevel() + "," +
                            "\"networkStatus\":\"" + getNetworkStatus() + "\"," +
                            "\"street\":\"" + escapeJson(street) + "\"," +
                            "\"number\":\"" + escapeJson(number) + "\"," +
                            "\"neighborhood\":\"" + escapeJson(neighborhood) + "\"," +
                            "\"city\":\"" + escapeJson(city) + "\"," +
                            "\"state\":\"" + escapeJson(state) + "\"," +
                            "\"cep\":\"" + escapeJson(cep) + "\"," +
                            "\"fullAddress\":\"" + escapeJson(fullAddress) + "\"," +
                            "\"status\":\"LOCATION_ACQUIRED\"," +
                            "\"type\":\"" + type + "\"" +
                            "}";

                    boolean uploaded = false;

                    // 1. Tentar envio local via USB (127.0.0.1:8088)
                    try {
                        URL url = new URL(DEFAULT_LOCATION_ENDPOINT);
                        conn = (HttpURLConnection) url.openConnection();
                        conn.setRequestMethod("POST");
                        conn.setDoOutput(true);
                        conn.setConnectTimeout(1500);
                        conn.setReadTimeout(1500);
                        conn.setRequestProperty("Content-Type", "application/json");

                        OutputStream os = conn.getOutputStream();
                        os.write(payload.getBytes(StandardCharsets.UTF_8));
                        os.flush();
                        os.close();

                        if (conn.getResponseCode() == 200) {
                            uploaded = true;
                            Log.i(TAG, "[LOG] LOCATION_UPLOAD_SUCCESS (USB Local)");
                        }
                    } catch (Exception ignored) {
                    } finally {
                        if (conn != null) { conn.disconnect(); conn = null; }
                    }

                    // 2. Se local não respondeu (sem USB), enviar diretamente para a Nuvem Oficial via Wi-Fi/4G
                    if (!uploaded) {
                        try {
                            URL cloudUrl = new URL(CLOUD_LOCATION_ENDPOINT);
                            conn = (HttpURLConnection) cloudUrl.openConnection();
                            conn.setRequestMethod("POST");
                            conn.setDoOutput(true);
                            conn.setConnectTimeout(3500);
                            conn.setReadTimeout(3500);
                            conn.setRequestProperty("Content-Type", "application/json");

                            OutputStream os = conn.getOutputStream();
                            os.write(payload.getBytes(StandardCharsets.UTF_8));
                            os.flush();
                            os.close();

                            if (conn.getResponseCode() == 200) {
                                uploaded = true;
                                Log.i(TAG, "[LOG] LOCATION_UPLOAD_SUCCESS (Cloud Nuvem)");
                            }
                        } catch (Exception ignored) {
                        } finally {
                            if (conn != null) { conn.disconnect(); conn = null; }
                        }
                    }

                    // 3. Checagem em segundo plano: verificar se há comando de Bloqueio Remoto Online emitido pelo cliente/site
                    try {
                        URL stateUrl = new URL(CLOUD_STATE_ENDPOINT + "?deviceId=" + configManager.getDeviceId());
                        conn = (HttpURLConnection) stateUrl.openConnection();
                        conn.setRequestMethod("GET");
                        conn.setConnectTimeout(3000);
                        conn.setReadTimeout(3000);
                        conn.setRequestProperty("Accept", "application/json");

                        if (conn.getResponseCode() == 200) {
                            java.io.BufferedReader reader = new java.io.BufferedReader(new java.io.InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8));
                            StringBuilder sb = new StringBuilder();
                            String line;
                            while ((line = reader.readLine()) != null) sb.append(line);
                            reader.close();

                            String jsonResp = sb.toString();
                            if ((jsonResp.contains("\"status\":\"PENDING\"") || jsonResp.contains("\"status\":\"LOCKED\"")) && configManager.isPaidOrUnlocked()) {
                                Log.w(TAG, "[MDM ALERTA] Comando de Bloqueio Remoto Detectado via Nuvem! Rebloqueando aparelho...");
                                configManager.setAuthoritativeState("PENDING", "OP-ONLINE-LOCK", "CLOUD_AUTHORITY");
                                KioskSecurityPolicyManager.applyKioskLock(context);

                                // Reabilitar MainActivity e abrir tela Kiosk imediatamente
                                try {
                                    android.content.ComponentName cn = new android.content.ComponentName(context, MainActivity.class);
                                    context.getPackageManager().setComponentEnabledSetting(
                                        cn,
                                        android.content.pm.PackageManager.COMPONENT_ENABLED_STATE_ENABLED,
                                        android.content.pm.PackageManager.DONT_KILL_APP
                                    );
                                } catch (Exception ignored) {}

                                Intent lockIntent = new Intent(context, MainActivity.class);
                                lockIntent.putExtra("state", "PENDING");
                                lockIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
                                context.startActivity(lockIntent);
                            } else if ((jsonResp.contains("\"status\":\"PAID\"") || jsonResp.contains("\"status\":\"UNLOCKED\"")) && !configManager.isPaidOrUnlocked()) {
                                Log.i(TAG, "[MDM ALERTA] Comando de Liberação Remota Detectado via Nuvem! Desbloqueando e restaurando aba de notificações...");
                                configManager.setAuthoritativeState(ConfigManager.STATE_PAID, "OP-ONLINE-UNLOCK", "CLOUD_AUTHORITY");
                                configManager.exportReleaseAck();
                                KioskSecurityPolicyManager.applyKioskUnlock(context);

                                try {
                                    Intent homeIntent = new Intent(Intent.ACTION_MAIN);
                                    homeIntent.addCategory(Intent.CATEGORY_HOME);
                                    homeIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                                    context.startActivity(homeIntent);
                                } catch (Exception ignored) {}
                            }
                        }
                    } catch (Exception ignored) {
                    } finally {
                        if (conn != null) conn.disconnect();
                    }
                } catch (Exception e) {
                    Log.w(TAG, "[LOG] LOCATION_CYCLE_NOTE: " + e.getMessage());
                }
            }
        }, "MDM-Location-Upload").start();
    }

    private void attemptIpGeolocationFallback() {
        new Thread(new Runnable() {
            @Override
            public void run() {
                HttpURLConnection conn = null;
                try {
                    URL ipUrl = new URL("https://ipwho.is/");
                    conn = (HttpURLConnection) ipUrl.openConnection();
                    conn.setConnectTimeout(4500);
                    conn.setReadTimeout(4500);
                    if (conn.getResponseCode() == 200) {
                        java.io.BufferedReader r = new java.io.BufferedReader(new java.io.InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8));
                        StringBuilder sb = new StringBuilder();
                        String line;
                        while ((line = r.readLine()) != null) sb.append(line);
                        r.close();
                        String resp = sb.toString();

                        double lat = extractJsonDouble(resp, "latitude");
                        double lon = extractJsonDouble(resp, "longitude");
                        String city = extractJsonString(resp, "city");
                        String state = extractJsonString(resp, "region_code");

                        if (lat != 0.0 && lon != 0.0) {
                            Location ipLoc = new Location("network_ip");
                            ipLoc.setLatitude(lat);
                            ipLoc.setLongitude(lon);
                            ipLoc.setAccuracy(80.0f);
                            ipLoc.setTime(System.currentTimeMillis());
                            lastValidLocation = ipLoc;
                            Log.i(TAG, "[LOG] LOCATION_ACQUIRED (IP Geolocation): " + lat + ", " + lon + " (" + city + " - " + state + ")");
                            sendLocationToBackend(ipLoc, "IP_GEOLOCATION");
                            return;
                        }
                    }
                } catch (Exception e) {
                    Log.w(TAG, "[LOG] IP Geolocation attempt note: " + e.getMessage());
                } finally {
                    if (conn != null) conn.disconnect();
                }

                uploadUnavailablePayload("BACKGROUND_LOCATION_BLOCKED");
            }
        }, "MDM-IP-Geo").start();
    }

    private double extractJsonDouble(String json, String key) {
        try {
            int idx = json.indexOf("\"" + key + "\":");
            if (idx != -1) {
                int start = idx + key.length() + 3;
                int end = json.indexOf(",", start);
                if (end == -1) end = json.indexOf("}", start);
                if (end != -1) {
                    return Double.parseDouble(json.substring(start, end).trim());
                }
            }
        } catch (Exception ignored) {}
        return 0.0;
    }

    private String extractJsonString(String json, String key) {
        try {
            int idx = json.indexOf("\"" + key + "\":\"");
            if (idx != -1) {
                int start = idx + key.length() + 4;
                int end = json.indexOf("\"", start);
                if (end != -1) {
                    return json.substring(start, end).trim();
                }
            }
        } catch (Exception ignored) {}
        return "";
    }

    private void uploadUnavailablePayload(final String reason) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                HttpURLConnection conn = null;
                try {
                    URL url = new URL(DEFAULT_LOCATION_ENDPOINT);
                    conn = (HttpURLConnection) url.openConnection();
                    conn.setRequestMethod("POST");
                    conn.setDoOutput(true);
                    conn.setConnectTimeout(3000);
                    conn.setReadTimeout(3000);
                    conn.setRequestProperty("Content-Type", "application/json");

                    String payload = "{" +
                            "\"deviceId\":\"" + configManager.getDeviceId() + "\"," +
                            "\"status\":\"LOCATION_UNAVAILABLE\"," +
                            "\"reason\":\"" + reason + "\"," +
                            "\"timestamp\":" + System.currentTimeMillis() + "," +
                            "\"batteryLevel\":" + getBatteryLevel() + "," +
                            "\"networkStatus\":\"" + getNetworkStatus() + "\"" +
                            "}";

                    OutputStream os = conn.getOutputStream();
                    os.write(payload.getBytes(StandardCharsets.UTF_8));
                    os.flush();
                    os.close();

                    conn.getResponseCode();
                    Log.i(TAG, "[LOG] LOCATION_UNAVAILABLE report enviado ao servidor");
                } catch (Exception ignored) {
                } finally {
                    if (conn != null) conn.disconnect();
                }
            }
        }, "MDM-Location-Unavailable").start();
    }
}
