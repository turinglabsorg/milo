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
    category: Literal["people", "updates", "newsletters"] | None = None
    snoozed_until: float | None = None


class DraftInput(BaseModel):
    id: str | None = None
    account_id: str
    to: str = Field(max_length=2000)
    subject: str = Field(max_length=998)
    body: str = Field(max_length=100000)
    reply_to_id: str | None = None


class AISettings(BaseModel):
    model: str = Field(default="mistral-large-4:cloud", min_length=1, max_length=150)
    automatic: bool = False
    cloud_consent: bool = False


class RuleInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    field: Literal["sender", "subject", "body"]
    contains: str = Field(min_length=1, max_length=300)
    category: Literal["people", "updates", "newsletters"]
