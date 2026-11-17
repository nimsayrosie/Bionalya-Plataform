"""Configura o login do projeto no Supabase, de uma vez.

O que ele ajusta (em Authentication, no painel do Supabase):
  · endereço do site e endereços para onde os links dos e-mails podem voltar
  · confirmação de e-mail ligada, senha com pelo menos 8 caracteres
  · SMTP próprio (Gmail), para os e-mails chegarem a qualquer pessoa — sem
    ele, o Supabase só manda para quem é da equipe do projeto, e poucos por hora
  · modelos de e-mail em português (supabase/emails/), com o link apontando
    para as telas confirmar-email.html e redefinir-senha.html

Como rodar, da pasta plataforma/:

    python supabase/configurar.py            # mostra o que vai mudar
    python supabase/configurar.py --aplicar  # muda

Lê do ambiente (ou do .env): SUPABASE_ACCESS_TOKEN (token pessoal, gerado em
supabase.com/dashboard/account/tokens), SUPABASE_URL, SITE_URL, SMTP_HOST,
SMTP_PORTA, SMTP_USUARIO, SMTP_SENHA e, se quiser, SMTP_REMETENTE e SMTP_NOME.

O token pessoal dá acesso a todos os seus projetos no Supabase: use aqui, na
sua máquina, e não ponha no Render nem em commit.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import httpx

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
from api import config  # noqa: E402  (lê o .env)

API = "https://api.supabase.com/v1"


def _falta(*nomes: str) -> list[str]:
    return [n for n in nomes if not os.getenv(n)]


def desejado() -> dict:
    site = config.SITE_URL
    permitidos = [f"{site}/**", "http://127.0.0.1:8000/**", "http://localhost:8000/**"]
    cfg = {
        "site_url": site,
        "uri_allow_list": ",".join(dict.fromkeys(permitidos)),
        "disable_signup": False,
        "external_email_enabled": True,
        "mailer_autoconfirm": False,          # confirmação de e-mail ligada
        "password_min_length": 8,
        "mailer_otp_exp": 3600,               # link vale uma hora
        "mailer_subjects_confirmation": "Confirme seu e-mail na Bionalya",
        "mailer_templates_confirmation_content":
            (AQUI / "emails" / "confirmacao.html").read_text(encoding="utf-8"),
        "mailer_subjects_recovery": "Sua senha nova na Bionalya",
        "mailer_templates_recovery_content":
            (AQUI / "emails" / "recuperacao.html").read_text(encoding="utf-8"),
    }
    if config.SMTP_HOST:
        cfg.update({
            "smtp_host": config.SMTP_HOST,
            "smtp_port": str(config.SMTP_PORTA),
            "smtp_user": config.SMTP_USUARIO,
            "smtp_pass": config.SMTP_SENHA,
            "smtp_admin_email": config.SMTP_REMETENTE,
            "smtp_sender_name": config.SMTP_NOME,
            "smtp_max_frequency": 60,          # 1 e-mail por minuto por pessoa
            "rate_limit_email_sent": 30,       # por hora, no projeto todo
        })
    return cfg


def main() -> int:
    aplicar = "--aplicar" in sys.argv
    faltando = _falta("SUPABASE_ACCESS_TOKEN", "SUPABASE_URL", "SITE_URL")
    if faltando:
        print("Faltam no ambiente (ou no .env): " + ", ".join(faltando))
        return 1
    m = re.match(r"https://([a-z0-9]+)\.supabase\.co", config.SUPABASE_URL)
    if not m:
        print(f"SUPABASE_URL não parece de um projeto do Supabase: {config.SUPABASE_URL}")
        return 1
    ref = m.group(1)
    if not config.SMTP_HOST:
        print("AVISO: sem SMTP_HOST, o Supabase continua com o e-mail de teste dele, "
              "que só entrega para quem é da equipe do projeto.\n")

    cab = {"Authorization": f"Bearer {os.environ['SUPABASE_ACCESS_TOKEN']}"}
    with httpx.Client(base_url=API, headers=cab, timeout=30) as c:
        r = c.get(f"/projects/{ref}/config/auth")
        if r.status_code != 200:
            print(f"Não deu para ler a configuração ({r.status_code}): {r.text[:300]}")
            return 1
        atual = r.json()
        quero = desejado()

        # Só manda o que a API conhece: nome de campo errado viraria erro.
        desconhecidos = [k for k in quero if k not in atual]
        for k in desconhecidos:
            print(f"  (ignorado, a API não tem este campo: {k})")
            quero.pop(k)

        mudancas = {k: v for k, v in quero.items() if atual.get(k) != v}
        if not mudancas:
            print("Nada a mudar: o projeto já está configurado.")
            return 0
        for k, v in mudancas.items():
            mostrar = "••••" if k == "smtp_pass" else (
                f"{len(v)} caracteres" if isinstance(v, str) and len(v) > 80 else v)
            print(f"  {k}: {mostrar}")

        if not aplicar:
            print("\nNada foi mudado. Rode de novo com --aplicar para mudar.")
            return 0
        r = c.patch(f"/projects/{ref}/config/auth", json=mudancas)
        if r.status_code >= 300:
            print(f"\nO Supabase recusou ({r.status_code}): {r.text[:500]}")
            return 1
        print(f"\nPronto: {len(mudancas)} configuração(ões) aplicadas.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
