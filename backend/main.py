from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

app = FastAPI()

# 1. Le middleware CORS DOIT être ajouté en premier
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

# 2. Ensuite seulement, les routes
@app.options("/")
def options_root():
    return Response(status_code=200)

@app.get("/")
def read_root():
    return {
        "message": "🔥 TEST DEPLOYMENT AWS - LE CORS ET LE CODE SONT BIEN A JOUR ! 🔥",
        "version": "v3-debug"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}