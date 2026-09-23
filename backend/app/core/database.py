from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# 创建数据库引擎
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=settings.DEBUG
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基础模型类
Base = declarative_base()


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库表"""
    # 导入所有模型以确保它们被注册到Base.metadata
    from app.models import user, invoice, attachment, email_config, system_log
    
    # 创建所有表
    Base.metadata.create_all(bind=engine)
    _ensure_schema_updates()
    
    # 创建默认管理员用户
    from app.db.init_db import init_db as create_default_user
    create_default_user()


def _ensure_schema_updates():
    inspector = inspect(engine)
    if "invoices" not in inspector.get_table_names():
        return

    invoice_columns = {column["name"] for column in inspector.get_columns("invoices")}
    statements = []
    if "reimbursement_status" not in invoice_columns:
        statements.append(
            "ALTER TABLE invoices "
            "ADD COLUMN reimbursement_status VARCHAR(30) "
            "DEFAULT 'unreimbursed'"
        )

    if not statements:
        return

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
