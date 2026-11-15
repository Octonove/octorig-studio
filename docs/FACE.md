# Facial controls for a rigged character

This experimental Blender workflow creates explicit jaw and shape-key controls
on a copy of a `.blend` file. It does not detect facial anatomy or automatically
animate an arbitrary face. Choose suitable landmarks, bone names, topology and
animation values for each character, then inspect the deformation in Blender.
It preserves unrelated vertex groups and does not weld, cut or re-topologize a
mesh. It does not infer lip sync from audio.

The implementation draws on the project's earlier face-rig experiments: edge
distances for a jaw mask, a hinge bone and Gaussian landmark displacements for
expressions. Coordinates and animation below are illustrative **only**; never
reuse them as anatomical defaults. The Python modules implementing this workflow
are GPL-3.0-or-later; see `LICENSES/GPL-3.0-or-later.txt`.

## Inputs and preparation

1. Start with a local `.blend` file with a mesh skinned to an armature. Make a
   separate backup. The mesh must have an armature modifier referencing that
   armature. Linked objects and absolute shape keys are not supported.
2. For a new jaw, choose the head parent bone, jaw hinge and bone tail in
   **armature-local coordinates**, and the jaw's rotation axis in the armature
   rest coordinate system. The head vertex group must already contain weights.
   The new jaw takes only a fraction of that head group's weights; other bone
   groups are retained.
3. Identify jaw and stationary face vertex indices on the actual mesh. Distances
   travel along mesh edges; each connected component needs at least one seed of
   **each** type. Disconnected teeth, texture-seam splits and accessories may
   require manual mesh preparation or separate handling. The tool rejects
   disconnected components without coverage rather than guessing weights.
4. Choose shape-key landmark centers, radii and offsets in **mesh-local units**.
   Review the resulting shapes and adjust them for the character. Do not assume
   generic presets fit all faces. Existing shape keys must use relative mode,
   and new shape-key names must not already exist.

## Configuration example

Save a JSON file and replace all names, positions and vertex indices with values
measured on your character. If a jaw bone and matching vertex group already exist,
use `"mode": "existing"` with `bone` and `axis`; that mode does not change weights.
An existing jaw must use Blender's quaternion rotation mode.

```json
{
  "schema": "octorig.face/1",
  "mesh": "CharacterMesh",
  "armature": "CharacterRig",
  "jaw": {
    "mode": "create",
    "bone": "Jaw",
    "parent_bone": "Head",
    "head": [0.0, 0.0, 0.0],
    "tail": [0.0, 0.1, 0.0],
    "axis": [1.0, 0.0, 0.0],
    "jaw_seeds": [0],
    "face_seeds": [10],
    "blend": [0.35, 0.65]
  },
  "expressions": [
    {
      "name": "Smile",
      "attenuate_jaw": true,
      "pushes": [{"center": [0.0, 0.0, 0.0], "radius": 0.05, "offset": [0.0, 0.0, 0.01]}]
    }
  ],
  "clips": [
    {
      "name": "ExpressionTest",
      "frames": [
        {"frame": 1, "jaw_degrees": 0, "expressions": {"Smile": 0}},
        {"frame": 12, "jaw_degrees": 12, "expressions": {"Smile": 0.7}},
        {"frame": 24, "jaw_degrees": 0, "expressions": {"Smile": 0}}
      ]
    }
  ]
}
```

`jaw_seeds` and `face_seeds` must be nonempty vertex-index lists. Seed locations,
hinge orientation and angle signs depend on the mesh and rig. `blend` controls
the transition from face to jaw. `attenuate_jaw` defaults to true, reducing a
shape-key displacement in vertices already affected by the jaw. Expressions
may have multiple pushes; their offsets are summed. Each frame is an integer,
strictly increasing, and missing expression values default to zero. Animation
speed comes from the Blender scene's existing frame rate.

## Run

From the repository root, set the executable and paths for your computer:

```console
blender --background --factory-startup --disable-autoexec --python-exit-code 1 --python octorig/face_blender.py -- --input character.blend --config face.json --output character-face.blend
```

The output must be a new `.blend` filename. The input is never saved over. The
created tracks are muted by default to avoid unexpectedly combining them with
existing animation. To inspect a clip, open the output in Blender and unmute the
matching track on both the armature and shape-key NLA stacks. Inspect the teeth,
lips, seams and all views between keys, then adjust or animate the controls as
needed. No final animation or collision quality is certified by this tool.

**Current verification status:** geometry helpers and input validation have
automated Python tests. In Blender 5.2.2, a generated synthetic mesh was rigged,
its facial tracks were activated through the NLA editor operations, and tests
confirmed jaw motion, expression values and deformation of mesh vertices.
Artistic quality and performance on diverse real-world models have not been
visually verified; treat the workflow as experimental.
