"""Create a fresh localhost configuration; never overwrite an existing .env."""
from pathlib import Path
import secrets


def main():
    root = Path(__file__).resolve().parent.parent
    password = secrets.token_urlsafe(32)
    template = (root / '.env.example').read_text(encoding='utf-8')
    content = template.replace(
        'replace-with-a-new-random-secret-of-at-least-50-characters', secrets.token_urlsafe(64)
    ).replace('replace-with-your-database-password', password)
    try:
        with (root / '.env').open('x', encoding='utf-8') as output:
            output.write(content)
        (root / '.env').chmod(0o600)
    except FileExistsError:
        raise SystemExit('.env already exists; no configuration changed.')
    print('Created .env with fresh secrets for localhost. Set your own BOT_TOKEN and BOT_USERNAME there.')


if __name__ == '__main__':
    main()
