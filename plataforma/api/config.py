"""Caminhos e constantes da Bionalya. Mexa só aqui para mudar onde as coisas ficam."""

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent      # .../plataforma
PROJETO = RAIZ.parent                              # raiz do repositório

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

# A base que vem de fábrica. O CSV completo (32 MB) não é versionado; a amostra
# com os isolados que têm antibiograma é, para a plataforma funcionar logo depois
# de clonar e nas hospedagens onde não dá para subir 32 MB.
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


# Sessão expira em 12 horas. Protótipo: sem refresh token.
HORAS_SESSAO = 12

# ---------------------------------------------------------------------------
# Contas semeadas por variável de ambiente.
#
# Na sua máquina, deixe em branco: a API gera uma senha aleatória e grava em
# PRIMEIRO-ACESSO.txt. Numa hospedagem grátis o disco some a cada reinício, e
# o banco vai junto — lá vale definir estas variáveis no painel do serviço,
# para o admin e o convidado existirem sempre com a mesma senha.
# ---------------------------------------------------------------------------
ADMIN_EMAIL = os.getenv("BIONALYA_ADMIN_EMAIL", "equipe@bionalya.app")
ADMIN_SENHA = os.getenv("BIONALYA_ADMIN_SENHA") or None

DEMO_EMAIL = os.getenv("BIONALYA_DEMO_EMAIL") or None
DEMO_SENHA = os.getenv("BIONALYA_DEMO_SENHA") or None
DEMO_NOME = os.getenv("BIONALYA_DEMO_NOME", "Acesso de demonstração")
