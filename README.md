# CyberSec Quiz Generator (RAG)

Hey there! Our cybersec RAG project (for cybersec noobies... or if you're an expert that's fine as well) will ingest cybersecurity study materials (PDF/TXT), and generate interactive multiple choice quizzes with explanations powered by... well.. RAG.

## How it works

1. Upload study materials (PDF or text)
2. Documents get chunked and embedded (ChromaDB handles embedding with MiniLM internally)
3. When you request a quiz, hybrid search (semantic + BM25 keyword) finds relevant chunks using Reciprocal Rank Fusion (so we don't miss the keywords but also capture the bigger idea)
4. Retrieved context goes to the LLM which generates quiz questions with explanations
5. Take the quiz and get scored! 

## Setup

```bash
# install dependencies
uv sync

# set up api key
echo "DUKE_API_KEY=your_actual_key_here" > .env


# run
uv run streamlit run app.py
```

### Docker
```bash
docker build -t cybersec-quiz .
docker run --env-file .env -p 8501:8501 cybersec-quiz (this connects your local 8501 port to the containers 8501 port)
```

## AI Citation
App scaffolding drafted with Claude Sonnet 5 via Claude Code Assistant on 09/07/2026 at 4:55 PM EST.

Since claude code chats are local jsons and can't be shared, here are the screenshots.
https://drive.google.com/drive/folders/1BhWHL2m5BKwpO7tlVkxD5e3FP8f7AH-Q?usp=share_link