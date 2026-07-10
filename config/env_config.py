import os
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    AWS_REGION: str = os.getenv('AWS_REGION', 'ap-south-1')
    S3_BUCKET: str = os.getenv('S3_BUCKET', 'vaani-audio-storage')

    BEDROCK_MODEL_ID: str = os.getenv('BEDROCK_MODEL_ID', 'meta.llama3-8b-instruct-v1:0')
    BEDROCK_MAX_TOKENS: int = int(os.getenv('BEDROCK_MAX_TOKENS', '500'))
    BEDROCK_TEMPERATURE: float = float(os.getenv('BEDROCK_TEMPERATURE', '0.7'))

    POLLY_VOICE: str = os.getenv('POLLY_VOICE', 'Aditi')
    POLLY_ENGINE: str = os.getenv('POLLY_ENGINE', 'neural')
    POLLY_OUTPUT_FORMAT: str = os.getenv('POLLY_OUTPUT_FORMAT', 'mp3')

    TRANSCRIBE_LANGUAGE: str = os.getenv('TRANSCRIBE_LANGUAGE', 'hi-IN')

    LAMBDA_TIMEOUT: int = int(os.getenv('LAMBDA_TIMEOUT', '60'))
    LAMBDA_MEMORY: int = int(os.getenv('LAMBDA_MEMORY', '256'))

    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')

    API_GATEWAY_STAGE: str = os.getenv('API_GATEWAY_STAGE', 'prod')

    @classmethod
    def validate(cls) -> bool:
        required_vars = ['S3_BUCKET']
        missing_vars = [var for var in required_vars if not getattr(cls, var)]

        if missing_vars:
            raise ValueError(f"Missing required configuration: {', '.join(missing_vars)}")

        return True
