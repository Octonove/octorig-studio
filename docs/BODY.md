# Body animation from mapped poses

This experimental workflow bakes configurable rotations and translations onto
an existing rigged GLB. It uses the bone's rest orientation to translate
character-axis rotations into each bone's local space, samples poses on every
frame, preserves quaternion continuity, and exports named NLA tracks as GLB
animations. These are techniques used in the original animation workflow, now
driven by an explicit mapping and independent of any particular character.

**Status:** profile validation and sampling have automated Python tests. The
Blender bake and export have also been checked on a synthetic rig in Blender
5.2.2. Real characters and visual quality still need individual review.

## Example

From the repository root, replace `BLENDER` with the path to Blender:

```sh
BLENDER --background --factory-startup --disable-autoexec --python-exit-code 1 \
  --python octorig/body_blender.py -- --input examples/wave.glb \
  --profile octorig/body_example.json --output jobs/example-body
```

`jobs/example-body` must not exist. The script writes a new editable
`body-motion.blend`, `body-motion.glb`, and a small JSON result report there;
the source file is not modified. The example uses a synthetic two-bone model
and creates a single gentle loop. In a model with multiple armatures, pass
`--armature NAME`.

`octorig/body_humanoid_example.json` is a separate **starting template** for
Idle, Roar, and Slam body movements. Its sample bone names are placeholders:
edit the mapping, orientation, poses, and scale for the target model before
using it. These templates have not been tested on a real character. The Slam
does not plant hands or feet and does not guarantee contact with the ground.

## Using another character

Make a copy of `octorig/body_example.json`. Map each semantic role to an exact,
unique bone name in the model; the role labels are arbitrary. For each clip,
give a unique name, a duration in seconds, and poses at increasing `phase`
values from 0 to 1. Each pose maps roles to `rotation` and/or `translation`
vectors. An omitted role or component is zero at that pose. Rotations are XYZ
Euler angles in degrees from the rest pose; translations are in model units.
`rotation_scale` and `translation_scale` allow overall adjustments.

The vectors are expressed in character axes that initially match world XYZ.
`character_axes_degrees` rotates those axes relative to world XYZ, allowing a
different character orientation. Test each bone individually before composing a
clip: anatomy, bind pose, bone roll, joint limits, and front direction differ
across assets. Frame rate is an integer from 1 to 120 and clip duration must
align to a whole number of frames. Looping clips must end at the starting pose.

The tool does not discover a skeleton mapping, generate an animation from a
text prompt, solve IK, plant feet, or guarantee collision-free movement. It does
not create a facial rig. It replaces animation tracks on the chosen armature in
the exported copy, while leaving the original input file untouched. Review the
motion, floor contacts, other animated objects and deformation in Blender.

`body_motion.py` and `body_blender.py` are GPL-3.0-or-later; see
`LICENSES/GPL-3.0-or-later.txt`. They do not confer rights to input assets.
