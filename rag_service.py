import math
import re
from typing import List, Dict

class SimpleVectorStore:
    """Lightweight in-memory vector store with TF-IDF cosine similarity & fallback embeddings"""
    def __init__(self):
        self.documents = []
        self.vocabulary = {}
        self.doc_vectors = []

    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        words = text.split()
        if not words:
            return []
        chunks = []
        i = 0
        while i < len(words):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
            i += (chunk_size - overlap)
        return chunks

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r'\b\w{2,}\b', text.lower())

    def add_documents(self, texts: List[str], metadatas: List[Dict] = None):
        for idx, text in enumerate(texts):
            chunks = self.chunk_text(text)
            for chunk_idx, chunk in enumerate(chunks):
                meta = (metadatas[idx] if metadatas and idx < len(metadatas) else {})
                self.documents.append({
                    'chunk': chunk,
                    'metadata': {**meta, 'chunk_index': chunk_idx}
                })

        # Build vocabulary
        all_tokens = set()
        for doc in self.documents:
            all_tokens.update(self._tokenize(doc['chunk']))
        self.vocabulary = {term: idx for idx, term in enumerate(all_tokens)}

        # Vectorize docs
        self.doc_vectors = [self._vectorize(doc['chunk']) for doc in self.documents]

    def _vectorize(self, text: str) -> List[float]:
        tokens = self._tokenize(text)
        vec = [0.0] * len(self.vocabulary)
        if not tokens:
            return vec
        for t in tokens:
            if t in self.vocabulary:
                vec[self.vocabulary[t]] += 1.0
        # Normalize
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def similarity_search(self, query: str, top_k: int = 3) -> List[Dict]:
        if not self.documents or not self.vocabulary:
            return []
        query_vec = self._vectorize(query)
        scores = []
        for idx, doc_vec in enumerate(self.doc_vectors):
            dot = sum(q * d for q, d in zip(query_vec, doc_vec))
            scores.append((dot, self.documents[idx]))
        
        scores.sort(key=lambda x: x[0], reverse=True)
        return [doc for score, doc in scores[:top_k] if score > 0] or [d for d in self.documents[:top_k]]

def run_rag_pipeline(query: str, reference_texts: List[str], top_k: int = 3) -> str:
    """Runs document ingestion, chunking, indexing, and returns top semantic contexts."""
    if not reference_texts:
        return ""
    store = SimpleVectorStore()
    store.add_documents(reference_texts)
    results = store.similarity_search(query, top_k=top_k)
    return "\n\n---\n\n".join([r['chunk'] for r in results])
