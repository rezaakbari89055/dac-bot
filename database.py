from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship, declarative_base
import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String(50), nullable=True)
    wallet = Column(Float, default=0.0)
    invited_by = Column(Integer, ForeignKey("users.telegram_id"), nullable=True)
    is_banned = Column(Boolean, default=False)
    is_test_used = Column(Boolean, default=False)
    services = relationship("UserServices", back_populates="user")

class Reseller(Base):
    __tablename__ = "resellers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, index=True)
    wallet = Column(Float, default=0.0)

class Server(Base):
    __tablename__ = "servers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100))
    type = Column(String(20)) # local / remote
    panel_url = Column(String(255))
    panel_user = Column(String(100))
    panel_pass = Column(String(100))

class Inbound(Base):
    __tablename__ = "inbounds"
    id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(Integer, ForeignKey("servers.id"))
    inbound_id = Column(Integer)
    tag = Column(String(100))

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(100))
    name = Column(String(100))
    days = Column(Integer)
    traffic_gb = Column(Float)
    price_toman = Column(Float)
    price_crypto = Column(Float, default=0)
    reseller_price = Column(Float, default=0)
    inbound_id = Column(Integer, ForeignKey("inbounds.id"))
    is_active = Column(Boolean, default=True)
    is_manual = Column(Boolean, default=False)

class UserServices(Base):
    __tablename__ = "user_services"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_telegram_id = Column(Integer, ForeignKey("users.telegram_id"))
    service_id = Column(Integer, ForeignKey("services.id"))
    uuid = Column(String(100))
    sub_link = Column(Text)
    expire_date = Column(DateTime)
    traffic_limit = Column(Float)
    traffic_used = Column(Float, default=0)
    is_active = Column(Boolean, default=True)
    sold_by_reseller = Column(Integer, nullable=True)
    user = relationship("User", back_populates="services")

class DiscountCode(Base):
    __tablename__ = "discount_codes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True)
    percent = Column(Integer)
    max_use = Column(Integer, default=1)
    used = Column(Integer, default=0)

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_telegram_id = Column(Integer)
    amount = Column(Float)
    currency = Column(String(10))
    tracking_code = Column(String(100), nullable=True)
    status = Column(String(20), default="pending")

class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_telegram_id = Column(Integer)
    text = Column(Text)
    is_admin_reply = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.now)

class Tutorial(Base):
    __tablename__ = "tutorials"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(100))
    content = Column(Text)

class Settings(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(50), unique=True)
    value = Column(Text)
