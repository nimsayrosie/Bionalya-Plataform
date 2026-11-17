"""Caminhos e constantes da Bionalya. Mexa só aqui para mudar onde as coisas ficam."""

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent      # .../plataforma
PROJETO = RAIZ.parent                              # raiz do repositório


def _ler_env() -> None:
    """Lê plataforma/.env (ou o da raiz) para os.environ, sem sobrescrever.

    Na hospedagem as variáveis vêm do painel; isto é para a sua máquina, onde
    copiar .env.example para .env e preencher basta. Formato CHAVE=valor, uma
    por linha; # começa comentário.
    """
    for arquivo in (RAIZ / ".env", PROJETO / ".env"):
        if not arquivo.exists():
            continue
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            valor = valor.strip()
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
                valor = valor[1:-1]
            os.environ.setdefault(chave.strip(), valor)


_ler_env()

PASTA_MODELOS = RAIZ / "modelos"                   # modelos/<base>/<antibiotico>.joblib
PASTA_WEB = RAIZ / "web"                           # html, css, js
BANCO = RAIZ / "bionalya.db"                       # só quando não há DATABASE_URL


def url_banco() -> str:
    """Onde está o banco. DATABASE_URL ganha; sem ela, o SQLite local.

    O Render (e quase toda hospedagem) entrega a URL como postgres://... ou
    postgresql://..., que o SQLAlchemy entenderia como o driver antigo,
    psycopg2. Aqui ela é reescrita para o psycopg 3, que é o instalado.
    """
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{BANCO}"
    for prefixo in ("postgres://", "postgresql://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url[len(prefixo):]
    return url

PASTA_DADOS = PROJETO / "dados"                    # bases CSV
PASTA_ENVIADAS = PASTA_DADOS / "enviadas"          # as que alguém subiu pela plataforma

# A base que vem de fábrica. As duas estão no repositório: a completa (31 MB) e a
# amostra com os isolados que têm antibiograma. A imagem Docker leva só a
# amostra (ver .dockerignore), que é o que a hospedagem usa.
BASE_PADRAO = "neisseria-gonorrhoeae"
ARQUIVOS_BASE_PADRAO = (
    "neisseria-gonorrheae.csv",                 # completa, baixada do NCBI
    "amostra-neisseria-gonorrhoeae.csv",        # versionada, só com antibiograma
)


def arquivo_base_padrao() -> str:
    """O primeiro arquivo da lista que existir. A completa ganha da amostra."""
    for nome in ARQUIVOS_BASE_PADRAO:
        if (PASTA_DADOS / nome).exists():
            return nome
    return ARQUIVOS_BASE_PADRAO[0]


ARQUIVO_BASE_PADRAO = arquivo_base_padrao()
CAMINHO_BASE = PASTA_DADOS / ARQUIVO_BASE_PADRAO   # compatibilidade

ESPECIE_PADRAO = "Neisseria gonorrhoeae"

# Limites do upload de base
MAX_MB_BASE = 120
MIN_LINHAS_BASE = 30

# Quantas bases um pesquisador pode ter ao mesmo tempo, contando as que ainda
# estão em análise. A equipe não tem limite. Sem isso, o disco acaba.
MAX_BASES_POR_PESQUISADOR = 3

# ---------------------------------------------------------------------------
# Dados pessoais (LGPD). As regras estão em docs/requisitos-lgpd.md; se mudar
# um número aqui, mude lá também.
# ---------------------------------------------------------------------------
# Quanto tempo o histórico de análises de cada pessoa fica guardado.
RETENCAO_ANALISES_DIAS = 90
# Conta desativada há mais que isso é apagada sozinha (login, cadastro,
# histórico). As bases que a pessoa enviou ficam, sem dono.
RETENCAO_CONTA_DESATIVADA_DIAS = 365
# Texto do consentimento pedido no cadastro. A versão fica gravada junto.
CONSENTIMENTO_VERSAO = "2026-11"
# Montado a partir do prazo acima: o texto aceito nunca contradiz o que a
# plataforma faz. Mudou o prazo? Suba também CONSENTIMENTO_VERSAO.
CONSENTIMENTO = (
    "Autorizo a Bionalya a guardar meu nome, e-mail, instituição, vínculo e a "
    "finalidade que declarei, só para liberar e identificar meu acesso, e o "
    f"histórico das minhas análises por {RETENCAO_ANALISES_DIAS} dias. Sei que "
    "esses dados ficam em servidores do Supabase, nos Estados Unidos, e que posso "
    "pedir para apagar minha conta a qualquer momento."
)

# Envio do arquivo de um isolado na Nova análise: lido em memória, nunca
# gravado. Limites para um arquivo de um isolado, não de uma base inteira.
MAX_MB_ISOLADO = 5
MAX_ISOLADOS_NO_ARQUIVO = 500

# Termo que quem envia uma base precisa aceitar. A versão é guardada junto com
# o aceite: se o texto mudar, dá para saber o que a pessoa leu de fato.
TERMO_BASE_VERSAO = "2026-11"
TERMO_BASE = (
    "Declaro que tenho autorização para usar os dados deste arquivo, que ele "
    "não contém informação que identifique pacientes (nome, documento, "
    "prontuário, endereço ou data de nascimento) e que assumo a "
    "responsabilidade pelo que envio. A Bionalya é um protótipo acadêmico sem "
    "validação clínica."
)

# Nomes em português para o que vem em inglês do NCBI.
NOMES_PT = {
    "ciprofloxacin": "Ciprofloxacino",
    "ceftriaxone": "Ceftriaxona",
    "cefixime": "Cefixima",
    "tetracycline": "Tetraciclina",
    "azithromycin": "Azitromicina",
    "penicillin": "Penicilina",
    "benzylpenicillin": "Benzilpenicilina",
    "spectinomycin": "Espectinomicina",
    "zoliflodacin": "Zoliflodacina",
    "cefoxitin": "Cefoxitina",
    "cefotaxime": "Cefotaxima",
    "cefepime": "Cefepima",
    "gentamicin": "Gentamicina",
    "erythromycin": "Eritromicina",
    "ertapenem": "Ertapeném",
}


def nome_pt(nome_base: str) -> str:
    return NOMES_PT.get(str(nome_base).lower(), str(nome_base).capitalize())


# ---------------------------------------------------------------------------
# Login: Supabase Auth.
#
# O Supabase guarda e-mail e senha, manda os e-mails de confirmação e de
# recuperação de senha e entrega o token de sessão. O resto do cadastro (papel,
# status, instituição) continua na tabela usuarios, no nosso banco.
#
#   SUPABASE_URL          https://<ref>.supabase.co
#   SUPABASE_ANON_KEY     chave pública (anon / publishable)
#   SUPABASE_SERVICE_KEY  chave secreta (service_role / secret). Só no servidor:
#                         cria as contas de admin, de demonstração e as que o
#                         admin cria pela tela, e troca senha pelo admin.
#   SUPABASE_JWT_SECRET   opcional. Só para projeto antigo, com JWT assinado por
#                         segredo (HS256). Projeto novo usa chave assimétrica, e
#                         a API confere o token pela chave pública do projeto.
# ---------------------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
SUPABASE_SERVICE_KEY = (os.getenv("SUPABASE_SERVICE_KEY")
                        or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "").strip()

# Endereço público do site. Entra nos links dos e-mails (confirmar cadastro,
# redefinir senha). Na sua máquina, o próprio uvicorn.
SITE_URL = (os.getenv("SITE_URL") or "http://127.0.0.1:8000").strip().rstrip("/")

# ---------------------------------------------------------------------------
# E-mail que a própria plataforma manda (acesso liberado ou recusado).
#
# Os e-mails de login (confirmação, nova senha) quem manda é o Supabase, pelo
# SMTP configurado no painel dele. Estes aqui saem direto da API, pelo mesmo
# SMTP. Sem SMTP_HOST, a plataforma funciona igual e só não manda o aviso.
#
# Com Gmail: smtp.gmail.com, porta 587, o endereço completo como usuário e uma
# "senha de app" (não a senha da conta). Passo a passo em
# docs/banco-e-hospedagem.md.
# ---------------------------------------------------------------------------
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORTA = int(os.getenv("SMTP_PORTA") or os.getenv("SMTP_PORT") or 587)
SMTP_USUARIO = os.getenv("SMTP_USUARIO") or os.getenv("SMTP_USER") or ""
SMTP_SENHA = (os.getenv("SMTP_SENHA") or os.getenv("SMTP_PASS") or "").replace(" ", "")
SMTP_REMETENTE = os.getenv("SMTP_REMETENTE") or SMTP_USUARIO
SMTP_NOME = os.getenv("SMTP_NOME") or "Bionalya"

# ---------------------------------------------------------------------------
# Contas semeadas por variável de ambiente.
#
# O admin existe sempre. Sem BIONALYA_ADMIN_SENHA, a API sorteia uma senha na
# primeira vez e grava em PRIMEIRO-ACESSO.txt (que não é versionado). Se a conta
# já existir no Supabase, a senha dela não é mexida, a não ser que a variável
# esteja definida.
# ---------------------------------------------------------------------------
ADMIN_EMAIL = (os.getenv("BIONALYA_ADMIN_EMAIL") or "equipe@bionalya.app").strip().lower()
ADMIN_SENHA = os.getenv("BIONALYA_ADMIN_SENHA") or None

DEMO_EMAIL = (os.getenv("BIONALYA_DEMO_EMAIL") or "").strip().lower() or None
DEMO_SENHA = os.getenv("BIONALYA_DEMO_SENHA") or None
DEMO_NOME = os.getenv("BIONALYA_DEMO_NOME") or "Acesso de demonstração"
