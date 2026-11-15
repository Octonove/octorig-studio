import copy
import io
import json
import struct
import unittest
import tempfile
from unittest.mock import patch
from contextlib import redirect_stderr,redirect_stdout
from pathlib import Path
import numpy as np
from test_core import fixture,TEST_TMP
from octorig.glb import GLB,AssetError,write_glb
from octorig.jobs import artifact,save_json,new_job,approve_skeleton,sha256
from octorig.unirig import runtime_config,infer_skin,environment
from octorig.cli import main


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=TEST_TMP);self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_artifact_cannot_escape_job(self):
        with self.assertRaises(ValueError):artifact(self.root,'../outside')
    def test_skin_requires_review(self):
        source=self.root/'x.glb';fixture(source);job=new_job(self.root/'job',source,{})
        with self.assertRaisesRegex(ValueError,'review'):infer_skin(job)
    def test_backend_success_cannot_admit_corrupt_glb(self):
        source=self.root/'x.glb';fixture(source)
        cfg={'python':'python','checkpoint_sha256':{}}
        job=new_job(self.root/'job',source,cfg);work=job/'runtime';(work/'inference').mkdir(parents=True);(work/'input').mkdir()
        skeleton=work/'inference/skeleton.fbx';skeleton.write_bytes(b'reviewed skeleton')
        prepared=work/'input/body.glb';fixture(prepared)
        state=json.loads((job/'job.json').read_text());state.update(status='skeleton_reviewed',skeleton='runtime/inference/skeleton.fbx',approved_skeleton_sha256=sha256(skeleton),prepared='runtime/input/body.glb',prepared_sha256=sha256(prepared),seed=123)
        save_json(job/'job.json',state)
        def broken_backend(job,label,argv,needed,cwd=None,timeout=1200):
            target=Path(needed);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b'NOT_A_GLB')
        with patch('octorig.unirig._run',broken_backend):
            with self.assertRaises(RuntimeError):infer_skin(job)
        self.assertEqual(json.loads((job/'job.json').read_text())['status'],'failed')
    def test_runtime_rejects_wrong_checkpoint_hash(self):
        sw=self.root/'software';(sw/'src').mkdir(parents=True);(sw/'configs').mkdir();(sw/'run.py').write_text('')
        ck=self.root/'ck';ck.mkdir();(ck/'skeleton.ckpt').write_bytes(b'x');(ck/'skin.ckpt').write_bytes(b'y')
        exe=self.root/'python.exe';exe.write_bytes(b'not executed')
        cfg={'schema':'octorig.runtime/1','python':str(exe),'blender':str(exe),'software':str(sw),'checkpoints':str(ck),
             'checkpoint_sha256':{'skeleton':'0'*64,'skin':'0'*64}}
        path=self.root/'runtime.json';save_json(path,cfg)
        with self.assertRaisesRegex(ValueError,'SHA256'):runtime_config(path)
    def test_environment_disables_telemetry_without_touching_parent(self):
        e=environment();self.assertEqual(e['HF_HUB_OFFLINE'],'1');self.assertEqual(e['WANDB_MODE'],'disabled');self.assertNotIn('SSLKEYLOGFILE',e)
    def test_inspect_corrupt_input_returns_nonzero(self):
        p=self.root/'bad.glb';p.write_bytes(b'notGLB')
        with redirect_stderr(io.StringIO()),redirect_stdout(io.StringIO()):code=main(['inspect',str(p)])
        self.assertEqual(code,2)
    def test_retarget_rejects_missing_inputs_before_starting_blender(self):
        with patch('subprocess.run') as run, redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            code=main(['retarget','--blender',str(self.root/'missing-blender'),
                       '--source',str(self.root/'missing-source'), '--target',str(self.root/'missing-target'),
                       '--mapping',str(self.root/'missing-mapping'), '--output',str(self.root/'new-output')])
        self.assertEqual(code,2)
        run.assert_not_called()
    def test_unknown_runtime_schema(self):
        f=self.root/'x.json';save_json(f,{'schema':'future'})
        with self.assertRaisesRegex(ValueError,'Unsupported'):runtime_config(f)
    def test_atomic_json_replaces_cleanly(self):
        f=self.root/'data.json';save_json(f,{'a':1});save_json(f,{'a':2})
        self.assertEqual(json.loads(f.read_text()),{'a':2});self.assertFalse(f.with_suffix('.json.tmp').exists())
    def test_rejects_multiple_parents(self):
        p=self.root/'x.glb';fixture(p,nodes=[{'children':[2]},{'children':[2]},{}])
        with self.assertRaisesRegex(AssetError,'multiple parents'):GLB(p)
    def test_rejects_negative_weights(self):
        p=self.root/'x.glb';d,b=fixture(p);off=d['bufferViews'][2]['byteOffset'];b[off:off+4]=struct.pack('<f',-1);write_glb(p,d,b)
        self.assertFalse(GLB(p).validate()['valid'])
    def test_rejects_invalid_joint_index(self):
        p=self.root/'x.glb';d,b=fixture(p);off=d['bufferViews'][1]['byteOffset'];b[off]=8;write_glb(p,d,b)
        self.assertFalse(GLB(p).validate()['valid'])
    def test_rejects_zero_quaternion(self):
        p=self.root/'x.glb';fixture(p,nodes=[{'rotation':[0,0,0,0]},{'mesh':0,'skin':0}])
        self.assertFalse(GLB(p).validate()['valid'])
    def test_rejects_duplicate_clips(self):
        p=self.root/'x.glb';d,b=fixture(p);d['animations']*=2;write_glb(p,d,b)
        with self.assertRaisesRegex(AssetError,'duplicate'):GLB(p)
    def test_rejects_non_monotonic_animation(self):
        p=self.root/'x.glb';d,b=fixture(p);off=d['bufferViews'][4]['byteOffset'];b[off:off+8]=struct.pack('<ff',1,0);write_glb(p,d,b)
        self.assertFalse(GLB(p).validate()['valid'])
    def test_cubic_interpolation_tangents(self):
        p=self.root/'x.glb';d,b=fixture(p)
        values=np.array([[0,0,0],[0,0,0],[0,0,0],[0,0,0],[0,0,2],[0,0,0]],dtype='<f4')
        b.extend(b'\0'*(-len(b)%4));off=len(b);b.extend(values.tobytes())
        d['bufferViews'].append({'buffer':0,'byteOffset':off,'byteLength':values.nbytes})
        d['accessors'][5].update(bufferView=len(d['bufferViews'])-1,count=6)
        d['animations'][0]['samplers'][0]['interpolation']='CUBICSPLINE';write_glb(p,d,b)
        np.testing.assert_allclose(GLB(p).pose('move',.5)['meshes'][0]['positions'][:,2],1.)

if __name__=='__main__':unittest.main()
