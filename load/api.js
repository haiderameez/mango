import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: 20,
  duration: '30s',
  thresholds: {
    http_req_duration: ['p(95)<250'],
    http_req_failed: ['rate<0.01'],
  },
};

const baseUrl = __ENV.MANGO_URL || 'http://localhost:8000';

export function setup() {
  const response = http.post(`${baseUrl}/auth/login`, JSON.stringify({
    email: __ENV.MANGO_EMAIL || 'demo@mango.dev',
    password: __ENV.MANGO_PASSWORD || 'mango-demo',
  }), { headers: { 'Content-Type': 'application/json' } });
  check(response, { 'login succeeded': (result) => result.status === 200 });
  if (response.status !== 200) throw new Error(`Login failed: ${response.status}`);
  return response.json('access_token');
}

export default function (token) {
  const response = http.get(`${baseUrl}/incidents?limit=50&offset=0`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  check(response, { 'incident register loaded': (result) => result.status === 200 });
}
