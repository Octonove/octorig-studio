"""Derive test-only seeds from the synthetic body fixture."""
import json
import sys
from pathlib import Path
import bpy

output = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
if output.exists():
    raise ValueError('Configuration output already exists')
mesh = bpy.data.objects['SyntheticBody']
adj = [set() for _ in mesh.data.vertices]
for edge in mesh.data.edges:
    a, b = edge.vertices
    adj[a].add(b)
    adj[b].add(a)
remaining = set(range(len(adj)))
jaw_seeds, face_seeds = [], []
while remaining:
    root = min(remaining)
    stack, component = [root], set()
    while stack:
        index = stack.pop()
        if index in component:
            continue
        component.add(index)
        stack.extend(adj[index] - component)
    remaining -= component
    if len(component) < 2:
        raise ValueError('Synthetic mesh component is too small for seed selection')
    order = sorted(component, key=lambda i: (mesh.data.vertices[i].co.z, i))
    jaw_seeds.append(order[0])
    face_seeds.append(order[-1])
config = {'schema':'octorig.face/1', 'mesh':'SyntheticBody', 'armature':'TestArmature',
          'jaw':{'mode':'create', 'bone':'Jaw', 'parent_bone':'Upper', 'head':[0,0,1],
                 'tail':[0,-0.5,1], 'axis':[1,0,0], 'jaw_seeds':jaw_seeds,
                 'face_seeds':face_seeds, 'blend':[0.35,0.65]},
          'expressions':[{'name':'Smile','pushes':[{'center':[0,0,1.5], 'radius':2,
                                                    'offset':[0.1,0,0]}]}],
          'clips':[{'name':'ExpressionTest','frames':[{'frame':1,'jaw_degrees':0,'expressions':{'Smile':0}},
                   {'frame':15,'jaw_degrees':15,'expressions':{'Smile':1}},
                   {'frame':30,'jaw_degrees':0,'expressions':{'Smile':0}}]}]}
output.write_text(json.dumps(config), encoding='utf-8')
