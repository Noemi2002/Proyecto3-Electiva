const int pinR   = 3;
const int pinG   = 5;
const int pinB   = 6;
const int pinMIC = 7;    // KY-037 OUT
const int pinBUZ = 8;    // Buzzer activo +
const int pinLDR = A0;   // Fotocelda (con resistencia 10kΩ a GND)
const bool ANODO_COMUN = false;

String incoming = "";

// ── Brillo adaptativo ─────────────────────────
int  currentR = 0, currentG = 0, currentB = 0;
int  currentBrightness = 255;           // 0-255
unsigned long lastLDRRead = 0;
const int LDR_INTERVAL = 2000;          // leer cada 2 segundos

// ── Detección de palmadas ──────────────────────
const int CLAP_WINDOW   = 600;
const int CLAP_COOLDOWN = 800;
unsigned long lastClapTime  = 0;
unsigned long firstClapTime = 0;
bool waitingSecond = false;

void setup() {
  pinMode(pinR,   OUTPUT);
  pinMode(pinG,   OUTPUT);
  pinMode(pinB,   OUTPUT);
  pinMode(pinMIC, INPUT);
  pinMode(pinBUZ, OUTPUT);
  Serial.begin(9600);
  Serial.println("BOOT:OK - Arduino listo");
  testBlink();
}

void loop() {
  // ── Leer serial ──
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      incoming.trim();
      if (incoming.length() > 0) {
        Serial.print("CMD_IN: ");
        Serial.println(incoming);
        processCommand(incoming);
      }
      incoming = "";
    } else {
      incoming += c;
    }
  }

  detectClap();
  readLDR();
}

// ── Fotocelda ─────────────────────────────────
void readLDR() {
  unsigned long now = millis();
  if (now - lastLDRRead < LDR_INTERVAL) return;
  lastLDRRead = now;

  int ldrVal = analogRead(pinLDR);   // 0 (oscuro) – 1023 (muy claro)

  // Mapear luz ambiente → brillo del LED
  // Oscuro = tenue (mín 30), claro = pleno (255)
  int newBrightness = map(ldrVal, 0, 1023, 30, 255);

  if (abs(newBrightness - currentBrightness) > 10) {
    currentBrightness = newBrightness;
    applyColor();   // reaplicar color con nuevo brillo
  }

  // Reportar a la app
  Serial.print("LDR:");
  Serial.println(ldrVal);
}

// ── LED ───────────────────────────────────────
void applyColor() {
  // Escalar cada canal por el brillo actual
  int r = (currentR * currentBrightness) / 255;
  int g = (currentG * currentBrightness) / 255;
  int b = (currentB * currentBrightness) / 255;

  if (ANODO_COMUN) {
    analogWrite(pinR, 255 - r);
    analogWrite(pinG, 255 - g);
    analogWrite(pinB, 255 - b);
  } else {
    analogWrite(pinR, r);
    analogWrite(pinG, g);
    analogWrite(pinB, b);
  }
}

void setColor(int r, int g, int b) {
  currentR = r;
  currentG = g;
  currentB = b;
  applyColor();
}

// ── Buzzer ────────────────────────────────────
void beep(int ms) {
  digitalWrite(pinBUZ, HIGH);
  delay(ms);
  digitalWrite(pinBUZ, LOW);
}

void buzzStart()   { beep(120); Serial.println("BUZZ_START_DONE"); }
void buzzWorkEnd() { for(int i=0;i<3;i++){beep(80);delay(80);} Serial.println("BUZZ_WORK_DONE"); }
void buzzRestEnd() { beep(300); delay(150); beep(300); Serial.println("BUZZ_REST_DONE"); }

// ── Palmadas ──────────────────────────────────
void detectClap() {
  unsigned long now = millis();
  bool soundDetected = (digitalRead(pinMIC) == LOW);

  if (soundDetected && (now - lastClapTime > CLAP_COOLDOWN)) {
    lastClapTime = now;
    if (!waitingSecond) {
      firstClapTime = now;
      waitingSecond = true;
    } else {
      waitingSecond = false;
      Serial.println("CLAP:2");
    }
  }

  if (waitingSecond && (now - firstClapTime > CLAP_WINDOW)) {
    waitingSecond = false;
    Serial.println("CLAP:1");
  }
}

// ── Comandos ──────────────────────────────────
void processCommand(String cmd) {
  if (cmd.startsWith("LED:")) {
    int comma1 = cmd.indexOf(',');
    int comma2 = cmd.indexOf(',', comma1 + 1);
    if (comma1 == -1 || comma2 == -1) { Serial.println("ERR: formato invalido"); return; }
    int r = constrain(cmd.substring(4, comma1).toInt(), 0, 255);
    int g = constrain(cmd.substring(comma1 + 1, comma2).toInt(), 0, 255);
    int b = constrain(cmd.substring(comma2 + 1).toInt(), 0, 255);
    Serial.print("LED_SET R="); Serial.print(r);
    Serial.print(" G="); Serial.print(g);
    Serial.print(" B="); Serial.println(b);
    setColor(r, g, b);
    Serial.println("LED_OK");

  } else if (cmd == "PING")          { Serial.println("PONG");
  } else if (cmd == "BUZZ:START")    { buzzStart();
  } else if (cmd == "BUZZ:WORK_END") { buzzWorkEnd();
  } else if (cmd == "BUZZ:REST_END") { buzzRestEnd();
  } else {
    Serial.print("ERR: comando desconocido -> "); Serial.println(cmd);
  }
}

void testBlink() {
  setColor(255, 0, 0); delay(300);
  setColor(0, 255, 0); delay(300);
  setColor(0, 0, 255); delay(300);
  setColor(0, 0, 0);
}
