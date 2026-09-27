'use client';

import Link from 'next/link';
import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import AppHeader from '../components/AppHeader';
import { useRequireAuth } from '../components/useRequireAuth';
import { getAnalysis, resumeComplianceCheck, type AnalysisResult, type QuestionDetail } from '../lib/api';

function ArrowLeftIcon() {
  return <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24"><path d="M19 12H5m6 6-6-6 6-6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" /></svg>;
}

function formatAnswer(detail: QuestionDetail) {
  if (Array.isArray(detail.answer)) return detail.answer.length ? detail.answer.join(', ') : 'Aucune option retenue';
  return detail.answer || 'Sans réponse';
}

function SourceBadge({ detail }: { detail: QuestionDetail }) {
  if (detail.source === 'human') {
    return <span className="rounded-full bg-sky-50 px-2 py-0.5 text-xs font-medium text-sky-700">Vous</span>;
  }
  const lowConfidence = detail.confidence === 'low';
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${lowConfidence ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-600'}`}>
      IA{detail.confidence ? ` · confiance ${detail.confidence}` : ''}
    </span>
  );
}

function AnalyseContent() {
  const analysisId = useSearchParams().get('id');
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loadError, setLoadError] = useState('');
  const [answers, setAnswers] = useState<Record<string, string | string[]>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  useEffect(() => {
    if (!analysisId) return;
    let cancelled = false;
    getAnalysis(analysisId)
      .then((loaded) => {
        if (!cancelled) setResult(loaded);
      })
      .catch((error) => {
        if (!cancelled) setLoadError(error instanceof Error ? error.message : 'Impossible de charger cette analyse.');
      });
    return () => {
      cancelled = true;
    };
  }, [analysisId]);

  const error = analysisId ? loadError : 'Aucune analyse sélectionnée.';

  const setRadioAnswer = (fieldId: string, value: string) => {
    setAnswers((previous) => ({ ...previous, [fieldId]: value }));
  };

  // The real checker form treats "None of the above" as exclusive with every
  // other option in its group (live-verified: checking it there clears the
  // others, and checking another option afterwards is rejected by the site's
  // own JS). Our own review UI has no such rule by default, so a human could
  // submit both at once — replayed onto the real form via Playwright, that's
  // an order-dependent, effectively undefined result. Mirror it here instead.
  const isNoneOfTheAbove = (option: string) => option.trim().toLowerCase() === 'none of the above';

  const toggleCheckboxAnswer = (fieldId: string, option: string, checked: boolean) => {
    setAnswers((previous) => {
      const current = Array.isArray(previous[fieldId]) ? (previous[fieldId] as string[]) : [];
      if (!checked) {
        return { ...previous, [fieldId]: current.filter((value) => value !== option) };
      }
      const next = isNoneOfTheAbove(option)
        ? [option]
        : [...current.filter((value) => !isNoneOfTheAbove(value)), option];
      return { ...previous, [fieldId]: next };
    });
  };

  const setTextAnswer = (fieldId: string, value: string) => {
    setAnswers((previous) => ({ ...previous, [fieldId]: value }));
  };

  const submitAnswers = async () => {
    if (!result?.session_id || isSubmitting) return;
    const payload = Object.entries(answers)
      .filter(([, value]) => (Array.isArray(value) ? value.length > 0 : value.trim() !== ''))
      .map(([field_id, value]) => ({ field_id, value }));
    if (payload.length === 0) return;

    setIsSubmitting(true);
    setSubmitError('');
    try {
      const updated = await resumeComplianceCheck(result.session_id, payload);
      setResult((previous) => (previous ? { ...previous, ...updated } : updated));
      setAnswers({});
    } catch (submitErr) {
      setSubmitError(submitErr instanceof Error ? submitErr.message : 'Erreur inconnue.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const hasAnswersToSubmit = Object.values(answers).some((value) =>
    Array.isArray(value) ? value.length > 0 : value.trim() !== '',
  );

  return (
    <section className="mx-auto max-w-4xl px-6 pb-20 pt-10 lg:px-10">
      <Link className="inline-flex items-center gap-2 text-sm font-medium text-[#277da1] hover:underline" href="/historique"><ArrowLeftIcon />Mes analyses</Link>

      <div className="mt-9 flex flex-col justify-between gap-5 border-b border-slate-200 pb-7 sm:flex-row sm:items-end">
        <div>
          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-[#277da1]">Fichier soumis</p>
          <h1 className="text-3xl font-semibold tracking-[-0.03em] text-slate-900">{result?.filename || 'Résultat de l’analyse'}</h1>
          {result?.created_at && (
            <p className="mt-2 text-sm text-slate-500">
              Analysé le {new Date(result.created_at).toLocaleString('fr-FR')}
              {result.company_name ? ` · ${result.company_name}` : ''}
            </p>
          )}
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
          {error} <Link className="font-medium underline" href="/historique">Voir mes analyses</Link>
        </div>
      )}

      {!result && !error && <p className="mt-8 text-sm text-slate-500">Chargement de l’analyse…</p>}

      {result && (
        <>
          {result.pdf_warning && (
            <div className="mt-8 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              {result.pdf_warning}
            </div>
          )}
          <div className="mt-8 rounded-xl border border-slate-200 bg-white p-6 shadow-[0_12px_40px_rgba(15,23,42,0.05)]">
            <p className="text-xs font-semibold uppercase tracking-[0.15em] text-[#277da1]">Recommandation de l’EU AI Act Compliance Checker</p>
            <p className="mt-2 text-sm text-slate-500">{result.questions_answered} question(s) répondue(s)</p>
            <pre className="mt-4 whitespace-pre-wrap font-sans text-sm leading-6 text-slate-800">{result.results_text}</pre>
          </div>

          {result.needs_human_input.length > 0 && result.session_id && (
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
                    <p className="whitespace-pre-line font-medium text-amber-900">{item.question}</p>
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

          {result.needs_human_input.length > 0 && !result.session_id && (
            <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-800">
              <p className="font-semibold">{result.needs_human_input.length} question(s) restaient sans réponse</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-amber-900">
                {result.needs_human_input.map((item) => (
                  <li className="whitespace-pre-line" key={item.field_id}>{item.question}</li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-amber-700">
                La session de cette analyse a expiré (30 min) : pour y répondre, <Link className="font-medium underline" href="/">relancez une analyse</Link> en renvoyant le fichier.
              </p>
            </div>
          )}

          {result.question_details.length > 0 && (
            <div className="mt-6 rounded-xl border border-slate-200 bg-white p-6">
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-[#277da1]">Détail des réponses au formulaire</p>
              <ol className="mt-4 divide-y divide-slate-100">
                {result.question_details.map((detail, index) => (
                  <li className="py-4 first:pt-0 last:pb-0" key={`${detail.field_id}-${index}`}>
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                      <p className="whitespace-pre-line text-sm font-medium text-slate-800">{detail.question}</p>
                      <SourceBadge detail={detail} />
                    </div>
                    <p className="mt-2 text-sm text-slate-700"><span className="text-slate-500">Réponse :</span> {formatAnswer(detail)}</p>
                    {detail.reasoning && <p className="mt-1 text-xs text-slate-500">{detail.reasoning}</p>}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </>
      )}
    </section>
  );
}

export default function AnalysePage() {
  const user = useRequireAuth();

  if (!user) return <main className="min-h-screen bg-[#f8fafc]" />;

  return (
    <main className="min-h-screen bg-[#f8fafc] text-slate-900">
      <AppHeader user={user} />
      {/* useSearchParams must sit under a Suspense boundary or `next build` fails (Next 16 docs). */}
      <Suspense fallback={<p className="mx-auto max-w-4xl px-6 pt-10 text-sm text-slate-500 lg:px-10">Chargement…</p>}>
        <AnalyseContent />
      </Suspense>
    </main>
  );
}
