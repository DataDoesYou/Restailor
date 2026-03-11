/**
 * Catch-all API proxy route
 * Forwards all /api/* requests to the backend and properly handles cookies
 * This is necessary because Next.js rewrites don't forward Set-Cookie headers
 */

import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.INTERNAL_API_BASE_URL || 'http://api:8000';

export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path, 'GET');
}

export async function POST(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path, 'POST');
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path, 'PUT');
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path, 'PATCH');
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path, 'DELETE');
}

async function proxyRequest(
  request: NextRequest,
  pathSegments: string[],
  method: string
) {
  // Reconstruct the path
  const path = pathSegments.join('/');
  
  // Get query parameters
  const searchParams = request.nextUrl.searchParams;
  const queryString = searchParams.toString();
  const fullPath = queryString ? `/${path}?${queryString}` : `/${path}`;
  
  // Build backend URL
  const backendUrl = `${BACKEND_URL}${fullPath}`;
  
  // Forward cookies from the incoming request
  const cookieHeader = request.headers.get('cookie');
  
  // Prepare headers
  const headers: HeadersInit = {
    'Content-Type': request.headers.get('content-type') || 'application/json',
  };
  
  if (cookieHeader) {
    headers['Cookie'] = cookieHeader;
  }
  
  // Forward other relevant headers
  const relevantHeaders = [
    'authorization',
    'x-requested-with',
    'x-admin-key',
    'user-agent',
    'referer',
  ];
  
  for (const headerName of relevantHeaders) {
    const value = request.headers.get(headerName);
    if (value) {
      headers[headerName] = value;
    }
  }
  
  // Prepare request body for non-GET requests
  let body: BodyInit | undefined;
  if (method !== 'GET' && method !== 'HEAD') {
    const contentType = request.headers.get('content-type') || '';
    
    if (contentType.includes('application/json')) {
      try {
        const jsonBody = await request.json();
        body = JSON.stringify(jsonBody);
      } catch {
        body = undefined;
      }
    } else if (contentType.includes('application/x-www-form-urlencoded')) {
      body = await request.text();
      headers['Content-Type'] = 'application/x-www-form-urlencoded';
    } else if (contentType.includes('multipart/form-data')) {
      // For FormData, don't set Content-Type (fetch will set it with boundary)
      delete headers['Content-Type'];
      body = await request.blob();
    } else {
      body = await request.text();
    }
  }
  
  // Make the backend request
  const backendResponse = await fetch(backendUrl, {
    method,
    headers,
    body,
    // Don't follow redirects automatically - let the client handle them
    redirect: 'manual',
  });
  
  // Get response body
  const responseBody = await backendResponse.arrayBuffer();
  
  // Create Next response with same status
  const response = new NextResponse(responseBody, {
    status: backendResponse.status,
    statusText: backendResponse.statusText,
  });
  
  // Forward response headers, especially Set-Cookie
  backendResponse.headers.forEach((value, key) => {
    // Skip some headers that shouldn't be forwarded
    const skipHeaders = ['connection', 'keep-alive', 'transfer-encoding', 'upgrade'];
    if (!skipHeaders.includes(key.toLowerCase())) {
      response.headers.set(key, value);
    }
  });
  
  return response;
}
