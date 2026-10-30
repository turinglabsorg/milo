from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Login(BaseModel):
    password: str = Field(min_length=12, max_length=256)
    bootstrap: str = Field(default="", max_length=512)


class SetupGrant(BaseModel):
    token: str = Field(min_length=1, max_length=512)


class AccountInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)
    imap_host: str = Field(min_length=1, max_length=253)
    imap_port: int = Field(default=993, ge=1, le=65535)
    smtp_host: str = Field(min_length=1, max_length=253)
    smtp_port: int = Field(default=465, ge=1, le=65535)
    smtp_security: Literal["tls", "starttls"] = "tls"
    color: str = "#afa4ff"

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        if "@" not in value or any(c in value for c in "\r\n\x00"):
            raise ValueError("Indirizzo email non valido")
        return value

    @field_validator("imap_host", "smtp_host")
    @classmethod
    def host_valid(cls, value):
        if any(c.isspace() or c in '/\\\x00' for c in value):
            raise ValueError("Inserisci solo il nome del server")
        return value


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    enabled: bool | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    username: str | None = Field(default=None, min_length=1, max_length=254)
    password: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)
    imap_host: str | None = Field(default=None, min_length=1, max_length=253)
    imap_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_host: str | None = Field(default=None, min_length=1, max_length=253)
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_security: Literal["tls", "starttls"] | None = None

    @field_validator("imap_host", "smtp_host")
    @classmethod
    def host_valid(cls, value):
        return AccountInput.host_valid(value) if value is not None else value


class GoogleStart(BaseModel):
    account_id: str | None = Field(default=None, max_length=64)


class MessagePatch(BaseModel):
    read: bool | None = None
    starred: bool | None = None
    archived: bool | None = None
    pinned: bool | None = None
    category: Literal["people", "updates", "newsletters"] | None = None
    snoozed_until: float | None = None


class Appearance(BaseModel):
    theme: Literal["system", "light", "dark"] = "system"


class DraftInput(BaseModel):
    id: str | None = None
    account_id: str
    to: str = Field(max_length=2000)
    cc: str = Field(default="", max_length=2000)
    subject: str = Field(max_length=998)
    body: str = Field(max_length=1_000_000)
    html: str = Field(default="", max_length=1_000_000)
    reply_to_id: str | None = None
    context_message_id: str | None = None
    mode: Literal["new", "reply", "reply_all", "forward"] = "new"
    revision: int = Field(default=0, ge=0)
    track: bool = True


class AISettings(BaseModel):
    model: str = Field(default="deepseek-v4.1-flash:cloud", min_length=1, max_length=150)
    automatic: bool = False
    cloud_consent: bool = False


class Identity(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(default="", max_length=120)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    context: str = Field(default="", max_length=2000)
    reply_language: Literal["auto", "en", "it", "fr", "de", "es", "pt"] = "auto"

    @field_validator("aliases")
    @classmethod
    def aliases_valid(cls, values):
        result = []
        for value in values:
            value = value.strip()
            if not value or len(value) > 80 or any(c in value for c in "\r\n\x00"):
                raise ValueError("Inserisci nomi brevi, separati da virgole")
            if value.casefold() not in {name.casefold() for name in result}:
                result.append(value)
        return result


class RuleInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    field: Literal["sender", "subject", "body"]
    contains: str = Field(min_length=1, max_length=300)
    category: Literal["people", "updates", "newsletters"]


class ScheduleInput(BaseModel):
    send_at: float
    followup_days: int | None = Field(default=None, ge=1, le=60)


class TodoPatch(BaseModel):
    done: bool


class TodoAccept(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class SenderPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["approved", "blocked"] | None = None
    vip: bool | None = None


class SenderAction(BaseModel):
    action: Literal["archive", "trash", "read"]


class Signatures(BaseModel):
    signatures: dict[str, str] = Field(default_factory=dict)

    @field_validator("signatures")
    @classmethod
    def signatures_valid(cls, values):
        if len(values) > 20 or any(len(key) > 64 or len(value) > 4000 for key, value in values.items()):
            raise ValueError("Firme troppo lunghe")
        return values


class Template(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=8000)


class Templates(BaseModel):
    templates: list[Template] = Field(default_factory=list, max_length=50)


class ScreenerSettings(BaseModel):
    enabled: bool = False


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class DeviceInput(BaseModel):
    token: str = Field(min_length=32, max_length=200)
    environment: Literal["production", "sandbox"] = "production"
