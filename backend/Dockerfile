FROM python:3.11-slim

WORKDIR /app

# Le serveur ne tourne pas en root : il décompresse des archives et exécute
# Repomix sur du contenu fourni par les utilisateurs.
RUN useradd --create-home --uid 1000 app

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
# Installé hors de /root (emplacement par défaut) pour que l'utilisateur `app`
# puisse le lancer.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN python -m playwright install --with-deps chromium

# Pré-télécharge le modèle d'embeddings local (utilisé par code_index.py) pour
# que le premier vrai compliance-check n'attende pas ce téléchargement.
# cache_dir DOIT correspondre à EMBEDDING_CACHE_DIR dans code_index.py
# (.embeddings_cache, relatif à ce dossier) sinon ce téléchargement va dans le
# cache par défaut, un endroit différent de celui que le code lit au
# démarrage — le pré-téléchargement serait alors inutile.
RUN python -c "from llama_index.embeddings.fastembed import FastEmbedEmbedding; FastEmbedEmbedding(model_name='sentence-transformers/all-MiniLM-L6-v2', cache_dir='/app/.embeddings_cache')" \
    && chown -R app:app /app/.embeddings_cache

# Copier tout le code source (dont ton main.py)
COPY --chown=app:app . .

USER app

# Lancer l'application FastAPI avec Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
