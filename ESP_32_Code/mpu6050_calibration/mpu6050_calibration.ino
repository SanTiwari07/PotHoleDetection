/*************************************************
 *  MPU6050 OFFSET CALIBRATION (paper, Section 4.4)
 *
 *  Run once on the sensor node, mounted in the vehicle as it will be used,
 *  sitting still on level ground with the MPU6050's Z axis pointing up.
 *
 *  1. Discards the first 100 readings so the sensor settles.
 *  2. Averages 1000 readings on all six axes.
 *  3. Adjusts the MPU6050 offset registers until every axis is within
 *     8 LSB of its target (0 for X/Y and the gyros, 16384 = 1 g for Z).
 *  4. Prints the offsets as #defines to paste into esp_32_final.ino.
 *
 *  Wiring as in esp_32_final.ino: SDA GPIO21, SCL GPIO22, AD0 -> 3V3 (address 0x69).
 *  Open the Serial Monitor at 115200 baud.
 *************************************************/

#include <Wire.h>

#define MPU_ADDR 0x69
#define SDA_PIN 21
#define SCL_PIN 22

#define DISCARD_READINGS 100
#define AVERAGE_READINGS 1000
#define TOLERANCE_LSB 8
#define MAX_ITERATIONS 40

// At +/-2 g one accel offset step is ~8 raw LSB; at +/-250 deg/s one gyro offset step is ~4 raw LSB
#define ACCEL_STEP_LSB 8
#define GYRO_STEP_LSB 4

// Offset register addresses: accel X/Y/Z, gyro X/Y/Z (high byte first)
const uint8_t OFFSET_REG[6] = {0x06, 0x08, 0x0A, 0x13, 0x15, 0x17};
const long TARGET[6] = {0, 0, 16384, 0, 0, 0};
const char *AXIS_NAME[6] = {"ACCEL_OFFSET_X", "ACCEL_OFFSET_Y", "ACCEL_OFFSET_Z",
                            "GYRO_OFFSET_X", "GYRO_OFFSET_Y", "GYRO_OFFSET_Z"};

int16_t offsets[6];

void writeReg(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(value);
  Wire.endTransmission();
}

int16_t readWord(uint8_t reg) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.endTransmission(false);
  Wire.requestFrom((uint16_t)MPU_ADDR, (uint8_t)2, true);
  return (int16_t)(Wire.read() << 8 | Wire.read());
}

void writeWord(uint8_t reg, int16_t value) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write((uint8_t)(value >> 8));
  Wire.write((uint8_t)(value & 0xFF));
  Wire.endTransmission();
}

// Reads accel X/Y/Z and gyro X/Y/Z (temperature in between is skipped)
bool readRaw(int16_t raw[6]) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0 || Wire.requestFrom((uint16_t)MPU_ADDR, (uint8_t)14, true) != 14) {
    return false;
  }
  int16_t v[7];
  for (int i = 0; i < 7; i++) {
    v[i] = (int16_t)(Wire.read() << 8 | Wire.read());
  }
  raw[0] = v[0]; raw[1] = v[1]; raw[2] = v[2];   // accel
  raw[3] = v[4]; raw[4] = v[5]; raw[5] = v[6];   // gyro (v[3] is temperature)
  return true;
}

void averageReadings(long mean[6]) {
  long sum[6] = {0, 0, 0, 0, 0, 0};
  int16_t raw[6];
  int got = 0;
  while (got < AVERAGE_READINGS) {
    if (readRaw(raw)) {
      for (int a = 0; a < 6; a++) sum[a] += raw[a];
      got++;
    }
    delay(2);
  }
  for (int a = 0; a < 6; a++) mean[a] = sum[a] / AVERAGE_READINGS;
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);

  Wire.beginTransmission(MPU_ADDR);
  if (Wire.endTransmission() != 0) {
    Serial.println("MPU6050 not found at 0x69. Check wiring and that AD0 is tied to 3V3.");
    return;
  }

  writeReg(0x6B, 0x00);   // wake up
  writeReg(0x1C, 0x00);   // accel +/-2 g (same range the sensor node uses)
  writeReg(0x1B, 0x00);   // gyro +/-250 deg/s
  delay(100);

  // Start from the chip's current (factory) offsets
  for (int a = 0; a < 6; a++) offsets[a] = readWord(OFFSET_REG[a]);

  Serial.println("Keep the vehicle still. Settling...");
  int16_t raw[6];
  for (int i = 0; i < DISCARD_READINGS; i++) {
    readRaw(raw);
    delay(2);
  }

  for (int iter = 1; iter <= MAX_ITERATIONS; iter++) {
    long mean[6];
    averageReadings(mean);

    bool done = true;
    Serial.printf("Pass %2d  error:", iter);
    for (int a = 0; a < 6; a++) {
      long err = mean[a] - TARGET[a];
      Serial.printf(" %6ld", err);
      if (abs(err) > TOLERANCE_LSB) {
        done = false;
        int step = (a < 3) ? ACCEL_STEP_LSB : GYRO_STEP_LSB;
        long change = err / step;
        if (change == 0) change = (err > 0) ? 1 : -1;  // always make progress
        offsets[a] -= change;
        writeWord(OFFSET_REG[a], offsets[a]);
      }
    }
    Serial.println();

    if (done) {
      Serial.println("\nCalibration done. Paste these into esp_32_final.ino:\n");
      Serial.println("#define MPU_OFFSETS_CALIBRATED 1");
      for (int a = 0; a < 6; a++) {
        Serial.printf("#define MPU_%s %d\n", AXIS_NAME[a], offsets[a]);
      }
      return;
    }
  }
  Serial.println("\nDid not converge. Make sure the vehicle is still and the sensor is level, then reset.");
}

void loop() {}
