from dotenv import load_dotenv
import os, httpx, json
load_dotenv()
token = os.getenv('TELEGRAM_BOT_TOKEN')
r = httpx.get(f'https://api.telegram.org/bot{token}/getUpdates', timeout=10)
data = r.json()
results = data.get('result', [])
print(f'So updates: {len(results)}')
for u in results:
    if 'message' in u:
        chat = u['message']['chat']
        cid = chat.get('id')
        fname = chat.get('first_name', '')
        uname = chat.get('username', '?')
        text = u['message'].get('text', '')
        print(f'Chat ID: {cid} | {fname} @{uname} | Text: {text}')
