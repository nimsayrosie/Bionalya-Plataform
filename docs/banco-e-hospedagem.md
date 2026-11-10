# Banco de dados e hospedagem da Bionalya

Este documento explica onde a Bionalya guarda as informações, por que elas se perdiam
na hospedagem, o que foi mudado para isso parar de acontecer, o que é grátis, o que é
pago e o que tem prazo. No fim tem o passo a passo para rodar e para publicar.

Resolve a [issue #22 — Banco que não some no reinício](https://github.com/nimsayrosie/Bionalya-Plataform/issues/22).

---

## 1. Em uma frase

Antes, toda vez que o servidor na internet reiniciava ou dormia, a plataforma voltava do
zero. Agora as informações ficam num banco PostgreSQL grátis e sem prazo (no **Neon**),
e nada se perde. Na sua máquina continua tudo como era.

---

## 2. O banco é seu — então o que se paga?

O banco **é seu**. O PostgreSQL é um programa livre e gratuito, e o código e os dados são
do projeto. O que pode custar dinheiro não é o banco: é **o computador onde ele fica
ligado**.

| Onde a plataforma roda | Onde fica o banco | Custa? | Tem prazo? |
|---|---|---|---|
| **Na sua máquina** | o arquivo `plataforma/bionalya.db` (SQLite), no seu disco | não | não |
| **Na internet** (link para a banca, para outras pessoas) | um computador de alguma empresa, ligado 24 horas | depende da empresa | depende da empresa |

Na sua máquina nada se perde nunca, mas a plataforma só existe enquanto o seu computador
está ligado e só você acessa. Para ter um link público, alguém precisa deixar um
computador ligado por você — e cada empresa tem uma regra.

---

## 3. As peças da hospedagem

A plataforma na internet tem **duas peças**, em dois serviços diferentes:

```
            pessoa no navegador
                     │
                     ▼
   ┌───────────────────────────────────┐
   │ RENDER — o servidor (grátis)      │   roda a API e as telas
   │ disco APAGADO a cada reinício,    │
   │ atualização ou cochilo            │
   └───────────────┬───────────────────┘
                   │ DATABASE_URL
                   ▼
   ┌───────────────────────────────────┐
   │ NEON — o banco Postgres (grátis)  │   guarda tudo
   │ não apaga, não tem prazo          │
   └───────────────────────────────────┘
```

### Peça 1 — o servidor, no Render (grátis, sem prazo)

- 750 horas por mês, o suficiente para ficar ligado o mês inteiro.
- **Dorme depois de 15 minutos** sem ninguém acessar. A primeira visita depois disso leva
  cerca de 1 minuto para acordar.
- **O disco é apagado** a cada reinício, a cada atualização (deploy) **e a cada vez que
  ele dorme**. No plano grátis não dá para contratar um disco permanente.

Esse último ponto era o problema: com o banco no disco, a plataforma se apagava sozinha
várias vezes por dia.

### Peça 2 — o banco, no Neon (grátis, sem prazo)

- Plano grátis **permanente**, não é teste. Não pede cartão de crédito.
- **1 GB** de espaço por projeto.
- Não apaga projeto parado. Quando ninguém usa, ele "cochila" depois de 5 minutos e
  acorda na próxima consulta em menos de um segundo.

### Por que não o banco do próprio Render

O Render também oferece um Postgres grátis, mas ele **expira 30 dias depois de criado**.
Depois disso dá 14 dias para começar a pagar; se ninguém pagar, **o Render apaga o banco
com todos os dados**. Não faz backup e só permite um por conta. Por isso não é usado.

### Comparação

| Opção | Custo | Prazo | Espaço |
|---|---|---|---|
| SQLite na sua máquina | grátis | nenhum | o do seu disco |
| **Neon grátis (o escolhido)** | **grátis, sem cartão** | **nenhum** | **1 GB** |
| Postgres grátis do Render | grátis | **apagado em 30 + 14 dias** | 1 GB |
| Postgres pago do Render | cerca de US$ 7/mês + US$ 0,30 por GB (valor de fonte secundária, conferir no site) | nenhum | a contratar |

Valores conferidos em novembro de 2026 em
[render.com/docs/free](https://render.com/docs/free) e
[neon.com/pricing](https://neon.com/pricing). Planos grátis mudam; vale olhar de novo
antes de depender deles.

**O que você precisa pagar: nada.** Render grátis + Neon grátis.

---

## 4. O que a plataforma guarda

| Informação | Onde fica | Antes, na hospedagem | Agora |
|---|---|---|---|
| Usuários, papéis e senhas (só o hash) | tabela `usuarios` | perdia | fica salvo |
| Logins abertos | tabela `sessoes` | perdia (todo mundo deslogado) | fica salvo |
| Bases cadastradas e o termo que a pessoa aceitou | tabela `bases` | perdia | fica salvo |
| Antibióticos, nome em português, modelo padrão | tabela `antibioticos` | perdia | fica salvo |
| Avisos para a equipe | tabela `notificacoes` | perdia | fica salvo |
| CSVs que as pessoas enviam (`dados/enviadas/`) | disco + cópia na tabela `arquivos` | perdia | fica salvo |
| Modelos que as pessoas treinam (`plataforma/modelos/<base>/`) | disco + cópia na tabela `arquivos` | perdia | fica salvo |
| Base de fábrica e os 6 modelos iniciais | no repositório | já vinha no deploy | igual |

**Atenção ao espaço:** os CSVs enviados ocupam o 1 GB do Neon. Cada um pode ter até
120 MB (`MAX_MB_BASE` em `config.py`), e cada pesquisador pode ter até 3 bases
(`MAX_BASES_POR_PESQUISADOR`). Na prática cabem algumas bases grandes; se o espaço
apertar, dá para baixar esses limites.

---

## 5. O que foi mudado no código

### `plataforma/api/config.py` — onde está o banco

Nova função `url_banco()`:

- Se existir a variável de ambiente **`DATABASE_URL`**, o banco é o Postgres dela.
- Se não existir, é o SQLite de sempre, `plataforma/bionalya.db`.

Ela também reescreve `postgres://` e `postgresql://` para `postgresql+psycopg://`, que é
o formato que o SQLAlchemy precisa para usar o driver instalado (psycopg 3). Assim dá
para colar a URL do Neon exatamente como ele entrega.

### `plataforma/api/banco.py` — funcionar nos dois bancos

- A conexão é criada por `_criar_motor()`. No Postgres usa `pool_pre_ping` (testa a
  conexão antes de usar; o Neon fecha conexão parada quando cochila) e `pool_recycle`.
- A migração automática (`migrar()`) usava um comando que só existe no SQLite
  (`PRAGMA table_info`). Agora usa o `inspect` do SQLAlchemy, que funciona nos dois.
  Continua só **acrescentando** colunas que faltam, sem apagar nada.
- As datas passaram a ser `DateTime(timezone=True)`: no Postgres ficam gravadas com fuso
  (UTC). No SQLite não muda nada.
- Tabela nova, **`arquivos`**: caminho do arquivo, conteúdo (bytes), tamanho e data.

### `plataforma/api/arquivos.py` — novo: cópia dos arquivos no banco

O banco guarda as informações, mas os CSVs e os modelos treinados são **arquivos**, e o
disco do Render é apagado. Este módulo resolve isso sem precisar de outro serviço:

1. **Quando a plataforma grava** um CSV enviado ou um modelo treinado, o arquivo vai
   também para a tabela `arquivos` (`guardar`).
2. **Quando uma base é removida**, as cópias dela e dos modelos dela saem do banco
   (`apagar`, `apagar_pasta`).
3. **Quando a API sobe**, antes de qualquer outra coisa, recria no disco o que está no
   banco e falta no disco (`restaurar`).

O resto do código continua lendo do disco, como sempre.

Liga e desliga sozinho: **ligado com Postgres, desligado com SQLite** (na sua máquina o
disco já é permanente, e copiar CSV para dentro do `bionalya.db` só dobraria o espaço).
Para forçar, `BIONALYA_ARQUIVOS_NO_BANCO=1` liga e `=0` desliga.

### `plataforma/api/main.py` — os pontos que avisam o módulo

- Na partida: `arquivos.restaurar()` antes de semear os antibióticos.
- No envio de base (`POST /api/bases`): `arquivos.guardar(...)` do CSV.
- No treino (`POST /api/antibioticos/treinar`): `arquivos.guardar(...)` do `.joblib` e
  do `.json`.
- Na remoção de base (`DELETE /api/bases/{id}`): apaga as cópias do CSV e dos modelos.

### `plataforma/requirements.txt`

Acrescentado `psycopg[binary]==3.3.6`, o driver do PostgreSQL. O `[binary]` já traz
tudo junto; não precisa instalar nada no sistema.

### `plataforma/Dockerfile`

O comando de partida ganhou um `exec`. Antes, o `sh` ficava entre a hospedagem e o
uvicorn e não repassava o aviso de parada (SIGTERM): a hospedagem esperava e acabava
matando o processo à força. Agora o uvicorn recebe o aviso e desliga sozinho, em menos
de meio segundo (testado). Não perdia dado, mas cada reinício ficava mais lento.

### `render.yaml`

- `DATABASE_URL` com `sync: false`: o Render **pede o valor** na hora de criar o
  serviço. Ele não fica escrito no arquivo porque contém a senha do banco.
- Nenhum banco do Render é criado (ver seção 3).

---

## 6. Como foi testado

Tudo rodado de verdade, num Postgres 17 em container e com a imagem Docker do projeto.

**Simulação do disco descartável** — três rodadas; entre elas a cópia do servidor era
apagada e recriada do zero, e só o banco ficava:

| Rodada | O que foi verificado | Resultado |
|---|---|---|
| 1 | login do admin, criar usuária, enviar base, treinar ciprofloxacino, prever | ok |
| 2 (disco novo) | CSV e modelo recriados no disco; login antigo ainda vale; usuária entra; base listada; download idêntico ao enviado; **mesma probabilidade** de antes; remover a base | ok |
| 3 (disco novo) | o que foi removido **não** volta | ok |

17 de 17 verificações passaram.

**Imagem Docker** (a mesma que o Render roda): enviar base, treinar tetraciclina, parar o
container, subir um container novo — os 3 arquivos foram recriados e a previsão
respondeu.

**SQLite na máquina**: a API sobe, cria o `bionalya.db` com as 6 tabelas e os 6
antibióticos, e mantém tudo entre reinícios.

---

## 7. Como rodar na sua máquina

Nada muda: sem `DATABASE_URL`, usa o SQLite.

```bash
python -m venv .venv               # só na primeira vez
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r plataforma/requirements.txt
cd plataforma
python -m uvicorn api.main:app --reload
```

Abra <http://127.0.0.1:8000>. Na primeira vez, o login de admin fica em
`plataforma/PRIMEIRO-ACESSO.txt` (não vai para o GitHub).

Para testar contra o Neon na sua máquina, é só definir a variável antes de subir:

```bash
export DATABASE_URL='postgresql://usuario:senha@ep-xxxx.sa-east-1.aws.neon.tech/neondb?sslmode=require'
python -m uvicorn api.main:app --reload
```

---

## 8. Como publicar (Neon + Render)

### 8.1 Criar o banco no Neon

1. Entre em [neon.com](https://neon.com) e crie uma conta (dá para entrar com GitHub).
   Não pede cartão.
2. Crie um projeto. Nome: `bionalya`. Região: a mais próxima do servidor do Render
   (o `render.yaml` usa **Oregon**, então escolha **US West (Oregon)**).
3. No painel do projeto, clique em **Connect** e copie a *connection string*. Ela tem
   esta cara:
   ```
   postgresql://neondb_owner:SENHA@ep-xxxx-xxxx.us-west-2.aws.neon.tech/neondb?sslmode=require
   ```
   **Guarde como senha.** Quem tem essa linha tem acesso ao banco inteiro.

Não precisa criar tabela nenhuma: a API cria tudo sozinha na primeira vez que sobe.

### 8.2 Ligar no Render

- **Serviço novo:** em [dashboard.render.com](https://dashboard.render.com), *New →
  Blueprint*, aponte para o repositório. O Render vai pedir o valor de `DATABASE_URL`:
  cole a linha do Neon.
- **Serviço que já existe:** abra o serviço → *Environment* → *Add Environment
  Variable* → chave `DATABASE_URL`, valor a linha do Neon → *Save*. O Render reinicia
  sozinho.

No log do primeiro deploy deve aparecer `Admin criado a partir das variáveis de
ambiente`. A senha do admin está em *Environment*, na variável `BIONALYA_ADMIN_SENHA`.

### 8.3 Conferir

Cadastre algo, espere o serviço dormir (15 minutos sem acesso) ou clique em
*Manual Deploy → Restart*, e entre de novo: tem que estar tudo lá. Quando há arquivos
para recriar, o log mostra `N arquivo(s) recriados a partir do banco.`

---

## 9. Variáveis de ambiente

| Variável | Para quê |
|---|---|
| `DATABASE_URL` | o Postgres (Neon). Sem ela, usa o `bionalya.db` local |
| `BIONALYA_ARQUIVOS_NO_BANCO` | `1`/`0` força ligar/desligar a cópia dos arquivos no banco. Padrão: ligada com Postgres, desligada com SQLite |
| `BIONALYA_ADMIN_EMAIL` | e-mail da conta de admin |
| `BIONALYA_ADMIN_SENHA` | senha dela. Em branco = sorteada e gravada em `PRIMEIRO-ACESSO.txt` |
| `BIONALYA_DEMO_EMAIL` / `_SENHA` / `_NOME` | conta aberta de demonstração (opcional) |

Com o banco persistente, a conta de admin só é criada **uma vez**. Se depois você trocar
a senha pela tela *Minha conta*, vale a nova — mudar `BIONALYA_ADMIN_SENHA` no painel
não altera uma conta que já existe.

---

## 10. Limites e cuidados

- **1 GB no Neon.** Usuários e modelos ocupam pouco; o que pesa são os CSVs enviados.
- **Sem backup automático no plano grátis.** Para uma cópia de segurança, rode na sua
  máquina (precisa do `pg_dump` instalado):
  `pg_dump "$DATABASE_URL" > backup-bionalya.sql`
- **A connection string é segredo.** Não coloque no `render.yaml`, no README nem em
  commit.
- **Migração automática só acrescenta coluna.** Remover coluna ou mudar tipo pede uma
  migração de verdade (Alembic).
- **Planos grátis mudam.** Os números deste documento foram conferidos em novembro de
  2026.
