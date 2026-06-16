/*
  ─────────────────────────────────────────────────────────
  Pomodoro Lamp - Arduino UNO + HC-05 + NeoPixel
  CE5507 – Modelación Hardware Software con Orientación a Objetos
  ─────────────────────────────────────────────────────────

  IMPORTANTE (Arduino UNO):
  El UNO solo tiene UN puerto serial físico (pines 0/1) y ese
  mismo puerto lo usa el cable USB para programar y para el
  Monitor Serial. Si el HC-05 quedara conectado ahí, tendrías
  que desconectarlo cada vez que subas un sketch.

  Por eso aquí el HC-05 se conecta a dos pines digitales
  CUALQUIERA (en este caso 2 y 3) usando la librería
  SoftwareSerial. Así:
    - Pines 0/1 quedan libres para el cable USB y el
      Monitor Serial (depuración).
    - Pines 2/3 manejan la comunicación con la app
      (a través del Bluetooth del HC-05).

  ─────────────────────────────────────────────────────────
  CONEXIONES
  ─────────────────────────────────────────────────────────

    NeoPixel -> Pin 6 (DIN), 5V, GND
    Buzzer   -> Pin 9 (+) , GND (-)
    LDR      -> A0 (divisor de voltaje con resistencia a GND)
    KY-037   -> A1 (salida analógica AO), 5V, GND

    Botones de modo (4): cada uno entre el pin digital y GND,
    usando la resistencia interna de pull-up del Arduino
    (no se necesita resistencia externa).
      Botón Clásico     -> Pin 4  -> GND
      Botón Invertido   -> Pin 5  -> GND
      Botón Flowmodoro  -> Pin 7  -> GND
      Botón Personalizado -> Pin 8 -> GND

    HC-05:
      TXD del HC-05  -> Pin 2 del Arduino (RX por software)
                        Conexión DIRECTA, sin divisor.
      RXD del HC-05  -> Pin 3 del Arduino (TX por software)
                        *** USAR DIVISOR DE VOLTAJE ***
                        Pin 3 ---[1k]---+---[2k]--- GND
                                         |
                                       RXD del HC-05
                        (Esto baja la señal de 5V a ~3.3V,
                         que es lo que tolera el HC-05)
      VCC -> 5V
      GND -> GND

  ─────────────────────────────────────────────────────────
  PROTOCOLO SERIAL (9600 baud, terminado en '\n')
  Igual que en la versión Leonardo, pero ahora viaja por
  SoftwareSerial (pines 2/3) en vez del puerto serial 0/1.
  ─────────────────────────────────────────────────────────

  Comandos que el Arduino RECIBE desde la app (vía HC-05):
    LED:r,g,b        -> Pinta todos los pixeles del NeoPixel
                        (color fijo; cancela cualquier FADE activo)
    FADE:r1,g1,b1,r2,g2,b2,periodo_ms
                     -> Crossfade continuo en bucle entre dos colores
                        (ej. para indicar descanso con una animación)
    BRIGHT:0-255     -> Ajusta el brillo global del NeoPixel
    BUZZ:START       -> Beep corto de inicio de sesión
    BUZZ:WORK_END    -> 3 beeps cortos
    BUZZ:REST_END    -> 2 beeps largos
    BUZZ:PAUSE       -> Tono descendente (pausa)
    BUZZ:RESUME      -> Tono ascendente (reanudar)
    PING             -> Responde "PONG"

  Mensajes que el Arduino ENVÍA hacia la app (vía HC-05):
    PONG, LED_OK, FADE_OK, BRIGHT_OK, CLAP:1 / CLAP:2, LDR:valor,
    BUZZ_START_DONE, BUZZ_WORK_DONE, BUZZ_REST_DONE,
    BUZZ_PAUSE_DONE, BUZZ_RESUME_DONE, ERR:...
    MODE:CLASICO / MODE:INVERTIDO / MODE:FLOWMODORO / MODE:CUSTOM
       -> se envía al presionar el botón físico correspondiente

  Estos mismos mensajes también se imprimen por Serial (USB)
  para que puedas ver lo que pasa en el Monitor Serial mientras
  desarrollas, sin que eso afecte la comunicación con la app.
*/

#include <SoftwareSerial.h>
#include <Adafruit_NeoPixel.h>

// ── Configuración de hardware ──────────────────────────────
#define PIN_NEOPIXEL   6
#define NUM_PIXELS     47      // ajustar según el largo de la tira/anillo
#define PIN_BUZZER     9
#define PIN_LDR        A0
#define PIN_SOUND      A1     // salida analógica del KY-037

#define PIN_BT_RX      2      // <- TXD del HC-05
#define PIN_BT_TX      3      // <- RXD del HC-05 (con divisor de voltaje)

// Botones de modo (pull-up interno, presionado = LOW)
#define PIN_BTN_CLASICO     4
#define PIN_BTN_INVERTIDO   5
#define PIN_BTN_FLOWMODORO  7
#define PIN_BTN_CUSTOM      8

#define DEFAULT_BRIGHTNESS 150   // 0-255

SoftwareSerial bt(PIN_BT_RX, PIN_BT_TX);
Adafruit_NeoPixel strip(NUM_PIXELS, PIN_NEOPIXEL, NEO_GRB + NEO_KHZ800);

// ── Estado interno ──────────────────────────────────────────
String inputBuffer = "";

// Lectura periódica de la fotocelda
unsigned long lastLDRsend = 0;
const unsigned long LDR_INTERVAL = 1000;   // ms

// Detección de palmadas (KY-037)
int soundThreshold = 400;                  // ajustar según ambiente/sensor
unsigned long lastSoundTime = 0;
const unsigned long SOUND_DEBOUNCE = 300;  // ms entre detecciones individuales
unsigned long clapWindowStart = 0;
const unsigned long CLAP_WINDOW = 600;     // ventana para agrupar 1 o 2 palmadas
int clapCount = 0;

// Debug de sensor
unsigned long lastSensorDebug = 0;
const unsigned long SENSOR_DEBUG_INTERVAL = 500;  // ms entre prints de debug

// Animación FADE (crossfade continuo entre dos colores)
bool fadeActive = false;
uint8_t fadeR1, fadeG1, fadeB1;   // color inicial
uint8_t fadeR2, fadeG2, fadeB2;   // color destino
unsigned long fadePeriod = 5000;  // duración de un ciclo completo (ms)
unsigned long fadeStart = 0;
unsigned long lastFadeUpdate = 0;
const unsigned long FADE_STEP = 30;  // ms entre actualizaciones (~33 fps)

// Botones de modo
const int NUM_MODE_BUTTONS = 4;
const int modeButtonPins[NUM_MODE_BUTTONS] = {
  PIN_BTN_CLASICO, PIN_BTN_INVERTIDO, PIN_BTN_FLOWMODORO, PIN_BTN_CUSTOM
};
const char* modeButtonNames[NUM_MODE_BUTTONS] = {
  "CLASICO", "INVERTIDO", "FLOWMODORO", "CUSTOM"
};
int modeButtonLastState[NUM_MODE_BUTTONS] = {HIGH, HIGH, HIGH, HIGH};
unsigned long modeButtonLastChange[NUM_MODE_BUTTONS] = {0, 0, 0, 0};
const unsigned long BUTTON_DEBOUNCE = 50;   // ms

// ─────────────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);   // Monitor Serial (USB) - solo para depurar
  bt.begin(9600);       // Comunicación con la app vía HC-05

  strip.begin();
  strip.setBrightness(DEFAULT_BRIGHTNESS);
  setColor(0, 0, 0);   // asegura que arranque apagado (no en blanco)

  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_SOUND, INPUT);

  for (int i = 0; i < NUM_MODE_BUTTONS; i++) {
    pinMode(modeButtonPins[i], INPUT_PULLUP);   // presionado = LOW
  }

  Serial.println("Listo. Esperando comandos por HC-05 (pines 2/3)...");
}

void loop() {
  readBluetooth();
  checkModeButtons();
  checkSound();
  sendLDR();
  updateFade();
}

// ── Lectura de comandos por Bluetooth ──────────────────────
void readBluetooth() {
  while (bt.available()) {
    char c = bt.read();
    if (c == '\n') {
      processCommand(inputBuffer);
      inputBuffer = "";
    } else if (c != '\r') {
      inputBuffer += c;
    }
  }
}

void processCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  Serial.print("Recibido: ");
  Serial.println(cmd);

  if (cmd == "PING") {
    sendMsg("PONG");
  }
  else if (cmd.startsWith("LED:")) {
    int r, g, b;
    if (parseRGB(cmd.substring(4), r, g, b)) {
      fadeActive = false;   // un color fijo cancela cualquier animación
      setColor(r, g, b);
      sendMsg("LED_OK");
    } else {
      sendMsg("ERR:LED_PARSE");
    }
  }
  else if (cmd.startsWith("FADE:")) {
    int r1, g1, b1, r2, g2, b2;
    unsigned long period;
    if (parseFade(cmd.substring(5), r1, g1, b1, r2, g2, b2, period)) {
      fadeR1 = r1; fadeG1 = g1; fadeB1 = b1;
      fadeR2 = r2; fadeG2 = g2; fadeB2 = b2;
      fadePeriod = period;
      fadeStart = millis();
      lastFadeUpdate = 0;
      fadeActive = true;
      sendMsg("FADE_OK");
    } else {
      sendMsg("ERR:FADE_PARSE");
    }
  }
  else if (cmd.startsWith("BRIGHT:")) {
    int val = cmd.substring(7).toInt();
    val = constrain(val, 0, 255);
    strip.setBrightness(val);
    strip.show();   // re-aplica el color actual con el nuevo brillo
    sendMsg("BRIGHT_OK");
  }
  else if (cmd.startsWith("BUZZ:")) {
    String type = cmd.substring(5);
    if (type == "START") {
      tone(PIN_BUZZER, 1000, 150);
      delay(150);
      noTone(PIN_BUZZER);
      sendMsg("BUZZ_START_DONE");
    }
    else if (type == "WORK_END") {
      for (int i = 0; i < 3; i++) {
        tone(PIN_BUZZER, 1500, 100);
        delay(150);
      }
      noTone(PIN_BUZZER);
      sendMsg("BUZZ_WORK_DONE");
    }
    else if (type == "REST_END") {
      for (int i = 0; i < 2; i++) {
        tone(PIN_BUZZER, 800, 300);
        delay(400);
      }
      noTone(PIN_BUZZER);
      sendMsg("BUZZ_REST_DONE");
    }
    else if (type == "PAUSE") {
      // Tono descendente: indica que la sesión se detuvo
      tone(PIN_BUZZER, 1000, 120);
      delay(130);
      tone(PIN_BUZZER, 600, 150);
      delay(150);
      noTone(PIN_BUZZER);
      sendMsg("BUZZ_PAUSE_DONE");
    }
    else if (type == "RESUME") {
      // Tono ascendente: indica que la sesión continúa
      tone(PIN_BUZZER, 600, 120);
      delay(130);
      tone(PIN_BUZZER, 1000, 150);
      delay(150);
      noTone(PIN_BUZZER);
      sendMsg("BUZZ_RESUME_DONE");
    }
    else {
      sendMsg("ERR:BUZZ_UNKNOWN");
    }
  }
  else {
    sendMsg("ERR:UNKNOWN_CMD:" + cmd);
  }
}

// Envía un mensaje tanto al HC-05 (app) como al Monitor Serial (USB)
void sendMsg(const String &msg) {
  bt.println(msg);
  Serial.print("Enviado: ");
  Serial.println(msg);
}

// ── Utilidades NeoPixel ─────────────────────────────────────
bool parseRGB(String params, int &r, int &g, int &b) {
  int c1 = params.indexOf(',');
  int c2 = params.indexOf(',', c1 + 1);
  if (c1 == -1 || c2 == -1) return false;

  r = params.substring(0, c1).toInt();
  g = params.substring(c1 + 1, c2).toInt();
  b = params.substring(c2 + 1).toInt();

  r = constrain(r, 0, 255);
  g = constrain(g, 0, 255);
  b = constrain(b, 0, 255);
  return true;
}

void setColor(int r, int g, int b) {
  uint32_t color = strip.Color(r, g, b);
  for (int i = 0; i < NUM_PIXELS; i++) {
    strip.setPixelColor(i, color);
  }
  strip.show();
}

// Parsea "r1,g1,b1,r2,g2,b2,periodo_ms"
bool parseFade(String params, int &r1, int &g1, int &b1,
               int &r2, int &g2, int &b2, unsigned long &period) {
  int idx[6];
  int pos = -1;
  for (int i = 0; i < 6; i++) {
    idx[i] = params.indexOf(',', pos + 1);
    if (idx[i] == -1) return false;
    pos = idx[i];
  }

  r1 = constrain(params.substring(0, idx[0]).toInt(), 0, 255);
  g1 = constrain(params.substring(idx[0] + 1, idx[1]).toInt(), 0, 255);
  b1 = constrain(params.substring(idx[1] + 1, idx[2]).toInt(), 0, 255);
  r2 = constrain(params.substring(idx[2] + 1, idx[3]).toInt(), 0, 255);
  g2 = constrain(params.substring(idx[3] + 1, idx[4]).toInt(), 0, 255);
  b2 = constrain(params.substring(idx[4] + 1, idx[5]).toInt(), 0, 255);
  period = params.substring(idx[5] + 1).toInt();

  return period > 0;
}

// Actualiza la animación de crossfade (si está activa).
// Hace un ciclo sinusoidal continuo entre (r1,g1,b1) y (r2,g2,b2)
// con duración total "fadePeriod" por ciclo completo.
void updateFade() {
  if (!fadeActive) return;

  unsigned long now = millis();
  if (now - lastFadeUpdate < FADE_STEP) return;
  lastFadeUpdate = now;

  unsigned long elapsed = (now - fadeStart) % fadePeriod;
  // t va de 0 a 1 y vuelve a 0 suavemente (función seno desplazada)
  float t = (sin(2.0 * PI * elapsed / (float)fadePeriod - HALF_PI) + 1.0) / 2.0;

  uint8_t r = fadeR1 + (int)((fadeR2 - fadeR1) * t);
  uint8_t g = fadeG1 + (int)((fadeG2 - fadeG1) * t);
  uint8_t b = fadeB1 + (int)((fadeB2 - fadeB1) * t);

  uint32_t color = strip.Color(r, g, b);
  for (int i = 0; i < NUM_PIXELS; i++) {
    strip.setPixelColor(i, color);
  }
  strip.show();
}

// ── Detección de palmadas (KY-037) ──────────────────────────
void checkSound() {
  int level = analogRead(PIN_SOUND);
  unsigned long now = millis();

  // Debug: mostrar nivel del sensor cada 500ms
  if (now - lastSensorDebug >= SENSOR_DEBUG_INTERVAL) {
    lastSensorDebug = now;
    Serial.print("[SENSOR] Nivel KY-037: ");
    Serial.print(level);
    Serial.print(" (umbral: ");
    Serial.print(soundThreshold);
    Serial.println(")");
  }

  if (level > soundThreshold && (now - lastSoundTime) > SOUND_DEBOUNCE) {
    lastSoundTime = now;
    Serial.print("[CLAP DETECTADO] Nivel: ");
    Serial.print(level);
    Serial.print(" > umbral: ");
    Serial.println(soundThreshold);
    if (clapCount == 0) {
      clapWindowStart = now;
    }
    clapCount++;
  }

  if (clapCount > 0 && (now - clapWindowStart) > CLAP_WINDOW) {
    if (clapCount == 1) {
      sendMsg("CLAP:1");
    } else {
      sendMsg("CLAP:2");
    }
    clapCount = 0;
  }
}

// ── Lectura periódica de la fotocelda ───────────────────────
void sendLDR() {
  unsigned long now = millis();
  if (now - lastLDRsend >= LDR_INTERVAL) {
    lastLDRsend = now;
    int val = analogRead(PIN_LDR);
    bt.print("LDR:");
    bt.println(val);
  }
}

// ── Botones físicos de selección de modo ────────────────────
// Cada botón va entre su pin y GND, usando el pull-up interno
// (INPUT_PULLUP), por lo que en reposo el pin lee HIGH y al
// presionar el botón lee LOW. Se envía MODE:<nombre> al detectar
// el flanco de presión (HIGH -> LOW), con un pequeño debounce
// para evitar múltiples envíos por una sola pulsación.
void checkModeButtons() {
  unsigned long now = millis();

  for (int i = 0; i < NUM_MODE_BUTTONS; i++) {
    int reading = digitalRead(modeButtonPins[i]);

    if (reading != modeButtonLastState[i] &&
        (now - modeButtonLastChange[i]) > BUTTON_DEBOUNCE) {

      modeButtonLastChange[i] = now;
      modeButtonLastState[i] = reading;

      if (reading == LOW) {   // se acaba de presionar
        sendMsg(String("MODE:") + modeButtonNames[i]);
      }
    }
  }
}
