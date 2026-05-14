"""FastAPI app entry point"""
from fastapi import FastAPI

app = FastAPI(title="My API", version="0.1.0")


@app.get("/")
def root():
    return {"message": "Hello World"}


@app.get("/health")
def health():
    return {"status": "ok"}
