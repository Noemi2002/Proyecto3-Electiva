from kivy.core.window import Window
Window.size = (360, 640)
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.graphics import Color, Rectangle

# -------------------------
# Pantalla de Inicio
# -------------------------
class InicioScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        layout = FloatLayout()

        # Fondo amarillo
        with layout.canvas.before:
            Color(1, 0.75, 0, 1)
            self.rect = Rectangle(
                size=layout.size,
                pos=layout.pos
            )

        layout.bind(size=self.actualizar_fondo)
        layout.bind(pos=self.actualizar_fondo)

        # GIF de tomates (fondo animado)
        gif_tomates = Image(
            source="Tomates flotando.gif",
            anim_delay=0.05,
            size_hint=(1, 1),
            allow_stretch=True,
            keep_ratio=False
        )
        # Logo
        logo = Image(
            source="logo.png",
            size_hint=(0.8, 0.5),
            pos_hint={"center_x": 0.5, "center_y": 0.55}
        )

        # Botón
        boton = Button(
            text="INICIA TU MODO",
            size_hint=(0.7, 0.08),
            pos_hint={"center_x": 0.5, "center_y": 0.45},
            background_color=(255, 0, 0, 1)
        )

        boton.bind(on_press=self.ir_a_pomodoro)
        layout.add_widget(gif_tomates)
        layout.add_widget(logo)
        layout.add_widget(boton)

        self.add_widget(layout)

    def actualizar_fondo(self, instance, value):
        self.rect.size = instance.size
        self.rect.pos = instance.pos

    def ir_a_pomodoro(self, instance):
        self.manager.current = "pomodoro"


# -------------------------
# Pantalla Pomodoro
# -------------------------
class PomodoroScreen(Screen):
    pass

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        layout = FloatLayout()

        texto = Label(
            text="Aquí va Pomodoro App",
            font_size="24sp",
            pos_hint={"center_x": 0.5, "center_y": 0.5}
        )

        layout.add_widget(texto)

        self.add_widget(layout)


# -------------------------
# App Principal
# -------------------------
class PomodoroApp(App):

    def build(self):

        sm = ScreenManager()

        sm.add_widget(InicioScreen(name="inicio"))
        sm.add_widget(PomodoroScreen(name="pomodoro"))

        return sm


if __name__ == "__main__":
    PomodoroApp().run()