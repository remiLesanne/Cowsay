'use client';

import { ChangeEvent, DragEvent, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import AppHeader from './components/AppHeader';
import { useRequireAuth } from './components/useRequireAuth';
import { runComplianceCheck } from './lib/api';

const ACCEPTED_EXTENSIONS = ['.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.go', '.rs', '.php', '.rb', '.c', '.cpp', '.cs', '.xml', '.md', '.zip'];
const ACCEPTED_LABEL = 'Code, XML, Markdown ou ZIP';
const MAX_CODE_FILE_SIZE = 10 * 1024 * 1024;
const MAX_ZIP_FILE_SIZE = 500 * 1024 * 1024;
// specs/006: a PDF is a bounded document (register entry, DPIA, factsheet), not a
// project archive — reuses the single-code-file ceiling rather than a new constant.
const MAX_PDF_FILE_SIZE = 10 * 1024 * 1024;

function UploadIcon() {
  return <svg aria-hidden="true" className="h-8 w-8" fill="none" viewBox="0 0 24 24"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14v4.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V14" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" /></svg>;
}

function CheckIcon() {
  return <svg aria-hidden="true" className="h-5 w-5" fill="none" viewBox="0 0 24 24"><path d="m5 12 4.5 4.5L19 7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" /></svg>;
}

export default function Home() {
  const router = useRouter();
  const user = useRequireAuth();
  const inputRef = useRef<HTMLInputElement>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [pdf, setPdf] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [message, setMessage] = useState('');
  const [pdfMessage, setPdfMessage] = useState('');
  const [isAnalysing, setIsAnalysing] = useState(false);

  const isAccepted = (candidate: File) => {
    const extension = `.${candidate.name.split('.').pop()?.toLowerCase()}`;
    return ACCEPTED_EXTENSIONS.includes(extension);
  };

  const selectFile = (candidate?: File) => {
    if (!candidate) return;
    if (!isAccepted(candidate)) {
      setFile(null);
      setMessage('Ce format n’est pas pris en charge. Ajoutez un fichier de code, XML, Markdown ou ZIP.');
      return;
    }
    const isZip = candidate.name.toLowerCase().endsWith('.zip');
    const maxFileSize = isZip ? MAX_ZIP_FILE_SIZE : MAX_CODE_FILE_SIZE;

    if (candidate.size > maxFileSize) {
      setFile(null);
      setMessage(`Ce fichier dépasse la taille maximale de ${isZip ? '500' : '10'} Mo.`);
      return;
    }
    setMessage('');
    setFile(candidate);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    selectFile(event.dataTransfer.files[0]);
  };

  const handleInput = (event: ChangeEvent<HTMLInputElement>) => {
    selectFile(event.target.files?.[0]);
    event.target.value = '';
  };

  const selectPdf = (candidate?: File) => {
    if (!candidate) return;
    if (!candidate.name.toLowerCase().endsWith('.pdf')) {
      setPdf(null);
      setPdfMessage('Ce fichier n’est pas un PDF.');
      return;
    }
    if (candidate.size > MAX_PDF_FILE_SIZE) {
      setPdf(null);
      setPdfMessage('Ce PDF dépasse la taille maximale de 10 Mo.');
      return;
    }
    setPdfMessage('');
    setPdf(candidate);
  };

  const handlePdfInput = (event: ChangeEvent<HTMLInputElement>) => {
    selectPdf(event.target.files?.[0]);
    event.target.value = '';
  };

  const formatSize = (size: number) => size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} Ko` : `${(size / (1024 * 1024)).toFixed(1)} Mo`;

  const openAnalysis = async () => {
    if ((!file && !pdf) || isAnalysing) return;

    setIsAnalysing(true);
    setMessage('');
    try {
      // Returns as soon as the analysis is queued; its page follows it to the result.
      const submitted = await runComplianceCheck(file, pdf);
      router.push(`/analyse?id=${encodeURIComponent(submitted.analysis_id)}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Impossible d’analyser ce fichier.');
      setIsAnalysing(false);
    }
  };

  if (!user) return <main className="min-h-screen bg-[#f8fafc]" />;

  return (
    <main className="min-h-screen bg-[#f8fafc] text-slate-900">
      <AppHeader user={user} />

      <section className="mx-auto max-w-3xl px-6 pb-20 pt-16 text-center lg:pt-24">
        <p className="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-[#277da1]">Analyse de conformité</p>
        <h1 className="text-4xl font-semibold tracking-[-0.04em] text-slate-900 sm:text-5xl">Évaluez les risques de votre IA</h1>
        <p className="mx-auto mt-5 max-w-xl text-[17px] leading-8 text-slate-500">Déposez un fichier de votre projet pour obtenir une première analyse au regard des recommandations de l’AI Act.</p>

        <div className="mt-12 rounded-2xl border border-slate-200 bg-white p-3 shadow-[0_12px_40px_rgba(15,23,42,0.05)] sm:p-4">
          <div aria-label="Zone de dépôt de fichier" className={`flex min-h-[270px] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 transition-colors ${isDragging ? 'border-[#277da1] bg-[#f0f9fc]' : 'border-slate-300 bg-slate-50/60 hover:border-[#5a9db7] hover:bg-[#f7fcfd]'}`} onClick={() => inputRef.current?.click()} onDragEnter={(event) => { event.preventDefault(); setIsDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={(event) => { if (event.currentTarget === event.target) setIsDragging(false); }} onDrop={handleDrop} role="button" tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click(); }}>
            <input ref={inputRef} className="hidden" type="file" accept={ACCEPTED_EXTENSIONS.join(',')} onChange={handleInput} />
            {file ? <><div className="mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-50 text-emerald-600"><CheckIcon /></div><p className="max-w-full truncate text-base font-medium text-slate-800">{file.name}</p><p className="mt-1 text-sm text-slate-500">{formatSize(file.size)} · Fichier prêt à être analysé</p><button className="mt-5 text-sm font-medium text-[#277da1] hover:underline" onClick={(event) => { event.stopPropagation(); inputRef.current?.click(); }} type="button">Choisir un autre fichier</button></> : <><div className="mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-[#e8f4f7] text-[#277da1]"><UploadIcon /></div><p className="text-base font-medium text-slate-700">Glissez-déposez votre fichier ici</p><p className="mt-2 text-sm text-slate-500">ou <span className="font-medium text-[#277da1]">parcourez vos fichiers</span></p><p className="mt-6 text-xs text-slate-400">{ACCEPTED_LABEL} · 500 Mo maximum</p></>}
          </div>
          {message && <p className="px-2 pt-3 text-left text-sm text-rose-600">{message}</p>}
        </div>

        <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4 text-left shadow-[0_12px_40px_rgba(15,23,42,0.05)]">
          <p className="text-sm font-medium text-slate-700">Optionnel : ajoutez un PDF décrivant le système IA</p>
          <p className="mt-1 text-xs text-slate-500">Par exemple une fiche de registre IA, une DPIA, ou toute documentation — utile si vous n’avez pas (ou pas tout) le code source.</p>
          <input ref={pdfInputRef} className="hidden" type="file" accept=".pdf,application/pdf" onChange={handlePdfInput} />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:border-[#5a9db7] hover:text-[#277da1]" onClick={() => pdfInputRef.current?.click()} type="button">
              {pdf ? 'Changer le PDF' : 'Choisir un PDF'}
            </button>
            {pdf && (
              <span className="flex items-center gap-2 text-sm text-slate-600">
                {pdf.name} ({formatSize(pdf.size)})
                <button className="text-[#277da1] hover:underline" onClick={() => setPdf(null)} type="button">retirer</button>
              </span>
            )}
          </div>
          {pdfMessage && <p className="pt-2 text-sm text-rose-600">{pdfMessage}</p>}
        </div>

        <button className="mt-6 inline-flex h-12 w-full items-center justify-center rounded-lg bg-[#173f5f] px-7 text-sm font-semibold text-white transition hover:bg-[#12344f] disabled:cursor-not-allowed disabled:bg-slate-300 sm:w-auto" disabled={(!file && !pdf) || isAnalysing} onClick={openAnalysis} type="button">{isAnalysing ? 'Envoi en cours…' : 'Lancer l’analyse'}</button>
        {!file && !pdf && <p className="mt-3 text-xs text-rose-500">Ajoutez un fichier de code ou un PDF pour continuer.</p>}
        <p className="mt-5 text-xs text-slate-400">Vos fichiers sont utilisés uniquement pour cette analyse.</p>
      </section>
    </main>
  );
}
