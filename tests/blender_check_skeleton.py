"""Perform structural checks on an FBX before test-only approval."""
import math
import sys
from pathlib import Path
import bpy

source = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
if not source.is_file():
    raise ValueError('Skeleton FBX does not exist')
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(source))
armatures = [obj for obj in bpy.context.scene.objects if obj.type == 'ARMATURE']
if len(armatures) != 1:
    raise ValueError('Expected one skeleton')
bones = list(armatures[0].data.bones)
if len(bones) < 2 or any(not math.isfinite(value) for bone in bones for value in bone.head_local):
    raise ValueError('Skeleton is empty or has non-finite joints')
if len([bone for bone in bones if bone.parent is None]) != 1:
    raise ValueError('Skeleton must have one root')
print(f'SKELETON_STRUCTURE_OK bones={len(bones)}')
