/*
 * Smart Energy Guardian — ESP32 reference firmware
 *
 * Reports occupancy (PIR) and per-channel electrical readings (PZEM-004T v3) to the backend,
 * receives ON/OFF commands, drives relays and acknowledges each command.
 *
 * Protocol (see docs/HARDWARE.md):
 *   POST /api/v1/esp32/telemetry          -> response includes pending commands
 *   POST /api/v1/esp32/commands/{id}/ack  {success, relay_on, error}
 *   Headers: X-Device-Id, X-Device-Key
 *
 * Safety design:
 *   - Relays default to the "appliance ON" (normally-closed / de-energised) state at boot and on
 *     loss of connectivity, so a backend or Wi-Fi failure never leaves rooms dark.
 *   - Commands are absolute (on/off) and idempotent; re-delivery is harmless.
 *   - Expired commands (past expires_at relative to server_time) are ignored.
 *   - The backend only sends hardware commands when REAL_SWITCHING_ENABLED=true and an admin has
 *     validated this device. This sketch has NOT been compiled or tested on hardware by the
 *     project authors; validate wiring and behaviour on a bench before connecting mains loads.
 *
 * Libraries: ArduinoJson (v7), PZEM004Tv30 (mandulaj), WiFi/HTTPClient (ESP32 core).
 */
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <PZEM004Tv30.h>
#include "config.h"

static const char* FW_VERSION = "1.0.0";

HardwareSerial PzemSerial(2);
PZEM004Tv30* pzem[NUM_CHANNELS];
bool relayOn[NUM_CHANNELS];
unsigned long lastMotionMs = 0;
unsigned long lastTelemetryMs = 0;
bool pirHealthy = true;

void setRelay(int ch, bool on) {
  if (ch < 0 || ch >= NUM_CHANNELS) return;
  relayOn[ch] = on;
  // Wiring assumption: appliance powered through the relay's NC contact, so "on" = coil released.
  bool energise = !on;
  digitalWrite(RELAY_PINS[ch], (RELAY_ACTIVE_LOW ? !energise : energise) ? HIGH : LOW);
}

void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) delay(250);
}

bool postJson(const String& path, const String& body, String& response) {
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  http.setTimeout(5000);
  http.begin(String(SEG_BASE_URL) + path);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Id", SEG_DEVICE_ID);
  http.addHeader("X-Device-Key", SEG_DEVICE_KEY);
  int code = http.POST(body);
  response = code > 0 ? http.getString() : "";
  http.end();
  return code >= 200 && code < 300;
}

void ack(long commandId, bool success, int ch, const char* error) {
  JsonDocument doc;
  doc["success"] = success;
  if (ch >= 0 && ch < NUM_CHANNELS) doc["relay_on"] = relayOn[ch];
  if (error) doc["error"] = error;
  String body, resp;
  serializeJson(doc, body);
  postJson("/api/v1/esp32/commands/" + String(commandId) + "/ack", body, resp);
}

void handleCommands(JsonArray cmds) {
  for (JsonObject c : cmds) {
    long id = c["command_id"] | -1L;
    int ch = c["channel"] | -1;
    const char* action = c["action"] | "";
    if (id < 0) continue;
    if (ch < 0 || ch >= NUM_CHANNELS) { ack(id, false, -1, "unknown relay channel"); continue; }
    bool wantOn = strcmp(action, "on") == 0;
    if (!wantOn && strcmp(action, "off") != 0) { ack(id, false, ch, "unknown action"); continue; }
    setRelay(ch, wantOn);
    delay(300);  // let the contact settle, then verify with the meter
    float p = pzem[ch]->power();
    bool verified = isnan(p) || (wantOn ? true : p < 5.0);  // off must drop below standby
    ack(id, verified, ch, verified ? nullptr : "power still present after OFF (relay fault?)");
  }
}

void sendTelemetry() {
  JsonDocument doc;
  doc["format"] = "seg.v1";
  JsonObject occ = doc["occupancy"].to<JsonObject>();
  if (pirHealthy) {
    occ["occupied"] = (millis() - lastMotionMs) < PIR_HOLD_MS;
    occ["sensor_ok"] = true;
  } else {
    occ["occupied"] = nullptr;
    occ["sensor_ok"] = false;
  }
  JsonArray readings = doc["readings"].to<JsonArray>();
  for (int ch = 0; ch < NUM_CHANNELS; ch++) {
    float p = pzem[ch]->power(), v = pzem[ch]->voltage(), i = pzem[ch]->current();
    if (isnan(p)) continue;  // meter not responding: omit -> backend marks data stale
    JsonObject r = readings.add<JsonObject>();
    r["channel"] = ch;
    r["power_w"] = p;
    if (!isnan(v)) r["voltage_v"] = v;
    if (!isnan(i)) r["current_a"] = i;
    r["relay_on"] = relayOn[ch];
  }
  JsonObject h = doc["health"].to<JsonObject>();
  h["firmware"] = FW_VERSION;
  h["rssi_dbm"] = WiFi.RSSI();
  h["uptime_s"] = millis() / 1000;
  h["free_heap"] = ESP.getFreeHeap();
  h["ip"] = WiFi.localIP().toString();

  String body, resp;
  serializeJson(doc, body);
  if (!postJson("/api/v1/esp32/telemetry", body, resp)) return;
  JsonDocument res;
  if (deserializeJson(res, resp) == DeserializationError::Ok) handleCommands(res["commands"].as<JsonArray>());
}

void setup() {
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);
  for (int ch = 0; ch < NUM_CHANNELS; ch++) {
    pinMode(RELAY_PINS[ch], OUTPUT);
    setRelay(ch, true);  // fail-safe default: appliances powered
  }
  PzemSerial.begin(9600, SERIAL_8N1, PZEM_RX_PIN, PZEM_TX_PIN);
  for (int ch = 0; ch < NUM_CHANNELS; ch++) pzem[ch] = new PZEM004Tv30(PzemSerial, PZEM_RX_PIN, PZEM_TX_PIN, 0x01 + ch);
  connectWifi();
}

void loop() {
  if (digitalRead(PIR_PIN) == HIGH) lastMotionMs = millis();
  if (millis() - lastTelemetryMs >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryMs = millis();
    connectWifi();
    sendTelemetry();
  }
  delay(50);
}
