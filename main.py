import os
import json
import sqlite3
import base64
import threading
from datetime import datetime

# ==============================================================================
# MOTOR Y SERVIDOR BACKEND (NBO-A / SALON STUDIO PRO)
# ==============================================================================
try:
    import cv2
    import numpy as np
    from flask import Flask, request, jsonify
    from flask_cors import CORS
    HAS_SERVER_DEPS = True
except ImportError:
    HAS_SERVER_DEPS = False

app_backend = Flask(__name__) if HAS_SERVER_DEPS else None
if app_backend:
    CORS(app_backend)

def base64_a_cv2(b64_string):
    if ',' in b64_string:
        b64_string = b64_string.split(',')[1]
    datos = base64.b64decode(b64_string)
    np_arr = np.frombuffer(datos, np.uint8)
    return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

def cv2_a_base64(img_cv2):
    _, buffer = cv2.imencode('.jpg', img_cv2)
    b64_bytes = base64.b64encode(buffer)
    return f"data:image/jpeg;base64,{b64_bytes.decode('utf-8')}"

if app_backend:
    @app_backend.route('/api/validar_licencia', methods=['POST'])
    def api_validar_licencia():
        data = request.json or {}
        lic = data.get("licencia", "")
        if lic:
            return jsonify({"estatus": "ok", "mensaje": "Licencia activa correctamente"})
        return jsonify({"estatus": "error", "mensaje": "Clave de licencia inválida"}), 400

    @app_backend.route('/api/procesar_rostro', methods=['POST'])
    def api_procesar_rostro():
        data = request.json or {}
        img_b64 = data.get("imagen_base64", "")
        brillo = float(data.get("brillo", 100)) / 100.0
        contraste = float(data.get("contraste", 100)) / 100.0
        suavizado = int(data.get("suavizado", 0))
        modo_color = data.get("modo_color", "normal")

        if not img_b64:
            return jsonify({"estatus": "error", "mensaje": "No se recibió imagen"}), 400

        img = base64_a_cv2(img_b64)
        if img is None:
            return jsonify({"estatus": "error", "mensaje": "Error al decodificar la imagen"}), 400

        # Ajuste de Brillo y Contraste
        img = cv2.convertScaleAbs(img, alpha=contraste, beta=(brillo - 1.0) * 50)

        # Suavizado de Piel (Filtro Bilateral)
        if suavizado > 0:
            d = int(suavizado / 5) | 1
            img = cv2.bilateralFilter(img, d, 75, 75)

        # Modos de Color / Filtros
        if modo_color == "gris":
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        elif modo_color == "rosa":
            b, g, r = cv2.split(img)
            r = cv2.add(r, 30)
            img = cv2.merge([b, g, r])

        res_b64 = cv2_a_base64(img)
        return jsonify({"estatus": "ok", "imagen_procesada": res_b64})

    @app_backend.route('/api/editar_rasgos', methods=['POST'])
    def api_editar_rasgos():
        data = request.json or {}
        img_b64 = data.get("imagen_base64", "")
        zona = data.get("zona", "Labios")
        cx = int(data.get("coord_x", 0))
        cy = int(data.get("coord_y", 0))
        hex_color = data.get("color", "#ff0055")

        if not img_b64:
            return jsonify({"estatus": "error", "mensaje": "No se recibió imagen"}), 400

        img = base64_a_cv2(img_b64)
        if img is None:
            return jsonify({"estatus": "error", "mensaje": "Error al decodificar la imagen"}), 400

        # Conversión de Hex a BGR
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        
        # Aplicación de Capa de Color Zonal por Distancia
        h, w, _ = img.shape
        if 0 <= cx < w and 0 <= cy < h:
            radio = int(min(h, w) * 0.08)
            mascara = np.zeros((h, w), dtype=np.uint8)
            cv2.circle(mascara, (cx, cy), radio, 255, -1)
            mascara = cv2.GaussianBlur(mascara, (21, 21), 0)

            capa_color = np.full_like(img, (b, g, r), dtype=np.uint8)
            alpha = (mascara.astype(float) / 255.0) * 0.4
            alpha = np.repeat(alpha[:, :, np.newaxis], 3, axis=2)

            img = (img.astype(float) * (1.0 - alpha) + capa_color.astype(float) * alpha).astype(np.uint8)

        res_b64 = cv2_a_base64(img)
        return jsonify({"estatus": "ok", "imagen_resultante": res_b64})

def iniciar_servidor_local():
    if HAS_SERVER_DEPS and app_backend:
        app_backend.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

# Iniciar servidor backend en un hilo independiente para ejecución local
threading.Thread(target=iniciar_servidor_local, daemon=True).start()

# ==============================================================================
# APLICACIÓN CLIENTE KIVY
# ==============================================================================

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.modalview import ModalView
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.scatterlayout import ScatterLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.slider import Slider
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.image import Image
from kivy.uix.camera import Camera
from kivy.core.window import Window
from kivy.properties import ListProperty, BooleanProperty, StringProperty, NumericProperty
from kivy.cache import Cache
from kivy.metrics import dp
from kivy.utils import platform
from kivy.clock import Clock
from kivy.network.urlrequest import UrlRequest

Window.softinput_mode = 'below_target'

URL_SERVIDOR_DEFAULT = "https://servidor-salon-backend-1.onrender.com"

def obtener_ruta_archivos():
    if platform == 'android':
        ruta_dcim = '/storage/emulated/0/DCIM'
        if os.path.exists(ruta_dcim):
            return ruta_dcim
        ruta_almacenamiento = '/storage/emulated/0'
        if os.path.exists(ruta_almacenamiento):
            return ruta_almacenamiento
    return os.path.expanduser('~')

def solicitar_permisos_android(dt=None):
    if platform == 'android':
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([
                Permission.CAMERA,
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.READ_EXTERNAL_STORAGE,
                "android.permission.READ_MEDIA_IMAGES"
            ])
        except Exception as e:
            print(f"Error solicitando permisos: {e}")

def obtener_camaras_disponibles():
    camaras = []
    if platform == 'android':
        try:
            from jnius import autoclass
            CameraManager = autoclass('android.hardware.camera2.CameraManager')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            context = PythonActivity.mActivity
            manager = context.getSystemService(context.CAMERA_SERVICE)
            id_list = manager.getCameraIdList()
            for i in range(len(id_list)):
                camaras.append(f"Cámara {i}")
        except Exception:
            camaras = ["Cámara 0 (Trasera)", "Cámara 1 (Frontal)"]
    else:
        camaras = ["Cámara 0 (Trasera)", "Cámara 1 (Frontal)"]
    return camaras if camaras else ["Cámara 0"]

DB_NAME = 'salon.db'

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('PRAGMA journal_mode=WAL;')
        
        # Servicios
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS servicios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                categoria TEXT,
                precio REAL NOT NULL,
                foto_path TEXT
            )
        ''')
        
        # Estilistas / Colaboradores
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS estilistas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                porcentaje_comision REAL DEFAULT 50.0
            )
        ''')
        
        # Ventas ampliadas con Método de Pago
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                total REAL NOT NULL,
                metodo_pago TEXT DEFAULT 'Efectivo'
            )
        ''')
        
        # Detalle de Ventas con Estilista
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detalle_ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venta_id INTEGER,
                servicio_nombre TEXT NOT NULL,
                estilista_nombre TEXT DEFAULT 'General',
                cantidad INTEGER NOT NULL,
                precio_unitario REAL NOT NULL,
                subtotal REAL NOT NULL,
                FOREIGN KEY (venta_id) REFERENCES ventas (id)
            )
        ''')
        
        # Movimientos de Caja / Egresos / Gastos Fijos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS movimientos_caja (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                tipo TEXT NOT NULL, -- 'Ingreso' o 'Egreso'
                concepto TEXT NOT NULL,
                monto REAL NOT NULL
            )
        ''')
        
        # Insertar estilista general por defecto si no existen
        cursor.execute("SELECT COUNT(*) FROM estilistas")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO estilistas (nombre, porcentaje_comision) VALUES ('General', 50.0)")
            
        conn.commit()

init_db()

class CapaVirtual(ScatterLayout):
    def __init__(self, foto_path, **kwargs):
        super().__init__(**kwargs)
        self.do_rotation = True
        self.do_scale = True
        self.do_translation = True
        self.size_hint = (None, None)
        self.size = (dp(160), dp(160))
        img = Image(
            source=foto_path,
            allow_stretch=True,
            keep_ratio=True,
            size_hint=(1, 1),
            pos=(0, 0)
        )
        self.add_widget(img)


KV = '''
<ScreenLicencia>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(15)
        canvas.before:
            Color:
                rgba: app.bg_color
            Rectangle:
                pos: self.pos
                size: self.size

        Widget:
            size_hint_y: 0.1

        BoxLayout:
            orientation: 'vertical'
            padding: dp(16)
            spacing: dp(12)
            size_hint_y: None
            height: dp(320)
            canvas.before:
                Color:
                    rgba: app.card_color
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [dp(12)]

            Label:
                text: "🔐 ACTIVACIÓN DE LICENCIA"
                font_size: '16sp'
                bold: True
                color: app.accent_color
                size_hint_y: None
                height: dp(30)

            Label:
                text: "Para utilizar el sistema de estética y retoque NBO-A, ingresa la clave asignada en tu compra de Mercado Libre:"
                font_size: '11sp'
                color: app.text_sec_color
                halign: 'center'
                valign: 'middle'
                text_size: self.width, None
                size_hint_y: None
                height: dp(45)

            TextInput:
                id: in_licencia_key
                hint_text: "Ej. GEN-2026-09-30-A1B2C3"
                multiline: False
                size_hint_y: None
                height: dp(45)
                font_size: '13sp'
                halign: 'center'

            Button:
                id: btn_validar
                text: "VERIFICAR Y ACTIVAR ➔"
                font_size: '13sp'
                bold: True
                size_hint_y: None
                height: dp(45)
                background_normal: ''
                background_color: app.accent_color
                color: 1, 1, 1, 1
                on_release: root.validar_licencia_servidor()

            Label:
                id: lbl_estado_licencia
                text: ""
                font_size: '11sp'
                bold: True
                color: 0.9, 0.3, 0.3, 1
                halign: 'center'
                size_hint_y: None
                height: dp(35)

        Widget:
            size_hint_y: 0.1


<ScreenConfig>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(12)
        spacing: dp(10)
        canvas.before:
            Color:
                rgba: app.bg_color
            Rectangle:
                pos: self.pos
                size: self.size

        # Encabezado
        BoxLayout:
            size_hint_y: None
            height: dp(50)
            padding: dp(8)
            spacing: dp(6)
            canvas.before:
                Color:
                    rgba: app.card_color
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [dp(8)]

            Label:
                text: "⚙️ CONFIGURACIÓN"
                font_size: '14sp'
                bold: True
                color: app.text_main_color

            Button:
                text: "📊 REPORTES"
                size_hint_x: 0.32
                font_size: '10sp'
                bold: True
                background_normal: ''
                background_color: 0.13, 0.65, 0.4, 1
                color: 1, 1, 1, 1
                on_release: root.mostrar_modal_reporte_diario()

            Button:
                text: "🎨 TEMAS"
                size_hint_x: 0.28
                font_size: '10sp'
                bold: True
                background_normal: ''
                background_color: app.accent_color
                color: 1, 1, 1, 1
                on_release: app.abrir_catalogo_temas()

        ScrollView:
            BoxLayout:
                orientation: 'vertical'
                size_hint_y: None
                height: self.minimum_height
                spacing: dp(12)
                padding: [0, dp(5)]

                # Información del Negocio y Servidor
                BoxLayout:
                    orientation: 'vertical'
                    size_hint_y: None
                    height: dp(140)
                    padding: dp(10)
                    spacing: dp(6)
                    canvas.before:
                        Color:
                            rgba: app.card_color
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(10)]

                    Label:
                        text: "INFORMACIÓN DEL NEGOCIO Y MOTOR NBO-A"
                        font_size: '11sp'
                        bold: True
                        color: app.accent_color
                        size_hint_y: None
                        height: dp(18)

                    TextInput:
                        id: in_nombre_negocio
                        hint_text: "Nombre de la Estética / Estudio"
                        multiline: False
                        size_hint_y: None
                        height: dp(38)
                        text: app.nombre_negocio
                        on_text: app.nombre_negocio = self.text

                    TextInput:
                        id: in_url_servidor
                        hint_text: "URL del Servidor NBO-A"
                        multiline: False
                        size_hint_y: None
                        height: dp(38)
                        text: app.url_servidor
                        on_text: app.url_servidor = self.text

                # Formulario Alta de Estilistas
                Label:
                    text: "REGISTRAR ESTILISTA / COLABORADOR"
                    font_size: '13sp'
                    bold: True
                    color: app.accent_color
                    size_hint_y: None
                    height: dp(20)

                BoxLayout:
                    orientation: 'vertical'
                    size_hint_y: None
                    height: dp(140)
                    padding: dp(10)
                    spacing: dp(6)
                    canvas.before:
                        Color:
                            rgba: app.card_color
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(10)]

                    TextInput:
                        id: in_nombre_estilista
                        hint_text: "Nombre del Estilista"
                        multiline: False
                        size_hint_y: None
                        height: dp(38)

                    TextInput:
                        id: in_comision_estilista
                        hint_text: "Comisión % (Ej: 50)"
                        input_filter: 'float'
                        multiline: False
                        size_hint_y: None
                        height: dp(38)

                    Button:
                        text: "👤 GUARDAR ESTILISTA"
                        font_size: '11sp'
                        bold: True
                        size_hint_y: None
                        height: dp(38)
                        background_normal: ''
                        background_color: 0.2, 0.5, 0.8, 1
                        color: 1, 1, 1, 1
                        on_release: root.guardar_estilista_db()

                # Formulario Alta de Servicio
                Label:
                    text: "REGISTRAR SERVICIO / CAPA AL CATÁLOGO"
                    font_size: '13sp'
                    bold: True
                    color: app.accent_color
                    size_hint_y: None
                    height: dp(20)

                BoxLayout:
                    orientation: 'vertical'
                    size_hint_y: None
                    height: dp(410)
                    padding: dp(12)
                    spacing: dp(8)
                    canvas.before:
                        Color:
                            rgba: app.card_color
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(10)]

                    TextInput:
                        id: in_nombre_servicio
                        hint_text: "Nombre (ej. Peinado Bob / Maquillaje Rosa)"
                        multiline: False
                        size_hint_y: None
                        height: dp(40)

                    Spinner:
                        id: in_cat_servicio
                        text: "Categoría: Cortes"
                        values: ["Cortes", "Tintes", "Maquillaje", "Peinados", "Manicura", "Tratamientos"]
                        size_hint_y: None
                        height: dp(40)

                    TextInput:
                        id: in_precio_servicio
                        hint_text: "Precio $"
                        input_filter: 'float'
                        multiline: False
                        size_hint_y: None
                        height: dp(40)

                    # Selector de Cámara
                    BoxLayout:
                        size_hint_y: None
                        height: dp(35)
                        spacing: dp(6)

                        Label:
                            text: "📷 Cámara:"
                            font_size: '11sp'
                            color: app.text_main_color
                            size_hint_x: 0.35

                        Spinner:
                            id: sp_camara_config
                            text: app.camaras_disponibles[0] if app.camaras_disponibles else "Cámara 0"
                            values: app.camaras_disponibles
                            size_hint_x: 0.65
                            font_size: '11sp'
                            on_text: root.cambiar_camara_seleccionada(self.text)

                    # Vista Previa Imagen / Cámara
                    BoxLayout:
                        id: box_preview_config
                        orientation: 'vertical'
                        size_hint_y: None
                        height: dp(100)
                        padding: dp(4)
                        canvas.before:
                            Color:
                                rgba: [0, 0, 0, 0.25]
                            RoundedRectangle:
                                pos: self.pos
                                size: self.size
                                radius: [dp(6)]

                        Image:
                            id: img_preview_config
                            source: ''
                            opacity: 1 if self.source else 0
                            allow_stretch: True
                            keep_ratio: True

                        Label:
                            id: lbl_preview_config
                            text: "[ Subir PNG transparente para probar capas ]" if not img_preview_config.source else ""
                            color: app.text_sec_color
                            font_size: '11sp'
                            halign: 'center'

                    BoxLayout:
                        size_hint_y: None
                        height: dp(38)
                        spacing: dp(8)

                        Button:
                            text: "📁 ARCHIVO"
                            font_size: '11sp'
                            bold: True
                            background_normal: ''
                            background_color: 0.2, 0.35, 0.5, 1
                            color: 1, 1, 1, 1
                            on_release: root.abrir_selector_imagen()

                        Button:
                            text: "📷 ON/OFF"
                            font_size: '11sp'
                            bold: True
                            background_normal: ''
                            background_color: 0.2, 0.5, 0.8, 1
                            color: 1, 1, 1, 1
                            on_release: root.toggle_camara_config()

                        Button:
                            text: "📸 CAPTURAR"
                            font_size: '11sp'
                            bold: True
                            background_normal: ''
                            background_color: 0.13, 0.55, 0.4, 1
                            color: 1, 1, 1, 1
                            on_release: root.tomar_foto_camara_config()

                    Button:
                        text: "💾 GUARDAR SERVICIO"
                        font_size: '13sp'
                        bold: True
                        size_hint_y: None
                        height: dp(42)
                        background_normal: ''
                        background_color: app.accent_color
                        color: 1, 1, 1, 1
                        on_release: root.guardar_servicio_db()

                # Lista de Servicios Guardados
                Label:
                    text: "SERVICIOS EN CATÁLOGO"
                    font_size: '13sp'
                    bold: True
                    color: app.accent_color
                    size_hint_y: None
                    height: dp(20)

                BoxLayout:
                    id: box_gestion_servicios
                    orientation: 'vertical'
                    size_hint_y: None
                    height: self.minimum_height
                    spacing: dp(6)

                Button:
                    text: "IR A PANTALLA DE TRABAJO ➔"
                    font_size: '14sp'
                    bold: True
                    size_hint_y: None
                    height: dp(48)
                    background_normal: ''
                    background_color: 0.13, 0.77, 0.36, 1
                    color: 1, 1, 1, 1
                    on_release: root.ir_a_trabajo()


<ScreenWork>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(10)
        spacing: dp(8)
        canvas.before:
            Color:
                rgba: app.bg_color
            Rectangle:
                pos: self.pos
                size: self.size

        # Barra Superior
        BoxLayout:
            size_hint_y: None
            height: dp(45)
            spacing: dp(6)

            Button:
                text: "⚙️ Config"
                size_hint_x: 0.18
                font_size: '10sp'
                bold: True
                background_normal: ''
                background_color: app.card_color
                color: app.text_main_color
                on_release: root.ir_a_config()

            Button:
                text: "📈 Finanzas"
                size_hint_x: 0.18
                font_size: '10sp'
                bold: True
                background_normal: ''
                background_color: 0.13, 0.65, 0.4, 1
                color: 1, 1, 1, 1
                on_release: root.ir_a_finanzas()

            Label:
                text: app.nombre_negocio
                font_size: '12sp'
                bold: True
                color: app.accent_color

            Button:
                text: "🎛️ Retoque NBO-A"
                size_hint_x: 0.28
                font_size: '10sp'
                bold: True
                background_normal: ''
                background_color: 0.5, 0.2, 0.8, 1
                color: 1, 1, 1, 1
                on_release: root.mostrar_modal_retoque_nboa()

            Button:
                text: "✨ Capas"
                size_hint_x: 0.18
                font_size: '10sp'
                bold: True
                background_normal: ''
                background_color: 0.9, 0.4, 0.1, 1
                color: 1, 1, 1, 1
                on_release: root.limpiar_capas_virtuales()

            Button:
                text: "🗑️ Ticket"
                size_hint_x: 0.18
                font_size: '10sp'
                bold: True
                background_normal: ''
                background_color: 0.8, 0.2, 0.2, 1
                color: 1, 1, 1, 1
                on_release: root.limpiar_ticket()

        # Visor Interactivo del Cliente con Capas Virtuales
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: 0.48
            padding: dp(6)
            spacing: dp(5)
            canvas.before:
                Color:
                    rgba: app.card_color
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [dp(10)]

            BoxLayout:
                size_hint_y: None
                height: dp(32)
                spacing: dp(6)

                Label:
                    text: "📷 Seleccionar Cámara:"
                    font_size: '11sp'
                    bold: True
                    color: app.accent_color
                    size_hint_x: 0.45

                Spinner:
                    id: sp_camara_work
                    text: app.camaras_disponibles[0] if app.camaras_disponibles else "Cámara 0"
                    values: app.camaras_disponibles
                    size_hint_x: 0.55
                    font_size: '11sp'
                    on_text: root.cambiar_camara_work(self.text)

            # Contenedor Multitáctil
            FloatLayout:
                id: visor_camara
                canvas.before:
                    Color:
                        rgba: [0, 0, 0, 0.2]
                    Rectangle:
                        pos: self.pos
                        size: self.size

                Image:
                    id: img_cliente
                    source: ''
                    opacity: 1 if self.source else 0
                    allow_stretch: True
                    keep_ratio: True
                    size_hint: (1, 1)
                    pos_hint: {'x': 0, 'y': 0}

                FloatLayout:
                    id: capa_efectos
                    size_hint: (1, 1)
                    pos_hint: {'x': 0, 'y': 0}

                Label:
                    id: lbl_estado_visor
                    text: "[ Toma o carga la foto del cliente ]\\n[ Doble toque en el rostro para maquillar zona ]" if not img_cliente.source else ""
                    color: app.text_sec_color
                    font_size: '11sp'
                    halign: 'center'
                    pos_hint: {'center_x': 0.5, 'center_y': 0.5}

            BoxLayout:
                size_hint_y: None
                height: dp(36)
                spacing: dp(6)

                Button:
                    text: "📷 ON/OFF"
                    font_size: '10sp'
                    bold: True
                    background_normal: ''
                    background_color: 0.2, 0.5, 0.8, 1
                    color: 1, 1, 1, 1
                    on_release: root.toggle_camara()

                Button:
                    text: "📸 CAPTURAR"
                    font_size: '10sp'
                    bold: True
                    background_normal: ''
                    background_color: 0.13, 0.65, 0.4, 1
                    color: 1, 1, 1, 1
                    on_release: root.tomar_captura()

                Button:
                    text: "📁 Cargar Foto"
                    font_size: '10sp'
                    bold: True
                    background_normal: ''
                    background_color: app.accent_color
                    color: 1, 1, 1, 1
                    on_release: root.cargar_foto_cliente_archivo()

        # Catálogo de Servicios y Ticket
        BoxLayout:
            size_hint_y: 0.52
            spacing: dp(8)

            # Columna Izquierda: Catálogo
            BoxLayout:
                orientation: 'vertical'
                size_hint_x: 0.48
                padding: dp(6)
                spacing: dp(6)
                canvas.before:
                    Color:
                        rgba: app.card_color
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [dp(8)]

                Label:
                    text: "CATÁLOGO (TOCA AÑADIR)"
                    font_size: '11sp'
                    bold: True
                    color: app.accent_color
                    size_hint_y: None
                    height: dp(20)

                ScrollView:
                    BoxLayout:
                        id: box_catalogo_servicios
                        orientation: 'vertical'
                        size_hint_y: None
                        height: self.minimum_height
                        spacing: dp(6)

            # Columna Derecha: Ticket
            BoxLayout:
                orientation: 'vertical'
                size_hint_x: 0.52
                padding: dp(6)
                spacing: dp(6)
                canvas.before:
                    Color:
                        rgba: app.card_color
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [dp(8)]

                Label:
                    text: "TICKET ACTUAL"
                    font_size: '12sp'
                    bold: True
                    color: 0.96, 0.62, 0.04, 1
                    size_hint_y: None
                    height: dp(20)

                # Selector Estilista Activo
                BoxLayout:
                    size_hint_y: None
                    height: dp(30)
                    spacing: dp(4)

                    Label:
                        text: "Atiende:"
                        font_size: '10sp'
                        color: app.text_main_color
                        size_hint_x: 0.35

                    Spinner:
                        id: sp_estilista_ticket
                        text: "General"
                        values: ["General"]
                        size_hint_x: 0.65
                        font_size: '10sp'

                ScrollView:
                    BoxLayout:
                        id: box_ticket_items
                        orientation: 'vertical'
                        size_hint_y: None
                        height: self.minimum_height
                        spacing: dp(4)

                Label:
                    id: lbl_total_precio
                    text: "TOTAL: $0.00"
                    font_size: '13sp'
                    bold: True
                    color: app.text_main_color
                    size_hint_y: None
                    height: dp(25)

                Button:
                    text: "🧾 COBRAR / TICKET"
                    font_size: '11sp'
                    bold: True
                    size_hint_y: None
                    height: dp(38)
                    background_normal: ''
                    background_color: 0.13, 0.77, 0.36, 1
                    color: 1, 1, 1, 1
                    on_release: root.mostrar_modal_ticket()


<ScreenFinanzas>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(12)
        spacing: dp(10)
        canvas.before:
            Color:
                rgba: app.bg_color
            Rectangle:
                pos: self.pos
                size: self.size

        # Encabezado
        BoxLayout:
            size_hint_y: None
            height: dp(45)
            spacing: dp(6)
            canvas.before:
                Color:
                    rgba: app.card_color
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [dp(8)]

            Button:
                text: "⬅️ Volver"
                size_hint_x: 0.25
                font_size: '11sp'
                bold: True
                background_normal: ''
                background_color: app.bg_color
                color: app.text_main_color
                on_release: root.ir_a_trabajo()

            Label:
                text: "📈 FINANZAS Y CAJA"
                font_size: '14sp'
                bold: True
                color: app.accent_color

        ScrollView:
            BoxLayout:
                orientation: 'vertical'
                size_hint_y: None
                height: self.minimum_height
                spacing: dp(12)

                # Resumen de Métodos de Pago
                BoxLayout:
                    orientation: 'vertical'
                    size_hint_y: None
                    height: dp(160)
                    padding: dp(10)
                    spacing: dp(6)
                    canvas.before:
                        Color:
                            rgba: app.card_color
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(10)]

                    Label:
                        text: "RESUMEN DE COBROS DE HOY"
                        font_size: '12sp'
                        bold: True
                        color: app.accent_color
                        size_hint_y: None
                        height: dp(20)

                    Label:
                        id: lbl_fin_efectivo
                        text: "💵 Efectivo: $0.00"
                        font_size: '11sp'
                        color: app.text_main_color
                        halign: 'left'

                    Label:
                        id: lbl_fin_tarjeta
                        text: "💳 Tarjeta (TPV): $0.00"
                        font_size: '11sp'
                        color: app.text_main_color
                        halign: 'left'

                    Label:
                        id: lbl_fin_transferencia
                        text: "📲 Transferencia: $0.00"
                        font_size: '11sp'
                        color: app.text_main_color
                        halign: 'left'

                    Label:
                        id: lbl_fin_total
                        text: "💰 TOTAL INGRESOS: $0.00"
                        font_size: '13sp'
                        bold: True
                        color: 0.13, 0.77, 0.36, 1
                        halign: 'left'

                # Formulario Movimientos de Caja (Retiros / Gastos)
                BoxLayout:
                    orientation: 'vertical'
                    size_hint_y: None
                    height: dp(170)
                    padding: dp(10)
                    spacing: dp(6)
                    canvas.before:
                        Color:
                            rgba: app.card_color
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(10)]

                    Label:
                        text: "REGISTRAR RETIRO / GASTO DE CAJA"
                        font_size: '11sp'
                        bold: True
                        color: app.accent_color
                        size_hint_y: None
                        height: dp(18)

                    TextInput:
                        id: in_gasto_concepto
                        hint_text: "Concepto (Ej. Compra de Insumos / Agua)"
                        multiline: False
                        size_hint_y: None
                        height: dp(38)

                    TextInput:
                        id: in_gasto_monto
                        hint_text: "Monto $"
                        input_filter: 'float'
                        multiline: False
                        size_hint_y: None
                        height: dp(38)

                    Button:
                        text: "💸 REGISTRAR SALIDA"
                        font_size: '11sp'
                        bold: True
                        size_hint_y: None
                        height: dp(38)
                        background_normal: ''
                        background_color: 0.8, 0.2, 0.2, 1
                        color: 1, 1, 1, 1
                        on_release: root.registrar_gasto_caja()

                # Comisiones de Estilistas
                Label:
                    text: "COMISIONES / PAGO A ESTILISTAS (HOY)"
                    font_size: '12sp'
                    bold: True
                    color: app.accent_color
                    size_hint_y: None
                    height: dp(20)

                BoxLayout:
                    id: box_comisiones_estilistas
                    orientation: 'vertical'
                    size_hint_y: None
                    height: self.minimum_height
                    spacing: dp(6)
'''

Builder.load_string(KV)


class ScreenLicencia(Screen):
    def on_enter(self):
        lic_guardada = App.get_running_app().cargar_licencia_local()
        if lic_guardada:
            self.ids.in_licencia_key.text = lic_guardada
            self.validar_licencia_servidor()

    def validar_licencia_servidor(self):
        key = self.ids.in_licencia_key.text.strip()
        if not key:
            self.ids.lbl_estado_licencia.text = "Ingresa una licencia válida."
            return

        self.ids.lbl_estado_licencia.text = "Conectando con servidor NBO-A..."
        self.ids.btn_validar.disabled = True

        app = App.get_running_app()
        payload = {"licencia": key}
        headers = {'Content-Type': 'application/json'}

        UrlRequest(
            f"{app.url_servidor}/api/validar_licencia",
            req_body=json.dumps(payload),
            req_headers=headers,
            on_success=self._on_exito,
            on_failure=self._on_error,
            on_error=self._on_error,
            method='POST',
            timeout=60
        )

    def _on_exito(self, request, result):
        self.ids.btn_validar.disabled = False
        if result.get("estatus") == "ok":
            app = App.get_running_app()
            app.licencia_activa = self.ids.in_licencia_key.text.strip()
            app.guardar_licencia_local(app.licencia_activa)
            self.manager.current = 'work'
        else:
            msg = result.get("mensaje", "Licencia inválida o expirada.")
            self.ids.lbl_estado_licencia.text = f"❌ {msg}"

    def _on_error(self, request, error):
        self.ids.btn_validar.disabled = False
        self.ids.lbl_estado_licencia.text = "❌ Servidor despertando / Error de conexión."


class ScreenConfig(Screen):
    cam_activa = BooleanProperty(False)
    index_camara_actual = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.foto_servicio_path = None
        self.widget_camara = None

    def on_enter(self):
        self.actualizar_lista_servicios()

    def on_leave(self):
        self.detener_camara_config()

    def guardar_estilista_db(self):
        nombre = self.ids.in_nombre_estilista.text.strip()
        comision_txt = self.ids.in_comision_estilista.text.strip()

        if nombre and comision_txt:
            try:
                comision = float(comision_txt)
                with sqlite3.connect(DB_NAME) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO estilistas (nombre, porcentaje_comision) VALUES (?, ?)",
                        (nombre, comision)
                    )
                    conn.commit()

                self.ids.in_nombre_estilista.text = ""
                self.ids.in_comision_estilista.text = ""

                modal_ok = ModalView(size_hint=(0.7, 0.2), auto_dismiss=True)
                modal_ok.add_widget(Label(text=f"✅ Estilista {nombre} guardado"))
                modal_ok.open()

            except ValueError:
                pass

    def obtener_indice_de_texto(self, texto):
        try:
            partes = texto.split()
            for p in partes:
                if p.isdigit():
                    return int(p)
        except Exception:
            pass
        return 0

    def cambiar_camara_seleccionada(self, texto_camara):
        nuevo_idx = self.obtener_indice_de_texto(texto_camara)
        if nuevo_idx != self.index_camara_actual:
            self.index_camara_actual = nuevo_idx
            if self.cam_activa:
                self.detener_camara_config()
                self.iniciar_camara_config()

    def toggle_camara_config(self):
        if self.cam_activa:
            self.detener_camara_config()
        else:
            self.iniciar_camara_config()

    def iniciar_camara_config(self):
        self.ids.img_preview_config.source = ""
        self.detener_camara_config()
        Clock.schedule_once(self._crear_widget_camara_config, 0.2)

    def _crear_widget_camara_config(self, dt):
        box = self.ids.box_preview_config
        try:
            self.widget_camara = Camera(index=int(self.index_camara_actual), play=False, resolution=(640, 480))
            box.add_widget(self.widget_camara)
            self.widget_camara.play = True
            self.cam_activa = True
            self.ids.lbl_preview_config.text = ""
        except Exception as e:
            self.cam_activa = False
            self.ids.lbl_preview_config.text = "📷 Cámara en vivo no soportada.\\nUsa ARCHIVO."

    def detener_camara_config(self):
        box = self.ids.box_preview_config
        if self.widget_camara:
            try:
                self.widget_camara.play = False
            except Exception:
                pass
            if self.widget_camara in box.children:
                box.remove_widget(self.widget_camara)
            self.widget_camara = None
        self.cam_activa = False

    def tomar_foto_camara_config(self):
        if self.widget_camara and self.cam_activa:
            try:
                path = os.path.join(App.get_running_app().user_data_dir, "temp_servicio.jpg")
                self.widget_camara.export_to_png(path)
                self.detener_camara_config()
                self.foto_servicio_path = path
                self.refrescar_imagen_preview(path)
            except Exception as e:
                self.ids.lbl_preview_config.text = "Error al capturar la imagen."

    def refrescar_imagen_preview(self, path):
        Cache.remove('kv.image', path)
        Cache.remove('kv.texture', path)
        self.ids.img_preview_config.source = path
        self.ids.img_preview_config.reload()

    def abrir_selector_imagen(self):
        self.detener_camara_config()
        contenido = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        ruta_inicial = obtener_ruta_archivos()
        filechooser = FileChooserListView(
            path=ruta_inicial,
            filters=['*.png', '*.jpg', '*.jpeg', '*.PNG', '*.JPG', '*.JPEG']
        )
        contenido.add_widget(filechooser)

        btn_bar = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(10))
        btn_seleccionar = Button(text="SELECCIONAR", background_normal='', background_color=(0.13, 0.77, 0.36, 1), color=(1, 1, 1, 1))
        btn_cancelar = Button(text="CANCELAR", background_normal='', background_color=(0.92, 0.28, 0.6, 1), color=(1, 1, 1, 1))

        btn_bar.add_widget(btn_seleccionar)
        btn_bar.add_widget(btn_cancelar)
        contenido.add_widget(btn_bar)

        modal = ModalView(size_hint=(0.9, 0.8), auto_dismiss=False)
        modal.add_widget(contenido)

        def confirmar(instance):
            if filechooser.selection:
                self.foto_servicio_path = filechooser.selection[0]
                self.refrescar_imagen_preview(self.foto_servicio_path)
            modal.dismiss()

        btn_seleccionar.bind(on_release=confirmar)
        btn_cancelar.bind(on_release=modal.dismiss)
        modal.open()

    def guardar_servicio_db(self):
        nombre = self.ids.in_nombre_servicio.text.strip()
        categoria = self.ids.in_cat_servicio.text.replace("Categoría: ", "").strip()
        precio_txt = self.ids.in_precio_servicio.text.strip()

        if nombre and precio_txt:
            try:
                precio = float(precio_txt)
                with sqlite3.connect(DB_NAME) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO servicios (nombre, categoria, precio, foto_path) VALUES (?, ?, ?, ?)",
                        (nombre, categoria, precio, self.foto_servicio_path or "")
                    )
                    conn.commit()

                self.ids.in_nombre_servicio.text = ""
                self.ids.in_precio_servicio.text = ""
                self.ids.img_preview_config.source = ""
                self.foto_servicio_path = None
                self.detener_camara_config()
                self.actualizar_lista_servicios()

                modal_ok = ModalView(size_hint=(0.7, 0.2), auto_dismiss=True)
                modal_ok.add_widget(Label(text="✅ Servicio / Capa guardado"))
                modal_ok.open()

            except ValueError:
                pass

    def eliminar_servicio(self, s_id):
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM servicios WHERE id = ?", (s_id,))
            conn.commit()
        self.actualizar_lista_servicios()

    def actualizar_lista_servicios(self):
        box = self.ids.box_gestion_servicios
        box.clear_widgets()

        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, nombre, categoria, precio FROM servicios ORDER BY id DESC")
            servicios = cursor.fetchall()

        app = App.get_running_app()
        for s_id, nombre, cat, precio in servicios:
            row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
            lbl = Label(
                text=f"{nombre} ({cat}) - ${precio:.2f}",
                font_size='11sp',
                color=app.text_main_color,
                halign='left',
                size_hint_x=0.8
            )
            lbl.bind(size=lbl.setter('text_size'))
            btn_del = Button(
                text="🗑️",
                size_hint_x=0.2,
                background_normal='',
                background_color=(0.8, 0.2, 0.2, 1)
            )
            btn_del.bind(on_release=lambda x, i=s_id: self.eliminar_servicio(i))

            row.add_widget(lbl)
            row.add_widget(btn_del)
            box.add_widget(row)

    def mostrar_modal_reporte_diario(self):
        hoy_prefix = datetime.now().strftime("%Y-%m-%d")
        
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), SUM(total) FROM ventas WHERE fecha LIKE ?", (f"{hoy_prefix}%",))
            num_ventas, total_recaudado = cursor.fetchone()
            total_recaudado = total_recaudado or 0.0

            cursor.execute('''
                SELECT dv.servicio_nombre, SUM(dv.cantidad), SUM(dv.subtotal)
                FROM detalle_ventas dv
                JOIN ventas v ON dv.venta_id = v.id
                WHERE v.fecha LIKE ?
                GROUP BY dv.servicio_nombre
                ORDER BY SUM(dv.subtotal) DESC
            ''', (f"{hoy_prefix}%",))
            agrupado = cursor.fetchall()

        app = App.get_running_app()
        contenido = BoxLayout(orientation='vertical', padding=12, spacing=10)
        contenido.add_widget(Label(text=f"📊 REPORTE DE HOY ({datetime.now().strftime('%d/%m/%Y')})", font_size='14sp', bold=True, size_hint_y=None, height=dp(25)))
        
        box_resumen = BoxLayout(size_hint_y=None, height=dp(35), spacing=dp(8))
        box_resumen.add_widget(Label(text=f"Tickets: {num_ventas}", font_size='11sp', color=app.text_sec_color))
        box_resumen.add_widget(Label(text=f"TOTAL: ${total_recaudado:.2f}", font_size='13sp', bold=True, color=(0.13, 0.77, 0.36, 1)))
        contenido.add_widget(box_resumen)

        scroll = ScrollView(size_hint_y=0.7)
        box_items = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(6))
        box_items.bind(minimum_height=box_items.setter('height'))

        if agrupado:
            for s_nombre, cant_total, sub_total in agrupado:
                row = BoxLayout(size_hint_y=None, height=dp(26), spacing=dp(4))
                lbl_n = Label(text=f"{s_nombre}", font_size='11sp', halign='left', size_hint_x=0.5)
                lbl_n.bind(size=lbl_n.setter('text_size'))
                lbl_c = Label(text=f"x{cant_total}", font_size='11sp', size_hint_x=0.2, color=app.text_sec_color)
                lbl_p = Label(text=f"${sub_total:.2f}", font_size='11sp', bold=True, size_hint_x=0.3)
                row.add_widget(lbl_n)
                row.add_widget(lbl_c)
                row.add_widget(lbl_p)
                box_items.add_widget(row)
        else:
            box_items.add_widget(Label(text="No se registran ventas el día de hoy.", font_size='11sp', color=app.text_sec_color))

        scroll.add_widget(box_items)
        contenido.add_widget(scroll)

        btn_cerrar = Button(text="CERRAR", size_hint_y=None, height=dp(38), background_normal='', background_color=app.accent_color, color=(1, 1, 1, 1))
        modal = ModalView(size_hint=(0.85, 0.7), auto_dismiss=True)
        btn_cerrar.bind(on_release=modal.dismiss)
        contenido.add_widget(btn_cerrar)

        modal.add_widget(contenido)
        modal.open()

    def ir_a_trabajo(self):
        self.manager.current = 'work'


class ScreenWork(Screen):
    cam_activa = BooleanProperty(False)
    index_camara_actual = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.widget_camara = None
        self.ticket_actual = []
        self.ruta_foto_original = None
        self.zona_maquillaje_actual = "Labios"
        self.color_maquillaje_actual = "#ff0055"
        self.intensidad_maquillaje = 60

    def on_enter(self):
        self.cargar_catalogo_desde_db()
        self.cargar_estilistas_spinner()
        self.actualizar_vista_ticket()

    def on_leave(self):
        self.detener_camara()

    def cargar_estilistas_spinner(self):
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nombre FROM estilistas")
            estilistas = [row[0] for row in cursor.fetchall()]
        
        if estilistas:
            self.ids.sp_estilista_ticket.values = estilistas
            self.ids.sp_estilista_ticket.text = estilistas[0]

    def on_touch_down(self, touch):
        if touch.is_double_tap:
            visor = self.ids.img_cliente
            if visor.collide_point(*touch.pos) and self.ruta_foto_original:
                self.procesar_doble_toque_rasgos(touch.x, touch.y)
                return True
        return super().on_touch_down(touch)

    def procesar_doble_toque_rasgos(self, touch_x, touch_y):
        visor = self.ids.img_cliente
        rel_x = (touch_x - visor.x) / visor.width
        rel_y = 1.0 - ((touch_y - visor.y) / visor.height)

        from PIL import Image as PILImage
        try:
            with PILImage.open(self.ruta_foto_original) as img_temp:
                img_w, img_h = img_temp.size
        except Exception:
            img_w, img_h = 640, 480

        coord_x = int(rel_x * img_w)
        coord_y = int(rel_y * img_h)

        self.enviar_a_editar_rasgos_nboa(
            zona=self.zona_maquillaje_actual,
            coord_x=coord_x,
            coord_y=coord_y,
            color_hex=self.color_maquillaje_actual,
            intensidad=self.intensidad_maquillaje
        )

    def enviar_a_procesar_nboa(self, brillo=100, contraste=100, suavizado=0, tono_r=100, tono_b=100, modo_color="normal"):
        if not self.ruta_foto_original or not os.path.exists(self.ruta_foto_original):
            return

        app = App.get_running_app()
        with open(self.ruta_foto_original, "rb") as image_file:
            img_b64 = base64.b64encode(image_file.read()).decode('utf-8')

        payload = {
            "licencia": app.licencia_activa,
            "imagen_base64": f"data:image/jpeg;base64,{img_b64}",
            "brillo": brillo,
            "contraste": contraste,
            "suavizado": suavizado,
            "tono_r": tono_r,
            "tono_b": tono_b,
            "modo_color": modo_color
        }

        headers = {'Content-Type': 'application/json'}
        UrlRequest(
            f"{app.url_servidor}/api/procesar_rostro",
            req_body=json.dumps(payload),
            req_headers=headers,
            on_success=self._on_nboa_exito,
            on_failure=self._on_nboa_error,
            on_error=self._on_nboa_error,
            method='POST',
            timeout=60
        )

    def enviar_a_editar_rasgos_nboa(self, zona, coord_x, coord_y, color_hex, intensidad):
        if not self.ruta_foto_original or not os.path.exists(self.ruta_foto_original):
            return

        app = App.get_running_app()
        path_base = os.path.join(app.user_data_dir, "temp_cliente_nboa.jpg")
        if not os.path.exists(path_base):
            path_base = self.ruta_foto_original

        with open(path_base, "rb") as image_file:
            img_b64 = base64.b64encode(image_file.read()).decode('utf-8')

        payload = {
            "licencia": app.licencia_activa,
            "imagen_base64": f"data:image/jpeg;base64,{img_b64}",
            "zona": zona,
            "coord_x": coord_x,
            "coord_y": coord_y,
            "color": color_hex,
            "intensidad": intensidad
        }

        headers = {'Content-Type': 'application/json'}
        UrlRequest(
            f"{app.url_servidor}/api/editar_rasgos",
            req_body=json.dumps(payload),
            req_headers=headers,
            on_success=self._on_nboa_exito,
            on_failure=self._on_nboa_error,
            on_error=self._on_nboa_error,
            method='POST',
            timeout=60
        )

    def _on_nboa_exito(self, request, result):
        if result.get("estatus") == "ok":
            img_b64_res = result.get("imagen_procesada") or result.get("imagen_resultante") or ""
            if ',' in img_b64_res:
                img_b64_res = img_b64_res.split(',')[1]

            img_data = base64.b64decode(img_b64_res)
            path_salida = os.path.join(App.get_running_app().user_data_dir, "temp_cliente_nboa.jpg")
            with open(path_salida, "wb") as f:
                f.write(img_data)

            Cache.remove('kv.image', path_salida)
            Cache.remove('kv.texture', path_salida)
            self.ids.img_cliente.source = path_salida
            self.ids.img_cliente.reload()

    def _on_nboa_error(self, request, error):
        print(f"Error procesando en servidor NBO-A: {error}")

    def mostrar_modal_retoque_nboa(self):
        if not self.ruta_foto_original:
            return

        contenido = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(6))
        contenido.add_widget(Label(text="🎛️ RETOQUE NBO-A GÉNESIS B", font_size='13sp', bold=True, size_hint_y=None, height=dp(22)))

        scroll = ScrollView(size_hint_y=0.75)
        box_controls = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(6))
        box_controls.bind(minimum_height=box_controls.setter('height'))

        box_controls.add_widget(Label(text="Brillo", font_size='10sp', size_hint_y=None, height=dp(16)))
        sld_brillo = Slider(min=10, max=200, value=100, step=1, size_hint_y=None, height=dp(26))
        box_controls.add_widget(sld_brillo)

        box_controls.add_widget(Label(text="Contraste", font_size='10sp', size_hint_y=None, height=dp(16)))
        sld_contraste = Slider(min=10, max=200, value=100, step=1, size_hint_y=None, height=dp(26))
        box_controls.add_widget(sld_contraste)

        box_controls.add_widget(Label(text="Suavizado de Piel", font_size='10sp', size_hint_y=None, height=dp(16)))
        sld_suavizado = Slider(min=0, max=100, value=0, step=1, size_hint_y=None, height=dp(26))
        box_controls.add_widget(sld_suavizado)

        box_controls.add_widget(Label(text="Modo de Color / Filtro", font_size='10sp', size_hint_y=None, height=dp(16)))
        sp_modo = Spinner(text="normal", values=["normal", "gris", "rosa"], size_hint_y=None, height=dp(30))
        box_controls.add_widget(sp_modo)

        box_controls.add_widget(Label(text="--- MAQUILLAJE ZONAL (DOBLE TOQUE) ---", font_size='10sp', bold=True, size_hint_y=None, height=dp(20)))
        sp_zona = Spinner(text=self.zona_maquillaje_actual, values=["Labios", "Rubor", "Sombras", "Cabello"], size_hint_y=None, height=dp(30))
        box_controls.add_widget(sp_zona)

        sp_color = Spinner(text=self.color_maquillaje_actual, values=["#ff0055", "#cc0000", "#e60073", "#800020", "#ff6699", "#4a2c11"], size_hint_y=None, height=dp(30))
        box_controls.add_widget(sp_color)

        scroll.add_widget(box_controls)
        contenido.add_widget(scroll)

        btn_aplicar = Button(
            text="APLICAR AJUSTES GLOBALES",
            size_hint_y=None,
            height=dp(36),
            background_normal='',
            background_color=(0.13, 0.77, 0.36, 1),
            bold=True
        )

        def ejecutar_aplicar(instance):
            self.zona_maquillaje_actual = sp_zona.text
            self.color_maquillaje_actual = sp_color.text
            self.enviar_a_procesar_nboa(
                brillo=sld_brillo.value,
                contraste=sld_contraste.value,
                suavizado=sld_suavizado.value,
                modo_color=sp_modo.text
            )

        btn_aplicar.bind(on_release=ejecutar_aplicar)
        contenido.add_widget(btn_aplicar)

        modal = ModalView(size_hint=(0.85, 0.75), auto_dismiss=True)
        modal.add_widget(contenido)
        modal.open()

    def obtener_indice_de_texto(self, texto):
        try:
            partes = texto.split()
            for p in partes:
                if p.isdigit():
                    return int(p)
        except Exception:
            pass
        return 0

    def cambiar_camara_work(self, texto_camara):
        nuevo_idx = self.obtener_indice_de_texto(texto_camara)
        if nuevo_idx != self.index_camara_actual:
            self.index_camara_actual = nuevo_idx
            if self.cam_activa:
                self.detener_camara()
                self.iniciar_camara()

    def cargar_catalogo_desde_db(self):
        box = self.ids.box_catalogo_servicios
        box.clear_widgets()

        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, nombre, categoria, precio, foto_path FROM servicios")
            servicios = cursor.fetchall()

        app = App.get_running_app()
        for s_id, nombre, cat, precio, foto in servicios:
            btn = Button(
                text=f"{nombre}\\n${precio:.2f}",
                size_hint_y=None,
                height=dp(48),
                font_size='11sp',
                background_normal='',
                background_color=app.card_color,
                color=app.text_main_color
            )
            btn.bind(on_release=lambda x, n=nombre, p=precio, f=foto: self.agregar_al_ticket(n, p, f))
            box.add_widget(btn)

    def agregar_al_ticket(self, nombre, precio, foto=None):
        estilista = self.ids.sp_estilista_ticket.text
        for item in self.ticket_actual:
            if item['nombre'] == nombre and item['estilista'] == estilista:
                item['cantidad'] += 1
                item['subtotal'] = item['cantidad'] * item['precio']
                break
        else:
            self.ticket_actual.append({
                "nombre": nombre,
                "estilista": estilista,
                "precio": precio,
                "cantidad": 1,
                "subtotal": precio
            })

        if foto and os.path.exists(foto):
            self.detener_camara()
            self.superponer_capa_virtual(foto)

        self.actualizar_vista_ticket()

    def superponer_capa_virtual(self, foto_path):
        capa_efectos = self.ids.capa_efectos
        capa = CapaVirtual(foto_path=foto_path)
        capa.pos = (
            capa_efectos.width / 2 - capa.width / 2,
            capa_efectos.height / 2 - capa.height / 2
        )
        capa_efectos.add_widget(capa)

    def limpiar_capas_virtuales(self):
        self.ids.capa_efectos.clear_widgets()

    def toggle_camara(self):
        if self.cam_activa:
            self.detener_camara()
        else:
            self.iniciar_camara()

    def iniciar_camara(self):
        self.ids.img_cliente.source = ""
        self.detener_camara()
        Clock.schedule_once(self._crear_widget_camara_work, 0.2)

    def _crear_widget_camara_work(self, dt):
        visor = self.ids.visor_camara
        try:
            self.widget_camara = Camera(index=int(self.index_camara_actual), play=False, resolution=(640, 480))
            visor.add_widget(self.widget_camara, index=len(visor.children))
            self.widget_camara.play = True
            self.cam_activa = True
            self.ids.lbl_estado_visor.text = ""
        except Exception as e:
            self.cam_activa = False
            self.ids.lbl_estado_visor.text = "📷 Cámara no disponible.\\nUsa 'Cargar Foto'."

    def detener_camara(self):
        visor = self.ids.visor_camara
        if self.widget_camara:
            try:
                self.widget_camara.play = False
            except Exception:
                pass
            if self.widget_camara in visor.children:
                visor.remove_widget(self.widget_camara)
            self.widget_camara = None
        self.cam_activa = False

    def tomar_captura(self):
        if self.widget_camara and self.cam_activa:
            try:
                path = os.path.join(App.get_running_app().user_data_dir, "cap_cliente.png")
                self.widget_camara.export_to_png(path)
                self.detener_camara()
                self.ruta_foto_original = path
                Cache.remove('kv.image', path)
                Cache.remove('kv.texture', path)
                self.ids.img_cliente.source = path
                self.ids.img_cliente.reload()
            except Exception as e:
                self.ids.lbl_estado_visor.text = "Error al capturar la imagen."

    def cargar_foto_cliente_archivo(self):
        self.detener_camara()
        contenido = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        ruta_inicial = obtener_ruta_archivos()
        filechooser = FileChooserListView(
            path=ruta_inicial,
            filters=['*.png', '*.jpg', '*.jpeg', '*.PNG', '*.JPG', '*.JPEG']
        )
        contenido.add_widget(filechooser)

        btn_bar = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(10))
        btn_sel = Button(text="OK", background_normal='', background_color=(0.13, 0.77, 0.36, 1))
        btn_can = Button(text="CANCELAR", background_normal='', background_color=(0.8, 0.2, 0.2, 1))
        btn_bar.add_widget(btn_sel)
        btn_bar.add_widget(btn_can)
        contenido.add_widget(btn_bar)

        modal = ModalView(size_hint=(0.9, 0.8), auto_dismiss=False)
        modal.add_widget(contenido)

        def sel(instance):
            if filechooser.selection:
                path = filechooser.selection[0]
                self.ruta_foto_original = path
                Cache.remove('kv.image', path)
                Cache.remove('kv.texture', path)
                self.ids.img_cliente.source = path
                self.ids.img_cliente.reload()
            modal.dismiss()

        btn_sel.bind(on_release=sel)
        btn_can.bind(on_release=modal.dismiss)
        modal.open()

    def eliminar_item_ticket(self, idx):
        if 0 <= idx < len(self.ticket_actual):
            if self.ticket_actual[idx]['cantidad'] > 1:
                self.ticket_actual[idx]['cantidad'] -= 1
                self.ticket_actual[idx]['subtotal'] = self.ticket_actual[idx]['cantidad'] * self.ticket_actual[idx]['precio']
            else:
                self.ticket_actual.pop(idx)
            self.actualizar_vista_ticket()

    def limpiar_ticket(self):
        self.ticket_actual.clear()
        self.limpiar_capas_virtuales()
        self.actualizar_vista_ticket()

    def actualizar_vista_ticket(self):
        box = self.ids.box_ticket_items
        box.clear_widgets()
        total = 0.0

        for idx, item in enumerate(self.ticket_actual):
            row = BoxLayout(size_hint_y=None, height=dp(28), spacing=dp(4))
            lbl = Label(
                text=f"{item['cantidad']}x {item['nombre']} ({item['estilista']})",
                font_size='10sp',
                halign='left',
                size_hint_x=0.55
            )
            lbl.bind(size=lbl.setter('text_size'))
            
            lbl_p = Label(
                text=f"${item['subtotal']:.2f}",
                font_size='10sp',
                bold=True,
                size_hint_x=0.3
            )
            btn_del = Button(
                text="×",
                size_hint_x=0.15,
                background_normal='',
                background_color=(0.8, 0.2, 0.2, 1)
            )
            btn_del.bind(on_release=lambda x, i=idx: self.eliminar_item_ticket(i))

            row.add_widget(lbl)
            row.add_widget(lbl_p)
            row.add_widget(btn_del)
            box.add_widget(row)
            total += item['subtotal']

        self.ids.lbl_total_precio.text = f"TOTAL: ${total:.2f}"

    def mostrar_modal_ticket(self):
        if not self.ticket_actual:
            return

        total = sum(i['subtotal'] for i in self.ticket_actual)
        app = App.get_running_app()
        fecha_obj = datetime.now()
        fecha_str = fecha_obj.strftime("%d/%m/%Y %H:%M")
        fecha_db = fecha_obj.strftime("%Y-%m-%d %H:%M:%S")

        contenido = BoxLayout(orientation='vertical', padding=12, spacing=8)
        contenido.add_widget(Label(text=f"=== {app.nombre_negocio.upper()} ===", font_size='14sp', bold=True, size_hint_y=None, height=dp(22)))
        contenido.add_widget(Label(text=f"Fecha: {fecha_str}", font_size='10sp', color=app.text_sec_color, size_hint_y=None, height=dp(18)))

        scroll = ScrollView(size_hint_y=0.5)
        box_items = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(4))
        box_items.bind(minimum_height=box_items.setter('height'))

        for item in self.ticket_actual:
            row = BoxLayout(size_hint_y=None, height=dp(20))
            row.add_widget(Label(text=f"{item['cantidad']}x {item['nombre']} [{item['estilista']}]", font_size='10sp', halign='left'))
            row.add_widget(Label(text=f"${item['subtotal']:.2f}", font_size='10sp', bold=True))
            box_items.add_widget(row)

        scroll.add_widget(box_items)
        contenido.add_widget(scroll)

        # Selección Método de Pago
        box_pago = BoxLayout(size_hint_y=None, height=dp(35), spacing=dp(6))
        box_pago.add_widget(Label(text="Método de Pago:", font_size='11sp', size_hint_x=0.4))
        sp_metodo_pago = Spinner(
            text="Efectivo",
            values=["Efectivo", "Tarjeta (TPV)", "Transferencia"],
            size_hint_x=0.6,
            font_size='11sp'
        )
        box_pago.add_widget(sp_metodo_pago)
        contenido.add_widget(box_pago)

        contenido.add_widget(Label(text=f"TOTAL: ${total:.2f}", font_size='14sp', bold=True, size_hint_y=None, height=dp(30)))

        btn_box = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(8))
        btn_imprimir = Button(text="💾 GUARDAR TICKET TXT", background_normal='', background_color=(0.13, 0.77, 0.36, 1), color=(1, 1, 1, 1))
        btn_cerrar = Button(text="CERRAR", background_normal='', background_color=(0.8, 0.2, 0.2, 1), color=(1, 1, 1, 1))

        btn_box.add_widget(btn_imprimir)
        btn_box.add_widget(btn_cerrar)
        contenido.add_widget(btn_box)

        modal = ModalView(size_hint=(0.85, 0.7), auto_dismiss=False)

        def exportar_y_registrar_venta(instance):
            metodo = sp_metodo_pago.text
            with sqlite3.connect(DB_NAME) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO ventas (fecha, total, metodo_pago) VALUES (?, ?, ?)", (fecha_db, total, metodo))
                venta_id = cursor.lastrowid
                
                for item in self.ticket_actual:
                    cursor.execute('''
                        INSERT INTO detalle_ventas (venta_id, servicio_nombre, estilista_nombre, cantidad, precio_unitario, subtotal)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (venta_id, item['nombre'], item['estilista'], item['cantidad'], item['precio'], item['subtotal']))
                conn.commit()

            filename = f"ticket_{fecha_obj.strftime('%Y%m%d_%H%M%S')}.txt"
            path_txt = os.path.join(app.user_data_dir, filename)
            with open(path_txt, "w", encoding="utf-8") as f:
                f.write("============================\n")
                f.write(f"   {app.nombre_negocio.upper()}\n")
                f.write(f"   Fecha: {fecha_str}\n")
                f.write(f"   Pago:  {metodo}\n")
                f.write("============================\n\n")
                for item in self.ticket_actual:
                    f.write(f"{item['cantidad']}x {item['nombre']} ({item['estilista']})\n")
                    f.write(f"                      ${item['subtotal']:.2f}\n")
                f.write("\n----------------------------\n")
                f.write(f"TOTAL:              ${total:.2f}\n")
                f.write("============================\n")
                f.write("   ¡Gracias por su visita!\n")

            modal.dismiss()
            self.limpiar_ticket()

        btn_imprimir.bind(on_release=exportar_y_registrar_venta)
        btn_cerrar.bind(on_release=modal.dismiss)
        modal.add_widget(contenido)
        modal.open()

    def ir_a_config(self):
        self.manager.current = 'config'

    def ir_a_finanzas(self):
        self.manager.current = 'finanzas'


class ScreenFinanzas(Screen):
    def on_enter(self):
        self.cargar_resumen_caja()
        self.cargar_comisiones_estilistas()

    def cargar_resumen_caja(self):
        hoy_prefix = datetime.now().strftime("%Y-%m-%d")
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT SUM(total) FROM ventas WHERE fecha LIKE ? AND metodo_pago = 'Efectivo'", (f"{hoy_prefix}%",))
            efectivo = cursor.fetchone()[0] or 0.0

            cursor.execute("SELECT SUM(total) FROM ventas WHERE fecha LIKE ? AND metodo_pago LIKE 'Tarjeta%'", (f"{hoy_prefix}%",))
            tarjeta = cursor.fetchone()[0] or 0.0

            cursor.execute("SELECT SUM(total) FROM ventas WHERE fecha LIKE ? AND metodo_pago = 'Transferencia'", (f"{hoy_prefix}%",))
            transferencia = cursor.fetchone()[0] or 0.0

            cursor.execute("SELECT SUM(monto) FROM movimientos_caja WHERE fecha LIKE ? AND tipo = 'Egreso'", (f"{hoy_prefix}%",))
            egresos = cursor.fetchone()[0] or 0.0

        total_ingresos = efectivo + tarjeta + transferencia
        efectivo_en_caja = efectivo - egresos

        self.ids.lbl_fin_efectivo.text = f"💵 Efectivo en Caja: ${efectivo_en_caja:.2f} (Egresos: -${egresos:.2f})"
        self.ids.lbl_fin_tarjeta.text = f"💳 Tarjeta (TPV): ${tarjeta:.2f}"
        self.ids.lbl_fin_transferencia.text = f"📲 Transferencia: ${transferencia:.2f}"
        self.ids.lbl_fin_total.text = f"💰 TOTAL VENTAS: ${total_ingresos:.2f}"

    def registrar_gasto_caja(self):
        concepto = self.ids.in_gasto_concepto.text.strip()
        monto_txt = self.ids.in_gasto_monto.text.strip()
        fecha_db = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if concepto and monto_txt:
            try:
                monto = float(monto_txt)
                with sqlite3.connect(DB_NAME) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO movimientos_caja (fecha, tipo, concepto, monto) VALUES (?, 'Egreso', ?, ?)",
                        (fecha_db, concepto, monto)
                    )
                    conn.commit()

                self.ids.in_gasto_concepto.text = ""
                self.ids.in_gasto_monto.text = ""
                self.cargar_resumen_caja()

                modal_ok = ModalView(size_hint=(0.7, 0.2), auto_dismiss=True)
                modal_ok.add_widget(Label(text="✅ Salida de caja registrada"))
                modal_ok.open()
            except ValueError:
                pass

    def cargar_comisiones_estilistas(self):
        hoy_prefix = datetime.now().strftime("%Y-%m-%d")
        box = self.ids.box_comisiones_estilistas
        box.clear_widgets()

        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT e.nombre, e.porcentaje_comision, SUM(dv.subtotal)
                FROM detalle_ventas dv
                JOIN ventas v ON dv.venta_id = v.id
                JOIN estilistas e ON dv.estilista_nombre = e.nombre
                WHERE v.fecha LIKE ?
                GROUP BY e.nombre
            ''', (f"{hoy_prefix}%",))
            resultados = cursor.fetchall()

        app = App.get_running_app()
        if resultados:
            for e_nombre, comision_pct, total_generado in resultados:
                pago_estilista = total_generado * (comision_pct / 100.0)
                ganancia_salon = total_generado - pago_estilista

                row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(6))
                lbl = Label(
                    text=f"👤 {e_nombre} ({comision_pct:.0f}%)\\nGen: ${total_generado:.2f} | Pago: ${pago_estilista:.2f} | Salón: ${ganancia_salon:.2f}",
                    font_size='10sp',
                    color=app.text_main_color,
                    halign='left',
                    size_hint_x=1.0
                )
                lbl.bind(size=lbl.setter('text_size'))
                row.add_widget(lbl)
                box.add_widget(row)
        else:
            box.add_widget(Label(text="Sin servicios asignados a estilistas hoy.", font_size='11sp', color=app.text_sec_color))

    def ir_a_trabajo(self):
        self.manager.current = 'work'


class SalonApp(App):
    nombre_negocio = StringProperty("ESTUDIO Y BELLEZA")
    url_servidor = StringProperty(URL_SERVIDOR_DEFAULT)
    licencia_activa = StringProperty("")
    camaras_disponibles = ListProperty([])

    bg_color = ListProperty([0.06, 0.09, 0.16, 1])
    card_color = ListProperty([0.12, 0.16, 0.23, 1])
    accent_color = ListProperty([0.92, 0.28, 0.6, 1])
    text_main_color = ListProperty([1, 1, 1, 1])
    text_sec_color = ListProperty([0.58, 0.64, 0.72, 1])

    TEMAS = [
        {
            "nombre": "Noche Cyber (Oscuro)",
            "bg": [0.06, 0.09, 0.16, 1],
            "card": [0.12, 0.16, 0.23, 1],
            "accent": [0.92, 0.28, 0.6, 1],
            "text_main": [1, 1, 1, 1],
            "text_sec": [0.58, 0.64, 0.72, 1]
        },
        {
            "nombre": "Rosa Glam (Claro)",
            "bg": [0.98, 0.92, 0.95, 1],
            "card": [1, 1, 1, 1],
            "accent": [0.85, 0.2, 0.5, 1],
            "text_main": [0.2, 0.1, 0.15, 1],
            "text_sec": [0.5, 0.4, 0.45, 1]
        },
        {
            "nombre": "Minimalista Azul",
            "bg": [0.94, 0.94, 0.95, 1],
            "card": [1, 1, 1, 1],
            "accent": [0.2, 0.5, 0.9, 1],
            "text_main": [0.1, 0.1, 0.12, 1],
            "text_sec": [0.4, 0.4, 0.45, 1]
        }
    ]

    def obtener_path_licencia(self):
        return os.path.join(self.user_data_dir, "licencia.json")

    def guardar_licencia_local(self, key):
        try:
            with open(self.obtener_path_licencia(), "w", encoding="utf-8") as f:
                json.dump({"licencia": key}, f)
        except Exception as e:
            print(f"Error guardando licencia: {e}")

    def cargar_licencia_local(self):
        path = self.obtener_path_licencia()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("licencia", "")
            except Exception:
                return ""
        return ""

    def on_start(self):
        Clock.schedule_once(solicitar_permisos_android, 0.5)
        self.camaras_disponibles = obtener_camaras_disponibles()

    def aplicar_tema(self, idx):
        t = self.TEMAS[idx]
        self.bg_color = t["bg"]
        self.card_color = t["card"]
        self.accent_color = t["accent"]
        self.text_main_color = t["text_main"]
        self.text_sec_color = t["text_sec"]

    def abrir_catalogo_temas(self):
        contenido = BoxLayout(orientation='vertical', padding=15, spacing=10)
        contenido.add_widget(Label(text="SELECCIONAR TEMA", font_size='15sp', bold=True, size_hint_y=None, height=dp(30)))

        scroll = ScrollView()
        grid = GridLayout(cols=1, spacing=dp(8), size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))

        modal = ModalView(size_hint=(0.8, 0.6), auto_dismiss=True)

        for i, tema in enumerate(self.TEMAS):
            btn = Button(
                text=tema['nombre'],
                size_hint_y=None,
                height=dp(42),
                background_normal='',
                background_color=tema['accent'],
                color=(1, 1, 1, 1)
            )
            btn.bind(on_release=lambda x, idx=i: (self.aplicar_tema(idx), modal.dismiss()))
            grid.add_widget(btn)

        scroll.add_widget(grid)
        contenido.add_widget(scroll)

        btn_cerrar = Button(text="CERRAR", size_hint_y=None, height=dp(38))
        btn_cerrar.bind(on_release=modal.dismiss)
        contenido.add_widget(btn_cerrar)

        modal.add_widget(contenido)
        modal.open()

    def build(self):
        sm = ScreenManager()
        sm.add_widget(ScreenLicencia(name='licencia'))
        sm.add_widget(ScreenConfig(name='config'))
        sm.add_widget(ScreenWork(name='work'))
        sm.add_widget(ScreenFinanzas(name='finanzas'))
        return sm


if __name__ == '__main__':
    SalonApp().run()
