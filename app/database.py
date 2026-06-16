import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_config():
    config_path = os.path.join(BASE_DIR, 'config.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

config = load_config()

db_path = config['database']['url'].replace('sqlite:///', '')
db_dir = os.path.join(BASE_DIR, db_path.replace('/', '')) if db_path.startswith('/') else os.path.join(BASE_DIR, db_path)
os.makedirs(os.path.dirname(db_dir), exist_ok=True)

engine = create_engine(
    config['database']['url'],
    echo=False,
    connect_args={'check_same_thread': False} if 'sqlite' in config['database']['url'] else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from . import models
    Base.metadata.create_all(bind=engine)
