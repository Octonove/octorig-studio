# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Octonove
"""Retarget FK animation in a common coordinate space inside Blender.

An explicit bone mapping preserves target bone lengths and scales root motion.
An optional mesh can follow a mapped bone. Unknown anatomies and orientations
are not resolved automatically, and contacts require manual review.
"""
import argparse
import json
import math
import sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector


def root_motion_scale(config, source_height, target_height):
    """Return the requested scale, or infer it from non-degenerate heights."""
    if 'root_motion_scale' in config:
        ratio=float(config['root_motion_scale'])
    else:
        if not math.isfinite(source_height) or abs(source_height)<1e-12:
            raise ValueError('Source bone height is zero or invalid; specify root_motion_scale')
        ratio=target_height/source_height
    if not math.isfinite(ratio) or not .1<ratio<10:
        raise ValueError('Invalid root motion scale: expected a finite value between 0.1 and 10')
    return ratio


def activate(objects,name):
    starts=[]
    for o in objects:
        if not o.animation_data:continue
        o.animation_data.action=None
        for track in o.animation_data.nla_tracks:
            track.is_solo=False;track.mute=track.name!=name
            if not track.mute and track.strips:starts.append(track.strips[0].frame_start)
    if not starts:raise ValueError('Track not found: '+name)
    return min(starts)


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--target',required=True)
    p.add_argument('--mapping',required=True);p.add_argument('--output',required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);out=Path(a.output).resolve()
    if out.exists():raise ValueError('Output must be a new directory')
    config=json.loads(Path(a.mapping).read_text(encoding='utf-8'))
    if config.get('schema')!='octorig.retarget/1':raise ValueError('Unsupported mapping schema')
    fps=int(config.get('fps',60))
    if not 24<=fps<=240:raise ValueError('FPS is outside the supported range')
    bpy.ops.wm.read_factory_settings(use_empty=True);sc=bpy.context.scene;sc.render.fps=fps;sc.render.fps_base=1
    bpy.ops.import_scene.gltf(filepath=str(Path(a.source).resolve()));source_objects=list(sc.objects)
    source_arm=next((o for o in source_objects if o.type=='ARMATURE'),None)
    if source_arm is None:raise ValueError('The source has no armature')
    bpy.ops.import_scene.gltf(filepath=str(Path(a.target).resolve()));target_objects=[o for o in sc.objects if o not in source_objects]
    target_arm=next((o for o in target_objects if o.type=='ARMATURE'),None)
    if target_arm is None:raise ValueError('The target has no armature')
    pairs=config['pairs'];mapped={target:source for source,target in pairs.items()}
    if len(mapped)!=len(pairs):raise ValueError('Bone mapping is ambiguous')
    for sn,tn in pairs.items():
        if sn not in source_arm.data.bones or tn not in target_arm.data.bones:raise ValueError('Bone missing from mapping: '+sn+' -> '+tn)
    sr={b.name:b.matrix_local.copy() for b in source_arm.data.bones};tr={b.name:b.matrix_local.copy() for b in target_arm.data.bones}
    sroot=config['root_source'];troot=config['root_target']
    if pairs.get(sroot)!=troot:raise ValueError('The root pair must appear in the mapping')
    height_source=max(b.head_local.z for b in source_arm.data.bones)-min(b.head_local.z for b in source_arm.data.bones)
    height_target=max(b.head_local.z for b in target_arm.data.bones)-min(b.head_local.z for b in target_arm.data.bones)
    ratio=root_motion_scale(config,height_source,height_target)
    attachments=[]
    for spec in config.get('attachments',[]):
        obj=next((o for o in source_objects if o.name==spec['object']),None)
        if obj is None or obj.type!='MESH':raise ValueError('Attachment mesh not found')
        if 'release' in spec and spec['release']:raise ValueError('Attachment release requires explicit authoring; a falling object cannot be transferred as a permanent grip')
        attachments.append((obj,spec))
    for o in target_objects:
        if o.animation_data:
            o.animation_data.action=None
            for t in list(o.animation_data.nla_tracks):o.animation_data.nla_tracks.remove(t)
    clips=config.get('clips') or [t.name for t in source_arm.animation_data.nla_tracks]
    # Capture the source before creating animation curves for attachments.
    samples={}
    for name in clips:
        start=activate(source_objects,name);track=next(t for t in source_arm.animation_data.nla_tracks if t.name==name)
        end=max(s.frame_end for s in track.strips);dur=(end-start)/fps;frames=round(dur*fps);rows=[]
        for f in range(frames+1):
            sc.frame_set(math.floor(start+f));sc.frame_set(math.floor(start+f),subframe=(start+f)%1);bpy.context.view_layer.update()
            rows.append(({b.name:b.matrix.copy() for b in source_arm.pose.bones},[o.matrix_world.copy() for o,_ in attachments]))
        samples[name]=(dur,rows)
    for obj,_ in attachments:
        obj.animation_data_clear();obj.parent=None
    records=[]
    for name,(dur,rows) in samples.items():
        targets=[target_arm]+[o for o,_ in attachments]
        for obj in targets:obj.animation_data_create();obj.animation_data.action=bpy.data.actions.new('Retarget_'+name+'_'+obj.name)
        previous={}
        for f,(source_pose,weapon_matrices) in enumerate(rows):
            sc.frame_set(f+1);P={}
            for b in target_arm.data.bones:
                rest=tr[b.name];sn=mapped.get(b.name)
                head=P[b.parent.name]@tr[b.parent.name].inverted()@rest.translation if b.parent else rest.translation.copy()
                if sn:
                    delta=source_pose[sn].to_3x3()@sr[sn].to_3x3().inverted();rot=delta@rest.to_3x3()
                elif b.parent:rot=P[b.parent.name].to_3x3()@tr[b.parent.name].to_3x3().inverted()@rest.to_3x3()
                else:rot=rest.to_3x3()
                if b.name==troot:head=rest.translation+(source_pose[sroot].translation-sr[sroot].translation)*ratio
                P[b.name]=Matrix.Translation(head)@rot.to_4x4()
                kw={'parent_matrix':P[b.parent.name],'parent_matrix_local':tr[b.parent.name]} if b.parent else {}
                pb=target_arm.pose.bones[b.name];pb.rotation_mode='QUATERNION';pb.matrix_basis=b.convert_local_to_pose(P[b.name],rest,invert=True,**kw)
                q=pb.rotation_quaternion
                if b.name in previous and q.dot(previous[b.name])<0:q.negate()
                previous[b.name]=q.copy()
                for key in ('location','rotation_quaternion','scale'):pb.keyframe_insert(data_path=key,frame=f+1,group=b.name)
            for wi,(obj,spec) in enumerate(attachments):
                sb=spec['source_bone'];tb=pairs[sb]
                # Transfer the deformation between bones without confusing local
                # spaces whose bind, roll and rest positions may differ.
                obj.matrix_world=target_arm.matrix_world@P[tb]@tr[tb].inverted()@sr[sb]@source_pose[sb].inverted()@source_arm.matrix_world.inverted()@weapon_matrices[wi]
                obj.rotation_mode='QUATERNION'
                for key in ('location','rotation_quaternion','scale'):obj.keyframe_insert(data_path=key,frame=f+1)
        for obj in targets:
            action=obj.animation_data.action;obj.animation_data.action=None;track=obj.animation_data.nla_tracks.new();track.name=name
            strip=track.strips.new(name,1,action);strip.action_frame_start=1;strip.action_frame_end=1+round(dur*fps);track.mute=True
        records.append({'name':name,'duration':dur,'frames':len(rows)})
    for obj in source_objects:
        if obj not in [o for o,_ in attachments]:obj.hide_render=True
    out.mkdir(parents=True);sc.frame_set(1)
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'retarget.blend'))
    bpy.ops.object.select_all(action='DESELECT')
    for obj in target_objects+[o for o,_ in attachments]:obj.select_set(True)
    bpy.context.view_layer.objects.active=target_arm
    bpy.ops.export_scene.gltf(filepath=str(out/'retarget.glb'),export_format='GLB',use_selection=True,
        export_animations=True,export_force_sampling=True,export_animation_mode='NLA_TRACKS',export_nla_strips=True,
        export_anim_slide_to_zero=True,export_frame_range=False,export_optimize_animation_size=False)
    (out/'retarget-report.json').write_text(json.dumps({'schema':'octorig.retarget-report/1','root_motion_scale':ratio,'clips':records,
        'unmapped_target_bones':[n for n in tr if n not in mapped],
        'limitations':['FK requires a common reference orientation; align facing direction and rest poses first.',
                       'Contacts are not corrected automatically; review and adjust the result.',
                       'Attachment release is not transferred as a permanent grip.']},indent=2),encoding='utf-8')

if __name__=='__main__':main()
