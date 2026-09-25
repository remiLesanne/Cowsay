'use client';

import { ChangeEvent, DragEvent, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { analyzeFile } from './lib/api';

const ACCEPTED_EXTENSIONS = ['.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.go', '.rs', '.php', '.rb', '.c', '.cpp', '.cs', '.xml', '.md', '.zip'];
const ACCEPTED_LABEL = 'Code, XML, Markdown ou ZIP';
const MAX_FILE_SIZE = 10 * 1024 * 1024;

function FileCodeIcon() {
  return <svg aria-hidden="true" className="h-7 w-7" fill="none" viewBox="0 0 24 24"><path d="m8.5 8-4 4 4 4M15.5 8l4 4-4 4M13.5 5l-3 14" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" /></svg>;
}

function UploadIcon() {
  return <svg aria-hidden="true" className="h-8 w-8" fill="none" viewBox="0 0 24 24"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14v4.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V14" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" /></svg>;
}

function CheckIcon() {
  return <svg aria-hidden="true" className="h-5 w-5" fill="none" viewBox="0 0 24 24"><path d="m5 12 4.5 4.5L19 7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" /></svg>;
}

export default function Home() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [message, setMessage] = useState('');
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
    if (candidate.size > MAX_FILE_SIZE) {
      setFile(null);
      setMessage('Ce fichier dépasse la taille maximale de 10 Mo.');
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

  const formatSize = (size: number) => size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} Ko` : `${(size / (1024 * 1024)).toFixed(1)} Mo`;

  const openAnalysis = async () => {
    if (!file || isAnalysing) return;

    setIsAnalysing(true);
    try {
      if (file.name.toLowerCase().endsWith('.zip')) {
        const analysisResult = await analyzeFile(file);
        sessionStorage.setItem('ai-risk-check-file', JSON.stringify({
          name: file.name,
          size: file.size,
          type: file.type,
          content: '',
          analysisResult,
        }));
        router.push('/analyse');
        return;
      }

      const content = await file.text();
      sessionStorage.setItem('ai-risk-check-file', JSON.stringify({
        name: file.name,
        size: file.size,
        type: file.type,
        content,
      }));
      router.push('/analyse');
    } catch {
      setMessage('Impossible de lire ce fichier.');
      setIsAnalysing(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#f8fafc] text-slate-900">
      <header className="border-b border-slate-200/80 bg-white">
        <div className="mx-auto flex h-[72px] w-full max-w-6xl items-center justify-between px-6 lg:px-10">
          <div className="flex items-center gap-3"><div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#173f5f] text-white"><FileCodeIcon /></div><span className="text-[17px] font-semibold tracking-[-0.02em] text-slate-800">AI Risk Check</span></div>
          <div className="hidden items-center gap-2 text-sm text-slate-500 sm:flex"><span className="h-2 w-2 rounded-full bg-emerald-500" />Conforme à l’AI Act</div>
        </div>
      </header>

      <section className="mx-auto max-w-3xl px-6 pb-20 pt-16 text-center lg:pt-24">
        <p className="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-[#277da1]">Analyse de conformité</p>
        <h1 className="text-4xl font-semibold tracking-[-0.04em] text-slate-900 sm:text-5xl">Évaluez les risques de votre IA</h1>
        <p className="mx-auto mt-5 max-w-xl text-[17px] leading-8 text-slate-500">Déposez un fichier de votre projet pour obtenir une première analyse au regard des recommandations de l’AI Act.</p>

        <div className="mt-12 rounded-2xl border border-slate-200 bg-white p-3 shadow-[0_12px_40px_rgba(15,23,42,0.05)] sm:p-4">
          <div aria-label="Zone de dépôt de fichier" className={`flex min-h-[270px] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 transition-colors ${isDragging ? 'border-[#277da1] bg-[#f0f9fc]' : 'border-slate-300 bg-slate-50/60 hover:border-[#5a9db7] hover:bg-[#f7fcfd]'}`} onClick={() => inputRef.current?.click()} onDragEnter={(event) => { event.preventDefault(); setIsDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={(event) => { if (event.currentTarget === event.target) setIsDragging(false); }} onDrop={handleDrop} role="button" tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click(); }}>
            <input ref={inputRef} className="hidden" type="file" accept={ACCEPTED_EXTENSIONS.join(',')} onChange={handleInput} />
            {file ? <><div className="mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-50 text-emerald-600"><CheckIcon /></div><p className="max-w-full truncate text-base font-medium text-slate-800">{file.name}</p><p className="mt-1 text-sm text-slate-500">{formatSize(file.size)} · Fichier prêt à être analysé</p><button className="mt-5 text-sm font-medium text-[#277da1] hover:underline" onClick={(event) => { event.stopPropagation(); inputRef.current?.click(); }} type="button">Choisir un autre fichier</button></> : <><div className="mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-[#e8f4f7] text-[#277da1]"><UploadIcon /></div><p className="text-base font-medium text-slate-700">Glissez-déposez votre fichier ici</p><p className="mt-2 text-sm text-slate-500">ou <span className="font-medium text-[#277da1]">parcourez vos fichiers</span></p><p className="mt-6 text-xs text-slate-400">{ACCEPTED_LABEL} · 10 Mo maximum</p></>}
          </div>
          {message && <p className="px-2 pt-3 text-left text-sm text-rose-600">{message}</p>}
        </div>

        <button className="mt-6 inline-flex h-12 w-full items-center justify-center rounded-lg bg-[#173f5f] px-7 text-sm font-semibold text-white transition hover:bg-[#12344f] disabled:cursor-not-allowed disabled:bg-slate-300 sm:w-auto" disabled={!file || isAnalysing} onClick={openAnalysis} type="button">{isAnalysing ? 'Préparation…' : 'Lancer l’analyse'}</button>
        <p className="mt-5 text-xs text-slate-400">Vos fichiers sont utilisés uniquement pour cette analyse.</p>
      </section>
    </main>
  );
}
