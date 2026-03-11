'use client';

import { useEffect } from 'react';
import { logger } from '@/lib/logger';

/**
 * TokenRefreshInitializer
 * 
 * Client-side component that initializes automatic token refresh.
 * This keeps users logged in indefinitely by proactively refreshing
 * access tokens before they expire.
 */
export default function TokenRefreshInitializer() {
  useEffect(() => {
    logger.debug('[TokenRefreshInitializer] Component mounted, loading tokenRefresh module...');
    
    // Dynamically import to ensure client-side only execution
    import('@/lib/tokenRefresh').then(({ initTokenRefresh }) => {
      logger.debug('[TokenRefreshInitializer] Module loaded, calling initTokenRefresh...');
      initTokenRefresh();
    }).catch(err => {
      logger.error('[TokenRefreshInitializer] Failed to initialize:', err);
    });
  }, []);

  // This component renders nothing
  return null;
}
