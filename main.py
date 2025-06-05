import pvporcupine
import sounddevice as sd
import speech_recognition as sr
from gtts import gTTS
from playsound import playsound
import numpy as np
import os
import webbrowser
import json
from datetime import datetime
import threading
from google import genai

# ---------------------------------------------------
# 0) Inicialización de GenAI (Google Gemini) con google-genai
# ---------------------------------------------------
# En lugar de leer la clave desde una variable de entorno, la pegamos directamente aquí:
API_KEY = "AIzaSyBHCR2HrTrQLnyhaRFxii6fkJ1L_U9pQe4"  # <— Reemplaza por tu API Key real

# Creamos el cliente GenAI usando esa misma clave:
client_genai = genai.Client(api_key=API_KEY)

def preguntar_gemini_genai(prompt_text):
    """
    Envía 'prompt_text' al modelo Gemini (gemini-1.5-flash) usando genai.Client
    y devuelve la respuesta limpia, sin "***" ni "**".
    """
    response = client_genai.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt_text
    )

    texto = response.text

    # Eliminar triples asteriscos "***"
    texto = texto.replace("***", "")
    # Eliminar dobles asteriscos "**"
    texto = texto.replace("**", "")
    # Limpiar espacios en blanco al inicio y al final
    texto = texto.strip()

    return texto

# ---------------------------------------------------
# Variables globales y carga del JSON de carreras
# ---------------------------------------------------
conversando = False
buffer_bytes = bytearray()
device_index = None  # None = micrófono predeterminado (en Windows). En Pi, cambiar por índice ALSA.

with open("carreras.json", "r", encoding="utf-8") as f:
    carreras = json.load(f)

access_key = "k5hC+zp+caYClUGXqwCL3MDhMNBBEWsLcQHUXyAt4wN6CMRd4t1ePg=="
porcupine = pvporcupine.create(
    access_key=access_key,
    model_path="porcupine_params_es.pv",
    keyword_paths=["hola-sena-ti_es_windows_v3_0_0.ppn"]
)

# ---------------------------------------------------
# 1) Función TTS (gTTS + playsound + borrado con timestamp)
# ---------------------------------------------------
def hablar(texto):
    """
    Genera un archivo MP3 con gTTS, lo reproduce con playsound y luego lo borra.
    """
    ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
    filename = f"respuesta_{ts}.mp3"
    tts = gTTS(text=texto, lang="es")
    tts.save(filename)
    playsound(filename)
    try:
        os.remove(filename)
    except OSError:
        pass

# ---------------------------------------------------
# 2) Función para procesar intenciones (incluye llamada a Gemini)
# ---------------------------------------------------
def procesar_intencion(texto):
    """
    Procesa el 'texto' recibido (en minúsculas) y devuelve:
      - respuesta_para_TTS (string)
      - termino_busqueda (string o None)
    Intenciones locales:
      • Lista de carreras: si aparece “carr…” + (“tienes”|“tiene”|“ofrecen”|“ofrece”|“otra”|“otras”|“más”).
      • Descripción de carrera: si aparece un nombre clave de 'carreras.json' en el texto.
      • Hora: si aparece la palabra “hora”.
      • Búsqueda en Google: si el texto empieza con “busca” o contiene “busca”.
    Si no coincide ninguna, invoca a Gemini (GenAI) y limpia la respuesta.
    """
    if not texto:
        return None, None

    palabras = texto.split()

    # 2.1) Pregunta por lista de carreras
    contiene_carr = any(pal.startswith("carr") for pal in palabras)
    if contiene_carr and any(cond in palabras for cond in ["tienes", "tiene", "ofrecen", "ofrece", "otra", "otras", "más"]):
        lista = ", ".join(carreras.keys())
        return f"Tenemos estas carreras: {lista}. ¿Cuál te interesa saber más?", None

    # 2.2) Descripción de una carrera específica
    for nombre_carrera, descripcion in carreras.items():
        if nombre_carrera in texto:
            return descripcion, None

    # 2.3) Pregunta por la hora
    if "hora" in palabras:
        ahora = datetime.now().strftime("%H:%M")
        return f"La hora actual es {ahora}.", None

    # 2.4) Búsqueda en Google
    if texto.startswith("busca ") or "busca" in palabras:
        termino = texto.replace("busca", "").strip()
        if termino:
            return f"Buscando {termino} en Google...", termino

    # 2.5) Fallback: invocar a Gemini (GenAI)
    try:
        gemini_resp = preguntar_gemini_genai(texto)
        return gemini_resp, None
    except Exception as e:
        print("Error al llamar a Gemini (GenAI):", e)
        return "Lo siento, en este momento no puedo responder a eso.", None

# ---------------------------------------------------
# 3) Modo conversación (escucha libre sin wake word)
# ---------------------------------------------------
def escuchar_libre():
    """
    Modo conversación: mientras conversando == True, graba audio con STT.
    Si detecta silencio prolongado (sr.WaitTimeoutError), termina este modo y regresa al wake word.
    """
    global conversando
    r = sr.Recognizer()
    mic = sr.Microphone()

    # Calibrar ruido ambiental 1 segundo
    with mic as source:
        r.adjust_for_ambient_noise(source, duration=1)

    while conversando:
        with mic as source:
            print("Modo conversación: escuchando tu pregunta (silencio = volver a wake word)…")
            try:
                audio_data = r.listen(source, timeout=3, phrase_time_limit=5)
            except sr.WaitTimeoutError:
                print("Silencio prolongado. Volviendo a modo wake word.")
                conversando = False
                break

        try:
            texto = r.recognize_google(audio_data, language="es-ES").lower().strip()
            print("Usuario dijo (modo libre):", texto)
            respuesta, termino_busqueda = procesar_intencion(texto)

            if termino_busqueda:
                webbrowser.open(f"https://www.google.com/search?q={termino_busqueda}")
            if respuesta:
                hablar(respuesta)
        except sr.UnknownValueError:
            hablar("No entendí, intenta de nuevo.")
        except sr.RequestError:
            hablar("Error de conexión en el servicio de reconocimiento.")

    print("Modo conversación inactivo. Volviendo a escucha wake word.")

# ---------------------------------------------------
# 4) Callback de Porcupine (espera wake word)
# ---------------------------------------------------
def callback(indata, frames, time, status):
    """
    Cada vez que llegan N muestras (512 muestras × 2 bytes = 1024 bytes),
    acumulamos en buffer_bytes. Si conversando == False, procesamos con Porcupine.
    Al detectarse la wake word, ponemos conversando = True, saludamos y lanzamos hilo de conversación.
    """
    global buffer_bytes, conversando

    if status:
        print("Warning (sounddevice):", status)

    # Si estamos en modo conversación, no procesamos Porcupine
    if conversando:
        return

    pcm_bytes = indata[:, 0].tobytes()
    buffer_bytes.extend(pcm_bytes)
    frame_byte_len = porcupine.frame_length * 2  # 512 muestras × 2 bytes = 1024 bytes

    while len(buffer_bytes) >= frame_byte_len:
        chunk_bytes = buffer_bytes[:frame_byte_len]
        buffer_bytes = buffer_bytes[frame_byte_len:]
        pcm_int16 = np.frombuffer(chunk_bytes, dtype=np.int16)

        if porcupine.process(pcm_int16) >= 0:
            print("Wake word ‘Hola Senati’ detectada!")
            conversando = True
            hablar("Hola, ¿en qué puedo ayudarte?")
            hilo = threading.Thread(target=escuchar_libre, daemon=True)
            hilo.start()
            break

# ---------------------------------------------------
# 5) Loop principal
# ---------------------------------------------------
print("Inicializando asistente con GenAI (Gemini)…")
stream = sd.InputStream(
    device=device_index,
    channels=1,
    samplerate=porcupine.sample_rate,
    blocksize=porcupine.frame_length,
    dtype="int16",
    callback=callback
)

try:
    print("Esperando 'Hola Senati'… (Ctrl+C para salir)")
    with stream:
        while True:
            sd.sleep(1000)
except KeyboardInterrupt:
    print("\nPrograma detenido por usuario.")
finally:
    porcupine.delete()
    stream.close()
