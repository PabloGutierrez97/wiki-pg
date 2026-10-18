"""IA local de la wiki (Ollama + RAG).

- ollama:    cliente HTTP mínimo (generar, generar en streaming, embeddings).
- rag:       troceado e indexado de artículos y búsqueda semántica.
- filtros:   lo que se decide sin modelo (identidad, fuera de tema, respuestas fijas).
- prompts:   construcción de los prompts de sistema.
- mensajes:  textos fijos que ve el visitante.
- servicio:  el flujo completo de una pregunta, con límites y caché.
"""
