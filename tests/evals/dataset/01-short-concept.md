# Vector Embeddings

A vector embedding is a numerical representation of a piece of data — a word, a
sentence, an image, or a document — as a fixed-length array of floating point
numbers. Embeddings place semantically similar items close together in a
high-dimensional space, so that distance between two vectors approximates the
similarity of the things they represent.

Embeddings are produced by an embedding model. For text, the model reads the
input and emits a dense vector (commonly 384 to 3072 dimensions). Two sentences
that mean roughly the same thing map to nearby vectors even when they share no
words, which is what makes embeddings far more powerful than keyword matching
for capturing meaning.

The typical use is similarity search: encode a query into a vector, then find
the stored vectors nearest to it (by cosine similarity or dot product). This is
the foundation of semantic search and of retrieval pipelines that feed context
to language models.
