# Validación

## Entorno disponible

Pruebas realizadas el 8 de octubre de 2026 en Windows 11 Pro de 64 bits, compilación 26200, Intel Core i5-12450H (8 núcleos / 12 hilos), 31.7 GB de RAM. La aplicación utiliza CPU; no necesita la GPU NVIDIA ni CUDA.

Windows 10 22H2 de 64 bits es el objetivo de compatibilidad, pero **no se ha ejecutado una prueba en Windows 10**: no hay una segunda computadora ni una VM de ese sistema disponible en este entorno. La [matriz de Qt 6.8](https://doc.qt.io/qt-6.8/supported-platforms.html) incluye Windows 10 y 11; [CPython 3.11](https://docs.python.org/3.11/using/windows.html) también contempla Windows 10. Esto respalda la elección de dependencias, pero no sustituye una prueba completa de la aplicación.

## Resultados ejecutados

- **22 pruebas automatizadas aprobadas:** orden temporal de dos fuentes, exportación UTF-8 y escritura atómica, conservación de un archivo previo ante error, solapamiento de bloques sin repetir palabras recortadas, conversión de audio estéreo, detención por exceso de cola, vaciado al detener, cambio adaptativo de modelo conservando todos los segmentos, pausa y reanudación, desconexión, apertura serializada de PortAudio, detención con loopback inactivo, micrófono sin loopback, cancelación del guardado y controles y ajuste de altura de subtítulos.
- **Captura WASAPI simultánea aprobada:** salida Bluetooth G435 y micrófono Intel Smart Sound. El audio inglés sintético reproducido se reconoció correctamente. Del micrófono se guardaron únicamente métricas; no se almacenaron ni su audio ni su transcripción.
- **Carpeta portable aprobada:** traducción Argos, carga y reconocimiento con `small.en` y `base.en`, interfaz, exportación y detección de dispositivos. La prueba bloqueó las conexiones de red de Python y no detectó intentos de conexión.
- **Apertura por doble clic aprobada:** `Traductor.exe` sin argumentos abrió la ventana desde un directorio distinto al de la aplicación. El `PATH` se limitó a Windows; los módulos y modelos se cargaron exclusivamente desde la carpeta portable.
- **Firma del runtime:** `Get-AuthenticodeSignature` devolvió `Valid` para `Traductor.exe`, copia sin modificaciones de `pythonw.exe` del paquete oficial de Python Software Foundation. La firma pertenece al runtime; el código de esta aplicación se distribuye como archivos Python.

El ejecutable sin firma de PyInstaller fue bloqueado por el Control de aplicaciones de este equipo. Por eso la entrega principal usa el runtime oficial incluido. No se cambiaron políticas ni ajustes de seguridad de Windows. El resultado de PyInstaller se conserva por separado para compilación y eventual firma de una distribución.

## Rendimiento

El modo Estándar completó 900 segundos de audio sintético, produjo 333 segmentos y terminó sin errores ni audio pendiente. Mediana de retraso: **3.106 s**; percentil 95: **10.374 s**; máximo: **37.053 s**. La cola llegó a 27 segundos de audio y se vació al detener. Por tanto, **el modelo Estándar fijo no mantuvo el objetivo de 3–6 segundos durante toda la prueba**.

La versión inicial empezaba en Estándar. La actualización para reducir el retraso empieza en Rápido y usa bloques de hasta 2,5 segundos en ese modo, manteniendo 4,5 segundos en Estándar. Con **Priorizar velocidad si aumenta el retraso** activado, si hay más de 18 segundos de audio pendiente en Estándar cambia a `base.en` sin descartar segmentos. El cambio y la conservación de la cola se verificaron con pruebas automatizadas. La medición prolongada de abajo corresponde a los bloques anteriores de 4,5 segundos, con modelos fijos, sin ese cambio automático.

El modo Rápido completó 900 segundos de audio sintético, produjo 425 segmentos y terminó sin errores ni audio pendiente. Mediana de retraso: **3.158 s**; percentil 95: **5.636 s**; máximo: **6.852 s**. La cola máxima fue de 9 segundos de audio, sin crecimiento sostenido. El 95 % de las entregas quedó dentro de 6 segundos; hubo picos por encima del objetivo. Ambas sesiones se ejecutaron sin intentos de conexión. El informe completo está en `validation/benchmark-15min.json`.

La prueba utiliza una muestra inglesa sintética de 11.408 segundos repetida con pausas, enviada a ritmo real por el mismo motor de reconocimiento y traducción que utiliza la aplicación. Evalúa una fuente, con bloques de hasta 4.5 segundos y 0.5 segundos de solapamiento. **No es una prueba de 15 minutos de dispositivos físicos**, ni una garantía de precisión con conversaciones naturales o voces superpuestas. El objetivo de retraso se mide desde el final de cada segmento reconocido hasta la entrega de su traducción.

## Pruebas pendientes que requieren otro entorno

### Actualización de menor retraso

La actualización pasó 23 pruebas automatizadas, incluida la división de audio en bloques cortos con solapamiento y vaciado completo al detener. En dos sesiones sintéticas de 60 segundos usando `base.en`, el retraso desde el final del segmento hasta su traducción cambió de mediana 1.774 s / percentil 95 4.100 s / máximo 4.619 s (bloques de 4,5 s) a mediana 1.134 s / percentil 95 2.319 s / máximo 2.635 s (bloques de 2,5 s). Ambas terminaron sin errores ni audio pendiente. Informes: `validation/latency-before.json` y `validation/latency-after.json`. La reducción de contexto puede cortar frases y disminuir precisión; no se ha repetido la prueba de 15 minutos con esta configuración. Las sesiones breves tuvieron unos segundos de solapamiento al cargar la segunda; no son un ensayo controlado de aislamiento de CPU.

1. En Windows 10 22H2 x64, copiar toda la carpeta `dist\Traductor` y ejecutar `Probar-Compatibilidad.cmd`; revisar que `autoprueba.json` indique `success: true` y `network_attempts: []`.
2. En ese equipo, probar salida y micrófono por separado y juntos, subtítulos sobre una reunión, pausa y reanudación, desconexión física y exportación.
3. Medir conversaciones naturales y uso prolongado con dos fuentes hablando a la vez, especialmente en equipos menos potentes. La biblioteca de audio puede responder de forma distinta según el controlador.

Los casos de desconexión y exceso de cola se verificaron también con pruebas simuladas para comprobar la conservación de los textos. No se desconectaron físicamente dispositivos ni se cambiaron permisos del sistema durante la validación.
