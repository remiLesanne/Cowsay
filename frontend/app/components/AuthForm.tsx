'use client';

import Link from 'next/link';
import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import { login, register } from '../lib/api';
import { Logo } from './AppHeader';

const COPY = {
  login: {
    title: 'Connexion',
    subtitle: 'Connectez-vous pour analyser un projet et retrouver vos analyses.',
    submit: 'Se connecter',
    pending: 'Connexion…',
    switchText: 'Pas encore de compte ?',
    switchLink: 'Créer un compte',
    switchHref: '/register',
  },
  register: {
    title: 'Créer un compte',
    subtitle: 'Un compte permet de lancer des analyses et de les retrouver plus tard.',
    submit: 'Créer mon compte',
    pending: 'Création…',
    switchText: 'Déjà un compte ?',
    switchLink: 'Se connecter',
    switchHref: '/login',
  },
};

export default function AuthForm({ mode }: { mode: 'login' | 'register' }) {
  const router = useRouter();
  const copy = COPY[mode];
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isSubmitting) return;
    setIsSubmitting(true);
    setError('');
    try {
      await (mode === 'login' ? login(email, password) : register(email, password));
      router.replace('/');
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Erreur inconnue.');
      setIsSubmitting(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#f8fafc] text-slate-900">
      <header className="border-b border-slate-200/80 bg-white">
        <div className="mx-auto flex h-[72px] w-full max-w-6xl items-center px-6 lg:px-10"><Logo /></div>
      </header>

      <section className="mx-auto max-w-md px-6 pb-20 pt-16">
        <h1 className="text-3xl font-semibold tracking-[-0.03em] text-slate-900">{copy.title}</h1>
        <p className="mt-3 text-sm leading-6 text-slate-500">{copy.subtitle}</p>

        <form className="mt-8 space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-[0_12px_40px_rgba(15,23,42,0.05)]" onSubmit={handleSubmit}>
          <label className="block text-sm font-medium text-slate-700">
            Email
            <input autoComplete="email" className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Mot de passe
            <input autoComplete={mode === 'login' ? 'current-password' : 'new-password'} className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm" minLength={mode === 'register' ? 8 : undefined} onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />
            {mode === 'register' && <span className="mt-1 block text-xs font-normal text-slate-400">8 caractères minimum</span>}
          </label>

          {error && <p className="text-sm text-rose-600">{error}</p>}

          <button className="inline-flex h-11 w-full items-center justify-center rounded-lg bg-[#173f5f] text-sm font-semibold text-white transition hover:bg-[#12344f] disabled:cursor-not-allowed disabled:bg-slate-300" disabled={isSubmitting} type="submit">
            {isSubmitting ? copy.pending : copy.submit}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-slate-500">
          {copy.switchText}{' '}
          <Link className="font-medium text-[#277da1] hover:underline" href={copy.switchHref}>{copy.switchLink}</Link>
        </p>
      </section>
    </main>
  );
}
