'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { resumeComplianceCheck } from '../lib/api';

type UnresolvedQuestion = {
  field_id: string;
  // The checker form has other free-text-like input kinds too (e.g. "email");
  // anything without `options` is rendered as a plain text input, so this is
  // intentionally not a closed union.
  type: 'radio' | 'checkbox' | string;
  question: string;
  reasoning: string;
  options?: string[];
};

type ComplianceResult = {
  session_id: string;
  is_complete: boolean;
  results_text: string;
  questions_answered: number;
  needs_human_input: UnresolvedQuestion[];
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
  const [name, setName] = useState<string | null>(null);
  const [result, setResult] = useState<ComplianceResult | null>(null);
  const [error, setError] = useState('');
  const [answers, setAnswers] = useState<Record<string, string | string[]>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  useEffect(() => {
    const raw = sessionStorage.getItem('ai-risk-check-result');
    const timer = window.setTimeout(() => {
      if (!raw) {
        setError('Aucun résultat trouvé. Retournez au dépôt pour lancer une analyse.');
        return;
      }
      try {
        const stored = JSON.parse(raw) as StoredResult;
        setName(stored.name);
        setResult(stored.result);
      } catch {
        setError('Impossible de lire le résultat de l’analyse.');
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const setRadioAnswer = (fieldId: string, value: string) => {
    setAnswers((previous) => ({ ...previous, [fieldId]: value }));
  };

  const toggleCheckboxAnswer = (fieldId: string, option: string, checked: boolean) => {
    setAnswers((previous) => {
      const current = Array.isArray(previous[fieldId]) ? (previous[fieldId] as string[]) : [];
      const next = checked ? [...current, option] : current.filter((value) => value !== option);
      return { ...previous, [fieldId]: next };
    });
  };

  const setTextAnswer = (fieldId: string, value: string) => {
    setAnswers((previous) => ({ ...previous, [fieldId]: value }));
  };

  const submitAnswers = async () => {
    if (!result || isSubmitting) return;
    const payload = Object.entries(answers)
      .filter(([, value]) => (Array.isArray(value) ? value.length > 0 : value !== ''))
      .map(([field_id, value]) => ({ field_id, value }));
    if (payload.length === 0) return;

    setIsSubmitting(true);
    setSubmitError('');
    try {
      const updated = await resumeComplianceCheck(result.session_id, payload);
      setResult(updated);
      setAnswers({});
      sessionStorage.setItem('ai-risk-check-result', JSON.stringify({ name, result: updated }));
    } catch (submitErr) {
      setSubmitError(submitErr instanceof Error ? submitErr.message : 'Erreur inconnue.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const hasAnswersToSubmit = Object.values(answers).some((value) =>
    Array.isArray(value) ? value.length > 0 : value !== '',
  );

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
            <h1 className="text-3xl font-semibold tracking-[-0.03em] text-slate-900">{name ?? 'Résultat de l’analyse'}</h1>
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
                  Répondez ci-dessous puis envoyez pour continuer l’analyse.
                </p>
                <ul className="mt-4 space-y-4 text-sm">
                  {result.needs_human_input.map((item) => (
                    <li className="rounded-lg bg-white/70 p-4" key={item.field_id}>
                      <p className="font-medium text-amber-900">{item.question}</p>
                      <p className="mt-1 text-xs text-amber-700">{item.reasoning}</p>

                      {item.type === 'radio' && (
                        <div className="mt-3 space-y-2">
                          {item.options?.map((option) => (
                            <label className="flex items-center gap-2 text-sm text-slate-700" key={option}>
                              <input
                                checked={answers[item.field_id] === option}
                                name={`answer-${item.field_id}`}
                                onChange={() => setRadioAnswer(item.field_id, option)}
                                type="radio"
                              />
                              {option}
                            </label>
                          ))}
                        </div>
                      )}

                      {item.type === 'checkbox' && (
                        <div className="mt-3 space-y-2">
                          {item.options?.map((option) => (
                            <label className="flex items-center gap-2 text-sm text-slate-700" key={option}>
                              <input
                                checked={
                                  Array.isArray(answers[item.field_id]) &&
                                  (answers[item.field_id] as string[]).includes(option)
                                }
                                onChange={(event) =>
                                  toggleCheckboxAnswer(item.field_id, option, event.target.checked)
                                }
                                type="checkbox"
                              />
                              {option}
                            </label>
                          ))}
                        </div>
                      )}

                      {item.type !== 'radio' && item.type !== 'checkbox' && (
                        <input
                          className="mt-3 block w-full rounded-md border border-amber-300 px-3 py-2 text-sm"
                          onChange={(event) => setTextAnswer(item.field_id, event.target.value)}
                          type="text"
                          value={(answers[item.field_id] as string) ?? ''}
                        />
                      )}
                    </li>
                  ))}
                </ul>

                {submitError && <p className="mt-3 text-sm text-rose-700">{submitError}</p>}

                <button
                  className="mt-4 rounded-lg bg-[#173f5f] px-5 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
                  disabled={!hasAnswersToSubmit || isSubmitting}
                  onClick={submitAnswers}
                  type="button"
                >
                  {isSubmitting ? 'Envoi en cours…' : 'Envoyer mes réponses'}
                </button>
              </div>
            )}
          </>
        )}
      </section>
    </main>
  );
}
