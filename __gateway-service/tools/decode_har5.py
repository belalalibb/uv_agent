import sys, json, os, base64
sys.stdout.reconfigure(encoding='utf-8')
har_path = sys.argv[1] if len(sys.argv) > 1 else 'sample.har'
if not os.path.exists(har_path):
    print(f"HAR file not found: {har_path}")
    sys.exit(0)
with open(har_path, encoding='utf-8', errors='ignore') as f:
    data = json.load(f)
resp_text = data['log']['entries'][0]['response']['content']['text']
decoded = base64.b64decode(resp_text).decode('utf-8', errors='ignore')

content_parts = []
reasoning_parts = []
for line in decoded.splitlines():
    if line.startswith('data: '):
        chunk = line[6:].strip()
        if chunk in ('[DONE]', '{"type":"done"}'):
            break
        try:
            ev = json.loads(chunk)
            if ev.get('type') == 'content_delta':
                content_parts.append(ev.get('text', ''))
            elif ev.get('type') == 'reasoning_delta':
                reasoning_parts.append(ev.get('text', ''))
        except Exception:
            pass

full_content = ''.join(content_parts)
print('=== CONTENT DELTA LENGTH ===', len(full_content))
print('=== REASONING LENGTH ===', len(''.join(reasoning_parts)))
print('\n=== FULL CONTENT ===')
print(full_content)
