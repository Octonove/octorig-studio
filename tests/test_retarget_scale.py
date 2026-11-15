import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def load_retarget():
    mathutils = types.ModuleType('mathutils')
    mathutils.Matrix, mathutils.Vector = object, object
    path = Path(__file__).resolve().parents[1] / 'octorig' / 'retarget.py'
    spec = importlib.util.spec_from_file_location('_retarget_scale_test', path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'bpy': types.ModuleType('bpy'), 'mathutils': mathutils}):
        spec.loader.exec_module(module)
    return module


class RootMotionScaleTests(unittest.TestCase):
    def test_explicit_scale_works_for_flat_source_skeleton(self):
        self.assertEqual(load_retarget().root_motion_scale({'root_motion_scale': 1.25}, 0, 2), 1.25)

    def test_automatic_scale_uses_heights(self):
        self.assertEqual(load_retarget().root_motion_scale({}, 2, 3), 1.5)

    def test_zero_height_requires_explicit_scale(self):
        with self.assertRaisesRegex(ValueError, 'height'):
            load_retarget().root_motion_scale({}, 0, 2)

    def test_nonfinite_or_out_of_range_scale_rejected(self):
        for value in (float('nan'), float('inf'), 0.1, 10):
            with self.subTest(value=value), self.assertRaises(ValueError):
                load_retarget().root_motion_scale({'root_motion_scale': value}, 1, 1)


class TrackSelectionTests(unittest.TestCase):
    def test_activates_requested_track_and_clears_active_action(self):
        track_a = types.SimpleNamespace(name='Idle', strips=[types.SimpleNamespace(frame_start=3)], is_solo=True, mute=False)
        track_b = types.SimpleNamespace(name='Wave', strips=[types.SimpleNamespace(frame_start=7)], is_solo=True, mute=False)
        animation_data = types.SimpleNamespace(action='old action', nla_tracks=[track_a, track_b])
        obj = types.SimpleNamespace(animation_data=animation_data)
        self.assertEqual(load_retarget().activate([obj], 'Wave'), 7)
        self.assertIsNone(animation_data.action)
        self.assertTrue(track_a.mute)
        self.assertFalse(track_b.mute)
        self.assertFalse(track_a.is_solo)
        self.assertFalse(track_b.is_solo)

    def test_missing_track_is_rejected(self):
        obj = types.SimpleNamespace(animation_data=None)
        with self.assertRaisesRegex(ValueError, 'Track not found'):
            load_retarget().activate([obj], 'missing')


if __name__ == '__main__':
    unittest.main()
