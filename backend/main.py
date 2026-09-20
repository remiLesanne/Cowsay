from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

origins = [
    "http://localhost:3000",
    "https://cowsay-one.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    # MODIFICATION DE TEST : On change radicalement le message pour voir la différence
    return {
        "message": "🔥 TEST DEPLOYMENT AWS - LE CORS ET LE CODE SONT BIEN A JOUR ! 🔥",
        "version": "v2-debug"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}