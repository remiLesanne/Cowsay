'use client';

import { useEffect, useState } from 'react';
import { fetchFromApi } from '@/app/lib/api';

export default function Home() {
  const [responseMessage, setResponseMessage] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchFromApi('/')
      .then((data) => {
        // Adapte selon la structure JSON renvoyée par ton API FastAPI (ex: data.message ou data)
        setResponseMessage(JSON.stringify(data, null, 2));
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24 bg-gray-50 text-gray-900">
      <div className="z-10 max-w-5xl w-full items-center justify-between font-mono text-sm">
        <h1 className="text-4xl font-bold mb-8 text-center">
          Monorepo CowSay 🐮
        </h1>

        <div className="p-6 bg-white rounded-xl shadow-md border border-gray-200">
          <h2 className="text-lg font-semibold mb-4 text-indigo-600">
            Réponse de API FastAPI (AWS) :
          </h2>

          {loading && <p className="text-gray-500 animate-pulse">Chargement des données...</p>}
          
          {error && <p className="text-red-500">Erreur : {error}</p>}

          {!loading && !error && (
            <pre className="bg-gray-900 text-green-400 p-4 rounded-lg overflow-x-auto">
              {responseMessage}
            </pre>
          )}
        </div>
      </div>
    </main>
  );
}