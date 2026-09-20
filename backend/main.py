from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Configuration CORS pour autoriser ton frontend (local et futur Vercel)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En production, tu pourras restreindre à ton URL Vercel
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Hello depuis FastAPI sur AWS ! 🚀"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}