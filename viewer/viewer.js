import * as THREE from './vendor/three/build/three.module.min.js';
import { OrbitControls } from './vendor/three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from './vendor/three/examples/jsm/loaders/GLTFLoader.js';
import { resolveResourceURL } from './resource-policy.js';

const el = Object.fromEntries(['file', 'clips', 'play', 'fit', 'status', 'viewport'].map(id => [id, document.getElementById(id)]));
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, 1, .001, 10000);
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
} catch (error) {
  el.status.textContent = 'Could not start the 3D viewer. WebGL is required.';
  el.status.classList.add('error');
  throw error;
}
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
el.viewport.appendChild(renderer.domElement);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
scene.add(new THREE.HemisphereLight(0xffffff, 0x546070, 2));
const light = new THREE.DirectionalLight(0xffffff, 2.5);
light.position.set(4, 6, 5); scene.add(light);
camera.position.set(3, 2, 3); controls.update();

const manager = new THREE.LoadingManager();
manager.setURLModifier(resolveResourceURL);
const loader = new GLTFLoader(manager);
const clock = new THREE.Clock();
let model = null, mixer = null, action = null, animations = [], loadVersion = 0;

function status(message, error = false) { el.status.textContent = message; el.status.classList.toggle('error', error); }
function dispose(root) {
  root.traverse(obj => {
    obj.geometry?.dispose();
    const materials = Array.isArray(obj.material) ? obj.material : obj.material ? [obj.material] : [];
    for (const material of materials) {
      for (const value of Object.values(material)) if (value?.isTexture) value.dispose();
      material.dispose();
    }
  });
}
function clearModel() {
  if (mixer) { mixer.stopAllAction(); mixer.uncacheRoot(model); }
  if (model) { scene.remove(model); dispose(model); }
  model = mixer = action = null; animations = [];
  el.clips.replaceChildren(new Option('No animations loaded', ''));
  el.clips.disabled = el.play.disabled = el.fit.disabled = true;
  el.play.textContent = 'Pause';
}
function fitModel() {
  if (!model) return;
  const bounds = new THREE.Box3().setFromObject(model);
  if (bounds.isEmpty()) throw new Error('The model contains no visible geometry.');
  const size = bounds.getSize(new THREE.Vector3());
  const center = bounds.getCenter(new THREE.Vector3());
  const radius = Math.max(size.length() / 2, 0.001);
  const vertical = THREE.MathUtils.degToRad(camera.fov);
  const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * camera.aspect);
  const distance = radius / Math.sin(Math.min(vertical, horizontal) / 2) * 1.3;
  const direction = new THREE.Vector3(1, .65, 1).normalize();
  controls.target.copy(center); camera.position.copy(center).addScaledVector(direction, distance);
  camera.near = Math.max(radius / 1000, .00001); camera.far = distance + radius * 20;
  controls.minDistance = radius / 50; controls.maxDistance = distance * 20;
  camera.updateProjectionMatrix(); controls.update();
}
function chooseClip() {
  if (action) action.stop();
  action = mixer.clipAction(animations[Number(el.clips.value)]); action.reset().play();
  el.play.textContent = 'Pause';
}
el.clips.addEventListener('change', chooseClip);
el.play.addEventListener('click', () => {
  if (!action) return;
  action.paused = !action.paused; el.play.textContent = action.paused ? 'Play' : 'Pause';
});
el.fit.addEventListener('click', () => { try { fitModel(); } catch (error) { status(error.message, true); } });
el.file.addEventListener('change', async () => {
  const file = el.file.files[0], version = ++loadVersion;
  if (!file) return;
  clearModel(); status('Loading model…');
  try {
    if (!file.name.toLowerCase().endsWith('.glb')) throw new Error('Choose a .glb file.');
    const bytes = await file.arrayBuffer();
    const gltf = await new Promise((resolve, reject) => loader.parse(bytes, '', resolve, reject));
    if (version !== loadVersion) { dispose(gltf.scene); return; }
    model = gltf.scene; animations = gltf.animations; scene.add(model);
    fitModel(); el.fit.disabled = false;
    if (animations.length) {
      mixer = new THREE.AnimationMixer(model);
      el.clips.replaceChildren(...animations.map((clip, index) => new Option(clip.name || `Animation ${index + 1}`, String(index))));
      el.clips.disabled = el.play.disabled = false; chooseClip();
      status(`Loaded ${file.name} · ${animations.length} animation${animations.length === 1 ? '' : 's'}.`);
    } else status(`Loaded ${file.name} · No animations found.`);
  } catch (error) {
    if (version !== loadVersion) return;
    clearModel(); status(`Could not open model: ${error.message || String(error)}`, true);
  } finally { if (version === loadVersion) el.file.value = ''; }
});
new ResizeObserver(() => {
  const { clientWidth: width, clientHeight: height } = el.viewport;
  if (!width || !height) return;
  renderer.setSize(width, height, false); camera.aspect = width / height; camera.updateProjectionMatrix();
}).observe(el.viewport);
renderer.setAnimationLoop(() => { const delta = Math.min(clock.getDelta(), .1); mixer?.update(delta); controls.update(); renderer.render(scene, camera); });
