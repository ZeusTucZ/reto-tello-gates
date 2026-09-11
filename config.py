"""Parámetros iniciales de laboratorio; NINGUNO está calibrado con vuelo real.

Velocidades en unidades RC [-100, 100], no una distancia/velocidad medida.
Áreas y tamaños en píxeles de PROCESS_WIDTH; errores/deadbands normalizados.
"""

DRY_RUN = False
PROCESS_WIDTH = 640
CONTROL_HZ = 20
SHOW_MASK = True
LOCAL_VIDEO_FPS_FALLBACK = 30.0

# Ejemplo AZUL: sustituir por los valores de hsv_calibration.py.
HSV_MIN = (100, 80, 60)
HSV_MAX = (130, 255, 255)
MIN_CONTOUR_AREA = 1500
MIN_GATE_SIZE = 45
ASPECT_RATIO_TOLERANCE = 0.45  # acepta [1-tolerancia, 1/(1-tolerancia)]
MIN_RECTANGULARITY = 0.60     # área exterior / área bounding box
POLYGON_EPSILON = 0.03        # fracción del perímetro
MIN_POLYGON_VERTICES = 4
MAX_POLYGON_VERTICES = 6
REQUIRE_HOLE = True          # gate de marco coloreado, no un panel sólido
MIN_HOLE_AREA_RATIO = 0.25   # hueco interior / área exterior
MAX_HOLE_AREA_RATIO = 0.95
MORPH_KERNEL_SIZE = 3        # impar
MORPH_OPEN_ITERATIONS = 1
MORPH_CLOSE_ITERATIONS = 2
DETECTED_FRAMES = 1
MAX_CENTER_JUMP = 0.15       # distancia normalizada por diagonal entre frames
MAX_SIZE_CHANGE = 1.5        # cociente máximo de ancho entre frames

# u = Kp * error. Kp ya está en unidades RC por unidad de error.
KP_X = 80.0
KP_Y = 80.0
MAX_LR_SPEED = 30
MAX_UD_SPEED = 30
DEADBAND_X = 0.08
DEADBAND_Y = 0.08
EMA_ALPHA = 1.0             # 1 = sin suavizado; menor = más retardo

APPROACH_SPEED = 8
CROSS_SPEED = 30              # avance RC reducido; no es velocidad medida
CROSS_DURATION = 4.0         # segundos; NO garantiza cruzar 1 m
CLOSE_WIDTH_RATIO = 0.60     # tamaño aparente, NO distancia métrica
ALIGNED_FRAMES = 5
CROSS_STABLE_FRAMES = 8
REALIGN_MULTIPLIER = 1.5     # histéresis al salir de APPROACH
LOST_FRAMES = 3
DONE_HOVER_SECONDS = 1.0

MIN_TAKEOFF_BATTERY = 40
MIN_FLIGHT_BATTERY = 25
MAX_RC_SPEED = 30             # límite global adicional conservador
GATE_LOSS_TIMEOUT = 20.0      # espera sin movimiento por detección estable antes de aterrizar
FRAME_TIMEOUT = 1.0
TELEMETRY_TIMEOUT = 3.0
PRE_FLIGHT_TIMEOUT = 15.0
MAX_FLIGHT_SECONDS = 60.0
TAKEOFF_SETTLE_SECONDS = 2.0
COMMAND_TIMEOUT = 0.5        # watchdog: RC cero si el bucle se bloquea
SDK_COMMAND_TIMEOUT = 7.0
SDK_TAKEOFF_TIMEOUT = 20.0
SDK_RETRIES = 2
HUD_LOG_INTERVAL = 1

ADVANCE_PULSE_SECONDS = 0.4  # punto de partida; requiere calibración
FINAL_ADVANCE_SECONDS = 3.0  # único avance adicional tras perder el gate; luego aterriza


def validate():
    """Rechazar configuración peligrosa antes de conectar/despegar."""
    import math

    for name, value in globals().items():
        if name.isupper() and isinstance(value, (int, float)):
            if not math.isfinite(value):
                raise ValueError(f'{name} debe ser finito')
    for low, high, maximum in zip(HSV_MIN, HSV_MAX, (179, 255, 255)):
        if not 0 <= low <= high <= maximum:
            raise ValueError('HSV_MIN/MAX inválidos (H: 0..179; S/V: 0..255)')
    if len(HSV_MIN) != 3 or len(HSV_MAX) != 3:
        raise ValueError('HSV necesita tres componentes')
    for name in ('PROCESS_WIDTH', 'DETECTED_FRAMES', 'ALIGNED_FRAMES',
                 'CROSS_STABLE_FRAMES', 'LOST_FRAMES', 'MORPH_KERNEL_SIZE',
                 'MIN_GATE_SIZE', 'SDK_RETRIES'):
        value = globals()[name]
        if not isinstance(value, int) or value < 1:
            raise ValueError(f'{name} debe ser entero positivo')
    if MORPH_KERNEL_SIZE % 2 == 0:
        raise ValueError('MORPH_KERNEL_SIZE debe ser impar')
    for name in ('MORPH_OPEN_ITERATIONS', 'MORPH_CLOSE_ITERATIONS'):
        if not isinstance(globals()[name], int) or globals()[name] < 0:
            raise ValueError(f'{name} debe ser entero no negativo')
    if not 0 < MAX_RC_SPEED <= 100:
        raise ValueError('MAX_RC_SPEED debe estar en (0, 100]')
    for name in ('MAX_LR_SPEED', 'MAX_UD_SPEED', 'APPROACH_SPEED', 'CROSS_SPEED'):
        if not isinstance(globals()[name], int) or not 0 <= globals()[name] <= MAX_RC_SPEED:
            raise ValueError(f'{name} debe ser entero entre 0 y MAX_RC_SPEED')
    if KP_X < 0 or KP_Y < 0 or not 0 < EMA_ALPHA <= 1:
        raise ValueError('Kp debe ser no negativo y EMA_ALPHA estar en (0,1]')
    for name in ('DEADBAND_X', 'DEADBAND_Y', 'CLOSE_WIDTH_RATIO',
                 'ASPECT_RATIO_TOLERANCE', 'MAX_CENTER_JUMP', 'POLYGON_EPSILON'):
        if not 0 < globals()[name] < 1:
            raise ValueError(f'{name} debe estar en (0,1)')
    if not 0 < MIN_RECTANGULARITY <= 1:
        raise ValueError('MIN_RECTANGULARITY inválida')
    if not 0 <= MIN_HOLE_AREA_RATIO < MAX_HOLE_AREA_RATIO <= 1:
        raise ValueError('Ratios de hueco inválidos')
    if not 3 <= MIN_POLYGON_VERTICES <= MAX_POLYGON_VERTICES:
        raise ValueError('Límites de vértices inválidos')
    if not 0 <= MIN_FLIGHT_BATTERY <= MIN_TAKEOFF_BATTERY <= 100:
        raise ValueError('Límites de batería inválidos')
    if REALIGN_MULTIPLIER < 1 or MAX_SIZE_CHANGE < 1:
        raise ValueError('Multiplicadores deben ser >= 1')
    for name in ('CONTROL_HZ', 'MIN_CONTOUR_AREA', 'CROSS_DURATION',
                 'ADVANCE_PULSE_SECONDS', 'FINAL_ADVANCE_SECONDS',
                 'GATE_LOSS_TIMEOUT', 'FRAME_TIMEOUT', 'TELEMETRY_TIMEOUT',
                 'PRE_FLIGHT_TIMEOUT', 'MAX_FLIGHT_SECONDS', 'COMMAND_TIMEOUT',
                 'SDK_COMMAND_TIMEOUT', 'SDK_TAKEOFF_TIMEOUT', 'LOCAL_VIDEO_FPS_FALLBACK', 'HUD_LOG_INTERVAL'):
        if globals()[name] <= 0:
            raise ValueError(f'{name} debe ser positivo')
    if DONE_HOVER_SECONDS < 0 or TAKEOFF_SETTLE_SECONDS < 0:
        raise ValueError('Tiempos de hover deben ser no negativos')
    if COMMAND_TIMEOUT <= 1 / CONTROL_HZ:
        raise ValueError('COMMAND_TIMEOUT debe superar un período de control')
