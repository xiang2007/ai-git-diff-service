from unidiff.patch import PatchedFile, PatchSet


CHUNK_BYTES = 65_536

PatchChunk = list[PatchedFile]

def chunk_patch(patch: PatchSet, max_bytes: int = CHUNK_BYTES) -> list[PatchChunk]:
    chunks: list[PatchChunk] = []
    currentChunks : PatchChunk = []
    currentSize = 0
    fileSize = 0

    for patchedFiles in patch:
        fileSize = len(str(patchedFiles).encode("utf-8"))
        if currentChunks and currentSize + fileSize > max_bytes:
            chunks.append(currentChunks)
            currentChunks = []
            currentSize = 0
        currentChunks.append(patchedFiles)
        currentSize += fileSize
    if currentChunks:
        chunks.append(currentChunks)
    return chunks