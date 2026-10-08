import unittest
from semantic_index import SemanticDocument, TfidfIndex, hybrid_search, lexical_scores, tokenize


class SemanticIndexTests(unittest.TestCase):
    def setUp(self):
        self.documents = [
            SemanticDocument("a", "The revenue increased after the pricing change", start_seconds=10),
            SemanticDocument("b", "The dashboard shows customer retention metrics", start_seconds=20),
            SemanticDocument("c", "A motorcycle travels through the city", start_seconds=30),
        ]

    def test_tokenize_removes_stopwords(self):
        self.assertEqual(tokenize("The revenue is growing"), ["revenue", "growing"])

    def test_tfidf_prefers_relevant_document(self):
        scores = TfidfIndex(self.documents).semantic_scores("revenue pricing")
        self.assertGreater(scores[0], scores[1])
        self.assertGreater(scores[0], scores[2])

    def test_lexical_scores(self):
        scores = lexical_scores(self.documents, "customer retention")
        self.assertEqual(max(range(len(scores)), key=scores.__getitem__), 1)

    def test_hybrid_ranking_and_components(self):
        results = hybrid_search(self.documents, "revenue pricing", top_k=2, semantic_weight=0.7)
        self.assertEqual(results[0].document_id, "a")
        self.assertGreaterEqual(results[0].semantic_score, 0)
        self.assertGreaterEqual(results[0].lexical_score, 0)
        self.assertGreater(results[0].score, results[1].score)

    def test_empty_query(self):
        self.assertEqual(hybrid_search(self.documents, ""), [])

    def test_weight_is_bounded(self):
        results = hybrid_search(self.documents, "revenue", semantic_weight=4)
        self.assertEqual(results[0].document_id, "a")


if __name__ == "__main__":
    unittest.main()
