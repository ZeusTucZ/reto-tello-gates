"""Casos de fallos de captura y ciclo de vida con hardware simulado."""
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import config as cfg
from main import State, Navigation, parse_args, run
from video_source import VideoSource, FlightGuard
from gate_detector import GateDetection, draw_debug


class CaptureSafetyTests(unittest.TestCase):
    def source(self):
        source = MagicMock()
        source.is_local = False
        source.eof = False
        source.battery.return_value = 80
        return source

    def test_rgb_tello_converts_to_bgr(self):
        source = VideoSource()
        source.reader = MagicMock()
        source.reader.frame = np.full((48, 64, 3), (255, 0, 0), np.uint8)
        frame = source.read()
        np.testing.assert_array_equal(frame[0, 0], (0, 0, 255))

    def test_no_initial_frames_prevents_takeoff(self):
        source = self.source()
        source.read.return_value = None
        with patch('main.VideoSource', return_value=source), patch.object(cfg, 'DRY_RUN', False), \
                patch.object(cfg, 'PRE_FLIGHT_TIMEOUT', 0.001), patch('main.cv2.waitKey', return_value=-1):
            with self.assertLogs('main', level='ERROR'):
                code = run(parse_args([]))
        self.assertEqual(code, 1)
        source.tello.takeoff.assert_not_called()
        source.close.assert_called_once()

    def test_stream_loss_aborts_after_initial_frame(self):
        source = self.source()
        source.read.side_effect = [np.zeros((480, 640, 3), np.uint8), None, None]
        with patch('main.VideoSource', return_value=source), patch.object(cfg, 'FRAME_TIMEOUT', 0.001):
            with self.assertLogs('main', level='ERROR'):
                code = run(parse_args(['--dry-run', '--headless']))
        self.assertEqual(code, 1)
        source.close.assert_called_once()

    def test_manual_quit_stops_and_lands_after_mock_takeoff(self):
        source = self.source()
        source.read.return_value = np.zeros((480, 640, 3), np.uint8)
        source.tello.get_current_state.side_effect = lambda: {'bat': 80}
        with patch('main.VideoSource', return_value=source), patch.object(cfg, 'DRY_RUN', False), \
                patch('main.cv2.waitKey', side_effect=[ord('t'), -1, -1, ord('q')]), \
                patch('main.cv2.imshow'), patch('main.cv2.getWindowProperty', return_value=1):
            code = run(parse_args([]))
        self.assertEqual(code, 0)
        source.tello.takeoff.assert_called_once()
        source.tello.send_rc_control.assert_any_call(0, 0, 0, 0)
        source.tello.land.assert_called_once()
        source.close.assert_called_once()

    def test_guard_clamps_all_channels(self):
        guard = FlightGuard(MagicMock())
        guard.submit((1000, -1000, 500, -500))
        self.assertEqual(guard.command, (cfg.MAX_RC_SPEED, -cfg.MAX_RC_SPEED,
                                          cfg.MAX_RC_SPEED, -cfg.MAX_RC_SPEED))

    def test_overlay_can_render_without_detection(self):
        frame = np.zeros((480, 640, 3), np.uint8)
        drawn = draw_debug(frame, GateDetection(), 'SEARCH', (0, 0), (0, 0, 0, 0))
        self.assertEqual(drawn.shape, frame.shape)
        self.assertGreater(np.count_nonzero(drawn), 0)
        self.assertEqual(np.count_nonzero(frame), 0)

    def test_hover_still_obeys_mission_timeout(self):
        nav = Navigation(stage='hover')
        nav.start(0)
        nav.update(GateDetection(), (480, 640), cfg.MAX_FLIGHT_SECONDS + 1)
        self.assertEqual(nav.state, State.EMERGENCY)


if __name__ == '__main__':
    unittest.main()
