"""
RAG Step 2 – Knowledge Base Retrieval
Uses TF-IDF + cosine similarity to find the most relevant KB articles.
"""

import json
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class KnowledgeRetriever:
    """Loads the banking KB JSON and retrieves top-K relevant documents."""

    def __init__(self, kb_path: str):
        with open(kb_path, "r", encoding="utf-8") as f:
            kb_data = json.load(f)

        self.documents = kb_data.get("entries", [])

        # Build corpus: title + content for each document
        texts = [
            doc["title"] + " " + doc["content"]
            for doc in self.documents
        ]

        self.vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
        self.doc_vectors = self.vectorizer.fit_transform(texts)

    def search(self, query: str, top_k: int = 3, min_score: float = 0.05):
        """
        Return top_k documents most relevant to the query.

        Parameters
        ----------
        query     : search string (usually ticket title + description)
        top_k     : maximum results to return
        min_score : minimum cosine similarity threshold

        Returns
        -------
        list of dicts with id, title, category, content, score
        """
        query_vector = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vector, self.doc_vectors)[0]

        query_lower = query.lower()
        is_fraud_query = any(w in query_lower for w in ["scam", "fraud", "fake", "impersonat", "stolen", "unauthorized", "cheat", "hacked", "cyber"])

        scored_docs = []
        for idx in range(len(self.documents)):
            score = float(scores[idx])
            doc = self.documents[idx]
            cat = doc.get("category", "")
            
            # Smart domain weight adjustment
            if not is_fraud_query and cat in ["Social Engineering", "Fraud & Security", "Malware / Remote Access", "Account Takeover"]:
                # Suppress fraud scam advisories when user has a regular procedural/login issue
                score *= 0.72
            elif not is_fraud_query and (cat in ["Password/Login Issue", "Digital Banking", "Account Maintenance"] or "reset" in doc["title"].lower()):
                # Boost legitimate procedural resolution guides
                score *= 1.25
            elif is_fraud_query and cat in ["Social Engineering", "Fraud & Security", "Account Takeover"]:
                # Boost fraud resolution guides for fraud reports
                score *= 1.20

            if score >= min_score:
                scored_docs.append({
                    "id":       doc["id"],
                    "title":    doc["title"],
                    "category": cat,
                    "content":  doc["content"],
                    "score":    round(score, 4),
                })

        # Sort by adjusted relevance score
        scored_docs.sort(key=lambda d: d["score"], reverse=True)
        return scored_docs[:top_k]
