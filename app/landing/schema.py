from pydantic import BaseModel


class ServiceItem(BaseModel):
    title: str
    description: str


class HeroSection(BaseModel):
    title: str
    subtitle: str
    cta_text: str


class MetaInfo(BaseModel):
    title: str
    description: str


class CompanyInfo(BaseModel):
    name: str
    city: str
    phone: str | None = None
    whatsapp_url: str | None = None


class ContactsInfo(BaseModel):
    phone: str | None = None
    whatsapp_url: str | None = None
    address: str | None = None
    city: str | None = None


class ThemeInfo(BaseModel):
    style: str = "modern"
    primary_color: str = "#1f2937"
    accent_color: str = "#c9975b"


class WorkStage(BaseModel):
    number: int
    title: str
    description: str


class FaqItem(BaseModel):
    question: str
    answer: str


class ClaimItem(BaseModel):
    text: str
    source_field: str
    verified: bool = True


class LandingProfile(BaseModel):
    meta: MetaInfo
    company: CompanyInfo
    hero: HeroSection
    services: list[ServiceItem] = []
    advantages: list[str] = []
    work_stages: list[WorkStage] = []
    faq: list[FaqItem] = []
    contacts: ContactsInfo = ContactsInfo()
    theme: ThemeInfo = ThemeInfo()
    language: str = "ru"
    claims: list[ClaimItem] = []
