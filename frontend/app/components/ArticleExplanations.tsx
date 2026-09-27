'use client';

import { useEffect, useState } from 'react';
import { getArticleExplanations, type ArticleExplanationSet, type ExplainedArticle } from '../lib/api';

// "Annex III" -> "Annexe III", "Chapter III Section 2" -> "Chapitre III, section 2".
function frenchRef(ref: string) {
  return ref
    .replace(/^Annex /, 'Annexe ')
    .replace(/^Chapter (\w+) Section (\d+)$/, 'Chapitre $1, section $2')
    .replace(/^Chapter /, 'Chapitre ');
}

function formatArticleList(numbers: string[]) {
  if (numbers.length === 0) return '';
  const values = numbers.map(Number);
  const isRange = values.every((value, index) => index === 0 || value === values[index - 1] + 1);
  if (isRange && values.length > 2) return `articles ${values[0]} à ${values[values.length - 1]}`;
  return `${values.length > 1 ? 'articles' : 'article'} ${numbers.join(', ')}`;
}

function ArticleCard({ article }: { article: ExplainedArticle }) {
  return (
    <li className="rounded-lg border border-slate-200 p-5">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:gap-3">
        <span className="shrink-0 rounded-full bg-[#e8f4f7] px-2.5 py-0.5 text-xs font-semibold text-[#173f5f]">{frenchRef(article.ref)}</span>
        <p className="text-sm font-semibold text-slate-800">{article.title}</p>
      </div>

      {!article.available ? (
        <p className="mt-3 text-sm text-slate-500">Le texte de cette référence n’est pas disponible dans notre copie de l’AI Act.</p>
      ) : (
        <>
          {article.explanation && <p className="mt-3 text-sm leading-6 text-slate-700">{article.explanation}</p>}
          {article.why_it_applies && (
            <div className="mt-3">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Pourquoi ça vous concerne</p>
              <p className="mt-1 text-sm leading-6 text-slate-700">{article.why_it_applies}</p>
            </div>
          )}
          {article.what_it_implies && (
            <div className="mt-3">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Ce que ça implique</p>
              <p className="mt-1 text-sm leading-6 text-slate-700">{article.what_it_implies}</p>
            </div>
          )}
          {article.passages.length > 0 && (
            <details className="mt-4 rounded-md bg-slate-50 px-4 py-3 text-sm">
              <summary className="cursor-pointer font-medium text-slate-600">
                Extraits officiels utilisés ({article.passages.length}) — version anglaise
              </summary>
              <ul className="mt-3 space-y-3">
                {article.passages.map((passage) => (
                  <li key={passage.label}>
                    <span className="font-mono text-xs font-semibold text-[#277da1]">{passage.label}</span>
                    <p className="mt-1 text-xs leading-5 text-slate-600">{passage.text}</p>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}

      <a className="mt-4 inline-block text-sm font-medium text-[#277da1] hover:underline" href={article.url} rel="noopener noreferrer" target="_blank">
        Texte officiel (FR) ↗
      </a>
    </li>
  );
}

type LoadState = { key: string; data?: ArticleExplanationSet; error?: string };

// specs/007: explains the articles the checker's verdict cites. Loaded after the verdict
// is displayed so the check itself is never slowed down; the backend caches the result.
export default function ArticleExplanations({
  analysisId,
  isComplete,
  resultsText,
}: {
  analysisId: string;
  isComplete: boolean;
  resultsText: string;
}) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<LoadState>({ key: '' });
  // A new verdict (after a resume round) or a retry changes the key and reloads.
  const requestKey = `${analysisId}|${resultsText}|${attempt}`;

  useEffect(() => {
    if (!isComplete) return;
    let cancelled = false;
    getArticleExplanations(analysisId)
      .then((data) => {
        if (!cancelled) setState({ key: requestKey, data });
      })
      .catch((error) => {
        if (!cancelled) setState({ key: requestKey, error: error instanceof Error ? error.message : 'Erreur inconnue.' });
      });
    return () => {
      cancelled = true;
    };
  }, [analysisId, isComplete, requestKey]);

  const isLoading = isComplete && state.key !== requestKey;
  const data = state.key === requestKey ? state.data : undefined;
  const error = state.key === requestKey ? state.error : undefined;

  return (
    <div className="mt-6 rounded-xl border border-slate-200 bg-white p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.15em] text-[#277da1]">Articles de l’AI Act concernés</p>
      <p className="mt-2 text-xs leading-5 text-slate-500">
        Explications générées par IA à partir du texte officiel de l’AI Act, pour vous aider à lire la recommandation ci-dessus.
        C’est la recommandation du checker officiel qui fait foi.
      </p>

      {!isComplete && (
        <p className="mt-4 text-sm text-slate-500">Complétez le formulaire pour obtenir l’explication des articles concernés.</p>
      )}

      {isLoading && <p className="mt-4 animate-pulse text-sm text-slate-500">Analyse des articles de l’AI Act…</p>}

      {error && (
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          <span>{error}</span>
          <button className="font-medium underline" onClick={() => setAttempt((value) => value + 1)} type="button">Réessayer</button>
        </div>
      )}

      {data?.status === 'no_references' && (
        <p className="mt-4 text-sm text-slate-500">La recommandation ne cite aucun article de l’AI Act.</p>
      )}

      {data?.status === 'ready' && (
        <>
          {data.articles.length > 0 && (
            <ul className="mt-5 space-y-4">
              {data.articles.map((article) => <ArticleCard article={article} key={article.ref} />)}
            </ul>
          )}
          {data.see_also.length > 0 && (
            <div className="mt-5">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Voir aussi</p>
              <ul className="mt-2 space-y-1 text-sm">
                {data.see_also.map((entry) => (
                  <li key={entry.ref}>
                    <a className="font-medium text-[#277da1] hover:underline" href={entry.url} rel="noopener noreferrer" target="_blank">{frenchRef(entry.ref)}</a>
                    <span className="text-slate-600"> — {entry.title}{entry.articles.length > 0 ? ` (${formatArticleList(entry.articles)})` : ''}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
