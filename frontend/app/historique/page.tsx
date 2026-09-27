'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import AppHeader from '../components/AppHeader';
import { useRequireAuth } from '../components/useRequireAuth';
import { listAnalyses, type AnalysisSummary } from '../lib/api';

function StatusBadge({ analysis }: { analysis: AnalysisSummary }) {
  const [label, style] =
    analysis.status === 'queued' ? ['En attente', 'bg-sky-50 text-sky-700']
    : analysis.status === 'running' ? ['En cours', 'bg-sky-50 text-sky-700']
    : analysis.status === 'failed' ? ['Échec', 'bg-rose-50 text-rose-700']
    : analysis.is_complete ? ['Complété', 'bg-emerald-50 text-emerald-700']
    : ['Incomplet', 'bg-amber-50 text-amber-700'];
  return <span className={`self-start rounded-full px-3 py-1 text-xs font-medium sm:self-auto ${style}`}>{label}</span>;
}

export default function HistoriquePage() {
  const user = useRequireAuth();
  const [analyses, setAnalyses] = useState<AnalysisSummary[] | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    listAnalyses()
      .then((loaded) => {
        if (!cancelled) setAnalyses(loaded);
      })
      .catch((loadError) => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : 'Impossible de charger vos analyses.');
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  if (!user) return <main className="min-h-screen bg-[#f8fafc]" />;

  return (
    <main className="min-h-screen bg-[#f8fafc] text-slate-900">
      <AppHeader user={user} />

      <section className="mx-auto max-w-4xl px-6 pb-20 pt-10 lg:px-10">
        <div className="flex flex-col justify-between gap-4 border-b border-slate-200 pb-7 sm:flex-row sm:items-end">
          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-[#277da1]">Historique</p>
            <h1 className="text-3xl font-semibold tracking-[-0.03em] text-slate-900">Mes analyses</h1>
          </div>
          <Link className="inline-flex h-10 items-center justify-center rounded-lg bg-[#173f5f] px-5 text-sm font-semibold text-white hover:bg-[#12344f]" href="/">Nouvelle analyse</Link>
        </div>

        {error && <div className="mt-6 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div>}

        {!analyses && !error && <p className="mt-8 text-sm text-slate-500">Chargement…</p>}

        {analyses && analyses.length === 0 && (
          <div className="mt-8 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
            <p className="text-base font-medium text-slate-700">Aucune analyse pour l’instant</p>
            <p className="mt-2 text-sm text-slate-500">Vos analyses apparaîtront ici automatiquement.</p>
            <Link className="mt-5 inline-block text-sm font-medium text-[#277da1] hover:underline" href="/">Lancer une première analyse</Link>
          </div>
        )}

        {analyses && analyses.length > 0 && (
          <ul className="mt-8 divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200 bg-white">
            {analyses.map((analysis) => (
              <li key={analysis.id}>
                <Link className="flex flex-col gap-2 px-5 py-4 transition hover:bg-slate-50 sm:flex-row sm:items-center sm:justify-between" href={`/analyse?id=${encodeURIComponent(analysis.id)}`}>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-800">{analysis.filename}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      {new Date(analysis.created_at).toLocaleString('fr-FR')}
                      {analysis.company_name ? ` · ${analysis.company_name}` : ''}
                    </p>
                  </div>
                  <StatusBadge analysis={analysis} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
