"""Verify concurrent body and facial motion in the same synthetic rig."""
import bpy

rig = bpy.data.objects['TestArmature']
mesh = bpy.data.objects['SyntheticBody']
keys = mesh.data.shape_keys
assert rig.animation_data.nla_tracks.get('GentleMotion'), 'Body track missing'
assert rig.animation_data.nla_tracks.get('ExpressionTest'), 'Jaw track missing'
assert keys.animation_data.nla_tracks.get('ExpressionTest'), 'Face track missing'
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
bpy.context.scene.frame_set(1)
bpy.context.view_layer.update()
upper0 = rig.pose.bones['Upper'].rotation_quaternion.copy()
jaw0 = rig.pose.bones['Jaw'].rotation_quaternion.copy()
smile0 = keys.key_blocks['Smile'].value
bpy.context.scene.frame_set(15)
bpy.context.view_layer.update()
upper1 = rig.pose.bones['Upper'].rotation_quaternion.copy()
jaw1 = rig.pose.bones['Jaw'].rotation_quaternion.copy()
smile1 = keys.key_blocks['Smile'].value
assert upper0.rotation_difference(upper1).angle > 0.01, 'Body did not animate'
assert jaw0.rotation_difference(jaw1).angle > 0.01, 'Jaw did not animate'
assert smile1 > smile0 + 0.5, 'Face did not animate'
print('COMBINED_BODY_FACE_OK', flush=True)
