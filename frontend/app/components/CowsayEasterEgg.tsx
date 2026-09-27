'use client';

import { useEffect, useState } from 'react';

// Easter egg: the exact output of the Linux command `cowsay "je suis la sainte vache qui parle"`.
const COW = String.raw` ___________________________________
< je suis la sainte vache qui parle >
 -----------------------------------
        \   ^__^
         \  (oo)\_______
            (__)\       )\/\
                ||----w |
                ||     ||`;

const SECRET = 'cowsay';
const VISIBLE_MS = 6000;

// Triggered by typing "cowsay" anywhere outside a form field, or by the near-invisible
// button in the bottom-right corner. The cow leaves on its own after a few seconds.
export default function CowsayEasterEgg() {
  // Timestamp rather than a boolean so a new trigger restarts the timer.
  const [shownAt, setShownAt] = useState<number | null>(null);

  useEffect(() => {
    let typed = '';
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement).closest('input, textarea, select, [contenteditable]')) return;
      if (event.key.length !== 1) return;
      typed = (typed + event.key.toLowerCase()).slice(-SECRET.length);
      if (typed === SECRET) setShownAt(Date.now());
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  useEffect(() => {
    if (shownAt === null) return;
    const timer = setTimeout(() => setShownAt(null), VISIBLE_MS);
    return () => clearTimeout(timer);
  }, [shownAt]);

  return (
    <>
      <button
        aria-label="Meuh ?"
        className="fixed bottom-1 right-1 z-40 h-5 w-5 text-xs opacity-0 transition-opacity hover:opacity-60"
        onClick={() => setShownAt(Date.now())}
        type="button"
      >
        🐄
      </button>

      {shownAt !== null && (
        <div
          className="cowsay-pop fixed bottom-8 right-6 z-50 cursor-pointer rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-2xl"
          key={shownAt}
          onClick={() => setShownAt(null)}
          role="status"
        >
          <pre className="text-xs leading-4 text-emerald-300 sm:text-sm sm:leading-5">{COW}</pre>
        </div>
      )}
    </>
  );
}
