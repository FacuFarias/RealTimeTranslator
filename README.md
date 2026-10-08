# Traductor local de audio

Aplicación portable para **Windows 10 22H2 y Windows 11, de 64 bits**. Transcribe inglés y muestra su traducción al español. Procesa el audio en tu computadora, sin cuentas, servicios externos ni conexión a internet.

## Abrir y usar

Para usar la aplicación en otra PC desde GitHub, descarga `Traductor-Portable.zip` desde **Releases**, extrae el ZIP completo y abre `Traductor.exe` dentro de la carpeta `Traductor`. El ZIP del código fuente de GitHub no contiene los modelos ni las dependencias necesarias para ejecutar la aplicación directamente. No hace falta instalar Python ni descargar modelos después de extraer la versión portable.

1. Abre `dist\Traductor\Traductor.exe`. Para copiarla a otra computadora, copia **toda la carpeta Traductor**, incluidos `_internal`, `models` y `licenses`.
2. Activa **Audio del sistema**, **Micrófono** o ambos. Para videos o reuniones, selecciona la misma salida de audio que usa esa aplicación. Si cambias de auriculares, detén la sesión y pulsa **Actualizar dispositivos**.
3. El modo **Rápido** está seleccionado por defecto para reducir el retraso: procesa bloques de hasta 2,5 segundos y entrega antes las pausas. Puedes elegir **Estándar** para disponer de más contexto y precisión, con bloques de hasta 4,5 segundos. **Priorizar velocidad si aumenta el retraso** cambia de Estándar a Rápido si se acumula audio, conservando los segmentos pendientes. Pulsa **Iniciar** y espera a que el estado indique **Escuchando**.
4. La ventana flotante muestra las últimas frases. Muévela por su barra de título, cambia su tamaño desde los bordes y ajusta letra y opacidad en la ventana principal. Desmarcar **Subtítulos flotantes** los oculta sin detener la sesión.
5. **Pausar** deja de incorporar audio nuevo; el audio anterior termina de procesarse. **Reanudar** continúa la sesión.
6. Pulsa **Detener**, espera a que termine lo pendiente y selecciona **Guardar textos**. El archivo `.txt` UTF-8 incluye marcas de tiempo, fuente, transcripción en inglés y traducción al español.

No se graban archivos de audio. El historial de textos permanece en memoria hasta guardarlo; el programa avisa antes de descartarlo. Un cierre forzado o corte de energía puede perder el historial sin guardar.

## Requisitos y límites

- Windows 10 **22H2** o Windows 11 de **64 bits**, con dispositivos de audio compatibles con WASAPI. No requiere Python instalado.
- CPU con soporte para los modelos CTranslate2; recomendado Intel/AMD moderno, 8 GB de RAM y unos 2 GB libres para la carpeta portable. La implementación utiliza CPU y no requiere CUDA.
- Primera versión: inglés → español. Música, ruido y habla en otros idiomas no son objetivos del reconocimiento.
- Se captura el dispositivo de salida seleccionado, no todas las salidas simultáneamente. Algunas aplicaciones con audio protegido o modo exclusivo pueden impedir la captura.
- La traducción aparece por bloques de hasta cinco segundos; el objetivo de retraso es 3–6 segundos, sujeto al equipo y la carga. El modo rápido reduce consumo a costa de precisión.
- Al usar sistema y micrófono a la vez, utiliza auriculares para evitar que el micrófono capture también los altavoces. No hay separación de hablantes ni cancelación automática de eco.
- Si hay más de 60 segundos de audio pendiente sumando las fuentes, se detiene la captura, se avisa y se procesa lo recibido.
- Los subtítulos funcionan sobre ventanas normales y pantalla completa sin bordes; algunos juegos en pantalla completa exclusiva pueden ocultarlos.
- Si el micrófono no responde, revisa **Configuración → Privacidad → Micrófono** en Windows 10, o **Privacidad y seguridad → Micrófono** en Windows 11, y permite acceso a aplicaciones de escritorio.

## Desarrollo y compilación

Para recompilar, usa la carpeta raíz del proyecto que contiene `pyproject.toml`, `translator` y `scripts` (en esta entrega, `E:\Translator`). La carpeta portable no contiene las herramientas de compilación. Con Python 3.11 de 64 bits:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe scripts\prepare_models.py
.\.venv\Scripts\python.exe scripts\collect_licenses.py
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe main.py
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

La preparación descarga los modelos de reconocimiento `Systran/faster-whisper-small.en`, `Systran/faster-whisper-base.en` y el paquete Argos inglés → español. Las revisiones y el hash del paquete Argos están fijados en `models.lock.json`; también se incluyen en `models\manifest.json`. La aplicación usa rutas locales y no descarga modelos durante las sesiones.

La compilación usa PyInstaller para analizar y recopilar dependencias. El ejecutable PyInstaller queda en `dist\Traductor-PyInstaller`; la entrega principal en `dist\Traductor` incluye el [runtime oficial embebible de CPython](https://docs.python.org/3.11/using/windows.html#windows-embeddable). Su `Traductor.exe` es una copia sin modificaciones del ejecutable gráfico firmado por Python Software Foundation y abre esta aplicación al hacer doble clic. Este empaquetado no modifica las políticas de seguridad de Windows. La primera compilación descarga el ZIP oficial de Python 3.11.9; las siguientes reutilizan `.tools\python-embed.zip`.

La carpeta `diagnostics` contiene una muestra de voz inglesa generada para las pruebas. No es una grabación de una sesión. `Probar-Compatibilidad.cmd` verifica interfaz, exportación y los tres modelos bloqueando conexiones de red de Python, y escribe `autoprueba.json`. Desde PowerShell, la misma prueba se puede ejecutar con `Traductor.exe main.py --self-test --sample diagnostics\sample.wav --report autoprueba.json`.

Para regenerar el entorno de desarrollo sin el archivo de versiones fijadas: `python -m pip install -e ".[build]"`. Usa `scripts\collect_licenses.py` antes de compilar para recopilar avisos de terceros. La inferencia de traducción utiliza el cargador y tokenizador de Argos directamente sobre los bloques ya segmentados, evitando la descarga de recursos de segmentación de Stanza.

## Validación

Consulta `VALIDATION.md` para resultados reales, rendimiento y pruebas pendientes. La compatibilidad prevista con Windows 10 no equivale a una prueba ejecutada en ese sistema.

Fuentes técnicas: [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [Argos Translate](https://github.com/argosopentech/argos-translate), [PySide6](https://doc.qt.io/qtforpython-6/), [PyInstaller](https://pyinstaller.org/en/stable/).
