"""E-mails que a própria plataforma manda.

Os de login (confirmar cadastro, nova senha) quem manda é o Supabase. Estes são
os avisos do fluxo de aprovação: acesso liberado, acesso recusado, conta criada
pelo admin. Saem pelo mesmo SMTP configurado no Supabase (Gmail, no plano
grátis), direto da API.

Mandar e-mail nunca derruba a operação que o gerou: a rota responde primeiro e
o envio roda depois, em segundo plano (BackgroundTasks do FastAPI). Se falhar,
fica só o registro no log.
"""

from __future__ import annotations

import html
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from . import config


def configurado() -> bool:
    return bool(config.SMTP_HOST and config.SMTP_USUARIO and config.SMTP_SENHA)


def enviar(para: str, assunto: str, texto: str, botao: tuple[str, str] | None = None) -> bool:
    """Manda um e-mail simples, em texto e em HTML. Devolve se saiu."""
    if not configurado() or not para:
        return False
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = formataddr((config.SMTP_NOME, config.SMTP_REMETENTE))
    msg["To"] = para
    msg["Message-ID"] = make_msgid(domain=config.SMTP_REMETENTE.split("@")[-1])

    corpo = texto
    if botao:
        corpo += f"\n\n{botao[0]}: {botao[1]}"
    corpo += ("\n\n—\nBionalya · protótipo de pesquisa, sem validação clínica.\n"
              "Projeto Interdisciplinar I · Centro Universitário Dom Helder")
    msg.set_content(corpo)
    msg.add_alternative(_html(assunto, texto, botao), subtype="html")

    try:
        contexto = ssl.create_default_context()
        if config.SMTP_PORTA == 465:
            with smtplib.SMTP_SSL(config.SMTP_HOST, 465, context=contexto, timeout=20) as s:
                s.login(config.SMTP_USUARIO, config.SMTP_SENHA)
                s.send_message(msg)
        else:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORTA, timeout=20) as s:
                s.starttls(context=contexto)
                s.login(config.SMTP_USUARIO, config.SMTP_SENHA)
                s.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as e:
        print(f"[correio] não foi possível mandar '{assunto}' para {para}: {e}")
        return False


def _html(assunto: str, texto: str, botao: tuple[str, str] | None) -> str:
    """O mesmo visual dos e-mails de login (ver supabase/emails/)."""
    paragrafos = "".join(
        f'<p style="margin:0 0 16px">{html.escape(p).replace(chr(10), "<br>")}</p>'
        for p in texto.split("\n\n"))
    acao = ""
    if botao:
        rotulo, link = (html.escape(botao[0]), html.escape(botao[1], quote=True))
        acao = (f'<p style="margin:24px 0"><a href="{link}" style="background:#301A4B;'
                'color:#FFFFFF;text-decoration:none;padding:12px 20px;border-radius:8px;'
                f'font-weight:bold;display:inline-block">{rotulo}</a></p>'
                '<p style="margin:0 0 16px;font-size:13px;color:#5B4A70">Se o botão não '
                f'abrir, copie o endereço: <br>{link}</p>')
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><body style="margin:0;padding:0;background:#FFEAEC">
<div style="max-width:560px;margin:0 auto;padding:32px 16px;font-family:'Atkinson Hyperlegible',Verdana,Arial,sans-serif;font-size:16px;line-height:1.5;color:#301A4B">
  <p style="margin:0 0 24px;font-size:20px;font-weight:bold;color:#301A4B">Bionalya</p>
  <div style="background:#FFFFFF;border-radius:12px;padding:24px">
    <h1 style="margin:0 0 16px;font-size:22px">{html.escape(assunto)}</h1>
    {paragrafos}{acao}
  </div>
  <p style="margin:24px 0 0;font-size:13px;color:#5B4A70">Bionalya · protótipo de pesquisa,
  sem validação clínica.<br>Projeto Interdisciplinar I · Centro Universitário Dom Helder</p>
</div></body></html>"""


# --------------------------------------------------------------------------- #
# Os avisos do fluxo de acesso
# --------------------------------------------------------------------------- #

def acesso_liberado(para: str, nome: str) -> bool:
    primeiro = (nome or "").split(" ")[0] or "Olá"
    return enviar(
        para, "Seu acesso à Bionalya foi liberado",
        f"{primeiro}, a equipe conferiu seu cadastro e liberou o acesso.\n\n"
        "Entre com o e-mail e a senha que você escolheu no cadastro.",
        ("Entrar na Bionalya", f"{config.SITE_URL}/login.html"))


def acesso_recusado(para: str, nome: str, motivo: str | None) -> bool:
    primeiro = (nome or "").split(" ")[0] or "Olá"
    texto = (f"{primeiro}, a equipe analisou seu pedido de acesso à Bionalya e "
             "não pôde liberar agora.")
    if motivo:
        texto += f"\n\nMotivo: {motivo}"
    texto += ("\n\nSe achar que foi engano, responda este e-mail contando seu "
              "vínculo com a pesquisa.")
    return enviar(para, "Sobre o seu pedido de acesso à Bionalya", texto)


def conta_criada(para: str, nome: str, por: str) -> bool:
    primeiro = (nome or "").split(" ")[0] or "Olá"
    return enviar(
        para, "Criaram uma conta para você na Bionalya",
        f"{primeiro}, {por} criou uma conta para você na Bionalya, a plataforma de "
        "previsão de resistência bacteriana do Projeto Interdisciplinar.\n\n"
        "A senha inicial vem por quem criou a conta. Se preferir, defina a sua "
        "pelo link “Esqueci minha senha” na tela de entrada.",
        ("Entrar na Bionalya", f"{config.SITE_URL}/login.html"))
