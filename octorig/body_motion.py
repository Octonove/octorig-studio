# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Octonove
"""Validate and sample explicitly mapped, character-independent body poses."""
import copy
import math


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label} must be a finite number')
    return float(value)


def _vector(value, label):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f'{label} must contain exactly three numbers')
    return [_number(v, label) for v in value]


def _pose(bones, roles):
    if not isinstance(bones, dict):
        raise ValueError('Pose bones must be an object')
    result = {role: {'rotation': [0.0, 0.0, 0.0], 'translation': [0.0, 0.0, 0.0]} for role in roles}
    for role, values in bones.items():
        if role not in roles:
            raise ValueError(f'Unknown role: {role}')
        if not isinstance(values, dict) or set(values) - {'rotation', 'translation'}:
            raise ValueError(f'Invalid pose values for role: {role}')
        for key, value in values.items():
            result[role][key] = _vector(value, f'{role}.{key}')
    return result


def validate_profile(profile):
    """Return a normalized independent copy or reject an unsafe/ambiguous profile."""
    if not isinstance(profile, dict) or profile.get('schema') != 'octorig.body-motion/1':
        raise ValueError('Unsupported body motion profile schema')
    result = copy.deepcopy(profile)
    fps = result.get('fps', 30)
    if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 120:
        raise ValueError('fps must be an integer between 1 and 120')
    result['fps'] = fps
    roles = result.get('roles')
    if (not isinstance(roles, dict) or not roles or
            any(not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
                for k, v in roles.items())):
        raise ValueError('roles must map non-empty role names to bone names')
    if len(set(roles.values())) != len(roles):
        raise ValueError('Mapped target bone names must be unique')
    for key in ('rotation_scale', 'translation_scale'):
        result[key] = _number(result.get(key, 1), key)
        if not 0 < result[key] <= 1000:
            raise ValueError(f'{key} must be greater than zero and at most 1000')
    result['character_axes_degrees'] = _vector(result.get('character_axes_degrees', [0, 0, 0]), 'character_axes_degrees')
    clips = result.get('clips')
    if not isinstance(clips, list) or not clips:
        raise ValueError('At least one clip is required')
    seen = set()
    for clip in clips:
        if not isinstance(clip, dict):
            raise ValueError('Each clip must be an object')
        name = clip.get('name')
        if not isinstance(name, str) or not name.strip() or name in seen:
            raise ValueError('Clip names must be non-empty and unique')
        seen.add(name)
        duration = _number(clip.get('duration_seconds'), 'duration_seconds')
        if duration <= 0 or duration > 120 or round(duration * fps) < 1 or abs(duration * fps - round(duration * fps)) > 1e-6:
            raise ValueError('Clip duration must be positive, at most 120 seconds, and align to a frame')
        clip['duration_seconds'] = duration
        if not isinstance(clip.get('loop', False), bool):
            raise ValueError('loop must be true or false')
        clip['loop'] = clip.get('loop', False)
        if clip.get('interpolation', 'smooth') not in ('smooth', 'linear'):
            raise ValueError('Interpolation must be smooth or linear')
        clip['interpolation'] = clip.get('interpolation', 'smooth')
        keys = clip.get('poses')
        if not isinstance(keys, list) or len(keys) < 2:
            raise ValueError('A clip needs at least two poses')
        previous = -1.0
        for key in keys:
            if not isinstance(key, dict):
                raise ValueError('Each pose must be an object')
            phase = _number(key.get('phase'), 'phase')
            if not 0 <= phase <= 1 or phase <= previous:
                raise ValueError('Pose phases must increase strictly from 0 to 1')
            previous = phase
            key['phase'] = phase
            key['bones'] = _pose(key.get('bones', {}), roles)
        if keys[0]['phase'] != 0 or keys[-1]['phase'] != 1:
            raise ValueError('Pose phases must start at 0 and end at 1')
        if clip['loop'] and keys[0]['bones'] != keys[-1]['bones']:
            raise ValueError('A loop must end in its starting pose')
    return result


def evaluate(profile, clip, phase):
    """Sample a validated clip. Angles are degrees; translations are model units."""
    phase = _number(phase, 'phase')
    if not 0 <= phase <= 1:
        raise ValueError('phase must be between 0 and 1')
    keys = clip['poses']
    i = next((i for i in range(1, len(keys)) if phase <= keys[i]['phase']), len(keys) - 1)
    a, b = keys[i - 1], keys[i]
    w = (phase - a['phase']) / (b['phase'] - a['phase'])
    if clip['interpolation'] == 'smooth':
        w = w * w * (3 - 2 * w)
    result = {}
    for role in profile['roles']:
        result[role] = {}
        for key, factor in (('rotation', profile['rotation_scale']), ('translation', profile['translation_scale'])):
            result[role][key] = [(x + (y - x) * w) * factor for x, y in zip(a['bones'][role][key], b['bones'][role][key])]
    return result
