FROM alpine:3.20 AS model

RUN apk add --no-cache ca-certificates curl
RUN mkdir -p /models && \
    curl -L --retry 8 --retry-delay 5 --speed-time 30 --speed-limit 1024 \
    https://huggingface.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf \
    -o /models/qwen-model.gguf

FROM ghcr.io/ggml-org/llama.cpp:server

COPY --from=model /models/qwen-model.gguf /models/qwen-model.gguf
