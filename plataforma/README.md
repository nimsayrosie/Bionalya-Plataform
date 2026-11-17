# Bionalya — plataforma

Previsão de resistência bacteriana a antibióticos a partir dos genes encontrados no
sequenciamento. Dezoito telas, uma API em FastAPI e seis antibióticos com quatro modelos
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

**3. As chaves do login.** O login (cadastro, senha, e-mails) é do Supabase. Copie
`plataforma/.env.example` para `plataforma/.env` e preencha com as chaves do projeto —
peça a quem cuida da hospedagem, ou crie um projeto seu seguindo
[`docs/banco-e-hospedagem.md`](../docs/banco-e-hospedagem.md). Sem elas a API sobe, mas
ninguém entra.

**4. Subir a plataforma.**

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

**5. Primeiro acesso.** Na primeira vez que sobe, a API cria a conta de **admin**
(`BIONALYA_ADMIN_EMAIL`) no Supabase. Sem `BIONALYA_ADMIN_SENHA` no `.env`, a senha é
sorteada e gravada em `plataforma/PRIMEIRO-ACESSO.txt`, que está no `.gitignore`. Ao
entrar com ela, a plataforma pede na hora para trocar por uma senha sua. Se a conta já
existir no Supabase (outra pessoa da equipe subiu antes), a senha dela não é mexida.

**6. Testes.** Não precisam de chave nem de internet: usam um Supabase de mentira e um
SQLite temporário.

```bash
pip install -r requirements-dev.txt
python -m pytest
```

**7. Onde ficam os dados.** Na sua máquina, o banco é o arquivo `plataforma/bionalya.db`
(SQLite), criado sozinho na primeira vez. Ele não se perde ao reiniciar e não vai para o
GitHub. Para usar um PostgreSQL em vez dele — o mesmo da hospedagem, por exemplo —
defina a variável `DATABASE_URL` antes de subir:

```bash
export DATABASE_URL='postgresql://usuario:senha@servidor/banco?sslmode=require'
# Windows (PowerShell):  $env:DATABASE_URL = 'postgresql://...'
python -m uvicorn api.main:app --reload
```

Cuidado: com `DATABASE_URL` apontando para o banco da hospedagem, o que você fizer na
sua máquina vale para todo mundo que usa o site.

### Compartilhar o acesso com alguém

Duas formas, ambas na conta de admin:

- **Tela Usuários → "Criar um acesso para compartilhar".** A conta já nasce aprovada,
  sem a pessoa precisar se cadastrar e esperar liberação. Deixando a senha em branco, a
  plataforma sorteia uma e mostra **uma única vez** — depois disso ninguém consegue ler.
  No primeiro acesso, a pessoa é obrigada a trocar por uma senha dela. A pessoa também
  recebe um e-mail avisando da conta. É o caminho para a banca e para o orientador.
- **Cadastro comum.** A pessoa se cadastra em `cadastro.html`, fica em análise e alguém
  da equipe libera na tela *Acessos*.

Há um terceiro caminho: as variáveis `BIONALYA_DEMO_EMAIL` e `BIONALYA_DEMO_SENHA`
garantem, toda vez que a API sobe, uma conta aberta de demonstração — um pesquisador
comum, que analisa e consulta mas não libera acesso, não treina modelo e não importa
base. Essa não é obrigada a trocar a senha, de propósito: ela é compartilhada.

### O cadastro e o login

1. A pessoa se cadastra em `cadastro.html`. A conta nasce no Supabase, que manda um
   **e-mail de confirmação**, e o pedido fica em análise.
2. O link do e-mail abre `confirmar-email.html`; um clique confirma.
3. A equipe libera ou recusa em `equipe.html` (a lista mostra se o e-mail já foi
   confirmado). A pessoa recebe **um e-mail com a decisão**, e o motivo, se for recusa.
4. Para entrar, precisa das duas coisas: e-mail confirmado e acesso liberado. Quem tenta
   entrar sem confirmar vê um botão para receber o link de novo.

O token de sessão vale 1 hora; as telas renovam sozinhas, sem a pessoa perceber.

### Quando alguém esquece a senha

1. Na tela de login, a pessoa clica em **Esqueci minha senha** (`esqueci-senha.html`) e
   digita o e-mail do cadastro.
2. Chega um e-mail com um link, que vale **1 hora** e funciona uma vez.
3. O link abre `redefinir-senha.html`. Salvando a senha nova, a pessoa já entra, e as
   outras sessões dela caem.

A tela responde a mesma coisa para qualquer e-mail, exista ou não a conta, para não
entregar quem está cadastrado.

**Plano B, sem e-mail.** Se o e-mail não sair (Gmail fora do ar, limite do dia), o
pedido vira um aviso no painel da equipe. Um admin abre o aviso, que leva para a tela
*Usuários* filtrada naquela pessoa, e clica em **Gerar senha nova**. A senha aparece
uma vez só; o admin manda por um canal confiável e, ao entrar, a pessoa é **obrigada a
trocar na hora**, num pop-up que não fecha. A API recusa as outras rotas até a troca,
então o pop-up não dá para contornar.

### Atualizando uma versão anterior

Não precisa apagar o `bionalya.db`. Ao subir, a API compara o banco com o código e
acrescenta sozinha as colunas que faltam, preenchendo as linhas antigas com o padrão —
você vê no terminal um `Banco atualizado — colunas acrescentadas: ...`.

**A troca para o Supabase é a exceção.** Um banco da época em que a senha ficava aqui
(coluna `senha_hash`) tem as tabelas `usuarios` e `sessoes` apagadas na partida, e o
terminal mostra `Login antigo descartado`. O Supabase não importa senha em PBKDF2, e a
troca foi feita antes de alguém se cadastrar de verdade. Bases, modelos e avisos ficam;
o admin é recriado.

A migração só sabe **acrescentar** coluna, que é o que o SQLite permite com
`ALTER TABLE`. Remover ou mudar o tipo de uma coluna pede migração de verdade; se um dia
o projeto precisar disso, vale trazer o Alembic. A mesma migração roda igual no
PostgreSQL.

**Trocar de banco não leva os dados junto.** Quando a `DATABASE_URL` passa a apontar
para um Postgres novo, ele começa vazio: a API cria as tabelas, a conta de admin e os
seis antibióticos de fábrica, mas os usuários e as bases do `bionalya.db` local ficam no
arquivo local. Na hospedagem isso não faz diferença, porque lá o banco antigo já se
apagava a cada reinício.

## Os três papéis

| Papel | Pode |
|---|---|
| **pesquisador** | Analisar isolados, ver os modelos e explorar a base |
| **equipe** | tudo acima + liberar cadastros, treinar modelos, definir o modelo padrão |
| **admin** | tudo acima + mudar papéis e ativar/desativar contas |

São cumulativos: quem é admin pode tudo que a equipe pode. Promover alguém já libera o
acesso dessa pessoa.

Mudar o papel não é mais imediato: a tela abre uma janela com o papel atual, o novo e o
que a pessoa passa a poder fazer. **Promover a equipe ou admin pede a senha de quem está
promovendo**, conferida no Supabase, e toda mudança de papel vira um aviso para a equipe,
com quem fez. Rebaixar só pede a confirmação.

**Desativar** corta o acesso na hora e pode ser desfeito. **Apagar** pede confirmação e
tira a conta do login (Supabase), da tabela `usuarios` e dos avisos que ela gerou; não
dá para desfazer. As bases que a pessoa enviou ficam na plataforma, marcadas como
`(conta apagada)`: ninguém é dono delas, e só a equipe pode treinar com elas ou removê-las. A
plataforma impede que você rebaixe, desative ou apague a si mesmo, e que o sistema fique sem
nenhum admin ativo.

## Como está organizado

```
plataforma/
  api/
    main.py       as rotas
    treino.py     o pipeline: rótulos, features, split por cluster, 4 modelos
    modelos.py    carrega os .joblib e responde a previsão
    banco.py      tabelas e migração; Postgres (DATABASE_URL) ou SQLite local
    arquivos.py   cópia dos CSVs e modelos no banco, para o disco descartável
    autenticacao.py  login pelo Supabase Auth: cadastro, sessão, senha nova, token
    correio.py    e-mails de acesso liberado/recusado e de conta criada (Gmail)
    seguranca.py  regra mínima de senha e sorteio de senha
    config.py     caminhos, nomes em português e variáveis de ambiente (lê o .env)
  modelos/
    <base>/       um .joblib + um .json por antibiótico daquela base
  web/            as telas, o style.css, o tema.js e o app.js
    inicio.html          pública: o que é a plataforma
    login · cadastro · acesso-pendente · acesso-recusado
    esqueci-senha.html   pública: pedir o link de senha nova por e-mail
    redefinir-senha.html pública: onde o link de senha nova abre
    confirmar-email.html pública: onde o link de confirmação do cadastro abre
    index.html           painel
    nova-analise · resultado · modelos · isolados
    bases.html           equipe: importar e listar bases
    antibioticos.html    equipe: treinar e escolher o modelo padrão
    equipe.html          equipe: liberar ou recusar cadastros
    usuarios.html        admin: papéis, contas, acesso compartilhado e senha nova
    conta.html           trocar a própria senha
  supabase/
    emails/       modelos de e-mail em português (confirmação, senha nova)
    configurar.py configura o login do projeto no Supabase de uma vez
  testes/         testes do fluxo de acesso, com um Supabase de mentira
  .env.example    as variáveis, para copiar para .env
  Dockerfile      para hospedar (na sua máquina não precisa)
  bionalya.db     o banco local (gerado na primeira execução)
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

## Trazer a própria base

Na seção **Bases de dados**, aberta a todo mundo. Serve para trazer outra espécie, outro
recorte ou dados do próprio laboratório, sem mexer em código.

**Não há fila de aprovação.** A base entra valendo assim que o envio termina — para quem
enviou e para todo mundo — e quem enviou já pode treinar os modelos dela na tela
*Antibióticos*. A equipe não libera nada; ela é **avisada**: cada importação e cada
treino feito por um pesquisador vira um aviso no painel (ver *Avisos* abaixo). Se algo
estiver errado, o admin remove a base depois, em vez de segurar o trabalho de todo mundo
antes.

Quem não é da equipe aceita um **termo de responsabilidade** antes de enviar — declara
que tem autorização para usar aquele dado e que não há informação que identifique
pacientes. A versão do texto aceito fica guardada junto com o registro, não só um "sim":
se o termo mudar, dá para saber o que a pessoa leu. O texto vive em `config.TERMO_BASE`
e a tela lê pela rota `/api/termo-base`, para o que está escrito na página e o que é
guardado serem a mesma coisa.

Cada pesquisador pode ter **três bases** ao mesmo tempo
(`config.MAX_BASES_POR_PESQUISADOR`). Sem limite, o disco acaba.

Quem enviou pode **baixar de volta** o arquivo e **remover** a própria base quando
quiser; remover apaga junto os modelos treinados com ela. Admin remove qualquer uma,
menos a de fábrica.

### Quem treina o quê

| Base | Quem pode treinar |
|---|---|
| a que a pessoa enviou | ela mesma, e a equipe |
| a de fábrica e as das outras pessoas | só a equipe |

A verificação é no servidor, em `pode_treinar()`: a tela só esconde o que não dá para
fazer, mas é a API que recusa.

## Avisos para a equipe

Como importar e treinar deixaram de passar por aprovação, a equipe precisa de um lugar
para acompanhar o que foi feito. É a seção **Avisos** no painel, visível de equipe para
cima, com um contador de não lidos no menu.

Dois eventos geram aviso, e só quando quem fez **não** é da equipe: importar uma base e
treinar um modelo. O aviso é coletivo — qualquer pessoa da equipe lê e marca como lido
para todas —, porque o que importa é alguém ter visto, não cada um ter visto.

### O que a plataforma confere no arquivo

É um CSV ou TSV no formato do NCBI Pathogen Detection, de até 120 MB. Ele é gravado em
pedaços — ler dezenas de MB na memória antes de validar derrubaria a API — e só depois
conferido. São três conferências:

1. **Coluna de genótipo** (*AMR genotypes*): a lista de genes de cada isolado, de onde
   saem as variáveis do modelo.
2. **Coluna de antibiograma** (*AST phenotypes*): o resultado do laboratório. É a
   resposta certa; sem ela não há o que treinar.
3. **Tamanho mínimo**: pelo menos 30 linhas, e alguma delas com antibiograma preenchido.

Falhando qualquer uma, o arquivo é **apagado** e a mensagem diz exatamente o que não foi
encontrado. Passando, a resposta já lista quais antibióticos daquela base têm isolados
suficientes para treinar.

Importar **não treina**: a base entra valendo, mas os modelos dela começam vazios. Vá
em *Antibióticos*, escolha-a na lista e treine um antibiótico de cada vez.

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

### Render + Supabase + Gmail, tudo grátis

O repositório já traz o `Dockerfile` e o `render.yaml` prontos. São três peças:

- **Render** roda a API e as telas. Dorme depois de 15 minutos sem acesso (a primeira
  visita leva cerca de 1 minuto) e **apaga o disco** a cada reinício.
- **Supabase** guarda o banco (Postgres) e cuida do login. Pausa o projeto depois de 7
  dias sem uso; um job do GitHub (`.github/workflows/manter-acordado.yml`) abre o site
  duas vezes por semana para isso não acontecer.
- **Gmail do projeto**, com senha de app, manda os e-mails: confirmação de cadastro,
  link de senha nova e a decisão da equipe.

Em resumo:

1. Crie a conta Gmail do projeto, ative a verificação em duas etapas e gere uma senha
   de app.
2. Crie o projeto no Supabase e copie a URL, as duas chaves e o endereço do banco
   (*Connect → Session pooler*).
3. Rode `python supabase/configurar.py --aplicar` na sua máquina: configura SMTP,
   modelos de e-mail em português e os endereços permitidos.
4. No Render (*New → Blueprint* num serviço novo, ou *Environment* no que já existe),
   preencha as variáveis que ele pedir.
5. Abra `/saude`: `banco`, `login` e `email` têm que estar `true`.

**O passo a passo completo**, com onde achar cada chave e o que fazer sem o script, está
em [`docs/banco-e-hospedagem.md`](../docs/banco-e-hospedagem.md). A lista de variáveis
está em [`.env.example`](.env.example).

A conta de admin é criada **uma vez só**, na primeira partida. Se você trocar a senha em
*Minha conta*, vale a nova; mudar `BIONALYA_ADMIN_SENHA` no painel depois disso não
altera a conta que já existe.

### O que fica guardado

| O quê | Onde mora | Sobrevive ao reinício? |
|---|---|---|
| E-mail e senha (hash bcrypt), sessões | Supabase Auth | sim |
| Nome, instituição, finalidade, papel, status | tabela `usuarios` | sim |
| Bases cadastradas e o termo aceito | tabela `bases` | sim |
| Antibióticos, nome em português, modelo padrão | tabela `antibioticos` | sim |
| Avisos para a equipe | tabela `notificacoes` | sim |
| CSVs enviados (`dados/enviadas/`) | disco **+ cópia na tabela `arquivos`** | sim, recriados na partida |
| Modelos treinados (`modelos/<base>/`) | disco **+ cópia na tabela `arquivos`** | sim, recriados na partida |
| Base de fábrica e os 6 modelos iniciais | no repositório | sim, vêm no deploy |

A cópia dos arquivos no banco é o módulo `api/arquivos.py`: toda vez que a plataforma
grava um CSV ou treina um modelo, o arquivo vai também para a tabela `arquivos`; quando
a base é removida, a cópia sai junto; e na partida o que falta no disco é recriado
antes de tudo. O disco continua sendo de onde tudo é lido.

Os arquivos ocupam o espaço do Postgres: o grátis do Supabase tem 500 MB, e cada CSV pode ter
até 120 MB (`MAX_MB_BASE`). Com SQLite, na sua máquina, a cópia fica desligada — o disco
já é permanente e ela só dobraria o espaço.

Quando há arquivos para recriar, o log da partida mostra
`N arquivo(s) recriados a partir do banco.`

**Backup.** O plano grátis do Supabase não faz cópia de segurança automática. Para guardar
uma, rode na sua máquina (precisa do `pg_dump`, que vem com o PostgreSQL):

```bash
pg_dump "$DATABASE_URL" > backup-bionalya.sql
```

O arquivo tem os dados de todos os usuários e as bases enviadas: trate como dado
pessoal e não suba para o GitHub.

### Em qualquer outro lugar

Com Docker, o contexto do build é a **raiz do repositório**, não a pasta `plataforma/`:

```bash
docker build -f plataforma/Dockerfile -t bionalya .
docker run -p 8000:8000 --env-file plataforma/.env bionalya
```

O `.env` não entra na imagem (está no `.dockerignore`): as variáveis vão na hora de
rodar. Sem `DATABASE_URL`, o banco fica dentro do container e some quando ele é
recriado.

## A API

Documentação navegável em `/docs`. As rotas:

```
POST   /api/cadastro                            solicita acesso (manda e-mail de confirmação)
POST   /api/confirmar-email                     confirma pelo link do e-mail
POST   /api/reenviar-confirmacao                manda o link de confirmação de novo
POST   /api/sessao                              entra, devolve token e refresh_token
POST   /api/sessao/renovar                      troca o refresh_token por um token novo
DELETE /api/sessao                              sai
GET    /api/eu                                  quem está logado
POST   /api/recuperar-senha                     manda o link de senha nova por e-mail
POST   /api/redefinir-senha                     define a senha nova a partir do link

GET    /api/termo-base                          o termo e os limites do envio
GET    /api/bases                               as bases que esta pessoa enxerga
POST   /api/bases                               envia uma base (entra valendo na hora)
GET    /api/bases/{id}/arquivo                  baixa o CSV (dono ou equipe)
DELETE /api/bases/{id}                          remove a base (dono ou admin)
GET    /api/base/resumo                         números do painel
GET    /api/base/antibioticos                   antibióticos com modelo
GET    /api/antibioticos/{id}/genes             features daquele modelo
GET    /api/modelos?antibiotico=...             comparação dos 4 algoritmos
GET    /api/base/isolados                       busca nos isolados
POST   /api/prever                              a previsão
POST   /api/eu/senha                            troca a própria senha

GET    /api/notificacoes                        equipe — avisos não lidos
POST   /api/notificacoes/lidas                  equipe — marca tudo como lido
GET    /api/equipe/solicitacoes                 equipe
POST   /api/equipe/solicitacoes/{id}/decidir    equipe
GET    /api/antibioticos/disponiveis            dono da base ou equipe
POST   /api/antibioticos/treinar                dono da base ou equipe
POST   /api/antibioticos/{id}/padrao            dono da base ou equipe

GET    /api/admin/usuarios                      admin
POST   /api/admin/usuarios                      admin — cria acesso compartilhável
POST   /api/admin/usuarios/{id}/papel           admin — promover pede senha_admin
POST   /api/admin/usuarios/{id}/ativo           admin
POST   /api/admin/usuarios/{id}/senha           admin — gera senha nova para quem esqueceu
DELETE /api/admin/usuarios/{id}                 admin — apaga a conta de vez
```

As rotas que falam de um antibiótico usam a chave composta
`<base>__<antibiotico>` — por exemplo `neisseria-gonorrhoeae__ciprofloxacin`. As que
falam de uma base aceitam `?base=<id>`; sem isso, usam a base de fábrica.

Autenticação por token no cabeçalho: `Authorization: Bearer <token>`. O token é do
Supabase, vem do `POST /api/sessao` e vale 1 hora; o `refresh_token` que vem junto
renova em `POST /api/sessao/renovar` (o `app.js` faz isso sozinho). A API confere a
assinatura do token pela chave pública do projeto, sem ir ao Supabase a cada pedido.

Enquanto a pessoa estiver com uma senha que outra pessoa definiu, só `GET /api/eu` e
`POST /api/eu/senha` respondem; o resto devolve 403 pedindo a troca.

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

A senha não passa pelo nosso banco: fica no Supabase Auth, como hash bcrypt; nem a
equipe consegue ler a senha de alguém. Login com senha errada e com e-mail inexistente
devolvem a mesma mensagem, e o pedido de senha nova responde igual exista ou não a
conta, para não entregar quem está cadastrado. Recusar ou desativar alguém corta o
acesso na hora, porque toda rota confere o status. Senha definida por outra pessoa
precisa ser trocada antes de qualquer outra coisa.

As telas nunca falam com o Supabase: a chave secreta dele, a senha do banco e a senha
de app do Gmail ficam só no servidor. O Supabase publica as tabelas numa API REST
própria; a API liga o RLS em todas elas, sem política nenhuma, para essa porta ficar
fechada.

Com o envio de base pelo pesquisador, a plataforma passou a guardar **dado de
terceiro**, não só o cadastro de quem usa. Por isso o termo de responsabilidade é
obrigatório e fica registrado com a versão do texto aceito, cada importação e cada
treino geram um aviso para a equipe, e quem enviou pode remover a própria base a
qualquer momento. É o mínimo; não substitui a
definição de base legal e prazo de retenção, que continua pendente.

**O que ainda falta resolver no documento de processo:** com cadastro e login, a
plataforma passou a tratar dados pessoais (nome, e-mail, instituição, finalidade), o que
contradiz o **RNF10** como ele está escrito hoje. Esse requisito precisa ser reescrito, e
vale somar requisitos de autenticação, armazenamento de senha com hash, base legal e
prazo de retenção sob a LGPD.

**O banco da hospedagem fica num serviço de terceiro.** Os cadastros, as contas de
login e os CSVs enviados ficam nos servidores do Supabase, nos Estados Unidos, e os
e-mails passam pelo Gmail. Sob a LGPD isso é transferência internacional de dado
pessoal, e entra na mesma definição pendente de base legal. (Criar o projeto do Supabase
na região de São Paulo resolve a localização, ao custo de respostas mais lentas.)
Regras práticas:

- `DATABASE_URL`, `SUPABASE_SERVICE_KEY` e `SMTP_SENHA` só no painel do Render e no
  `.env` local, nunca no `render.yaml`, no README ou num commit;
- um backup feito com `pg_dump` tem os mesmos dados e merece o mesmo cuidado.

O **log de previsões** foi deixado de fora de propósito, por isso mesmo: gravar consulta
ligada a usuário é tratamento de dado pessoal e pede essa definição antes. A tabela está
desenhada e entra depois.

## O que ainda falta

- Log de previsões, junto com a reescrita do RNF10
- Upload do CSV do isolado na tela de nova análise (hoje só a marcação de genes)
- Treino em segundo plano, para a tela não ficar esperando
- Backup automático do banco da hospedagem (hoje é à mão, com `pg_dump`)
- Levar os dados de um `bionalya.db` local para o Postgres, se um dia for preciso
