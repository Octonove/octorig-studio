"""Staged backend for a local, audited UniRig installation.

It does not install or download software, modify the original runtime, or accept shell commands.
UniRig software and its checkpoints are trusted external dependencies.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from .jobs import new_job,load_job,save_json,sha256,artifact

ROOT=Path(__file__).resolve().parents[1]
SKELETON_TASK='quick_inference_skeleton_articulationxl_ar_256'
SKIN_TASK='quick_inference_unirig_skin'


def environment():
    env=os.environ.copy();env.pop('SSLKEYLOGFILE',None)
    env.update(HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',DO_NOT_TRACK='1',
               WANDB_MODE='disabled',PYTHONIOENCODING='utf-8',TOKENIZERS_PARALLELISM='false')
    return env


def runtime_config(path,verify_checkpoints=True):
    path=Path(path).resolve();cfg=json.loads(path.read_text(encoding='utf-8'))
    if cfg.get('schema')!='octorig.runtime/1':raise ValueError('Unsupported runtime configuration')
    for key in ('python','blender','software','checkpoints'):
        cfg[key]=str((path.parent/cfg[key]).resolve())
    for key in ('python','blender'):
        if not Path(cfg[key]).is_file():raise ValueError('Missing executable: '+key)
    software=Path(cfg['software'])
    for rel in ('src','configs','run.py'):
        if not (software/rel).exists():raise ValueError('Incomplete UniRig software: '+rel)
    for name in ('skeleton','skin'):
        f=Path(cfg['checkpoints'])/(name+'.ckpt')
        if not f.is_file():raise ValueError('Missing checkpoint: '+name)
        expected=cfg.get('checkpoint_sha256',{}).get(name)
        if not expected or len(expected)!=64:raise ValueError('Checkpoint SHA256 must be specified: '+name)
        if verify_checkpoints and sha256(f)!=expected:raise ValueError('Checkpoint SHA256 mismatch: '+name)
    return cfg


def doctor(config):
    cfg=runtime_config(config)
    code="import json,sys,torch,numpy;import bpy,spconv.pytorch,torch_scatter,torch_cluster;print(json.dumps({'python':sys.version.split()[0],'torch':torch.__version__,'cuda':torch.cuda.is_available(),'gpu':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,'numpy':numpy.__version__,'bpy':bpy.app.version_string}))"
    p=subprocess.run([cfg['python'],'-c',code],capture_output=True,text=True,env=environment(),timeout=90)
    if p.returncode:raise RuntimeError('ML runtime unavailable:\n'+p.stderr[-4000:])
    lines=[line for line in p.stdout.splitlines() if line.startswith('{')]
    if not lines:raise RuntimeError('ML runtime returned no diagnostics')
    info=json.loads(lines[-1]);info['checkpoint_hashes_verified']=True
    if not info['cuda']:raise RuntimeError('UniRig requires a CUDA GPU in this configuration')
    bp=subprocess.run([cfg['blender'],'--background','--factory-startup','--disable-autoexec','--version'],capture_output=True,text=True,env=environment(),timeout=30)
    if bp.returncode:raise RuntimeError('Blender failed to start')
    info['blender']=bp.stdout.splitlines()[0]
    return info


def _run(job,label,argv,needed,cwd=None,timeout=1200):
    job=Path(job);state=load_job(job,verify_source=True);log=job/'logs'/(label+'.log');log.parent.mkdir(exist_ok=True)
    stamp=time.monotonic();print(label,flush=True)
    with log.open('w',encoding='utf-8') as stream:
        try:p=subprocess.run([str(x) for x in argv],cwd=cwd or job,env=environment(),stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
        except (OSError,subprocess.TimeoutExpired) as e:
            state['status']='failed';state['error']=str(e);save_json(job/'job.json',state);raise
    record={'name':label,'argv':[str(x) for x in argv],'seconds':round(time.monotonic()-stamp,3),'exit_code':p.returncode,'log':str(log.relative_to(job))}
    state['steps'].append(record)
    output=Path(needed)
    if p.returncode or not output.is_file() or output.stat().st_size==0:
        state['status']='failed';state['error']=label+' did not produce valid output';save_json(job/'job.json',state)
        raise RuntimeError(state['error']+'; see '+str(log))
    record['output']={'path':str(output.relative_to(job)),'sha256':sha256(output)}
    save_json(job/'job.json',state)


def infer_skeleton(config,source,job,seed=123,height=3.,rotate_z=0.):
    cfg=runtime_config(config);source=Path(source).resolve()
    if source.suffix.lower()!='.glb':raise ValueError('Inference v0.1 accepts static GLB meshes; convert OBJ/FBX using Blender first')
    root=new_job(job,source,cfg);work=root/'runtime';work.mkdir()
    sw=Path(cfg['software'])
    for directory in ('src','configs'):
        shutil.copytree(sw/directory,work/directory,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.git'))
    shutil.copy2(sw/'run.py',work/'run.py')
    source_hashes={str(f.relative_to(sw)).replace('\\','/'):sha256(f) for f in sw.rglob('*.py') if '__pycache__' not in f.parts}
    save_json(root/'runtime-source-hashes.json',source_hashes)
    for task,checkpoint in ((SKELETON_TASK,'skeleton'),(SKIN_TASK,'skin')):
        file=work/'configs'/'task'/(task+'.yaml')
        lines=file.read_text(encoding='utf-8').splitlines()
        replacement='resume_from_checkpoint: '+json.dumps((Path(cfg['checkpoints'])/(checkpoint+'.ckpt')).as_posix())
        lines=[replacement if line.startswith('resume_from_checkpoint:') else line for line in lines]
        if replacement not in lines:raise ValueError('Task missing resume_from_checkpoint: '+task)
        file.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (work/'inference').mkdir()
    _run(root,'prepare',[cfg['blender'],'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',ROOT/'octorig'/'prepare_mesh.py','--','--input',source,'--output',work/'input'/'body.glb','--height',height,'--rotate-z',rotate_z],work/'input'/'body.glb')
    extract=[cfg['python'],'-m','src.data.extract','--config','configs/data/quick_inference.yaml','--faces_target_count','50000','--num_runs','1','--force_override','True','--id','0']
    _run(root,'extract-mesh',extract+['--require_suffix','glb','--time','octorig_mesh','--input','input/body.glb','--output_dir','data'],work/'data/input/body/raw_data.npz',work)
    _run(root,'skeleton',[cfg['python'],'run.py','--task','configs/task/'+SKELETON_TASK+'.yaml','--seed',seed,'--input','input/body.glb','--npz_dir','data','--output','inference/skeleton.fbx'],work/'inference/skeleton.fbx',work)
    state=load_job(root);state.update(status='skeleton_ready',skeleton='runtime/inference/skeleton.fbx',seed=seed,
        prepared='runtime/input/body.glb',prepared_sha256=sha256(work/'input/body.glb'))
    save_json(root/'job.json',state)
    return {'job':str(root),'status':state['status'],'skeleton':str(work/'inference/skeleton.fbx'),'sha256':sha256(work/'inference/skeleton.fbx'),
        'next':'Review the joints in Blender and approve the file SHA256 before infer skin.'}


def infer_skin(job):
    root=Path(job).resolve();state=load_job(root,verify_source=True)
    if state['status']!='skeleton_reviewed':raise ValueError('First review and approve the skeleton')
    skeleton=artifact(root,state['skeleton'])
    if sha256(skeleton)!=state.get('approved_skeleton_sha256'):raise ValueError('The skeleton changed after approval')
    if sha256(artifact(root,state['prepared']))!=state['prepared_sha256']:raise ValueError('The prepared mesh changed')
    cfg=state['config']
    # The state records checkpoint hashes; verify them again before the second process.
    for name,h in cfg['checkpoint_sha256'].items():
        if sha256(Path(cfg['checkpoints'])/(name+'.ckpt'))!=h:raise ValueError('Checkpoint changed: '+name)
    work=root/'runtime';py=cfg['python']
    _run(root,'extract-skeleton',[py,'-m','src.data.extract','--config','configs/data/quick_inference.yaml','--faces_target_count','50000','--num_runs','1','--force_override','True','--id','0','--require_suffix','fbx','--time','octorig_skeleton','--input','inference/skeleton.fbx','--output_dir','skin_data'],work/'skin_data/inference/skeleton/raw_data.npz',work)
    _run(root,'skin',[py,'run.py','--task','configs/task/'+SKIN_TASK+'.yaml','--seed',state['seed'],'--input','inference/skeleton.fbx','--npz_dir','skin_data','--data_name','raw_data.npz','--output','inference/skin.fbx'],work/'inference/skin.fbx',work)
    _run(root,'merge',[py,'-m','src.inference.merge','--require_suffix','glb','--num_runs','1','--id','0','--source','inference/skin.fbx','--target','input/body.glb','--output','inference/rig.glb'],work/'inference/rig.glb',work)
    state=load_job(root)
    try:
        from .glb import GLB
        validation=GLB(work/'inference/rig.glb').validate()
        if not validation['valid'] or validation['bones']<1 or validation['vertices']<1:
            raise ValueError('Expected a valid skinned mesh: '+str(validation['errors']))
    except (ValueError,OSError,KeyError,IndexError) as e:
        state.update(status='failed',error='UniRig output is not a valid rigged GLB: '+str(e))
        save_json(root/'job.json',state)
        raise RuntimeError(state['error']) from e
    state.update(status='complete',output='runtime/inference/rig.glb',output_sha256=sha256(work/'inference/rig.glb'),validation=validation)
    save_json(root/'job.json',state)
    return {'status':'complete','glb':str(work/'inference/rig.glb'),'sha256':state['output_sha256']}
