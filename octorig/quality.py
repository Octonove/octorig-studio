"""Observable metrics; these do not certify artistic quality."""
import json
from pathlib import Path
import numpy as np
from .glb import GLB,AssetError
from .jobs import sha256,save_json


def contract(path):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    clips=data.get('clips',[])
    if isinstance(clips,dict):clips=[dict(v,name=k) for k,v in clips.items()]
    return {c['name']:c for c in clips}


def measure(path, clips=None, fps=60, profile=None):
    if not 10<=fps<=240:raise ValueError('Supported sampling rate: 10–240 Hz')
    g=GLB(path);validation=g.validate()
    if not validation['valid']:raise AssetError('; '.join(validation['errors']))
    policy=contract(clips) if clips else {}
    record={'schema':'octorig.quality/1','sha256':sha256(path),'validation':validation,
        'sample_hz':fps,'space':'glTF world, +Y up, model units','clips':{},
        'notes':['Surface speed includes intentional movement.',
                 'Loop closure is evaluated only when the contract declares a loop.',
                 'Grip distance is omitted during a release declared in the profile.',
                 'These metrics do not establish artistic naturalness or the absence of collisions.']}
    rest=g.pose();rest_by_name={m['name']:m for m in rest['meshes']}
    # The profile defines the anatomical point: UniRig names do not imply
    # that all characters have the same hand or proportions.
    grip=None
    if profile:
        config=json.loads(Path(profile).read_text(encoding='utf-8-sig'))
        gp=config['grip'];hand=config['bones']['right']['hand'];weapon=config['objects']['weapon']
        def y_up(p):return np.array([p[0],p[2],-p[1],1.])
        if hand not in rest['named_world'] or weapon not in rest['named_world']:raise AssetError('Profile grip landmarks are missing')
        grip={'hand':hand,'weapon':weapon,'local':np.linalg.inv(rest['named_world'][hand])@y_up(gp['right_rest_palm']),
              'weapon_local':y_up(gp['right_weapon_local']),'release':gp.get('release',{})}
    for name in g.animations:
        dur=g.duration(name);n=max(1,round(dur*fps));times=np.linspace(0,dur,n+1)
        previous=None;first=None;end=None;minimum=float('inf');grips=[];max_speed=0.;speeds=[];world_steps=[]
        for t in times:
            pose=g.pose(name,float(t));arrays=[m['positions'] for m in pose['meshes']]
            surface=np.vstack(arrays)
            if not np.isfinite(surface).all():raise AssetError('Non-finite surface in '+name)
            minimum=min(minimum,float(surface[:,1].min()))
            if first is None:first=surface.copy()
            if previous is not None:
                d=np.linalg.norm(surface-previous,axis=1)/(dur/n if dur else 1.)
                max_speed=max(max_speed,float(d.max()));speeds.append(float(np.percentile(d,99)))
                wrist_name=grip['hand'] if grip else None
                wrist=pose['named_world'].get(wrist_name) if wrist_name else None
                if wrist is not None:
                    r=wrist[:3,:3];last=previous_world['named_world'][wrist_name][:3,:3]
                    world_steps.append(float(np.degrees(np.arccos(np.clip((np.trace(last.T@r)-1)/2,-1,1)))))
            if grip and (name!=grip['release'].get('clip') or t<=dur*grip['release'].get('phase',1)+1e-9):
                w=pose['named_world'];grips.append(float(np.linalg.norm((w[grip['hand']]@grip['local']-w[grip['weapon']]@grip['weapon_local'])[:3])))
            previous=surface;previous_world=pose;end=surface
        meta=policy.get(name,{})
        loop=bool(meta.get('loop',False));expected=meta.get('duration_seconds',meta.get('duration',dur))
        record['clips'][name]={'duration':dur,'contract_duration':expected,'duration_error':abs(dur-expected),
            'samples':len(times),'loop':loop,'loop_surface_max_distance':float(np.linalg.norm(end-first,axis=1).max()) if loop else None,
            'surface_min_y':minimum,'surface_peak_speed':max_speed,'surface_p99_speed_max':max(speeds,default=0.),
            'wrist_world_step_max_degrees':max(world_steps,default=0.) if world_steps else None,
            'right_grip_max_distance':max(grips) if grips else None,
            'contact_normalized':meta.get('contact_normalized')}
    return record


def compare(a,b,clips=None,fps=60,profile=None):
    aa=measure(a,clips,fps,profile);bb=measure(b,clips,fps,profile);rows=[]
    for name in sorted(aa['clips'].keys()|bb['clips'].keys()):
        va=aa['clips'].get(name);vb=bb['clips'].get(name)
        rows.append({'name':name,'a':va,'b':vb,'surface_peak_speed_delta':vb['surface_peak_speed']-va['surface_peak_speed'] if va and vb else None})
    return {'schema':'octorig.comparison-quality/1','a':aa,'b':bb,'rows':rows,
        'same_clip_inventory':list(aa['clips'])==list(bb['clips']),
        'all_durations_match':set(aa['clips'])==set(bb['clips']) and all(abs(aa['clips'][n]['duration']-bb['clips'][n]['duration'])<1e-4 for n in aa['clips']),
        'verdict':'REVIEW_REQUIRED','meaning':'Differences are measurements; the final choice requires observing both movements.'}
