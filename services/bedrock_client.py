import json
import boto3
import time
from typing import Dict, Any, Optional
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from config.env_config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


class BedrockClient:
    def __init__(self):
        self.config = BotoConfig(
            region_name=Config.AWS_REGION,
            retries={
                'max_attempts': 3,
                'mode': 'adaptive'
            },
            connect_timeout=30,
            read_timeout=60
        )

        self.client = boto3.client('bedrock-runtime', config=self.config)
        self.model_id = Config.BEDROCK_MODEL_ID

        logger.info("Bedrock client initialized", model_id=self.model_id, region=Config.AWS_REGION)

    def generate_response(
        self,
        user_question: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        start_time = time.time()

        try:
            prompt = self._build_prompt(user_question)

            if 'anthropic' in self.model_id.lower():
                request_body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": max_tokens or Config.BEDROCK_MAX_TOKENS,
                    "temperature": temperature or Config.BEDROCK_TEMPERATURE,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                }
            elif 'meta.llama' in self.model_id.lower():
                request_body = {
                    "prompt": prompt,
                    "max_gen_len": max_tokens or Config.BEDROCK_MAX_TOKENS,
                    "temperature": temperature or Config.BEDROCK_TEMPERATURE
                }
            elif 'amazon.nova' in self.model_id.lower():
                request_body = {
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"text": prompt}]
                        }
                    ],
                    "inferenceConfig": {
                        "max_new_tokens": max_tokens or Config.BEDROCK_MAX_TOKENS,
                        "temperature": temperature or Config.BEDROCK_TEMPERATURE
                    }
                }
            else:
                request_body = {
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"text": prompt}]
                        }
                    ],
                    "inferenceConfig": {
                        "maxTokens": max_tokens or Config.BEDROCK_MAX_TOKENS,
                        "temperature": temperature or Config.BEDROCK_TEMPERATURE
                    }
                }

            logger.info("Calling Bedrock API", model=self.model_id, question_length=len(user_question))

            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body)
            )

            response_body = json.loads(response['body'].read())

            if 'anthropic' in self.model_id.lower():
                answer_text = response_body['content'][0]['text']
                usage = response_body.get('usage', {})
                input_tokens = usage.get('input_tokens', 0)
                output_tokens = usage.get('output_tokens', 0)
            elif 'meta.llama' in self.model_id.lower():
                answer_text = response_body.get('generation', '')
                input_tokens = response_body.get('prompt_token_count', 0)
                output_tokens = response_body.get('generation_token_count', 0)
            elif 'amazon.nova' in self.model_id.lower():
                answer_text = response_body['output']['message']['content'][0]['text']
                usage = response_body.get('usage', {})
                input_tokens = usage.get('inputTokens', 0)
                output_tokens = usage.get('outputTokens', 0)
            else:
                answer_text = response_body.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', '')
                usage = response_body.get('usage', {})
                input_tokens = usage.get('inputTokens', 0)
                output_tokens = usage.get('outputTokens', 0)

            elapsed_time = time.time() - start_time

            logger.info(
                "Bedrock response generated",
                status="success",
                elapsed_time=f"{elapsed_time:.2f}s",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                answer_length=len(answer_text)
            )

            return {
                'success': True,
                'text': answer_text,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'elapsed_time': elapsed_time
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']

            logger.error(
                "Bedrock API error",
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
            logger.error("Unexpected error in Bedrock call", status="error", error=str(e))

            return {
                'success': False,
                'error': str(e)
            }

    def _build_prompt(self, user_question: str) -> str:
        prompt = f"""You are Vaani, an AI agricultural assistant helping farmers with practical advice.

Your areas of expertise:
1. Crop cultivation (wheat, rice, pulses, vegetables, fruits)
2. Soil health and fertilisers
3. Pest and disease management
4. Irrigation methods
5. Government schemes (PM-KISAN, crop insurance, MSP)
6. Getting better prices at markets
7. Weather-based farming advice
8. Agricultural loans and subsidies

Rules you must follow:
- Detect the language of the farmer's question and reply in that exact same language.
- Never switch languages mid-answer.
- Keep answers under 100 words so they are easy to listen to.
- Use simple, everyday vocabulary — avoid technical jargon.
- Give practical, ground-level advice.
- If you do not know the answer, honestly say so and advise the farmer to contact their nearest agricultural department.

Farmer's question:
{user_question}

Answer now in the same language as the question:
"""
        return prompt.strip()
