import http from 'k6/http';
import { check } from 'k6';
import { Trend } from 'k6/metrics';

const registerDuration = new Trend('incident_register_duration', true);

export const options = {
  vus: 20,
  duration: '30s',
  thresholds: {
    incident_register_duration: ['p(95)<250'],
    http_req_failed: ['rate<0.01'],
  },
};

const baseUrl = __ENV.MANGO_URL || 'http://localhost:8000';

export function setup() {
  if (__ENV.MANGO_TOKEN) return __ENV.MANGO_TOKEN;

  const response = http.post(`${baseUrl}/auth/login`, JSON.stringify({
    email: __ENV.MANGO_EMAIL || 'demo@mango.dev',
    password: __ENV.MANGO_PASSWORD || 'mango-demo',
  }), { headers: { 'Content-Type': 'application/json' } });
  check(response, { 'login succeeded': (result) => result.status === 200 });
  if (response.status !== 200) throw new Error(`Login failed: ${response.status}`);
  return response.json('access_token');
}

export default function (token) {
  const response = http.get(
    `${baseUrl}/incidents?status=OPEN&severity=HIGH&limit=50&offset=0`,
    {
    headers: { Authorization: `Bearer ${token}` },
    },
  );
  registerDuration.add(response.timings.duration);
  check(response, { 'incident register loaded': (result) => result.status === 200 });
}
