// Example firmware: send temperature and humidity over UART as a checked frame.
//
// Frame (one per line):   $<temperature_c>,<humidity_pct>*<CRC>\n     e.g.  $23.45,41.2*BE
// <CRC> is CRC-8 (polynomial 0x07, initial value 0) over the text between '$' and '*',
// printed as two uppercase hex digits. The Python logger in ../../src checks it and
// drops frames that arrive corrupted.
//
// Board: Arduino Uno with a DHT11 sensor on pin 2 (library: "DHT sensor library" by Adafruit).
// Adapt the sensor and pins to your own hardware; for an STM32 board, send the same
// frame format with snprintf/printf over UART.

#include <DHT.h>
#include <stdio.h>
#include <stdlib.h>

#define DHT_PIN 2
#define DHT_TYPE DHT11

// Plausible physical range; keep in sync with TEMP_RANGE_C / HUMIDITY_RANGE_PCT in src/sources.py
#define TEMP_MIN_C -40.0
#define TEMP_MAX_C 85.0
#define HUM_MIN_PCT 0.0
#define HUM_MAX_PCT 100.0

DHT dht(DHT_PIN, DHT_TYPE);

uint8_t crc8(const char *data) {
  uint8_t crc = 0;
  while (*data) {
    crc ^= (uint8_t)*data++;
    for (uint8_t bit = 0; bit < 8; bit++) {
      crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
    }
  }
  return crc;
}

void setup() {
  Serial.begin(115200);
  dht.begin();
}

void loop() {
  float humidity = dht.readHumidity();
  float temperature = dht.readTemperature();

  // Only send complete, plausible readings. A failed read returns NaN.
  bool ok = !isnan(humidity) && !isnan(temperature) &&
            temperature >= TEMP_MIN_C && temperature <= TEMP_MAX_C &&
            humidity >= HUM_MIN_PCT && humidity <= HUM_MAX_PCT;

  if (ok) {
    char t[10], h[10], payload[24];
    dtostrf(temperature, 1, 2, t);  // AVR snprintf has no %f, so format floats with dtostrf
    dtostrf(humidity, 1, 1, h);
    snprintf(payload, sizeof(payload), "%s,%s", t, h);

    char crc_text[3];
    snprintf(crc_text, sizeof(crc_text), "%02X", crc8(payload));

    Serial.print('$');
    Serial.print(payload);
    Serial.print('*');
    Serial.println(crc_text);
  }
  delay(1000);  // DHT11 can be read at most about once per second
}
