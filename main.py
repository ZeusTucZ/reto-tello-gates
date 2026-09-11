"""Fase 2: máquina de estados explícita y ejecución segura por defecto."""
import argparse
import csv
from enum import Enum
import logging
import math
from pathlib import Path
import time
import threading
import cv2
import config as cfg
from controller import PController
from gate_detector import GateDetection, GateDetector, draw_debug, normalized_error
from video_source import FlightGuard, VideoSource

LOG = logging.getLogger(__name__)
ZERO = (0, 0, 0, 0)


class State(str, Enum):
    PRE_FLIGHT = 'PRE_FLIGHT'
    SEARCH = 'SEARCH'
    ALIGN = 'ALIGN'
    APPROACH = 'APPROACH'
    CROSS = 'CROSS'
    FINAL_ADVANCE = 'FINAL_ADVANCE'
    DONE = 'DONE'
    EMERGENCY = 'EMERGENCY'


class Navigation:
    """Lógica pura sin hardware. now se inyecta para tests y video grabado."""
    def __init__(self, settings=cfg, stage='full'):
        self.cfg = settings
        self.stage = stage
        self.controller = PController(settings)
        self.state = State.PRE_FLIGHT
        self.detected_frames = self.aligned_frames = self.lost_frames = 0
        self.close_frames = 0
        self.previous = None
        self.last_seen = None
        self.started_at = None
        self.cross_started = None
        self.has_advanced = False
        self.done_started = None
        self.errors = (0.0, 0.0)
        self.reason = ''

    def start(self, now):
        self.started_at = self.last_seen = now
        self.state = State.SEARCH

    def abort(self, reason):
        self.state = State.EMERGENCY
        self.reason = reason
        self.controller.reset()
        return ZERO

    def same_target(self, detection, shape):
        if self.previous is None:
            return True
        distance = math.hypot(detection.center_x - self.previous.center_x,
                              detection.center_y - self.previous.center_y)
        old_w, new_w = self.previous.bbox[2], detection.bbox[2]
        size_change = max(old_w, new_w) / max(1, min(old_w, new_w))
        return (distance / math.hypot(*shape[:2]) <= self.cfg.MAX_CENTER_JUMP
                and size_change <= self.cfg.MAX_SIZE_CHANGE)

    def update(self, detection, shape, now):
        self.errors = normalized_error(detection, shape)
        if self.state in (State.PRE_FLIGHT, State.DONE, State.EMERGENCY):
            return ZERO
        if now - self.started_at >= self.cfg.MAX_FLIGHT_SECONDS:
            return self.abort('Tiempo máximo de misión')
        if self.state in (State.CROSS, State.FINAL_ADVANCE):
            duration = (self.cfg.FINAL_ADVANCE_SECONDS if self.state == State.FINAL_ADVANCE
                        else self.cfg.ADVANCE_PULSE_SECONDS)
            if now - self.cross_started >= duration:
                if self.state == State.FINAL_ADVANCE:
                    self.state = State.DONE
                    self.done_started = now
                else:
                    self.has_advanced = True
                    self.state = State.ALIGN
                    self.aligned_frames = self.detected_frames = self.close_frames = 0
                    self.lost_frames = 0
                    self.previous = None
                    self.controller.reset()
                return ZERO
            return (0, self.cfg.CROSS_SPEED, 0, 0)
        if self.stage == 'hover':
            return ZERO
        if not detection.detected:
            self.lost_frames += 1
            self.detected_frames = self.aligned_frames = self.close_frames = 0
            self.previous = None
            self.controller.reset()
            if self.state == State.APPROACH:
                self.state = State.ALIGN
            if now - self.last_seen >= self.cfg.GATE_LOSS_TIMEOUT:
                return self.abort('Pérdida prolongada del gate')
            if self.lost_frames >= self.cfg.LOST_FRAMES:
                if self.stage == 'full' and self.has_advanced:
                    self.state = State.FINAL_ADVANCE
                    self.cross_started = now
                    return (0, self.cfg.CROSS_SPEED, 0, 0)
                self.state = State.SEARCH
            return ZERO  # frenar desde el PRIMER frame perdido
        if not self.same_target(detection, shape):
            self.detected_frames = self.aligned_frames = self.close_frames = 0
            self.state = State.SEARCH
            self.controller.reset()
        self.previous = detection
        self.detected_frames += 1
        self.lost_frames = 0
        if self.detected_frames < self.cfg.DETECTED_FRAMES:
            if self.state == State.APPROACH:
                self.state = State.ALIGN
            if now - self.last_seen >= self.cfg.GATE_LOSS_TIMEOUT:
                return self.abort('No se obtiene detección estable')
            return ZERO
        self.last_seen = now
        if self.state == State.SEARCH:
            self.state = State.ALIGN
        x, y = self.errors
        aligned = abs(x) <= self.cfg.DEADBAND_X and abs(y) <= self.cfg.DEADBAND_Y
        self.aligned_frames = self.aligned_frames + 1 if aligned else 0
        close = aligned and detection.width_ratio >= self.cfg.CLOSE_WIDTH_RATIO
        self.close_frames = self.close_frames + 1 if close else 0
        lr, ud = self.controller.update(x, y)
        if self.stage == 'horizontal':
            return (lr, 0, 0, 0)
        if self.stage == 'align':
            return (lr, 0, ud, 0)
        if self.state == State.APPROACH and (
            abs(x) > self.cfg.DEADBAND_X * self.cfg.REALIGN_MULTIPLIER or
            abs(y) > self.cfg.DEADBAND_Y * self.cfg.REALIGN_MULTIPLIER
        ):
            self.state = State.ALIGN
            self.aligned_frames = self.close_frames = 0
        if self.state == State.ALIGN and self.aligned_frames >= self.cfg.ALIGNED_FRAMES:
            if self.stage == 'full':
                # Alineación confirmada: un pulso recto antes de realinear.
                self.state = State.CROSS
                self.cross_started = now
                self.controller.reset()
                return (0, self.cfg.CROSS_SPEED, 0, 0)
            self.state = State.APPROACH
        # Etapa approach se detiene al alcanzar proximidad sin ejecutar CROSS.
        forward = self.cfg.APPROACH_SPEED if self.state == State.APPROACH else 0
        if self.stage == 'approach' and detection.width_ratio >= self.cfg.CLOSE_WIDTH_RATIO:
            forward = 0
        return (lr, forward, ud, 0)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--video', help='Archivo local (siempre DRY RUN)')
    source.add_argument('--webcam', type=int, help='Índice webcam (siempre DRY RUN)')
    parser.add_argument('--dry-run', action='store_true', help='Forzar ausencia de movimiento')
    parser.add_argument('--stage', choices=['hover', 'horizontal', 'align', 'approach', 'full'],
                        default='full', help='Límite de autonomía para pruebas progresivas')
    parser.add_argument('--headless', action='store_true', help='Sin GUI; sólo DRY RUN')
    parser.add_argument('--max-frames', type=int, default=0, help='0 = sin límite')
    parser.add_argument('--log-csv', type=Path, help='Registro de estados, errores y comandos')
    args = parser.parse_args(argv)
    if args.max_frames < 0:
        parser.error('--max-frames debe ser >= 0')
    return args


def run(args):
    cfg.validate()
    source = VideoSource(args.video, args.webcam)
    dry_run = cfg.DRY_RUN or args.dry_run or source.is_local
    if args.headless and not dry_run:
        raise ValueError('El vuelo real requiere GUI para armado y emergencia')
    nav = Navigation(stage=args.stage)
    detector = GateDetector()
    guard = None
    takeoff_attempted = False
    takeoff_thread = None
    takeoff_errors = []
    log_file = None
    processed = 0
    commands = ZERO
    last_frame = None
    last_mask = None
    detection = GateDetection()
    start_wall = last_frame_at = time.monotonic()
    last_log = 0.0
    settle_until = None
    exit_code = 0
    try:
        if args.log_csv:
            log_file = args.log_csv.open('w', newline='', encoding='utf-8')
            writer = csv.writer(log_file)
            writer.writerow(['time', 'state', 'detected', 'error_x', 'error_y',
                             'lr', 'fb', 'ud', 'yaw', 'width_ratio'])
        source.open()
        battery = source.battery()
        if not dry_run and (battery is None or battery < cfg.MIN_TAKEOFF_BATTERY):
            raise RuntimeError('Batería insuficiente para permitir despegue')
        LOG.info('Modo %s | etapa %s', 'DRY RUN' if dry_run else 'VUELO: despegue automatico al recibir video valido', args.stage)
        start_wall = last_frame_at = time.monotonic()
        period = 1 / (source.fps if args.video else cfg.CONTROL_HZ)
        while True:
            tick = time.monotonic()
            if guard and guard.fault:
                raise RuntimeError(guard.fault)
            # Procesar tecla antes de calcular/enviar otro comando.
            key = (cv2.waitKey(1) & 0xFF) if not args.headless else -1
            if key in (27, ord('q')):
                nav.abort('Parada manual')
                break
            frame = source.read()
            fresh = frame is not None
            if fresh:
                last_frame = frame
                last_frame_at = tick
                processed += 1
                detection, last_mask = detector.detect(frame)
            else:
                detection = GateDetection()
            # El video grabado usa tiempo de contenido, incluso en headless rápido.
            now = source.frame_number / source.fps if args.video else tick
            if last_frame is None:
                if source.eof or tick - start_wall > cfg.PRE_FLIGHT_TIMEOUT:
                    raise RuntimeError('PRE_FLIGHT: no llegaron frames válidos')
            elif nav.state == State.PRE_FLIGHT:
                if dry_run:
                    nav.start(now)
                elif fresh and not takeoff_attempted:
                    battery = source.battery()
                    if battery is None or battery < cfg.MIN_TAKEOFF_BATTERY:
                        raise RuntimeError('Batería insuficiente al armar')
                    # Exigir telemetría que se actualiza, no sólo batería cacheada.
                    state_before = source.tello.get_current_state()
                    deadline = time.monotonic() + cfg.TELEMETRY_TIMEOUT
                    while source.tello.get_current_state() is state_before:
                        if time.monotonic() > deadline:
                            raise RuntimeError('No hay telemetría fresca antes del despegue')
                        if cv2.waitKey(1) & 0xFF in (27, ord('q')):
                            raise KeyboardInterrupt
                        time.sleep(1 / cfg.CONTROL_HZ)
                    takeoff_attempted = True  # incluso si se pierde la confirmación SDK
                    # MOVIMIENTO FÍSICO: vuelo habilitado, video y telemetría válidos.
                    # El SDK bloquea durante takeoff; otro hilo mantiene GUI/ESC vivos.
                    def takeoff_worker():
                        try:
                            source.tello.takeoff()
                        except Exception as exc:
                            takeoff_errors.append(exc)
                    takeoff_thread = threading.Thread(target=takeoff_worker, daemon=True)
                    takeoff_thread.start()
                elif takeoff_thread is not None and not takeoff_thread.is_alive():
                    if takeoff_errors:
                        raise RuntimeError(f'Takeoff no confirmado: {takeoff_errors[0]}')
                    guard = FlightGuard(source.tello)
                    guard.start()
                    now = time.monotonic()
                    nav.start(now)
                    settle_until = now + cfg.TAKEOFF_SETTLE_SECONDS
                    last_frame_at = now
                    # Descartar el frame anterior al despegue.
                    fresh = False
                    detection = GateDetection()
            if source.eof:
                LOG.info('Fin del video local')
                break
            if nav.state != State.PRE_FLIGHT:
                if tick - last_frame_at > cfg.FRAME_TIMEOUT:
                    raise RuntimeError('Video ausente/congelado')
                if settle_until is not None and now < settle_until:
                    commands = ZERO
                    nav.last_seen = now
                elif fresh:
                    commands = nav.update(detection, last_frame.shape, now)
                elif nav.state in (State.CROSS, State.FINAL_ADVANCE):
                    # Falta de contorno es normal; fallo del stream no lo es.
                    commands = nav.update(detection, last_frame.shape, now)
                else:
                    commands = ZERO
                    # No contar ticks sin frame como observaciones distintas.
                    nav.controller.reset()
                if guard:
                    valid_until = None
                    if nav.state in (State.CROSS, State.FINAL_ADVANCE):
                        duration = (cfg.FINAL_ADVANCE_SECONDS if nav.state == State.FINAL_ADVANCE
                                    else cfg.ADVANCE_PULSE_SECONDS)
                        valid_until = nav.cross_started + duration + 1 / cfg.CONTROL_HZ
                    guard.submit(commands, valid_until)
            if fresh:
                battery = source.battery()
                if log_file:
                    writer.writerow([now, nav.state.value, detection.detected, *nav.errors,
                                     *commands, detection.width_ratio])
                if now - last_log >= cfg.HUD_LOG_INTERVAL:
                    LOG.info('State=%s e=(%+.3f,%+.3f) rc=%s ratio=%.3f',
                             nav.state.value, *nav.errors, commands, detection.width_ratio)
                    last_log = now
            if not args.headless and last_frame is not None:
                fps = processed / max(time.monotonic() - start_wall, 1e-6)
                overlay = draw_debug(last_frame, detection, nav.state.value, nav.errors,
                                     commands, fps, battery, dry_run,
                                     f'detected={nav.detected_frames} aligned={nav.aligned_frames} lost={nav.lost_frames}')
                cv2.imshow('Tello Gate', overlay)
                if cfg.SHOW_MASK and last_mask is not None:
                    cv2.imshow('HSV mask', last_mask)
                if cv2.getWindowProperty('Tello Gate', cv2.WND_PROP_VISIBLE) < 1:
                    nav.abort('Ventana cerrada')
                    break
            if nav.state == State.EMERGENCY:
                raise RuntimeError(nav.reason)
            if nav.state == State.DONE and now - nav.done_started >= cfg.DONE_HOVER_SECONDS:
                break
            if args.max_frames and processed >= args.max_frames:
                break
            if not (args.headless and args.video):
                time.sleep(max(0, period - (time.monotonic() - tick)))
    except KeyboardInterrupt:
        nav.abort('Ctrl+C')
        LOG.warning('Interrupción manual')
    except Exception as exc:
        nav.abort(str(exc))
        LOG.exception('EMERGENCY: %s', exc)
        exit_code = 1
    finally:
        try:
            if guard:
                guard.close()
            elif takeoff_attempted:
                # RC cero inmediato; SDK takeoff no es cancelable en pleno ascenso.
                try:
                    source.tello.send_rc_control(*ZERO)
                except Exception:
                    LOG.exception('No se pudo enviar RC cero durante takeoff')
                if takeoff_thread is not None:
                    takeoff_thread.join(cfg.SDK_TAKEOFF_TIMEOUT * cfg.SDK_RETRIES + 2)
                # MOVIMIENTO FÍSICO: aterrizar aunque se pierda confirmación takeoff.
                FlightGuard(source.tello)._zero_and_land()
        finally:
            source.close()
            cv2.destroyAllWindows()
            if log_file:
                log_file.close()
        LOG.info('Fin: state=%s frames=%s dry_run=%s motivo=%s',
                 nav.state.value, processed, dry_run, nav.reason or 'fin normal')
    return exit_code


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    raise SystemExit(run(parse_args()))
