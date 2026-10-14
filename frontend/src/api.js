const API = '/api/datasets';

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

export const api = {
  list: () => request(API),
  summary: () => request(`${API}/summary`),
  register: (snapshot) => request(API, { method: 'POST', body: JSON.stringify(snapshot) }),
  update: (id, changes) => request(`${API}/${id}`, { method: 'PUT', body: JSON.stringify(changes) }),
  archive: (id) => request(`${API}/${id}`, { method: 'DELETE' }),
  purge: (id) => request(`${API}/${id}?purge=true`, { method: 'DELETE' }),
};
