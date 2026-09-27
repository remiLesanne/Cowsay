'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getMe, getToken, type User } from '../lib/api';

// Client-side guard for pages that need an account (spec 005 FR-015). The backend
// enforces the same rule on its own; this only avoids showing a page that can't work.
export function useRequireAuth(): User | null {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace('/login');
      return;
    }
    let cancelled = false;
    getMe()
      .then((me) => {
        if (!cancelled) setUser(me);
      })
      .catch(() => {
        // authFetch already redirected to /login on 401.
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  return user;
}
