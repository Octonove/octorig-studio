# Transfer an animation between rigs

The experimental retarget script transfers existing FK animation from a source
GLB to a target GLB. It uses a user-supplied mapping rather than assuming a
particular bone naming convention. This is a starting point for editing; it
does not generate a performance or automatically fix ground and hand contacts.

**Status:** Python validation tests and an end-to-end transfer between two
synthetic rigs passed in Blender 5.2.2. Check real-character results on a copy.

## Requirements

- A trusted Blender installation with glTF import and export enabled.
- A source GLB with an armature and NLA tracks, and a target GLB with an
  armature. Rigs need compatible hierarchies, facing direction and rest poses.
- A JSON mapping with schema `octorig.retarget/1`, a `pairs` object from source
  bone names to target bone names, and the corresponding `root_source` and
  `root_target` pair. Target names must be unique.
- A **new** output directory; an existing directory is rejected.

From the repository root, use the path to your own Blender executable:

```console
blender --background --factory-startup --disable-autoexec --python-exit-code 1 --python octorig/retarget.py -- --source examples/wave.glb --target examples/static.glb --mapping examples/retarget-example.json --output jobs/retarget-demo
```

The synthetic example models are deliberately simple. The example is a
reproducible starting point, not proof that the transfer works on all models.
The script attempts to create `retarget.blend`, `retarget.glb` and
`retarget-report.json`. Review their motion from several angles before use.

`fps` must be between 24 and 240. `clips` optionally selects source NLA tracks;
if omitted, all source tracks are selected. `root_motion_scale` is optional:
when omitted, it uses the ratio between target and source bone heights. Use a
finite explicit value strictly between 0.1 and 10 if that ratio is unsuitable or
the source has zero vertical extent. Optional `attachments` can carry a rigid
mesh alongside a mapped bone, but release events are not supported and are
rejected instead of being silently treated as permanent attachment.

This script is GPL-3.0-or-later; see `LICENSES/GPL-3.0-or-later.txt`.
