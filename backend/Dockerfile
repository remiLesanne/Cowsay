FROM python:3.11-slim

WORKDIR /app

# Repomix est un outil Node.js exécuté par le backend.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Installer Repomix de façon reproductible depuis package.json.
COPY package.json .
RUN npm install --omit=dev

# Copier et installer les dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright pilote un vrai navigateur pour remplir le formulaire officiel de
# l'EU AI Act Compliance Checker (logique de scoring dynamique, non reproduite ici).
RUN python -m playwright install --with-deps chromium

# Pré-télécharge le modèle d'embeddings local (utilisé par code_index.py) pour
# que le premier vrai compliance-check n'attende pas ce téléchargement.
# cache_folder DOIT correspondre à EMBEDDING_CACHE_DIR dans code_index.py
# (.embeddings_cache, relatif à ce dossier) sinon ce téléchargement va dans le
# cache HF par défaut, un endroit différent de celui que le code lit au
# démarrage — le pré-téléchargement serait alors inutile.
RUN python -c "from llama_index.embeddings.huggingface import HuggingFaceEmbedding; HuggingFaceEmbedding(model_name='sentence-transformers/all-MiniLM-L6-v2', cache_folder='/app/.embeddings_cache')"

# Copier tout le code source (dont ton main.py)
COPY . .

# Lancer l'application FastAPI avec Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
