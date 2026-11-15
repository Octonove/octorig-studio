"""Isolated jobs, input hashes and explicit skeleton review."""
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path


def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def save_json(path,data):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_suffix(p.suffix+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temp.replace(p)


def new_job(path,source,config):
    path=Path(path).resolve();source=Path(source).resolve()
    if not source.is_file():raise ValueError('Source does not exist: '+str(source))
    if path.exists() and any(path.iterdir()):raise ValueError('The job directory must be new or empty')
    path.mkdir(parents=True,exist_ok=True)
    save_json(path/'job.json',{'schema':'octorig.job/1','created':datetime.now(timezone.utc).isoformat(),
        'status':'created','source':str(source),'source_sha256':sha256(source),'config':config,'steps':[]})
    return path


def load_job(path,verify_source=False):
    state=json.loads((Path(path)/'job.json').read_text(encoding='utf-8'))
    if state.get('schema')!='octorig.job/1':raise ValueError('Unsupported job version')
    if verify_source and sha256(state['source'])!=state['source_sha256']:raise ValueError('Source changed since the job began')
    return state


def artifact(job,relative):
    root=Path(job).resolve();p=(root/relative).resolve()
    if not p.is_relative_to(root):raise ValueError('Artifact is outside the job directory')
    return p


def approve_skeleton(path,expected_sha):
    root=Path(path).resolve();state=load_job(root,verify_source=True)
    if state['status']!='skeleton_ready':raise ValueError('The job is not awaiting skeleton review')
    skeleton=artifact(root,state['skeleton'])
    if sha256(skeleton)!=expected_sha:raise ValueError('Hash does not match the reviewed skeleton')
    state.update(status='skeleton_reviewed',approved_skeleton_sha256=expected_sha)
    save_json(root/'job.json',state)
