# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Octonove
"""Conservative preparation; run inside Blender, never on the source."""
import argparse
import json
import math
import sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector

p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True)
p.add_argument('--height',type=float,default=3.);p.add_argument('--rotate-z',type=float,default=0.)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
source=Path(a.input).resolve();output=Path(a.output).resolve()
if source==output or output.exists():raise ValueError('The destination must be new and different from the source')
if not .01<a.height<1000:raise ValueError('Height is out of range')
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(source))
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
if not meshes:raise ValueError('No meshes found')
if any(o.type=='ARMATURE' for o in bpy.context.scene.objects):raise ValueError('A static source is required, not an already rigged character')
pts=[o.matrix_world@v.co for o in meshes for v in o.data.vertices]
lo=Vector([min(v[k] for v in pts) for k in range(3)]);hi=Vector([max(v[k] for v in pts) for k in range(3)])
if hi.z-lo.z<1e-6:raise ValueError('Mesh has no height')
scale=a.height/(hi.z-lo.z);center=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,lo.z))
rotation=Matrix.Rotation(math.radians(a.rotate_z),3,'Z')
for o in meshes:
    transform=o.matrix_world.copy()
    for v in o.data.vertices:v.co=rotation@((transform@v.co-center)*scale)
    o.parent=None;o.matrix_world=Matrix.Identity(4)
bpy.ops.object.select_all(action='DESELECT')
for o in meshes:o.select_set(True)
output.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.export_scene.gltf(filepath=str(output),export_format='GLB',use_selection=True,export_animations=False)
output.with_suffix('.prepare.json').write_text(json.dumps({'height':a.height,'scale':scale,'rotate_z_degrees':a.rotate_z,'center':list(center),'meshes':[o.name for o in meshes],'vertices':len(pts),'geometry_cut':False},indent=2),encoding='utf-8')
