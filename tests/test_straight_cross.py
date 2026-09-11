"""Transición y avance recto sin hardware ni GUI."""
import unittest
from unittest.mock import patch

import config as cfg
from gate_detector import GateDetection
from main import Navigation, State, ZERO


class StraightCrossTests(unittest.TestCase):
    def test_five_aligned_frames_then_straight_until_timeout(self):
        nav = Navigation(stage='full')
        nav.start(0)
        gate = GateDetection(True, 320, 216, (240, 136, 160, 160),
                             25600, 0.25, 1.0)
        with patch.object(cfg, 'DETECTED_FRAMES', 1), \
                patch.object(cfg, 'ALIGNED_FRAMES', 5), \
                patch('main.normalized_error', return_value=(0.0, 0.0)):
            for i in range(1, 5):
                self.assertEqual(nav.update(gate, (480, 640), i * .05), ZERO)
                self.assertEqual(nav.state, State.ALIGN)
            forward = (0, cfg.CROSS_SPEED, 0, 0)
            self.assertEqual(nav.update(gate, (480, 640), .25), forward)
            self.assertEqual(nav.state, State.CROSS)
        with patch('main.normalized_error', return_value=(.8, -.8)):
            self.assertEqual(nav.update(gate, (480, 640), .30), forward)
        self.assertEqual(nav.update(GateDetection(), (480, 640), .35), forward)
        self.assertEqual(nav.update(GateDetection(), (480, 640),
                                    .25 + cfg.ADVANCE_PULSE_SECONDS), ZERO)
        self.assertEqual(nav.state, State.ALIGN)
        now = .25 + cfg.ADVANCE_PULSE_SECONDS
        for i in range(cfg.LOST_FRAMES):
            now += .05
            rc = nav.update(GateDetection(), (480, 640), now)
            self.assertEqual(rc, forward if i == cfg.LOST_FRAMES - 1 else ZERO)
        self.assertEqual(nav.state, State.FINAL_ADVANCE)
        self.assertEqual(nav.update(gate, (480, 640), now + .05), forward)
        self.assertEqual(nav.update(gate, (480, 640),
                                    now + cfg.FINAL_ADVANCE_SECONDS + .001), ZERO)
        self.assertEqual(nav.state, State.DONE)
        self.assertEqual(nav.update(GateDetection(), (480, 640), now + 1), ZERO)

    def test_initial_missing_gate_never_triggers_forward(self):
        nav = Navigation(stage='full')
        nav.start(0)
        for i in range(cfg.LOST_FRAMES + 2):
            self.assertEqual(nav.update(GateDetection(), (480, 640), (i + 1) * .05), ZERO)
        self.assertEqual(nav.state, State.SEARCH)

    def test_visible_gate_realigns_before_second_pulse(self):
        nav = Navigation(stage='full')
        nav.start(0)
        gate = GateDetection(True, 320, 216, (240, 136, 160, 160), 25600, .25, 1.)
        with patch('main.normalized_error', return_value=(0., 0.)), \
                patch.object(cfg, 'DETECTED_FRAMES', 1), patch.object(cfg, 'ALIGNED_FRAMES', 5):
            for i in range(5):
                nav.update(gate, (480, 640), (i + 1) * .05)
            end = .25 + cfg.ADVANCE_PULSE_SECONDS + .001
            self.assertEqual(nav.update(gate, (480, 640), end), ZERO)
            for i in range(1, 5):
                self.assertEqual(nav.update(gate, (480, 640), end + i * .05), ZERO)
                self.assertEqual(nav.state, State.ALIGN)
            self.assertEqual(nav.update(gate, (480, 640), end + .25), (0, cfg.CROSS_SPEED, 0, 0))
            self.assertEqual(nav.state, State.CROSS)

    def test_misalignment_resets_confirmation_and_align_stage_never_advances(self):
        gate = GateDetection(True, 320, 216, (240, 136, 160, 160),
                             25600, .25, 1.0)
        for stage in ('full', 'align'):
            nav = Navigation(stage=stage)
            nav.start(0)
            errors = [(0., 0.)] * 4 + [(.2, 0.)] + [(0., 0.)] * 5
            with patch.object(cfg, 'DETECTED_FRAMES', 1), \
                    patch.object(cfg, 'ALIGNED_FRAMES', 5), \
                    patch('main.normalized_error', side_effect=errors):
                for i in range(10):
                    rc = nav.update(gate, (480, 640), (i + 1) * .05)
                    if i < 9 or stage == 'align':
                        self.assertEqual(rc[1], 0)
                        self.assertNotEqual(nav.state, State.CROSS)
                self.assertEqual(nav.state, State.CROSS if stage == 'full' else State.ALIGN)
