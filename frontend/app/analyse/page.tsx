'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

type ComplianceResult = {
  is_complete: boolean;
  results_text: string;
  questions_answered: number;
  needs_human_input: Array<{ question: string; reasoning: string }>;
  filename: string;
  file_count: number;
};

type StoredResult = {
  name: string;
  size: number;
  result: ComplianceResult;
};

function FileCodeIcon() {
  return <svg aria-hidden="true" className="h-6 w-6" fill="none" viewBox="0 0 24 24"><path d="m8.5 8-4 4 4 4M15.5 8l4 4-4 4M13.5 5l-3 14" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" /></svg>;
}

function ArrowLeftIcon() {
  return <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24"><path d="M19 12H5m6 6-6-6 6-6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" /></svg>;
}

export default function AnalysePage() {
  const [stored, setStored] = useState<StoredResult | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const raw = sessionStorage.getItem('ai-risk-check-result');
    const timer = window.setTimeout(() => {
      if (!raw) {
        setError('Aucun résultat trouvé. Retournez au dépôt pour lancer une analyse.');
        return;
      }
      try {
        setStored(JSON.parse(raw) as StoredResult);
      } catch {
        setError('Impossible de lire le résultat de l’analyse.');
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const result = stored?.result;

  return (
    <main className="min-h-screen bg-[#f8fafc] text-slate-900">
      <header className="border-b border-slate-200/80 bg-white">
        <div className="mx-auto flex h-[72px] w-full max-w-6xl items-center justify-between px-6 lg:px-10">
          <Link className="flex items-center gap-3" href="/">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#173f5f] text-white"><FileCodeIcon /></div>
            <span className="text-[17px] font-semibold tracking-[-0.02em] text-slate-800">AI Risk Check</span>
          </Link>
          <span className="text-sm text-slate-500">Analyse de conformité</span>
        </div>
      </header>

      <section className="mx-auto max-w-4xl px-6 pb-20 pt-10 lg:px-10">
        <Link className="inline-flex items-center gap-2 text-sm font-medium text-[#277da1] hover:underline" href="/"><ArrowLeftIcon />Retour au dépôt</Link>

        <div className="mt-9 flex flex-col justify-between gap-5 border-b border-slate-200 pb-7 sm:flex-row sm:items-end">
          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-[#277da1]">Fichier soumis</p>
            <h1 className="text-3xl font-semibold tracking-[-0.03em] text-slate-900">{stored?.name ?? 'Résultat de l’analyse'}</h1>
          </div>
          {result && (
            <span className={`rounded-full px-3 py-1.5 text-xs font-medium ${result.is_complete ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
              {result.is_complete ? 'Formulaire complété' : 'Formulaire incomplet'}
            </span>
          )}
          {error && <span className="rounded-full bg-rose-50 px-3 py-1.5 text-xs font-medium text-rose-700">Erreur</span>}
        </div>

        {error && (
          <div className="mt-6 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
            {error} <Link className="font-medium underline" href="/">Sélectionner un fichier</Link>
          </div>
        )}

        {result && (
          <>
            <div className="mt-8 rounded-xl border border-slate-200 bg-white p-6 shadow-[0_12px_40px_rgba(15,23,42,0.05)]">
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-[#277da1]">Recommandation de l’EU AI Act Compliance Checker</p>
              <p className="mt-2 text-sm text-slate-500">{result.questions_answered} question(s) répondue(s) automatiquement</p>
              <pre className="mt-4 whitespace-pre-wrap font-sans text-sm leading-6 text-slate-800">{result.results_text}</pre>
            </div>

            {result.needs_human_input.length > 0 && (
              <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-6">
                <p className="text-sm font-semibold text-amber-800">
                  {result.needs_human_input.length} question(s) nécessitent une réponse humaine
                </p>
                <p className="mt-1 text-xs text-amber-700">
                  L’IA n’a pas trouvé assez d’information dans le code pour répondre avec confiance.
                </p>
                <ul className="mt-4 space-y-3 text-sm">
                  {result.needs_human_input.map((item) => (
                    <li className="rounded-lg bg-white/60 p-3" key={item.question}>
                      <p className="font-medium text-amber-900">{item.question}</p>
                      <p className="mt-1 text-amber-700">{item.reasoning}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </section>
    </main>
  );
}
