from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://cowsay-one.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route explicite pour capturer les requêtes OPTIONS de preflight sur la racine
@app.options("/")
options_root = lambda: Response(status_code=200)

@app.get("/")
def read_root():
    return {
        "message": "🔥 TEST DEPLOYMENT AWS - LE CORS ET LE CODE SONT BIEN A JOUR ! 🔥",
        "version": "v2-debug"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}