"""Run Blender integration checks using only generated and synthetic assets."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from octorig.glb import GLB

parser = argparse.ArgumentParser()
parser.add_argument('--blender', required=True)
parser.add_argument('--workdir', required=True)
args = parser.parse_args()
blender = Path(args.blender).resolve()
work = Path(args.workdir).resolve()
if not blender.is_file() or work.exists():
    raise SystemExit('Blender must exist and workdir must be new')
work.mkdir(parents=True)
env = os.environ.copy()
env.pop('SSLKEYLOGFILE', None)


def run_script(name, script, arguments=(), blend=None):
    command = [str(blender), '--background', '--factory-startup', '--disable-autoexec', '--python-exit-code', '1']
    if blend:
        command.append(str(blend))
    command += ['--python', str(ROOT / script), '--', *map(str, arguments)]
    process = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    (work / (name + '.log')).write_text(process.stdout + '\n' + process.stderr, encoding='utf-8')
    if process.returncode:
        raise RuntimeError(f'{name} failed; see {work / (name + ".log")}')
    print(name + ': PASS', flush=True)


body = work / 'body'
run_script('body', 'octorig/body_blender.py', ['--input', ROOT/'examples/wave.glb',
           '--profile', ROOT/'octorig/body_example.json', '--output', body])
body_glb = GLB(body/'body-motion.glb')
assert body_glb.validate()['valid'] and 'GentleMotion' in body_glb.animations
assert not np.allclose(body_glb.pose('GentleMotion', 0)['meshes'][0]['positions'],
                       body_glb.pose('GentleMotion', 1)['meshes'][0]['positions']), 'Body geometry did not move'

retarget = work / 'retarget'
run_script('retarget', 'octorig/retarget.py', ['--source', ROOT/'examples/wave.glb',
           '--target', ROOT/'examples/static.glb', '--mapping', ROOT/'examples/retarget-example.json',
           '--output', retarget])
retarget_glb = GLB(retarget/'retarget.glb')
assert retarget_glb.validate()['valid'] and 'Wave' in retarget_glb.animations
assert not np.allclose(retarget_glb.pose('Wave', 0)['meshes'][0]['positions'],
                       retarget_glb.pose('Wave', 0.5)['meshes'][0]['positions']), 'Retargeted geometry did not move'

fixture = work/'face-input.blend'
run_script('face-fixture', 'tests/blender_face_fixture.py', [fixture])
config = {'schema':'octorig.face/1', 'mesh':'CharacterMesh', 'armature':'CharacterRig',
          'jaw':{'mode':'create', 'bone':'Jaw', 'parent_bone':'Head', 'head':[0,0,1],
                 'tail':[0,-0.5,1], 'axis':[1,0,0], 'jaw_seeds':[0,1,2,3],
                 'face_seeds':[4,5,6,7], 'blend':[0.35,0.65]},
          'expressions':[{'name':'Smile','pushes':[{'center':[0,0,1.5], 'radius':2,
                                                    'offset':[0.1,0,0]}]}],
          'clips':[{'name':'ExpressionTest','frames':[{'frame':1,'jaw_degrees':0,'expressions':{'Smile':0}},
                   {'frame':15,'jaw_degrees':15,'expressions':{'Smile':1}},
                   {'frame':30,'jaw_degrees':0,'expressions':{'Smile':0}}]}]}
config_path = work/'face.json'
config_path.write_text(json.dumps(config), encoding='utf-8')
face = work/'face-output.blend'
run_script('face', 'octorig/face_blender.py', ['--input', fixture, '--config', config_path, '--output', face])
run_script('face-verify', 'tests/blender_face_verify.py', blend=face)
combined_config = work/'combined.json'
run_script('combined-config', 'tests/blender_combined_config.py', [combined_config], blend=body/'body-motion.blend')
combined_face = work/'body-and-face.blend'
run_script('combined-face', 'octorig/face_blender.py', ['--input', body/'body-motion.blend',
           '--config', combined_config, '--output', combined_face])
run_script('combined-verify', 'tests/blender_combined_verify.py', blend=combined_face)
print('BLENDER_INTEGRATION_OK', flush=True)
