"""Pruebas sintéticas y de invariantes; no requieren Tello, red ni GUI."""
from dataclasses import replace
import importlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
import cv2
import numpy as np
import config as cfg
from controller import PController
from gate_detector import GateDetection, GateDetector, normalized_error
from main import Navigation, State, parse_args, run
from video_source import FlightGuard, VideoSource
from samples.generate_sample import generate


def settings(**overrides):
    values = {key: value for key, value in vars(cfg).items() if key.isupper()}
    values.update(overrides)
    return SimpleNamespace(**values)


def gate(cx=320, cy=240, width=160):
    return GateDetection(True, cx, cy, (int(cx-width/2), int(cy-width/2), width, width),
                         width * width, width / 640, 1.0)


class DetectorTests(unittest.TestCase):
    def frame(self, center=(320, 240), half=80):
        frame = np.zeros((480, 640, 3), np.uint8)
        cx, cy = center
        cv2.rectangle(frame, (cx-half, cy-half), (cx+half, cy+half), (0, 255, 0), 10)
        return frame

    def test_center_and_mask(self):
        detection, mask = GateDetector().detect(self.frame())
        self.assertTrue(detection.detected)
        self.assertAlmostEqual(detection.center_x, 320, delta=1)
        self.assertAlmostEqual(detection.center_y, 240, delta=1)
        self.assertEqual(mask.shape, (480, 640))
        self.assertGreater(detection.width_ratio, 0.2)

    def test_normalized_error_and_signs(self):
        for cx, cy, expected in [(480, 120, (0.5, 0.5)), (160, 360, (-0.5, -0.5)),
                                  (320, 240, (0.0, 0.0))]:
            self.assertEqual(normalized_error(gate(cx, cy), (480, 640, 3)), expected)
        doubled = replace(gate(480, 120), center_x=960, center_y=240)
        self.assertEqual(normalized_error(doubled, (960, 1280, 3)), (0.5, 0.5))

    def test_no_detection_invalid_and_blank(self):
        for frame in (None, np.zeros((480, 640, 3), np.uint8), np.zeros((2, 2), np.uint8)):
            self.assertFalse(GateDetector().detect(frame)[0].detected)
        self.assertEqual(normalized_error(GateDetection(), (480, 640)), (0, 0))

    def test_reject_solid_panel_and_small_noise(self):
        frame = np.zeros((480, 640, 3), np.uint8)
        cv2.rectangle(frame, (200, 120), (400, 320), (0, 255, 0), -1)
        self.assertFalse(GateDetector().detect(frame)[0].detected)
        self.assertFalse(GateDetector().detect(self.frame(half=10))[0].detected)

    def test_moderate_perspective(self):
        frame = np.zeros((480, 640, 3), np.uint8)
        polygon = np.array([[230, 150], [400, 165], [410, 330], [220, 320]], np.int32)
        cv2.polylines(frame, [polygon], True, (0, 255, 0), 12)
        self.assertTrue(GateDetector().detect(frame)[0].detected)


class ControllerTests(unittest.TestCase):
    def test_deadband_clears_previous_command(self):
        controller = PController()
        controller.update(1, 1)
        self.assertEqual(controller.update(0.01, -0.01), (0, 0))
        self.assertEqual(controller.update(cfg.DEADBAND_X, cfg.DEADBAND_Y), (0, 0))

    def test_saturation_and_sign(self):
        controller = PController(settings(KP_X=1000, KP_Y=1000, EMA_ALPHA=1))
        self.assertEqual(controller.update(1, -1), (cfg.MAX_LR_SPEED, -cfg.MAX_UD_SPEED))

    def test_ema_and_sign_reversal(self):
        controller = PController(settings(KP_X=10, EMA_ALPHA=0.5))
        self.assertEqual(controller.update(1, 0)[0], 5)
        self.assertLess(controller.update(-1, 0)[0], 0)
        controller.reset()
        self.assertEqual(controller.smoothed, [0, 0])

    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            PController().update(float('nan'), 0)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.cfg = settings(DETECTED_FRAMES=2, ALIGNED_FRAMES=2, CROSS_STABLE_FRAMES=2)
        self.nav = Navigation(self.cfg)
        self.nav.start(0)
        self.now = 0

    def step(self, detection):
        self.now += 0.05
        return self.nav.update(detection, (480, 640, 3), self.now)

    def test_single_detection_never_moves(self):
        self.assertEqual(self.step(gate(450)), (0, 0, 0, 0))
        self.assertEqual(self.nav.state, State.SEARCH)

    def test_align_approach_cross_done(self):
        self.step(gate(420))
        rc = self.step(gate(420))
        self.assertEqual(self.nav.state, State.ALIGN)
        self.assertGreater(rc[0], 0)
        self.assertEqual(rc[1], 0)
        for _ in range(5):
            self.step(gate())
        self.assertEqual(self.nav.state, State.APPROACH)
        for width in (200, 250, 310, 390, 400, 400):
            self.step(gate(width=width))
        self.assertEqual(self.nav.state, State.CROSS)
        self.assertEqual(self.step(GateDetection())[1], cfg.CROSS_SPEED)
        rc = self.nav.update(GateDetection(), (480, 640), self.now + cfg.CROSS_DURATION)
        self.assertEqual(rc, (0, 0, 0, 0))
        self.assertEqual(self.nav.state, State.DONE)

    def test_loss_stops_immediately_and_reacquires(self):
        for _ in range(4):
            self.step(gate())
        self.assertEqual(self.nav.state, State.APPROACH)
        self.assertEqual(self.step(GateDetection()), (0, 0, 0, 0))
        self.assertEqual(self.nav.state, State.ALIGN)
        self.assertEqual(self.step(gate()), (0, 0, 0, 0))
        self.assertEqual(self.step(gate())[1], 0)
        for _ in range(cfg.LOST_FRAMES):
            self.step(GateDetection())
        self.assertEqual(self.nav.state, State.SEARCH)

    def test_loss_timeout_and_manual_abort(self):
        self.nav.update(GateDetection(), (480, 640), cfg.GATE_LOSS_TIMEOUT + 1)
        self.assertEqual(self.nav.state, State.EMERGENCY)
        self.assertEqual(self.nav.abort('q'), (0, 0, 0, 0))

    def test_desalignment_stops_forward(self):
        for _ in range(4):
            self.step(gate())
        rc = self.step(gate(375))
        self.assertEqual(self.nav.state, State.ALIGN)
        self.assertEqual(rc[1], 0)

    def test_target_jumps_never_accumulate_stability(self):
        for i in range(10):
            self.assertEqual(self.step(gate(150 if i % 2 else 490)), (0, 0, 0, 0))
        self.assertEqual(self.nav.state, State.SEARCH)

    def test_stages_limit_motion(self):
        for stage in ('hover', 'horizontal', 'align', 'approach'):
            nav = Navigation(self.cfg, stage)
            nav.start(0)
            for i in range(10):
                rc = nav.update(gate(width=400), (480, 640), i * .05)
            self.assertNotEqual(nav.state, State.CROSS)
            self.assertEqual(rc[1], 0)


class SafetyTests(unittest.TestCase):
    def test_stale_telemetry_and_low_battery(self):
        tello = MagicMock()
        tello.get_current_state.return_value = {'bat': 80}
        guard = FlightGuard(tello)
        self.assertEqual(guard.health_error(0), '')
        self.assertIn('Telemetría', guard.health_error(cfg.TELEMETRY_TIMEOUT + 1))
        tello.get_current_state.return_value = {'bat': 5}
        self.assertEqual(guard.health_error(10), 'Batería baja')

    def test_expired_command_stops_and_lands(self):
        tello = MagicMock()
        tello.get_current_state.return_value = {'bat': 80}
        guard = FlightGuard(tello)
        guard.deadline = -1
        guard._run()
        tello.send_rc_control.assert_called_once_with(0, 0, 0, 0)
        tello.land.assert_called_once()

    def test_stream_cleanup_continues_after_failure(self):
        source = VideoSource()
        source.tello = MagicMock()
        source.stream_attempted = True
        source.tello.streamoff.side_effect = RuntimeError('simulado')
        with self.assertLogs('video_source', level='ERROR'):
            source.close()
        source.tello.end.assert_called_once()

    def test_config_rejects_excessive_speed(self):
        with patch.object(cfg, 'CROSS_SPEED', 101):
            with self.assertRaises(ValueError):
                cfg.validate()

    def test_tello_dry_run_does_not_move(self):
        source = MagicMock()
        source.is_local = False
        source.eof = False
        source.battery.return_value = 80
        source.read.return_value = np.zeros((480, 640, 3), np.uint8)
        with patch('main.VideoSource', return_value=source), patch('main.FlightGuard') as guard:
            result = run(parse_args(['--dry-run', '--headless', '--max-frames', '2']))
        self.assertEqual(result, 0)
        guard.assert_not_called()
        source.tello.takeoff.assert_not_called()
        source.tello.send_rc_control.assert_not_called()
        source.tello.land.assert_not_called()
        source.close.assert_called_once()

    def test_real_preflight_low_battery_never_takes_off(self):
        source = MagicMock()
        source.is_local = False
        source.battery.return_value = 5
        with patch.object(cfg, 'DRY_RUN', False), patch('main.VideoSource', return_value=source):
            with self.assertLogs('main', level='ERROR'):
                result = run(parse_args([]))
        self.assertEqual(result, 1)
        source.tello.takeoff.assert_not_called()
        source.close.assert_called_once()


class IntegrationTests(unittest.TestCase):
    def test_imports_without_hardware(self):
        for name in ('main', 'config', 'controller', 'gate_detector', 'video_source', 'hsv_calibration'):
            importlib.import_module(name)

    def test_local_video_forces_dry_run_and_reaches_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = generate(Path(tmp) / 'gate.avi')
            log = Path(tmp) / 'run.csv'
            with patch.object(cfg, 'DRY_RUN', False), patch('main.FlightGuard') as guard:
                code = run(parse_args(['--video', str(video), '--headless', '--log-csv', str(log)]))
            self.assertEqual(code, 0)
            guard.assert_not_called()
            rows = log.read_text().splitlines()
            for state in ('SEARCH', 'ALIGN', 'APPROACH', 'CROSS', 'DONE'):
                self.assertTrue(any(',' + state + ',' in row for row in rows), state)


if __name__ == '__main__':
    unittest.main()
