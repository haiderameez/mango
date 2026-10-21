import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: 4,
  iterations: 4,
  thresholds: { http_req_duration: ['p(95)<250'], http_req_failed: ['rate<0.01'] },
};

const baseUrl = __ENV.MANGO_URL || 'http://localhost:8000';

export function setup() {
  const response = http.post(`${baseUrl}/auth/login`, JSON.stringify({
    email: __ENV.MANGO_EMAIL || 'demo@mango.dev',
    password: __ENV.MANGO_PASSWORD || 'mango-demo',
  }), { headers: { 'Content-Type': 'application/json' } });
  if (response.status !== 200) throw new Error(`Login failed: ${response.status}`);
  return response.json('access_token');
}

export default function (token) {
  const incidents = (__ENV.MANGO_INCIDENT_IDS || '').split(',').filter(Boolean);
  if (incidents.length < 4) {
    throw new Error('Set MANGO_INCIDENT_IDS to four distinct open incident IDs.');
  }
  const incidentId = incidents[(__VU - 1) % incidents.length];
  const response = http.post(`${baseUrl}/incidents/${incidentId}/investigate`, null, {
    headers: { Authorization: `Bearer ${token}` },
  });
  check(response, { 'investigation queued': (result) => result.status === 202 });
}
