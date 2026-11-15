"""Blender-independent glTF 2.0 reader and evaluator.

Only self-contained GLB, triangle meshes and linear skinning are supported. This fails explicitly
for Draco, morph targets and other data this evaluator cannot interpret.
"""
import json
import math
import struct
from pathlib import Path
import numpy as np


class AssetError(ValueError):
    pass


DTYPES={5120:np.dtype('i1'),5121:np.dtype('u1'),5122:np.dtype('<i2'),
        5123:np.dtype('<u2'),5125:np.dtype('<u4'),5126:np.dtype('<f4')}
WIDTH={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT2':4,'MAT3':9,'MAT4':16}


def write_glb(path, doc, binary):
    binary=bytes(binary);binary+=b'\0'*(-len(binary)%4)
    doc['buffers']=[{'byteLength':len(binary)}]
    data=json.dumps(doc,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode()
    data+=b' '*(-len(data)%4)
    Path(path).write_bytes(struct.pack('<III',0x46546c67,2,28+len(data)+len(binary))+
        struct.pack('<II',len(data),0x4e4f534a)+data+
        struct.pack('<II',len(binary),0x004e4942)+binary)


def quat_matrix(q):
    q=np.asarray(q,dtype=float)
    if not np.isfinite(q).all() or np.linalg.norm(q)<1e-12:raise AssetError('Invalid quaternion')
    x,y,z,w=q/np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


def slerp(q,r,u):
    q=np.asarray(q,float);r=np.asarray(r,float)
    q=q/np.linalg.norm(q);r=r/np.linalg.norm(r);dot=float(np.dot(q,r))
    if dot<0:r=-r;dot=-dot
    if dot>.9995:
        v=q*(1-u)+r*u;return v/np.linalg.norm(v)
    angle=math.acos(np.clip(dot,-1,1))
    return (q*math.sin((1-u)*angle)+r*math.sin(u*angle))/math.sin(angle)


class GLB:
    def __init__(self,path):
        self.path=Path(path);data=self.path.read_bytes();self._cache={}
        if len(data)<28:raise AssetError('Truncated GLB')
        magic,version,size=struct.unpack_from('<III',data)
        if magic!=0x46546c67 or version!=2 or size!=len(data):raise AssetError('Invalid GLB header or length')
        chunks=[];at=12
        while at<len(data):
            if at+8>len(data):raise AssetError('Truncated chunk header')
            n,t=struct.unpack_from('<II',data,at);at+=8
            if n%4 or at+n>len(data):raise AssetError('Chunk extends beyond the file')
            chunks.append((t,data[at:at+n]));at+=n
        if chunks[0][0]!=0x4e4f534a:raise AssetError('Missing glTF JSON')
        try:self.doc=json.loads(chunks[0][1])
        except (ValueError,UnicodeError) as e:raise AssetError('Invalid JSON') from e
        bins=[b for t,b in chunks if t==0x004e4942]
        self.binary=bins[0] if bins else b''
        buffers=self.doc.get('buffers',[])
        if len(buffers)!=1 or 'uri' in buffers[0]:raise AssetError('Only embedded GLB buffers are supported')
        if buffers[0].get('byteLength',0)>len(self.binary):raise AssetError('Truncated buffer')
        if any('uri' in im for im in self.doc.get('images',[])):raise AssetError('External textures are not allowed')
        for ext in self.doc.get('extensionsRequired',[]):
            if ext not in ('KHR_materials_unlit',):raise AssetError('Required extension is not evaluated: '+ext)
        self.nodes=self.doc.get('nodes',[]);self.parents={}
        for i,n in enumerate(self.nodes):
            for c in n.get('children',[]):
                if not isinstance(c,int) or not 0<=c<len(self.nodes):raise AssetError('Invalid child index')
                if c in self.parents:raise AssetError('Node has multiple parents')
                self.parents[c]=i
        for i in range(len(self.nodes)):
            seen=set();k=i
            while k in self.parents:
                if k in seen:raise AssetError('Cycle in hierarchy')
                seen.add(k);k=self.parents[k]
        self.animations={a.get('name',str(i)):a for i,a in enumerate(self.doc.get('animations',[]))}
        if len(self.animations)!=len(self.doc.get('animations',[])):raise AssetError('Clips have duplicate names')

    def _view(self,index):
        try:v=self.doc['bufferViews'][index]
        except (IndexError,KeyError,TypeError):raise AssetError('Unknown bufferView')
        off=v.get('byteOffset',0);length=v.get('byteLength',-1)
        if v.get('buffer',0)!=0 or off<0 or length<0 or off+length>len(self.binary):raise AssetError('bufferView extends beyond the buffer')
        return v,off,length

    def accessor(self,index):
        if index in self._cache:return self._cache[index]
        try:a=self.doc['accessors'][index];dt=DTYPES[a['componentType']];w=WIDTH[a['type']];count=a['count']
        except (KeyError,IndexError,TypeError):raise AssetError('Unknown accessor or unsupported format')
        if count<0 or count>100_000_000:raise AssetError('Invalid accessor count')
        if a['type'] in ('MAT2','MAT3') and dt.itemsize<4:raise AssetError('Compact matrices are not supported')
        if 'bufferView' not in a:arr=np.zeros((count,w),dtype=dt)
        else:
            view,offset,length=self._view(a['bufferView']);start=a.get('byteOffset',0);stride=view.get('byteStride',dt.itemsize*w)
            end=start+(count-1)*stride+dt.itemsize*w if count else start
            if start<0 or stride<dt.itemsize*w or end>length:raise AssetError('Accessor exceeds its bufferView')
            arr=np.ndarray((count,w),dtype=dt,buffer=self.binary,offset=offset+start,strides=(stride,dt.itemsize)).copy()
        if 'sparse' in a:
            sp=a['sparse'];n=sp['count'];ix=sp['indices'];vals=sp['values']
            idt=DTYPES.get(ix['componentType'])
            if idt is None or idt.kind!='u':raise AssetError('Invalid sparse indices')
            _,io,il=self._view(ix['bufferView']);_,vo,vl=self._view(vals['bufferView'])
            ios=ix.get('byteOffset',0);vos=vals.get('byteOffset',0)
            if n<0 or ios<0 or vos<0 or ios+n*idt.itemsize>il or vos+n*w*dt.itemsize>vl:raise AssetError('Sparse data exceeds the buffer')
            ids=np.frombuffer(self.binary,dtype=idt,count=n,offset=io+ios)
            if n and (ids.max()>=count or np.any(np.diff(ids.astype('i8'))<=0)):raise AssetError('Sparse indices are out of range or unordered')
            arr[ids]=np.frombuffer(self.binary,dtype=dt,count=n*w,offset=vo+vos).reshape(n,w)
        if a.get('normalized') and dt.kind in 'ui':
            arr=arr.astype(float)/np.iinfo(dt).max
            if dt.kind=='i':arr=np.maximum(arr,-1)
        self._cache[index]=arr
        return arr

    def duration(self,clip):
        if clip not in self.animations:raise AssetError('Clip does not exist: '+str(clip))
        return max((float(self.accessor(s['input'])[-1,0]) for s in self.animations[clip]['samplers']),default=0.)

    def pose(self,clip=None,time=0.,surfaces=True):
        if clip is not None and clip not in self.animations:raise AssetError('Clip does not exist: '+str(clip))
        states=[{k:np.asarray(n.get(k,d),float) for k,d in [('translation',[0,0,0]),('rotation',[0,0,0,1]),('scale',[1,1,1])]} for n in self.nodes]
        if clip is not None:
            a=self.animations[clip]
            for ch in a['channels']:
                sa=a['samplers'][ch['sampler']];ts=self.accessor(sa['input']).ravel();vs=self.accessor(sa['output']);target=ch['target'];path=target['path'];node=target['node']
                if path not in ('translation','rotation','scale'):raise AssetError('Channel is not evaluated: '+path)
                if 'matrix' in self.nodes[node]:raise AssetError('Animated TRS on a static matrix')
                if len(ts)==0 or not np.isfinite(ts).all() or np.any(np.diff(ts)<=0):raise AssetError('Times are non-finite or not increasing')
                mode=sa.get('interpolation','LINEAR')
                expected=len(ts)*3 if mode=='CUBICSPLINE' else len(ts)
                if len(vs)!=expected:raise AssetError('Incomplete animation samples')
                i=max(0,min(len(ts)-2,int(np.searchsorted(ts,time,side='right')-1))) if len(ts)>1 else 0
                u=float(np.clip((time-ts[i])/(ts[i+1]-ts[i]),0,1)) if len(ts)>1 else 0.
                if mode=='STEP' or len(ts)==1:v=vs[i*3+1] if mode=='CUBICSPLINE' else vs[i]
                elif mode=='LINEAR':v=slerp(vs[i],vs[i+1],u) if path=='rotation' else vs[i]*(1-u)+vs[i+1]*u
                elif mode=='CUBICSPLINE':
                    dt=float(ts[i+1]-ts[i]);v=(2*u**3-3*u*u+1)*vs[3*i+1]+(u**3-2*u*u+u)*dt*vs[3*i+2]+(-2*u**3+3*u*u)*vs[3*i+4]+(u**3-u*u)*dt*vs[3*i+3]
                    if path=='rotation':v=v/np.linalg.norm(v)
                else:raise AssetError('Unknown interpolation: '+mode)
                states[node][path]=v
        world={}
        def matrix(i):
            if i in world:return world[i]
            n=self.nodes[i];s=states[i]
            if 'matrix' in n:m=np.asarray(n['matrix'],float).reshape(4,4,order='F')
            else:
                m=np.eye(4);m[:3,:3]=quat_matrix(s['rotation'])@np.diag(s['scale']);m[:3,3]=s['translation']
            if i in self.parents:m=matrix(self.parents[i])@m
            if not np.isfinite(m).all():raise AssetError('Non-finite transformation')
            world[i]=m;return m
        for i in range(len(self.nodes)):matrix(i)
        meshes=[]
        if surfaces:
            for i,n in enumerate(self.nodes):
                if 'mesh' not in n:continue
                mesh=self.doc['meshes'][n['mesh']]
                if mesh.get('weights'):raise AssetError('Morph targets are not evaluated')
                for pi,pr in enumerate(mesh['primitives']):
                    if pr.get('targets') or pr.get('mode',4)!=4:raise AssetError('Only triangles without morph targets are supported')
                    attr=pr['attributes'];pos=self.accessor(attr['POSITION']);vh=np.column_stack((pos,np.ones(len(pos))))
                    if 'skin' in n:
                        sk=self.doc['skins'][n['skin']];ib=self.accessor(sk['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1) if 'inverseBindMatrices' in sk else np.tile(np.eye(4),(len(sk['joints']),1,1))
                        jm=np.asarray([matrix(k)@m for k,m in zip(sk['joints'],ib)]);vv=np.zeros((len(pos),4))
                        for suffix in ('0','1'):
                            if 'JOINTS_'+suffix not in attr:continue
                            ids=self.accessor(attr['JOINTS_'+suffix]).astype(int);weights=self.accessor(attr['WEIGHTS_'+suffix])
                            if ids.min()<0 or ids.max()>=len(jm):raise AssetError('Joint index is out of range')
                            for k in range(ids.shape[1]):vv+=np.einsum('nij,nj->ni',jm[ids[:,k]],vh)*weights[:,k,None]
                        pos=vv[:,:3]
                    else:pos=(matrix(i)@vh.T).T[:,:3]
                    ix=self.accessor(pr['indices']).ravel().astype(int) if 'indices' in pr else np.arange(len(pos))
                    meshes.append({'name':n.get('name',str(i)),'node':i,'primitive':pi,'positions':pos,'triangles':ix.reshape(-1,3)})
        return {'world':world,'named_world':{n.get('name',str(i)):world[i] for i,n in enumerate(self.nodes)},'meshes':meshes}

    def validate(self):
        errors=[];vertices=triangles=0;weight_deviation=0.
        for mi,mesh in enumerate(self.doc.get('meshes',[])):
            for pr in mesh['primitives']:
                try:
                    at=pr['attributes'];p=self.accessor(at['POSITION']);vertices+=len(p)
                    if not np.isfinite(p).all():errors.append('Non-finite positions')
                    ids=self.accessor(pr['indices']).ravel() if 'indices' in pr else np.arange(len(p));triangles+=len(ids)//3
                    if len(ids)%3 or (len(ids) and ids.max()>=len(p)):errors.append('Invalid triangles or indices')
                    total=np.zeros(len(p))
                    for suffix in ('0','1'):
                        if 'WEIGHTS_'+suffix in at:
                            w=self.accessor(at['WEIGHTS_'+suffix]);total+=w.sum(axis=1)
                            if not np.isfinite(w).all() or np.any(w<0):errors.append('Non-finite or negative weights')
                    if 'WEIGHTS_0' in at:
                        dev=float(np.max(np.abs(total-1)));weight_deviation=max(weight_deviation,dev)
                        if dev>2e-3:errors.append('Weights are not normalized')
                except (AssetError,ValueError,IndexError,KeyError) as e:errors.append(f'Mesh {mi}: {e}')
        try:self.pose(surfaces=True)
        except (AssetError,ValueError,IndexError,KeyError) as e:errors.append(str(e))
        for name in self.animations:
            try:
                dur=self.duration(name)
                if not math.isfinite(dur) or dur<0:raise AssetError('Invalid duration')
                self.pose(name,dur*.5,surfaces=False)
            except (AssetError,ValueError,IndexError,KeyError) as e:errors.append(f'Clip {name}: {e}')
        return {'valid':not errors,'errors':errors,'vertices':vertices,'triangles':triangles,
                'bones':sum(len(x['joints']) for x in self.doc.get('skins',[])),
                'weight_sum_max_deviation':weight_deviation,
                'clips':[{'name':n,'duration':self.duration(n)} for n in self.animations]}
