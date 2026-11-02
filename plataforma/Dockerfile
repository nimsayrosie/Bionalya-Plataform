# Bionalya — imagem da plataforma.
#
# Serve para rodar em qualquer lugar que aceite Docker (Render, Railway, Fly,
# uma máquina da faculdade). Na sua máquina você não precisa dela: lá é só
#   pip install -r requirements.txt  &&  python -m uvicorn api.main:app --reload
#
# O contexto do build é a RAIZ DO REPOSITÓRIO, não a pasta plataforma/, porque
# a base de dados mora em dados/ — um nível acima.
#   docker build -t bionalya .
#   docker run -p 8000:8000 bionalya

FROM python:3.12-slim

# PYTHONUNBUFFERED: o log aparece na hora no painel da hospedagem, sem ficar
# preso no buffer. PIP_NO_CACHE_DIR: imagem menor.
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libgomp1: o XGBoost precisa dela para o OpenMP. Sem isso a importação quebra.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# As dependências primeiro, sozinhas: enquanto o requirements.txt não mudar,
# o Docker reaproveita esta camada e o build seguinte leva segundos.
COPY plataforma/requirements.txt ./plataforma/requirements.txt
RUN pip install -r plataforma/requirements.txt

# Agora o código, os modelos treinados e a base.
COPY plataforma/ ./plataforma/
COPY dados/ ./dados/

WORKDIR /app/plataforma

# A hospedagem escolhe a porta e manda em $PORT; 8000 é o padrão local.
ENV PORT=8000
EXPOSE 8000

# Sem --reload: em produção ele só gasta memória vigiando arquivo.
CMD ["sh", "-c", "python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
