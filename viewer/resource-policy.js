// Restrict GLB resources to the model itself and embedded data.
export function resolveResourceURL(url) {
  if (url.startsWith('blob:') || url.startsWith('data:')) return url;
  throw new Error('External resources are not supported; use a self-contained GLB.');
}
