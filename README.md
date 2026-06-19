# Proyecto 3: Lámpara Pomora

**Curso:** Modelación Hardware/Software con Orientación a Objetos

**Profesor:** Marco Hernández Vásquez

## Integrantes

| Nombre             | Carné      | Carrera                         |
| ------------------ | ---------- | ------------------------------- |
| Katarina Castro    | 2021039878 | Ingeniería en Diseño Industrial |
| Carolina Rodríguez | 2021037281 | Ingeniería en Computadores      |
| Karol Rodríguez    | 2021015410 | Ingeniería en Diseño Industrial |
| Noemí Vargas       | 2021082564 | Ingeniería en Computadores      |

---

# Descripción del proyecto

La **Lámpara Pomora** es un sistema desarrollado sobre Arduino UNO que implementa la técnica Pomodoro para administración del tiempo, controlado mediante una aplicación de escritorio desarrollada con Python y Kivy.

La aplicación se comunica inalámbricamente con el Arduino utilizando un módulo Bluetooth HC-05, permitiendo controlar el funcionamiento de la lámpara sin necesidad de mantener una conexión USB permanente.

El sistema incorpora:

* Temporizador Pomodoro configurable.
* Control de una tira LED NeoPixel.
* Ajuste automático de brillo mediante una fotocelda.
* Pausa y reanudación mediante detección de palmadas.
* Notificaciones mediante buzzer.
* Configuración de tiempos de trabajo y descanso desde la aplicación.

---

# Tecnologías utilizadas

## Hardware

* Arduino Uno
* Módulo Bluetooth HC-05
* Tira LED NeoPixel
* Sensor de sonido KY-037
* Fotocelda
* Resistencias
* Buzzer activo
* Power Bank USB

## Software

* Python 3.12+
* Kivy 2.3
* PySerial
* Arduino IDE
* threading
* time

---

# Arquitectura del sistema

```text
+-------------------+
| Aplicación Kivy   |
| (Python)          |
+---------+---------+
          |
          | Bluetooth Serial (HC-05)
          |
+---------v---------+
| Arduino Uno       |
|                   |
|  NeoPixel         |
|  KY-037           |
|  LDR              |
|  Buzzer           |
+-------------------+
```

La aplicación envía comandos mediante Bluetooth y recibe información del Arduino en tiempo real para actualizar la interfaz gráfica y el color de la tira Neopixel.

---

# Requisitos

## Hardware

* Arduino Uno
* HC-05
* NeoPixel
* KY-037
* LDR
* Buzzer
* Power Bank y/o alimentación USB

## Software

### Windows

* Python 3.12 o superior
* Arduino IDE
* Drivers Bluetooth

### Linux (Ubuntu)

* Python 3.12 o superior
* bluetoothctl
* rfcomm
* Arduino IDE

---

# Instrucciones de montaje

## HC-05

| HC-05 | Arduino                           |
| ----- | --------------------------------- |
| VCC   | 5V                                |
| GND   | GND                               |
| TXD   | Pin 2                             |
| RXD   | Pin 3 mediante divisor de voltaje |

---

## NeoPixel

| NeoPixel | Arduino                   |
| -------- | ------------------------- |
| DIN      | Pin 6                     |
| VCC      | 5V                        |
| GND      | GND                       |

---

## Sensor KY-037

| KY-037 | Arduino                             |
| ------ | ----------------------------------- |
| AO     | Pin A1                              |
| VCC    | 5V                                  |
| GND    | GND                                 |

---

## Fotocelda

La fotocelda debe conectarse: una patita a una resistencia que del otro extremo se conecta a GND, y la otra patita al Arduino al Pin A0.

---

## Buzzer

Conectar el buzzer activo al Pin 9 del Arduino y a GND.

---

# Instrucciones de instalación

## 1. Clonar el repositorio

```bash
git clone https://github.com/Noemi2002/Proyecto3-Electiva.git
cd Proyecto3-Electiva
```

---

## 2. Crear el entorno virtual

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
```

---

## 3. Instalar dependencias

Las dependencias externas necesarias son:

- `kivy`
- `pyserial`

### Linux

```bash
pip install kivy pyserial
```

### Windows

```powershell
pip install kivy pyserial
```

---

# Configuración del Bluetooth

## Windows

1. Encender el Arduino.
2. Alimentar el Arduino mediante USB o Power Bank.
3. Emparejar el HC-05 desde la configuración de Bluetooth de Windows.
4. Abrir el **Administrador de dispositivos**.
5. Identificar el puerto:

```
Standard Serial over Bluetooth link (COMx,el número x puede variar)
```

6. Ejecutar la aplicación.
7. Seleccionar el puerto COM correspondiente.

---

## Linux

### Emparejar el dispositivo

```bash
bluetoothctl
```

Dentro de bluetoothctl:

```text
power on
agent on
default-agent
scan on
```

Cuando aparezca el dispositivo:

```text
pair XX:XX:XX:XX:XX:XX
trust XX:XX:XX:XX:XX:XX
quit
```

---

### Crear el puerto serial Bluetooth

```bash
sudo rfcomm bind 0 XX:XX:XX:XX:XX:XX 1
```

Verificar:

```bash
ls -l /dev/rfcomm0
```

Debe aparecer:

```text
/dev/rfcomm0
```

---

# Ejecución

Actualmente la aplicación se ejecuta desde la terminal.

## Linux

```bash
source .venv/bin/activate

python3 combinada.py
```


## Windows

```powershell
.venv\Scripts\activate

python neopixel.py
```

---

# Uso

1. Alimentar el Arduino mediante Power Bank.
2. Encender el sistema.
3. Crear el puerto Bluetooth (Linux) o identificar el puerto COM (Windows).
4. Ejecutar la aplicación.
5. Seleccionar el puerto Bluetooth en la aplicación.
6. Presionar **Iniciar Pomodoro**.
7. Configurar:

   * Seleccionar el modo en la aplicación o con los botones de la lámpara.

8. Iniciar el temporizador.

Durante la ejecución la aplicación permite:

* Iniciar el Pomodoro.
* Pausar y reanudar, ya sea mediante la apliccación o con aplausos.
* Configurar tiempos personalizados.
* Controlar y personalizar el color de la tira NeoPixel.
* Visualizar el estado de conexión.
* Recibir información enviada por el Arduino (fotocelda, sensor de sonido y buzzer).

---
