# Muestras para pruebas

No se incluyen grabaciones reales ni resultados de precisión inventados.
Genera un video sintético verde con `python samples/generate_sample.py` desde la
raíz. Produce `samples/synthetic_gate.avi` (MJPG, 640×480, 20 FPS, 240 frames).
El gate se desplaza al centro y crece: permite recorrer estados sin hardware.

Para agregar datos reales:

1. Graba desde la cámara del Tello con gate quieto a diversas distancias/ángulos.
2. Incluye escenas sin gate, fondo del mismo color, oclusión, cambios de luz y movimiento.
3. Guarda el archivo como `gate_test.mp4` o pasa otra ruta a `--video`.
4. Registra resolución, FPS, color, iluminación, distancia medida, fecha y parámetros HSV.
5. Etiqueta frames con presencia/ausencia, bbox y centro esperado; usa fixtures de
   OpenCV en `tests/test_detector.py` para compararlos con tolerancias explícitas.
6. Separa videos de calibración y evaluación antes de calcular falsos positivos,
   falsos negativos o errores de centro. Reporta cantidad de frames y condiciones.

Los videos y CSV están excluidos de Git por tamaño; compártelos por separado o
añade una muestra pequeña explícitamente. Los FPS reportados por main en headless
son de procesamiento, no una medición de latencia del enlace del Tello.
