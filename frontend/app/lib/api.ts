const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function fetchFromApi(endpoint: string, options: RequestInit = {}) {
  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`Erreur API: ${response.statusText}`);
  }

  return response.json();
}

export async function analyzeFile(file: File, outputFormat: 'xml' | 'markdown' = 'xml') {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_URL}/api/v1/analyses?output_format=${outputFormat}`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail || 'Impossible d’analyser le fichier.');
  }

  return response.json();
}

export async function runComplianceCheck(file: File, companyName?: string, companyContext?: string) {
  const formData = new FormData();
  formData.append('file', file);
  if (companyName) formData.append('company_name', companyName);
  if (companyContext) formData.append('company_context', companyContext);

  const response = await fetch(`${API_URL}/api/v1/compliance-check`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail || 'Impossible de lancer le compliance-check.');
  }

  return response.json();
}
