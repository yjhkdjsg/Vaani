# Vaani

Vaani is a voice-and-text AI assistant for rural Indian farmers. It accepts Hindi speech or text input, generates an agricultural advisory response using a large language model, and returns the answer as both text and synthesised speech.

---

## Architecture

```
Browser (CloudFront + S3)
        |
        | HTTPS POST /chat
        v
API Gateway (HTTP API)
        |
        v
Lambda: chat_handler
        |
   +----|----+--------+
   |         |        |
   v         v        v
Transcribe Bedrock  Polly
(auto-     (LLM)   (voice
 detect            selected
 language)         by language)
        |
        v
   S3 audio bucket
   (temp voice input,
    lifecycle: 7 days)
```

**Flow for a voice request**

1. Browser records audio and base64-encodes it.
2. `POST /chat` with `{"type": "voice", "audio": "<base64>"}` hits API Gateway.
3. Lambda decodes the audio, uploads it to S3, and starts an Amazon Transcribe job with `IdentifyLanguage=True` — the spoken language is detected automatically.
4. The transcribed text and detected language code are passed to Amazon Bedrock. The system prompt instructs the model to reply in the same language as the question.
5. The LLM response is synthesised to MP3 by Amazon Polly using a voice automatically selected for the detected language.
6. Lambda returns `{"success": true, "text": "...", "audio": "<base64 mp3>", "transcription": "...", "detected_language": "hi-IN"}`.
7. Browser plays the audio and displays the text.

**Flow for a text request**

Step 3 (Transcribe) is skipped; the text goes directly to Bedrock. The model detects the language from the text itself and responds in kind. Polly voice selection uses the language of the LLM response.

---

## Repository Structure

```
Vaani/
├── config/
│   └── env_config.py          # Centralised config loaded from environment variables
├── frontend/
│   ├── index.html             # Single-page chat UI
│   ├── styles.css             # UI styles
│   └── app.js                 # Chat logic, voice recording, API calls
├── infra/
│   └── terraform/
│       ├── main.tf            # All AWS infrastructure
│       ├── backend.tf         # Remote state config (optional)
│       ├── build.sh           # Lambda zip build script (Linux/macOS)
│       └── build.ps1          # Lambda zip build script (Windows)
├── lambda/
│   ├── chat_handler/
│   │   └── lambda_function.py # Lambda entry point
│   └── layer_requirements.txt # Dependencies for Lambda layer
├── services/
│   ├── bedrock_client.py      # Amazon Bedrock (LLM) wrapper
│   ├── polly_client.py        # Amazon Polly (TTS) wrapper
│   └── transcribe_client.py   # Amazon Transcribe (STT) wrapper
├── utils/
    └── logger.py              # Structured JSON logger
```

---

## Prerequisites

- AWS account with access to Bedrock, Transcribe, Polly, S3, Lambda, API Gateway, and CloudFront
- Bedrock model access enabled for the chosen model in your target region
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.0
- Python 3.11+
- `pip`

---

## Configuration

All runtime configuration is driven by environment variables. Terraform injects these into Lambda automatically. For local development, create a `.env` file in the project root.

| Variable | Default | Description |
|---|---|---|
| `AWS_REGION` | `ap-south-1` | AWS deployment region |
| `S3_BUCKET` | `vaani-audio-storage` | S3 bucket for temporary audio files |
| `BEDROCK_MODEL_ID` | `meta.llama3-8b-instruct-v1:0` | Bedrock model to use |
| `BEDROCK_MAX_TOKENS` | `500` | Maximum tokens in the LLM response |
| `BEDROCK_TEMPERATURE` | `0.7` | LLM sampling temperature |
| `POLLY_VOICE` | _(auto-selected by language)_ | Override Polly voice ID |
| `POLLY_ENGINE` | _(auto-selected by language)_ | Override engine: `neural` or `standard` |
| `POLLY_OUTPUT_FORMAT` | `mp3` | Audio output format |
| `TRANSCRIBE_LANGUAGE` | _(auto-detected)_ | Override Transcribe language code |
| `LOG_LEVEL` | `INFO` | Logging level |
| `ALLOWED_ORIGIN` | `*` | CORS origin returned by Lambda (set to your CloudFront URL in production) |

> **Cost note:** switching `POLLY_ENGINE` from `neural` to `standard` reduces Polly costs by approximately 75% at the cost of slightly less natural speech quality.

---

## Deployment

### 1. Build the Lambda package

**Linux / macOS**

```bash
cd infra/terraform
chmod +x build.sh
./build.sh
```

**Windows (PowerShell)**

```powershell
cd infra\terraform
.\build.ps1
```

Both scripts install boto3 for the `linux/arm64` platform (matching the Lambda runtime), copy all service modules, and produce `infra/build/chat_handler.zip`.

### 2. Deploy infrastructure

```bash
cd infra/terraform
terraform init
terraform plan
terraform apply
```

Terraform will output:

| Output | Description |
|---|---|
| `website_url` | CloudFront HTTPS URL — use this as the public frontend URL |
| `chat_api_url` | API Gateway `/chat` endpoint |
| `s3_website_bucket` | S3 bucket to upload frontend files to |
| `s3_audio_bucket` | S3 bucket used for temporary audio storage |
| `lambda_function` | Lambda function name |
| `cloudfront_distribution_id` | Distribution ID for cache invalidation |

### 3. Upload the frontend

After `terraform apply`, upload the three frontend files to the website S3 bucket:

```bash
aws s3 cp frontend/index.html s3://<s3_website_bucket>/
aws s3 cp frontend/styles.css s3://<s3_website_bucket>/
aws s3 cp frontend/app.js    s3://<s3_website_bucket>/
```

### 4. Set the API endpoint

The frontend reads the API Gateway URL from `window.VAANI_API_ENDPOINT`. Add a small inline script to `index.html` before `app.js`, or inject it at deploy time:

```html
<script>window.VAANI_API_ENDPOINT = 'https://<api-id>.execute-api.ap-south-1.amazonaws.com/chat';</script>
<script src="app.js"></script>
```

Replace the placeholder with the `chat_api_url` output from `terraform apply`.

### 5. Invalidate the CloudFront cache (after frontend updates)

```bash
aws cloudfront create-invalidation \
  --distribution-id <cloudfront_distribution_id> \
  --paths "/*"
```

---

## Infrastructure Details

### S3 buckets

| Bucket | Purpose | Access |
|---|---|---|
| `vaani-chatbot-website-<env>` | Static frontend hosting | Public read via bucket policy |
| `vaani-audio-storage-<env>` | Temporary voice input and transcripts | Private; Lambda IAM role only |

Both buckets have AES-256 server-side encryption enabled. The audio bucket has a lifecycle rule that permanently deletes objects after 7 days and transitions them to Intelligent-Tiering after 1 day.

### IAM

The Lambda execution role follows least-privilege:
- CloudWatch Logs: `CreateLogStream` and `PutLogEvents` scoped to the specific Lambda log group
- S3: `GetObject`, `PutObject`, `DeleteObject` scoped to the audio bucket only
- Transcribe: `StartTranscriptionJob`, `GetTranscriptionJob`, `DeleteTranscriptionJob` scoped to jobs prefixed `vaani-*`
- Polly: `SynthesizeSpeech`
- Bedrock: `InvokeModel` scoped to the single configured foundation model ARN

### API Gateway

HTTP API with CORS restricted to the CloudFront distribution domain. Only `POST /chat` and `OPTIONS` are permitted. The `GET` method is not exposed.

### Lambda

- Runtime: Python 3.11 on `arm64` (approximately 20% cheaper than x86_64)
- Timeout: 120 seconds (accommodates Transcribe polling)
- Memory: 512 MB

---

## Supported Bedrock Models

The `bedrock_client.py` automatically selects the correct request/response format based on the `BEDROCK_MODEL_ID` prefix:

| Prefix | Model family | Example model ID |
|---|---|---|
| `anthropic` | Claude | `anthropic.claude-3-haiku-20240307-v1:0` |
| `meta.llama` | Llama 3 | `meta.llama3-8b-instruct-v1:0` |
| `amazon.nova` | Amazon Nova | `amazon.nova-lite-v1:0` |

Any other model ID falls back to the Amazon Converse-compatible generic format.

---

## Supported Languages

Language is detected automatically for both voice and text input. The table below shows the Transcribe language code and Polly voice used for each supported language.

| Language | Code | Polly voice | Engine |
|---|---|---|---|
| Hindi | `hi-IN` | Aditi | neural |
| English (US) | `en-US` | Joanna | neural |
| English (UK) | `en-GB` | Amy | neural |
| English (India) | `en-IN` | Aditi | neural |
| Tamil | `ta-IN` | Aditi | neural |
| Telugu | `te-IN` | Aditi | neural |
| Kannada | `kn-IN` | Aditi | neural |
| Malayalam | `ml-IN` | Aditi | neural |
| Marathi | `mr-IN` | Aditi | neural |
| Gujarati | `gu-IN` | Aditi | neural |
| Punjabi | `pa-IN` | Aditi | neural |
| Bengali | `bn-IN` | Aditi | neural |
| French | `fr-FR` | Lea | neural |
| German | `de-DE` | Vicki | neural |
| Spanish | `es-ES` | Lucia | neural |
| Portuguese (BR) | `pt-BR` | Camila | neural |
| Arabic | `ar-SA` | Zeina | standard |
| Japanese | `ja-JP` | Kazuha | neural |
| Chinese (Mandarin) | `zh-CN` | Zhiyu | neural |
| Korean | `ko-KR` | Seoyeon | neural |

Indian regional languages without a dedicated Polly voice fall back to the Aditi (Hindi) voice for audio. The LLM response text is still generated in the correct regional language.

To add more languages, extend `LANGUAGE_OPTIONS` in `transcribe_client.py` and `LANGUAGE_VOICE_MAP` in `polly_client.py`.

---

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file:

```
AWS_REGION=ap-south-1
S3_BUCKET=vaani-audio-storage-dev
BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
LOG_LEVEL=DEBUG
```

AWS credentials must be available in the environment or via a profile (`~/.aws/credentials`). The services can be exercised directly by instantiating the client classes.

---

## Remote Terraform State (Optional)

`infra/terraform/backend.tf` contains a commented-out S3 backend configuration. To enable remote state, create the S3 bucket and DynamoDB lock table, then uncomment and update the block before running `terraform init`.

---

## Security Notes

- The audio S3 bucket is fully private. Lambda accesses it via IAM, not pre-signed URLs exposed to the browser.
- CORS on both the API Gateway and the audio bucket CORS configuration is restricted to the CloudFront distribution domain, not `*`.
- Lambda CORS response headers read the allowed origin from the `ALLOWED_ORIGIN` environment variable, which Terraform can set to the CloudFront URL at deploy time.
- User input is rendered using `document.createTextNode` — not `innerHTML` — preventing XSS from LLM-generated or user-supplied content.
- The frontend API endpoint is not embedded in source; it is injected at deploy time via `window.VAANI_API_ENDPOINT`.
- All input is length-bounded in Lambda (minimum 2 characters, maximum 500 characters) before reaching Bedrock.
