"""Create a small synthetic skinned mesh for the Blender integration test."""
import sys
from pathlib import Path
import bpy

output = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
if output.exists():
    raise ValueError('Fixture output already exists')
bpy.ops.wm.read_factory_settings(use_empty=True)
arm_data = bpy.data.armatures.new('RigData')
rig = bpy.data.objects.new('CharacterRig', arm_data)
bpy.context.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
head = arm_data.edit_bones.new('Head')
head.head = (0, 0, 0)
head.tail = (0, 0, 2)
bpy.ops.object.mode_set(mode='OBJECT')
data = bpy.data.meshes.new('MeshData')
vertices = [(-1,-1,0), (1,-1,0), (-1,1,0), (1,1,0),
            (-1,-1,2), (1,-1,2), (-1,1,2), (1,1,2)]
faces = [(0,1,3,2), (4,6,7,5), (0,4,5,1),
         (2,3,7,6), (0,2,6,4), (1,5,7,3)]
data.from_pydata(vertices, [], faces)
data.update()
mesh = bpy.data.objects.new('CharacterMesh', data)
bpy.context.collection.objects.link(mesh)
group = mesh.vertex_groups.new(name='Head')
group.add(list(range(len(vertices))), 1.0, 'REPLACE')
modifier = mesh.modifiers.new('Armature', 'ARMATURE')
modifier.object = rig
mesh.parent = rig
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(output))
