import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// Routes that require authentication
const protectedRoutes = [
  '/resume',
  '/history',
  '/analytics',
  '/billing',
  '/security',
  '/settings',
  '/admin',
  '/admin/analytics',
  '/db-test',
];

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  
  // Check if the route is protected
  const isProtectedRoute = protectedRoutes.some(route => pathname.startsWith(route));

  // Skip middleware for non-auth-related routes
  if (!isProtectedRoute) {
    return NextResponse.next();
  }
  
  // Get session cookie
  const sessionCookie = request.cookies.get('rt_session');
  const hasSessionCookie = !!sessionCookie?.value;
  
  // For protected routes, validate session by checking with API
  if (isProtectedRoute) {
    if (!hasSessionCookie) {
      // No cookie at all - immediate redirect
      const url = request.nextUrl.clone();
      url.pathname = '/';
      return NextResponse.redirect(url);
    }
    
    // Validate cookie with API
    try {
      const apiBase = process.env.INTERNAL_API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || '';
      const cookieHeader = request.headers.get('cookie') || '';
      
      const res = await fetch(`${apiBase}/users/me`, {
        headers: {
          Cookie: cookieHeader,
        },
        cache: 'no-store',
      });
      
      if (!res.ok) {
        // Invalid/expired session - redirect to home
        const url = request.nextUrl.clone();
        url.pathname = '/';
        const response = NextResponse.redirect(url);
        response.headers.set('X-Middleware-Reason', `API returned ${res.status}`);
        return response;
      }
    } catch (error) {
      // API error - redirect to be safe
      const url = request.nextUrl.clone();
      url.pathname = '/';
      const response = NextResponse.redirect(url);
      response.headers.set('X-Middleware-Reason', `API error: ${error}`);
      return response;
    }
  }
  
  return NextResponse.next();
}

// Configure which routes the middleware runs on
export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public assets
     */
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
};

export default proxy;
