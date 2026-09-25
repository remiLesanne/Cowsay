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

# Copier tout le code source (dont ton main.py)
COPY . .

# Lancer l'application FastAPI avec Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
