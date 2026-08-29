/**
 * Frontend client for North Star HTTP API.
 * FE/BE separation: do not import Python lib; call dashboard plugin routes.
 *
 * Base path: /api/plugins/vaelis-north-star
 * Contract: docs/vaelis/north_star/API.md
 */
const BASE = '/api/plugins/vaelis-north-star';
async function request(path, init) {
    const res = await fetch(`${BASE}${path}`, {
        ...init,
        headers: {
            'content-type': 'application/json',
            ...(init?.headers || {})
        }
    });
    if (!res.ok) {
        throw new Error(`vaelis-api ${path} → ${res.status}`);
    }
    return res.json();
}
export function vaelisHealth() {
    return request('/health');
}
export function vaelisBoard() {
    return request('/board');
}
export function vaelisTask(body) {
    return request('/task', {
        method: 'POST',
        body: JSON.stringify(body)
    });
}
export function vaelisPreviewList(limit = 50) {
    return request(`/preview?limit=${limit}`);
}
export function vaelisPreview(body) {
    return request('/preview', {
        method: 'POST',
        body: JSON.stringify(body)
    });
}
export function vaelisOps(body) {
    return request('/ops', {
        method: 'POST',
        body: JSON.stringify(body)
    });
}
export function vaelisMorningReport() {
    return request('/morning-report');
}
