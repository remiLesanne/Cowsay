# Cowsay

Application web composée d’un frontend Next.js et d’une API backend FastAPI.
Le frontend appelle l’API au chargement de la page et affiche la réponse JSON
retournée par le backend.

## Vue d’ensemble

```text
Navigateur
    |
    | http://localhost:3000
    v
Frontend Next.js (frontend/)
    |
    | GET /
    | URL définie par NEXT_PUBLIC_API_URL
    v
Backend FastAPI (backend/)
    |
    | GET /       -> message de test
    | GET /health -> état de santé
    v
Déploiement AWS ECS / ECR
```

Le dépôt est organisé en deux parties :

```text
.
├── backend/
│   ├── main.py             # API FastAPI et configuration CORS
│   ├── requirements.txt    # Dépendances Python
│   └── Dockerfile          # Image Docker du backend
├── frontend/
│   ├── app/page.tsx        # Page principale React
│   ├── app/lib/api.ts      # Fonction cliente pour appeler l’API
│   ├── package.json        # Scripts et dépendances JavaScript
│   └── .env.exemple        # Exemple de configuration locale
└── .github/workflows/
    └── deploy.yml          # Déploiement automatique du backend sur AWS
```

## Fonctionnement de l’application

1. Le navigateur ouvre le frontend Next.js.
2. `frontend/app/page.tsx` exécute `fetchFromApi('/')` au montage du composant.
3. `frontend/app/lib/api.ts` construit l’URL à partir de `NEXT_PUBLIC_API_URL`.
   Si cette variable n’est pas définie, l’URL utilisée est
   `http://localhost:8000`.
4. FastAPI reçoit la requête et renvoie un objet JSON contenant `message` et
   `version`.
5. Le frontend affiche cet objet dans un bloc de code. En cas d’erreur réseau
   ou HTTP, un message d’erreur est affiché.

## API backend

Le backend est défini dans [`backend/main.py`](backend/main.py).

### `GET /`

Retourne actuellement une réponse de test semblable à :

```json
{
  "message": "🔥 TEST DEPLOYMENT AWS - LE CORS ET LE CODE SONT BIEN A JOUR ! 🔥",
  "version": "v3-debug"
}
```

### `GET /health`

Endpoint destiné aux vérifications de santé :

```json
{
  "status": "healthy"
}
```

### CORS

Les requêtes provenant de ces deux origines sont autorisées :

- `http://localhost:3000` pour le développement local ;
- `https://cowsay-one.vercel.app` pour le frontend déployé.

Si le frontend est déployé sur une autre adresse, celle-ci doit être ajoutée
dans `allow_origins` de `backend/main.py`.

## Lancer le projet en local

### 1. Démarrer le backend

Depuis la racine du projet :

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
# Windows PowerShell : .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

L’API est alors disponible sur <http://localhost:8000>.

Tests rapides :

```bash
curl http://localhost:8000/
curl http://localhost:8000/health
```

### 2. Démarrer le frontend

Dans un autre terminal :

```bash
cd frontend
cp .env.exemple .env.local
npm ci
npm run dev
```

Vérifier que `frontend/.env.local` contient :

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Le frontend est disponible sur <http://localhost:3000>.

Autres commandes utiles :

```bash
npm run lint   # Vérifie le code
npm run build  # Construit l’application pour la production
npm start      # Démarre la version construite
```

## Déploiement du backend

Le fichier [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) se
lance automatiquement à chaque push sur la branche `main`.

Le workflow :

1. récupère le code du dépôt ;
2. configure les identifiants AWS ;
3. se connecte à Amazon ECR ;
4. construit l’image Docker située dans `backend/` ;
5. pousse l’image dans ECR avec le SHA du commit comme tag ;
6. récupère la définition de tâche ECS existante ;
7. remplace l’image du conteneur `Main` ;
8. déploie la nouvelle définition sur le service ECS ;
9. attend que le service soit stable.

Le workflow utilise actuellement :

- région AWS : `us-east-1` ;
- cluster ECS : `default` ;
- service ECS : `cowsay-backend-dcab` ;
- définition de tâche : `default-cowsay-backend-dcab`.

Les secrets suivants doivent être configurés dans GitHub, dans
**Settings → Secrets and variables → Actions** :

- `AWS_ACCESS_KEY_ID` ;
- `AWS_SECRET_ACCESS_KEY`.

## Construire et lancer le backend avec Docker

```bash
cd backend
docker build -t cowsay-backend .
docker run --rm -p 8000:8000 cowsay-backend
```

Le backend sera accessible sur <http://localhost:8000>.

## Points à connaître

- Le projet n’utilise pas encore de `docker-compose.yml` : le frontend et le
  backend se lancent séparément.
- Le frontend attend une réponse JSON et affiche la réponse complète, pas
  uniquement le champ `message`.
- `NEXT_PUBLIC_API_URL` est une variable exposée au navigateur : elle ne doit
  donc pas contenir de secret.
- Le backend autorise actuellement un nombre limité d’origines CORS. Toute
  nouvelle URL de frontend doit être ajoutée explicitement.
- Le message de la route `/` contient encore du texte de test (`v3-debug`) et
  pourra être remplacé lorsque la logique métier du hackathon sera finalisée.

## Développement recommandé

Pour modifier l’interface, commencer par
[`frontend/app/page.tsx`](frontend/app/page.tsx). Pour modifier les appels API,
utiliser [`frontend/app/lib/api.ts`](frontend/app/lib/api.ts). Pour ajouter ou
modifier une route backend, éditer [`backend/main.py`](backend/main.py), puis
mettre à jour ce README si le contrat de l’API change.
