function normalizeBase(base) {
  if (!base) return '';
  return String(base).replace(/\/+$/, '');
}

export function getApiBase(baseOverride) {
  return normalizeBase(baseOverride ?? import.meta.env.VITE_API_URL);
}

export function apiUrl(path, baseOverride) {
  const base = getApiBase(baseOverride);
  const normalizedPath = String(path || '').startsWith('/') ? String(path || '') : `/${path || ''}`;
  return base ? `${base}${normalizedPath}` : normalizedPath;
}
