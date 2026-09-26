'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { analyzeFile } from '../lib/api';

type StoredFile = {
  name: string;
  size: number;
  type?: string;
  content: string;
  analysisResult?: AnalysisResult;
};

type AnalysisResult = {
  analysis_id: string;
  filename: string;
  status: string;
  summary: {
    risk_level: string;
    score: number;
  };
  findings: Array<unknown>;
  representation?: string;
  representation_format?: 'xml' | 'markdown';
  metadata: {
    content_length?: number;
    content_type?: string;
    archive?: boolean;
    file_count?: number;
    files?: string[];
    uncompressed_size?: number;
  };
};

function FileCodeIcon() {
  return <svg aria-hidden="true" className="h-6 w-6" fill="none" viewBox="0 0 24 24"><path d="m8.5 8-4 4 4 4M15.5 8l4 4-4 4M13.5 5l-3 14" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" /></svg>;
}

function ArrowLeftIcon() {
  return <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24"><path d="M19 12H5m6 6-6-6 6-6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" /></svg>;
}

export default function AnalysePage() {
  const [file, setFile] = useState<StoredFile | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [isAnalysing, setIsAnalysing] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const storedFile = sessionStorage.getItem('ai-risk-check-file');
    if (storedFile) {
      let cancelled = false;
      try {
        const parsedFile = JSON.parse(storedFile) as StoredFile;
        const timer = window.setTimeout(() => {
          if (cancelled) return;

          setFile(parsedFile);

          if (parsedFile.analysisResult) {
            setResult(parsedFile.analysisResult);
            return;
          }

          const reconstructedFile = new File(
            [parsedFile.content],
            parsedFile.name,
            { type: parsedFile.type || 'text/plain' },
          );

          setIsAnalysing(true);
          analyzeFile(reconstructedFile, 'markdown')
            .then((analysisResult: AnalysisResult) => {
              if (!cancelled) setResult(analysisResult);
            })
            .catch((analysisError: Error) => {
              if (!cancelled) setError(analysisError.message);
            })
            .finally(() => {
              if (!cancelled) setIsAnalysing(false);
            });
        }, 0);

        return () => {
          cancelled = true;
          window.clearTimeout(timer);
        };
      } catch {
        sessionStorage.removeItem('ai-risk-check-file');
        window.setTimeout(() => setError('Impossible de préparer le fichier.'), 0);
      }
    }
  }, []);

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
            <h1 className="text-3xl font-semibold tracking-[-0.03em] text-slate-900">{file?.name ?? 'Contenu du fichier'}</h1>
          </div>
          {isAnalysing && <span className="rounded-full bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700">Analyse en cours…</span>}
          {result && <span className="rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700">Analyse terminée</span>}
          {error && <span className="rounded-full bg-rose-50 px-3 py-1.5 text-xs font-medium text-rose-700">Échec de l’analyse</span>}
        </div>

        <div className="mt-6 flex flex-col items-start justify-between gap-4 rounded-xl border border-slate-200 bg-white px-5 py-4 text-sm text-slate-500 sm:flex-row sm:items-center">
          <span>{error || (isAnalysing ? 'Le fichier est en cours d’analyse.' : result ? 'L’analyse est terminée.' : file ? 'Le contenu est prêt pour l’analyse des risques AI Act.' : 'Votre sélection a peut-être expiré.')}</span>
          {!file && <Link className="font-medium text-[#277da1] hover:underline" href="/">Sélectionner un fichier</Link>}
        </div>

        {result?.representation && (
          <section className="mt-6 overflow-hidden rounded-xl border border-slate-200 bg-white">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <h2 className="text-sm font-semibold text-slate-800">Sortie Repomix — Markdown</h2>
              <span className="text-xs text-slate-400">Générée par le backend</span>
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
