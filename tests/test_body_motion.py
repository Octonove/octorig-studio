import unittest
import json
from pathlib import Path

from octorig.body_motion import evaluate, validate_profile


def profile():
    return {
        'schema': 'octorig.body-motion/1',
        'fps': 20,
        'roles': {'root': 'Root', 'upper': 'Upper'},
        'rotation_scale': 1.0,
        'translation_scale': 2.0,
        'clips': [{
            'name': 'Breathing', 'duration_seconds': 1.0, 'loop': True,
            'poses': [
                {'phase': 0.0, 'bones': {'upper': {'rotation': [0, 0, 0]}}},
                {'phase': 0.5, 'bones': {'upper': {'rotation': [10, 0, 0]},
                                         'root': {'translation': [0, 0, 0.1]}}},
                {'phase': 1.0, 'bones': {'upper': {'rotation': [0, 0, 0]}}},
            ],
        }],
    }


class BodyMotionTests(unittest.TestCase):
    def test_interpolates_declared_roles_and_scales_translation(self):
        cfg = validate_profile(profile())
        pose = evaluate(cfg, cfg['clips'][0], 0.25)
        self.assertEqual(pose['upper']['rotation'], [5.0, 0.0, 0.0])
        self.assertEqual(pose['root']['translation'], [0.0, 0.0, 0.1])

    def test_closed_loop_returns_to_start(self):
        cfg = validate_profile(profile())
        clip = cfg['clips'][0]
        self.assertEqual(evaluate(cfg, clip, 0), evaluate(cfg, clip, 1))

    def test_missing_role_in_pose_is_rejected(self):
        cfg = profile()
        cfg['clips'][0]['poses'][0]['bones']['unknown'] = {'rotation': [1, 2, 3]}
        with self.assertRaisesRegex(ValueError, 'Unknown role'):
            validate_profile(cfg)

    def test_duplicate_target_bones_are_rejected(self):
        cfg = profile()
        cfg['roles']['upper'] = 'Root'
        with self.assertRaisesRegex(ValueError, 'unique'):
            validate_profile(cfg)

    def test_nonfinite_or_missing_endpoints_are_rejected(self):
        cfg = profile()
        cfg['clips'][0]['poses'][1]['bones']['upper']['rotation'][0] = float('nan')
        with self.assertRaises(ValueError):
            validate_profile(cfg)
        cfg = profile()
        cfg['clips'][0]['poses'][-1]['phase'] = 0.9
        with self.assertRaises(ValueError):
            validate_profile(cfg)

    def test_nonclosed_loop_is_rejected(self):
        cfg = profile()
        cfg['clips'][0]['poses'][-1]['bones']['upper']['rotation'][0] = 1
        with self.assertRaisesRegex(ValueError, 'loop'):
            validate_profile(cfg)

    def test_sampling_outside_clip_is_rejected(self):
        cfg = validate_profile(profile())
        with self.assertRaises(ValueError):
            evaluate(cfg, cfg['clips'][0], 1.1)

    def test_tiny_duration_cannot_produce_zero_frames(self):
        cfg = profile()
        cfg['clips'][0]['duration_seconds'] = 1e-12
        with self.assertRaises(ValueError):
            validate_profile(cfg)

    def test_shipped_example_maps_to_synthetic_model(self):
        from octorig.glb import GLB
        root = Path(__file__).resolve().parents[1]
        cfg = validate_profile(json.loads((root / 'octorig/body_example.json').read_text(encoding='utf-8')))
        glb = GLB(root / 'examples/wave.glb')
        joints = {glb.doc['nodes'][i].get('name') for skin in glb.doc['skins'] for i in skin['joints']}
        self.assertTrue(set(cfg['roles'].values()) <= joints)

    def test_humanoid_template_has_three_valid_distinct_clips(self):
        root = Path(__file__).resolve().parents[1]
        cfg = validate_profile(json.loads((root / 'octorig/body_humanoid_example.json').read_text(encoding='utf-8')))
        self.assertEqual([clip['name'] for clip in cfg['clips']], ['Idle', 'Roar', 'Slam'])
        for clip in cfg['clips']:
            self.assertNotEqual(evaluate(cfg, clip, 0), evaluate(cfg, clip, 0.3))


if __name__ == '__main__':
    unittest.main()
