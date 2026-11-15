"""Windows compatibility: original default MHA plus SDPA varlen attention.

UniRig only constructs MHA(cross_attn=True), whose upstream default is ordinary
PyTorch attention, not FlashAttention. Load those upstream classes unchanged,
without importing the compiled package. Learned parameter names stay exact.
The PTv3 varlen entry point uses native PyTorch SDPA on identical segments.
"""
import ast
import math
from functools import partial
from pathlib import Path
from types import SimpleNamespace
import torch
from torch import nn
import torch.nn.functional as F
from einops import rearrange, repeat

_path=Path(__file__).with_name('flash_mha_upstream_v2.8.3.py')
_tree=ast.parse(_path.read_text(encoding='utf-8'))
_classes=[node for node in _tree.body if isinstance(node,ast.ClassDef) and node.name in ('SelfAttention','CrossAttention','MHA')]
assert len(_classes)==3
_unmodified_scope={'__name__':__name__,'torch':torch,'nn':nn,'math':math,'partial':partial,'rearrange':rearrange,'repeat':repeat}
exec(compile(ast.fix_missing_locations(ast.Module(body=_classes,type_ignores=[])),str(_path),'exec'),_unmodified_scope)
MHA=_unmodified_scope['MHA']

def flash_attn_varlen_qkvpacked_func(qkv,cu_seqlens,max_seqlen,dropout_p=0.0,softmax_scale=None,causal=False,**kwargs):
    assert not causal and not kwargs,('unsupported attention options',causal,kwargs)
    assert qkv.ndim==4 and qkv.shape[1]==3
    limits=cu_seqlens.detach().cpu().tolist()
    assert limits[0]==0 and limits[-1]==qkv.shape[0]
    chunks=[]
    for start,end in zip(limits,limits[1:]):
        q,k,v=qkv[start:end].unbind(dim=1)
        q=q.transpose(0,1).unsqueeze(0)
        k=k.transpose(0,1).unsqueeze(0)
        v=v.transpose(0,1).unsqueeze(0)
        result=F.scaled_dot_product_attention(q,k,v,attn_mask=None,dropout_p=dropout_p,is_causal=False,scale=softmax_scale)
        chunks.append(result.squeeze(0).transpose(0,1))
    return torch.cat(chunks,dim=0)

flash_attn_compat=SimpleNamespace(flash_attn_varlen_qkvpacked_func=flash_attn_varlen_qkvpacked_func)
