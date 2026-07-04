"""
Lightweight stemming utility for keyword-based matching (MCP tool routing,
policy/knowledge lookup).

This is intentionally NOT used on the pgvector semantic search path -
embeddings already generalize across word forms far better than stemming
does. It's only for the naive keyword/substring matching in mcp_server,
which otherwise misses things like "leaves"/"leaving" vs. "leave", or
"policies" vs. "policy".

Uses nltk's PorterStemmer, which is a pure algorithmic stemmer requiring no
downloaded corpora (unlike nltk's tokenizers), so no `nltk.download(...)`
step is needed.
"""
from nltk.stem import PorterStemmer

_stemmer = PorterStemmer()
_PUNCT = ".,!?;:()[]{}\"'"


def stem_word(word: str) -> str:
    return _stemmer.stem(word.strip(_PUNCT).lower())


def stem_text(text: str) -> str:
    """Lowercase + stem every whitespace-separated token."""
    return " ".join(stem_word(t) for t in text.split() if t.strip(_PUNCT))


def stem_tokens(text: str) -> set:
    """Stemmed token set, handy for `stem in stem_tokens(query)` membership checks."""
    return set(stem_text(text).split())