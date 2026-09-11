"""Detección geométrica de un marco coloreado; entrada siempre BGR."""
from dataclasses import dataclass
import math
import cv2
import numpy as np
import config as cfg


@dataclass(frozen=True)
class GateDetection:
    detected: bool = False
    center_x: float = 0.0
    center_y: float = 0.0
    bbox: tuple = (0, 0, 0, 0)
    area: float = 0.0
    width_ratio: float = 0.0
    confidence: float = 0.0  # puntuación heurística, NO probabilidad medida


def normalized_error(detection, frame_shape):
    if not detection.detected:
        return 0.0, 0.0

    height, width = frame_shape[:2]
    if height <= 0 or width <= 0:
        raise ValueError('Dimensiones de frame inválidas')

    target_y = height * 0.25

    return (
        (detection.center_x - width / 2) / (width / 2),
        (target_y - detection.center_y) / (height / 2),
    )


class GateDetector:
    def __init__(self, settings=cfg):
        self.cfg = settings

    def detect(self, frame):
        """Retorna (GateDetection, máscara). Estabilidad temporal vive en main.

        Se usa contorno exterior para centro/área; el hueco rechaza paneles.
        Permite perspectiva moderada, pero no reconoce cualquier gate.
        """
        if frame is None or frame.size == 0 or frame.ndim != 3 or frame.shape[2] != 3:
            return GateDetection(), None
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array(self.cfg.HSV_MIN, dtype=np.uint8),
                           np.array(self.cfg.HSV_MAX, dtype=np.uint8))
        kernel = np.ones((self.cfg.MORPH_KERNEL_SIZE,) * 2, np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel,
                                iterations=self.cfg.MORPH_OPEN_ITERATIONS)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel,
                                iterations=self.cfg.MORPH_CLOSE_ITERATIONS)
        contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        best, best_score = GateDetection(), -1.0
        height, width = frame.shape[:2]
        for index, contour in enumerate(contours):
            if hierarchy[0][index][3] != -1:  # sólo contornos exteriores
                continue
            area = cv2.contourArea(contour)
            if area < self.cfg.MIN_CONTOUR_AREA:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            ratio = w / h
            low = 1 - self.cfg.ASPECT_RATIO_TOLERANCE
            if min(w, h) < self.cfg.MIN_GATE_SIZE or not low <= ratio <= 1 / low:
                continue
            rectangularity = area / (w * h)
            if rectangularity < self.cfg.MIN_RECTANGULARITY:
                continue
            polygon = cv2.approxPolyDP(contour, self.cfg.POLYGON_EPSILON *
                                      cv2.arcLength(contour, True), True)
            if not self.cfg.MIN_POLYGON_VERTICES <= len(polygon) <= self.cfg.MAX_POLYGON_VERTICES:
                continue
            if not cv2.isContourConvex(polygon):
                continue
            child = hierarchy[0][index][2]
            hole_area = 0.0
            while child != -1:
                hole_area = max(hole_area, cv2.contourArea(contours[child]))
                child = hierarchy[0][child][0]
            if self.cfg.REQUIRE_HOLE and not (
                self.cfg.MIN_HOLE_AREA_RATIO <= hole_area / area <= self.cfg.MAX_HOLE_AREA_RATIO
            ):
                continue
            moments = cv2.moments(contour)
            if moments['m00'] == 0:
                continue
            cx = moments['m10'] / moments['m00']
            cy = moments['m01'] / moments['m00']
            # Favorece área, geometría y cercanía al centro sin pesos ocultos.
            center_distance = math.hypot((cx - width / 2) / width,
                                         (cy - height / 2) / height)
            confidence = rectangularity * min(ratio, 1 / ratio)
            score = area * confidence / (1 + center_distance)
            if score > best_score:
                best_score = score
                best = GateDetection(True, cx, cy, (x, y, w, h), area, w / width, confidence)
        return best, mask


def draw_debug(frame, detection, state, errors, commands, fps=0.0,
               battery=None, dry_run=True, counters='', settings=cfg):
    canvas = frame.copy()
    height, width = canvas.shape[:2]
    center = (width // 2, height // 2)
    dx, dy = int(width / 2 * settings.DEADBAND_X), int(height / 2 * settings.DEADBAND_Y)
    cv2.rectangle(canvas, (center[0] - dx, center[1] - dy),
                  (center[0] + dx, center[1] + dy), (255, 255, 0), 1)
    cv2.drawMarker(canvas, center, (255, 255, 255), cv2.MARKER_CROSS, 16, 1)
    if detection.detected:
        x, y, w, h = detection.bbox
        gate_center = (int(detection.center_x), int(detection.center_y))
        cv2.rectangle(canvas, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.circle(canvas, gate_center, 4, (0, 0, 255), -1)
        cv2.line(canvas, center, gate_center, (0, 255, 255), 2)
    lines = [f'State: {state} | {"DRY RUN" if dry_run else "FLIGHT ENABLED"}',
             f'error_x: {errors[0]:+.3f}  error_y: {errors[1]:+.3f}',
             f'lr: {commands[0]}  fb: {commands[1]}  ud: {commands[2]}  yaw: {commands[3]}',
             f'gate ratio: {detection.width_ratio:.3f}  score: {detection.confidence:.2f}',
             f'FPS: {fps:.1f}  battery: {battery if battery is not None else "N/A"}',
             counters, 'AUTO takeoff | q / ESC: stop + land | Ctrl+C: stop'
             if not dry_run else 'DRY RUN | q / ESC / Ctrl+C: stop']
    for i, line in enumerate(lines):
        point = (10, 22 + i * 22)
        cv2.putText(canvas, line, point, cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 0), 3)
        cv2.putText(canvas, line, point, cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1)
    return canvas
