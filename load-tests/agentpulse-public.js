import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 10 },
    { duration: '1m', target: 25 },
    { duration: '1m', target: 50 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<300', 'p(99)<750'],
    checks: ['rate>0.99'],
  },
};

const BASE = 'https://agentpulse.ca';

const headers = {
  'User-Agent': 'k6-agentpulse-public-check',
  'X-Test-Traffic': 'k6',
};

export default function () {
  const routes = [
    {
      path: '/',
      name: 'homepage',
      mustContain: 'AgentPulse',
    },
    {
      path: '/install.sh',
      name: 'install script',
      mustContain: 'agentpulse',
    },
    {
      path: '/health.json',
      name: 'health json',
      mustContain: '"ok": true',
    },
    {
      path: '/api/health/',
      name: 'api health static',
      mustContain: '"ok":true',
    },
  ];

  for (const route of routes) {
    const res = http.get(`${BASE}${route.path}`, { headers });

    check(res, {
      [`${route.name} status success`]: (r) => r.status >= 200 && r.status < 400,
      [`${route.name} under 300ms`]: (r) => r.timings.duration < 300,
      [`${route.name} content check`]: (r) => r.body.includes(route.mustContain),
    });
  }

  sleep(1);
}
