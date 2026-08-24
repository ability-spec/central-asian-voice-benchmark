# Central Asian AI Voice Benchmark

## Purpose
Research benchmark comparing existing AI voice/translation systems for Central Asian languages.
Not a product. Not a dataset training project. Not a website or API.

## Language Pairs
- English → Uzbek
- English → Kazakh

## Pipeline Under Test
STT → Translation → TTS/Dubbing (each step benchmarked independently and end-to-end)

## Evidence Standards
All capability claims must be labeled one of:
- **CONFIRMED** — verified by working API call or official documentation
- **CLAIMED** — provider asserts capability but not yet tested
- **UNKNOWN** — insufficient evidence

Never promote UNKNOWN to a guess.

## Project Status
Initial environment audit complete (2026-08-23). No benchmark runs yet.

## Environment
- Python 3.14.6 (boto3 not installed — must `pip install boto3` before any Bedrock calls)
- AWS CLI v2, region us-east-2 (root account)
- Bedrock accessible; Transcribe/Translate NOT subscribed
- LiveKit Agents 1.6.6 + livekit-plugins-google installed
- Google Cloud Speech + TTS SDKs installed (no credentials configured)
- ElevenLabs SDK installed (no ELEVENLABS_API_KEY)
- OpenAI SDK installed (no OPENAI_API_KEY)
- ffmpeg installed

## Do Not
- Build a website or API
- Train models
- Generate benchmark audio until test corpus is defined
- Make product recommendations
