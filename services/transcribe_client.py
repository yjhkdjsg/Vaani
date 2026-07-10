import json
import boto3
import time
import uuid
import os
import urllib.request
from typing import Dict, Any, Optional
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from config.env_config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


class TranscribeClient:
    def __init__(self):
        self.config = BotoConfig(
            region_name=Config.AWS_REGION,
            retries={
                'max_attempts': 3,
                'mode': 'adaptive'
            }
        )

        self.client = boto3.client('transcribe', config=self.config)
        self.s3_client = boto3.client('s3', config=self.config)

        logger.info("Transcribe client initialized", region=Config.AWS_REGION)

    LANGUAGE_OPTIONS = [
        'hi-IN', 'en-US', 'en-GB', 'en-IN',
        'ta-IN', 'te-IN', 'kn-IN', 'ml-IN',
        'mr-IN', 'gu-IN', 'pa-IN', 'bn-IN',
        'fr-FR', 'de-DE', 'es-ES', 'pt-BR',
        'ar-SA', 'ja-JP', 'zh-CN', 'ko-KR',
    ]

    def transcribe_audio(
        self,
        s3_uri: str,
        language_code: Optional[str] = None
    ) -> Dict[str, Any]:
        start_time = time.time()
        job_name = f"vaani-transcribe-{uuid.uuid4().hex[:8]}"

        try:
            if language_code:
                job_params = dict(
                    TranscriptionJobName=job_name,
                    Media={'MediaFileUri': s3_uri},
                    MediaFormat='webm',
                    LanguageCode=language_code,
                )
            else:
                job_params = dict(
                    TranscriptionJobName=job_name,
                    Media={'MediaFileUri': s3_uri},
                    MediaFormat='webm',
                    IdentifyLanguage=True,
                    LanguageOptions=self.LANGUAGE_OPTIONS,
                )

            logger.info(
                "Starting transcription job",
                job_name=job_name,
                language=language_code or 'auto-detect'
            )

            self.client.start_transcription_job(**job_params)

            job_status = self._wait_for_job_completion(job_name)

            if job_status['success']:
                elapsed_time = time.time() - start_time

                logger.info(
                    "Transcription completed",
                    status="success",
                    job_name=job_name,
                    elapsed_time=f"{elapsed_time:.2f}s",
                    detected_language=job_status.get('detected_language', 'unknown'),
                    text_length=len(job_status['text'])
                )

                return {
                    'success': True,
                    'text': job_status['text'],
                    'detected_language': job_status.get('detected_language'),
                    'job_name': job_name,
                    'elapsed_time': elapsed_time
                }
            else:
                logger.error(
                    "Transcription failed",
                    status="error",
                    job_name=job_name,
                    reason=job_status.get('error', 'Unknown error')
                )

                return {
                    'success': False,
                    'error': job_status.get('error', 'Transcription failed'),
                    'job_name': job_name
                }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']

            logger.error(
                "Transcribe API error",
                status="error",
                error_code=error_code,
                error_message=error_message
            )

            return {
                'success': False,
                'error': error_message,
                'error_code': error_code
            }

        except Exception as e:
            logger.error("Unexpected error in transcription", status="error", error=str(e))

            return {
                'success': False,
                'error': str(e)
            }

        finally:
            try:
                self.client.delete_transcription_job(TranscriptionJobName=job_name)
                logger.debug("Transcription job deleted", job_name=job_name)
            except Exception as e:
                logger.warning("Failed to delete transcription job", job_name=job_name, error=str(e))

    def _wait_for_job_completion(
        self,
        job_name: str,
        max_wait_time: int = 120,
        poll_interval: int = 2
    ) -> Dict[str, Any]:
        elapsed = 0

        while elapsed < max_wait_time:
            try:
                response = self.client.get_transcription_job(
                    TranscriptionJobName=job_name
                )

                status = response['TranscriptionJob']['TranscriptionJobStatus']

                if status == 'COMPLETED':
                    job = response['TranscriptionJob']
                    transcript_uri = job['Transcript']['TranscriptFileUri']
                    transcript_text = self._download_transcript(transcript_uri)
                    detected_language = (
                        job.get('IdentifiedLanguageCode')
                        or job.get('LanguageCode')
                    )

                    return {
                        'success': True,
                        'text': transcript_text,
                        'detected_language': detected_language,
                    }

                elif status == 'FAILED':
                    failure_reason = response['TranscriptionJob'].get('FailureReason', 'Unknown')
                    return {
                        'success': False,
                        'error': failure_reason
                    }

                time.sleep(poll_interval)
                elapsed += poll_interval

            except Exception as e:
                logger.error("Error polling transcription job", job_name=job_name, error=str(e))
                return {
                    'success': False,
                    'error': str(e)
                }

        return {
            'success': False,
            'error': f'Transcription job timed out after {max_wait_time}s'
        }

    def transcribe_audio_file(
        self,
        audio_file_path: str,
        language_code: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            file_extension = os.path.splitext(audio_file_path)[1] or '.mp3'
            s3_key = f"temp/transcribe-{uuid.uuid4().hex[:8]}{file_extension}"

            logger.info("Uploading audio file to S3", s3_key=s3_key)

            with open(audio_file_path, 'rb') as audio_file:
                self.s3_client.put_object(
                    Bucket=Config.S3_BUCKET,
                    Key=s3_key,
                    Body=audio_file
                )

            s3_uri = f"s3://{Config.S3_BUCKET}/{s3_key}"

            result = self.transcribe_audio(s3_uri, language_code)

            try:
                self.s3_client.delete_object(Bucket=Config.S3_BUCKET, Key=s3_key)
                logger.debug("Cleaned up S3 file", s3_key=s3_key)
            except Exception as e:
                logger.warning("Failed to delete S3 file", s3_key=s3_key, error=str(e))

            return result

        except Exception as e:
            logger.error("Error transcribing local file", error=str(e))
            return {
                'success': False,
                'error': str(e)
            }

    def _download_transcript(self, transcript_uri: str) -> str:
        req = urllib.request.Request(transcript_uri)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                transcript_data = json.loads(response.read())
        except Exception as e:
            logger.error("Failed to download transcript", error=str(e))
            raise

        transcript_text = transcript_data['results']['transcripts'][0]['transcript']
        return transcript_text
