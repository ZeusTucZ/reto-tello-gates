"""Calibración HSV interactiva sin despegue: Tello, webcam o archivo."""
import argparse
import logging
import time
import cv2
import numpy as np
import config as cfg
from video_source import VideoSource


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--video', help='Video local; se repite al terminar')
    group.add_argument('--webcam', type=int, help='Índice de cámara, por ejemplo 0')
    args = parser.parse_args(argv)
    cfg.validate()
    source = VideoSource(args.video, args.webcam)
    previous = None
    frame = None
    last_frame_at = time.monotonic()
    window = 'HSV calibration'
    names = ('H min', 'S min', 'V min', 'H max', 'S max', 'V max')
    try:
        source.open()
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        for name, value, maximum in zip(names, cfg.HSV_MIN + cfg.HSV_MAX,
                                         (179, 255, 255, 179, 255, 255)):
            cv2.createTrackbar(name, window, value, maximum, lambda value: None)
        print('Ajusta sliders. p: imprimir; espacio: pausa local; q/ESC: salir.')
        paused = False
        last_frame_at = time.monotonic()
        while True:
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord('q')):
                break
            if key == ord(' ') and source.is_local:
                paused = not paused
            if not paused:
                new_frame = source.read()
                if new_frame is not None:
                    frame = new_frame
                    last_frame_at = time.monotonic()
                elif source.eof:
                    if source.frame_number == 0:
                        raise RuntimeError('Video vacío o no decodificable')
                    source.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    source.eof = False
                elif time.monotonic() - last_frame_at > cfg.PRE_FLIGHT_TIMEOUT:
                    raise RuntimeError('No llegan frames de la cámara')
            values = tuple(cv2.getTrackbarPos(name, window) for name in names)
            lower, upper = values[:3], values[3:]
            if values != previous or key == ord('p'):
                print(f'HSV_MIN = {lower}\nHSV_MAX = {upper}', flush=True)
                if any(a > b for a, b in zip(lower, upper)):
                    print('Rango inválido: cada mínimo debe ser <= máximo.')
                previous = values
            if frame is not None:
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                mask = cv2.inRange(hsv, np.array(lower, np.uint8), np.array(upper, np.uint8))
                filtered = cv2.bitwise_and(frame, frame, mask=mask)
                cv2.imshow(window, frame)
                cv2.imshow('HSV mask', mask)
                cv2.imshow('Filtered BGR', filtered)
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                break
            time.sleep(1 / (source.fps if args.video else cfg.CONTROL_HZ))
    except KeyboardInterrupt:
        pass
    finally:
        if previous:
            print(f'Copiar a config.py:\nHSV_MIN = {previous[:3]}\nHSV_MAX = {previous[3:]}')
        source.close()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
