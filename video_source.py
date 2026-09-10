"""Captura compartida y vigilancia de comandos; importar no conecta hardware."""
import logging
import threading
import time
import cv2
import config as cfg

LOG = logging.getLogger(__name__)


def valid_frame(frame):
    return (frame is not None and frame.ndim == 3 and frame.shape[2] == 3
            and frame.size > 0)


def resize_frame(frame):
    height, width = frame.shape[:2]
    return cv2.resize(frame, (cfg.PROCESS_WIDTH, max(1, round(height * cfg.PROCESS_WIDTH / width))))


class VideoSource:
    def __init__(self, video=None, webcam=None):
        self.video = video
        self.webcam = webcam
        self.tello = None
        self.capture = None
        self.reader = None
        self.stream_attempted = False
        self.connected = False
        self.eof = False
        self.frame_number = 0
        self.fps = cfg.LOCAL_VIDEO_FPS_FALLBACK

    @property
    def is_local(self):
        return self.video is not None or self.webcam is not None

    def open(self):
        if self.is_local:
            self.capture = cv2.VideoCapture(self.video if self.video is not None else self.webcam)
            if not self.capture.isOpened():
                raise RuntimeError('No se pudo abrir video/webcam')
            fps = self.capture.get(cv2.CAP_PROP_FPS)
            if fps > 0 and fps < float('inf'):
                self.fps = fps
        else:
            from djitellopy import Tello
            self.tello = Tello(retry_count=cfg.SDK_RETRIES)
            self.tello.RESPONSE_TIMEOUT = cfg.SDK_COMMAND_TIMEOUT
            self.tello.TAKEOFF_TIMEOUT = cfg.SDK_TAKEOFF_TIMEOUT
            self.tello.connect()
            self.connected = True
            LOG.info('Conectado. Batería: %s%%', self.battery())
            self.stream_attempted = True
            self.tello.streamon()
            # Cola de un frame: no reutilizar un frame congelado ni acumular latencia.
            self.reader = self.tello.get_frame_read(with_queue=True, max_queue_len=1)

    def read(self):
        if self.capture is not None:
            ok, frame = self.capture.read()
            if not ok:
                self.eof = self.video is not None
                return None
        else:
            frame = self.reader.frame
            if not valid_frame(frame):
                return None
            # DJITelloPy 2.5.0 devuelve RGB (PyAV/PIL); OpenCV usa BGR.
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        if not valid_frame(frame):
            return None
        self.frame_number += 1
        return resize_frame(frame)

    def battery(self):
        return self.tello.get_battery() if self.connected else None

    def close(self):
        # Cada recurso se intenta cerrar incluso si falla el anterior.
        actions = []
        if self.capture is not None:
            actions.append(('capture.release', self.capture.release))
        if self.reader is not None:
            actions.append(('reader.stop', self.reader.stop))
        if self.tello is not None:
            if self.stream_attempted:
                actions.append(('streamoff', self.tello.streamoff))
            actions.append(('tello.end', self.tello.end))
        for label, action in actions:
            try:
                action()
            except Exception:
                LOG.exception('No se pudo cerrar %s', label)


class FlightGuard:
    """Un solo emisor RC, periódico, con lease del bucle y telemetría fresca.

    Se construye SÓLO en vuelo real. Si el bucle se atasca, detiene y solicita
    aterrizaje. UDP no garantiza entrega; no sustituye al operador físico.
    """
    def __init__(self, tello, settings=cfg):
        self.tello = tello
        self.cfg = settings
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.command = (0, 0, 0, 0)
        self.deadline = 0.0
        self.fault = ''
        self.last_state = None
        self.last_telemetry = time.monotonic()
        self.thread = None

    def submit(self, command, valid_until=None):
        now = time.monotonic()
        limit = min(self.cfg.MAX_RC_SPEED, 100)
        bounded = tuple(int(max(-limit, min(limit, v))) for v in command)
        with self.lock:
            self.command = bounded
            self.deadline = min(now + self.cfg.COMMAND_TIMEOUT,
                                valid_until if valid_until is not None else float('inf'))

    def health_error(self, now):
        # DJITelloPy 2.5.0 reemplaza el dict en cada datagrama de estado.
        # Se compara identidad, no valores: un dron inmóvil también transmite.
        state = self.tello.get_current_state()
        if state and state is not self.last_state:
            self.last_state = state
            self.last_telemetry = now
        battery = state.get('bat') if state else None
        if battery is not None and battery < self.cfg.MIN_FLIGHT_BATTERY:
            return 'Batería baja'
        if now - self.last_telemetry > self.cfg.TELEMETRY_TIMEOUT:
            return 'Telemetría ausente/congelada'
        return ''

    def start(self):
        self.submit((0, 0, 0, 0))
        self.thread = threading.Thread(target=self._run, name='rc-watchdog', daemon=True)
        self.thread.start()

    def _run(self):
        try:
            while not self.stop_event.is_set():
                now = time.monotonic()
                with self.lock:
                    command, deadline = self.command, self.deadline
                reason = self.health_error(now)
                if now > deadline:
                    reason = reason or 'Bucle de control detenido (watchdog)'
                if reason:
                    self.fault = reason
                    break
                # MOVIMIENTO FÍSICO: único envío periódico de velocidades.
                self.tello.send_rc_control(*command)
                self.stop_event.wait(1 / self.cfg.CONTROL_HZ)
        except Exception as exc:
            self.fault = f'Fallo de comunicación RC: {exc}'
        finally:
            if self.fault:
                LOG.error(self.fault)
                self._zero_and_land()

    def _zero_and_land(self):
        try:
            self.tello.send_rc_control(0, 0, 0, 0)
        except Exception:
            LOG.exception('No se pudo enviar RC cero')
        try:
            # MOVIMIENTO FÍSICO: aterrizaje controlado, no corte de motores.
            self.tello.land()
        except Exception:
            LOG.exception('No se pudo confirmar aterrizaje; requiere operador')

    def close(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(self.cfg.SDK_COMMAND_TIMEOUT * self.cfg.SDK_RETRIES + 2)
        # Reintentar si el aterrizaje del watchdog no se confirmó.
        if not self.fault or self.tello.is_flying:
            self._zero_and_land()
