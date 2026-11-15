import json
import struct
import tempfile
import unittest
from pathlib import Path
import numpy as np
from octorig.glb import GLB, AssetError, write_glb
from octorig.jobs import new_job, approve_skeleton, load_job, sha256

TEST_TMP=Path(__file__).resolve().parents[1]/'.local'/'test-tmp'
TEST_TMP.mkdir(parents=True,exist_ok=True)


def fixture(path, **overrides):
    binary = bytearray()
    views, accessors = [], []
    def add(values, dtype, kind, ct):
        arr = np.asarray(values, dtype=dtype)
        binary.extend(b'\0' * (-len(binary) % 4))
        views.append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': arr.nbytes})
        binary.extend(arr.tobytes())
        accessors.append({'bufferView': len(views)-1, 'componentType': ct,
                          'type': kind, 'count': len(arr)})
        return len(accessors)-1
    pos=add([[0,0,0],[1,0,0],[0,1,0]],'<f4','VEC3',5126)
    ids=add([[0,0,0,0]]*3,'u1','VEC4',5121)
    weights=add([[1,0,0,0]]*3,'<f4','VEC4',5126)
    ibm=add([np.eye(4).flatten(order='F')],'<f4','MAT4',5126)
    times=add([[0],[1]],'<f4','SCALAR',5126)
    trs=add([[0,0,0],[0,0,2]],'<f4','VEC3',5126)
    doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],
         'bufferViews':views,'accessors':accessors,'scenes':[{'nodes':[0,1]}],
         'nodes':[{'name':'bone'}, {'name':'body','mesh':0,'skin':0}],
         'meshes':[{'primitives':[{'attributes':{'POSITION':pos,'JOINTS_0':ids,'WEIGHTS_0':weights}}]}],
         'skins':[{'joints':[0],'inverseBindMatrices':ibm}],
         'animations':[{'name':'move','samplers':[{'input':times,'output':trs}],
                        'channels':[{'sampler':0,'target':{'node':0,'path':'translation'}}]}]}
    doc.update(overrides)
    write_glb(path,doc,binary)
    return doc,binary


class GLBTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=TEST_TMP); self.p=Path(self.tmp.name)/'test.glb'
    def tearDown(self): self.tmp.cleanup()
    def test_evaluates_animation_and_skin_world_space(self):
        fixture(self.p); g=GLB(self.p)
        np.testing.assert_allclose(g.pose('move',.5)['meshes'][0]['positions'],[[0,0,1],[1,0,1],[0,1,1]])
    def test_rejects_bad_length(self):
        self.p.write_bytes(b'glTF'+struct.pack('<II',2,100)+b'x'*10)
        with self.assertRaises(AssetError): GLB(self.p)
    def test_rejects_accessor_overrun(self):
        d,b=fixture(self.p);d['accessors'][0]['count']=99999;write_glb(self.p,d,b)
        with self.assertRaises(AssetError):GLB(self.p).accessor(0)
    def test_rejects_cycles(self):
        fixture(self.p,nodes=[{'children':[1]},{'children':[0]}])
        with self.assertRaises(AssetError):GLB(self.p)
    def test_reports_non_normalized_weights(self):
        d,b=fixture(self.p);off=d['bufferViews'][2]['byteOffset'];b[off:off+4]=struct.pack('<f',.4);write_glb(self.p,d,b)
        self.assertTrue(any('normaliz' in x for x in GLB(self.p).validate()['errors']))
    def test_rejects_external_buffers(self):
        d,b=fixture(self.p);d['buffers'][0]['uri']='../../secret'
        jb=json.dumps(d).encode();jb+=b' '*(-len(jb)%4)
        self.p.write_bytes(struct.pack('<III',0x46546c67,2,28+len(jb)+len(b))+
            struct.pack('<II',len(jb),0x4e4f534a)+jb+struct.pack('<II',len(b),0x004e4942)+b)
        with self.assertRaises(AssetError):GLB(self.p)
    def test_unknown_clip_does_not_silently_use_idle(self):
        fixture(self.p)
        with self.assertRaises(AssetError):GLB(self.p).pose('missing',0)
    def test_normalized_integer_accessors(self):
        d,b=fixture(self.p);d['accessors'][1]['normalized']=True
        d['bufferViews'][1]['byteOffset']=0;write_glb(self.p,d,b)
        self.assertEqual(GLB(self.p).accessor(1).dtype,np.float64)


class JobTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=TEST_TMP);self.root=Path(self.tmp.name)
        self.src=self.root/'source.glb';fixture(self.src)
    def tearDown(self):self.tmp.cleanup()
    def test_refuses_nonempty_work_directory(self):
        path=self.root/'job';path.mkdir();(path/'keep').write_text('x')
        with self.assertRaises(ValueError):new_job(path,self.src,{})
        self.assertEqual((path/'keep').read_text(),'x')
    def test_approval_bound_to_real_skeleton_hash(self):
        job=new_job(self.root/'job',self.src,{})
        f=job/'skeleton.fbx';f.write_bytes(b'new-skeleton')
        state=load_job(job);state['status']='skeleton_ready';state['skeleton']='skeleton.fbx'
        (job/'job.json').write_text(json.dumps(state))
        with self.assertRaises(ValueError):approve_skeleton(job,'bad')
        approve_skeleton(job,sha256(f))
        self.assertEqual(load_job(job)['status'],'skeleton_reviewed')
    def test_detects_changed_source(self):
        job=new_job(self.root/'job',self.src,{})
        self.src.write_bytes(b'changed')
        with self.assertRaises(ValueError):load_job(job,verify_source=True)

if __name__=='__main__':unittest.main()
