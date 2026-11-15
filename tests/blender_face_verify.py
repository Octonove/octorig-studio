"""Check generated facial tracks using Blender's NLA editor activation."""
import bpy

rig = bpy.data.objects['CharacterRig']
mesh = bpy.data.objects['CharacterMesh']
assert 'Jaw' in rig.data.bones, 'Jaw bone missing'
assert mesh.vertex_groups.get('Jaw') is not None, 'Jaw weights missing'
assert mesh.data.shape_keys and 'Smile' in mesh.data.shape_keys.key_blocks, 'Expression missing'
rig_track = rig.animation_data.nla_tracks['ExpressionTest']
shape_track = mesh.data.shape_keys.animation_data.nla_tracks['ExpressionTest']
assert rig_track.mute and shape_track.mute, 'New tracks must be muted on load'
assert rig_track.strips[0].action_slot and shape_track.strips[0].action_slot, 'Action slots missing'

# Direct RNA assignment to NlaTrack.mute does not reliably rebuild animation
# dependency relations. Use Blender's editor channel operation, as a user does.
# https://projects.blender.org/blender/blender/pulls/134347
area = next(area for area in bpy.context.window.screen.areas if area.type == 'DOPESHEET_EDITOR')
area.type = 'NLA_EDITOR'
area.spaces.active.dopesheet.show_only_selected = False
region = next(region for region in area.regions if region.type == 'WINDOW')
for obj in bpy.context.scene.objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = mesh
with bpy.context.temp_override(area=area, region=region):
    assert bpy.ops.anim.channels_expand(all=True) == {'FINISHED'}
    assert bpy.ops.anim.channels_select_all(action='SELECT') == {'FINISHED'}
    assert bpy.ops.anim.channels_setting_disable(type='MUTE') == {'FINISHED'}
assert not rig_track.mute and not shape_track.mute, 'Facial tracks failed to activate'

def positions():
    evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    data = evaluated.to_mesh()
    try:
        return [vertex.co.copy() for vertex in data.vertices]
    finally:
        evaluated.to_mesh_clear()

bpy.context.scene.frame_set(1)
bpy.context.view_layer.update()
q1 = rig.pose.bones['Jaw'].rotation_quaternion.copy()
value1 = mesh.data.shape_keys.key_blocks['Smile'].value
vertices1 = positions()
bpy.context.scene.frame_set(15)
bpy.context.view_layer.update()
q2 = rig.pose.bones['Jaw'].rotation_quaternion.copy()
value2 = mesh.data.shape_keys.key_blocks['Smile'].value
vertices2 = positions()
assert q1.rotation_difference(q2).angle > 0.01, 'Jaw did not animate'
assert value2 > value1 + 0.5, 'Expression did not animate'
assert max((a-b).length for a, b in zip(vertices1, vertices2)) > 0.05, 'Face geometry did not deform'
print('FACE_INTEGRATION_OK', flush=True)
