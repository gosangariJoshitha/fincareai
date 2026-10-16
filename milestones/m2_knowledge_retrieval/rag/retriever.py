
"""
RAG Step 2 – Knowledge Base Retrieval
Temporary fallback: TF-IDF-style ranking using Python only.
No scikit-learn or scipy required.
"""

import json
import math
import re
from collections import Counter


STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "to", "of",
    "in", "on", "for", "and", "or", "my", "i", "me", "it",
    "this", "that", "with", "be", "been", "have", "has", "do",
    "does", "not", "but", "when", "what", "how", "can", "could"
}


def tokenize(text):
    words = re.findall(r"[a-zA-Z0-9]+", str(text).lower())
    return [word for word in words if word not in STOP_WORDS]


class KnowledgeRetriever:
    """Loads the complete KB and ranks relevant documents."""

    def __init__(self, kb_path: str):
        with open(kb_path, "r", encoding="utf-8") as f:
            kb_data = json.load(f)

        self.documents = kb_data.get("entries", [])

        # Keep the full knowledge corpus, independent of UI pagination.
        self.texts = [
            str(doc.get("title", "")) + " " +
            str(doc.get("content", ""))
            for doc in self.documents
        ]

        self.tokens = [tokenize(text) for text in self.texts]
        self.doc_count = len(self.documents)

        # Calculate IDF values for each term.
        document_frequency = Counter()
        for words in self.tokens:
            document_frequency.update(set(words))

        self.idf = {
            word: math.log((1 + self.doc_count) /
                           (1 + frequency)) + 1
            for word, frequency in document_frequency.items()
        }

        self.doc_vectors = [
            self._make_vector(words) for words in self.tokens
        ]

    def _make_vector(self, words):
        counts = Counter(words)
        total = len(words) or 1

        return {
            word: (count / total) * self.idf.get(word, 0)
            for word, count in counts.items()
        }

    @staticmethod
    def _cosine_similarity(vector_a, vector_b):
        if not vector_a or not vector_b:
            return 0.0

        common = set(vector_a) & set(vector_b)
        dot = sum(vector_a[word] * vector_b[word] for word in common)

        norm_a = math.sqrt(sum(value * value for value in vector_a.values()))
        norm_b = math.sqrt(sum(value * value for value in vector_b.values()))

        if not norm_a or not norm_b:
            return 0.0

        return dot / (norm_a * norm_b)

    def search(self, query: str, top_k: int = 3, min_score: float = 0.05):
        """Return the top relevant knowledge articles."""

        query_vector = self._make_vector(tokenize(query))
        query_lower = query.lower()

        fraud_words = [
            "scam", "fraud", "fake", "impersonat", "stolen",
            "unauthorized", "cheat", "hacked", "cyber"
        ]
        is_fraud_query = any(word in query_lower for word in fraud_words)

        scored_docs = []

        for idx, doc in enumerate(self.documents):
            score = self._cosine_similarity(
                query_vector, self.doc_vectors[idx]
            )
            category = doc.get("category", "")
            title = str(doc.get("title", "")).lower()

            if not is_fraud_query and category in [
                "Social Engineering", "Fraud & Security",
                "Malware / Remote Access", "Account Takeover"
            ]:
                score *= 0.72
            elif not is_fraud_query and (
                category in [
                    "Password/Login Issue", "Digital Banking",
                    "Account Maintenance"
                ] or "reset" in title
            ):
                score *= 1.25
            elif is_fraud_query and category in [
                "Social Engineering", "Fraud & Security",
                "Account Takeover"
            ]:
                score *= 1.20

            if score >= min_score:
                scored_docs.append({
                    "id": doc.get("id", ""),
                    "title": doc.get("title", ""),
                    "category": category,
                    "content": doc.get("content", ""),
                    "score": round(score, 4),
                })

        scored_docs.sort(
            key=lambda item: item["score"], reverse=True
        )
        return scored_docs[:max(0, top_k)]