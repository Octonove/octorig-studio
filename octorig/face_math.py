# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Octonove
"""Geometry and configuration helpers for explicit facial controls.

The graph-distance weighting and soft Gaussian displacements follow the same
general techniques used in the project's earlier Blender facial-rig experiments.
Coordinates, landmarks and animation poses are always supplied by the user.
"""
import heapq
import math
import numbers
import numpy as np


def _vector(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f'{name} must contain three numbers')
    try:
        result = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name} must contain three numbers') from exc
    if result.shape != (3,) or not np.isfinite(result).all():
        raise ValueError(f'{name} must contain three finite numbers')
    return result


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, numbers.Real) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    return float(value)


def _name(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a non-empty string')
    return value


def validate_config(config):
    """Validate all settings without touching a Blender scene."""
    if not isinstance(config, dict) or config.get('schema') != 'octorig.face/1':
        raise ValueError('Expected octorig.face/1 configuration')
    _name(config.get('mesh'), 'mesh')
    _name(config.get('armature'), 'armature')
    jaw = config.get('jaw')
    if not isinstance(jaw, dict) or jaw.get('mode') not in ('create', 'existing'):
        raise ValueError('jaw.mode must be create or existing')
    _name(jaw.get('bone'), 'jaw.bone')
    axis = _vector(jaw.get('axis'), 'jaw.axis')
    if np.linalg.norm(axis) < 1e-9:
        raise ValueError('jaw.axis must be non-zero')
    if jaw['mode'] == 'create':
        if len(jaw['bone'].encode('utf-8')) > 55:
            raise ValueError('New jaw bone name must be at most 55 UTF-8 bytes')
        _name(jaw.get('parent_bone'), 'jaw.parent_bone')
        if np.linalg.norm(_vector(jaw.get('tail'), 'jaw.tail') - _vector(jaw.get('head'), 'jaw.head')) < 1e-9:
            raise ValueError('jaw head and tail must be distinct')
        for group in ('jaw_seeds', 'face_seeds'):
            seeds = jaw.get(group)
            if not isinstance(seeds, list) or not seeds or any(isinstance(i, bool) or not isinstance(i, int) or i < 0 for i in seeds):
                raise ValueError(f'jaw.{group} must be a non-empty list of vertex indices')
        limits = jaw.get('blend', [0.35, 0.65])
        if not isinstance(limits, list) or len(limits) != 2:
            raise ValueError('jaw.blend must contain two numbers')
        lo, hi = (_number(n, 'jaw.blend') for n in limits)
        if not 0 <= lo < hi <= 1:
            raise ValueError('jaw.blend must satisfy 0 <= low < high <= 1')
    expressions = config.get('expressions', [])
    if not isinstance(expressions, list):
        raise ValueError('expressions must be a list')
    names = set()
    for expression in expressions:
        if not isinstance(expression, dict):
            raise ValueError('Each expression must be an object')
        name = _name(expression.get('name'), 'expression.name')
        if len(name.encode('utf-8')) > 55:
            raise ValueError('Expression name must be at most 55 UTF-8 bytes')
        if name == 'Basis' or name in names:
            raise ValueError('Expression names must be unique and cannot be Basis')
        names.add(name)
        pushes = expression.get('pushes')
        if not isinstance(pushes, list) or not pushes:
            raise ValueError(f'Expression {name} requires at least one push')
        for push in pushes:
            if not isinstance(push, dict):
                raise ValueError('Each push must be an object')
            _vector(push.get('center'), 'push.center')
            _vector(push.get('offset'), 'push.offset')
            if _number(push.get('radius'), 'push.radius') <= 0:
                raise ValueError('push.radius must be positive')
        if not isinstance(expression.get('attenuate_jaw', True), bool):
            raise ValueError('attenuate_jaw must be true or false')
    clips = config.get('clips', [])
    if not isinstance(clips, list):
        raise ValueError('clips must be a list')
    clip_names = set()
    for clip in clips:
        if not isinstance(clip, dict):
            raise ValueError('Each clip must be an object')
        name = _name(clip.get('name'), 'clip.name')
        if len(name.encode('utf-8')) > 55:
            raise ValueError('Clip name must be at most 55 UTF-8 bytes')
        if name in clip_names:
            raise ValueError('Clip names must be unique')
        clip_names.add(name)
        frames = clip.get('frames')
        if not isinstance(frames, list) or len(frames) < 2:
            raise ValueError(f'Clip {name} requires at least two frames')
        previous = 0
        for row in frames:
            if not isinstance(row, dict):
                raise ValueError('Each keyframe must be an object')
            frame = row.get('frame')
            if isinstance(frame, bool) or not isinstance(frame, int) or frame <= previous:
                raise ValueError('Frame numbers must be positive and strictly increasing')
            previous = frame
            _number(row.get('jaw_degrees', 0), 'jaw_degrees')
            values = row.get('expressions', {})
            if not isinstance(values, dict) or not set(values) <= names:
                raise ValueError('Keyframe references an unknown expression')
            if any(not 0 <= _number(v, 'expression value') <= 1 for v in values.values()):
                raise ValueError('Expression values must be between 0 and 1')
    return config


def graph_distances(vertices, edges, seeds):
    """Shortest edge-path distance from supplied vertex indices; inf if disconnected."""
    points = np.asarray(vertices, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not len(points) or not np.isfinite(points).all():
        raise ValueError('vertices must be a non-empty finite Nx3 array')
    if not seeds or any(isinstance(i, bool) or not isinstance(i, (int, np.integer)) or not 0 <= i < len(points) for i in seeds):
        raise ValueError('seed vertex is out of range')
    neighbors = [[] for _ in points]
    for pair in edges:
        if len(pair) != 2 or any(isinstance(i, bool) or not isinstance(i, (int, np.integer)) or not 0 <= i < len(points) for i in pair):
            raise ValueError('edge vertex is out of range')
        a, b = pair
        length = float(np.linalg.norm(points[a] - points[b]))
        neighbors[a].append((b, length))
        neighbors[b].append((a, length))
    distances = np.full(len(points), np.inf)
    queue = []
    for seed in set(seeds):
        distances[seed] = 0
        heapq.heappush(queue, (0.0, seed))
    while queue:
        distance, vertex = heapq.heappop(queue)
        if distance > distances[vertex]:
            continue
        for neighbor, cost in neighbors[vertex]:
            candidate = distance + cost
            if candidate < distances[neighbor]:
                distances[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    return distances


def jaw_weights(vertices, edges, jaw_seeds, face_seeds, blend=(0.35, 0.65)):
    low, high = blend
    if not (0 <= low < high <= 1):
        raise ValueError('blend must satisfy 0 <= low < high <= 1')
    edges = list(edges)
    d_jaw = graph_distances(vertices, edges, jaw_seeds)
    d_face = graph_distances(vertices, edges, face_seeds)
    if not np.isfinite(d_jaw).all() or not np.isfinite(d_face).all():
        raise ValueError('Every connected mesh component needs both jaw and face seeds')
    total = d_jaw + d_face
    if np.any(total <= 1e-12):
        raise ValueError('Jaw and face seeds must not overlap or have zero-length paths')
    t = np.clip((d_face / total - low) / (high - low), 0, 1)
    return t * t * (3 - 2 * t)


def expression_offsets(vertices, pushes, attenuation=None):
    """Sum Gaussian displacements around caller-supplied landmarks in local units."""
    points = np.asarray(vertices, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError('vertices must be a finite Nx3 array')
    result = np.zeros_like(points)
    for push in pushes:
        center = _vector(push.get('center'), 'push.center')
        offset = _vector(push.get('offset'), 'push.offset')
        radius = _number(push.get('radius'), 'push.radius')
        if radius <= 0:
            raise ValueError('push.radius must be positive')
        factor = np.exp(-np.sum((points - center) ** 2, axis=1) / (2 * radius * radius))
        result += factor[:, None] * offset
    if attenuation is not None:
        weights = np.asarray(attenuation, dtype=float)
        if weights.shape != (len(points),) or not np.isfinite(weights).all() or np.any((weights < 0) | (weights > 1)):
            raise ValueError('attenuation must contain one weight between 0 and 1 per vertex')
        result *= (1 - weights[:, None])
    return result
