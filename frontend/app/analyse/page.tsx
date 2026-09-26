'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { getAnalysis } from '../lib/api';

type AnalysisResult = {
  analysis_id: string;
  filename: string;
  status: string;
  representation?: string;
  representation_format?: 'xml' | 'markdown';
  summary: {
    risk_level: string;
    score: number;
  };
  findings: Array<unknown>;
  metadata: {
    archive?: boolean;
    file_count?: number;
    file_size?: number;
    files?: string[];
    content_type?: string;
  };
};

function FileCodeIcon() {
  return <svg aria-hidden="true" className="h-6 w-6" fill="none" viewBox="0 0 24 24"><path d="m8.5 8-4 4 4 4M15.5 8l4 4-4 4M13.5 5l-3 14" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" /></svg>;
}

function ArrowLeftIcon() {
  return <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24"><path d="M19 12H5m6 6-6-6 6-6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" /></svg>;
}

export default function AnalysePage() {
  const searchParams = useSearchParams();
  const analysisId = searchParams.get('id');
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      if (!analysisId) {
        setError('Identifiant d’analyse manquant.');
        setIsLoading(false);
        return;
      }

      getAnalysis(analysisId)
        .then((analysisResult: AnalysisResult) => {
          if (!cancelled) setResult(analysisResult);
        })
        .catch((analysisError: Error) => {
          if (!cancelled) setError(analysisError.message);
        })
        .finally(() => {
          if (!cancelled) setIsLoading(false);
        });
    }, 0);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [analysisId]);

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

      <section className="mx-auto max-w-6xl px-6 pb-20 pt-10 lg:px-10">
        <Link className="inline-flex items-center gap-2 text-sm font-medium text-[#277da1] hover:underline" href="/"><ArrowLeftIcon />Retour au dépôt</Link>
        <div className="mt-9 flex flex-col justify-between gap-5 border-b border-slate-200 pb-7 sm:flex-row sm:items-end">
          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-[#277da1]">Fichier soumis</p>
            <h1 className="text-3xl font-semibold tracking-[-0.03em] text-slate-900">{result?.filename ?? 'Analyse du projet'}</h1>
          </div>
          {isLoading && <span className="rounded-full bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700">Récupération de l’analyse…</span>}
          {result && <span className="rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700">Analyse terminée</span>}
          {error && <span className="rounded-full bg-rose-50 px-3 py-1.5 text-xs font-medium text-rose-700">Échec de l’analyse</span>}
        </div>

        <div className="mt-6 flex flex-col items-start justify-between gap-4 rounded-xl border border-slate-200 bg-white px-5 py-4 text-sm text-slate-500 sm:flex-row sm:items-center">
          <span>{error || (isLoading ? 'Récupération de la représentation Repomix.' : result ? 'La représentation Markdown est prête.' : 'Aucune analyse trouvée.')}</span>
          {!result && !isLoading && <Link className="font-medium text-[#277da1] hover:underline" href="/">Sélectionner un fichier</Link>}
        </div>

        {result?.representation && (
          <section className="mt-6 overflow-hidden rounded-xl border border-slate-200 bg-white">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <h2 className="text-sm font-semibold text-slate-800">Synthèse du projet — Markdown</h2>
              <span className="text-xs text-slate-400">Générée à {new Date().toLocaleTimeString()}</span>
            </div>
            <pre className="max-h-[700px] overflow-auto whitespace-pre-wrap p-6 text-left font-mono text-[13px] leading-6 text-slate-700">
              {result.representation}
            </pre>
          </section>
        )}
      </section>
    </main>
  );
}
