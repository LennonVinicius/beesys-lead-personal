import re
from urllib.parse import quote


def normalize_phone_br(phone):
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return None
    if digits.startswith("55") and len(digits) >= 12:
        return digits
    if len(digits) in {10, 11}:
        return "55" + digits
    return digits


def whatsapp_link(phone, message=""):
    digits = normalize_phone_br(phone)
    if not digits:
        return None
    suffix = f"?text={quote(message)}" if message else ""
    return f"https://wa.me/{digits}{suffix}"


def build_followup_message(lead, context="followup"):
    name = lead.get("contact_name") or ""
    greeting = f"Oi, {name}!" if name else "Olá!"
    business = lead.get("name") or "seu negócio"
    status = lead.get("pipeline_status") or "VISITED"

    if status == "INTERESTED":
        body = (
            f"Aqui é da BeeSys. Passando para continuar nossa conversa sobre o {business}. "
            "Posso te mostrar rapidamente como funcionaria o agendamento e a organização dos atendimentos no dia a dia?"
        )
    elif status == "DEMO":
        body = (
            f"Aqui é da BeeSys. Queria saber o que você achou da demonstração para o {business} "
            "e se ficou alguma dúvida sobre o funcionamento."
        )
    elif status == "PROPOSAL":
        body = (
            f"Aqui é da BeeSys. Estou retomando a proposta que conversamos para o {business}. "
            "Se quiser, posso revisar os pontos principais e ajustar o que for necessário."
        )
    else:
        body = (
            f"Aqui é da BeeSys. Nós conversamos recentemente sobre o {business} e queria retomar o contato. "
            "Posso te explicar em poucos minutos como a plataforma pode ajudar na organização do atendimento?"
        )
    return f"{greeting} {body}"


def compact_brief(lead):
    lines = []
    lines.append(lead.get("why_approach") or "Sem justificativa calculada.")
    if lead.get("manual_booking_detected"):
        lines.append(f"Agenda manual: {lead.get('manual_booking_channel') or 'detectada'}.")
    if lead.get("competitor_detected"):
        lines.append(f"Concorrente detectado: {lead.get('competitor_name') or 'sim'}.")
    if lead.get("rating") is not None:
        lines.append(f"Google: {lead.get('rating')}/5 / {lead.get('reviews') or 0} avaliações.")
    return " ".join(lines)
