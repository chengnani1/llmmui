import requests

url="http://127.0.0.1:8001/v1/chat/completions"
payload={
    "model": "Qwen2.5-72B",
    "messages":[{"role":"user","content":"测试一下你能不能听到我？"}]
}

resp = requests.post(url, json=payload)
print(resp.text)