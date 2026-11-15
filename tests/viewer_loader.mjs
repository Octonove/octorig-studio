import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

export function resolve(specifier, context, nextResolve) {
  if (specifier === 'three') {
    const root = path.dirname(fileURLToPath(import.meta.url));
    return { url: pathToFileURL(path.join(root, '../viewer/vendor/three/build/three.module.min.js')).href, shortCircuit: true };
  }
  return nextResolve(specifier, context);
}
