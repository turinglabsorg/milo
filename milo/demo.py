import time
from email.message import EmailMessage
from email.utils import formatdate

from .mail import parse_message


def seed_demo(store):
    if store.accounts():
        return
    account_id = store.add_account({"name": "Personale", "email": "you@example.com", "username": "demo",
        "password": "demo-only", "imap_host": "demo.invalid", "imap_port": 993,
        "smtp_host": "demo.invalid", "smtp_port": 465, "smtp_security": "tls", "color": "#aca2ff"})
    samples = [
        ("Giulia Rossi", "giulia@example.com", "Un caffè e due idee per lunedì", "people", 8,
         "Ciao!\n\nHo messo insieme qualche idea per il nuovo progetto. Ti va di parlarne lunedì mattina, magari davanti a un caffè?\n\nMi piacerebbe partire dall'esperienza delle persone, poi scegliere la tecnologia. Ti allego mentalmente una lavagna piena di post-it.\n\nA presto,\nGiulia", True),
        ("Marco Bianchi", "marco@example.com", "Il design è pronto per il tuo feedback", "people", 42,
         "Ciao,\n\nLa prima versione del design è pronta. Ho semplificato la navigazione e dato più spazio alla lettura.\n\nQuando hai un momento, mi fai sapere cosa ne pensi? Possiamo rivederlo insieme domani.\n\nGrazie!\nMarco", False),
        ("Linear", "notifications@example.com", "Il tuo workspace, questa settimana", "updates", 76,
         "Il team ha completato 12 attività questa settimana.\n\n3 progetti sono in corso e 2 richieste aspettano il tuo feedback. Un buon momento per fare il punto e scegliere le prossime priorità.", False),
        ("Sara Conti", "sara@example.com", "Weekend fuori porta?", "people", 114,
         "Ehi!\n\nStavo pensando di andare al mare sabato. Se il tempo regge, potremmo partire presto e fermarci a pranzo.\n\nFammi sapere se ci sei!\nSara", False),
        ("The Pragmatic Engineer", "newsletter@example.com", "Building software that people love", "newsletters", 162,
         "This week: why the best software starts with a small, well-crafted experience.\n\nWe look at teams that ship thoughtful products, the tools they choose, and the tradeoffs behind seemingly simple interfaces.", False),
        ("GitHub", "notifications@github.example", "Una nuova release di Bowie", "updates", 250,
         "È disponibile una nuova release.\n\nMiglioramenti alla stabilità, strumenti più veloci e un nuovo flusso per gestire i task. Consulta il changelog del tuo progetto.", False),
        ("Luca Ferri", "luca@example.com", "Re: Ci vediamo alla conferenza", "people", 480,
         "Perfetto, ho confermato la mia presenza!\n\nCi troviamo all'ingresso alle 9:30. Porto anche il prototipo così possiamo provarlo insieme.\n\nLuca", False),
        ("Dense Discovery", "hello@example.com", "A little room to think", "newsletters", 900,
         "A quieter internet, thoughtful tools, and beautiful things worth your attention.\n\nThis edition explores how to create space for focused work without losing curiosity.", False),
    ]
    for index, (name, sender, subject, category, minutes, body, starred) in enumerate(samples):
        mail = EmailMessage()
        mail["From"] = f"{name} <{sender}>"
        mail["To"] = "you@example.com"
        mail["Subject"] = subject
        mail["Date"] = formatdate(time.time() - minutes * 60)
        mail["Message-ID"] = f"<demo-{index}@example.com>"
        mail.set_content(body)
        data = parse_message(mail.as_bytes(), account_id, "INBOX", "1", index + 1)
        data.update(category=category, read=int(index > 2), starred=int(starred))
        store.upsert_message(data)
