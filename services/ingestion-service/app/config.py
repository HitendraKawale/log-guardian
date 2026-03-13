import os

class Settings:
    AI_SERVER_URL = os.getenv("AI_SERVER_URL", "http://ai-service:8001")
    AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "2"))
    

settings = Settings()

