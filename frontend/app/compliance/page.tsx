'use client';

import Link from 'next/link';
import { useState } from 'react';
import { runComplianceCheck } from '../lib/api';

type ComplianceResult = {
  is_complete: boolean;
  results_text: string;
  questions_answered: number;
  needs_human_input: Array<{ question: string; reasoning: string }>;
  filename: string;
  file_count: number;
};

export default function CompliancePage() {
  const [file, setFile] = useState<File | null>(null);
  const [companyName, setCompanyName] = useState('');
  const [companyContext, setCompanyContext] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<ComplianceResult | null>(null);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    if (!file || isRunning) return;
    setIsRunning(true);
    setError('');
    setResult(null);
    try {
      const response = await runComplianceCheck(file, companyName || undefined, companyContext || undefined);
      setResult(response);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Erreur inconnue.');
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#f8fafc] p-8 text-slate-900">
      <div className="mx-auto max-w-3xl">
        <Link className="text-sm font-medium text-[#277da1] hover:underline" href="/">← Retour</Link>
        <h1 className="mt-4 text-2xl font-semibold">Test — Compliance Check (EU AI Act)</h1>
        <p className="mt-2 text-sm text-slate-500">
          Page de test locale pour <code>POST /api/v1/compliance-check</code>. Peut prendre 30–90s
          (Playwright pilote le vrai formulaire officiel + appels LLM).
        </p>

        <div className="mt-6 space-y-4 rounded-xl border border-slate-200 bg-white p-6">
          <div>
            <label className="block text-sm font-medium text-slate-700">Fichier ou zip du projet</label>
            <input
              accept=".py,.js,.ts,.tsx,.jsx,.java,.go,.rs,.php,.rb,.c,.cpp,.cs,.xml,.md,.zip"
              className="mt-1 block w-full text-sm"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              type="file"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700">Nom de l&apos;entreprise (optionnel)</label>
            <input
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              onChange={(event) => setCompanyName(event.target.value)}
              type="text"
              value={companyName}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700">Contexte additionnel (optionnel)</label>
            <textarea
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              onChange={(event) => setCompanyContext(event.target.value)}
              rows={3}
              value={companyContext}
            />
          </div>
          <button
            className="rounded-lg bg-[#173f5f] px-5 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
            disabled={!file || isRunning}
            onClick={handleSubmit}
            type="button"
          >
            {isRunning ? 'Analyse en cours…' : 'Lancer le compliance-check'}
          </button>
        </div>

        {error && (
          <div className="mt-6 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div>
        )}

        {result && (
          <div className="mt-6 space-y-4">
            <div className="rounded-xl border border-slate-200 bg-white p-5">
              <p className="text-sm text-slate-500">
                {result.is_complete ? '✅ Formulaire complété' : '⚠️ Formulaire incomplet'} ·{' '}
                {result.questions_answered} question(s) répondue(s)
              </p>
              <pre className="mt-3 whitespace-pre-wrap text-sm text-slate-800">{result.results_text}</pre>
            </div>

            {result.needs_human_input.length > 0 && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
                <p className="text-sm font-semibold text-amber-800">Questions nécessitant une réponse humaine</p>
                <ul className="mt-2 space-y-2 text-sm text-amber-900">
                  {result.needs_human_input.map((item) => (
                    <li key={item.question}>
                      <span className="font-medium">{item.question}</span>
                      <br />
                      <span className="text-amber-700">{item.reasoning}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
