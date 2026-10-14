// Copy to config.h and fill in. config.h is git-ignored: it contains secrets.
#pragma once

#define WIFI_SSID        "your-wifi"
#define WIFI_PASSWORD    "your-wifi-password"

// Backend base URL (use https:// in production; see docs/HARDWARE.md)
#define SEG_BASE_URL     "http://192.168.1.10:8000"
#define SEG_DEVICE_ID    "esp32-lab301"          // X-Device-Id (uid registered in the dashboard)
#define SEG_DEVICE_KEY   "seg_xxxxxxxxxxxxxxxx"  // X-Device-Key (shown once at registration)

#define TELEMETRY_INTERVAL_MS 5000

// ---- Pins -------------------------------------------------------------------
#define PIR_PIN          27      // HC-SR501 / AM312 digital output
#define PIR_HOLD_MS      120000  // occupied if motion seen within this window

// Relay channels (index = relay_channel configured for the appliance)
#define NUM_CHANNELS 4
static const int RELAY_PINS[NUM_CHANNELS] = {16, 17, 18, 19};
#define RELAY_ACTIVE_LOW 1       // most opto-isolated relay boards are active-low

// Power measurement: PZEM-004T v3 on UART2 (one module per channel via address, or one shared)
#define PZEM_RX_PIN 25
#define PZEM_TX_PIN 26
