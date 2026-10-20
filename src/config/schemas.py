from datetime import datetime
from pydantic import BaseModel, Field



# ===== Bronze =====

class RssBronzeBaseModel(BaseModel):
    """
    meta_*: metadata of the RSS source  
    system_*: additional context of the crawler  
    """
    
    title: str | None
    description: str | None
    pub_date: str | None
    link: str | None
    
    meta_title: str | None
    meta_description: str | None
    meta_link: str | None
    
    system_created_at: datetime = Field(default_factory=datetime.now)


class RssVnexpressBronzeModel(RssBronzeBaseModel):
    meta_pub_date: str | None
    meta_generator: str | None

    guid: str | None


class RssVietnamplusBronzeModel(RssBronzeBaseModel):
    meta_copyright: str | None
    meta_last_build_date: str | None
    meta_pub_date: str | None
    meta_language: str | None
    meta_docs: str | None
    meta_managing_editor: str | None
    meta_web_master: str | None
    meta_ttl: str | None
    meta_atom_link: str | None

    updated: str | None
    atom_link: str | None
    guid: str | None


class RssTuoitreBronzeModel(RssBronzeBaseModel):
    meta_language: str | None
    meta_copyright: str | None
    meta_last_build_date: str | None
    meta_docs: str | None
    meta_generator: str | None
    meta_ttl: str | None

    author: str | None


class RssDantriBronzeModel(RssBronzeBaseModel):
    meta_atom_link: str | None
    meta_last_build_date: str | None
    meta_pub_date: str | None
    meta_language: str | None
    meta_copyright: str | None
    meta_sy_update_period: str | None
    meta_sy_update_frequency: str | None
    meta_ttl: str | None
    
    guid: str | None
    dc_creator: str | None
    category: str | None


class RssThanhnienBronzeModel(RssBronzeBaseModel):
    meta_atom_link: str | None
    meta_copyright: str | None
    meta_generator: str | None
    meta_pub_date: str | None
    meta_language: str | None
    meta_last_build_date: str | None
    meta_atom_link_2: str | None
    meta_ttl: str | None
    
    guid: str | None


class RssBaoxaydungBronzeModel(RssBronzeBaseModel):
    meta_atom_link: str | None
    meta_copyright: str | None
    meta_generator: str | None
    meta_pub_date: str | None
    meta_language: str | None
    meta_last_build_date: str | None
    meta_atom_link_2: str | None
    meta_ttl: str | None
    
    guid: str | None


class RssTienphongBronzeModel(RssBronzeBaseModel):
    meta_copyright: str | None
    meta_last_build_date: str | None
    meta_pub_date: str | None
    meta_language: str | None
    meta_docs: str | None
    meta_managing_editor: str | None
    meta_web_master: str | None
    meta_ttl: str | None
    meta_atom_link: str | None
    
    updated: str | None
    atom_link: str | None
    guid: str | None





# ===== Silver =====


