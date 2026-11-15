"""Local interface. Run `python -m octorig --help`."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from . import __version__
from .glb import GLB,AssetError
from .jobs import save_json,sha256,approve_skeleton
from .quality import measure,compare

def main(argv=None):
    p=argparse.ArgumentParser(description='OctoRig Studio — local character workflow')
    p.add_argument('--version',action='version',version=__version__)
    sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('inspect',help='Validate GLB structure, weights and clips');q.add_argument('asset');q.add_argument('--out')
    q=sub.add_parser('doctor',help='Check Blender, CUDA, software and hashes');q.add_argument('--runtime',required=True);q.add_argument('--out')
    q=sub.add_parser('infer',help='Run UniRig inference in stages');ph=q.add_subparsers(dest='phase',required=True)
    z=ph.add_parser('skeleton');z.add_argument('--runtime',required=True);z.add_argument('--input',required=True);z.add_argument('--job',required=True);z.add_argument('--seed',type=int,default=123);z.add_argument('--height',type=float,default=3.);z.add_argument('--rotate-z',type=float,default=0.)
    z=ph.add_parser('approve');z.add_argument('--job',required=True);z.add_argument('--sha256',required=True)
    z=ph.add_parser('skin');z.add_argument('--job',required=True)
    q=sub.add_parser('retarget',help='Transfer existing animation between explicitly mapped rigs (experimental)')
    q.add_argument('--blender',required=True);q.add_argument('--source',required=True);q.add_argument('--target',required=True);q.add_argument('--mapping',required=True);q.add_argument('--output',required=True)
    q=sub.add_parser('quality',help='Measure surfaces, cycles and grip');q.add_argument('asset');q.add_argument('--clips');q.add_argument('--profile');q.add_argument('--fps',type=int,default=60);q.add_argument('--out',required=True)
    q=sub.add_parser('compare',help='Measure A and B using the same contract');q.add_argument('--a',required=True);q.add_argument('--b',required=True);q.add_argument('--clips');q.add_argument('--profile');q.add_argument('--fps',type=int,default=60);q.add_argument('--out',required=True)
    a=p.parse_args(argv)
    try:
        if a.command=='inspect':
            result=GLB(a.asset).validate();result['sha256']=sha256(a.asset)
            if a.out:save_json(a.out,result)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 0 if result['valid'] else 2
        if a.command=='doctor':
            from .unirig import doctor
            result=doctor(a.runtime)
        elif a.command=='infer':
            from .unirig import infer_skeleton,infer_skin
            if a.phase=='skeleton':result=infer_skeleton(a.runtime,a.input,a.job,a.seed,a.height,a.rotate_z)
            elif a.phase=='approve':
                approve_skeleton(a.job,a.sha256);result={'status':'skeleton_reviewed','sha256':a.sha256}
            else:result=infer_skin(a.job)
        elif a.command=='retarget':
            from .unirig import environment
            source=Path(a.source).resolve();target=Path(a.target).resolve();mapping=Path(a.mapping).resolve()
            blender=Path(a.blender).resolve();out=Path(a.output).resolve()
            if any(not item.is_file() for item in (source,target,mapping,blender)):
                raise ValueError('Blender, source, target and mapping must be existing files')
            if out.exists():raise ValueError('A new destination is required')
            out.parent.mkdir(parents=True,exist_ok=True);logpath=out.with_suffix('.blender.log')
            cmd=[str(blender),'--background','--factory-startup','--disable-autoexec','--python-exit-code','1',
                 '--python',str(Path(__file__).with_name('retarget.py')),'--','--source',str(source),
                 '--target',str(target),'--mapping',str(mapping),'--output',str(out)]
            with logpath.open('x',encoding='utf-8') as log:
                process=subprocess.run(cmd,env=environment(),stdout=log,stderr=subprocess.STDOUT,timeout=1800)
            if process.returncode:raise RuntimeError('Retarget failed; see '+str(logpath))
            final=out/'retarget.glb';result=GLB(final).validate()
            if not result['valid']:raise AssetError('; '.join(result['errors']))
            result.update(output=str(final),sha256=sha256(final));save_json(out/'validation.json',result)
        elif a.command=='quality':result=measure(a.asset,a.clips,a.fps,a.profile)
        elif a.command=='compare':result=compare(a.a,a.b,a.clips,a.fps,a.profile)
        if getattr(a,'out',None):save_json(a.out,result)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ValueError,OSError,RuntimeError,subprocess.SubprocessError,KeyError,IndexError) as e:
        print('ERROR: '+str(e),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
