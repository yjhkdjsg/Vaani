import boto3
import time
from typing import Dict, Any, Optional
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from config.env_config import Config
from utils.logger import get_logger

logger = get_logger(__name__)

LANGUAGE_VOICE_MAP = {
    'hi-IN':  ('Aditi',    'hi-IN',  'neural'),
    'en-US':  ('Joanna',   'en-US',  'neural'),
    'en-GB':  ('Amy',      'en-GB',  'neural'),
    'en-IN':  ('Aditi',    'hi-IN',  'neural'),
    'ta-IN':  ('Aditi',    'hi-IN',  'neural'),
    'te-IN':  ('Aditi',    'hi-IN',  'neural'),
    'kn-IN':  ('Aditi',    'hi-IN',  'neural'),
    'ml-IN':  ('Aditi',    'hi-IN',  'neural'),
    'mr-IN':  ('Aditi',    'hi-IN',  'neural'),
    'gu-IN':  ('Aditi',    'hi-IN',  'neural'),
    'pa-IN':  ('Aditi',    'hi-IN',  'neural'),
    'bn-IN':  ('Aditi',    'hi-IN',  'neural'),
    'fr-FR':  ('Lea',      'fr-FR',  'neural'),
    'de-DE':  ('Vicki',    'de-DE',  'neural'),
    'es-ES':  ('Lucia',    'es-ES',  'neural'),
    'pt-BR':  ('Camila',   'pt-BR',  'neural'),
    'ar-SA':  ('Zeina',    'arb',    'standard'),
    'ja-JP':  ('Kazuha',   'ja-JP',  'neural'),
    'zh-CN':  ('Zhiyu',    'cmn-CN', 'neural'),
    'ko-KR':  ('Seoyeon',  'ko-KR',  'neural'),
}

DEFAULT_VOICE_CONFIG = ('Joanna', 'en-US', 'neural')


def _resolve_voice(language_code: Optional[str]) -> tuple:
    if not language_code:
        return DEFAULT_VOICE_CONFIG
    entry = LANGUAGE_VOICE_MAP.get(language_code)
    if entry:
        return entry
    prefix = language_code.split('-')[0] + '-'
    for key, value in LANGUAGE_VOICE_MAP.items():
        if key.startswith(prefix):
            return value
    return DEFAULT_VOICE_CONFIG


class PollyClient:
    def __init__(self):
        self.config = BotoConfig(
            region_name=Config.AWS_REGION,
            retries={
                'max_attempts': 3,
                'mode': 'adaptive'
            }
        )

        self.client = boto3.client('polly', config=self.config)

        logger.info(
            "Polly client initialized",
            region=Config.AWS_REGION,
        )

    def synthesize_speech(
        self,
        text: str,
        language_code: Optional[str] = None,
        voice_id: Optional[str] = None,
        engine: Optional[str] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()

        try:
            resolved_voice, resolved_lang, resolved_engine = _resolve_voice(language_code)

            voice = voice_id or resolved_voice
            speech_engine = engine or resolved_engine
            polly_language = language_code or resolved_lang

            logger.info(
                "Synthesizing speech",
                text_length=len(text),
                voice=voice,
                engine=speech_engine,
                language=polly_language,
            )

            response = self.client.synthesize_speech(
                Text=text,
                OutputFormat=Config.POLLY_OUTPUT_FORMAT,
                VoiceId=voice,
                Engine=speech_engine,
                LanguageCode=polly_language,
            )

            audio_stream = response['AudioStream'].read()
            elapsed_time = time.time() - start_time

            logger.info(
                "Speech synthesis completed",
                status="success",
                elapsed_time=f"{elapsed_time:.2f}s",
                audio_size=f"{len(audio_stream)} bytes",
            )

            return {
                'success': True,
                'audio_stream': audio_stream,
                'content_type': response['ContentType'],
                'elapsed_time': elapsed_time,
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']

            logger.error(
                "Polly API error",
                status="error",
                error_code=error_code,
                error_message=error_message,
            )

            return {
                'success': False,
                'error': error_message,
                'error_code': error_code,
            }

        except Exception as e:
            logger.error("Unexpected error in speech synthesis", status="error", error=str(e))

            return {
                'success': False,
                'error': str(e),
            }

    def get_available_voices(self, language_code: str = 'en-US') -> list:
        try:
            response = self.client.describe_voices(LanguageCode=language_code)
            voices = response.get('Voices', [])

            logger.info("Retrieved available voices", language=language_code, count=len(voices))

            return voices

        except Exception as e:
            logger.error("Error getting available voices", error=str(e))
            return []
