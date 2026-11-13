import asyncio
import threading
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.core.window import Window
from kivymd.app import MDApp
from bleak import BleakScanner, BleakClient
from kivy.utils import platform

# Solicitar permisos si estamos en Android
if platform == 'android':
    from android.permissions import request_permissions, Permission
    request_permissions([
        Permission.BLUETOOTH_SCAN,
        Permission.BLUETOOTH_CONNECT,
        Permission.ACCESS_FINE_LOCATION,
        Permission.ACCESS_COARSE_LOCATION
    ])

# Ajustar tamaño de ventana para simular un celular en la PC
Window.size = (400, 750)

# Configuración BLE (Tus UUIDs)
DEVICE_NAME = "VitaSense-XIAO"
TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E" # XIAO a Python
RX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E" # Python a XIAO

KV = '''
MDScreen:
    md_bg_color: 0.95, 0.96, 0.98, 1
    
    MDBoxLayout:
        orientation: 'vertical'
        
        # Barra superior
        MDTopAppBar:
            title: "VitaSense"
            elevation: 2
            left_action_items: [["medical-bag", lambda x: None]]
            right_action_items: [["bluetooth", lambda x: app.conectar_ble()]]
            md_bg_color: 1, 1, 1, 1
            specific_text_color: 0.1, 0.1, 0.3, 1
            
        MDLabel:
            id: status_label
            text: "Estado: Desconectado"
            halign: "center"
            size_hint_y: None
            height: "40dp"
            theme_text_color: "Secondary"
            font_style: "Caption"

        # Navegación inferior
        MDBottomNavigation:
            panel_color: 1, 1, 1, 1
            selected_color_background: 0, 0, 0, .1
            text_color_active: 0.2, 0.5, 0.8, 1
            
            # --- PESTAÑA 1: SENSORES (Tarjetas) ---
            MDBottomNavigationItem:
                name: 'screen_sensores'
                text: 'Sensor'
                icon: 'view-dashboard'
                
                MDGridLayout:
                    cols: 2
                    padding: "15dp"
                    spacing: "15dp"
                    
                    # Tarjeta 1: Batería
                    MDCard:
                        orientation: "vertical"
                        padding: "10dp"
                        radius: [15, 15, 15, 15]
                        md_bg_color: 1, 1, 1, 1
                        elevation: 1
                        MDIcon:
                            icon: "battery-charging-60"
                            theme_text_color: "Custom"
                            text_color: 0.2, 0.7, 0.3, 1
                        MDLabel:
                            text: "Batería"
                            font_style: "Caption"
                            theme_text_color: "Secondary"
                        MDLabel:
                            id: bat_label
                            text: "-- V"
                            font_style: "H5"
                            bold: True
                            
                    # Tarjeta 2: Botón Pánico
                    MDCard:
                        orientation: "vertical"
                        padding: "10dp"
                        radius: [15, 15, 15, 15]
                        md_bg_color: 1, 1, 1, 1
                        elevation: 1
                        MDIcon:
                            icon: "alert-circle-outline"
                            theme_text_color: "Custom"
                            text_color: 0.8, 0.2, 0.2, 1
                        MDLabel:
                            text: "Botón Pánico"
                            font_style: "Caption"
                            theme_text_color: "Secondary"
                        MDLabel:
                            id: btn_label
                            text: "En reposo"
                            font_style: "Subtitle2"
                            bold: True
                            
                    # Tarjeta 3: Señal / Módem
                    MDCard:
                        orientation: "vertical"
                        padding: "10dp"
                        radius: [15, 15, 15, 15]
                        md_bg_color: 1, 1, 1, 1
                        elevation: 1
                        MDIcon:
                            icon: "signal-cellular-3"
                            theme_text_color: "Custom"
                            text_color: 0.2, 0.5, 0.8, 1
                        MDLabel:
                            text: "Red Módem"
                            font_style: "Caption"
                            theme_text_color: "Secondary"
                        MDLabel:
                            id: red_label
                            text: "Buscando..."
                            font_style: "Subtitle2"
                            bold: True
                            
                    # Tarjeta 4: Comandos Rápidos
                    MDCard:
                        orientation: "vertical"
                        padding: "10dp"
                        radius: [15, 15, 15, 15]
                        md_bg_color: 1, 1, 1, 1
                        elevation: 1
                        MDIcon:
                            icon: "vibrate"
                        MDLabel:
                            text: "Motor / Prueba"
                            font_style: "Caption"
                            theme_text_color: "Secondary"
                        MDRaisedButton:
                            text: "Test"
                            md_bg_color: 0.8, 0.9, 1, 1
                            text_color: 0.1, 0.3, 0.5, 1
                            elevation: 0
                            on_release: app.enviar_comando("estado")

            # --- PESTAÑA 2: HISTORIAL (Terminal cruda) ---
            MDBottomNavigationItem:
                name: 'screen_historial'
                text: 'Historial'
                icon: 'history'
                
                ScrollView:
                    MDLabel:
                        id: terminal_log
                        text: "Esperando datos..."
                        size_hint_y: None
                        height: self.texture_size[1]
                        padding: "10dp", "10dp"
                        theme_text_color: "Secondary"
                        font_style: "Caption"

            # --- PESTAÑA 3: SOS Y COMANDOS ---
            MDBottomNavigationItem:
                name: 'screen_sos'
                text: 'Comandos'
                icon: 'cellphone-message'
                
                MDBoxLayout:
                    orientation: 'vertical'
                    padding: "20dp"
                    spacing: "15dp"
                    MDTextField:
                        id: cmd_input
                        hint_text: "Comando (ej: llamar, alerta)"
                        mode: "rectangle"
                    MDRaisedButton:
                        text: "ENVIAR COMANDO"
                        pos_hint: {"center_x": .5}
                        md_bg_color: 0.2, 0.5, 0.8, 1
                        on_release: app.enviar_comando(cmd_input.text)
'''

class VitaSenseApp(MDApp):
    def build(self):
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "Blue"
        self.ble_client = None
        self.loop = asyncio.new_event_loop()
        return Builder.load_string(KV)

    def log_terminal(self, texto):
        actual = self.root.ids.terminal_log.text
        self.root.ids.terminal_log.text = f"{actual}\n{texto}"

    def interpretar_datos(self, texto):
        texto = texto.upper()
        if "BATERIA:" in texto:
            try:
                voltaje = texto.split("BATERIA:")[1].strip()
                self.root.ids.bat_label.text = voltaje
            except:
                pass
        
        if "BOTON PRESIONADO" in texto or "ALERTA" in texto:
            self.root.ids.btn_label.text = "¡PRESIONADO!"
            self.root.ids.btn_label.theme_text_color = "Error"
            Clock.schedule_once(lambda dt: self.reset_boton(), 5)

        if "RED: REGISTRADO" in texto:
            self.root.ids.red_label.text = "Conectado"
        elif "SEÑAL: CSQ" in texto:
            self.root.ids.red_label.text = "Buena señal"

    def reset_boton(self):
        self.root.ids.btn_label.text = "En reposo"
        self.root.ids.btn_label.theme_text_color = "Primary"

    def notification_handler(self, sender, data):
        texto = data.decode('utf-8').strip()
        Clock.schedule_once(lambda dt: self.log_terminal(f"XIAO: {texto}"))
        Clock.schedule_once(lambda dt: self.interpretar_datos(texto))

    async def ble_task(self):
        Clock.schedule_once(lambda dt: self.actualizar_estado("Buscando XIAO..."))
        dispositivos = await BleakScanner.discover()
        target_device = next((d for d in dispositivos if d.name and DEVICE_NAME in d.name), None)

        if not target_device:
            Clock.schedule_once(lambda dt: self.actualizar_estado("Error: XIAO no encontrado"))
            return

        try:
            self.ble_client = BleakClient(target_device.address)
            await self.ble_client.connect()
            Clock.schedule_once(lambda dt: self.actualizar_estado("¡CONECTADO!"))
            await self.ble_client.start_notify(TX_CHAR_UUID, self.notification_handler)
            
            while self.ble_client.is_connected:
                await asyncio.sleep(1)
                
        except Exception as e:
            Clock.schedule_once(lambda dt: self.actualizar_estado(f"Desconectado"))

    def actualizar_estado(self, estado):
        self.root.ids.status_label.text = f"Estado: {estado}"

    def start_ble_thread(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.ble_task())

    def conectar_ble(self):
        if self.ble_client and self.ble_client.is_connected:
            return
        threading.Thread(target=self.start_ble_thread, daemon=True).start()

    def enviar_comando(self, comando):
        if comando and self.ble_client and self.ble_client.is_connected:
            comando_final = comando.strip() + "\\n"
            asyncio.run_coroutine_threadsafe(
                self.ble_client.write_gatt_char(RX_CHAR_UUID, comando_final.encode('utf-8')), 
                self.loop
            )
            self.log_terminal(f"Tú: {comando}")
            self.root.ids.cmd_input.text = ""

if __name__ == '__main__':
    VitaSenseApp().run()
