'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { logout, type User } from '../lib/api';

function FileCodeIcon() {
  return <svg aria-hidden="true" className="h-6 w-6" fill="none" viewBox="0 0 24 24"><path d="m8.5 8-4 4 4 4M15.5 8l4 4-4 4M13.5 5l-3 14" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" /></svg>;
}

export function Logo() {
  return (
    <Link className="flex items-center gap-3" href="/">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#173f5f] text-white"><FileCodeIcon /></div>
      <span className="text-[17px] font-semibold tracking-[-0.02em] text-slate-800">AI Risk Check</span>
    </Link>
  );
}

export default function AppHeader({ user }: { user: User | null }) {
  const router = useRouter();

  const handleLogout = () => {
    logout();
    router.replace('/login');
  };

  return (
    <header className="border-b border-slate-200/80 bg-white">
      <div className="mx-auto flex h-[72px] w-full max-w-6xl items-center justify-between gap-4 px-6 lg:px-10">
        <Logo />
        <nav className="flex items-center gap-4 text-sm sm:gap-6">
          <Link className="font-medium text-[#277da1] hover:underline" href="/historique">Mes analyses</Link>
          {user && <span className="hidden max-w-[220px] truncate text-slate-500 sm:inline">{user.email}</span>}
          <button className="font-medium text-slate-600 hover:text-slate-900" onClick={handleLogout} type="button">Se déconnecter</button>
        </nav>
      </div>
    </header>
  );
}
