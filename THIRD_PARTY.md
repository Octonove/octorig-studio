# Third-party software

The root `LICENSE` applies to original code without a different license header.
The following components retain their own licenses and notices:

- `octorig/prepare_mesh.py`, `retarget.py`, `body_motion.py`,
  `body_blender.py`, `face_math.py` and `face_blender.py` are
  GPL-3.0-or-later. Their headers identify the license, reproduced in
  `LICENSES/GPL-3.0-or-later.txt`. Blender is a separate GPL-licensed program.
- `vendor/unirig` is an adapted copy of [UniRig](https://github.com/VAST-AI-Research/UniRig),
  commit `6793c6640ff01c8fb389f3993434124bb43d2933`; its MIT license is in
  `vendor/unirig/LICENSE`. It includes separately licensed components below.
  The adaptations include SDPA attention, local OPT configuration and restricted
  checkpoint loading. The vendored tree is not an unmodified upstream copy.
- Michelangelo code in `vendor/unirig/src/model/michelangelo` is GPL-3.0-or-later;
  its license and original headers are retained there.
- Pointcept code in `vendor/unirig/src/model/pointcept` carries its MIT notice.
  Some code includes adaptations from Detectron2 and OpenMMLab, whose
  notices remain in the relevant files; their upstream projects use Apache 2.0.
  A copy of that license is in `LICENSES/Apache-2.0.txt`.
- FlashAttention reference code retains its BSD-3-Clause license in
  `vendor/unirig/src/model/flash-attention-LICENSE`.
- The viewer contains [Three.js](https://threejs.org/) under MIT; its license
  is `viewer/vendor/three/LICENSE`.
- [NumPy](https://numpy.org/) and other runtime dependencies are installed
  separately and retain their own licenses.

No model checkpoints or user models are included. Checkpoint licenses and
distribution terms are separate from the code license and must be checked at
their source. This file does not grant rights to any input models or textures.
