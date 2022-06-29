from sqlalchemy import Column, Integer, String, UnicodeText, ForeignKey
from sqlalchemy.schema import UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Bibitem(Base):
    __tablename__ = 'bibitem'
    uuid = Column(String(36), primary_key=True)
    in_doc = Column(String(36))
    bibitem_string = Column(UnicodeText())


class BibitemLinkMap(Base):
    __tablename__ = 'bibitemlinkmap'
    # __table_args__ = (UniqueConstraint(
    #                   'uuid', 'link', name='uid_link_uniq'),)
    id = Column(Integer(), autoincrement=True, primary_key=True)
    uuid = Column(String(36), ForeignKey('bibitem.uuid'))
    link = Column(UnicodeText())


class BibitemArxivIDMap(Base):
    __tablename__ = 'bibitemarxividmap'
    # __table_args__ = (UniqueConstraint(
    #                   'uuid', 'arxiv_id', name='uid_aid_uniq'),)
    id = Column(Integer(), autoincrement=True, primary_key=True)
    uuid = Column(String(36), ForeignKey('bibitem.uuid'))
    arxiv_id = Column(String(36))


class BibitemMAGIDMap(Base):
    __tablename__ = 'bibitemmagidmap'
    # __table_args__ = (UniqueConstraint(
    #                   'uuid', 'mag_id', name='uid_mid_uniq'),)
    id = Column(Integer(), autoincrement=True, primary_key=True)
    uuid = Column(String(36), ForeignKey('bibitem.uuid'))
    mag_id = Column(String(36))
