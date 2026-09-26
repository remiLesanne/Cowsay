const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const TOKEN_KEY = 'cowsay-token';

export type User = { id: string; email: string; created_at?: string };
type AuthResponse = { access_token: string; token_type: string; user: User };

// Bearer token in localStorage rather than a cookie: front (Vercel) and back (AWS)
// are cross-origin — see specs/005-user-accounts-history/research.md.
export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function setToken(token: string) {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Storage blocked (private mode): the user stays logged in for this page only.
  }
}

export function clearToken() {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // nothing to clear
  }
}

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

// Adds the bearer token; a 401 means the login is missing or expired, so the token
// is dropped and the user is sent back to /login (spec 005 Edge Cases).
async function authFetch(endpoint: string, options: RequestInit = {}) {
  const token = getToken();
  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      ...options.headers,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (response.status === 401) {
    clearToken();
    // Plain module, no router available here; a full reload also wipes stale page state.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign('/login');
    throw new Error('Connexion requise ou expirée, merci de vous reconnecter.');
  }
  return response;
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
  // FastAPI validation errors (422): a list of {loc, msg, type}.
  if (Array.isArray(detail)) {
    const fields = detail.map((item) => (item as { loc?: unknown[] }).loc?.at(-1));
    if (fields.includes('password')) return 'Le mot de passe doit contenir au moins 8 caractères.';
    if (fields.includes('email')) return 'Adresse email invalide.';
    return fallback;
  }
  if (typeof detail === 'object' && detail !== null && 'message' in detail) {
    const withOptions = detail as { message: string; valid_options?: string[] };
    const options = withOptions.valid_options?.length
      ? ` (options valides : ${withOptions.valid_options.join(', ')})`
      : '';
    return `${withOptions.message}${options}`;
  }
  return fallback;
}

async function authenticate(endpoint: string, email: string, password: string, fallback: string) {
  const response = await fetch(`${API_URL}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(detailToMessage(error?.detail, fallback));
  }
  const data = (await response.json()) as AuthResponse;
  setToken(data.access_token);
  return data.user;
}

export function register(email: string, password: string) {
  return authenticate('/api/v1/auth/register', email, password, 'Impossible de créer le compte.');
}

export function login(email: string, password: string) {
  return authenticate('/api/v1/auth/login', email, password, 'Impossible de se connecter.');
}

export function logout() {
  clearToken();
}

export async function getMe(): Promise<User> {
  const response = await authFetch('/api/v1/auth/me');
  if (!response.ok) throw new Error('Impossible de récupérer le compte.');
  return response.json();
}

export async function runComplianceCheck(file: File, companyName?: string, companyContext?: string) {
  const formData = new FormData();
  formData.append('file', file);
  if (companyName) formData.append('company_name', companyName);
  if (companyContext) formData.append('company_context', companyContext);

  const response = await authFetch('/api/v1/compliance-check', {
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
  const response = await authFetch(`/api/v1/compliance-check/${sessionId}/answer`, {
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
