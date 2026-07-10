import json
import os
import boto3
import base64
import uuid
from typing import Dict, Any

from services.transcribe_client import TranscribeClient
from services.bedrock_client import BedrockClient
from services.polly_client import PollyClient
from utils.logger import get_logger
from config.env_config import Config

logger = get_logger(__name__)

s3_client = boto3.client('s3', region_name=Config.AWS_REGION)
transcribe_client = TranscribeClient()
bedrock_client = BedrockClient()
polly_client = PollyClient()


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        logger.info("Chat handler started", request_id=context.aws_request_id)

        if not event.get('body'):
            return error_response("Missing request body", 400)

        try:
            body = json.loads(event['body'])
        except json.JSONDecodeError:
            return error_response("Invalid JSON", 400)

        text_input = body.get('text')
        audio_input = body.get('audio')
        input_type = body.get('type', 'text')

        user_question = None
        detected_language = None

        if input_type == 'voice' and audio_input:
            logger.info("Processing voice input")
            voice_result = process_voice_input(audio_input)
            if not voice_result:
                return error_response("Failed to transcribe audio", 500)
            user_question = voice_result['text']
            detected_language = voice_result.get('detected_language')
            logger.info("Voice transcribed", detected_language=detected_language)

        elif input_type == 'text' and text_input:
            logger.info("Processing text input")
            user_question = text_input.strip()

        else:
            return error_response("Invalid input: provide either text or audio", 400)

        if len(user_question) > 500:
            return error_response("Input too long (max 500 characters)", 400)

        if len(user_question) < 2:
            return error_response("Input too short", 400)

        logger.info("User question received", question=user_question[:100])

        ai_result = bedrock_client.generate_response(user_question)

        if not ai_result['success']:
            logger.error("AI response generation failed", error=ai_result.get('error'))
            return error_response("Failed to generate response", 500)

        answer_text = ai_result['text']
        logger.info("AI response generated", answer_length=len(answer_text))

        speech_result = polly_client.synthesize_speech(
            answer_text,
            language_code=detected_language,
        )

        if not speech_result['success']:
            logger.error("Speech synthesis failed", error=speech_result.get('error'))
            return success_response(
                text=answer_text,
                audio=None,
                transcription=user_question if input_type == 'voice' else None,
                detected_language=detected_language,
            )

        audio_base64 = base64.b64encode(speech_result['audio_stream']).decode('utf-8')

        logger.info("Chat processing completed successfully")

        return success_response(
            text=answer_text,
            audio=audio_base64,
            transcription=user_question if input_type == 'voice' else None,
            detected_language=detected_language,
        )

    except Exception as e:
        logger.error("Unexpected error in chat handler", error=str(e), exception_type=type(e).__name__)
        return error_response("Internal server error", 500)


def process_voice_input(audio_base64: str) -> dict:
    audio_key = f"voice-input/{uuid.uuid4().hex}.webm"
    try:
        audio_data = base64.b64decode(audio_base64)

        logger.info("Uploading audio to S3", key=audio_key)
        s3_client.put_object(
            Bucket=Config.S3_BUCKET,
            Key=audio_key,
            Body=audio_data,
            ContentType='audio/webm'
        )

        s3_uri = f"s3://{Config.S3_BUCKET}/{audio_key}"

        logger.info("Starting transcription")
        transcription_result = transcribe_client.transcribe_audio(s3_uri)

        if not transcription_result['success']:
            logger.error("Transcription failed", error=transcription_result.get('error'))
            return None

        logger.info(
            "Transcription successful",
            text=transcription_result['text'][:100],
            detected_language=transcription_result.get('detected_language'),
        )

        return {
            'text': transcription_result['text'],
            'detected_language': transcription_result.get('detected_language'),
        }

    except Exception as e:
        logger.error("Error processing voice input", error=str(e))
        return None

    finally:
        try:
            s3_client.delete_object(Bucket=Config.S3_BUCKET, Key=audio_key)
            logger.debug("Cleaned up voice input from S3", key=audio_key)
        except Exception as e:
            logger.warning("Failed to delete voice input from S3", key=audio_key, error=str(e))


def success_response(text: str, audio: str = None, transcription: str = None, detected_language: str = None) -> Dict[str, Any]:
    response_body = {
        'success': True,
        'text': text,
        'audio': audio,
        'transcription': transcription,
        'detected_language': detected_language,
    }

    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': os.environ.get('ALLOWED_ORIGIN', '*'),
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'POST, OPTIONS'
        },
        'body': json.dumps(response_body)
    }


def error_response(message: str, status_code: int = 500) -> Dict[str, Any]:
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': os.environ.get('ALLOWED_ORIGIN', '*'),
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'POST, OPTIONS'
        },
        'body': json.dumps({
            'success': False,
            'error': message
        })
    }
