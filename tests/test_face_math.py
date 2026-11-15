import copy
import unittest
import numpy as np

from octorig.face_math import expression_offsets, graph_distances, jaw_weights, validate_config


class FacialGeometryTests(unittest.TestCase):
    def setUp(self):
        self.points = [[0, 0, 0], [1, 0, 0], [2, 0, 0], [1, 1, 0]]
        self.edges = [(0, 1), (1, 2), (1, 3)]

    def test_graph_distances_follow_the_mesh(self):
        np.testing.assert_allclose(graph_distances(self.points, self.edges, [0]), [0, 1, 2, 2])

    def test_jaw_mask_is_continuous_and_bounded(self):
        mask = jaw_weights(self.points, self.edges, [0], [2], [0.25, 0.75])
        np.testing.assert_allclose(mask, [1, 0.5, 0, 0.5])

    def test_disconnected_component_requires_both_seed_types(self):
        with self.assertRaisesRegex(ValueError, 'connected mesh component'):
            jaw_weights(self.points, [(0, 1), (2, 3)], [0], [1])

    def test_overlapping_seeds_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'overlap'):
            jaw_weights(self.points, self.edges, [0], [0])

    def test_invalid_indices_rejected(self):
        with self.assertRaisesRegex(ValueError, 'out of range'):
            graph_distances(self.points, self.edges, [9])
        with self.assertRaisesRegex(ValueError, 'out of range'):
            graph_distances(self.points, [(0, 8)], [0])

    def test_gaussian_displacements_and_jaw_attenuation(self):
        push = {'center': [0, 0, 0], 'radius': 1, 'offset': [0, 1, 0]}
        offsets = expression_offsets(self.points, [push], [0, 0.5, 1, 0])
        self.assertAlmostEqual(offsets[0, 1], 1)
        self.assertAlmostEqual(offsets[1, 1], np.exp(-0.5) * 0.5)
        np.testing.assert_allclose(offsets[2], [0, 0, 0])
        self.assertAlmostEqual(offsets[3, 1], np.exp(-1))

    def test_nonfinite_and_invalid_inputs_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'positive'):
            expression_offsets(self.points, [{'center': [0, 0, 0], 'radius': 0, 'offset': [1, 0, 0]}])
        with self.assertRaisesRegex(ValueError, 'finite'):
            graph_distances([[float('nan'), 0, 0]], [], [0])
        with self.assertRaisesRegex(ValueError, 'weight'):
            expression_offsets(self.points, [], [0, 1, 2, 0])


class FacialConfigTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            'schema': 'octorig.face/1', 'mesh': 'CharacterMesh', 'armature': 'Rig',
            'jaw': {'mode': 'create', 'bone': 'Jaw', 'parent_bone': 'Head',
                    'head': [0, 0, 0], 'tail': [0, 1, 0], 'axis': [1, 0, 0],
                    'jaw_seeds': [0], 'face_seeds': [2], 'blend': [0.25, 0.75]},
            'expressions': [{'name': 'Smile', 'pushes': [{'center': [0, 0, 0],
                                'offset': [0, 0.1, 0], 'radius': 0.3}]}],
            'clips': [{'name': 'Talk', 'frames': [{'frame': 1, 'jaw_degrees': 0},
                       {'frame': 12, 'jaw_degrees': 15, 'expressions': {'Smile': 0.5}}]}]}

    def test_valid_create_and_existing_jaw(self):
        self.assertIs(validate_config(self.config), self.config)
        existing = copy.deepcopy(self.config)
        existing['jaw'] = {'mode': 'existing', 'bone': 'Jaw', 'axis': [1, 0, 0]}
        validate_config(existing)

    def test_unknown_expression_rejected(self):
        self.config['clips'][0]['frames'][1]['expressions'] = {'Unknown': 1}
        with self.assertRaisesRegex(ValueError, 'unknown expression'):
            validate_config(self.config)

    def test_out_of_order_or_nonfinite_keyframes_rejected(self):
        self.config['clips'][0]['frames'][1]['frame'] = 1
        with self.assertRaisesRegex(ValueError, 'strictly increasing'):
            validate_config(self.config)
        self.config['clips'][0]['frames'][1]['frame'] = 12
        self.config['clips'][0]['frames'][1]['jaw_degrees'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'finite'):
            validate_config(self.config)

    def test_zero_axis_and_duplicate_names_rejected(self):
        self.config['jaw']['axis'] = [0, 0, 0]
        with self.assertRaisesRegex(ValueError, 'non-zero'):
            validate_config(self.config)
        self.config['jaw']['axis'] = [1, 0, 0]
        self.config['expressions'].append(copy.deepcopy(self.config['expressions'][0]))
        with self.assertRaisesRegex(ValueError, 'unique'):
            validate_config(self.config)


if __name__ == '__main__':
    unittest.main()
