import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { GLTFLoader } from '../viewer/vendor/three/examples/jsm/loaders/GLTFLoader.js';
import { resolveResourceURL } from '../viewer/resource-policy.js';

for (const url of ['blob:local', 'data:image/png;base64,AA==']) assert.equal(resolveResourceURL(url), url);
for (const url of ['https://example.com/model.bin', 'http://localhost/model.bin', '../model.bin', '//example.com/file']) {
  assert.throws(() => resolveResourceURL(url), /External resources/);
}
for (const [name, clips] of [['wave.glb', 1], ['static.glb', 0]]) {
  const buffer = await readFile(new URL(`../examples/${name}`, import.meta.url));
  const bytes = buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
  const gltf = await new Promise((resolve, reject) => new GLTFLoader().parse(bytes, '', resolve, reject));
  assert.equal(gltf.animations.length, clips);
  assert.ok(gltf.scene.children.length);
}
console.log('Viewer model parsing and resource policy checks passed.');
