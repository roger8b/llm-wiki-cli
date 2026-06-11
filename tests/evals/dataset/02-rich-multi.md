# Building a Retrieval-Augmented Generation System

Retrieval-Augmented Generation (RAG) is an architecture that grounds a language
model's answers in an external knowledge base instead of relying solely on the
model's parameters. At query time the system retrieves relevant passages and
passes them to the model as context, which reduces hallucination and lets the
answer cite sources. RAG combines several distinct components.

## Embeddings

An embedding model converts text into dense vectors so that semantically
similar passages land near each other. Good retrieval starts with a good
embedding model; the rest of the pipeline depends on the quality of these
vectors.

## Vector Database

A vector database stores embeddings and answers nearest-neighbour queries
efficiently, often with an approximate index such as HNSW or IVF. It is the
storage and search engine of a RAG system, returning the candidate passages for
a query.

## Chunking

Chunking is the process of splitting source documents into passages small enough
to embed and retrieve precisely, but large enough to remain meaningful. Chunk
size and overlap are tuning knobs that strongly affect retrieval quality.

## Reranking

A reranker is a second-stage model that re-scores the candidate passages
returned by the vector database, ordering them by true relevance to the query.
Reranking trades extra latency for higher precision in the passages that finally
reach the language model.

## Putting It Together

A request flows through chunking at index time, then embeddings, then the vector
database, then reranking at query time, and finally the language model. Each
component is independently swappable, which is why teams treat them as separate
concepts.
