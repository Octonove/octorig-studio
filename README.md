# OctoRig Studio

Local tools for preparing 3D character rigs, creating editable body and facial
animation, and inspecting the result. OctoRig combines an adapted UniRig source
snapshot with Blender scripts and a local GLB viewer. It does not require an
OctoRig account, and no project models or model checkpoints are bundled.

**Early development:** the Blender authoring and retargeting tools have been
tested with synthetic rigs and need real-character artistic review. Rigs differ in topology, orientation,
weights and anatomy; profiles and facial landmarks must be configured for each
model. The tools do not automatically animate every type of object, create
lip-sync from audio, or guarantee good deformation and ground contacts.

## What is included

- Rigging in stages: prepare a static GLB, predict a skeleton using UniRig,
  review it, then infer skin weights. This requires a separately installed ML
  environment and checkpoints.
- [Body animation](docs/BODY.md): map bones explicitly, describe editable poses,
  bake named clips, and export GLB and Blender files. Example motion profiles
  are starting points for compatible rigs.
- [Facial controls](docs/FACE.md): configure jaw landmarks and shape-key
  displacements, then create editable controls and facial animation in Blender.
- [Retargeting](docs/RETARGET.md): transfer existing clips using an explicit
  bone mapping and compatible rig orientations.
- GLB inspection and comparison, plus a local viewer for existing animations.

## Install the Python tools

Use Python 3.11 or later. From a checkout of this repository:

```console
python -m venv .venv
```

Activate `.venv` for your operating system, then run:

```console
python -m pip install -e .
python -m octorig --help
python -m octorig inspect examples/wave.glb
python -m unittest discover -s tests -v
```

The package requires NumPy. Blender authoring requires a separate trusted
Blender installation; the repository checkout contains the viewer, UniRig
source and documentation. An installed Python wheel does not include them.

## Configure automatic rigging

Install a compatible UniRig ML environment separately, including its CUDA and
PyTorch dependencies; see [upstream UniRig](https://github.com/VAST-AI-Research/UniRig)
for guidance. The included dependency list is not a verified universal
installer. Obtain the skeleton and skin checkpoints from the
[official model repository](https://huggingface.co/VAST-AI/UniRig), review their
terms, and place them as `skeleton.ckpt` and `skin.ckpt` in one directory.
Checkpoint versions must match the bundled software. No checkpoints are
downloaded automatically.

Copy `runtime.example.json` to `.local/runtime.json`. Edit the paths to the
ML Python executable, Blender and checkpoint directory, and enter the SHA-256
hash of each checkpoint. Relative paths are resolved from the JSON file; the
example `../vendor/unirig` is relative to `.local/runtime.json`.

```console
python -m octorig doctor --runtime .local/runtime.json
python -m octorig infer skeleton --runtime .local/runtime.json --input your-model.glb --job jobs/example
```

Review the generated skeleton in Blender. Calculate the reviewed file's
SHA-256, then approve it with `python -m octorig infer approve --job
jobs/example --sha256 REVIEWED_HASH` before `python -m octorig infer skin --job
jobs/example`. Each job records local paths and hashes and is not automatically
portable to a different computer. Keep job folders and personal models private.
The inference workflow has been checked locally with a real character; skeleton
quality was checked structurally for that test, not approved visually.

## View a GLB locally

From the checkout root run:

```console
python -m http.server 5211 --bind 127.0.0.1 --directory viewer
```

Open `http://127.0.0.1:5211/` and choose a self-contained GLB, such as
`examples/wave.glb`. Your file is handled in your browser and external model
resources are rejected. The viewer plays existing animations; it does not
author them. Its parser is tested, but the interface has not yet been visually
verified in a browser in this environment.

## License

Original code without a different header is MIT licensed; selected Blender and
animation modules are GPL-3.0-or-later. Bundled dependencies have their own
licenses, and model checkpoints are separate. See [THIRD_PARTY.md](THIRD_PARTY.md)
and the notices distributed alongside those components.
