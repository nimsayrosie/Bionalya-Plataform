# Bionalya — plataforma

Previsão de resistência bacteriana a antibióticos a partir dos genes encontrados no
sequenciamento. Treze telas, uma API em FastAPI e seis antibióticos com quatro modelos
treinados cada. A base de *Neisseria gonorrhoeae* vem junto, e dá para importar outras.

> **Protótipo acadêmico, sem validação clínica.** Nada aqui é diagnóstico e nada
> substitui o antibiograma.

## Como rodar

**1. A base.** O repositório já traz `dados/amostra-neisseria-gonorrhoeae.csv`: são os
**794 isolados que têm antibiograma**, que é tudo de que os modelos precisam. Com ela a
plataforma funciona logo depois do clone, sem baixar nada.

A base completa (72.503 isolados, 32 MB) não é versionada, e só muda o que aparece na
tela *Explorar a base* — os modelos são os mesmos. Se quiser: em
[NCBI Pathogen Detection](https://www.ncbi.nlm.nih.gov/pathogens/) escolha
*Neisseria gonorrhoeae*, baixe o CSV de isolados e salve como
`dados/neisseria-gonorrheae.csv`, na raiz do repositório. Existindo, ela ganha da amostra
automaticamente.

**2. Instalar as dependências.**

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -r plataforma/requirements.txt
```

**3. Subir a plataforma.**

```bash
cd plataforma
python -m uvicorn api.main:app --reload
```

> **Por que `python -m` e não só `uvicorn`:** no Windows o `uvicorn.exe` costuma ser
> instalado em `AppData\Roaming\Python\PythonXXX\Scripts`, que não está no PATH por
> padrão — o próprio pip avisa isso no meio da instalação. O `python -m` chama o pacote
> direto e não depende do PATH. Se você criou o ambiente virtual do passo 2 e ativou,
> o comando curto também funciona.

Abra <http://127.0.0.1:8000>. A documentação da API, gerada sozinha, fica em
<http://127.0.0.1:8000/docs>.

**4. Primeiro acesso.** Na primeira vez que sobe, a API cria a conta de **admin** com
senha aleatória e grava as credenciais em `plataforma/PRIMEIRO-ACESSO.txt`. Esse arquivo
está no `.gitignore` e a senha não existe em lugar nenhum do repositório. Entre com ela,
**troque em "Minha conta"** (a tela avisa enquanto você estiver usando a senha inicial),
e use essa conta para liberar os cadastros e distribuir os papéis.

### Compartilhar o acesso com alguém

Duas formas, ambas na conta de admin:

- **Tela Usuários → "Criar um acesso para compartilhar".** A conta já nasce aprovada,
  sem a pessoa precisar se cadastrar e esperar liberação. Deixando a senha em branco, a
  plataforma sorteia uma e mostra **uma única vez** — depois disso nem você consegue ler,
  porque o banco só guarda o hash. É o caminho para a banca e para o orientador.
- **Cadastro comum.** A pessoa se cadastra em `cadastro.html`, fica em análise e alguém
  da equipe libera na tela *Acessos*.

Para uma hospedagem onde o banco se perde a cada reinício, há um terceiro caminho: as
variáveis `BIONALYA_DEMO_EMAIL` e `BIONALYA_DEMO_SENHA` criam, toda vez que a API sobe,
uma conta aberta de demonstração — um pesquisador comum, que analisa e consulta mas não
libera acesso, não treina modelo e não importa base.

### Atualizando uma versão anterior

Não precisa apagar o `bionalya.db`. Ao subir, a API compara o banco com o código e
acrescenta sozinha as colunas que faltam, preenchendo as linhas antigas com o padrão —
você vê no terminal um `Banco atualizado — colunas acrescentadas: ...`. Os usuários já
cadastrados continuam lá. Se o banco for de quando só existiam dois papéis, a conta que
era da equipe é promovida a admin e mantém a mesma senha.

A migração só sabe **acrescentar** coluna, que é o que o SQLite permite com
`ALTER TABLE`. Remover ou mudar o tipo de uma coluna pede migração de verdade; se um dia
o projeto precisar disso, vale trazer o Alembic.

## Os três papéis

| Papel | Pode |
|---|---|
| **pesquisador** | Analisar isolados, ver os modelos e explorar a base |
| **equipe** | tudo acima + liberar cadastros, treinar modelos, definir o modelo padrão |
| **admin** | tudo acima + mudar papéis e ativar/desativar contas |

São cumulativos: quem é admin pode tudo que a equipe pode. Promover alguém já libera o
acesso dessa pessoa. Desativar uma conta derruba as sessões abertas dela na hora. A
plataforma impede que você rebaixe ou desative a si mesmo, e que o sistema fique sem
nenhum admin ativo.

## Como está organizado

```
plataforma/
  api/
    main.py       as rotas
    treino.py     o pipeline: rótulos, features, split por cluster, 4 modelos
    modelos.py    carrega os .joblib e responde a previsão
    banco.py      SQLite: usuários, sessões, antibióticos
    seguranca.py  hash de senha
    config.py     caminhos e nomes em português
  modelos/
    <base>/       um .joblib + um .json por antibiótico daquela base
  web/            as telas, o style.css, o tema.js e o app.js
    inicio.html          pública: o que é a plataforma
    login · cadastro · acesso-pendente · acesso-recusado
    index.html           painel
    nova-analise · resultado · modelos · isolados
    bases.html           equipe: importar e listar bases
    antibioticos.html    equipe: treinar e escolher o modelo padrão
    equipe.html          equipe: liberar ou recusar cadastros
    usuarios.html        admin: papéis, contas e acesso compartilhado
    conta.html           trocar a própria senha
  Dockerfile      para hospedar (na sua máquina não precisa)
  bionalya.db     o banco (gerado na primeira execução)
```

Os modelos ficam **em pasta por base** (`modelos/neisseria-gonorrhoeae/…`), e no banco a
chave de um antibiótico é `<base>__<antibiotico>`. É o que permite o mesmo antibiótico
ter um modelo diferente em cada base sem um sobrescrever o outro.

Ao contrário do resto do que é gerado, `modelos/` **vai para o repositório**, de
propósito: sem ele a hospedagem subiria sem nenhum antibiótico, e treinar na nuvem
exigiria a base completa de 32 MB. São cerca de 11 MB.

## Os modelos

Para cada antibiótico a plataforma ajusta **os quatro algoritmos** — regressão logística,
random forest, XGBoost e rede neural — usando só os isolados que têm resultado de
laboratório para ele. **Os quatro ficam guardados**, não só o vencedor.

Quem responde por padrão é o de melhor AUC, mas isso é configurável: na tela de
**Antibióticos** a equipe escolhe o padrão de cada um, e na **Nova análise** quem está
analisando pode trocar na hora. Quando a previsão sai de um modelo que não é o
recomendado, a tela de resultado diz isso.

Vale lembrar por que alguém escolheria um modelo pior de propósito: a regressão logística
é a única com peso por gene que significa de verdade "o quanto este gene empurrou a
decisão". Quando o que importa é explicar, e não acertar a terceira casa decimal, ela é a
escolha certa.

| Antibiótico | Modelo escolhido | AUC | Isolados | Confiança |
|---|---|---|---|---|
| Ciprofloxacino | Random Forest | 0,994 | 728 | alta |
| Tetraciclina | Random Forest | 0,997 | 466 | média |
| Azitromicina | XGBoost | 0,945 | 692 | alta |
| Penicilina | Regressão Logística | 0,972 | 285 | baixa |
| Ceftriaxona | Regressão Logística | 1,000 | 788 | baixa |
| Cefixima | Random Forest | 0,642 | 750 | baixa |

Três decisões do pipeline que valem ser lembradas:

**O rótulo é R contra S.** Isolados marcados I (intermediário), NS ou ND são descartados,
não agrupados. É a mesma regra do notebook — por isso o ciprofloxacino dá exatamente os
585/143 e os 58 genes que já foram apresentados.

**A separação treino/teste é por cluster genético**, nunca aleatória. Bactérias são
clonais: cópias quase idênticas do mesmo isolado caindo dos dois lados inflam a AUC para
1,000 sem significar nada. Foi assim que a primeira versão do projeto se enganou.

**O filtro de frequência dos genes é calculado só no treino.** Olhar a frequência no
conjunto inteiro já é vazamento.

### Sobre a AUC 1,000 da ceftriaxona

Ela está na tabela e está marcada como **baixa confiança** de propósito. A base tem 775
isolados sensíveis e só 13 resistentes à ceftriaxona; o conjunto de teste fica com umas
três resistentes. Com tão poucos, a AUC oscila muito de uma divisão para outra e não
deve ser lida como medida de desempenho. A plataforma mostra esse aviso na tela sempre
que o modelo usado está nessa situação — a regra é: menos de 10 isolados da classe
minoritária no teste dispara o alerta.

O mesmo vale, em menor grau, para cefixima (23 resistentes) e penicilina (18 sensíveis).

## Adicionar um antibiótico

Na tela **Antibióticos**, visível só para a equipe. A lista de candidatos vem da própria
base: são os antibióticos que aparecem na coluna de antibiograma. Só dá para treinar os
que têm pelo menos 60 isolados com R ou S e pelo menos 10 na classe minoritária — os
outros aparecem numa lista separada com o motivo.

Treinar leva alguns segundos e acontece na hora. O limiar de decisão é escolhido ali
mesmo: abaixá-lo faz o modelo errar menos para o lado perigoso (dizer "sensível" para uma
bactéria resistente), ao custo de mais alarmes falsos.

## Importar outra base

Na tela **Bases**, visível só para a equipe. Serve para trazer outra espécie, outro
recorte ou dados do próprio laboratório, sem mexer em código.

O arquivo é um CSV ou TSV no formato do NCBI Pathogen Detection, de até 120 MB. Ele é
gravado em pedaços — ler dezenas de MB na memória antes de validar derrubaria a API — e
só depois conferido. São três conferências:

1. **Coluna de genótipo** (*AMR genotypes*): a lista de genes de cada isolado, de onde
   saem as variáveis do modelo.
2. **Coluna de antibiograma** (*AST phenotypes*): o resultado do laboratório. É a
   resposta certa; sem ela não há o que treinar.
3. **Tamanho mínimo**: pelo menos 30 linhas, e alguma delas com antibiograma preenchido.

Falhando qualquer uma, o arquivo é **apagado** e a mensagem diz exatamente o que não foi
encontrado. Passando, a resposta já lista quais antibióticos daquela base têm isolados
suficientes para treinar.

Importar **não treina**: a base entra para consulta na hora, mas os modelos dela começam
vazios. Depois de importar, vá em *Antibióticos*, escolha a base nova e treine um
antibiótico de cada vez. Remover uma base é coisa de admin, apaga junto os modelos
treinados com ela, e a base de fábrica não pode ser removida.

## Hospedar para teste

### Por que não dá pelo GitHub Pages

O Pages serve **arquivo estático**: HTML, CSS, JS e imagem, entregues como estão. Ele
não roda Python, então não roda a API — e sem API não há login, nem busca na base, nem
`/api/prever`, porque a previsão acontece do lado do servidor, carregando um `.joblib` de
alguns MB.

|  | GitHub Pages | Com servidor |
|---|---|---|
| Telas, previsão com os 4 modelos | não | sim |
| Explorar a base | não | sim |
| Login, aprovação, papéis | não | sim |
| Treinar modelo, importar base | não | sim |

### Render, plano grátis

O repositório já traz o `Dockerfile` e o `render.yaml` prontos.

1. Suba o repositório para o GitHub (incluindo `plataforma/modelos/` e
   `dados/amostra-neisseria-gonorrhoeae.csv`).
2. Em [dashboard.render.com](https://dashboard.render.com), **New → Blueprint**, aponte
   para o repositório. Ele lê o `render.yaml` e monta o serviço sozinho. Não pede cartão.
3. Primeiro build leva uns 5 minutos. No fim sai uma URL `https://bionalya.onrender.com`.
4. Em **Environment**, copie o valor de `BIONALYA_ADMIN_SENHA` — o Render sorteou essa
   senha e é com ela que você entra como admin.

O que esperar do plano grátis: 750 horas de instância por mês (uma instância ligada o mês
inteiro cabe), o serviço **dorme depois de 15 minutos** sem acesso e a primeira visita
depois disso leva cerca de 1 minuto para acordar, e **o disco é descartável** — a cada
reinício o `bionalya.db` volta do zero.

É por causa da última que as contas vêm de variável de ambiente: sem elas, a senha do
admin mudaria a cada reinício e ninguém mais entraria.

| Variável | Para quê |
|---|---|
| `BIONALYA_ADMIN_EMAIL` | e-mail da conta de admin (padrão: `equipe@bionalya.app`) |
| `BIONALYA_ADMIN_SENHA` | senha dela. Em branco = sorteada e gravada em `PRIMEIRO-ACESSO.txt` |
| `BIONALYA_DEMO_EMAIL` | conta aberta de demonstração. Sem ela, não existe |
| `BIONALYA_DEMO_SENHA` | senha da conta de demonstração |
| `BIONALYA_DEMO_NOME` | nome que aparece nela |

Como o banco se perde a cada reinício, o que for cadastrado durante o teste **não
sobrevive**. Para uma banca isso basta; para uso contínuo, é trocar o SQLite por um
Postgres (o Render também tem um grátis) ou pagar um disco.

### Em qualquer outro lugar

Com Docker, o contexto do build é a **raiz do repositório**, não a pasta `plataforma/`:

```bash
docker build -f plataforma/Dockerfile -t bionalya .
docker run -p 8000:8000 -e BIONALYA_ADMIN_SENHA=escolha-uma bionalya
```

## A API

Documentação navegável em `/docs`. As rotas:

```
POST   /api/cadastro                            solicita acesso
POST   /api/sessao                              entra, devolve token
DELETE /api/sessao                              sai
GET    /api/eu                                  quem está logado

GET    /api/bases                               bases disponíveis
GET    /api/base/resumo                         números do painel
GET    /api/base/antibioticos                   antibióticos com modelo
GET    /api/antibioticos/{id}/genes             features daquele modelo
GET    /api/modelos?antibiotico=...             comparação dos 4 algoritmos
GET    /api/base/isolados                       busca nos isolados
POST   /api/prever                              a previsão
POST   /api/eu/senha                            troca a própria senha

GET    /api/equipe/solicitacoes                 equipe
POST   /api/equipe/solicitacoes/{id}/decidir    equipe
GET    /api/antibioticos/disponiveis            equipe
POST   /api/antibioticos/treinar                equipe
POST   /api/antibioticos/{id}/padrao            equipe — qual modelo responde
POST   /api/bases                               equipe — importa um CSV de isolados

GET    /api/admin/usuarios                      admin
POST   /api/admin/usuarios                      admin — cria acesso compartilhável
POST   /api/admin/usuarios/{id}/papel           admin
POST   /api/admin/usuarios/{id}/ativo           admin
DELETE /api/bases/{id}                          admin — remove base e modelos dela
```

As rotas que falam de um antibiótico usam a chave composta
`<base>__<antibiotico>` — por exemplo `neisseria-gonorrhoeae__ciprofloxacin`. As que
falam de uma base aceitam `?base=<id>`; sem isso, usam a base de fábrica.

Autenticação por token no cabeçalho: `Authorization: Bearer <token>`. O token vem do
`POST /api/sessao` e vale 12 horas.

Exemplo de previsão:

```json
// POST /api/prever
{ "antibiotico": "neisseria-gonorrhoeae__ciprofloxacin",
  "genes": ["gyrA_S91F", "parC_S87R", "gyrA_D95G", "ponA_L421P", "mtrR"],
  "modelo": "regressao_logistica" }       // opcional: sem isso usa o padrão

// resposta
{ "classe": "resistente",
  "probabilidade": 0.767,
  "limiar": 0.5,
  "genes_ignorados": [],
  "contribuicoes": [ { "gene": "gyrA_S91F", "peso": 3.8893 },
                     { "gene": "parC_S87R", "peso": 1.9596 } ],
  "explicacao_por": "regressão logística ajustada no mesmo conjunto de treino",
  "modelo": { "nome": "Regressão Logística", "versao": "a2182e556293", "auc": 0.990,
              "confianca": "alta", "alerta": null,
              "recomendado": "random_forest", "era_recomendado": false } }
```

**Por que a explicação vem da regressão logística** e não do modelo que respondeu: uma
floresta e uma rede neural não têm "peso por gene" que signifique a mesma coisa. Em vez
de inventar um número, a plataforma ajusta uma regressão logística no mesmo conjunto de
treino e usa os coeficientes dela, dizendo isso na própria resposta.

## Segurança e dados pessoais

Senha guardada só como hash PBKDF2-SHA256; nem a equipe consegue ler a senha de alguém.
Login e e-mail inexistente devolvem a mesma mensagem, para não entregar a quem está
tentando a informação de que o e-mail existe. Recusar um cadastro derruba as sessões
abertas daquela pessoa.

**O que ainda falta resolver no documento de processo:** com cadastro e login, a
plataforma passou a tratar dados pessoais (nome, e-mail, instituição, finalidade), o que
contradiz o **RNF10** como ele está escrito hoje. Esse requisito precisa ser reescrito, e
vale somar requisitos de autenticação, armazenamento de senha com hash, base legal e
prazo de retenção sob a LGPD.

O **log de previsões** foi deixado de fora de propósito, por isso mesmo: gravar consulta
ligada a usuário é tratamento de dado pessoal e pede essa definição antes. A tabela está
desenhada e entra depois.

## O que ainda falta

- Log de previsões, junto com a reescrita do RNF10
- Recuperação de senha por e-mail (hoje só a equipe consegue ajudar quem esqueceu)
- Upload do CSV do isolado na tela de nova análise (hoje só a marcação de genes)
- Treino em segundo plano, para a tela não ficar esperando
- Banco que sobrevive ao reinício na hospedagem grátis (trocar o SQLite por Postgres)
