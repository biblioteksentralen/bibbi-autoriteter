from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
from sqlalchemy import Column, Integer, String

class AuthorityTopic(Base):
    __tablename__ = 'AuthorityTopic'
    id = Column()

