"""Control proporcional sobre errores normalizados; yaw siempre es cero."""
import math
import numpy as np
import config as cfg


class PController:
    def __init__(self, settings=cfg):
        self.cfg = settings
        self.reset()

    def reset(self):
        self.smoothed = [0.0, 0.0]

    def update(self, error_x, error_y):
        """Positivo: derecha / arriba. Devuelve (lr, ud) enteros RC.

        EMA del comando P saturado. Dentro de deadband se pone cero
        inmediatamente y se borra memoria de ese eje para no seguir derivando.
        Un cambio de signo borra memoria para no corregir en sentido opuesto.
        """
        if not all(math.isfinite(e) for e in (error_x, error_y)):
            self.reset()
            raise ValueError('Error de control no finito')
        result = []
        for i, (error, gain, deadband, maximum) in enumerate(zip(
            (error_x, error_y), (self.cfg.KP_X, self.cfg.KP_Y),
            (self.cfg.DEADBAND_X, self.cfg.DEADBAND_Y),
            (self.cfg.MAX_LR_SPEED, self.cfg.MAX_UD_SPEED),
        )):
            limit = min(maximum, self.cfg.MAX_RC_SPEED, 100)
            if abs(error) <= deadband:
                self.smoothed[i] = 0.0
            else:
                target = float(np.clip(gain * error, -limit, limit))
                if target * self.smoothed[i] < 0:
                    self.smoothed[i] = 0.0
                alpha = self.cfg.EMA_ALPHA
                self.smoothed[i] = alpha * target + (1 - alpha) * self.smoothed[i]
            result.append(int(np.clip(round(self.smoothed[i]), -limit, limit)))
        return tuple(result)
