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

function detailToMessage(detail: unknown, fallback: string): string {
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  if (typeof detail === 'object' && detail !== null && 'message' in detail) {
    const withOptions = detail as { message: string; valid_options?: string[] };
    const options = withOptions.valid_options?.length
      ? ` (options valides : ${withOptions.valid_options.join(', ')})`
      : '';
    return `${withOptions.message}${options}`;
  }
  return fallback;
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
    throw new Error(detailToMessage(error?.detail, 'Impossible de lancer le compliance-check.'));
  }

  return response.json();
}

export type HumanAnswer = { field_id: string; value: string | string[] };

export async function resumeComplianceCheck(sessionId: string, answers: HumanAnswer[]) {
  const response = await fetch(`${API_URL}/api/v1/compliance-check/${sessionId}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answers }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(detailToMessage(error?.detail, 'Impossible d’envoyer la réponse.'));
  }

  return response.json();
}
