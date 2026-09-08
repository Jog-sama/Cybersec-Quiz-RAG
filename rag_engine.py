import os
import json
import streamlit as st
import chromadb
import pymupdf
from dotenv import load_dotenv
from openai import OpenAI
from rank_bm25 import BM25Okapi

load_dotenv()


# loading the key here (duke gateway was glitching so temporarily used my own openai key)
# FIX THIS LATER OR ASK PROF !!!

API_KEY = os.getenv("DUKE_API_KEY", "")

# to use the duke api key when i get access 
if API_KEY.startswith("sk-"):
    BASE_URL = "https://api.openai.com/v1"
    LLM_MODEL = os.getenv("MODEL_NAME", "gpt-4o-mini")
else:
    BASE_URL = "https://litellm.oit.duke.edu/v1"
    LLM_MODEL = os.getenv("MODEL_NAME", "duke-current")


# parsing pdfs and extracting raw text
def extract_text(uploaded_file):
    raw = uploaded_file.read()
    name = uploaded_file.name.lower()

    if name.endswith(".pdf"):
        #pymupdf is goated
        doc = pymupdf.open(stream=raw, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    else:
        # for regular text files, just decoding the binaries 
        return raw.decode("utf-8", errors="ignore")



# chunking - 500 characters per chunk is a sweet middleground 
# overlapping chunks so we dont lose context at chunk boundaries

def make_chunks(text, chunk_size=500, overlap=50):
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            # look for period or newline
            break_at = text.rfind(". ", start + chunk_size // 2, end)
            if break_at == -1:
                break_at = text.rfind("\n", start + chunk_size // 2, end)
            if break_at != -1:
                end = break_at + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # sliding the window forward for overlapping
        start = end - overlap
        if start >= len(text):
            break

    return chunks


# using chromaDB as our vector db . chromadb is already very lightweight plus has its own MiniLM embedding for semantic searching 

def get_chroma():
    if "chroma_col" not in st.session_state:
        #persistent client for chromadb so it survives app reloads
        client = chromadb.PersistentClient(path="chroma_data")
        st.session_state.chroma_client = client

        #cosine searching for semantic similarity search
        st.session_state.chroma_col = client.get_or_create_collection(
            name="cybersec_docs",
            metadata={"hnsw:space": "cosine"},
        )
    return st.session_state.chroma_col


def store_chunks_in_db(chunks, source_name):
    # taking the list of embeddings and storing to chromadb (handled by its built-in model)
    col = get_chroma()
    #unique id for each chunk
    ids = [f"{source_name}_chunk_{i}" for i in range(len(chunks))]
    #just adding some meta data so we know the source for each chunk
    metadatas = [{"source": source_name} for _ in chunks]

    #appending onto chroma db
    col.upsert(ids=ids, documents=chunks, metadatas=metadatas)

    return len(chunks)


# search (semantic + similarity)
# semantic is for captureing the meaning whereas keyword is so we don't miss specific stuff

# then we fuse them with reciprocal rank
# fusion to get the best of both worlds :)

def semantic_search(query, top_k=10):
    #using cosine similarity, ofcourse
    col = get_chroma()
    if col.count() == 0:
        return []

    n = min(top_k, col.count())
    results = col.query(query_texts=[query], n_results=n)

    docs = []
    for i in range(len(results["ids"][0])):
        docs.append({
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
        })
    return docs


def keyword_search(query, top_k=10):
    # using bm25
    col = get_chroma()
    if col.count() == 0:
        return []

    all_docs = col.get()
    if not all_docs["documents"]:
        return []

    tokenized_docs = [doc.lower().split() for doc in all_docs["documents"]]
    bm25 = BM25Okapi(tokenized_docs)

    #scoring every doc against our query
    query_tokens = query.lower().split()
    scores = bm25.get_scores(query_tokens)

    # sorting the most relevant docs with hightest scores
    scored = list(zip(all_docs["ids"], all_docs["documents"], scores))
    scored.sort(key=lambda x: x[2], reverse=True)

    #formatting results in the same structure as our semantic one
    docs = []
    for doc_id, doc_text, score in scored[:top_k]:
        docs.append({"id": doc_id, "text": doc_text})
    return docs


# reciprocal rank fusion (takes the rank of each doc and uses the following formula to calulate a hybrid final rank)
# formula: score = sum(1 / (k + rank))


def reciprocal_rank_fusion(semantic_results, keyword_results, k=60):
    # k is just a smoothing funciton
    rrf_scores = {}
    doc_map = {}
    # for semantic serch
    for rank, doc in enumerate(semantic_results):
        doc_id = doc["id"]
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (k + rank)
        doc_map[doc_id] = doc
    # for keyword search
    for rank, doc in enumerate(keyword_results):
        doc_id = doc["id"]
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (k + rank)
        doc_map[doc_id] = doc

    #sorting combined rrf scores
    ranked_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)
    return [doc_map[did] for did in ranked_ids]


def hybrid_search(query, top_k=10):
    # runs both the searches and calls the methods and returns the top k relevant chunks (using hybrid scoring)
    sem_results = semantic_search(query, top_k)
    kw_results = keyword_search(query, top_k)
    fused = reciprocal_rank_fusion(sem_results, kw_results)
    return fused[:top_k]


# QUIZ GENERATION
# this is the RAG part. we take the retrieved
# chunks as context, build a prompt, send it
# to the llm, and parse the quiz json back

def generate_quiz(topic, num_q=5):

    chunks = hybrid_search(topic)
    if not chunks:
        raise ValueError("no documents found, upload something first")

    context = "\n\n---\n\n".join(c["text"] for c in chunks)

    sys_msg = """You are a cybersecurity instructor creating a quiz for students.
Based on the provided study material, generate multiple choice questions.
Each question has exactly 4 options (A, B, C, D), one correct answer, and a brief explanation.
Make questions that test understanding, not just memorization.
Respond with ONLY valid JSON in this exact format, no other text:
{"questions": [{"question": "...", "options": {"A": "...", "B": "...", "C": "...", "D": "..."}, "correct": "A", "explanation": "..."}]}"""

    user_msg = f"Study Material:\n{context}\n\nGenerate exactly {num_q} questions about: {topic}\nRespond ONLY with JSON."

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=120.0)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.7,
        max_tokens=4000, #optimal settign after experimentation
    )

    raw = resp.choices[0].message.content.strip()

    #noticed that sometimes the response was being wrapped in markdown text. stripping the excess stuff if there.
    if raw.startswith("```json"):
        raw = raw[7:]
    if raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start_idx = raw.find("{")
        end_idx = raw.rfind("}") + 1
        if start_idx != -1 and end_idx > start_idx:
            return json.loads(raw[start_idx:end_idx])
        raise ValueError("couldnt parse quiz json from model response")



# GRADING
# compare user answers to correct answers

def grade_quiz(questions, user_answers):
    correct_count = 0
    for i, q in enumerate(questions):
        if user_answers.get(i) == q["correct"]:
            correct_count += 1

    score = correct_count / len(questions) * 100 if questions else 0
    return {"score": score, "correct": correct_count, "total": len(questions)}
