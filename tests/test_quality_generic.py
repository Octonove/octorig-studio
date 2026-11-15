import json
import tempfile
import unittest
from pathlib import Path

from test_core import fixture, TEST_TMP
from octorig.quality import measure


class GenericQualityTests(unittest.TestCase):
    def test_bone_name_alone_does_not_imply_a_wrist(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as tmp:
            asset = Path(tmp) / 'model.glb'
            fixture(asset, nodes=[{'name': 'bone_9'}, {'name': 'body', 'mesh': 0, 'skin': 0}])
            report = measure(asset, fps=10)
            self.assertIsNone(report['clips']['move']['wrist_world_step_max_degrees'])

    def test_profile_identifies_the_wrist_explicitly(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as tmp:
            asset, profile = Path(tmp) / 'model.glb', Path(tmp) / 'profile.json'
            fixture(asset, nodes=[{'name': 'wrist'}, {'name': 'body', 'mesh': 0, 'skin': 0}, {'name': 'prop'}],
                    scenes=[{'nodes': [0, 1, 2]}])
            profile.write_text(json.dumps({'grip': {'right_rest_palm': [0, 0, 0],
                'right_weapon_local': [0, 0, 0]}, 'bones': {'right': {'hand': 'wrist'}},
                'objects': {'weapon': 'prop'}}), encoding='utf-8')
            report = measure(asset, fps=10, profile=profile)
            self.assertIsNotNone(report['clips']['move']['wrist_world_step_max_degrees'])


if __name__ == '__main__':
    unittest.main()
