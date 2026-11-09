import json
import random
import time
import uuid
import httpx
from providers.notegpt import _core

token, _ = _core.select_account_token()
conv_id = str(uuid.uuid4())

def run_agent_message(prompt: str, msg_index: int):
    fake_ip = f"{random.randint(11, 199)}.{random.randint(10, 250)}.{random.randint(1, 254)}.{random.randint(1, 254)}"
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Origin": "https://notegpt.io",
        "Referer": "https://notegpt.io/ai-agent",
        "Authorization": f"Bearer {token}",
        "X-Forwarded-For": fake_ip,
        "X-Real-IP": fake_ip,
        "Client-IP": fake_ip,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
    }
    cookies = {
        "user_token": token,
        "nc_token": token,
        "anonymous_user_id": str(uuid.uuid4()),
    }
    body = {
        "app_id": "notegpt_8c92b6",
        "chat_mode": "agent",
        "conversation_id": conv_id,
        "language": "auto",
        "length": "moderate",
        "message": prompt,
        "model": "kimi-k3",
        "t": int(time.time()),
        "tone": "default",
    }
    body["sign"] = _core.sign_payload_dict(body, "notegpt_8c92b6")
    print(f"\n" + "="*50)
    print(f">>> MESSAGE {msg_index}: '{prompt}'")
    print(f"    Session ID: {conv_id[:8]}... | Fake IP: {fake_ip}")
    print("="*50)

    with httpx.Client(timeout=30) as client:
        resp = client.post("https://notegpt.io/api/v2/chat/stream", json=body, headers=headers, cookies=cookies)
        msg_id = None
        for line in resp.iter_lines():
            if line.startswith("data: "):
                print(f"  [Init Stream] {line}")
                d = json.loads(line[6:])
                if "msg_id" in d:
                    msg_id = d["msg_id"]

        # Continue loop
        for r in range(1, 15):
            cont_body = {
                "app_id": "notegpt_8c92b6",
                "conversation_id": conv_id,
                "t": int(time.time()),
            }
            if msg_id:
                cont_body["msg_id"] = msg_id
            cont_body["sign"] = _core.sign_payload_dict(cont_body, "notegpt_8c92b6")
            try:
                c_resp = client.post("https://notegpt.io/api/v2/chat/agent-stream/continue", json=cont_body, headers=headers, cookies=cookies)
            except Exception as e:
                print(f"  [Continue R{r}] Network error: {e}", flush=True)
                break
            
            done = False
            for line in c_resp.iter_lines():
                if line.startswith("data: "):
                    raw = line[6:].strip()
                    if raw == "[DONE]":
                        print(f"  [Continue R{r}] [DONE]", flush=True)
                        done = True
                        break
                    try:
                        d = json.loads(raw)
                        if "msg_id" in d:
                            msg_id = d["msg_id"]
                        ev = d.get("type")
                        if ev in ("prepare_env", "prepare_env_done", "credit_usage"):
                            print(f"  [Continue R{r}] Event: {ev} -> {d}", flush=True)
                        elif ev == "text":
                            txt = d.get("text", "")
                            if txt.strip():
                                print(f"  [Continue R{r}] Text chunk: {repr(txt)}", flush=True)
                        if d.get("finish_queue"):
                            print(f"  [Continue R{r}] Finish queue: True", flush=True)
                            done = True
                    except Exception:
                        pass
            if done:
                break
            time.sleep(1)

if __name__ == "__main__":
    run_agent_message("1+1=? answer in one number", 1)
    time.sleep(2)
    run_agent_message("what did I just ask you in the previous message?", 2)
    time.sleep(2)
    run_agent_message("multiply that result by 10", 3)
