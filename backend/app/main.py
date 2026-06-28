from fastapi import FastAPI
from pydantic import BaseModel

from services.llm import ask_llm

app = FastAPI(
    title="Rabeeh AI Agent Pro",
    version="1.0.0"
)


class ChatRequest(BaseModel):
    message: str


@app.get("/")
async def home():
    return {"message": "Rabeeh AI Agent Pro Running 🚀"}


@app.post("/chat")
async def chat(req: ChatRequest):
    answer = ask_llm(req.message)
    return {
        "response": answer
    }