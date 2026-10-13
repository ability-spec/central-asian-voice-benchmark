"""Start BirOvoz from any directory; --check performs offline readiness checks."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def check():
    required = {'fastapi': 'fastapi', 'uvicorn': 'uvicorn', 'dotenv': 'python-dotenv',
                'openai': 'openai', 'multipart': 'python-multipart'}
    missing = [package for module, package in required.items() if importlib.util.find_spec(module) is None]
    tools = {name: bool(shutil.which(name)) for name in ('ffmpeg', 'ffprobe')}
    result = {'dependencies_ready': not missing, 'missing_packages': missing,
              'audio_tools': tools, 'ready_to_start': not missing and all(tools.values())}
    if not missing:
        from dotenv import load_dotenv
        load_dotenv(ROOT / 'product/backend/.env')
        from product.backend.config import settings
        from product.backend.services.voice_clone import local_clone_configured
        result.update({'mode': 'mock' if settings.mock_mode else 'live-configured',
                       'local_clone_configured': local_clone_configured(),
                       'live_provider_verified': False, 'gpu_inference_verified': False})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Report offline readiness; no provider calls')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    import os
    os.chdir(ROOT)
    result = check()
    if args.check or not result['ready_to_start']:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result['ready_to_start']:
        print('Install backend requirements and ffmpeg/ffprobe, then retry.', file=sys.stderr)
        return 1
    if args.check:
        return 0
    # Runtime directories should be stable even when started outside the repo.
    import uvicorn
    print(f'BirOvoz: http://{args.host}:{args.port} ({result["mode"]})')
    uvicorn.run('product.backend.main:app', host=args.host, port=args.port)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
