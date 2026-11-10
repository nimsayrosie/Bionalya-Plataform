<p align="center">
  <img src="imagens/banner-claro.png" alt="Bionalya — previsão de resistência bacteriana a partir do genoma, com aprendizado de máquina" width="820">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/status-prot%C3%B3tipo%20de%20pesquisa-301A4B?style=flat-square" alt="Status: protótipo de pesquisa">
  <img src="https://img.shields.io/badge/dados-NCBI%20Pathogen%20Detection-6DB1BF?style=flat-square" alt="Dados: NCBI Pathogen Detection">
  <img src="https://img.shields.io/badge/antibi%C3%B3ticos-6%20com%20modelo-3F6C51?style=flat-square" alt="6 antibióticos com modelo treinado">
  <img src="https://img.shields.io/badge/AUC%20no%20teste-0%2C994-3F6C51?style=flat-square" alt="AUC no teste: 0,994">
  <img src="https://img.shields.io/badge/acessibilidade-WCAG%20AA-F39A9D?style=flat-square" alt="Acessibilidade: WCAG AA">
</p>

---

Quando uma bactéria resiste ao antibiótico escolhido, o tratamento certo só começa
depois que o laboratório devolve o antibiograma — e isso costuma levar de 24 a 72 horas.
A **Bionalya** testa uma pergunta mais curta: dá para prever esse resultado olhando só
para os **genes de resistência** que apareceram no sequenciamento da bactéria?

Este repositório tem as duas metades do projeto: o **pipeline de dados e os modelos**
(notebook) e a **plataforma**, que hoje é um sistema funcional — API em FastAPI, seis
antibióticos com quatro modelos treinados cada, controle de acesso com três papéis e
importação de novas bases.

> [!WARNING]
> **Protótipo acadêmico, sem validação clínica.** Nada aqui é diagnóstico e nada
> substitui o antibiograma. Os modelos foram treinados com uma única espécie e podem
> errar — inclusive prevendo "sensível" para uma bactéria resistente.

---

## Como funciona

<p align="center">
  <img src="imagens/fluxo-claro.png" alt="Fluxo em quatro etapas: isolado sequenciado, matriz de presença e ausência de genes, treino separado por cluster genético, previsão explicada" width="900">
</p>

O passo que mais mudou o projeto foi o **3**. Numa primeira versão a separação entre
treino e teste era aleatória, e o modelo chegava a AUC 1,000 — bom demais para ser
verdade. O motivo: bactérias são clonais, então cópias quase idênticas do mesmo isolado
caíam dos dois lados e o modelo só precisava reconhecê-las. Trocando para separação por
**cluster genético** (`GroupShuffleSplit`, com `StratifiedGroupKFold` quando a divisão
degenera), o número caiu para o patamar honesto que está na tabela abaixo.

Um detalhe do passo **2** segue a mesma lógica: a frequência dos genes é contada
**só no conjunto de treino**. Olhar a frequência na base inteira para decidir quais
genes viram variáveis já é vazamento de informação do teste para o treino.

## Resultados

Espécie *Neisseria gonorrhoeae*, antibiótico ciprofloxacino, 728 isolados usáveis
(585 no treino, 143 no teste) e 58 genes como variáveis.

| Modelo | AUC | Sensibilidade | Especificidade | Falsos negativos |
|---|---|---|---|---|
| **Random Forest** | **0,994** | 98,9% | 96,4% | 1 de 88 |
| Regressão Logística | 0,990 | 98,9% | 96,4% | 1 de 88 |
| Redes Neurais | 0,985 | 98,9% | 89,1% | 1 de 88 |
| XGBoost | 0,981 | 98,9% | 96,4% | 1 de 88 |

A meta definida no início do projeto, a partir da literatura, era AUC de 0,85.
A validação cruzada em cinco repetições, sempre respeitando os clusters, ficou em
0,990 ± 0,006 — ou seja, o resultado não veio de uma divisão de sorte.

> Os três primeiros colocados ficam dentro de meio ponto percentual um do outro. A rede
> neural é a mais sensível à semente aleatória e oscila mais entre execuções; por isso a
> plataforma guarda os quatro modelos treinados e deixa escolher qual responde, em vez de
> apagar os perdedores.

O gene que mais pesa é o `gyrA_S91F` (36% da importância no Random Forest), seguido de
`gyrA_D95A` (15%) e `parC_S87R` (10%). Isso bate com a biologia: **gyrA** e **parC**
codificam as enzimas que o ciprofloxacino ataca, e mutações nelas são o mecanismo
conhecido de resistência a quinolonas. O modelo não inventou um atalho — ele encontrou
o mecanismo.

### Os seis antibióticos com modelo

| Antibiótico | Modelo escolhido | AUC | Isolados usáveis | Confiança |
|---|---|---|---|---|
| Ciprofloxacino | Random Forest | 0,994 | 728 | alta |
| Tetraciclina | Random Forest | 0,997 | 466 | média |
| Azitromicina | XGBoost | 0,945 | 692 | alta |
| Penicilina | Regressão Logística | 0,972 | 285 | baixa |
| Ceftriaxona | Regressão Logística | 1,000 | 788 | baixa |
| Cefixima | Random Forest | 0,642 | 750 | baixa |

A coluna de confiança não é enfeite. A ceftriaxona tem AUC 1,000 e mesmo assim é
**baixa confiança**: a base tem 775 isolados sensíveis e só 13 resistentes, então o
conjunto de teste fica com umas três resistentes e a métrica deixa de significar
desempenho. A plataforma detecta isso sozinha — menos de 10 isolados da classe
minoritária no teste dispara o alerta — e mostra o aviso na tela junto do resultado.

## A plataforma

| Modo claro | Modo escuro |
|---|---|
| <img src="imagens/tela-claro.png" alt="Página inicial da Bionalya em modo claro" width="420"> | <img src="imagens/tela-escuro.png" alt="Página inicial da Bionalya em modo escuro" width="420"> |

**No ar em <https://bionalya-uvqh.onrender.com>** (o primeiro acesso depois de um tempo parado
leva cerca de 1 minuto, porque o servidor grátis dorme).

São **16 telas** servidas por uma API em FastAPI. O que dá para fazer nelas:

- **Analisar um isolado** — marcar os genes de resistência e receber a probabilidade,
  o limiar aplicado e o peso de cada gene na decisão.
- **Escolher o modelo** — os quatro algoritmos ficam treinados e guardados para cada
  antibiótico. A equipe define qual responde por padrão e quem analisa pode trocar na hora.
- **Explorar a base** — buscar entre os isolados por antibiótico, fenótipo ou gene.
- **Treinar um antibiótico novo** — direto pela tela, a partir da base escolhida.
- **Trazer a própria base** — qualquer pesquisador envia um CSV do NCBI e usa na hora:
  não há fila de aprovação. Cada base treina os seus próprios modelos, e quem enviou
  treina os dela.
- **Avisos para a equipe** — importar base e treinar modelo não dependem de ninguém,
  então cada uma dessas ações vira um aviso no painel de quem acompanha.
- **Recuperar a senha** — quem esqueceu pede pela tela de login; a equipe recebe o
  pedido e um admin gera uma senha nova, que a pessoa troca ao entrar. Ainda sem
  link por e-mail.
- **Controle de acesso** — cadastro com aprovação manual e três papéis cumulativos
  (pesquisador, equipe, administrador).

A identidade usa cinco cores fixas (roxo `#301A4B`, azul `#6DB1BF`, rosa-claro
`#FFEAEC`, rosa `#F39A9D` e verde `#3F6C51`) e a fonte **Atkinson Hyperlegible**,
desenhada pelo Braille Institute para baixa visão. Todo texto passa no mínimo de
4,5:1 da WCAG AA nos dois modos.

### Arquitetura

<p align="center">
  <img src="imagens/diagrama-componentes.png" alt="Diagrama de componentes: cliente web, camada de API, camada de domínio e armazenamento" width="900">
</p>

O cliente nunca alcança o banco nem os arquivos de modelo: tudo passa pela API, que é o
único lugar onde a permissão é verificada. E o módulo que treina não conversa com o que
prevê — o primeiro escreve os arquivos em `modelos/`, o segundo os lê.

Os detalhes de cada decisão, a lista de rotas e o passo a passo da hospedagem estão em
[`plataforma/README.md`](plataforma/README.md).

## Estrutura

```
dados/                        base de dados de isolados
  amostra-neisseria-gonorrhoeae.csv    os 794 isolados com antibiograma (versionada)
  neisseria-gonorrheae.csv             a base completa, 32 MB (não versionada)
dados_algoritmos.ipynb        caderno de análise exploratória e treinamento inicial
docs/
  banco-e-hospedagem.md       onde ficam os dados, o que é grátis, o que tem prazo, Neon + Render
imagens/                      logotipo, capturas de tela e diagramas da documentação
plataforma/                   a aplicação
  api/
    main.py                   as rotas da API
    treino.py                 pipeline: rótulos, features, separação por cluster, 4 modelos
    modelos.py                carrega os modelos salvos e responde a previsão
    banco.py                  esquema do banco (Postgres ou SQLite) e migração automática
    arquivos.py               guarda CSVs e modelos no banco, para sobreviverem ao reinício
    seguranca.py              resumo criptográfico de senha
    config.py                 caminhos, limites e nomes em português
  web/                        as 16 telas, o CSS, o tema e o cliente da API
  modelos/<base>/             um .joblib e um .json por antibiótico de cada base
  Dockerfile                  empacotamento para publicação
  requirements.txt            dependências com versão fixada
  README.md                   instruções de instalação, execução e publicação
bionalya/                     primeira versão das telas, mantida como registro
render.yaml                   configuração da hospedagem
```

## Como rodar

### A plataforma

Não precisa baixar nada: o repositório já traz a amostra da base e os modelos treinados.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -r plataforma/requirements.txt

cd plataforma
python -m uvicorn api.main:app --reload
```

Abra <http://127.0.0.1:8000>. A documentação da API, gerada sozinha, fica em
<http://127.0.0.1:8000/docs>.

Na primeira vez que sobe, a API cria a conta de administrador com senha aleatória e
grava as credenciais em `plataforma/PRIMEIRO-ACESSO.txt`, que não é versionado.

> **Por que `python -m` e não só `uvicorn`:** no Windows o `uvicorn.exe` costuma ser
> instalado numa pasta que não está no PATH. O `python -m` chama o pacote direto.

### O notebook

Para refazer a análise do zero, baixe a base completa em
[NCBI Pathogen Detection](https://www.ncbi.nlm.nih.gov/pathogens/) — escolha
*Neisseria gonorrhoeae*, baixe o CSV de isolados e salve como
`dados/neisseria-gonorrheae.csv`. Depois abra `dados_algoritmos.ipynb` e execute os
blocos em ordem; eles param com uma mensagem clara se a coluna esperada não existir.

### Hospedar

O repositório traz `Dockerfile` e `render.yaml` prontos. Em
[dashboard.render.com](https://dashboard.render.com), **New → Blueprint**, apontando
para este repositório, monta o serviço sozinho no plano gratuito. O passo a passo
completo e as variáveis de ambiente estão em
[`plataforma/README.md`](plataforma/README.md).

O servidor grátis do Render apaga o próprio disco a cada reinício e a cada vez que dorme
(15 minutos sem acesso). Por isso os dados ficam num **PostgreSQL grátis e sem prazo no
[Neon](https://neon.com)**: crie o banco lá antes (leva dois minutos, sem cartão) e cole
o endereço dele quando o Render pedir a variável `DATABASE_URL`. **Nada disso é pago.**
O que é grátis, o que tem prazo e o passo a passo estão em
[`docs/banco-e-hospedagem.md`](docs/banco-e-hospedagem.md).

| Peça | Onde | Custo | Prazo |
|---|---|---|---|
| Servidor (API e telas) | Render, plano grátis | nenhum | nenhum |
| Banco (usuários, bases, modelos treinados) | Neon, plano grátis | nenhum | nenhum |
| Na sua máquina | `plataforma/bionalya.db` (SQLite) | nenhum | nenhum |

## Limites conhecidos

- **Uma espécie.** Os modelos de fábrica são todos de *N. gonorrhoeae*. A importação de
  base permite trazer outras, mas isso ainda não foi testado com espécie diferente.
- **Antibiograma ausente é o gargalo.** Dos 72.503 isolados da base, só 794 têm
  resultado de laboratório registrado. O limite do projeto é esse, não o modelo.
- **Antibiótico fácil e antibiótico difícil.** O ciprofloxacino depende de poucas
  mutações bem conhecidas. Mecanismos multifatoriais são bem mais difíceis — a cefixima,
  com AUC 0,642, mostra exatamente isso.
- **1 GB de banco na hospedagem.** Os dados ficam num PostgreSQL grátis e sem prazo
  (Neon) e sobrevivem ao reinício, mas o espaço é de 1 GB, e os CSVs enviados ocupam
  esse espaço. Detalhes em [`docs/banco-e-hospedagem.md`](docs/banco-e-hospedagem.md).
- **Sem log de previsões.** Deixado de fora de propósito: gravar consulta associada a
  usuário é tratamento de dado pessoal e pede base legal e prazo de retenção definidos.
- **Licença ainda não definida.** Enquanto isso, trate como trabalho acadêmico.

## Equipe

Projeto Interdisciplinar I — Ciência da Computação, Centro Universitário Dom Helder.

| Integrante | Frente |
|---|---|
| Yasmin Lourdes e Silva | Dados, modelos de machine learning e identidade visual |
| Christian Ottero Marques | Scrum Master (gestão do processo) e testes |
| Maria Eduarda Souza Maia | Interface e front-end |
| André Vieira Prado | Desenvolvedor back-end e banco de dados |
| Gabriel Medeiros de Souza | Product Owner (requisitos e backlog) |

## Referências

- NCBI Pathogen Detection — <https://www.ncbi.nlm.nih.gov/pathogens/>
- GBD 2021 Antimicrobial Resistance Collaborators. *Global burden of bacterial
  antimicrobial resistance 1990–2021.* The Lancet, 2024. (4,7 milhões de mortes
  associadas à resistência em 2021)
- Revisão de aprendizado de máquina aplicado à previsão de resistência antimicrobiana.
  *PeerJ*, 2024. <https://doi.org/10.7717/peerj.18213>
  (desempenho relatado na literatura: Random Forest 0,89, XGBoost 0,87, Regressão Logística 0,87)
