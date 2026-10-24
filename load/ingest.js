import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: 10,
  duration: '30s',
  thresholds: {
    http_req_duration: ['p(95)<50'],
    http_req_failed: ['rate<0.01'],
  },
};

const baseUrl = __ENV.MANGO_URL || 'http://localhost:8000';
const ingestKey = __ENV.MANGO_INGEST_KEY;

export default function () {
  if (!ingestKey) {
    throw new Error('Set MANGO_INGEST_KEY to a service ingest key.');
  }

  const timestamp = new Date().toISOString();
  const body = Array.from({ length: 500 }, (_, index) => JSON.stringify({
    timestamp,
    service: 'load-test',
    level: 'INFO',
    message: `synthetic load record ${__VU}-${__ITER}-${index}`,
    request_id: `${__VU}-${__ITER}-${index}`,
    queue_depth: index,
  })).join('\n');

  const response = http.post(`${baseUrl}/ingest/logs`, body, {
    headers: { 'X-Ingest-Key': ingestKey, 'Content-Type': 'application/x-ndjson' },
  });
  check(response, { 'ingest accepted': (result) => result.status === 202 });
}
