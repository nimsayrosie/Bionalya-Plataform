# Banco, login, e-mail e hospedagem da Bionalya

Onde a Bionalya guarda as informações, quem cuida do login, como os e-mails saem, o que
é grátis e o que tem prazo. No fim tem o passo a passo para rodar e para publicar.

---

## 1. Em uma frase

O site roda no **Render** (grátis), o banco e o login ficam no **Supabase** (grátis) e
os e-mails saem por uma **conta Gmail do projeto** (grátis). Nada disso pede cartão.

---

## 2. As peças

```
                 pessoa no navegador
                          │  só fala com a nossa API
                          ▼
   ┌───────────────────────────────────────────┐
   │ RENDER — API e telas (grátis)             │
   │ disco APAGADO a cada reinício ou cochilo  │
   └──────┬───────────────────────┬────────────┘
          │ DATABASE_URL          │ SUPABASE_URL + chaves
          ▼                       ▼
   ┌───────────────────────────────────────────┐
   │ SUPABASE (grátis)                         │
   │  · Postgres: usuários, bases, modelos,    │
   │    avisos, cópia dos CSVs e .joblib       │
   │  · Auth: e-mail, senha, confirmação,      │
   │    link de senha nova, token de sessão    │──┐
   └───────────────────────────────────────────┘  │ SMTP
                                                  ▼
                                   ┌──────────────────────────┐
                                   │ GMAIL do projeto         │
                                   │ (senha de app)           │──► caixa de entrada
                                   └──────────────────────────┘
                     a API também manda por ele os avisos de
                     "acesso liberado" e "acesso recusado"
```

As telas nunca falam com o Supabase direto: tudo passa pela API. As chaves do Supabase
e a senha do Gmail ficam só no servidor.

### Render — o servidor

- 750 horas por mês, o suficiente para ficar ligado o mês inteiro.
- **Dorme depois de 15 minutos** sem acesso. A primeira visita depois disso leva cerca
  de 1 minuto.
- **O disco é apagado** a cada reinício, atualização e cochilo. Por isso nada fica
  guardado nele: o banco está no Supabase e os arquivos (CSVs enviados, modelos
  treinados) têm uma cópia no banco, que a API recria no disco quando sobe
  (`plataforma/api/arquivos.py`).

### Supabase — banco e login

- Plano grátis permanente, sem cartão. Até **2 projetos**.
- **500 MB** de banco. Usuários e modelos ocupam pouco; o que pesa são os CSVs enviados.
- **Pausa o projeto depois de 7 dias sem uso.** Pausado, o banco e o login param e o
  site inteiro fica fora do ar até alguém clicar em *Restore* no painel. Para isso não
  acontecer, o GitHub Actions abre `/saude` duas vezes por semana
  (`.github/workflows/manter-acordado.yml`), e essa visita faz uma consulta ao banco.
- **Sem backup no plano grátis.** Ver seção 8.

### Gmail — os e-mails

O Supabase tem um envio de e-mail de teste, mas ele só entrega para quem é da equipe do
projeto no Supabase, e poucos por hora. Para chegar a qualquer pessoa é preciso um SMTP
próprio. Sem domínio próprio, o caminho grátis que entrega bem é o Gmail:

- uma conta Gmail só do projeto, com verificação em duas etapas e uma **senha de app**;
- até cerca de **500 e-mails por dia**;
- sai pelos servidores do Google, assinado pelo próprio Gmail: cai na caixa de entrada,
  não no spam.

Serviços como Resend e SendGrid pedem domínio próprio para mandar a qualquer pessoa, por
isso não foram usados.

### O que custa

| Peça | Onde | Custo | Prazo |
|---|---|---|---|
| API e telas | Render, plano grátis | nenhum | nenhum |
| Banco e login | Supabase, plano grátis | nenhum | pausa com 7 dias parado (o ping evita) |
| E-mail | Gmail do projeto | nenhum | nenhum |
| Na sua máquina | `plataforma/bionalya.db` (SQLite) | nenhum | nenhum |

Planos grátis mudam: os números foram conferidos em novembro de 2026.

---

## 3. Como o login funciona

| Momento | O que acontece |
|---|---|
| **Cadastro** | A API cria a conta no Supabase, que manda o e-mail de confirmação. O pedido de acesso fica em análise na tabela `usuarios`. |
| **Confirmação** | O link abre `confirmar-email.html`; um clique confirma. O link usa `token_hash` e só é gasto no clique: o antivírus do e-mail, que abre todo link para conferir, não estraga nada. |
| **Análise** | A equipe libera ou recusa em `equipe.html`. A pessoa recebe um e-mail com a decisão. |
| **Login** | Precisa das duas coisas: e-mail confirmado e acesso liberado. |
| **Sessão** | O token do Supabase vale 1 hora. Quando vence, as telas trocam sozinhas o `refresh_token` por um novo (`app.js`). |
| **Esqueci a senha** | `esqueci-senha.html` → e-mail com link → `redefinir-senha.html`. Salvar a senha nova derruba as outras sessões. Se o e-mail não sair, o pedido vira aviso para a equipe, e um admin gera uma senha em *Usuários*. |
| **Senha definida por outra pessoa** | Quem entra com senha que o admin gerou (ou com que criou a conta) vê um pop-up obrigatório para trocar. A API recusa as outras rotas até a troca. |
| **Desativar ou recusar** | Corta o acesso na hora: toda rota confere o status na tabela `usuarios`. |

O que fica onde:

| Informação | Onde |
|---|---|
| E-mail e senha (hash bcrypt) | Supabase Auth |
| Nome, instituição, vínculo, finalidade, papel, status | tabela `usuarios` (coluna `auth_id` liga as duas) |
| Bases, antibióticos, avisos, cópia dos arquivos | tabelas `bases`, `antibioticos`, `notificacoes`, `arquivos` |

**API REST do Supabase fechada.** O Supabase publica toda tabela do schema `public`
numa API REST, e a chave pública dela não é segredo. A API da Bionalya liga o RLS em
todas as tabelas, sem nenhuma política, na partida: a API REST não vê nada, e a nossa
API continua lendo tudo, porque conecta como dona das tabelas.

---

## 4. Como rodar na sua máquina

```bash
python -m venv .venv               # só na primeira vez
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r plataforma/requirements.txt
cd plataforma
cp .env.example .env               # e preencha (seção 6)
python -m uvicorn api.main:app --reload
```

Sem `DATABASE_URL` no `.env`, o banco é o SQLite local (`plataforma/bionalya.db`). O
login, esse, é sempre o do Supabase: sem `SUPABASE_URL` e as chaves, a API sobe, mas
ninguém entra. Peça o `.env` para quem cuida da hospedagem.

Na primeira vez, se `BIONALYA_ADMIN_SENHA` estiver vazia, a API sorteia a senha do admin
e grava em `plataforma/PRIMEIRO-ACESSO.txt` (não vai para o GitHub). Se a conta de admin
já existir no Supabase, a senha dela não é mexida.

### Testes

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Os testes usam um Supabase de mentira, em memória (`plataforma/testes/conftest.py`), e
um SQLite temporário: não precisam de chave nem de internet. Cobrem cadastro,
confirmação, aprovação, login, renovação de sessão, senha nova pelo link, troca
obrigatória, desativação e a conferência do token. O GitHub roda os mesmos testes a
cada push e pull request (`.github/workflows/testes.yml`).

---

## 5. Como publicar

### 5.1 A conta Gmail do projeto

1. Crie uma conta Gmail só para a plataforma (por exemplo `bionalya.projeto@gmail.com`).
2. Ative a **verificação em duas etapas**: <https://myaccount.google.com/security>.
3. Gere uma **senha de app**: <https://myaccount.google.com/apppasswords>. Nome:
   `Bionalya`. Ele mostra 16 letras; guarde, é a `SMTP_SENHA`.

A senha de app só serve para mandar e-mail e pode ser apagada a qualquer momento na
mesma página, sem mexer na senha da conta.

### 5.2 O projeto no Supabase

1. Entre em <https://supabase.com/dashboard> (dá para entrar com GitHub) e crie um
   projeto. Nome `bionalya`; guarde a **senha do banco** que ele pede. Região: a mais
   perto do Render. O `render.yaml` usa Oregon, então **West US (North California)**.
2. **Chaves** — *Project Settings → API Keys*. Copie a chave pública (*publishable* ou
   *anon*) e a secreta (*secret* ou *service_role*). E a URL do projeto,
   `https://<ref>.supabase.co`.
3. **Endereço do banco** — botão **Connect** no topo → *Session pooler*. Copie a linha
   e troque `[YOUR-PASSWORD]` pela senha do banco. Use o *Session pooler* (porta 5432):
   a conexão direta é só IPv6, e o Render não sai por IPv6.

Não precisa criar tabela nenhuma: a API cria tudo na primeira vez que sobe.

### 5.3 Configurar o login (um comando)

Na sua máquina, com o `.env` preenchido (incluindo o Gmail e um **token pessoal** do
Supabase, gerado em <https://supabase.com/dashboard/account/tokens>):

```bash
cd plataforma
python supabase/configurar.py            # mostra o que vai mudar
python supabase/configurar.py --aplicar  # muda
```

Ele ajusta, em *Authentication*:

- endereço do site e endereços para onde os links podem voltar;
- confirmação de e-mail ligada, senha com pelo menos 8 caracteres, link válido por 1 hora;
- SMTP do Gmail, com limite de 30 e-mails por hora no projeto e 1 por minuto por pessoa;
- os modelos de e-mail em português (`plataforma/supabase/emails/`).

**Sem o script, pelo painel:** *Authentication → URL Configuration* (Site URL e
Redirect URLs), *Authentication → Emails → SMTP Settings* (host `smtp.gmail.com`,
porta `587`, usuário o Gmail completo, senha a senha de app), e *Authentication →
Emails → Templates*: em *Confirm signup* e *Reset password*, cole o HTML de
`plataforma/supabase/emails/confirmacao.html` e `recuperacao.html`. Os modelos padrão
do Supabase também funcionam (as telas entendem os dois formatos de link), mas vêm em
inglês.

### 5.4 Ligar no Render

Em *Environment* do serviço (ou, num serviço novo pelo *Blueprint*, quando o Render
pedir):

| Variável | Valor |
|---|---|
| `DATABASE_URL` | a linha do Session pooler |
| `SUPABASE_URL` | `https://<ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | a chave pública |
| `SUPABASE_SERVICE_KEY` | a chave secreta |
| `SITE_URL` | `https://bionalya-uvqh.onrender.com` (já vem no `render.yaml`) |
| `SMTP_HOST` / `SMTP_PORTA` | `smtp.gmail.com` / `587` (já vêm no `render.yaml`) |
| `SMTP_USUARIO` | o Gmail do projeto |
| `SMTP_SENHA` | a senha de app |
| `BIONALYA_ADMIN_EMAIL` | um e-mail que exista: é para ele que vai o link de senha nova |

O Render reinicia sozinho. Se faltar alguma variável do Supabase, o log da partida
avisa com uma linha `AVISO:`.

### 5.5 Conferir

1. Abra `https://bionalya-uvqh.onrender.com/saude`: tem que mostrar `"banco": true`,
   `"login": true` e `"email": true`.
2. Cadastre-se com um e-mail seu, confirme pelo link, libere pela conta de admin e
   entre. Chegam dois e-mails: a confirmação e o "acesso liberado".
3. Em *Esqueci minha senha*, peça o link e defina uma senha nova.
4. No GitHub, aba *Actions* → *Manter acordado* → *Run workflow*: tem que ficar verde.

---

## 6. Variáveis de ambiente

| Variável | Para quê |
|---|---|
| `DATABASE_URL` | o Postgres do Supabase (Session pooler). Sem ela, `bionalya.db` local |
| `SUPABASE_URL` | `https://<ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | chave pública do projeto |
| `SUPABASE_SERVICE_KEY` | chave secreta. Cria as contas de admin, demonstração e as que o admin cria, e troca senha pelo admin |
| `SUPABASE_JWT_SECRET` | só para projeto antigo, com JWT por segredo. Projeto novo não precisa |
| `SITE_URL` | endereço público; vai nos links dos e-mails |
| `SMTP_HOST`, `SMTP_PORTA`, `SMTP_USUARIO`, `SMTP_SENHA` | Gmail. Sem eles, a plataforma funciona, só não manda o aviso de acesso liberado/recusado |
| `SMTP_REMETENTE`, `SMTP_NOME` | opcionais. Padrão: o próprio Gmail e "Bionalya" |
| `BIONALYA_ADMIN_EMAIL` / `_SENHA` | conta de admin. Senha em branco = sorteada e gravada em `PRIMEIRO-ACESSO.txt` |
| `BIONALYA_DEMO_EMAIL` / `_SENHA` / `_NOME` | conta aberta de demonstração (opcional) |
| `BIONALYA_ARQUIVOS_NO_BANCO` | `1`/`0` força ligar/desligar a cópia dos arquivos no banco. Padrão: ligada com Postgres |
| `SUPABASE_ACCESS_TOKEN` | só para `supabase/configurar.py`, na sua máquina. **Nunca no Render** |

A conta de admin só é criada **uma vez**. Se depois a senha for trocada pela tela
*Minha conta*, vale a nova: mudar `BIONALYA_ADMIN_SENHA` no painel não mexe numa conta
que já existe.

---

## 7. Segurança e LGPD

- A **chave secreta**, a **senha do banco** e a **senha de app** do Gmail só no painel
  do Render e no `.env` local. Nunca no `render.yaml`, no README ou num commit.
- O **token pessoal** do Supabase dá acesso a todos os projetos da conta: só na sua
  máquina, e dá para apagar depois de configurar.
- Os dados ficam em servidores do Supabase nos Estados Unidos. Sob a LGPD isso é
  transferência internacional de dado pessoal (nome, e-mail, instituição), e entra na
  definição pendente de base legal e prazo de retenção. Para os dados ficarem no Brasil,
  o projeto do Supabase pode ser criado em **South America (São Paulo)**, ao custo de
  respostas mais lentas, porque o Render fica nos EUA.

---

## 8. Limites e cuidados

- **500 MB de banco.** Cada CSV enviado pode ter até 120 MB (`MAX_MB_BASE`) e cada
  pesquisador até 3 bases (`MAX_BASES_POR_PESQUISADOR`). Se apertar, baixe os limites.
- **Pausa com 7 dias parado.** O ping do GitHub evita. O GitHub desliga workflows
  agendados em repositório sem commit há 60 dias; se isso acontecer, a aba *Actions*
  tem um botão para religar.
- **Sem backup automático.** Para uma cópia, na sua máquina (precisa do `pg_dump`):
  `pg_dump "$DATABASE_URL" > backup-bionalya.sql`. O arquivo tem os dados de todo
  mundo: trate com o mesmo cuidado. As contas do login ficam no schema `auth`, que o
  `pg_dump` também leva.
- **E-mail:** cerca de 500 por dia pelo Gmail, e o limite configurado no Supabase é de
  30 e-mails de login por hora.
- **Migração automática só acrescenta coluna.** A única exceção é a troca para o
  Supabase: um banco com o login antigo (coluna `senha_hash`) tem `usuarios` e `sessoes`
  recriadas do zero na partida, porque o Supabase não importa senha em PBKDF2. Bases,
  modelos e avisos ficam.
