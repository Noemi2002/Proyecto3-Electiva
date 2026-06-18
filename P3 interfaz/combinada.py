"""
Pomodoro Lamp App
CE5507 – Modelación Hardware Software con Orientación a Objetos
Comunicación Bluetooth (HC-05) con Arduino Leonardo
LED de estado implementado con NeoPixel (Adafruit_NeoPixel)
"""

import threading
import time
import serial
import serial.tools.list_ports

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.progressbar import ProgressBar
from kivy.uix.popup import Popup
from kivy.uix.slider import Slider
from kivy.uix.colorpicker import ColorPicker
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle, Ellipse
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.graphics import Color, Rectangle
from kivy.core.window import Window

Window.size = (360, 640)

# ─────────────────────────────────────────────
# CAPA DE MODELO (POO)
# ─────────────────────────────────────────────

# Color de la luz mientras la sesión está en PAUSA, igual para todos
# los modos (blanco neutro ~4000K).
PAUSE_COLOR = (255, 244, 229)


class StudyMode:
    """Representa un modo de estudio con sus parámetros configurables."""

    def __init__(self, name: str, work_time: int, rest_time: int,
                 led_color: tuple, description: str = "",
                 rest_color: tuple = (0, 180, 80),
                 rest_fade_to: tuple | None = None,
                 rest_fade_period_ms: int = 6000):
        self.name = name
        self.work_time = work_time        # segundos
        self.rest_time = rest_time        # segundos
        self.led_color = led_color        # (R, G, B) color en fase WORK
        self.rest_color = rest_color      # (R, G, B) color inicial en fase REST
        self.rest_fade_to = rest_fade_to  # (R, G, B) color destino del fade (o None = sin animación)
        self.rest_fade_period_ms = rest_fade_period_ms
        self.description = description

    def get_led_command(self, phase: str) -> str:
        """Genera el comando a enviar al Arduino según la fase.

        - LED:r,g,b           -> color fijo (WORK, PAUSED, o REST sin animación)
        - FADE:r1,g1,b1,r2,g2,b2,periodo_ms
              -> crossfade continuo en bucle entre dos colores, usado
                 para la animación de la fase REST cuando rest_fade_to
                 está definido.

        En PAUSED siempre se usa PAUSE_COLOR (blanco neutro), igual
        para todos los modos. Al reanudar, el estado vuelve a WORK o
        REST y este mismo método devuelve de nuevo el color/animación
        que correspondía antes de pausar.
        """
        if phase == "WORK":
            r, g, b = self.led_color
            return f"LED:{r},{g},{b}\n"
        elif phase == "REST":
            if self.rest_fade_to is not None:
                r1, g1, b1 = self.rest_color
                r2, g2, b2 = self.rest_fade_to
                return (f"FADE:{r1},{g1},{b1},{r2},{g2},{b2},"
                        f"{self.rest_fade_period_ms}\n")
            r, g, b = self.rest_color
            return f"LED:{r},{g},{b}\n"
        else:  # PAUSED
            r, g, b = PAUSE_COLOR
            return f"LED:{r},{g},{b}\n"

    def __repr__(self):
        return (f"StudyMode({self.name}, work={self.work_time}s, "
                f"rest={self.rest_time}s)")


class PomodoroSession:
    """
    Controla el estado y tiempo de una sesión de estudio.
    Estados posibles: WORK, REST, PAUSED
    """

    STATES = ["WORK", "REST", "PAUSED"]

    def __init__(self, mode: StudyMode):
        self.mode = mode
        self.state: str = "WORK"
        self._pre_pause_state: str = "WORK"
        self.time_remaining: int = mode.work_time
        self.sessions_completed: int = 0
        self.on_state_change = None   # callback(state)
        self.on_tick = None           # callback(time_remaining)
        self.on_session_end = None    # callback(phase_ended)
        self.on_resume = None          # callback() - se llama solo al reanudar

    def set_mode(self, mode: StudyMode):
        """Cambia el modo y reinicia la sesión."""
        self.mode = mode
        self.state = "WORK"
        self.time_remaining = mode.work_time
        self.sessions_completed = 0
        self._notify_state_change()

    def pause(self):
        if self.state in ("WORK", "REST"):
            self._pre_pause_state = self.state
            self.state = "PAUSED"
            self._notify_state_change()

    def resume(self):
        if self.state == "PAUSED":
            self.state = self._pre_pause_state
            self._notify_state_change()
            if self.on_resume:
                self.on_resume()

    def toggle_pause(self):
        if self.state == "PAUSED":
            self.resume()
        else:
            self.pause()

    def extend(self, seconds: int = 300):
        """Extiende el tiempo actual (por voz o botón)."""
        self.time_remaining += seconds
        if self.on_tick:
            self.on_tick(self.time_remaining)

    def skip(self):
        """Salta al siguiente estado."""
        self._advance_phase()

    def tick(self):
        """Llamar cada segundo cuando el estado no es PAUSED."""
        if self.state == "PAUSED":
            return
        self.time_remaining -= 1
        if self.on_tick:
            self.on_tick(self.time_remaining)
        if self.time_remaining <= 0:
            self._advance_phase()

    def _advance_phase(self):
        if self.state == "WORK":
            self.sessions_completed += 1
            if self.on_session_end:
                self.on_session_end("WORK")
            self.state = "REST"
            self.time_remaining = self.mode.rest_time
        elif self.state == "REST":
            if self.on_session_end:
                self.on_session_end("REST")
            self.state = "WORK"
            self.time_remaining = self.mode.work_time
        self._notify_state_change()

    def _notify_state_change(self):
        if self.on_state_change:
            self.on_state_change(self.state)

    def get_progress(self) -> float:
        """Retorna progreso de 0.0 a 1.0."""
        total = (self.mode.work_time if self.state in ("WORK", "PAUSED")
                 else self.mode.rest_time)
        if total == 0:
            return 0.0
        elapsed = total - self.time_remaining
        return max(0.0, min(1.0, elapsed / total))

    @staticmethod
    def format_time(seconds: int) -> str:
        m, s = divmod(abs(seconds), 60)
        return f"{m:02d}:{s:02d}"


class BluetoothController:
    """Maneja la comunicación serial con el módulo HC-05."""

    BAUD_RATE = 9600

    def __init__(self):
        self._connection: serial.Serial | None = None
        self._port: str = ""
        self._lock = threading.Lock()
        self.on_data_received = None   # callback(data: str)

    def scan_ports(self) -> list[str]:
        return [p.device for p in serial.tools.list_ports.comports()]

    def connect(self, port: str) -> bool:
        try:
            self._connection = serial.Serial(port, self.BAUD_RATE, timeout=1)
            self._port = port
            threading.Thread(target=self._read_loop, daemon=True).start()
            return True
        except serial.SerialException:
            return False

    def disconnect(self):
        with self._lock:
            if self._connection and self._connection.is_open:
                self._connection.close()
            self._connection = None

    def send(self, command: str) -> bool:
        with self._lock:
            if not self.is_connected():
                return False
            try:
                self._connection.write(command.encode("utf-8"))
                return True
            except serial.SerialException:
                return False

    def is_connected(self) -> bool:
        return self._connection is not None and self._connection.is_open

    def _read_loop(self):
        while self.is_connected():
            try:
                if self._connection.in_waiting:
                    raw = self._connection.readline()
                    try:
                        line = raw.decode("utf-8").strip()
                    except UnicodeDecodeError:
                        # Byte corrupto/incompleto: se descarta esa línea
                        # y se sigue escuchando, en vez de morir.
                        print(f"[BT] Línea no decodificable, descartada: {raw!r}")
                        continue
                    if line and self.on_data_received:
                        self.on_data_received(line)
            except serial.SerialException as e:
                # Error real de conexión (cable desconectado, puerto
                # cerrado, etc.) -> aquí sí se detiene la escucha.
                print(f"[BT] Conexión perdida, deteniendo lectura: {e}")
                break
            except Exception as e:
                # Cualquier otro error inesperado: se reporta pero NO
                # se mata el hilo, para no quedar "sordos" en silencio.
                print(f"[BT] Error inesperado en _read_loop (ignorado): {e}")
                time.sleep(0.1)


class SoundDetectionHandler:
    """
    Interpreta comandos recibidos desde el Arduino
    que vienen del sensor KY-037 (palmadas).
    Protocolo esperado:
      CLAP:1  → una palmada  → toggle pause/reanudar
      CLAP:2  → dos palmadas → extender 5 min
    Incluye cooldown para evitar detecciones dobles accidentales.

    NOTA DE INTEGRACIÓN:
    Se conserva la lógica funcional de neopixel.py: por estabilidad del sensor,
    actualmente solo se ejecuta acción con CLAP:1 y se ignora CLAP:2.
    """

    COOLDOWN = 1.5   # segundos mínimos entre acciones

    def __init__(self, session: PomodoroSession):
        self.session = session
        self._last_action_time: float = 0.0
        self.on_clap = None   # callback(clap_count: int, action: str)

    def handle(self, raw: str):
        if not raw.startswith("CLAP:"):
            return

        try:
            count = int(raw.split(":")[1])
        except (IndexError, ValueError):
            return

        # Se mantiene igual que neopixel.py: CLAP:2 se ignora porque el sensor
        # puede generarlo falsamente de forma constante.
        if count != 1:
            return

        now = time.time()
        if now - self._last_action_time < self.COOLDOWN:
            return

        self._last_action_time = now

        print("[SoundDetection] Palmada detectada: toggle pause/reanudar")
        self.session.toggle_pause()

        action = "pause" if self.session.state == "PAUSED" else "resume"
        if self.on_clap:
            self.on_clap(1, action)


# ─────────────────────────────────────────────
# CAPA DE PRESENTACIÓN (Kivy UI)
# ─────────────────────────────────────────────

# ── Paleta visual refinada ──────────────────────────────────
BG_DARK    = (0.98, 0.94, 0.88, 1)   # crema cálida principal

BG_CARD    = (1.00, 0.87, 0.68, 1)   # durazno suave (card timer)
BG_CARD2   = (0.89, 0.78, 0.65, 1)   # beige medio (botones secundarios)
BG_CARD3   = (0.94, 0.87, 0.78, 1)   # beige claro (botones terciarios)

C_WORK     = (0.80, 0.22, 0.14, 1)   # rojo tomate profundo
C_REST     = (0.88, 0.55, 0.08, 1)   # ámbar intenso
C_PAUSE    = (0.55, 0.38, 0.16, 1)   # marrón ámbar

C_TEXT     = (0.15, 0.11, 0.07, 1)   # café casi negro
C_MUTED    = (0.48, 0.40, 0.32, 1)   # café apagado
C_SURFACE  = (0.96, 0.91, 0.83, 1)   # superficie neutra (status section)

C_PRIMARY  = (0.80, 0.22, 0.14, 1)   # tomate — acción primaria

# Brillo por defecto del NeoPixel (0-255), se sincroniza con el Arduino
DEFAULT_NEOPIXEL_BRIGHTNESS = 150

# Apagado automático por poca luz ambiental (fotocelda / LDR)
LDR_DARK_THRESHOLD_PCT = 60   # por debajo de este % se considera "poca luz"
LDR_OFF_TIMEOUT_S = 5         # segundos continuos en poca luz antes de apagar


def make_label(text, size=14, color=C_TEXT, bold=False, halign="left"):
    lbl = Label(text=text, font_size=size, color=color,
                bold=bold, halign=halign, valign="middle")
    lbl.bind(size=lbl.setter("text_size"))
    return lbl


def make_button(text, bg_color, font_size=14, height=48, color=(1, 1, 1, 1),
                bold=False):
    """Helper para crear botones con estilo consistente y tamaño táctil mínimo."""
    btn = Button(
        text=text,
        background_normal="",
        background_color=bg_color,
        font_size=font_size,
        color=color,
        bold=bold,
        size_hint_y=None,
        height=height,
    )
    return btn

class InicioScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        layout = FloatLayout()

        with layout.canvas.before:
            Color(1, 0.75, 0, 1)
            self.rect = Rectangle(
                size=layout.size,
                pos=layout.pos
            )

        layout.bind(size=self.actualizar_fondo)
        layout.bind(pos=self.actualizar_fondo)

        gif_tomates = Image(
            source="Tomates flotando.gif",
            anim_delay=0.05,
            size_hint=(1,1),
            allow_stretch=True,
            keep_ratio=False
        )

        logo = Image(
            source="logo.png",
            size_hint=(0.8,0.5),
            pos_hint={"center_x":0.5,"center_y":0.55}
        )
        boton = Button(
            text="INICIA TU MODO",
            size_hint=(0.7,0.08),
            pos_hint={"center_x":0.5,"center_y":0.45},
            background_normal="",
            background_color=(1, 0.3, 0.2, 1)
        )

        boton.bind(on_press=self.ir_a_app)

        layout.add_widget(gif_tomates)
        layout.add_widget(logo)
        layout.add_widget(boton)

        self.add_widget(layout)

    def actualizar_fondo(self, instance, value):
        self.rect.size = instance.size
        self.rect.pos = instance.pos

    def ir_a_app(self, instance):
        self.manager.current = "pomodoro"

        
class PomodoroScreen(Screen):
    pass


class PomodoroApp(App):

    def build(self):
        # ── Modos predefinidos ──
        self.modes = {
            "Clásico":     StudyMode(
                "Clásico", 25*60, 5*60,
                led_color=(80, 204, 100),          # #50CC64
                description="25 min trabajo · 5 min descanso",
                rest_color=(255, 147, 41),          # ámbar cálido 2200K
                rest_fade_to=(77, 44, 12),          # mismo ámbar atenuado (~30%)
                rest_fade_period_ms=5000,           # pulso suave cada 5 s
            ),
            "Invertido":   StudyMode(
                "Invertido", 5*60, 25*60,
                led_color=(255, 51, 51),            # #FF3333
                description="5 min trabajo · 25 min descanso",
                rest_color=(53, 88, 53),            # verde menta, brillo bajo
                rest_fade_to=(47, 72, 82),          # azul cielo, brillo bajo
                rest_fade_period_ms=6000,           # transición lenta y suave
            ),
            "Flowmodoro":  StudyMode(
                "Flowmodoro", 35*60, 10*60,
                led_color=(75, 0, 130),             # #4B0082 índigo
                description="Flujo libre · pausa sugerida a 35 min",
                rest_color=(75, 0, 130),            # parte del mismo índigo
                rest_fade_to=(230, 230, 250),       # se desvanece a lavanda #E6E6FA
                rest_fade_period_ms=8000,           # desvanecimiento lento
            ),
            "Método Personalizado":      StudyMode(
                "Método Personalizado", 25*60, 5*60,
                led_color=(255, 200, 0),
                description="Configurable desde la app",
                rest_color=(0, 180, 80),
            ),
        }

        # ── Controladores ──
        self.bt = BluetoothController()
        self.session = PomodoroSession(self.modes["Clásico"])
        self.sound_handler = SoundDetectionHandler(self.session)
        self._started = False   # el pomodoro no corre hasta presionar Start

        # Brillo actual del NeoPixel (se envía al Arduino con BRIGHT:n)
        self.neopixel_brightness = DEFAULT_NEOPIXEL_BRIGHTNESS

        # Apagado automático por poca luz (fotocelda)
        self._dark_since = None      # timestamp desde que hay poca luz
        self._lamp_auto_off = False   # True si el NeoPixel está apagado por esto

        self.bt.on_data_received = self._on_bt_data
        self.sound_handler.on_clap = self._on_clap

        self.session.on_state_change = self._on_state_change
        self.session.on_tick = self._on_tick
        self.session.on_session_end = self._on_session_end
        self.session.on_resume = self._on_resume

        # ── Layout raíz ──
        pomodoro_root = BoxLayout(orientation="vertical")
        with pomodoro_root.canvas.before:
            Color(*BG_DARK)
            self._bg_rect = RoundedRectangle(size=pomodoro_root.size, pos=pomodoro_root.pos)
        pomodoro_root.bind(size=self._update_bg, pos=self._update_bg)

        pomodoro_root.add_widget(self._build_header())
        pomodoro_root.add_widget(self._build_timer_section())
        pomodoro_root.add_widget(self._build_mode_tabs())
        pomodoro_root.add_widget(self._build_controls())
        pomodoro_root.add_widget(self._build_status_section())

        Clock.schedule_interval(self._clock_tick, 1)

        sm = ScreenManager()

        inicio = InicioScreen(name="inicio")

        pomodoro_screen = PomodoroScreen(name="pomodoro")
        pomodoro_screen.add_widget(pomodoro_root)

        sm.add_widget(inicio)
        sm.add_widget(pomodoro_screen)

        return sm

    # ─── Secciones UI ───────────────────────────────────────

    def _build_header(self):
        row = BoxLayout(size_hint_y=None, height=56, padding=(16, 10),
                        spacing=8)
        title = make_label("Lámpara Pomodoro", size=17, bold=True,
                           color=C_TEXT)
        row.add_widget(title)

        self.bt_label = make_label("Sin conexión", size=11,
                                   color=C_MUTED, halign="right")
        row.add_widget(self.bt_label)

        btn = Button(
            text="Bluetooth",
            size_hint=(None, None), size=(88, 36),
            background_normal="",
            background_color=(0.22, 0.20, 0.42, 1),
            font_size=12,
            bold=True,
            color=(1, 1, 1, 1),
        )
        btn.bind(on_press=lambda _: self._open_bt_popup())
        row.add_widget(btn)
        return row

    def _build_timer_section(self):
        box = BoxLayout(orientation="vertical", size_hint_y=None, height=210,
                        padding=(20, 10), spacing=4)
        with box.canvas.before:
            Color(*BG_CARD)
            rect = RoundedRectangle(size=box.size, pos=box.pos, radius=[20])
        box.bind(size=lambda w, s: setattr(rect, "size", s))
        box.bind(pos=lambda w, p: setattr(rect, "pos", p))

        # Etiqueta de estado — jerarquía alta, letra espaciada
        self.state_label = make_label("TRABAJANDO", size=13,
                                      color=C_WORK, halign="center", bold=True)
        box.add_widget(self.state_label)

        # Timer — elemento dominante de la pantalla
        self.timer_label = make_label(
            PomodoroSession.format_time(self.session.time_remaining),
            size=60, bold=True, halign="center", color=C_TEXT)
        box.add_widget(self.timer_label)

        # Barra de progreso más gruesa y visible
        self.progress = ProgressBar(max=100, value=0,
                                    size_hint_y=None, height=10)
        box.add_widget(self.progress)

        self.phase_label = make_label("Pomodoro clásico · sesión 1",
                                      size=11, color=C_MUTED, halign="center")
        box.add_widget(self.phase_label)
        return box

    def _build_mode_tabs(self):
        grid = GridLayout(cols=2, size_hint_y=None, height=100,
                          padding=(16, 8), spacing=8)
        self._mode_buttons = {}
        for name in self.modes:
            # El botón de configuración queda combinado con el modo personalizado.
            display_name = "Método Personalizado" if name == "Método Personalizado" else name
            btn = ToggleButton(
                text=display_name, group="modes",
                background_normal="",
                background_down="",
                background_color=BG_CARD2,
                color=C_MUTED,
                font_size=13,
                bold=False,
                size_hint_y=None,
                height=38,
            )
            if name == "Clásico":
                btn.state = "down"
                btn.background_color = C_WORK
                btn.color = (1, 1, 1, 1)
                btn.bold = True

            def _on_mode_press(b, n=name):
                self._select_mode(n)
                if n == "Método Personalizado":
                    self._open_custom_popup()

            btn.bind(on_press=_on_mode_press)
            self._mode_buttons[name] = btn
            grid.add_widget(btn)
        return grid

    def _build_controls(self):
        box = BoxLayout(orientation="vertical", size_hint_y=None, height=164,
                        padding=(16, 6), spacing=8)

        # ── CTA principal — acción de mayor jerarquía ──
        self.start_btn = Button(
            text="Iniciar Pomodoro",
            background_normal="",
            background_color=C_WORK,
            font_size=16,
            bold=True,
            color=(1, 1, 1, 1),
            size_hint_y=None,
            height=52,
        )
        self.start_btn.bind(on_press=lambda _: self._start_pomodoro())
        box.add_widget(self.start_btn)

        # ── Fila 1: Pausar / Saltar — acciones secundarias ──
        row1 = BoxLayout(spacing=10, size_hint_y=None, height=48)
        self.pause_btn = Button(
            text="Pausar",
            background_normal="",
            background_color=BG_CARD2,
            font_size=14,
            bold=True,
            color=C_TEXT,
            disabled=True,
        )
        self.pause_btn.bind(on_press=lambda _: self._toggle_pause())

        skip_btn = Button(
            text="Saltar",
            background_normal="",
            background_color=BG_CARD2,
            font_size=14,
            bold=True,
            color=C_TEXT,
        )
        skip_btn.bind(on_press=lambda _: self._skip())
        row1.add_widget(self.pause_btn)
        row1.add_widget(skip_btn)

        # ── Fila 2: Acciones terciarias — menor jerarquía ──
        row2 = BoxLayout(spacing=8, size_hint_y=None, height=38)
        ext_btn = Button(
            text="+5 min",
            background_normal="",
            background_color=BG_CARD3,
            font_size=12,
            color=C_TEXT,
        )
        ext_btn.bind(on_press=lambda _: self._extend())

        voice_btn = Button(
            text="Palmada",
            background_normal="",
            background_color=BG_CARD3,
            font_size=12,
            color=C_TEXT,
        )

        row2.add_widget(ext_btn)
        row2.add_widget(voice_btn)

        box.add_widget(row1)
        box.add_widget(row2)
        return box

    def _build_status_section(self):
        outer = BoxLayout(orientation="vertical", padding=(12, 6))
        with outer.canvas.before:
            Color(*C_SURFACE)
            rect2 = RoundedRectangle(size=outer.size, pos=outer.pos,
                                     radius=[14])
        outer.bind(size=lambda w, s: setattr(rect2, "size", s))
        outer.bind(pos=lambda w, p: setattr(rect2, "pos", p))

        box = BoxLayout(orientation="vertical", padding=(6, 4), spacing=5)
        box.add_widget(make_label("Estado del dispositivo", size=12,
                                  color=C_MUTED, bold=True))

        self.led_status = make_label("NeoPixel: —", size=13, color=C_TEXT)
        self.sessions_label = make_label("Sesiones completadas: 0",
                                         size=13, color=C_TEXT)
        self.sensor_label = make_label("KY-037: escuchando palmadas...",
                                       size=13, color=C_MUTED)
        self.buzzer_label = make_label("Buzzer: en espera",
                                       size=13, color=C_MUTED)
        self.ldr_label = make_label("Fotocelda: —",
                                    size=13, color=C_MUTED)

        for lbl in (self.led_status, self.sessions_label,
                    self.sensor_label, self.buzzer_label, self.ldr_label):
            box.add_widget(lbl)

        outer.add_widget(box)
        return outer

    # ─── Acciones ───────────────────────────────────────────

    def _start_pomodoro(self):
        if not self._started:
            self._started = True
            self.start_btn.text = "En curso"
            self.start_btn.background_color = C_MUTED
            self.start_btn.disabled = True
            self.pause_btn.disabled = False
            self.pause_btn.background_color = C_WORK
            self.bt.send("BUZZ:START\n")
            # forzar envío del color inicial
            self._on_state_change(self.session.state)

    def _toggle_pause(self):
        self.session.toggle_pause()

    def _skip(self):
        self.session.skip()

    def _extend(self):
        self.session.extend(300)

    def _select_mode(self, name: str):
        mode = self.modes[name]
        self.session.set_mode(mode)

        for n, btn in self._mode_buttons.items():

            if n == name:
                btn.state = "down"
                btn.background_color = C_WORK
                btn.color = (1, 1, 1, 1)
                btn.bold = True
            else:
                btn.state = "normal"
                btn.background_color = BG_CARD2
                btn.color = C_TEXT
                btn.bold = False

    # Traduce el nombre que envía el Arduino (sin tildes, en mayúsculas)
    # al nombre real usado en self.modes
    _PHYSICAL_BUTTON_TO_MODE = {
        "CLASICO": "Clásico",
        "INVERTIDO": "Invertido",
        "FLOWMODORO": "Flowmodoro",
        "CUSTOM": "Método Personalizado",
        "METODO PERSONALIZADO": "Método Personalizado",
        "MÉTODO PERSONALIZADO": "Método Personalizado",
    }

    def _on_physical_mode_button(self, button_name: str):
        """Se llama cuando el Arduino reporta MODE:<nombre> al
        presionar uno de los 4 botones físicos de selección de modo."""
        mode_name = self._PHYSICAL_BUTTON_TO_MODE.get(button_name)
        if mode_name is None:
            self.sensor_label.text = f"⚠ Botón desconocido: {button_name}"
            self.sensor_label.color = (1, 0.3, 0.3, 1)
            return

        self._select_mode(mode_name)
        self.sensor_label.text = f"Modo seleccionado: {mode_name}"
        self.sensor_label.color = C_REST

    # ─── Callbacks de sesión ────────────────────────────────

    def _clock_tick(self, dt):
        if self._started:
            self.session.tick()

    def _on_tick(self, remaining: int):
        def update(_):
            self.timer_label.text = PomodoroSession.format_time(remaining)
            self.progress.value = self.session.get_progress() * 100
        Clock.schedule_once(update)

    def _on_state_change(self, state: str):
        def update(_):
            colors = {"WORK": C_WORK, "REST": C_REST, "PAUSED": C_PAUSE}
            labels = {"WORK": "TRABAJANDO", "REST": "DESCANSANDO",
                      "PAUSED": "PAUSADO"}
            btn_texts = {"WORK": "Pausar", "REST": "Pausar",
                         "PAUSED": "Reanudar"}

            color = colors.get(state, C_MUTED)
            self.state_label.text = labels.get(state, state)
            self.state_label.color = color
            self.pause_btn.text = btn_texts.get(state, "Pausar")
            self.pause_btn.background_color = color

            cmd = self.session.mode.get_led_command(state)
            self.bt.send(cmd)

            if state == "PAUSED":
                self.bt.send("BUZZ:PAUSE\n")

            r, g, b, _ = color
            self.led_status.text = (f"NeoPixel: RGB({int(r*255)}, "
                                    f"{int(g*255)}, {int(b*255)}) · "
                                    f"brillo {self.neopixel_brightness}")
        Clock.schedule_once(update)

    def _on_resume(self):
        """Se llama solo cuando se reanuda desde PAUSADO (no en otros
        cambios de estado). El color/animación se restaura automáticamente
        porque _on_state_change vuelve a enviar el comando del estado
        (WORK o REST) en el que estaba la sesión antes de pausar."""
        self.bt.send("BUZZ:RESUME\n")

    def _on_session_end(self, phase: str):
        def update(_):
            self.sessions_label.text = (
                f"Sesiones completadas: {self.session.sessions_completed}")
            # Sonido diferente según qué fase terminó
            if phase == "WORK":
                self.bt.send("BUZZ:WORK_END\n")   # 3 beeps rápidos
            elif phase == "REST":
                self.bt.send("BUZZ:REST_END\n")   # 2 beeps largos
        Clock.schedule_once(update)

    # ─── Bluetooth ──────────────────────────────────────────

    def _on_bt_data(self, data: str):
        def update(_):
            self.sound_handler.handle(data)
            if data == "PONG":
                self.sensor_label.text = "Conexión verificada (PONG recibido)"
                self.sensor_label.color = C_REST
            elif data.startswith("MODE:"):
                button_name = data.split(":", 1)[1]
                print(f"[DEBUG] MODE recibido: '{button_name}'")
                try:
                    self._on_physical_mode_button(button_name)
                except Exception as e:
                    print(f"[DEBUG] Excepción en _on_physical_mode_button: {e}")
                    self.sensor_label.text = f"⚠ Error en MODE: {e}"
                    self.sensor_label.color = (1, 0.3, 0.3, 1)
            elif data.startswith("CLAP:"):
                pass  # feedback lo maneja _on_clap
            elif data.startswith("LED_OK"):
                self.sensor_label.text = "NeoPixel actualizado correctamente"
                self.sensor_label.color = C_REST
            elif data.startswith("BRIGHT_OK"):
                self.sensor_label.text = "Brillo de NeoPixel actualizado"
                self.sensor_label.color = C_REST
            elif data.startswith("LDR:"):
                try:
                    lux = int(data.split(":")[1])
                    pct = round((lux / 1023) * 100)
                    if pct < 20:
                        desc = "Muy oscuro"
                        col  = (0.4, 0.4, 0.5, 1)
                    elif pct < 50:
                        desc = "Poca luz"
                        col  = C_MUTED
                    else:
                        desc = "Buena luz"
                        col  = C_REST
                    self.ldr_label.text  = f"{desc} ({pct}%)"
                    self.ldr_label.color = col
                except (IndexError, ValueError):
                    pass
            elif data.startswith("ERR"):
                self.sensor_label.text = f"⚠ {data}"
                self.sensor_label.color = (1, 0.3, 0.3, 1)
            elif data == "BUZZ_DONE":
                self.buzzer_label.text = "Buzzer: sonido completado"
                self.buzzer_label.color = C_WORK
            elif data == "BUZZ_START_DONE":
                self.buzzer_label.text = "Buzzer: inicio de sesión"
                self.buzzer_label.color = C_REST
            elif data == "BUZZ_WORK_DONE":
                self.buzzer_label.text = "Buzzer: fin de trabajo"
                self.buzzer_label.color = C_WORK
            elif data == "BUZZ_REST_DONE":
                self.buzzer_label.text = "Buzzer: fin de descanso"
                self.buzzer_label.color = C_REST
            elif data == "BUZZ_PAUSE_DONE":
                self.buzzer_label.text = "Buzzer: pausa"
                self.buzzer_label.color = C_PAUSE
            elif data == "BUZZ_RESUME_DONE":
                self.buzzer_label.text = "Buzzer: reanudado"
                self.buzzer_label.color = C_REST
            else:
                self.sensor_label.text = f"Arduino → {data}"
                self.sensor_label.color = C_MUTED
        Clock.schedule_once(update)

    def _on_clap(self, count: int, action: str):
        """Feedback visual en la UI cuando se detecta una palmada."""
        messages = {
            (1, "pause"):  ("1 aplauso → Pausado",   C_PAUSE),
            (1, "resume"): ("1 aplauso → Reanudado",  C_REST),
            (2, "extend"): ("2 aplausos → +5 min",     C_WORK),
        }
        text, color = messages.get((count, action), (f"CLAP:{count}", C_MUTED))

        def update(_):
            self.sensor_label.text = text
            self.sensor_label.color = color
            # Volver al estado neutro después de 3 segundos
            def reset(_):
                self.sensor_label.text = "🎤 KY-037: escuchando palmadas..."
                self.sensor_label.color = C_MUTED
            Clock.schedule_once(reset, 3)
        Clock.schedule_once(update)

    def _open_bt_popup(self):
        content = BoxLayout(orientation="vertical", padding=12, spacing=8)
        ports = self.bt.scan_ports()
        if not ports:
            ports = ["No se encontraron puertos"]

        content.add_widget(make_label("Selecciona el puerto HC-05:",
                                      size=13, color=C_TEXT))
        for port in ports:
            btn = Button(text=port, size_hint_y=None, height=38,
                         background_color=BG_CARD2)
            btn.bind(on_press=lambda b, p=port: self._connect_bt(p, popup))
            content.add_widget(btn)

        popup = Popup(title="Conectar Bluetooth", content=content,
                      size_hint=(0.85, 0.6))
        popup.open()

    def _connect_bt(self, port: str, popup: Popup):
        popup.dismiss()
        ok = self.bt.connect(port)
        def update(_):
            if ok:
                self.bt_label.text = f"✓ {port}"
                self.bt_label.color = C_REST
                self.bt.send("PING\n")
                self.bt.send("BUZZ:START\n")   # beep de bienvenida
                # Sincronizar el brillo del NeoPixel con el Arduino
                self.bt.send(f"BRIGHT:{self.neopixel_brightness}\n")
                # Apagar el NeoPixel hasta presionar "Iniciar Pomodoro"
                self.bt.send("LED:0,0,0\n")
                self.sensor_label.text = "PING enviado — esperando PONG..."
                self.buzzer_label.text = "Buzzer: señal de inicio enviada"
                self.buzzer_label.color = C_REST
            else:
                self.bt_label.text = "✗ Error al conectar"
                self.bt_label.color = (1, 0.3, 0.3, 1)
                self.sensor_label.text = "Verifica que el HC-05 esté emparejado"
        Clock.schedule_once(update)

    # ─── Config personalizada ───────────────────────────────

    def _open_custom_popup(self):
        scroll = ScrollView(size_hint=(1, 1))
        content = BoxLayout(orientation="vertical", padding=(16, 12),
                            spacing=14, size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        # Fondo del contenido igual al de la app
        with content.canvas.before:
            Color(*BG_DARK)
            bg_rect = Rectangle(size=content.size, pos=content.pos)
        content.bind(size=lambda w, s: setattr(bg_rect, "size", s))
        content.bind(pos=lambda w, p: setattr(bg_rect, "pos", p))

        scroll.add_widget(content)

        # ── Título ──
        content.add_widget(make_label("Configuración", size=15,
                                      bold=True, color=C_TEXT))

        # ── Helper para filas de slider ──
        def make_slider_row(label_text, min_val, max_val, default):
            row = BoxLayout(orientation="vertical", size_hint_y=None,
                            height=64, spacing=2)
            row.add_widget(make_label(label_text, size=12, color=C_MUTED))
            inner = BoxLayout(size_hint_y=None, height=38, spacing=10)
            slider = Slider(min=min_val, max=max_val, value=default,
                            size_hint_x=1)
            val_lbl = make_label(str(int(default)), size=13, color=C_TEXT,
                                 halign="right")
            val_lbl.size_hint_x = None
            val_lbl.width = 36
            slider.bind(value=lambda s, v, lbl=val_lbl: setattr(
                lbl, "text", str(int(v))))
            inner.add_widget(slider)
            inner.add_widget(val_lbl)
            row.add_widget(inner)
            return row, slider, val_lbl

        work_row, self._work_slider, self._work_val = make_slider_row(
            "Tiempo de trabajo (min)", 1, 90, 25)
        rest_row, self._rest_slider, self._rest_val = make_slider_row(
            "Tiempo de descanso (min)", 1, 60, 5)
        bright_row, self._bright_slider, self._bright_val = make_slider_row(
            "Brillo NeoPixel (0-255)", 0, 255, self.neopixel_brightness)

        content.add_widget(work_row)
        content.add_widget(rest_row)
        content.add_widget(bright_row)

        # ── Separador visual ──
        sep = BoxLayout(size_hint_y=None, height=1)
        with sep.canvas:
            Color(*BG_CARD2)
            sep_rect = Rectangle(size=sep.size, pos=sep.pos)
        sep.bind(size=lambda w, s: setattr(sep_rect, "size", s))
        sep.bind(pos=lambda w, p: setattr(sep_rect, "pos", p))
        content.add_widget(sep)

        # ── Color picker ──
        content.add_widget(make_label("Color de la luz (modo trabajo)",
                                      size=12, color=C_MUTED))
        current = self.modes["Método Personalizado"].led_color
        self._color_picker = ColorPicker(
            color=[current[0] / 255, current[1] / 255, current[2] / 255, 1],
            size_hint_y=None, height=300)
        content.add_widget(self._color_picker)

        # ── Botón guardar — mismo estilo que CTA primario ──
        save_btn = Button(
            text="Guardar y aplicar",
            background_normal="",
            background_color=C_WORK,
            font_size=15,
            bold=True,
            color=(1, 1, 1, 1),
            size_hint_y=None,
            height=50,
        )

        def save(_):
            w = int(self._work_slider.value) * 60
            rest_secs = int(self._rest_slider.value) * 60
            cr, cg, cb, _ = self._color_picker.color
            work_color = (int(cr * 255), int(cg * 255), int(cb * 255))
            self.modes["Método Personalizado"] = StudyMode(
                "Método Personalizado", w, rest_secs, work_color,
                "Método Personalizado",
                rest_color=(0, 180, 80),
            )
            self._select_mode("Método Personalizado")
            self.neopixel_brightness = int(self._bright_slider.value)
            self.bt.send(f"BRIGHT:{self.neopixel_brightness}\n")
            popup.dismiss()

        save_btn.bind(on_press=save)
        content.add_widget(save_btn)

        popup = Popup(
            title=" Método Personalizado",
            content=scroll,
            size_hint=(0.95, 0.92),
            background="",
            background_color=(*BG_DARK[:3], 1),
            title_color=C_TEXT,
            title_size=15,
            separator_color=(*BG_CARD2[:3], 1),
        )
        popup.open()

    # ─── Helpers ────────────────────────────────────────────

    def _update_bg(self, instance, value):
        self._bg_rect.size = instance.size
        self._bg_rect.pos = instance.pos

    def on_stop(self):
        self.bt.disconnect()


if __name__ == "__main__":
    PomodoroApp().run()