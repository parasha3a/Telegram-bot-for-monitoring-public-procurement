from models import Base, engine

def init_database():
    """Initialize the database by creating all tables."""
    Base.metadata.create_all(engine)
    print("Database initialized successfully!")

if __name__ == "__main__":
    init_database() 