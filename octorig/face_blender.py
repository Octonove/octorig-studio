# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Octonove
"""Create explicit jaw and facial-expression controls in a copy of a Blender file.

Run through Blender with --background --disable-autoexec --python-exit-code 1.
The model and every landmark come from the user; no anatomical detector is used.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Quaternion

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from octorig.face_math import expression_offsets, jaw_weights, validate_config


def group_weights(mesh, name):
    group = mesh.vertex_groups.get(name)
    if group is None:
        raise ValueError(f'Missing vertex group: {name}')
    values = np.zeros(len(mesh.data.vertices), dtype=float)
    for vertex in mesh.data.vertices:
        for entry in vertex.groups:
            if entry.group == group.index:
                values[vertex.index] = entry.weight
                break
    return values


def make_action(owner, name, frames, apply_frame):
    """Write an independent, muted NLA track and preserve the previous action."""
    data = owner.animation_data_create()
    previous = data.action
    action = bpy.data.actions.new(name + '_action')
    data.action = action
    try:
        for frame in frames:
            apply_frame(frame)
        data.action = None
        track = data.nla_tracks.new()
        track.name = name
        track.strips.new(name, frames[0]['frame'], action)
        track.mute = True
    finally:
        data.action = previous


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, help='Existing .blend file')
    parser.add_argument('--config', required=True, help='octorig.face/1 JSON')
    parser.add_argument('--output', required=True, help='New .blend file')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    source = Path(args.input).resolve()
    config_file = Path(args.config).resolve()
    output = Path(args.output).resolve()
    if not source.is_file() or source.suffix.lower() != '.blend' or not config_file.is_file():
        raise ValueError('Input .blend or configuration file does not exist')
    if output.suffix.lower() != '.blend' or output == source or output.exists():
        raise ValueError('Output must be a new .blend file distinct from the input')
    config = validate_config(json.loads(config_file.read_text(encoding='utf-8')))
    bpy.ops.wm.open_mainfile(filepath=str(source))
    mesh = bpy.data.objects.get(config['mesh'])
    armature = bpy.data.objects.get(config['armature'])
    if mesh is None or mesh.type != 'MESH' or armature is None or armature.type != 'ARMATURE':
        raise ValueError('Configured mesh or armature is missing or has the wrong type')
    if mesh.library or mesh.data.library or armature.library or armature.data.library:
        raise ValueError('Linked mesh or armature must be made local before editing')
    if not any(mod.type == 'ARMATURE' and mod.object == armature for mod in mesh.modifiers):
        raise ValueError('Mesh must already have an armature modifier targeting the specified armature')
    jaw = config['jaw']
    jaw_name = jaw['bone']
    expressions = config.get('expressions', [])
    existing_keys = mesh.data.shape_keys
    if existing_keys:
        if not existing_keys.use_relative:
            raise ValueError('Absolute shape keys are not supported')
        if any(key['name'] in existing_keys.key_blocks for key in expressions):
            raise ValueError('An expression shape key already exists')
    new_clip_names = {clip['name'] for clip in config.get('clips', [])}
    for owner in (armature, existing_keys):
        data = owner.animation_data if owner else None
        if data and any(track.name in new_clip_names for track in data.nla_tracks):
            raise ValueError('A configured clip name already exists in an NLA track')
    points = np.array([tuple(v.co) for v in mesh.data.vertices], dtype=float)
    if existing_keys:
        points = np.array([tuple(v.co) for v in existing_keys.reference_key.data], dtype=float)
    if len(points) == 0:
        raise ValueError('Mesh has no vertices')
    if jaw['mode'] == 'create':
        if jaw_name in armature.data.bones or mesh.vertex_groups.get(jaw_name):
            raise ValueError('Jaw bone or vertex group already exists')
        parent_name = jaw['parent_bone']
        if parent_name not in armature.data.bones:
            raise ValueError('Configured parent bone does not exist')
        old_head_weights = group_weights(mesh, parent_name)
        if not np.any(old_head_weights > 0):
            raise ValueError('Parent bone has no mesh weights')
        edges = [(e.vertices[0], e.vertices[1]) for e in mesh.data.edges]
        mask = jaw_weights(points, edges, jaw['jaw_seeds'], jaw['face_seeds'], jaw.get('blend', [0.35, 0.65]))
        if not np.any(old_head_weights * mask > 1e-8):
            raise ValueError('Jaw mask does not overlap parent bone weights')
    else:
        if jaw_name not in armature.data.bones:
            raise ValueError('Configured jaw bone does not exist')
        if armature.pose.bones[jaw_name].rotation_mode != 'QUATERNION':
            raise ValueError('Existing jaw bone must already use quaternion rotation')
        mask = group_weights(mesh, jaw_name)
    offsets = {item['name']: expression_offsets(points, item['pushes'], mask if item.get('attenuate_jaw', True) else None)
               for item in expressions}
    if jaw['mode'] == 'create':
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        armature.select_set(True)
        bpy.context.view_layer.objects.active = armature
        bpy.ops.object.mode_set(mode='EDIT')
        bone = armature.data.edit_bones.new(jaw_name)
        bone.head, bone.tail = jaw['head'], jaw['tail']
        bone.parent = armature.data.edit_bones[jaw['parent_bone']]
        bpy.ops.object.mode_set(mode='OBJECT')
        armature.pose.bones[jaw_name].rotation_mode = 'QUATERNION'
        old_group = mesh.vertex_groups[jaw['parent_bone']]
        new_group = mesh.vertex_groups.new(name=jaw_name)
        for index, previous in enumerate(old_head_weights):
            if previous > 0:
                new_weight = float(previous * mask[index])
                old_group.add([index], float(previous - new_weight), 'REPLACE')
                if new_weight > 0:
                    new_group.add([index], new_weight, 'REPLACE')
    if expressions and mesh.data.shape_keys is None:
        mesh.shape_key_add(name='Basis')
    for item in expressions:
        key = mesh.shape_key_add(name=item['name'])
        key.data.foreach_set('co', (points + offsets[item['name']]).ravel())
        key.value = 0
    jaw_bone = armature.pose.bones[jaw_name]
    rest = jaw_bone.bone.matrix_local.to_3x3()
    initial_rotation = jaw_bone.rotation_quaternion.copy()
    axis = np.asarray(jaw['axis'], dtype=float)
    axis /= np.linalg.norm(axis)
    for clip in config.get('clips', []):
        frames = clip['frames']
        def set_jaw(row):
            delta = Quaternion(tuple(axis), math.radians(row.get('jaw_degrees', 0))).to_matrix()
            jaw_bone.rotation_quaternion = (rest.inverted() @ delta @ rest).to_quaternion()
            jaw_bone.keyframe_insert(data_path='rotation_quaternion', frame=row['frame'], group=jaw_name)
        make_action(armature, clip['name'], frames, set_jaw)
        if expressions:
            keys = mesh.data.shape_keys
            def set_expressions(row):
                values = row.get('expressions', {})
                for item in expressions:
                    key = keys.key_blocks[item['name']]
                    key.value = values.get(item['name'], 0)
                    key.keyframe_insert(data_path='value', frame=row['frame'])
            make_action(keys, clip['name'], frames, set_expressions)
    jaw_bone.rotation_quaternion = initial_rotation
    for item in expressions:
        mesh.data.shape_keys.key_blocks[item['name']].value = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    print(json.dumps({'status': 'saved', 'output': str(output),
                      'jaw_bone': jaw_name, 'expressions': [item['name'] for item in expressions],
                      'clips': [clip['name'] for clip in config.get('clips', [])]}))


if __name__ == '__main__':
    main()
