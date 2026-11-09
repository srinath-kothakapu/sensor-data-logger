// Example firmware: send temperature and humidity over UART as "temp,hum".
// Board: Arduino Uno with a DHT11 sensor on pin 2 (library: "DHT sensor library" by Adafruit).
// The Python logger in ../../src reads one line per sample at 115200 baud.
// Adapt the sensor and pins to your own hardware; for an STM32 board, send the same
// text format with printf over UART.

#include <DHT.h>

#define DHT_PIN 2
#define DHT_TYPE DHT11

DHT dht(DHT_PIN, DHT_TYPE);

void setup() {
  Serial.begin(115200);
  dht.begin();
}

void loop() {
  float humidity = dht.readHumidity();
  float temperature = dht.readTemperature();

  // Only send complete readings. A failed read returns NaN.
  if (!isnan(humidity) && !isnan(temperature)) {
    Serial.print(temperature, 2);
    Serial.print(",");
    Serial.println(humidity, 1);
  }
  delay(1000);  // DHT11 can be read at most about once per second
}
