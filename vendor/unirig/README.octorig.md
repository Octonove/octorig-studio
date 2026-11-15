# UniRig software in OctoRig Studio

This is an adapted source snapshot of VAST-AI-Research/UniRig at commit
`6793c6640ff01c8fb389f3993434124bb43d2933`. Its source license and notices
remain alongside the code. Changes inherited by this copy include SDPA
attention compatibility, local OPT configuration, and a restricted checkpoint
allowlist while retaining weights-only loading. See the root THIRD_PARTY.md
for bundled components with their own licenses.

Checkpoints, datasets, Python environments and caches are not included. The
upstream requirements file is informational; it is not a verified installer for
every platform or GPU. Configure your own compatible ML environment and verify
the model files and their terms before use. OctoRig copies this software into
each job and does not install packages or download checkpoints automatically.
