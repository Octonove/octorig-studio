# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Octonove
"""Bake explicitly mapped body poses in Blender and export a new GLB.

This script runs inside Blender. It never writes to the input model.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from body_motion import evaluate, validate_profile


def _args():
    parser = argparse.ArgumentParser(description='Bake mapped body motion in Blender')
    parser.add_argument('--input', required=True, help='Rigged input GLB')
    parser.add_argument('--profile', required=True, help='Body motion JSON profile')
    parser.add_argument('--output', required=True, help='New output directory')
    parser.add_argument('--armature', help='Armature object name, required if the file has more than one')
    return parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])


def _rotation(values):
    return Euler(tuple(math.radians(x) for x in values), 'XYZ').to_matrix()


def main():
    args = _args()
    source, profile_path, output = (Path(x).resolve() for x in (args.input, args.profile, args.output))
    if not source.is_file() or source.suffix.lower() != '.glb':
        raise ValueError('Input must be an existing GLB file')
    if not profile_path.is_file():
        raise ValueError('Motion profile does not exist')
    if output.exists():
        raise ValueError('Output directory must not already exist')
    profile = validate_profile(json.loads(profile_path.read_text(encoding='utf-8')))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == 'ARMATURE']
    if args.armature:
        armatures = [obj for obj in armatures if obj.name == args.armature]
    if len(armatures) != 1:
        raise ValueError('Expected one armature; supply --armature when the GLB contains several')
    arm = armatures[0]
    missing = [name for name in profile['roles'].values() if name not in arm.pose.bones]
    if missing:
        raise ValueError('Profile references missing bones: ' + ', '.join(missing))
    basis = arm.matrix_world.to_3x3().normalized()
    if basis.determinant() <= 0:
        raise ValueError('Armature must have a non-mirrored, non-degenerate world transform')
    axes = _rotation(profile['character_axes_degrees'])
    scene = bpy.context.scene
    scene.render.fps = profile['fps']
    scene.render.fps_base = 1
    arm.animation_data_create()
    arm.animation_data.action = None
    for track in list(arm.animation_data.nla_tracks):
        arm.animation_data.nla_tracks.remove(track)
    rest = {}
    for name in profile['roles'].values():
        bone = arm.pose.bones[name]
        bone.rotation_mode = 'QUATERNION'
        rest[name] = basis @ bone.bone.matrix_local.to_3x3().normalized()
        if abs(rest[name].determinant()) < 1e-8:
            raise ValueError('Mapped bone has a degenerate rest transform: ' + name)
    baked = []
    for clip in profile['clips']:
        frames = round(clip['duration_seconds'] * profile['fps'])
        action = bpy.data.actions.new(clip['name'])
        action.use_fake_user = True
        arm.animation_data.action = action
        previous = {}
        for index in range(frames + 1):
            scene.frame_set(index + 1)
            pose = evaluate(profile, clip, index / frames)
            for role, name in profile['roles'].items():
                bone = arm.pose.bones[name]
                delta = axes @ _rotation(pose[role]['rotation']) @ axes.inverted()
                transform = rest[name]
                q = (transform.inverted() @ delta @ transform).to_quaternion()
                if name in previous and previous[name].dot(q) < 0:
                    q.negate()
                bone.rotation_quaternion = q
                previous[name] = q.copy()
                bone.location = transform.inverted() @ (axes @ Vector(pose[role]['translation']))
                bone.keyframe_insert(data_path='rotation_quaternion', frame=index + 1, group=name)
                bone.keyframe_insert(data_path='location', frame=index + 1, group=name)
        arm.animation_data.action = None
        track = arm.animation_data.nla_tracks.new()
        track.name = clip['name']
        strip = track.strips.new(clip['name'], 1, action)
        if hasattr(strip, 'action_slot') and getattr(action, 'slots', None):
            strip.action_slot = action.slots[0]
        track.mute = True
        baked.append({'name': clip['name'], 'frames': frames, 'loop': clip['loop']})
    output.mkdir(parents=True, exist_ok=False)
    scene.frame_start = 1
    scene.frame_end = baked[0]['frames'] + 1
    arm.animation_data.nla_tracks[0].mute = False
    scene.frame_set(1)
    bpy.context.preferences.filepaths.save_version = 0
    blend_path = output / 'body-motion.blend'
    saved = bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    if 'FINISHED' not in saved or not blend_path.is_file() or blend_path.stat().st_size == 0:
        raise RuntimeError('Blender did not produce a non-empty BLEND file')
    for track in arm.animation_data.nla_tracks:
        track.mute = False
    glb_path = output / 'body-motion.glb'
    exported = bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format='GLB',
                                         export_animations=True, export_animation_mode='NLA_TRACKS',
                                         export_skins=True, export_frame_range=False, export_anim_slide_to_zero=True)
    if 'FINISHED' not in exported or not glb_path.is_file() or glb_path.stat().st_size == 0:
        raise RuntimeError('Blender did not produce a non-empty GLB file')
    (output / 'body-motion.json').write_text(json.dumps({
        'schema': 'octorig.body-motion-result/1', 'status': 'generated_review_required',
        'clips': baked, 'limitations': ['Body contact, collision and artistic quality require manual review.']
    }, indent=2) + '\n', encoding='utf-8')
    print('Body motion generated; review required.')


if __name__ == '__main__':
    main()
