"""Genera video SINTÉTICO reproducible; no representa desempeño físico."""
import argparse
from pathlib import Path
import cv2
import numpy as np


def generate(path, fps=20):
    path = Path(path)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), fps, (640, 480))
    if not writer.isOpened():
        raise RuntimeError('No se pudo crear video MJPG')
    try:
        for i in range(240):
            frame = np.zeros((480, 640, 3), np.uint8)
            cx = int(np.interp(i, [0, 60, 90, 239], [440, 440, 320, 320]))
            size = int(np.interp(i, [0, 100, 160, 239], [140, 140, 400, 400]))
            x, y = cx - size // 2, 240 - size // 2
            cv2.rectangle(frame, (x, y), (x + size, y + size), (0, 255, 0), 12)
            writer.write(frame)
    finally:
        writer.release()
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='samples/synthetic_gate.avi')
    args = parser.parse_args()
    print(generate(args.output))
