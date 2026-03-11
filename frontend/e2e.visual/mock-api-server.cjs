// Simple mock API to satisfy SSR fetches during Playwright
const http = require('http');
const url = require('url');

// In-memory storage for stage flags
const stageFlags = new Map();

const server = http.createServer((req, res) => {
  const parsedUrl = url.parse(req.url, true);
  const pathname = parsedUrl.pathname;
  
  // Allow CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-Job-Token');
  
  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end();
    return;
  }
  
  if (pathname === '/users/me') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ email: 'test@example.com', id: 1 }));
    return;
  }
  
  if (pathname === '/users/me/balance') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ balance_usd: '10.00' }));
    return;
  }
  
  // Applications list endpoint
  if (pathname === '/applications/list') {
    const mockItems = [
      {
        appliedKey: 'test-key-1',
        jdSnippet: 'Senior Software Engineer at Test Corp',
        jdHash: 'hash-1',
        baseHash: 'base-1',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        isApplied: false,
        snapshotId: 'snap-1',
        jobId: 'job-1',
        jobToken: 'token-1',
        isArchived: false,
        isStaged: true,
        interviewing: stageFlags.get('test-key-1-interviewing') || false,
        offer: stageFlags.get('test-key-1-offer') || false,
        hired: stageFlags.get('test-key-1-hired') || false,
        jobInputHashes: ['hash-1'],
      },
      {
        appliedKey: 'test-key-2',
        jdSnippet: 'Frontend Developer at Another Company',
        jdHash: 'hash-2',
        baseHash: 'base-2',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        isApplied: false,
        snapshotId: 'snap-2',
        jobId: 'job-2',
        jobToken: 'token-2',
        isArchived: false,
        isStaged: true,
        interviewing: stageFlags.get('test-key-2-interviewing') || false,
        offer: stageFlags.get('test-key-2-offer') || false,
        hired: stageFlags.get('test-key-2-hired') || false,
        jobInputHashes: ['hash-2'],
      },
    ];
    
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      page: 1,
      pageSize: 25,
      total: mockItems.length,
      items: mockItems,
    }));
    return;
  }
  
  // Stage flags update - jobs endpoint
  if (pathname.match(/^\/jobs\/[^\/]+\/stage-flags$/)) {
    if (req.method === 'PATCH') {
      let body = '';
      req.on('data', chunk => { body += chunk; });
      req.on('end', () => {
        try {
          const data = JSON.parse(body);
          const jobId = pathname.split('/')[2];
          
          // Store flags in memory (use appliedKey for simplicity)
          if (typeof data.interviewing === 'boolean') {
            stageFlags.set(`${jobId}-interviewing`, data.interviewing);
          }
          if (typeof data.offer === 'boolean') {
            stageFlags.set(`${jobId}-offer`, data.offer);
          }
          if (typeof data.hired === 'boolean') {
            stageFlags.set(`${jobId}-hired`, data.hired);
          }
          
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ success: true }));
        } catch (e) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Invalid JSON' }));
        }
      });
      return;
    }
  }
  
  // Stage flags update - applications endpoint
  if (pathname === '/applications/stage-flags') {
    if (req.method === 'PATCH') {
      let body = '';
      req.on('data', chunk => { body += chunk; });
      req.on('end', () => {
        try {
          const data = JSON.parse(body);
          const appliedKey = data.appliedKey;
          
          if (typeof data.interviewing === 'boolean') {
            stageFlags.set(`${appliedKey}-interviewing`, data.interviewing);
          }
          if (typeof data.offer === 'boolean') {
            stageFlags.set(`${appliedKey}-offer`, data.offer);
          }
          if (typeof data.hired === 'boolean') {
            stageFlags.set(`${appliedKey}-hired`, data.hired);
          }
          
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ success: true }));
        } catch (e) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Invalid JSON' }));
        }
      });
      return;
    }
  }
  
  // Apply endpoint
  if (pathname === '/applications/jd/apply') {
    if (req.method === 'POST') {
      let body = '';
      req.on('data', chunk => { body += chunk; });
      req.on('end', () => {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ success: true }));
      });
      return;
    }
  }
  
  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ error: 'not found' }));
});

const port = 3101;
server.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`Mock API on http://localhost:${port}`);
});
